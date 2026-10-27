"""Server-owned daily volume shortlist and paper-only BUY -> SELL lifecycle."""
import json
import os
from math import isfinite
import sqlite3
from dataclasses import replace
from datetime import datetime, timedelta
from threading import Event, Lock, Thread
from zoneinfo import ZoneInfo
from .database import DB_PATH
from .experimental_15m_stoch_rsi import Settings, evaluate, _ema, _stoch_rsi
from .experimental_15m_volume import verified_15m_same_slot_average
from .experimental_15m_upstox_runner import CompressedHistoryCache, fetch_symbol, _parse_rows
from .stock_universe import NIFTY_200

IST = ZoneInfo('Asia/Kolkata')


def empty_day(day):
    return dict(session_date=str(day), mode='PAPER', source='UPSTOX_HISTORY_V3',
                status='AWAITING_SCAN', selected=[], completed=[], fetch_errors={},
                processed_count=0, requested_count=200, order_execution_enabled=False)


class ShortlistStore:
    """Local transactional checkpoint, backed by the configured PostgreSQL database."""
    def __init__(self, path=DB_PATH, pg_url=None):
        self.path = path
        self.pg_url = os.environ.get('DATABASE_URL') if pg_url is None else pg_url
        self.persistence = 'LOCAL_ONLY'
        self.error = None
        self.lock = Lock()
        path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(path, timeout=10) as db:
            db.execute('CREATE TABLE IF NOT EXISTS daily_paper_shortlist (session_date TEXT PRIMARY KEY, payload TEXT NOT NULL)')

    def read(self, day):
        with sqlite3.connect(self.path, timeout=10) as db:
            row = db.execute('SELECT payload FROM daily_paper_shortlist WHERE session_date=?', (str(day),)).fetchone()
        return json.loads(row[0]) if row else empty_day(day)

    def carry_active(self, state):
        if state.get('scan_started_at_ist'):
            return
        with sqlite3.connect(self.path, timeout=10) as db:
            row = db.execute('SELECT payload FROM daily_paper_shortlist WHERE session_date < ? ORDER BY session_date DESC LIMIT 1', (state['session_date'],)).fetchone()
        if row:
            state['selected'] = [dict(x, carried_from_session=json.loads(row[0])['session_date'])
                                 for x in json.loads(row[0])['selected'] if x.get('buy_time')]

    def write(self, value, *, durable=False):
        raw = json.dumps(value, allow_nan=False)
        with self.lock, sqlite3.connect(self.path, timeout=10) as db:
            db.execute('INSERT INTO daily_paper_shortlist VALUES (?,?) ON CONFLICT(session_date) DO UPDATE SET payload=excluded.payload', (value['session_date'], raw))
        if durable and self.pg_url:
            try:
                import psycopg
                with psycopg.connect(self.pg_url, connect_timeout=5, options='-c statement_timeout=5000') as db:
                    db.execute('INSERT INTO daily_paper_shortlist VALUES (%s,%s) ON CONFLICT(session_date) DO UPDATE SET payload=excluded.payload', (value['session_date'], raw))
                self.persistence, self.error = 'POSTGRES_BACKED', None
            except Exception as exc:
                self.error = type(exc).__name__

    def restore(self):
        if not self.pg_url:
            return
        import psycopg
        with psycopg.connect(self.pg_url, connect_timeout=5, options='-c statement_timeout=5000') as db:
            db.execute('CREATE TABLE IF NOT EXISTS daily_paper_shortlist (session_date TEXT PRIMARY KEY, payload TEXT NOT NULL)')
            rows = db.execute('SELECT payload FROM daily_paper_shortlist ORDER BY session_date DESC LIMIT 10').fetchall()
        for row in rows:
            restored = json.loads(row[0])
            local = self.read(restored['session_date'])
            def checkpoint(value):
                return max(value.get('scan_started_at_ist', ''), value.get('scan_finished_at_ist', ''))
            if checkpoint(restored) > checkpoint(local):
                self.write(restored)
        self.persistence = 'POSTGRES_BACKED'


def advance_day(state, symbol, bars, history, now):
    """Qualify once; reanalyse retained stocks without reapplying the entry-volume gate."""
    active = {row['symbol']: row for row in state['selected']}
    if any(row['symbol'] == symbol for row in state['completed']):
        return
    old = active.get(symbol)
    if not bars or bars[-1]['timestamp'].date() != now.date():
        return
    latest = bars[-1]
    values = [float(latest[k]) for k in ('open','high','low','close','volume')]
    opn, high, low, close, volume = values
    if not all(isfinite(v) for v in values) or min(opn,high,low,close) <= 0 or volume < 0 or high < max(opn,close) or low > min(opn,close):
        return
    stamp = latest['timestamp'].isoformat()
    if old and old.get('candle_time', '') >= stamp:
        return  # duplicate polling cannot duplicate BUY or SELL records
    baseline = verified_15m_same_slot_average(latest, history, require_full_sessions=True)
    rvol = latest['volume'] / baseline if baseline else None
    if old is None and (rvol is None or rvol < 1.5):
        return
    row = dict(old or dict(symbol=symbol, first_qualified_candle=stamp,
                          qualification_rvol=round(rvol, 3), lifecycle='SHORTLISTED'))
    result = evaluate(bars, now=now, same_slot_average_volume=baseline,
                      settings=replace(Settings(), min_rvol=0))
    if len(bars) >= 52 and all(isfinite(float(b['close'])) and float(b['close']) > 0 for b in bars):
        closes = [float(b['close']) for b in bars]
        k, d = _stoch_rsi(closes, Settings())
        result.update(ema20=round(_ema(closes, 20)[-1], 4),
                      ema50=round(_ema(closes, 50)[-1], 4),
                      stoch_k=round(k[-1], 2), stoch_d=round(d[-1], 2))
    row.update(candle_time=stamp, relative_volume=round(rvol, 3) if rvol is not None else None,
               candle={k:latest[k] for k in ('open','high','low','close','volume')},
               signal=result['signal'], reason=result['reason'], details=result,
               volume_tier='STRONG' if rvol is not None and rvol >= 2 else 'RETAINED')
    event_time = (latest['timestamp'] + timedelta(minutes=15)).replace(tzinfo=IST).isoformat()
    if result['signal'] == 'PAPER_BUY' and not row.get('buy_time'):
        row.update(buy_time=event_time, buy_price=latest['close'], lifecycle='BUY_ACTIVE')
    if result['signal'] == 'PAPER_SELL':
        row.update(sell_time=event_time, sell_price=latest['close'], lifecycle='COMPLETED',
                   completion_basis='BUY_TO_SELL' if row.get('buy_time') else 'SELL_WITHOUT_PRIOR_BUY')
        row['gross_pnl_per_share'] = latest['close'] - row['buy_price'] if row.get('buy_price') else None
        state['completed'].append(row)
        active.pop(symbol, None)
    else:
        active[symbol] = row
    state['selected'] = sorted(active.values(), key=lambda x:x['symbol'])


class DailyShortlist:
    def __init__(self, store=None):
        self.store = store or ShortlistStore()
        self.stop = Event()
        self.thread = None
        self.cache = CompressedHistoryCache()
        self.day = None
        self.last_slot = None
        self.last_error = None
        self.retry_at = None

    def start(self):
        if self.thread is None:
            self.thread = Thread(target=self.loop, daemon=True, name='daily-15m-shortlist')
            self.thread.start()

    def snapshot(self, now=None, session_date=None):
        now = now or datetime.now(IST)
        value = self.store.read(session_date or now.date())
        value.update(worker_error=self.last_error, selected_count=len(value['selected']), completed_count=len(value['completed']),
                     persistence_status=self.store.persistence, persistence_error=self.store.error,
                     as_of_ist=now.isoformat())
        # Keep recorded signals as history, never present a stale signal as a current call.
        for row in value['selected']:
            try:
                stamp = datetime.fromisoformat(row['candle_time']).replace(tzinfo=IST)
                age = (now - stamp - timedelta(minutes=15)).total_seconds()
                row['signal_fresh'] = now.weekday() < 5 and 0 <= age <= 18 * 60 and now.hour * 60 + now.minute < 930
            except (KeyError, ValueError):
                row['signal_fresh'] = False
        return value

    def scan(self, now, api):
        local = now.astimezone(IST).replace(tzinfo=None)
        if self.day != local.date():
            self.cache = CompressedHistoryCache()
            self.day = local.date()
        state = self.store.read(local.date())
        self.store.carry_active(state)
        state.update(status='RUNNING', processed_count=0, fetch_errors={}, scan_started_at_ist=now.isoformat())
        self.store.write(state)
        blocked = False
        for symbol, key in NIFTY_200.items():
            try:
                bars, history = fetch_symbol(api, key, now=local, historical_cache=self.cache)
                # A month can contain fewer than 20 trading sessions. Fetch earlier
                # bounded chunks, rather than substituting an incomplete baseline.
                if len({b['timestamp'].date() for b in history}) < 20:
                    for _ in range(2):
                        end = min(b['timestamp'].date() for b in history) - timedelta(days=1) if history else local.date()-timedelta(days=31)
                        extra = api.get_historical_candle_data1(key, 'minutes', '15', str(end), str(end-timedelta(days=28)))
                        history = _parse_rows(extra.data.candles) + history
                        if len({b['timestamp'].date() for b in history}) >= 20:
                            break
                    self.cache[key] = history
                    bars = history + [b for b in bars if b['timestamp'].date() == local.date()]
                # Replay each completed candle in order, so qualification earlier
                # in the day survives a restart or opening the page later.
                for index, bar in enumerate(bars):
                    if bar['timestamp'].date() == local.date():
                        advance_day(state, symbol, bars[:index+1], history,
                                    local)
                state['fetch_errors'].pop(symbol, None)
            except Exception as exc:
                state['fetch_errors'][symbol] = type(exc).__name__ + ':' + str(getattr(exc, 'status', 'UNKNOWN'))
                if getattr(exc, 'retry_after', 0):
                    self.retry_at = now + timedelta(seconds=max(60, exc.retry_after))
                    state.update(status='PROVIDER_COOLDOWN', retry_at_ist=self.retry_at.isoformat())
                    blocked = True
                    break
            state['processed_count'] += 1
            if state['processed_count'] % 10 == 0:
                self.store.write(state, durable=True)
        state.update(scan_finished_at_ist=datetime.now(IST).isoformat())
        if not blocked:
            state['status'] = 'PARTIAL_DATA' if state['fetch_errors'] else 'READY'
        self.store.write(state, durable=True)
        return not blocked

    def loop(self):
        try:
            self.store.restore()
        except Exception as exc:
            self.store.error = type(exc).__name__
        while not self.stop.is_set():
            now = datetime.now(IST)
            minute = now.hour * 60 + now.minute
            slot = (str(now.date()), (minute - 555) // 15)
            if now.weekday() < 5 and 570 <= minute <= 945 and slot != self.last_slot and (self.retry_at is None or now >= self.retry_at):
                try:
                    from .history_transport import history_api
                    if self.scan(now, history_api()):
                        self.last_slot = slot
                    self.last_error = None
                except Exception as exc:
                    self.last_error = type(exc).__name__
            self.stop.wait(20)
