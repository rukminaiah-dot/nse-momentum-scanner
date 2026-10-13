"""Offline mocked tests for the isolated Upstox websocket smoke harness."""
import os
import sys
import types
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
        self.callbacks["message"]({"mock": True})

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

    def test_missing_acknowledgement_blocks_before_sdk(self):
        with patch.dict(os.environ, {**ENV, "FIX10_LIVE_STREAM_ACK": ""}, clear=True):
            with patch.dict(sys.modules, {"upstox_client": None}):
                self.assertEqual(probe.main(), 2)

    def test_mocked_open_and_message_pass(self):
        with patch.dict(os.environ, ENV, clear=True):
            with patch.dict(sys.modules, {"upstox_client": self.sdk}):
                self.assertEqual(probe.main(), 0)
        self.assertTrue(FakeStreamer.last.disconnected)

    def test_connector_exception_is_inconclusive(self):
        FakeStreamer.mode = "raise"
        with patch.dict(os.environ, ENV, clear=True):
            with patch.dict(sys.modules, {"upstox_client": self.sdk}):
                self.assertEqual(probe.main(), 3)
        self.assertTrue(FakeStreamer.last.disconnected)

    def test_error_event_is_inconclusive(self):
        FakeStreamer.mode = "error"
        with patch.dict(os.environ, ENV, clear=True):
            with patch.dict(sys.modules, {"upstox_client": self.sdk}):
                self.assertEqual(probe.main(), 3)
        self.assertTrue(FakeStreamer.last.disconnected)


if __name__ == "__main__":
    unittest.main()
