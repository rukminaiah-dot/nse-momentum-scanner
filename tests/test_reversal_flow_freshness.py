import unittest
import sys
import types
from datetime import date, datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

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
    def setUp(self):
        reversal_context._flow_cache = None
        reversal_context._flow_cache_date = None

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

    def test_upstox_cash_page_parser_reads_daily_cash_and_keeps_source_date(self):
        html = """
        <table><thead><tr><th>Date</th><th>FII gross purchase (Cr.)</th>
        <th>FII gross sales (Cr.)</th><th>FII Net purchase/sales (Cr.)</th>
        <th>DII Net purchase (Cr.)</th><th>DII gross sales (Cr.)</th>
        <th>DII Net purchase/sales (Cr.)</th></tr></thead><tbody>
        <tr><td>19-10-2026</td><td>₹11,240.64</td><td>₹12,389.28</td>
        <td>₹-1,148.64</td><td>₹14,781.31</td><td>₹11,580.12</td><td>₹3,201.19</td></tr>
        <tr><td>16-10-2026</td><td>₹19,951.59</td><td>₹18,785.67</td>
        <td>₹1,165.92</td><td>₹17,201.80</td><td>₹20,863.08</td><td>₹-3,661.28</td></tr>
        </tbody></table>
        """
        result = reversal_context._parse_upstox_cash_table(html, "fetched")
        self.assertEqual(result["as_of_date"], "2026-10-19")
        self.assertEqual(result["fii"]["latest"]["net_cr"], -1148.64)
        self.assertEqual(result["dii"]["latest"]["net_cr"], 3201.19)
        self.assertEqual(result["fii"]["recent"][1]["date"], "2026-10-16")
        self.assertEqual(result["source"], "Upstox FII/DII data page · NSE cash · daily")

    def test_upstox_cash_page_parser_fails_closed_on_schema_drift(self):
        with self.assertRaises(ValueError):
            reversal_context._parse_upstox_cash_table("<table><tr><th>Date</th><th>Net</th></tr></table>")

    def test_daily_flow_fetch_waits_for_publication_window_and_fetches_once(self):
        tz = ZoneInfo("Asia/Kolkata")
        before_publication = datetime(2026, 10, 20, 8, 30, tzinfo=tz)
        after_publication = datetime(2026, 10, 20, 9, 0, tzinfo=tz)
        with patch.object(reversal_context, "_fetch_upstox_cash_flows", return_value={
            "status": "AVAILABLE", "as_of_date": "2026-10-19",
            "fii": {"latest": {"date": "2026-10-19", "net_cr": -10}},
            "dii": {"latest": {"date": "2026-10-19", "net_cr": 20}},
        }) as fetch:
            early = reversal_context._institutional_flows(now=before_publication)
            self.assertEqual(early["status"], "AWAITING_DAILY_PUBLICATION")
            fetch.assert_not_called()
            result = reversal_context._institutional_flows(now=after_publication)
            again = reversal_context._institutional_flows(now=after_publication)
            self.assertEqual(result["freshness"], "CURRENT")
            self.assertIs(result, again)
            fetch.assert_called_once()


if __name__ == "__main__":
    unittest.main()
