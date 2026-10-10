"""Deterministic safety and selection tests for the research-only option ranker.

Run from repository root: python -m unittest discover -s tests -p 'test_option_contract_ranker.py'
"""
import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from v2.backend.option_contract_ranker import rank_option_candidates

IST = ZoneInfo("Asia/Kolkata")
NOW = datetime(2026, 10, 12, 10, 30, tzinfo=IST)  # Monday


def contract(kind="CE", **overrides):
    data = {
        "type": kind, "strike": 25000, "expiry": "2026-10-15",
        "bid": 100, "ask": 101, "volume": 25000,
        "open_interest": 150000, "lot_size": 65,
    }
    data.update(overrides)
    return data


def rank(direction="BULLISH", contracts=None, quote_time=NOW, now=NOW, index="NIFTY 50"):
    return rank_option_candidates(
        index, direction, [contract()] if contracts is None else contracts,
        quote_time=quote_time, now=now,
    )


class OptionRankerTests(unittest.TestCase):
    def test_bullish_selects_ce_only(self):
        result = rank(contracts=[contract("PE"), contract("CE")])
        self.assertEqual(result["status"], "RESEARCH_SHORTLIST_ONLY")
        self.assertEqual(len(result["candidates"]), 1)
        self.assertEqual(result["candidates"][0]["type"], "CE")
        self.assertEqual(result["candidates"][0]["estimated_one_lot_premium_inr"], 6565)
        self.assertFalse(result["order_execution_enabled"])

    def test_bearish_selects_pe_only(self):
        result = rank(direction="BEARISH", contracts=[contract("CE"), contract("PE")])
        self.assertEqual(result["candidates"][0]["type"], "PE")

    def test_unconfirmed_direction_fails_closed(self):
        self.assertEqual(rank(direction="WAIT")["reason"], "DIRECTION_NOT_CONFIRMED")

    def test_no_chain_fails_closed(self):
        self.assertEqual(rank(contracts=[])["reason"], "OPTION_CHAIN_NOT_CONNECTED")

    def test_stale_quote_fails_closed(self):
        result = rank(quote_time=NOW - timedelta(minutes=3))
        self.assertEqual(result["reason"], "STALE_OR_CLOSED_MARKET")

    def test_future_quote_fails_closed(self):
        result = rank(quote_time=NOW + timedelta(seconds=1))
        self.assertEqual(result["status"], "NO_TRADE")

    def test_weekend_fails_closed(self):
        saturday = datetime(2026, 10, 10, 10, 30, tzinfo=IST)
        self.assertEqual(rank(now=saturday, quote_time=saturday)["status"], "NO_TRADE")

    def test_wide_spread_rejected(self):
        self.assertEqual(rank(contracts=[contract(bid=90, ask=110)])["reason"], "NO_LIQUID_CONTRACTS")

    def test_low_liquidity_rejected(self):
        self.assertEqual(rank(contracts=[contract(volume=1, open_interest=2)])["reason"], "NO_LIQUID_CONTRACTS")

    def test_invalid_or_expired_contract_rejected(self):
        invalid = [contract(ask=float("nan")), contract(expiry="2026-10-09"), contract(lot_size=0)]
        self.assertEqual(rank(contracts=invalid)["status"], "NO_TRADE")

    def test_top_three_ranked_by_quality(self):
        options = [
            contract(strike=25000, bid=100, ask=101, volume=1000),
            contract(strike=25100, bid=100, ask=100.5, volume=30000),
            contract(strike=25200, bid=100, ask=100.8, volume=5000),
            contract(strike=25300, bid=100, ask=101.5, volume=200),
        ]
        result = rank(contracts=options)
        self.assertEqual(len(result["candidates"]), 3)
        self.assertEqual(result["candidates"][0]["strike"], 25100)
        self.assertEqual(result["status"], "RESEARCH_SHORTLIST_ONLY")

    def test_unverified_timestamp_fails_closed(self):
        self.assertEqual(rank(quote_time=NOW.replace(tzinfo=None))["reason"], "UNVERIFIED_QUOTE_TIME")


if __name__ == "__main__":
    unittest.main()
