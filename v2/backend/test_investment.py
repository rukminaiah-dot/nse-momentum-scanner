"""Offline checks: never require a brokerage token or network."""
import unittest
from unittest.mock import patch
from datetime import date
from v2.backend import investment as inv

class InvestmentTests(unittest.TestCase):
    def test_watchlist_is_exact(self):
        self.assertEqual(len(inv.SYMBOLS), 10)
        self.assertEqual(len(set(inv.SYMBOLS)), 10)
        self.assertIn("COROMANDEL", inv.SYMBOLS)
        self.assertIn("DALBHARAT", inv.SYMBOLS)

    def test_indicators(self):
        self.assertIsNone(inv.ema([1, 2], 20))
        self.assertAlmostEqual(inv.ema([2] * 30, 20), 2)
        self.assertAlmostEqual(inv.rsi(list(range(1, 50))), 100)

    def test_no_fabricated_prices_on_failure(self):
        inv.cached_snapshot.cache_clear()
        with patch.object(inv, "analyze", side_effect=RuntimeError("bad token")):
            result = inv.cached_snapshot(123456)
        self.assertFalse(result["data_is_live"])
        self.assertEqual(len(result["stocks"]), 10)
        self.assertTrue(all(s["price"] is None and s["status"] == "DATA_UNAVAILABLE"
                            for s in result["stocks"]))

    def test_daily_candle_screen_never_claims_live(self):
        dates = [date(2026, 10, 9).toordinal() - 299 + i for i in range(300)]
        rows = [[date.fromordinal(day).isoformat() + "T00:00:00+05:30",
                 100+i, 101+i, 99+i, 100+i, 1000, 0]
                for i, day in enumerate(dates)]
        with patch.object(inv, "candles_for", return_value=rows):
            result = inv.analyze("POLYCAB", date(2026, 10, 10))
        self.assertEqual(result["quote_type"], "DAILY_CLOSE_NOT_LIVE")
        self.assertEqual(result["price"], 399)
        self.assertIsNotNone(result["weekly_ema20"])

if __name__ == "__main__":
    unittest.main()
