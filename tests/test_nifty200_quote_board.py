import unittest
from datetime import datetime, timedelta, timezone

from v2.backend.nifty200_quotes import quote_change_fields
from v2.backend.stock_universe import NIFTY_200


class Nifty200QuoteBoardTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 22, 10, 0, tzinfo=timezone.utc)
        self.symbol = next(iter(NIFTY_200))
        self.key = NIFTY_200[self.symbol]

    def quote(self, **changes):
        data = {
            "last_price": 110.0,
            "prev_close_price": 100.0,
            "last_trade_time": int(self.now.timestamp() * 1000),
        }
        data.update(changes)
        return data

    def test_current_upstox_quote_calculates_session_change_against_previous_close(self):
        result = quote_change_fields(
            self.symbol, self.key, {"NSE_EQ:" + self.symbol: self.quote()},
            market_open=True, now_utc=self.now,
        )
        self.assertAlmostEqual(result["daily_change_pct"], 10.0)
        self.assertEqual(result["previous_close"], 100.0)
        self.assertEqual(result["quote_price"], 110.0)
        self.assertEqual(result["change_status"], "CURRENT")

    def test_closed_market_retains_only_a_recent_last_session_quote(self):
        result = quote_change_fields(
            self.symbol, self.key, {"NSE_EQ:" + self.symbol: self.quote()},
            market_open=False, now_utc=self.now + timedelta(hours=1),
        )
        self.assertAlmostEqual(result["daily_change_pct"], 10.0)
        self.assertEqual(result["change_status"], "LAST_SESSION")

    def test_stale_quotes_are_not_eligible_for_ranking(self):
        stale = self.quote(last_trade_time=int((self.now - timedelta(hours=1)).timestamp() * 1000))
        result = quote_change_fields(
            self.symbol, self.key, {"NSE_EQ:" + self.symbol: stale},
            market_open=True, now_utc=self.now,
        )
        self.assertIsNone(result["daily_change_pct"])
        self.assertEqual(result["change_status"], "STALE")

    def test_quote_without_valid_previous_close_is_rejected(self):
        result = quote_change_fields(
            self.symbol, self.key, {"NSE_EQ:" + self.symbol: self.quote(prev_close_price=0)},
            market_open=True, now_utc=self.now,
        )
        self.assertIsNone(result["daily_change_pct"])
        self.assertEqual(result["change_status"], "INVALID_QUOTE")

    def test_net_change_can_supply_a_verified_previous_close_fallback(self):
        quote = self.quote()
        quote.pop("prev_close_price")
        quote["net_change"] = 10.0
        result = quote_change_fields(
            self.symbol, self.key, {"NSE_EQ:" + self.symbol: quote},
            market_open=True, now_utc=self.now,
        )
        self.assertEqual(result["previous_close"], 100.0)
        self.assertAlmostEqual(result["daily_change_pct"], 10.0)

    def test_missing_quotes_are_explicit_and_do_not_remove_any_symbol(self):
        result = quote_change_fields(
            self.symbol, self.key, {}, market_open=True, now_utc=self.now,
        )
        self.assertIsNone(result["daily_change_pct"])
        self.assertEqual(result["change_status"], "NO_QUOTE")
        unavailable = quote_change_fields(
            self.symbol, self.key, {}, quote_error="TimeoutError",
            market_open=True, now_utc=self.now,
        )
        self.assertEqual(unavailable["change_status"], "UNAVAILABLE")
        self.assertEqual(len(NIFTY_200), 200)


if __name__ == "__main__":
    unittest.main()
