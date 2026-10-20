import unittest
import sys
import types
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from unittest.mock import patch

try:
    from v2.backend import reversal_context
except ModuleNotFoundError as exc:
    # The parser tests do not need FastAPI; some local test environments only
    # install the stdlib dependencies used by the offline suite.
    if exc.name != "fastapi":
        raise
    fastapi_stub = types.ModuleType("fastapi")

    class APIRouterStub:
        def get(self, *_args, **_kwargs):
            return lambda handler: handler

    fastapi_stub.APIRouter = APIRouterStub
    sys.modules["fastapi"] = fastapi_stub
    from v2.backend import reversal_context


class ReversalVixQuoteTests(unittest.TestCase):
    def test_parses_documented_upstox_v3_quote_with_millisecond_string(self):
        last_trade_time = str(int(datetime.now(timezone.utc).timestamp() * 1000))
        payload = {
            "status": "success",
            "data": {
                "NSE_INDEX:India VIX": {
                    "last_price": 14.25,
                    "prev_close_price": 13.5,
                    "last_trade_time": last_trade_time,
                }
            },
        }
        with patch.object(reversal_context, "_upstox_get", return_value=payload):
            result = reversal_context._upstox_quote("test-token")

        self.assertIn(result["status"], {"AVAILABLE", "HISTORICAL"})
        self.assertEqual(result["value"], 14.25)
        self.assertEqual(result["previous_close"], 13.5)
        self.assertAlmostEqual(result["change_pct"], 5.556, places=3)
        self.assertEqual(result["quote_fields"], ["last_price", "last_trade_time", "prev_close_price"])

    def test_uses_iso_timestamp_and_documented_net_change_when_close_is_omitted(self):
        quote_time = datetime.now(timezone.utc) - timedelta(minutes=1)
        payload = {
            "status": "success",
            "data": {
                "NSE_INDEX:India VIX": {
                    "last_price": 20,
                    "net_change": 2,
                    "timestamp": quote_time.isoformat(),
                }
            },
        }
        with patch.object(reversal_context, "_upstox_get", return_value=payload):
            result = reversal_context._upstox_quote("test-token")

        self.assertIn(result["status"], {"AVAILABLE", "HISTORICAL"})
        self.assertEqual(result["previous_close"], 18)
        self.assertEqual(result["as_of"], quote_time.isoformat())
        self.assertFalse(result["field_presence"]["prev_close_price"])
        self.assertTrue(result["field_presence"]["net_change"])

    def test_incomplete_quote_returns_field_names_without_values(self):
        payload = {
            "status": "success",
            "data": {"NSE_INDEX:India VIX": {"last_price": 17.2, "timestamp": "bad-time"}},
        }
        with patch.object(reversal_context, "_upstox_get", return_value=payload):
            result = reversal_context._upstox_quote("test-token")

        self.assertEqual(result["status"], "UNAVAILABLE")
        self.assertEqual(result["reason"], "ValueError")
        self.assertEqual(result["quote_fields"], ["last_price", "timestamp"])
        self.assertEqual(result["field_presence"]["last_price"], True)
        self.assertNotIn("17.2", repr(result))

    def test_yesterdays_quote_is_stale_during_open_session_and_historical_when_closed(self):
        ist = ZoneInfo("Asia/Kolkata")
        session_time = datetime(2026, 10, 20, 9, 30, tzinfo=ist)
        old_stamp = datetime(2026, 10, 19, 15, 30, tzinfo=ist)

        status, age = reversal_context._quote_freshness(old_stamp, session_time)
        self.assertEqual(status, "STALE")
        self.assertGreater(age, 15 * 60)

        closed_time = datetime(2026, 10, 20, 17, 0, tzinfo=ist)
        status, _ = reversal_context._quote_freshness(old_stamp, closed_time)
        self.assertEqual(status, "HISTORICAL")


if __name__ == "__main__":
    unittest.main()
