"""Offline tests for the isolated authenticated historical adapter."""
import unittest
from types import SimpleNamespace

from isolated_upstox_history import make_historical_fetch


class HistoryAdapterTests(unittest.TestCase):
    def test_fetch_only_authorized_instrument_and_one_minute_interval(self):
        class FakeHistory:
            def __init__(self):
                self.calls = []
            def get_intra_day_candle_data(self, *args):
                self.calls.append(args)
                return SimpleNamespace(data=SimpleNamespace(candles=[]))
        api = FakeHistory()
        fetch = make_historical_fetch(api, "AUTHORIZED")
        self.assertEqual(fetch("AUTHORIZED"), [])
        self.assertEqual(api.calls, [("AUTHORIZED", "minutes", "1")])
        with self.assertRaises(ValueError):
            fetch("OTHER")
        self.assertEqual(len(api.calls), 1)

    def test_malformed_response_fails_closed(self):
        for response in (None, SimpleNamespace(data=None),
                         SimpleNamespace(data=SimpleNamespace(candles=None)),
                         SimpleNamespace(data=SimpleNamespace(candles="bad"))):
            class FakeHistory:
                def get_intra_day_candle_data(self, *_):
                    return response
            with self.subTest(response=repr(response)):
                with self.assertRaises(ValueError):
                    make_historical_fetch(FakeHistory(), "AUTHORIZED")("AUTHORIZED")

    def test_empty_instrument_rejected(self):
        with self.assertRaises(ValueError):
            make_historical_fetch(object(), "")


if __name__ == "__main__":
    unittest.main()
