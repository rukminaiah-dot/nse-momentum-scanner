"""Offline contract tests for the manual read-only Upstox probe."""
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import probe_upstox_recovery as probe


class ProbeTests(unittest.TestCase):
    def test_missing_token_fails_without_sdk_import(self):
        with patch.dict("os.environ", {}, clear=True), patch.object(
            sys, "argv", ["probe", "--instrument-key", "TEST"]
        ):
            self.assertEqual(probe.main(), 2)

    def test_valid_response_is_read_only(self):
        from datetime import datetime, timedelta
        from zoneinfo import ZoneInfo
        now = datetime.now(ZoneInfo("Asia/Kolkata"))
        completed = (now - timedelta(minutes=2)).replace(second=0, microsecond=0)
        if completed.date() != now.date():
            self.skipTest("IST midnight boundary")
        row = [completed.isoformat(), 100, 103, 99, 102, 10]
        adjacent = [(completed - timedelta(minutes=1)).isoformat(), 100, 103, 99, 102, 10]
        calls = []
        from contextlib import redirect_stdout
        from io import StringIO
        output = StringIO()
        class Api:
            def __init__(self, client):
                pass
            def get_intra_day_candle_data(self, *args):
                calls.append(args)
                return SimpleNamespace(data=SimpleNamespace(candles=[row, adjacent]))
        fake_sdk = SimpleNamespace(
            Configuration=lambda: SimpleNamespace(access_token=None),
            ApiClient=lambda config: config, HistoryV3Api=Api)
        with patch.dict(sys.modules, {"upstox_client": fake_sdk}), patch.dict(
            "os.environ", {"UPSTOX_ACCESS_TOKEN": "offline-token"}
        ), patch.object(sys, "argv", ["probe", "--instrument-key", "TEST"]), redirect_stdout(output):
            self.assertEqual(probe.main(), 0)
        self.assertIn("PASS: real-candle in-memory gap insertion and idempotence verified", output.getvalue())
        self.assertEqual(calls, [("TEST", "minutes", "1")])

    def test_invalid_response_fails_closed(self):
        class Api:
            def __init__(self, client):
                pass
            def get_intra_day_candle_data(self, *args):
                return SimpleNamespace(data=None)
        fake_sdk = SimpleNamespace(
            Configuration=lambda: SimpleNamespace(access_token=None),
            ApiClient=lambda config: config, HistoryV3Api=Api)
        with patch.dict(sys.modules, {"upstox_client": fake_sdk}), patch.dict(
            "os.environ", {"UPSTOX_ACCESS_TOKEN": "offline-token"}
        ), patch.object(sys, "argv", ["probe", "--instrument-key", "TEST"]):
            self.assertEqual(probe.main(), 1)


    def test_broker_exception_returns_failure_without_disclosing_details(self):
        """A broker exception must be handled without exposing SDK exception text."""
        from contextlib import redirect_stderr
        from io import StringIO
        class Api:
            def __init__(self, client):
                pass
            def get_intra_day_candle_data(self, *args):
                raise RuntimeError("SENSITIVE_TOKEN_SHOULD_NOT_APPEAR")
        fake_sdk = SimpleNamespace(
            Configuration=lambda: SimpleNamespace(access_token=None),
            ApiClient=lambda config: config, HistoryV3Api=Api)
        output = StringIO()
        with patch.dict(sys.modules, {"upstox_client": fake_sdk}), patch.dict(
            "os.environ", {"UPSTOX_ACCESS_TOKEN": "offline-token"}
        ), patch.object(sys, "argv", ["probe", "--instrument-key", "TEST"]), redirect_stderr(output):
            self.assertEqual(probe.main(), 1)
        self.assertNotIn("SENSITIVE_TOKEN_SHOULD_NOT_APPEAR", output.getvalue())
        self.assertIn("RuntimeError", output.getvalue())

    def test_missing_candle_collection_is_not_a_success(self):
        class Api:
            def __init__(self, client):
                pass
            def get_intra_day_candle_data(self, *args):
                return SimpleNamespace(data=SimpleNamespace(candles=None))
        fake_sdk = SimpleNamespace(
            Configuration=lambda: SimpleNamespace(access_token=None),
            ApiClient=lambda config: config, HistoryV3Api=Api)
        with patch.dict(sys.modules, {"upstox_client": fake_sdk}), patch.dict(
            "os.environ", {"UPSTOX_ACCESS_TOKEN": "offline-token"}
        ), patch.object(sys, "argv", ["probe", "--instrument-key", "TEST"]):
            self.assertEqual(probe.main(), 1)

    def test_empty_response_is_inconclusive_not_verified(self):
        class Api:
            def __init__(self, client):
                pass
            def get_intra_day_candle_data(self, *args):
                return SimpleNamespace(data=SimpleNamespace(candles=[]))
        fake_sdk = SimpleNamespace(
            Configuration=lambda: SimpleNamespace(access_token=None),
            ApiClient=lambda config: config, HistoryV3Api=Api)
        with patch.dict(sys.modules, {"upstox_client": fake_sdk}), patch.dict(
            "os.environ", {"UPSTOX_ACCESS_TOKEN": "offline-token"}
        ), patch.object(sys, "argv", ["probe", "--instrument-key", "TEST"]):
            self.assertEqual(probe.main(), 3)

    def test_empty_response_never_prints_pass(self):
        from contextlib import redirect_stdout
        from io import StringIO
        class Api:
            def __init__(self, client):
                pass
            def get_intra_day_candle_data(self, *args):
                return SimpleNamespace(data=SimpleNamespace(candles=[]))
        fake_sdk = SimpleNamespace(
            Configuration=lambda: SimpleNamespace(access_token=None),
            ApiClient=lambda config: config, HistoryV3Api=Api)
        output = StringIO()
        with patch.dict(sys.modules, {"upstox_client": fake_sdk}), patch.dict(
            "os.environ", {"UPSTOX_ACCESS_TOKEN": "offline-token"}
        ), patch.object(sys, "argv", ["probe", "--instrument-key", "TEST"]), redirect_stdout(output):
            self.assertEqual(probe.main(), 3)
        self.assertIn("INCONCLUSIVE", output.getvalue())
        self.assertNotIn("PASS", output.getvalue())

if __name__ == "__main__":
    unittest.main()
