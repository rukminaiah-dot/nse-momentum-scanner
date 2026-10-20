import unittest

from v2.backend.long_horizon_reversal import (
    HORIZON_SESSIONS,
    classify_sustained_reversal,
    rule_definition,
)


class LongHorizonReversalTests(unittest.TestCase):
    def setUp(self):
        self.prior_down = [10000 - index * 10 for index in range(60)]
        self.prior_up = [10000 + index * 10 for index in range(60)]

    def test_long_horizon_rule_withholds_probabilities(self):
        rules = rule_definition()
        self.assertEqual(rules["horizon_trading_sessions"], 60)
        self.assertEqual(rules["probability_status"], "NOT_BACKTESTED")
        self.assertIsNone(rules["probabilities"])

    def test_sustained_500_point_move_against_prior_trend_is_reversal(self):
        future = [10000] * 45 + [10510] * 15
        result = classify_sustained_reversal(10000, self.prior_down, future)
        self.assertEqual(result["status"], "LABELED")
        self.assertEqual(result["prior_regime"], "DOWN")
        self.assertEqual(result["outcome"], "SUSTAINED_UP_REVERSAL")
        self.assertEqual(result["up_touches_in_final_15"], 15)

    def test_move_that_fades_before_persistence_is_not_confirmed_reversal(self):
        future = [10000] * 20 + [10510] + [10000] * 39
        result = classify_sustained_reversal(10000, self.prior_down, future)
        self.assertEqual(result["outcome"], "THRESHOLD_TOUCHED_NOT_SUSTAINED")

    def test_sustained_move_with_prior_trend_is_continuation(self):
        future = [10510] * HORIZON_SESSIONS
        result = classify_sustained_reversal(10000, self.prior_up, future)
        self.assertEqual(result["outcome"], "SUSTAINED_UP_CONTINUATION")

    def test_mixed_prior_regime_does_not_get_reversal_label(self):
        prior = [10000] * 60
        future = [10000] * 45 + [10510] * 15
        result = classify_sustained_reversal(10000, prior, future)
        self.assertEqual(result["prior_regime"], "MIXED")
        self.assertEqual(result["outcome"], "SUSTAINED_UP_UNCLASSIFIED_TREND")

    def test_history_gaps_and_invalid_data_fail_closed(self):
        self.assertEqual(
            classify_sustained_reversal(10000, [10000] * 59, [10000] * 60)["status"],
            "INSUFFICIENT_PRIOR_HISTORY",
        )
        self.assertEqual(
            classify_sustained_reversal(10000, self.prior_down, [10000] * 59)["status"],
            "INCOMPLETE_FUTURE_HORIZON",
        )
        bad = self.prior_down.copy()
        bad[3] = "missing"
        self.assertEqual(
            classify_sustained_reversal(10000, bad, [10000] * 60)["status"],
            "INVALID_CLOSE_HISTORY",
        )


if __name__ == "__main__":
    unittest.main()
