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

    def test_rejects_stale_candles(self):
        rows = [[date(2025, 1, 1).isoformat() + "T00:00:00+05:30",
                 100, 101, 99, 100, 1000, 0] for _ in range(120)]
        with patch.object(inv, "candles_for", return_value=rows):
            with self.assertRaisesRegex(ValueError, "Stale"):
                inv.analyze("POLYCAB", date(2026, 10, 9))

    def test_rejects_insufficient_history(self):
        rows = [[date(2026, 10, 9).isoformat() + "T00:00:00+05:30",
                 100, 101, 99, 100, 1000, 0] for _ in range(20)]
        with patch.object(inv, "candles_for", return_value=rows):
            with self.assertRaisesRegex(ValueError, "Insufficient"):
                inv.analyze("POLYCAB", date(2026, 10, 9))

    def test_excludes_future_dated_candles(self):
        rows = [
            ["2026-10-09T00:00:00+05:30", 1, 2, 1, 2, 100, 0],
            ["2026-10-12T00:00:00+05:30", 1, 2, 1, 999, 100, 0],
        ]
        with patch.dict("os.environ", {"UPSTOX_ACCESS_TOKEN": "test"}):
            with patch.object(inv, "NIFTY_200", {"POLYCAB": "NSE_EQ|TEST"}):
                from unittest.mock import MagicMock
                import json
                from io import BytesIO
                response = MagicMock()
                response.__enter__.return_value = BytesIO(json.dumps(
                    {"data": {"candles": rows}}).encode())
                with patch.object(inv.urllib.request, "urlopen", return_value=response):
                    actual = inv.candles_for("POLYCAB", date(2026, 10, 9))
        self.assertEqual(len(actual), 1)
        self.assertEqual(actual[0][4], 2)

    def test_weekly_ema_uses_completed_weeks(self):
        from datetime import timedelta
        end = date(2026, 10, 8)  # Thursday, incomplete week
        start = end - timedelta(days=350)
        rows = []
        for i in range(351):
            day = start + timedelta(days=i)
            if day.weekday() < 5:
                rows.append([day.isoformat() + "T00:00:00+05:30",
                             100, 101, 99, 100 if day.isocalendar()[:2] != end.isocalendar()[:2] else 1000,
                             1000, 0])
        with patch.object(inv, "candles_for", return_value=rows):
            result = inv.analyze("POLYCAB", end)
        self.assertAlmostEqual(result["weekly_ema20"], 100)

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
