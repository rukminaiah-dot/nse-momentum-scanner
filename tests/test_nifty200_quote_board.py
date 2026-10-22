import os
import sqlite3
import tempfile
import time
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from v2.backend import api
from v2.backend.stock_universe import NIFTY_200


class Nifty200QuoteBoardTests(unittest.TestCase):
    def setUp(self):
        for name in ("_quote_cache", "_quote_cache_at"):
            if hasattr(api.nifty200_stock_board, name):
                delattr(api.nifty200_stock_board, name)
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "scanner.db")
        with sqlite3.connect(self.db_path) as db:
            db.execute("""
                CREATE TABLE scanner_results (
                    symbol TEXT, updated_at TEXT, price REAL, momentum REAL,
                    signal TEXT, trend_5m TEXT
                )
            """)

    def tearDown(self):
        for name in ("_quote_cache", "_quote_cache_at"):
            if hasattr(api.nifty200_stock_board, name):
                delattr(api.nifty200_stock_board, name)
        self.temp_dir.cleanup()

    def call_board(self, quotes, tokens=None):
        environment = {
            "UPSTOX_ACCESS_TOKEN": tokens if tokens is not None else "test-token",
            "UPSTOX_ANALYTICS_TOKEN": "",
        }
        with patch.object(api, "DB_PATH", self.db_path), patch.dict(os.environ, environment, clear=False):
            with patch("v2.backend.upstox_quote_client.fetch_full_quotes",
                       return_value=(quotes, "test quote source")) as fetch:
                result = api.nifty200_stock_board()
        return result, fetch

    def test_board_attaches_real_quote_change_and_keeps_all_symbols(self):
        symbol = next(iter(NIFTY_200))
        key = NIFTY_200[symbol]
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        result, fetch = self.call_board({
            "NSE_EQ:" + symbol: {
                "last_price": 110.0,
                "prev_close_price": 100.0,
                "last_trade_time": now_ms,
            }
        })

        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(len(fetch.call_args.args[0]), 200)
        self.assertEqual(result["universe_size"], 200)
        row = next(item for item in result["stocks"] if item["symbol"] == symbol)
        self.assertAlmostEqual(row["daily_change_pct"], 10.0)
        self.assertEqual(row["previous_close"], 100.0)
        self.assertEqual(row["quote_price"], 110.0)
        self.assertIn(row["change_status"], ("CURRENT", "LAST_SESSION"))
        self.assertEqual(result["quotes_status"], "AVAILABLE")

    def test_missing_quote_is_explicit_and_does_not_remove_stock(self):
        result, _ = self.call_board({})
        self.assertEqual(len(result["stocks"]), 200)
        self.assertTrue(all(row["daily_change_pct"] is None for row in result["stocks"]))
        self.assertTrue(all(row["change_status"] == "NO_QUOTE" for row in result["stocks"]))

    def test_invalid_or_stale_quote_is_not_used_for_ranking(self):
        symbol = next(iter(NIFTY_200))
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        result, _ = self.call_board({
            "NSE_EQ:" + symbol: {
                "last_price": 110.0,
                "prev_close_price": 0,
                "last_trade_time": now_ms,
            }
        })
        row = next(item for item in result["stocks"] if item["symbol"] == symbol)
        self.assertIsNone(row["daily_change_pct"])
        self.assertEqual(row["change_status"], "INVALID_QUOTE")

    def test_provider_failure_is_safe_and_preserves_full_universe(self):
        with patch.object(api, "DB_PATH", self.db_path), patch.dict(os.environ, {
            "UPSTOX_ACCESS_TOKEN": "test-token",
            "UPSTOX_ANALYTICS_TOKEN": "",
        }, clear=False), patch("v2.backend.upstox_quote_client.fetch_full_quotes",
                               side_effect=TimeoutError()):
            result = api.nifty200_stock_board()
        self.assertEqual(len(result["stocks"]), 200)
        self.assertEqual(result["quotes_status"], "UNAVAILABLE")
        self.assertEqual(result["quotes_error"], "TimeoutError")
        self.assertTrue(all(row["daily_change_pct"] is None for row in result["stocks"]))
        self.assertNotIn("test-token", str(result))


if __name__ == "__main__":
    unittest.main()
