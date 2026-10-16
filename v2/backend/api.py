from .expiry_signals import expiry_signal, candle_is_fresh
from .smart_option_api import router as smart_option_router
from .expiry_momentum import expiry_watch_status
import sqlite3
from fastapi import FastAPI
from .database import DB_PATH
from .stock_universe import NIFTY_200

instrument_symbols = {key: symbol for symbol, key in NIFTY_200.items()}

app = FastAPI(title="NSE Momentum Scanner V2")
app.include_router(smart_option_router)


@app.get("/api/v2/premarket/evidence")
def get_premarket_evidence():
    """Fail-closed evidence contract for future verified source adapters.

    No automatic sources are configured. Never fabricate market observations.
    """
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from .premarket_sources import assess_verified_sources

    now = datetime.now(ZoneInfo("Asia/Kolkata"))
    prediction, sources = assess_verified_sources({}, now=now)
    missing_sources = [key for key, source in sources.items() if source['status'] != 'VERIFIED']
    forecast_ready = not missing_sources and prediction.status == "WAIT_LIVE_CONFIRMATION"
    return {
        "mode": "RESEARCH_ONLY",
        "order_execution_enabled": False,
        "status": prediction.status,
        "automatic_forecast_ready": forecast_ready,
        "missing_sources": missing_sources,
        "direction": prediction.direction,
        "evidence_score": prediction.evidence_score,
        "as_of_ist": prediction.as_of_ist,
        "sources": sources,
        "reasons": list(prediction.reasons),
        "note": "No verified automatic data sources configured; manual assessment is separate.",
    }

@app.get("/api/v2/trades")
def get_trades():
    con = sqlite3.connect(DB_PATH, timeout=10)
    con.row_factory = sqlite3.Row
    # Preserve every open trade; limit only closed history.
    rows = con.execute(
        "SELECT * FROM trades WHERE status != 'CLOSED' "
        "UNION ALL SELECT * FROM (SELECT * FROM trades WHERE status = 'CLOSED' "
        "ORDER BY id DESC LIMIT 100) ORDER BY id DESC"
    ).fetchall()
    con.close()
    items = [dict(row) for row in rows]
    from .trade_quote_freshness import quote_freshness
    for item in items:
        item["symbol"] = instrument_symbols.get(item["symbol"], item["symbol"])
        # Signal time and API refresh time are not verified quote timestamps.
        item["quote_freshness"] = quote_freshness()
        item["quote_timestamp_verified"] = False
    return items

from fastapi.responses import FileResponse

@app.get("/")
def dashboard():
    return FileResponse("v2/frontend/index.html")

@app.get("/api/v2/scanner")
def get_scanner_results():
    con = sqlite3.connect(DB_PATH, timeout=10)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT * FROM scanner_results ORDER BY updated_at DESC"
    ).fetchall()
    con.close()
    return [dict(row) for row in rows]


@app.get("/api/v2/history")
def get_daily_trade_history():
    import os
    import psycopg
    from psycopg.rows import dict_row
    from fastapi import HTTPException

    url = os.environ.get("DATABASE_URL")
    if not url:
        raise HTTPException(
            status_code=503,
            detail="PostgreSQL history database not configured"
        )

    try:
        with psycopg.connect(url, row_factory=dict_row) as con:
            rows = con.execute("""
                SELECT
                    id, trade_date, source_trade_id, symbol,
                    buy_time, buy_price, sell_time, sell_price,
                    quantity, pnl_per_share, pnl_total, pnl_pct,
                    status, buy_reason, exit_reason
                FROM daily_trade_history
                ORDER BY trade_date DESC, sell_time DESC
                LIMIT 500
            """).fetchall()

        for item in rows:
            item["symbol"] = instrument_symbols.get(
                item["symbol"], item["symbol"]
            )

        return rows

    except psycopg.Error as exc:
        print(f"PostgreSQL history API error: {exc}")
        raise HTTPException(
            status_code=503,
            detail="Trade history temporarily unavailable"
        ) from exc

@app.get("/history")
def history_page():
    return FileResponse("v2/frontend/history.html")

@app.get("/smart-option-buyer")
def smart_option_buyer_page():
    return FileResponse("v2/frontend/smart-option-buyer.html")


@app.get("/expiry-momentum")
def expiry_momentum_page():
    return FileResponse("v2/frontend/expiry-momentum.html")


@app.get("/api/v2/expiry-signals")
def get_expiry_signals():
    """Research-only expiry signals. No automatic orders."""
    rows = get_scanner_results()
    output = []
    for name in ("NIFTY 50", "SENSEX"):
        row = next((r for r in rows if r["symbol"] == name), None)
        from datetime import datetime
        from zoneinfo import ZoneInfo

        now = datetime.now(ZoneInfo("Asia/Kolkata"))
        status = expiry_watch_status(name, now)

        if status != "WATCH":
            reason = status
        elif row is None:
            reason = "DATA_UNAVAILABLE"
        elif not candle_is_fresh(row.get("updated_at"), now):
            reason = "STALE_DATA"
        else:
            reason = "SAFETY_CHECKS_PASSED"

        output.append({
            "index": name,
            "signal": "NO TRADE",
            "reason": reason,
            "price": row.get("price") if row else None,
            "updated_at": row.get("updated_at") if row else None,
        })
    return output


@app.get("/api/v2/nifty200-feed-health")
def nifty200_feed_health():
    """Read-only feed coverage, based on actual scanner-process ticks."""
    import json
    import time
    from pathlib import Path
    from datetime import datetime
    from zoneinfo import ZoneInfo
    now = time.time()
    ist = datetime.now(ZoneInfo("Asia/Kolkata"))
    base = {
        "universe_size": len(NIFTY_200),
        "checked_at_ist": ist.isoformat(),
        "market_session": "OPEN" if ist.weekday() < 5 and (9, 15) <= (ist.hour, ist.minute) <= (15, 30) else "CLOSED",
        "recent_tick_window_seconds": 120,
        "order_execution_enabled": False,
    }
    try:
        data = json.loads(Path("/tmp/nse_200_feed_health.json").read_text())
        observed = float(data["observed_at_epoch"])
        seen = data["last_tick_epoch"]
        if not isinstance(seen, dict) or observed > now + 30:
            raise ValueError("Invalid feed-health snapshot")
        valid_keys = set(NIFTY_200.values())
        observed_keys = valid_keys.intersection(seen)
        recent = sum(1 for k in observed_keys
                     if isinstance(seen[k], (int, float))
                     and 0 <= now - seen[k] <= 120)
        base.update(
            status="REPORTING" if now - observed <= 30 else "STALE_REPORT",
            snapshot_age_seconds=round(max(0, now - observed), 1),
            stocks_ever_observed=len(observed_keys),
            stocks_with_recent_ticks=recent,
            stocks_without_recent_ticks=len(valid_keys) - recent,
        )
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        base.update(status="NO_FEED_REPORT", stocks_ever_observed=0,
                    stocks_with_recent_ticks=0, stocks_without_recent_ticks=len(NIFTY_200))
    try:
        connection = json.loads(Path("/tmp/nse_200_connection_health.json").read_text())
        base["connection_last_event"] = connection.get("status", "UNKNOWN")
        base["connection_event_at_ist"] = connection.get("event_at_ist")
        base["connection_state_note"] = "Last recorded event; not a continuous connection guarantee"
    except (OSError, ValueError, TypeError):
        base["connection_last_event"] = "UNKNOWN"
        base["connection_state_note"] = "No connection event recorded"
    if base["market_session"] == "CLOSED" and base["status"] == "STALE_REPORT":
        base["status"] = "MARKET_CLOSED_TICK_REPORT_STALE"
    return base


@app.get("/api/v2/candle-feed-quality")
def candle_feed_quality():
    """Read-only observed candle continuity and volume; stale snapshots fail closed."""
    import json
    import time
    from pathlib import Path
    now = time.time()
    result = {
        "universe_size": len(NIFTY_200),
        "order_execution_enabled": False,
        "status": "NO_REPORT",
        "stocks_six_consecutive_today": 0,
        "stocks_with_recent_ticks": 0,
        "stocks_with_positive_last_candle_volume": 0,
        "stocks": {},
    }
    try:
        data = json.loads(Path("/tmp/nse_200_candle_quality.json").read_text())
        age = now - float(data["observed_at_epoch"])
        rows = data["stocks"]
        if not isinstance(rows, dict) or not 0 <= age <= 30:
            result["status"] = "STALE_REPORT"
            return result
        result["status"] = "REPORTING"
        result["snapshot_age_seconds"] = round(age, 1)
        result["stocks"] = rows
        recovery = data.get("gap_recovery")
        if isinstance(recovery, dict):
            result["gap_recovery"] = recovery
        from .quality_metrics import summarize_observed_history
        result.update(summarize_observed_history(rows))
        result["stocks_six_consecutive_today"] = sum(
            v.get("six_consecutive_today") is True for v in rows.values()
        )
        result["stocks_with_recent_ticks"] = sum(
            isinstance(v.get("last_tick_epoch"), (int, float))
            and 0 <= now - v["last_tick_epoch"] <= 120
            for v in rows.values()
        )
        result["stocks_missing_minute"] = sum(
            v.get("continuity_reason") == "MISSING_MINUTE" for v in rows.values()
        )
        result["stocks_overnight_gap"] = sum(
            v.get("continuity_reason") == "OVERNIGHT_GAP" for v in rows.values()
        )
        result["stocks_warmup"] = sum(
            v.get("continuity_reason") == "WARMUP" for v in rows.values()
        )
        result["stocks_with_positive_last_candle_volume"] = sum(
            isinstance(v.get("last_closed_volume"), (int, float))
            and v["last_closed_volume"] > 0
            for v in rows.values()
        )
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        pass
    return result


@app.get("/api/v2/top-momentum-setups")
def top_momentum_setups():
    """Rank verified fresh scanner candidates; research only, never place orders."""
    from datetime import datetime, time as clock_time, timedelta
    from math import isfinite
    from zoneinfo import ZoneInfo
    now = datetime.now(ZoneInfo("Asia/Kolkata"))
    session_open = now.weekday() < 5 and clock_time(9, 15) <= now.time() < clock_time(15, 30)
    output = {"status": "MARKET_CLOSED" if not session_open else "NO_QUALIFYING_SETUPS",
              "as_of_ist": now.isoformat(), "universe_size": len(NIFTY_200),
              "order_execution_enabled": False, "mode": "MANUAL_RESEARCH_ONLY",
              "setups": [], "fresh_stock_rows": 0, "rejected_stale_rows": 0}
    if not session_open:
        return output
    try:
        with sqlite3.connect(DB_PATH, timeout=5) as db:
            db.row_factory = sqlite3.Row
            rows = [dict(row) for row in db.execute(
                "SELECT symbol,updated_at,price,ema9,ema20,momentum,market,trend_5m,signal FROM scanner_results")]
    except sqlite3.Error:
        output["status"] = "SCANNER_DATABASE_UNAVAILABLE"
        return output
    eligible_symbols = set(NIFTY_200)
    for row in rows:
        if row["symbol"] not in eligible_symbols:
            continue
        try:
            stamp = datetime.strptime(row["updated_at"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=ZoneInfo("Asia/Kolkata"))
            if stamp.date() != now.date() or not timedelta(0) <= now - stamp <= timedelta(minutes=3):
                output["rejected_stale_rows"] += 1
                continue
            output["fresh_stock_rows"] += 1
            price, e9, e20, mom = (float(row[k]) for k in ("price", "ema9", "ema20", "momentum"))
            if not all(isfinite(v) for v in (price, e9, e20, mom)) or min(price, e9, e20) <= 0:
                continue
            if row["signal"] != "BUY" or row["trend_5m"] != "BULLISH" or not (price > e9 > e20 and mom > 0):
                continue
            # These are scanner-derived indicative levels, NOT ATR-validated executable orders.
            # Without an independently verified ATR, suppress targets and stops.
            score = round(mom + 100 * (e9 - e20) / price, 4)
            output["setups"].append({
                "symbol": row["symbol"], "last_price": round(price, 2),
                "indicative_entry": round(price, 2),
                "target_1": None, "target_2": None, "stop_loss": None,
                "levels_status": "ATR_LEVELS_NOT_VERIFIED",
                "momentum_pct": round(mom, 3), "ema9": round(e9, 2),
                "ema20": round(e20, 2), "trend_5m": row["trend_5m"],
                "candle_ist": row["updated_at"], "rank_score": score,
                "reasons": ["FRESH_COMPLETED_CANDLE", "BUY_SIGNAL",
                            "BULLISH_5M_TREND", "EMA9_ABOVE_EMA20", "POSITIVE_MOMENTUM"],
                "trade_status": "RESEARCH_ONLY",
            })
        except (ValueError, TypeError, OverflowError):
            continue
    output["setups"].sort(key=lambda item: (-item["rank_score"], item["symbol"]))
    output["setups"] = output["setups"][:5]
    if output["setups"]:
        output["status"] = "RESEARCH_SHORTLIST"
    return output


@app.get("/api/v2/nifty200-stock-board")
def nifty200_stock_board():
    """Display the configured NIFTY 200 universe even when market is closed."""
    from datetime import datetime, timedelta, time as clock_time
    from zoneinfo import ZoneInfo
    now = datetime.now(ZoneInfo("Asia/Kolkata"))
    open_now = now.weekday() < 5 and clock_time(9, 15) <= now.time() < clock_time(15, 30)
    stored = {}
    error = None
    try:
        with sqlite3.connect(DB_PATH, timeout=5) as db:
            db.row_factory = sqlite3.Row
            stored = {r["symbol"]: dict(r) for r in db.execute(
                "SELECT symbol,updated_at,price,momentum,signal,trend_5m FROM scanner_results")}
    except sqlite3.Error:
        error = "STOCK_DATA_UNAVAILABLE"
    stocks = []
    for symbol in sorted(NIFTY_200):
        row = stored.get(symbol) or {}
        fresh = False
        try:
            stamp = datetime.strptime(row["updated_at"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=ZoneInfo("Asia/Kolkata"))
            fresh = open_now and stamp.date() == now.date() and timedelta(0) <= now - stamp <= timedelta(minutes=3)
        except (ValueError, TypeError, KeyError):
            pass
        stocks.append({
            "symbol": symbol, "last_price": row.get("price"),
            "momentum_pct": row.get("momentum"),
            "last_candle_ist": row.get("updated_at"),
            "data_status": "LIVE_FRESH" if fresh else ("HISTORICAL" if row else "AWAITING_DATA"),
            "signal": row.get("signal") if fresh else None,
            "historical_signal": row.get("signal") if row and not fresh else None,
        })
    return {"status": error or ("MARKET_OPEN" if open_now else "MARKET_CLOSED"),
            "as_of_ist": now.isoformat(), "universe_size": len(stocks),
            "stocks_with_stored_data": sum(s["last_price"] is not None for s in stocks),
            "stocks_with_fresh_data": sum(s["data_status"] == "LIVE_FRESH" for s in stocks),
            "order_execution_enabled": False, "stocks": stocks}


@app.get("/api/v2/scalper-hourly-history")
def scalper_hourly_history(date: str):
    """Read-only hourly summary of persisted scanner candles; no inferred signals."""
    from datetime import date as date_type
    from fastapi import HTTPException
    try:
        day = date_type.fromisoformat(date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Date must be YYYY-MM-DD")
    try:
        with sqlite3.connect(DB_PATH, timeout=5) as db:
            db.row_factory = sqlite3.Row
            rows = [dict(r) for r in db.execute("""
                SELECT substr(candle_time, 12, 2) AS hour_ist,
                       COUNT(*) AS recorded_stock_candles,
                       COUNT(DISTINCT symbol) AS stocks_seen,
                       SUM(CASE WHEN signal='BUY' THEN 1 ELSE 0 END) AS buy_readings,
                       SUM(CASE WHEN signal='SELL' THEN 1 ELSE 0 END) AS sell_readings,
                       SUM(CASE WHEN signal='HOLD' THEN 1 ELSE 0 END) AS hold_readings
                FROM scanner_signal_history
                WHERE candle_time >= ? AND candle_time < ?
                  AND symbol IN (SELECT symbol FROM scanner_results WHERE symbol NOT IN ('NIFTY 50','SENSEX','BANK NIFTY'))
                GROUP BY substr(candle_time, 12, 2)
                ORDER BY hour_ist
            """, (date + " 00:00:00", date + " 23:59:59"))]
    except sqlite3.Error:
        return {"date":date,"status":"HISTORY_UNAVAILABLE","hours":[],"order_execution_enabled":False}
    return {"date":date,"status":"RECORDED" if rows else "NO_RECORDED_HISTORY",
            "note":"Counts are per-candle readings, not unique BUY trades. SQLite storage may be lost on Render restarts.",
            "hours":rows,"order_execution_enabled":False}


@app.get("/api/v2/quality-ratings")
def quality_ratings():
    """Research-only quality scores for 200 stocks and three tracked indices."""
    from datetime import datetime, timedelta, time as clock_time
    from math import isfinite
    from zoneinfo import ZoneInfo
    from .market_config import INDICES
    now = datetime.now(ZoneInfo("Asia/Kolkata"))
    session_open = now.weekday() < 5 and clock_time(9, 15) <= now.time() < clock_time(15, 30)
    universe = set(NIFTY_200) | set(INDICES)
    output = {"as_of_ist": now.isoformat(), "universe_size": len(universe),
              "status": "MARKET_CLOSED" if not session_open else "NO_VERIFIED_SETUPS",
              "mode": "RESEARCH_ONLY", "order_execution_enabled": False,
              "ratings": [], "unrated_count": len(universe)}
    if not session_open:
        return output
    try:
        with sqlite3.connect(DB_PATH, timeout=5) as db:
            db.row_factory = sqlite3.Row
            rows = [dict(row) for row in db.execute(
                "SELECT symbol,updated_at,price,ema9,ema20,momentum,trend_5m,signal FROM scanner_results")]
    except sqlite3.Error:
        output["status"] = "SCANNER_DATABASE_UNAVAILABLE"
        return output
    for row in rows:
        symbol = row["symbol"]
        if symbol not in universe:
            continue
        try:
            stamp = datetime.strptime(row["updated_at"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=ZoneInfo("Asia/Kolkata"))
            if stamp.date() != now.date() or not timedelta(0) <= now - stamp <= timedelta(minutes=3):
                continue
            price, e9, e20, mom = (float(row[k]) for k in ("price", "ema9", "ema20", "momentum"))
            if not all(isfinite(v) for v in (price, e9, e20, mom)) or min(price, e9, e20) <= 0:
                continue
            direction = row["signal"]
            if direction not in ("BUY", "SELL"):
                continue
            bullish = direction == "BUY"
            if not ((e9 > e20 and mom > 0) if bullish else (e9 < e20 and mom < 0)):
                continue
            index = symbol in INDICES
            trend = row["trend_5m"]
            if not index and trend != ("BULLISH" if bullish else "BEARISH"):
                continue
            # Heuristic, not a calibrated win probability. Only completed-candle
            # data available in scanner_results is scored.
            gap_pct = abs(e9 - e20) / price * 100
            score = min(100, round(40 + min(25, abs(mom) * 5)
                                   + min(20, gap_pct * 20)
                                   + (15 if trend == ("BULLISH" if bullish else "BEARISH") else 0)))
            output["ratings"].append({
                "symbol": symbol, "type": "INDEX" if index else "STOCK",
                "signal": direction, "rating": score,
                "rating_basis": "CANDLE_ONLY_HEURISTIC",
                "price": round(price, 2), "momentum": round(mom, 3),
                "trend_5m": trend, "candle_ist": row["updated_at"],
                "trade_status": "RESEARCH_ONLY", "volume_verified": False,
                "reason": "RVOL_AND_LIQUIDITY_NOT_INCLUDED_IN_SCORE",
            })
        except (TypeError, ValueError, OverflowError):
            continue
    output["ratings"].sort(key=lambda x: (-x["rating"], x["symbol"]))
    output["unrated_count"] = len(universe) - len(output["ratings"])
    if output["ratings"]:
        output["status"] = "CANDLE_RATINGS_AVAILABLE"
    return output


@app.get("/api/v2/signal-accuracy/daily")
def get_daily_signal_accuracy(date: str):
    """Read-only observed BUY-to-SELL paper ledger; no inferred executions."""
    from datetime import date as date_type
    from fastapi import HTTPException
    from .market_config import INDICES
    from .signal_accuracy_report import report_from_sqlite

    try:
        date_type.fromisoformat(date)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Date must be YYYY-MM-DD")
    try:
        result = report_from_sqlite(DB_PATH, date, index_symbols=set(INDICES))
    except sqlite3.Error as exc:
        print("SIGNAL_ACCURACY_READ_ERROR:", type(exc).__name__, flush=True)
        raise HTTPException(status_code=503, detail="Scanner signal history unavailable") from exc
    result["order_execution_enabled"] = False
    result["mode"] = "OBSERVED_SIGNALS_PAPER_ONLY"
    return result


@app.get("/api/v2/signal-accuracy/cumulative")
def get_cumulative_signal_accuracy(end_date: str):
    """Read-only cumulative observed signal cycles through an IST date."""
    import os
    from datetime import date as date_type
    from fastapi import HTTPException
    from .market_config import INDICES
    from .signal_cumulative_report import cumulative_report, fetch_cumulative_archive

    try:
        date_type.fromisoformat(end_date)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="end_date must be YYYY-MM-DD")
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise HTTPException(status_code=503, detail="PostgreSQL archive not configured")
    try:
        import psycopg
        with psycopg.connect(url, connect_timeout=5) as pg:
            rows = fetch_cumulative_archive(pg, end_date=end_date)
    except psycopg.Error as exc:
        print("SIGNAL_ARCHIVE_READ_ERROR:", type(exc).__name__, flush=True)
        raise HTTPException(status_code=503, detail="PostgreSQL signal archive unavailable") from exc
    try:
        result = cumulative_report(rows, index_symbols=set(INDICES))
    except (ValueError, TypeError, OverflowError) as exc:
        print("SIGNAL_ARCHIVE_INVALID_DATA:", type(exc).__name__, flush=True)
        raise HTTPException(status_code=503, detail="PostgreSQL signal archive contains invalid observations") from exc
    result["through_date_ist"] = end_date
    result["archive_reconciliation_status"] = "NOT_VERIFIED_FOR_THIS_REQUEST"
    result["archive_reading_scope"] = "BUY_SELL_ONLY"
    result["archive_empty_warning"] = (
        "No archived BUY/SELL readings found; this does not prove no scanner signals occurred."
        if result["observation_status"] == "NO_ARCHIVED_BUY_SELL_READINGS" else None
    )
    result["historical_completeness_verified"] = False
    result["archive_integrity_note"] = (
        "PostgreSQL signal values were not reconciled against SQLite for this request; "
        "missing or stale observations may change paper results."
    )
    result["order_execution_enabled"] = False
    return result


@app.get("/api/v2/signal-accuracy/cumulative.csv")
def download_cumulative_signal_accuracy(end_date: str):
    """Download observed completed calls, not broker trade confirmations."""
    from fastapi.responses import Response
    from .signal_accuracy_csv import closed_calls_csv
    report = get_cumulative_signal_accuracy(end_date)
    return Response(
        content=closed_calls_csv(report),
        media_type="text/csv",
        headers={"Content-Disposition":
                 'attachment; filename="paper_signal_accuracy_' + end_date + '.csv"'},
    )


@app.get("/api/v2/signal-accuracy/paper-pnl")
def get_signal_paper_pnl(
    end_date: str,
    notional_inr: float = 10000,
    round_trip_cost_pct: float = 0,
):
    """Explicit assumptions; no real broker P&L or index rupee estimates."""
    from fastapi import HTTPException
    from .signal_paper_pnl import model_stock_pnl
    report = get_cumulative_signal_accuracy(end_date)
    try:
        result = model_stock_pnl(
            report,
            notional_inr=notional_inr,
            round_trip_cost_pct=round_trip_cost_pct,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    result["through_date_ist"] = end_date
    result["order_execution_enabled"] = False
    return result


@app.get("/api/v2/signal-accuracy/archive-health")
def get_signal_archive_health():
    """Read-only process-local delivery status; never asserts full coverage."""
    import os
    from .signal_archive_delivery_health import archive_delivery_health

    result = archive_delivery_health()
    result["archive_enabled"] = os.getenv("ENABLE_SIGNAL_ARCHIVE_POSTGRES") == "1"
    result["mode"] = "OBSERVABILITY_ONLY"
    result["order_execution_enabled"] = False
    return result


@app.get("/api/v2/signal-accuracy/daily-summary.csv")
def download_daily_signal_accuracy_summary(end_date: str):
    """Download per-day closed signal calls; not executed broker trades."""
    from fastapi.responses import Response
    from .signal_daily_accuracy_csv import daily_accuracy_csv
    report = get_cumulative_signal_accuracy(end_date)
    return Response(
        content=daily_accuracy_csv(report),
        media_type="text/csv",
        headers={"Content-Disposition":
                 'attachment; filename="paper_signal_daily_summary_' + end_date + '.csv"'},
    )
