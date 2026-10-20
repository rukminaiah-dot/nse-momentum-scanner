import unittest
import sys
import types
from datetime import date

try:
    from v2.backend import reversal_context
except ModuleNotFoundError as exc:
    if exc.name != "fastapi":
        raise
    fastapi_stub = types.ModuleType("fastapi")

    class APIRouterStub:
        def get(self, *_args, **_kwargs):
            return lambda handler: handler

    fastapi_stub.APIRouter = APIRouterStub
    sys.modules["fastapi"] = fastapi_stub
    from v2.backend import reversal_context


class ReversalFlowFreshnessTests(unittest.TestCase):
    def test_prior_session_cash_flow_is_recent_context(self):
        self.assertEqual(
            reversal_context._flow_freshness("2026-10-19", today=date(2026, 10, 20)),
            "CURRENT",
        )

    def test_old_cash_flow_is_not_a_current_session_confirmation(self):
        self.assertEqual(
            reversal_context._flow_freshness("2026-10-08", today=date(2026, 10, 20)),
            "STALE",
        )

    def test_weekend_gap_remains_recent(self):
        self.assertEqual(
            reversal_context._flow_freshness("2026-10-16", today=date(2026, 10, 19)),
            "CURRENT",
        )

    def test_invalid_or_future_flow_date_is_unknown_or_stale(self):
        self.assertEqual(reversal_context._flow_freshness("not-a-date"), "UNKNOWN")
        self.assertEqual(
            reversal_context._flow_freshness("2026-10-21", today=date(2026, 10, 20)),
            "STALE",
        )

    def test_stale_flows_cannot_advance_live_reversal_rule(self):
        context = {
            "india_vix": {"status": "AVAILABLE", "value": 14.0, "change_pct": -1.0},
            "institutional_flows": {"status": "AVAILABLE", "freshness": "STALE",
                                    "fii": {"latest": {"net_cr": -10}},
                                    "latest_absorption_ratio": 2.0},
            "volume": {"status": "AVAILABLE", "bullish_surge_rows": 1,
                       "bearish_surge_rows": 0},
            "price_structure": {"status": "LIVE_FRESH", "direction": "BULLISH"},
        }
        result = reversal_context._rule_state(context)
        self.assertEqual(result["status"], "PARTIAL_INPUTS")
        self.assertIn("recent same-date FII/DII cash", result["summary"])


if __name__ == "__main__":
    unittest.main()
