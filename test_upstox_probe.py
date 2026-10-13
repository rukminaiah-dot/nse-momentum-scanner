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
        calls = []
        class Api:
            def __init__(self, client):
                pass
            def get_intra_day_candle_data(self, *args):
                calls.append(args)
                return SimpleNamespace(data=SimpleNamespace(candles=[row]))
        fake_sdk = SimpleNamespace(
            Configuration=lambda: SimpleNamespace(access_token=None),
            ApiClient=lambda config: config, HistoryV3Api=Api)
        with patch.dict(sys.modules, {"upstox_client": fake_sdk}), patch.dict(
            "os.environ", {"UPSTOX_ACCESS_TOKEN": "offline-token"}
        ), patch.object(sys, "argv", ["probe", "--instrument-key", "TEST"]):
            self.assertEqual(probe.main(), 0)
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


if __name__ == "__main__":
    unittest.main()
