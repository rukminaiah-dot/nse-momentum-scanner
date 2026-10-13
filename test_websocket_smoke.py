"""Offline mocked tests for the isolated Upstox websocket smoke harness."""
import os
import io
from contextlib import redirect_stderr
import sys
import types
import time
import unittest
from unittest.mock import patch

import probe_upstox_websocket_smoke as probe


ENV = {
    "FIX10_NONPRODUCTION_ACK": "I_AM_IN_AN_ISOLATED_TEST",
    "FIX10_LIVE_STREAM_ACK": "READ_ONLY_STREAM_TEST",
    "UPSTOX_ACCESS_TOKEN": "offline-test-only",
    "FIX10_TEST_INSTRUMENT_KEY": "MOCK_INSTRUMENT",
}


class FakeStreamer:
    mode = "success"
    last = None

    def __init__(self, *_args):
        self.callbacks = {}
        self.disconnected = False
        FakeStreamer.last = self

    def on(self, event, callback):
        self.callbacks[event] = callback

    def connect(self):
        if self.mode == "raise":
            raise RuntimeError("do not print secret-bearing SDK errors")
        if self.mode == "error":
            self.callbacks["error"]("mock failure")
            return
        self.callbacks["open"]()
        stamp = str(int(time.time() * 1000)) if self.mode != "stale" else "1760000000000"
        self.callbacks["message"]({"feeds": {"MOCK_INSTRUMENT": {"ltpc": {"ltp": 100.0, "ltt": stamp}}}})

    def disconnect(self):
        self.disconnected = True


class WebsocketSmokeTests(unittest.TestCase):
    def setUp(self):
        FakeStreamer.mode = "success"
        FakeStreamer.last = None
        self.sdk = types.SimpleNamespace(
            Configuration=lambda: types.SimpleNamespace(access_token=None),
            ApiClient=lambda config: config,
            MarketDataStreamerV3=FakeStreamer,
        )

    def test_heartbeat_and_other_instruments_are_not_ticks(self):
        for payload in (None, {}, {"type": "heartbeat"},
                        {"feeds": {}},
                        {"feeds": {"OTHER": {"ltpc": {"ltp": 100, "ltt": "1"}}}},
                        {"feeds": {"MOCK_INSTRUMENT": {"ltpc": {"ltp": 100}}}}):
            with self.subTest(payload=repr(payload)):
                self.assertFalse(probe.has_instrument_tick(payload, "MOCK_INSTRUMENT"))
        for price, stamp in ((float("nan"), "1"), (float("inf"), "1"),
                             (0, "1"), (-1, "1"), ("invalid", "1"),
                             (100, "invalid"), (100, "0"), (None, "1")):
            with self.subTest(price=str(price), stamp=str(stamp)):
                self.assertFalse(probe.has_instrument_tick(
                    {"feeds": {"MOCK_INSTRUMENT": {"ltpc": {"ltp": price, "ltt": stamp}}}},
                    "MOCK_INSTRUMENT"))
        self.assertTrue(probe.has_instrument_tick(
            {"feeds": {"MOCK_INSTRUMENT": {"ltpc": {"ltp": 100, "ltt": "1"}}}},
            "MOCK_INSTRUMENT"))

    def test_missing_acknowledgement_blocks_before_sdk(self):
        with patch.dict(os.environ, {**ENV, "FIX10_LIVE_STREAM_ACK": ""}, clear=True):
            with patch.dict(sys.modules, {"upstox_client": None}):
                self.assertEqual(probe.main(), 2)

    def test_unrecognized_recovery_ack_blocks_before_sdk(self):
        with patch.dict(os.environ, {**ENV,
                                      "FIX10_ISOLATED_RECOVERY_ACK": "READ_ONLY_HISTROY"},
                        clear=True):
            with patch.dict(sys.modules, {"upstox_client": None}):
                self.assertEqual(probe.main(), 2)

    def test_mocked_open_and_message_pass(self):
        with patch.dict(os.environ, ENV, clear=True):
            with patch.dict(sys.modules, {"upstox_client": self.sdk}):
                self.assertEqual(probe.main(), 0)
        self.assertTrue(FakeStreamer.last.disconnected)

    def test_explicit_recovery_ack_initializes_read_only_history(self):
        class FakeHistory:
            def __init__(self, *_args):
                self.calls = []
            def get_intra_day_candle_data(self, *args):
                self.calls.append(args)
                return types.SimpleNamespace(data=types.SimpleNamespace(candles=[]))
        self.sdk.HistoryV3Api = FakeHistory
        with patch.dict(os.environ, {**ENV,
                                      "FIX10_ISOLATED_RECOVERY_ACK": "READ_ONLY_HISTORY"},
                        clear=True):
            with patch.dict(sys.modules, {"upstox_client": self.sdk}):
                with patch.object(probe, "RECOVERY_OBSERVE_SECONDS", 0):
                    self.assertEqual(probe.main(), 3)
        self.assertTrue(FakeStreamer.last.disconnected)

    def test_recovery_is_not_initialized_without_separate_ack(self):
        with patch.dict(os.environ, ENV, clear=True):
            with patch.dict(sys.modules, {"upstox_client": self.sdk}):
                self.assertEqual(probe.main(), 0)

    def test_stale_tick_does_not_count_as_live_evidence(self):
        FakeStreamer.mode = "stale"
        # Patch the single event wait on the main thread only; the connector
        # still runs normally and can emit its stale mock message.
        original_wait = probe.threading.Event.wait
        def short_wait(event, timeout=None):
            if timeout == 45:
                return event.is_set()
            return original_wait(event, timeout)
        with patch.dict(os.environ, ENV, clear=True):
            with patch.dict(sys.modules, {"upstox_client": self.sdk}):
                with patch.object(probe.threading.Event, "wait", short_wait):
                    self.assertEqual(probe.main(), 3)
        self.assertTrue(FakeStreamer.last.disconnected)

    def test_disconnect_exception_is_safely_ignored(self):
        original = FakeStreamer.disconnect
        def broken_disconnect(streamer):
            streamer.disconnected = True
            raise RuntimeError("do not print SDK teardown secrets")
        try:
            FakeStreamer.disconnect = broken_disconnect
            with patch.dict(os.environ, ENV, clear=True):
                with patch.dict(sys.modules, {"upstox_client": self.sdk}):
                    self.assertEqual(probe.main(), 0)
            self.assertTrue(FakeStreamer.last.disconnected)
        finally:
            FakeStreamer.disconnect = original

    def test_connector_exception_is_inconclusive(self):
        FakeStreamer.mode = "raise"
        with patch.dict(os.environ, ENV, clear=True):
            with patch.dict(sys.modules, {"upstox_client": self.sdk}):
                self.assertEqual(probe.main(), 3)
        self.assertTrue(FakeStreamer.last.disconnected)

    def test_connection_exception_does_not_leak_sdk_details(self):
        FakeStreamer.mode = "raise"
        stderr = io.StringIO()
        with patch.dict(os.environ, ENV, clear=True):
            with patch.dict(sys.modules, {"upstox_client": self.sdk}):
                with redirect_stderr(stderr):
                    self.assertEqual(probe.main(), 3)
        self.assertNotIn("secret-bearing", stderr.getvalue())

    def test_missing_token_blocks_before_sdk(self):
        with patch.dict(os.environ, {**ENV, "UPSTOX_ACCESS_TOKEN": ""}, clear=True):
            with patch.dict(sys.modules, {"upstox_client": None}):
                self.assertEqual(probe.main(), 2)

    def test_error_event_is_inconclusive(self):
        FakeStreamer.mode = "error"
        with patch.dict(os.environ, ENV, clear=True):
            with patch.dict(sys.modules, {"upstox_client": self.sdk}):
                self.assertEqual(probe.main(), 3)
        self.assertTrue(FakeStreamer.last.disconnected)


if __name__ == "__main__":
    unittest.main()
