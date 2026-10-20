import unittest

from v2.backend.reversal_evidence import assess_long_reversal_evidence


class ReversalEvidenceTests(unittest.TestCase):
    def test_closed_market_uses_available_historical_flow_and_vix_only(self):
        result = assess_long_reversal_evidence(
            {"status": "HISTORICAL", "direction": None, "candle_ist": "2026-10-19 15:29:00"},
            {"status": "HISTORICAL", "value": 19.33, "session_date": "2026-10-19", "history": []},
            {"status": "HISTORICAL", "value": 14.77, "change_pct": 5.05,
             "as_of": "2026-10-19T10:30:00+00:00", "age_seconds": 90000},
            {"status": "AVAILABLE", "freshness": "CURRENT", "as_of_date": "2026-10-19",
             "latest_absorption_ratio": 2.787,
             "fii": {"latest": {"date": "2026-10-19", "net_cr": -1148.64}},
             "dii": {"latest": {"date": "2026-10-19", "net_cr": 3201.19}}},
            {"status": "MARKET_CLOSED_HISTORICAL", "verified_volume_rows": 0},
        )
        self.assertEqual(result["score_points"], 20)
        self.assertEqual(result["assessed_factors"], 2)
        self.assertFalse(result["is_probability"])
        self.assertEqual(result["factors"][1]["status"], "NOT_SCORED")
        self.assertEqual(result["factors"][2]["points"], 0)
        self.assertEqual(result["factors"][3]["points"], 20)

    def test_falling_pe_needs_three_comparable_consecutive_observations(self):
        common = {"status": "HISTORICAL"}
        pe = {"history": [
            {"session_date": "2026-10-15", "value": 20.0, "basis": "trailing EPS"},
            {"session_date": "2026-10-16", "value": 19.9, "basis": "trailing EPS"},
            {"session_date": "2026-10-19", "value": 19.8, "basis": "trailing EPS"},
        ]}
        result = assess_long_reversal_evidence(
            {"status": "UNAVAILABLE"}, pe, {}, {}, {})
        factor = result["factors"][1]
        self.assertEqual(factor["points"], 15)
        self.assertEqual(factor["status"], "ASSESSED")
        pe["history"][2]["basis"] = "different basis"
        result = assess_long_reversal_evidence({"status": "UNAVAILABLE"}, pe, {}, {}, {})
        self.assertEqual(result["factors"][1]["status"], "NOT_SCORED")

    def test_fresh_bullish_structure_and_verified_volume_can_add_points(self):
        result = assess_long_reversal_evidence(
            {"status": "LIVE_FRESH", "direction": "BULLISH",
             "candle_ist": "2026-10-20 10:05:00", "basis": "completed 5-minute candles"},
            {}, {"status": "AVAILABLE", "value": 26, "change_pct": -1.4,
                 "as_of": "2026-10-20T04:35:00+00:00", "age_seconds": 10},
            {"status": "AVAILABLE", "freshness": "CURRENT", "as_of_date": "2026-10-20",
             "latest_absorption_ratio": 1.2,
             "fii": {"latest": {"date": "2026-10-20", "net_cr": -1000}},
             "dii": {"latest": {"date": "2026-10-20", "net_cr": 1300}}},
            {"status": "AVAILABLE", "verified_volume_rows": 20, "bullish_surge_rows": 2},
        )
        self.assertEqual(result["score_points"], 95)
        self.assertEqual(result["assessed_factors"], 4)

    def test_news_is_timestamped_context_not_an_unvalidated_automatic_score(self):
        result = assess_long_reversal_evidence({}, {}, {}, {}, {})
        news = result["factors"][-1]
        self.assertEqual(news["status"], "CONTEXT_ONLY")
        self.assertIsNone(news["points"])
        self.assertFalse(result["is_probability"])
        self.assertIsNone(result["score_points"])


if __name__ == "__main__":
    unittest.main()
