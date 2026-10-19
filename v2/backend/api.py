from .expiry_signals import expiry_signal, candle_is_fresh
from .smart_option_api import router as smart_option_router
from .expiry_momentum import expiry_watch_status
import sqlite3
from fastapi import FastAPI
from .database import DB_PATH
from .stock_universe import NIFTY_200
from .persisted_learning import learning_report_from_records

instrument_symbols = {key: symbol for symbol, key in NIFTY_200.items()}

app = FastAPI(title="NSE Momentum Scanner V2")
app.include_router(smart_option_router)

@app.get("/api/v2/premarket-data")
def get_premarket_data():
    """Read Upstox global-index quotes for pre-market context, never trading signals."""
    import gzip
    import json
    import os
    import time
    import urllib.parse
    import urllib.request
    from datetime import datetime, timezone
    from fastapi import HTTPException

    now = time.monotonic()
    cache = getattr(get_premarket_data, "_cache", None)
    cache_at = getattr(get_premarket_data, "_cache_at", 0.0)
    if cache and now - cache_at < 60:
        return {**cache, "cache_age_seconds": round(now - cache_at, 1)}

    token = os.environ.get("UPSTOX_ACCESS_TOKEN")
    if not token:
        return {"status": "UPSTOX_TOKEN_UNAVAILABLE", "source": "Upstox Global Instruments",
                "as_of": None, "instruments": [], "order_execution_enabled": False}

    try:
        catalog = getattr(get_premarket_data, "_catalog", None)
        catalog_at = getattr(get_premarket_data, "_catalog_at", 0.0)
        if not catalog or now - catalog_at >= 86400:
            request = urllib.request.Request(
                "https://assets.upstox.com/market-quote/instruments/exchange/global.json.gz",
                headers={"User-Agent": "NSE-Momentum-Scanner/1.0", "Accept": "application/gzip"},
            )
            with urllib.request.urlopen(request, timeout=5) as response:
                raw = gzip.decompress(response.read())
            catalog = json.loads(raw.decode("utf-8"))
            if not isinstance(catalog, list):
                raise ValueError("Unexpected Upstox global instruments format")
            get_premarket_data._catalog = catalog
            get_premarket_data._catalog_at = now

        wanted = {
            "GIFT NIFTY": ("GIFT NIFTY",),
            "S&P 500": ("S&P 500", "S&P"),
            "DOW JONES": ("DOW JONES",),
            "NASDAQ": ("NASDAQ", "US TECH 100"),
            "FTSE 100": ("FTSE 100",),
            "DAX": ("DAX",),
            "NIKKEI 225": ("NIKKEI 225",),
            "HANG SENG": ("HANG SENG",),
        }
        selected = {}
        for instrument in catalog:
            if not isinstance(instrument, dict) or instrument.get("segment") != "GLOBAL_INDEX":
                continue
            aliases = {str(instrument.get(field, "")).strip().upper()
                       for field in ("name", "trading_symbol")}
            key = instrument.get("instrument_key")
            if not isinstance(key, str) or not key.startswith("GLOBAL_INDEX|"):
                continue
            for display_name, candidates in wanted.items():
                if display_name not in selected and aliases.intersection(candidates):
                    selected[display_name] = {"key": key, "latency": instrument.get("latency")}
        if "GIFT NIFTY" not in selected:
            raise ValueError("GIFT NIFTY is not present in the Upstox global instruments file")

        keys = [item["key"] for item in selected.values()]
        query = urllib.parse.urlencode({"instrument_key": ",".join(keys)})
        request = urllib.request.Request(
            "https://api.upstox.com/v3/market-quote/quotes?" + query,
            headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if not isinstance(payload, dict) or payload.get("status") != "success" or not isinstance(payload.get("data"), dict):
            raise ValueError("Upstox quote response was not successful")

        quotes = payload["data"]
        instruments = []
        for name, meta in selected.items():
            quote_key = meta["key"].replace("|", ":")
            quote = quotes.get(quote_key)
            if not isinstance(quote, dict):
                instruments.append({"name": name, "status": "NO_QUOTE", "latency": meta["latency"]})
                continue
            try:
                price = float(quote["last_price"])
                previous_close = float(quote["prev_close_price"])
                trade_ms = int(float(quote["last_trade_time"]))
                if price <= 0 or previous_close <= 0 or trade_ms <= 0:
                    raise ValueError("Invalid quote values")
                quote_time = datetime.fromtimestamp(trade_ms / 1000, timezone.utc).isoformat()
                change = price - previous_close
                instruments.append({
                    "name": name, "status": "QUOTED", "price": price,
                    "previous_close": previous_close, "change": change,
                    "change_pct": change / previous_close * 100,
                    "last_trade_at": quote_time, "latency": meta["latency"],
                })
            except (KeyError, TypeError, ValueError, OverflowError, OSError):
                instruments.append({"name": name, "status": "INVALID_QUOTE", "latency": meta["latency"]})

        result = {"status": "UPSTOX_QUOTES_AVAILABLE", "source": "Upstox Full Market Quotes V3",
                  "as_of": datetime.now(timezone.utc).isoformat(), "instruments": instruments,
                  "order_execution_enabled": False}
        get_premarket_data._cache = result
        get_premarket_data._cache_at = now
        return {**result, "cache_age_seconds": 0}
    except Exception as exc:
        # Never replace missing or failed upstream data with estimates.
        print("PREMARKET_UPSTOX_QUOTES_UNAVAILABLE:", type(exc).__name__, flush=True)
        if cache:
            return {**cache, "status": "UPSTOX_REFRESH_FAILED_USING_CACHED_QUOTE",
                    "cache_age_seconds": round(max(0, now - cache_at), 1)}
        return {"status": "UPSTOX_QUOTES_UNAVAILABLE", "source": "Upstox Full Market Quotes V3",
                "as_of": None, "instruments": [], "order_execution_enabled": False}

@app.get("/api/v2/trades")
def get_trades():
    """Return the same persistent recorded history used by Positions and P&L."""
    rows = get_daily_trade_history()
    return [
        {
            "id": row["id"],
            "symbol": row["symbol"],
            "status": row["status"],
            "entry_price": row["buy_price"],
            "signal_time": row["buy_time"],
            "exit_price": row["sell_price"],
            "exit_time": row["sell_time"],
            "pnl_total": row["pnl_total"],
        }
        for row in rows[:100]
    ]

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


@app.get("/api/v2/scanner-status")
def get_scanner_status():
    """Read-only stored-result visibility; does not claim live feed freshness."""
    from fastapi import HTTPException
    try:
        with sqlite3.connect(DB_PATH, timeout=10) as con:
            count, latest = con.execute(
                "SELECT COUNT(*), MAX(updated_at) FROM scanner_results"
            ).fetchone()
    except sqlite3.Error as exc:
        raise HTTPException(
            status_code=503, detail="Scanner result storage unavailable"
        ) from exc
    return {
        "status": "STORED_RESULTS_AVAILABLE" if count else "NO_STORED_RESULTS",
        "result_count": count,
        "latest_result_updated_at": latest,
        "live_feed_verified": False,
        "signal_freshness_verified": False,
        "order_execution_enabled": False,
    }


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


@app.get("/api/v2/signal-activity")
def signal_activity():
    """Read-only signal lifecycle from persisted trade history, never infer execution."""
    import os
    from fastapi import HTTPException
    url = os.environ.get("DATABASE_URL")
    if not url:
        return {"status": "HISTORY_STORAGE_NOT_CONFIGURED", "active": [], "completed": [],
                "source": "daily_trade_history", "order_execution_enabled": False}
    try:
        import psycopg
        from psycopg.rows import dict_row
        with psycopg.connect(url, row_factory=dict_row, connect_timeout=5) as con:
            records = con.execute("""
                SELECT id, symbol, buy_time, buy_price, sell_time, sell_price,
                       quantity, pnl_per_share, pnl_total, pnl_pct, status,
                       buy_reason, exit_reason, trade_date
                FROM daily_trade_history
                ORDER BY GREATEST(COALESCE(sell_time, buy_time), buy_time) DESC NULLS LAST, id DESC LIMIT 501
            """).fetchall()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Persisted signal history unavailable") from exc
    history_truncated = len(records) > 500
    records = records[:500]
    active, completed = [], []
    incomplete_records = 0
    for record in records:
        row = dict(record)
        row["symbol"] = instrument_symbols.get(row["symbol"], row["symbol"])
        # A recorded entry without exit is an active *record*, not proof of an executed order.
        if row["buy_price"] is None:
            incomplete_records += 1
            continue
        if row["sell_time"] is not None and row["sell_price"] is not None:
            row["display_status"] = "SELL / EXIT"
            completed.append(row)
        elif row["sell_time"] is None and row["sell_price"] is None:
            row["display_status"] = "BUY ACTIVE"
            active.append(row)
        else:
            incomplete_records += 1
    return {"status": "RECORDED_HISTORY", "history_limit": 500, "history_truncated": history_truncated, "incomplete_records": incomplete_records, "active": active, "completed": completed,
            "source": "daily_trade_history", "mode": "RECORDED_SIGNALS_NOT_BROKER_EXECUTIONS",
            "order_execution_enabled": False}


@app.get("/api/v2/pnl-history")
def pnl_history():
    """Return a complete, read-only seven-day IST aggregate of recorded exits."""
    import os
    from datetime import datetime, time, timedelta
    from zoneinfo import ZoneInfo
    from fastapi import HTTPException

    source = "daily_trade_history"
    url = os.environ.get("DATABASE_URL")
    if not url:
        return {
            "status": "HISTORY_STORAGE_NOT_CONFIGURED",
            "source": source,
            "days_requested": 7,
            "complete": False,
            "days": [],
            "order_execution_enabled": False,
        }

    ist = ZoneInfo("Asia/Kolkata")
    today = datetime.now(ist).date()
    first_day = today - timedelta(days=6)
    start_at = datetime.combine(first_day, time.min, tzinfo=ist)
    end_at = datetime.combine(today + timedelta(days=1), time.min, tzinfo=ist)
    try:
        import psycopg
        from psycopg.rows import dict_row
        with psycopg.connect(url, row_factory=dict_row, connect_timeout=5) as con:
            rows = con.execute("""
                SELECT
                    (sell_time AT TIME ZONE 'Asia/Kolkata')::date AS pnl_date,
                    COUNT(*) AS exit_count,
                    COUNT(*) FILTER (WHERE
                        buy_time IS NULL OR buy_price IS NULL OR sell_price IS NULL
                        OR quantity IS NULL OR buy_price <= 0 OR sell_price <= 0
                        OR quantity <= 0 OR sell_time < buy_time
                        OR buy_time > NOW() + INTERVAL '1 minute'
                        OR sell_time > NOW() + INTERVAL '1 minute'
                    ) AS invalid_count,
                    SUM(CASE WHEN
                        buy_time IS NOT NULL AND buy_price IS NOT NULL
                        AND sell_price IS NOT NULL AND quantity IS NOT NULL
                        AND buy_price > 0 AND sell_price > 0 AND quantity > 0
                        AND sell_time >= buy_time
                        AND buy_time <= NOW() + INTERVAL '1 minute'
                        AND sell_time <= NOW() + INTERVAL '1 minute'
                        THEN (sell_price - buy_price) * quantity
                        ELSE 0 END) AS total_pnl,
                    SUM(CASE WHEN
                        buy_time IS NOT NULL AND buy_price IS NOT NULL
                        AND sell_price IS NOT NULL AND quantity IS NOT NULL
                        AND buy_price > 0 AND sell_price > 0 AND quantity > 0
                        AND sell_time >= buy_time
                        AND buy_time <= NOW() + INTERVAL '1 minute'
                        AND sell_time <= NOW() + INTERVAL '1 minute'
                        THEN
                            LEAST(20, buy_price * quantity * 0.001)
                            + LEAST(20, sell_price * quantity * 0.001)
                            + sell_price * quantity * 0.00025
                            + buy_price * quantity * 0.00003
                            + (buy_price + sell_price) * quantity * 0.0000307
                            + (buy_price + sell_price) * quantity * 0.000001
                            + (buy_price + sell_price) * quantity * 0.000000001
                            + 0.18 * (
                                LEAST(20, buy_price * quantity * 0.001)
                                + LEAST(20, sell_price * quantity * 0.001)
                                + (buy_price + sell_price) * quantity * 0.0000307
                                + (buy_price + sell_price) * quantity * 0.000000001
                            )
                        ELSE 0 END) AS estimated_costs
                FROM daily_trade_history
                WHERE sell_time >= %s AND sell_time < %s
                GROUP BY pnl_date
                ORDER BY pnl_date
            """, (start_at, end_at)).fetchall()

        by_day = {row["pnl_date"].isoformat(): row for row in rows}
        days = []
        complete = True
        for offset in range(7):
            day = (first_day + timedelta(days=offset)).isoformat()
            row = by_day.get(day)
            exits = int(row["exit_count"]) if row else 0
            invalid = int(row["invalid_count"]) if row else 0
            total = row["total_pnl"] if row else None
            costs = row["estimated_costs"] if row else None
            if invalid or (exits and total is None):
                total = None
                costs = None
                complete = False
            elif total is not None and costs is not None:
                total = float(total)
                costs = float(costs)
                if not __import__("math").isfinite(total) or not __import__("math").isfinite(costs):
                    total = None
                    costs = None
                    complete = False
            else:
                total = None
                costs = None
            net = total - costs if total is not None and costs is not None else None
            days.append({
                "date": day,
                "exit_count": exits,
                "invalid_count": invalid,
                "total_pnl": total,
                "estimated_costs": costs,
                "estimated_net_pnl": net,
            })
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Persisted P&L history unavailable") from exc

    return {
        "status": "AGGREGATED_HISTORY",
        "source": source,
        "days_requested": 7,
        "complete": complete,
        "days": days,
        "mode": "RECORDED_SIGNALS_NOT_BROKER_EXECUTIONS",
        "order_execution_enabled": False,
        "cost_estimate": {
            "schedule": "Upstox NSE equity intraday indicative rates",
            "assumptions": "One entry and one exit order per recorded lifecycle; estimated from recorded prices and quantity; excludes slippage and per-charge rounding; actual charges depend on executed orders and account tariff.",
        },
    }


@app.get("/api/v2/decision-learning")
def decision_learning_status():
    """Read-only learning summary from the same durable ledger as P&L."""
    import os
    import psycopg
    from psycopg.rows import dict_row
    from fastapi import HTTPException

    url = os.environ.get("DATABASE_URL")
    if not url:
        return {
            "status": "HISTORY_STORAGE_NOT_CONFIGURED",
            "source": "daily_trade_history",
            "closed_records_seen": 0,
            "complete_records": 0,
            "invalid_records_excluded": 0,
            "gross_loss_count": 0,
            "gross_loss_reasons": {},
            "gross_losses_by_nifty_recovery_state": {},
            "model": {"status": "HISTORY_STORAGE_NOT_CONFIGURED"},
            "recommendations_enabled": False,
            "broker_orders_enabled": False,
            "notes": ["Persistent history is unavailable; no outcomes were inferred."],
        }
    try:
        with psycopg.connect(url, row_factory=dict_row, connect_timeout=5) as con:
            rows = con.execute("""
                SELECT buy_time, buy_price, sell_time, sell_price,
                       quantity, pnl_total, exit_reason
                FROM daily_trade_history
                WHERE sell_time IS NOT NULL
                ORDER BY sell_time, id
            """).fetchall()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Persisted learning history unavailable") from exc

    return learning_report_from_records(rows)

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
    if base["market_session"] == "CLOSED":
        if base["status"] == "STALE_REPORT":
            base["status"] = "MARKET_CLOSED_TICK_REPORT_STALE"
        elif base["status"] == "NO_FEED_REPORT":
            base["status"] = "MARKET_CLOSED_NO_FEED_REPORT"
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


@app.get("/api/v2/top-volume-surge")
def top_volume_surge():
    """Rank fresh stock RVOL using actual one-minute candle volumes only."""
    from datetime import datetime, timedelta, time as clock_time
    from math import isfinite
    from zoneinfo import ZoneInfo

    now = datetime.now(ZoneInfo("Asia/Kolkata"))
    session_open = now.weekday() < 5 and clock_time(9, 15) <= now.time() < clock_time(15, 30)
    threshold = 1.5
    output = {
        "status": "MARKET_CLOSED" if not session_open else "NO_VERIFIED_VOLUME_SURGES",
        "as_of_ist": now.isoformat(),
        "universe_size": len(NIFTY_200),
        "threshold_rvol": threshold,
        "comparison_basis": "Latest completed 1-minute candle volume / mean of prior 19 consecutive completed 1-minute candles",
        "surges": [],
        "fresh_stock_rows": 0,
        "verified_volume_rows": 0,
        "order_execution_enabled": False,
    }
    if not session_open:
        return output

    try:
        with sqlite3.connect(DB_PATH, timeout=5) as db:
            db.row_factory = sqlite3.Row
            rows = [dict(row) for row in db.execute(
                "SELECT symbol,updated_at,price,signal,trend_5m,rvol,current_volume,baseline_volume FROM scanner_results"
            )]
    except sqlite3.Error:
        output["status"] = "SCANNER_DATABASE_UNAVAILABLE"
        return output

    eligible_symbols = set(NIFTY_200)
    for row in rows:
        if row["symbol"] not in eligible_symbols:
            continue
        try:
            stamp = datetime.strptime(row["updated_at"], "%Y-%m-%d %H:%M:%S").replace(
                tzinfo=ZoneInfo("Asia/Kolkata")
            )
            if stamp.date() != now.date() or not timedelta(0) <= now - stamp <= timedelta(minutes=3):
                continue
            output["fresh_stock_rows"] += 1
            rvol, current_volume, baseline_volume = (
                float(row[name]) for name in ("rvol", "current_volume", "baseline_volume")
            )
            if (not all(isfinite(value) for value in (rvol, current_volume, baseline_volume))
                    or current_volume < 0 or baseline_volume <= 0):
                continue
            output["verified_volume_rows"] += 1
            if rvol < threshold:
                continue
            price = float(row["price"])
            if not isfinite(price) or price <= 0:
                continue
            output["surges"].append({
                "symbol": row["symbol"],
                "last_price": round(price, 2),
                "signal": row["signal"],
                "trend_5m": row["trend_5m"],
                "relative_volume": round(rvol, 2),
                "current_volume": round(current_volume, 2),
                "baseline_volume": round(baseline_volume, 2),
                "candle_ist": row["updated_at"],
                "volume_basis": "1-minute; prior 19 consecutive completed candles",
                "trade_status": "RESEARCH_ONLY",
            })
        except (TypeError, ValueError, OverflowError):
            continue

    output["surges"].sort(key=lambda item: (-item["relative_volume"], item["symbol"]))
    output["surges"] = output["surges"][:10]
    if output["surges"]:
        output["status"] = "VERIFIED_VOLUME_SURGES_AVAILABLE"
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
              "ratings": [], "historical_ratings": [],
              "historical_ratings_max_age_days": 30,
              "unrated_count": len(universe)}
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
            age = now - stamp
            if not timedelta(0) <= age <= timedelta(days=30):
                continue
            price, e9, e20, mom = (float(row[k]) for k in ("price", "ema9", "ema20", "momentum"))
            if not all(isfinite(v) for v in (price, e9, e20, mom)) or min(price, e9, e20) <= 0:
                continue
            direction = row["signal"]
            fresh = session_open and stamp.date() == now.date() and age <= timedelta(minutes=3)
            index = symbol in INDICES
            trend = row["trend_5m"]
            if direction not in ("BUY", "SELL"):
                # After close, scanner rows may be deliberately stored as WAITING
                # even though EMA and momentum values remain available. Preserve
                # that distinction: derive a historical bias for display only.
                if fresh:
                    continue
                if e9 > e20 and mom > 0:
                    direction = "BUY"
                elif e9 < e20 and mom < 0:
                    direction = "SELL"
                else:
                    direction = "WAIT"
            bullish = direction == "BUY"
            bearish = direction == "SELL"
            if (bullish and not (e9 > e20 and mom > 0)) or (bearish and not (e9 < e20 and mom < 0)):
                continue
            if fresh and not index and trend != ("BULLISH" if bullish else "BEARISH"):
                continue
            # Heuristic, not a calibrated win probability. Historical scores
            # describe stored indicator alignment, never a current setup.
            gap_pct = abs(e9 - e20) / price * 100
            trend_aligned = direction in ("BUY", "SELL") and trend == ("BULLISH" if bullish else "BEARISH")
            score = min(100, round(40 + min(25, abs(mom) * 5)
                                   + min(20, gap_pct * 20)
                                   + (15 if trend_aligned else 0)))
            historical = not fresh
            rating = {
                "symbol": symbol, "type": "INDEX" if index else "STOCK",
                "signal": direction, "rating": score,
                "rating_basis": "HISTORICAL_INDICATOR_HEURISTIC" if historical else "CANDLE_ONLY_HEURISTIC",
                "directional_bias": "BULLISH" if bullish else "BEARISH" if bearish else "NEUTRAL",
                "price": round(price, 2), "momentum": round(mom, 3),
                "trend_5m": trend, "candle_ist": row["updated_at"],
                "trade_status": "RESEARCH_ONLY", "volume_verified": False,
                "reason": "STORED_EMA_AND_MOMENTUM_ONLY; NOT A LIVE SIGNAL",
            }
            if fresh:
                output["ratings"].append(rating)
            else:
                output["historical_ratings"].append({
                    **rating,
                    "data_status": "HISTORICAL_LAST_STORED_CANDLE",
                })
        except (TypeError, ValueError, OverflowError):
            continue
    output["ratings"].sort(key=lambda x: (-x["rating"], x["symbol"]))
    output["historical_ratings"].sort(key=lambda x: (-x["rating"], x["symbol"]))
    output["historical_ratings_count"] = len(output["historical_ratings"])
    output["unrated_count"] = len(universe) - len(output["ratings"])
    if output["ratings"]:
        output["status"] = "CANDLE_RATINGS_AVAILABLE"
    return output


