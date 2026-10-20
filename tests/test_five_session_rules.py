import unittest

from v2.backend.five_session_rules import (
    classify_five_session_path,
    event_spec,
    rule_definition,
)


def five_bars(*, hit_up=False, hit_down=False):
    bars = [{"high": 10100, "low": 9900} for _ in range(5)]
    if hit_up:
        bars[1] = {"high": 10510, "low": 10000}
    if hit_down:
        bars[3] = {"high": 10000, "low": 9490}
    return bars


class FiveSessionRuleTests(unittest.TestCase):
    def test_event_levels_and_percent_require_verified_anchor(self):
        pending = event_spec()
        self.assertEqual(pending["status"], "AWAITING_VERIFIED_CLOSE")
        self.assertIsNone(pending["up_level"])
        self.assertEqual(event_spec(22888.95)["status"], "AWAITING_VERIFIED_CLOSE")
        self.assertEqual(event_spec(22888.95, "not-a-date")["status"], "AWAITING_VERIFIED_CLOSE")
        ready = event_spec(22888.95, "2026-10-19")
        self.assertEqual(ready["up_level"], 23388.95)
        self.assertEqual(ready["down_level"], 22388.95)
        self.assertAlmostEqual(ready["target_pct"], 2.1845, places=4)
        self.assertIsNone(ready["probabilities"])
        self.assertEqual(ready["probability_status"], "NOT_BACKTESTED")

    def test_path_labels_up_down_neither_and_both(self):
        up = classify_five_session_path(10000, five_bars(hit_up=True))
        down = classify_five_session_path(10000, five_bars(hit_down=True))
        neither = classify_five_session_path(10000, five_bars())
        both = classify_five_session_path(10000, five_bars(hit_up=True, hit_down=True))
        self.assertEqual(up["outcome"], "UP_ONLY")
        self.assertEqual(down["outcome"], "DOWN_ONLY")
        self.assertTrue(neither["neither_threshold_reached"])
        self.assertEqual(both["outcome"], "BOTH")
        self.assertFalse(both["neither_threshold_reached"])

    def test_same_daily_bar_touch_order_is_ambiguous(self):
        bars = five_bars()
        bars[0] = {"high": 10500, "low": 9500}
        result = classify_five_session_path(10000, bars)
        self.assertEqual(result["outcome"], "BOTH")
        self.assertEqual(result["first_touch"], "BOTH_SAME_SESSION")

    def test_labels_require_five_valid_future_bars(self):
        incomplete = classify_five_session_path(10000, five_bars()[:4])
        invalid = classify_five_session_path(10000, five_bars()[:4] + [{"high": "bad", "low": 9900}])
        self.assertEqual(incomplete["status"], "INCOMPLETE_FUTURE_HORIZON")
        self.assertEqual(invalid["status"], "INVALID_FUTURE_BAR")

    def test_rules_explicitly_require_timestamped_data_and_backtesting(self):
        rules = rule_definition()
        self.assertEqual(rules["probability_status"], "NOT_BACKTESTED")
        self.assertIsNone(rules["probabilities"])
        self.assertIn("published after the forecast cutoff", " ".join(rules["data_guards"]))
        self.assertIn("NIFTY 50 has no directly traded cash-index volume", " ".join(rules["data_guards"]))


if __name__ == "__main__":
    unittest.main()
