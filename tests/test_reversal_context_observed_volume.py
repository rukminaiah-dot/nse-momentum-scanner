import sqlite3
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

try:
    from v2.backend import reversal_context
except ModuleNotFoundError as exc:
    if exc.name != "fastapi":
        raise
    import sys
    import types

    fastapi_stub = types.ModuleType("fastapi")

    class APIRouterStub:
        def get(self, *_args, **_kwargs):
            return lambda handler: handler

    fastapi_stub.APIRouter = APIRouterStub
    sys.modules["fastapi"] = fastapi_stub
    from v2.backend import reversal_context


IST = ZoneInfo("Asia/Kolkata")


class ClosedMarketVolumeTests(unittest.TestCase):
    def test_closed_market_returns_dated_historical_volume_without_marking_it_live(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "scanner.db"
            with sqlite3.connect(db_path) as db:
                db.execute("""CREATE TABLE scanner_results (
                    symbol TEXT, updated_at TEXT, rvol REAL, current_volume REAL,
                    baseline_volume REAL, signal TEXT, trend_5m TEXT,
                    volume_candle_at TEXT
                )""")
                db.executemany("INSERT INTO scanner_results VALUES (?, ?, ?, ?, ?, ?, ?, ?)", [
                    ("RELIANCE", "2026-10-19 15:29:00", 1.7, 170, 100, "BUY", "BULLISH", "2026-10-19 15:15:00"),
                    ("TCS", "2026-10-19 15:28:00", 1.8, 180, 100, "SELL", "BEARISH", "2026-10-19 15:15:00"),
                    ("INFY", "2026-10-19 15:27:00", 0.8, 80, 100, "WAIT", "MIXED", "2026-10-19 15:15:00"),
                    ("RELIANCE", "2026-10-16 15:29:00", 2.0, 200, 100, "BUY", "BULLISH", "2026-10-16 15:15:00"),
                ])
            now = datetime(2026, 10, 20, 18, 0, tzinfo=IST)
            with patch.object(reversal_context, "DB_PATH", db_path):
                result = reversal_context._observed_volume(now, session_open=False)

        self.assertEqual(result["status"], "MARKET_CLOSED_HISTORICAL")
        self.assertEqual(result["verified_volume_rows"], 0)
        self.assertEqual(result["last_session"]["session_date"], "2026-10-19")
        self.assertEqual(result["last_session"]["verified_volume_rows"], 3)
        self.assertEqual(result["last_session"]["bullish_surge_rows"], 1)
        self.assertEqual(result["last_session"]["bearish_surge_rows"], 1)


if __name__ == "__main__":
    unittest.main()
