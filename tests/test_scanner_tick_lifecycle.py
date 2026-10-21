"""Offline read-only tests for the scanner's real on_tick lifecycle.

The actual scanner module is not imported. The handler runs with fake candle,
feed-health and analysis functions; no network, broker, or database is used.
"""
import ast
import math
import pathlib
import time
import unittest
from unittest.mock import Mock

SOURCE = (pathlib.Path(__file__).resolve().parents[1] /
          "v2" / "backend" / "scanner.py")


class ScannerTickLifecycleTests(unittest.TestCase):
    def setUp(self):
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
        node = next(item for item in tree.body
                    if isinstance(item, ast.FunctionDef)
                    and item.name == "on_tick")
        code = compile(ast.fix_missing_locations(ast.Module(
            body=[node], type_ignores=[])), str(SOURCE), "exec")

        self.calls = []
        self.closed = None

        class FakeCandles:
            def update(inner, key, price, timestamp, volume):
                self.calls.append(("candle", key, price, timestamp, volume))
                return self.closed

        self.context = {
            "time": time,
            "math": math,
            "INDICES": {"NIFTY 50": "INDEX"},
            "NIFTY_200": {"TEST": "STOCK"},
            "_last_accepted_tick_ms": {},
            "last_cumulative_volumes": {},
            "last_trade_updates": {},
            "active_trades": {},
            "candles": FakeCandles(),
            "update_market_recovery": Mock(),
            "record_feed_health": lambda key: self.calls.append(("health", key)),
            "request_recovery_on_gap": lambda key: self.calls.append(("recovery", key)),
            "write_candle_quality": lambda: self.calls.append(("quality",)),
            "analyse": lambda key: self.calls.append(("analyse", key)),
            "_decision_context": lambda key, price, tick_time: {"key": key, "price": price},
            "update_state": lambda *args, **kwargs: self.calls.append(("update_state", args)),
            "sell": lambda *args, **kwargs: self.calls.append(("sell", args)),
        }
        exec(code, self.context)

    def tick(self, price, timestamp_ms=None, volume=100):
        timestamp_ms = timestamp_ms or int(time.time() * 1000)
        self.context["on_tick"](
            "STOCK", {"ltp": price, "ltt": timestamp_ms, "vtt": volume}
        )
        return timestamp_ms

    def test_invalid_prices_are_rejected_before_position_or_feed_updates(self):
        now_ms = int(time.time() * 1000)
        self.context["active_trades"]["STOCK"] = {
            "id": 4, "target_1": 101, "target_2": 102,
            "invalidation": 99, "status": "OPEN",
        }
        for price in ("not-a-price", float("nan"), float("inf"), 0, -1):
            with self.subTest(price=price):
                self.context["on_tick"](
                    "STOCK", {"ltp": price, "ltt": now_ms, "vtt": 500}
                )

        self.assertEqual(self.calls, [])
        self.assertEqual(self.context["_last_accepted_tick_ms"], {})
        self.assertEqual(self.context["last_cumulative_volumes"], {})
        self.assertEqual(self.context["active_trades"]["STOCK"]["status"], "OPEN")

    def test_stale_future_and_malformed_ticks_have_no_lifecycle_effects(self):
        now_ms = int(time.time() * 1000)
        self.context["active_trades"]["STOCK"] = {
            "id": 4, "target_1": 101, "target_2": 102,
            "invalidation": 99, "status": "OPEN",
        }
        for value in (now_ms - 180_000, now_ms + 60_000, "not-a-time"):
            with self.subTest(timestamp=value):
                self.context["on_tick"](
                    "STOCK", {"ltp": 101.5, "ltt": value, "vtt": 500}
                )

        self.assertEqual(self.calls, [])
        self.assertEqual(self.context["_last_accepted_tick_ms"], {})
        self.assertEqual(self.context["last_cumulative_volumes"], {})
        self.assertEqual(self.context["active_trades"]["STOCK"]["status"], "OPEN")

    def test_invalid_cumulative_volume_does_not_poison_baseline_or_crash(self):
        now_ms = int(time.time() * 1000)
        values = ("not-a-volume", float("nan"), float("inf"), -1)
        for offset, value in enumerate(values):
            with self.subTest(volume=value):
                self.context["on_tick"](
                    "STOCK",
                    {"ltp": 100.5, "ltt": now_ms + offset * 1000, "vtt": value},
                )

        self.assertEqual(self.context["last_cumulative_volumes"], {})
        candles = [call for call in self.calls if call[0] == "candle"]
        self.assertEqual(len(candles), len(values))
        self.assertTrue(all(call[4] == 0 for call in candles))

    def test_existing_trade_state_is_not_mutated_by_scanner_ticks(self):
        trade = {"id": 7, "target_1": 101, "target_2": 102,
                 "invalidation": 99, "status": "OPEN"}
        self.context["active_trades"]["STOCK"] = trade
        first = self.tick(101.5, volume=100)
        self.tick(102.5, timestamp_ms=first + 1000, volume=125)
        self.assertEqual(trade["status"], "OPEN")
        self.assertFalse(any(call[0] in ("sell", "update_state") for call in self.calls))
        self.assertEqual(self.context["last_cumulative_volumes"]["STOCK"], 125)

    def test_invalidating_price_does_not_write_trade_lifecycle(self):
        trade = {"id": 11, "target_1": 101, "target_2": 102,
                 "invalidation": 99, "status": "OPEN"}
        self.context["active_trades"]["STOCK"] = trade
        now_ms = int(time.time() * 1000)
        self.tick(98.5, timestamp_ms=now_ms)
        self.closed = type("ClosedCandle", (), {"close": 98.5})()
        self.tick(98.5, timestamp_ms=now_ms + 1000)
        self.assertEqual(trade["status"], "OPEN")
        self.assertFalse(any(call[0] in ("sell", "update_state") for call in self.calls))

    def test_live_rollover_runs_gap_quality_and_analysis_in_order(self):
        self.closed = object()
        self.tick(100.5)

        stages = [call[0] for call in self.calls]
        self.assertEqual(stages, ["health", "candle", "recovery", "quality", "analyse"])


if __name__ == "__main__":
    unittest.main()
