"""Unit tests for fail-closed positional signal engine. Run: python -m unittest v2.backend.test_verified_positional_signals"""
import unittest
from datetime import date, timedelta
from v2.backend.verified_positional_signals import evaluate

class VerifiedSignalsTest(unittest.TestCase):
    def candles(self, n=75):
        end = date(2026, 10, 9)
        days = [end - timedelta(days=n-i-1) for i in range(n)]
        return [{"date": d.isoformat(), "open": 100, "high": 102, "low": 98,
                 "close": 100, "volume": 10000} for d in days]

    def test_no_data_is_not_buy(self):
        result = evaluate("BEL", [], as_of="2026-10-11")
        self.assertEqual(result["status"], "DATA_UNVERIFIED")
        self.assertIsNone(result["entry"])

    def test_missing_history_is_rejected(self):
        result = evaluate("BEL", self.candles(60), as_of="2026-10-11")
        self.assertEqual(result["reason"], "INSUFFICIENT_HISTORY_70_CANDLES")

    def test_stale_data_is_rejected(self):
        result = evaluate("BEL", self.candles(), as_of="2026-10-20")
        self.assertEqual(result["reason"], "STALE_HISTORY")

    def test_invalid_ohlc_is_rejected(self):
        rows = self.candles()
        rows[-1]["high"] = 99
        self.assertEqual(evaluate("BEL", rows, as_of="2026-10-11")["reason"], "INCONSISTENT_OHLC")

    def test_flat_price_has_no_breakout(self):
        result = evaluate("BEL", self.candles(), as_of="2026-10-11")
        self.assertEqual(result["status"], "NO_SIGNAL")
        self.assertFalse(result["checks"]["breakout_20d"])

    def test_future_candle_is_rejected(self):
        self.assertEqual(evaluate("BEL", self.candles(), as_of="2026-10-08")["reason"], "FUTURE_DATED_CANDLE")

    def test_duplicate_session_is_rejected(self):
        rows = self.candles()
        rows[-1]["date"] = rows[-2]["date"]
        self.assertEqual(evaluate("BEL", rows, as_of="2026-10-11")["reason"], "DUPLICATE_SESSION")

if __name__ == "__main__":
    unittest.main()
