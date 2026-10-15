"""Execute scanner on_tick with isolated fake market inputs; no broker/database."""
import ast
from datetime import date, datetime, time
from pathlib import Path
from types import SimpleNamespace
import unittest
from zoneinfo import ZoneInfo

from v2.backend.candle_manager import CandleManager
from v2.backend.offline_scanner_session_dispatch import dispatch_offline_scanner_tick

SOURCE = Path(__file__).resolve().parents[1] / "v2/backend/scanner.py"
IST = ZoneInfo("Asia/Kolkata")


def milliseconds(hour, minute):
    return int(datetime(2026, 10, 15, hour, minute, tzinfo=IST).timestamp() * 1000)


def isolated_scanner(now_ms):
    tree = ast.parse(SOURCE.read_text())
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
              and n.name == "on_tick")
    calls = []
    manager = CandleManager(log_closed_candles=False)
    namespace = {
        "__name__": "v2.backend.scanner_isolated_test",
        "__package__": "v2.backend",
        "SESSION_CANDLE_GATE_ENABLED": True,
        "NIFTY_200": {"TEST": "NSE_EQ|TEST"},
        "candles": manager,
        "time": SimpleNamespace(time=lambda: now_ms / 1000),
        "_last_accepted_tick_ms": {},
        "record_feed_health": lambda key: calls.append("health"),
        "active_trades": {"NSE_EQ|TEST": {
            "id": 1, "target_1": 110, "target_2": 120,
            "invalidation": 90, "status": "OPEN"}},
        "sell": lambda *args: calls.append("sell"),
        "update_state": lambda *args: calls.append("trade_update"),
        "last_trade_updates": {},
        "last_cumulative_volumes": {},
        "write_candle_quality": lambda: calls.append("quality"),
        "analyse": lambda key: calls.append("analyse"),
        "GAP_RECOVERY_ENABLED": False,
    }
    exec(compile(ast.Module(body=[fn], type_ignores=[]), str(SOURCE), "exec"),
         namespace)
    return namespace["on_tick"], manager, namespace, calls


class ScannerSessionExecutionTests(unittest.TestCase):
    def test_regular_session_ticks_update_candle_health_and_volume(self):
        key = "NSE_EQ|TEST"
        on_tick, manager, state, calls = isolated_scanner(milliseconds(10, 1))
        on_tick(key, {"ltp": 100, "ltt": milliseconds(10, 0), "vtt": 500})
        on_tick(key, {"ltp": 101, "ltt": milliseconds(10, 1), "vtt": 508})
        self.assertEqual(state["_last_accepted_tick_ms"][key],
                         milliseconds(10, 1))
        self.assertEqual(state["last_cumulative_volumes"][key], 508)
        self.assertEqual(len(manager.completed[key]), 1)
        self.assertEqual(manager.completed[key][0].close, 100)
        self.assertEqual(manager.current[key]["candle"].volume, 8)
        self.assertEqual(calls.count("health"), 2)
        self.assertEqual(calls.count("quality"), 1)
        self.assertEqual(calls.count("analyse"), 1)

    def test_out_of_order_regular_tick_cannot_rewind_state(self):
        key = "NSE_EQ|TEST"
        on_tick, manager, state, calls = isolated_scanner(milliseconds(10, 1))
        on_tick(key, {"ltp": 101, "ltt": milliseconds(10, 1), "vtt": 508})
        before = list(calls)
        on_tick(key, {"ltp": 90, "ltt": milliseconds(10, 0), "vtt": 600})
        self.assertEqual(calls, before)
        self.assertEqual(state["_last_accepted_tick_ms"][key],
                         milliseconds(10, 1))
        self.assertEqual(state["last_cumulative_volumes"][key], 508)
        self.assertEqual(manager.current[key]["candle"].close, 101)
        self.assertEqual(len(manager.completed.get(key, [])), 0)

    def test_out_of_order_same_minute_tick_cannot_change_ohlc(self):
        key = "NSE_EQ|TEST"
        on_tick, manager, state, calls = isolated_scanner(milliseconds(10, 1) + 35000)
        newer = milliseconds(10, 1) + 30000
        older = milliseconds(10, 1) + 10000
        on_tick(key, {"ltp": 101, "ltt": newer, "vtt": 508})
        before = list(calls)
        on_tick(key, {"ltp": 80, "ltt": older, "vtt": 600})
        candle = manager.current[key]["candle"]
        self.assertEqual((candle.open, candle.high, candle.low, candle.close),
                         (101, 101, 101, 101))
        self.assertEqual(state["_last_accepted_tick_ms"][key], newer)
        self.assertEqual(state["last_cumulative_volumes"][key], 508)
        self.assertEqual(calls, before)

    def test_after_hours_tick_does_not_mutate_trade_volume_or_health(self):
        on_tick, manager, state, calls = isolated_scanner(milliseconds(15, 55))
        on_tick("NSE_EQ|TEST", {"ltp": 125, "ltt": milliseconds(15, 55),
                               "vtt": 500})
        self.assertEqual(calls, [])
        self.assertEqual(state["last_cumulative_volumes"], {})
        self.assertEqual(state["_last_accepted_tick_ms"], {})
        self.assertEqual(len(manager.current), 0)

    def test_repeated_after_hours_ticks_cannot_reopen_finalized_candle(self):
        on_tick, manager, state, calls = isolated_scanner(milliseconds(15, 55))
        key = "NSE_EQ|TEST"
        manager.update(key, 100, milliseconds(15, 29), 5)
        on_tick(key, {"ltp": 125, "ltt": milliseconds(15, 30), "vtt": 500})
        on_tick(key, {"ltp": 130, "ltt": milliseconds(15, 40), "vtt": 600})
        on_tick(key, {"ltp": 140, "ltt": milliseconds(15, 55), "vtt": 700})
        self.assertEqual(calls, ["quality"])
        self.assertNotIn(key, manager.current)
        self.assertEqual(len(manager.completed[key]), 1)
        self.assertEqual(manager.completed[key][0].close, 100)
        self.assertEqual(manager.completed[key][0].volume, 5)
        self.assertEqual(state["last_cumulative_volumes"], {})
        self.assertEqual(state["_last_accepted_tick_ms"], {})

    def test_close_tick_finalizes_without_trade_or_signal(self):
        on_tick, manager, state, calls = isolated_scanner(milliseconds(15, 30))
        manager.update("NSE_EQ|TEST", 100, milliseconds(15, 29), 5)
        on_tick("NSE_EQ|TEST", {"ltp": 125, "ltt": milliseconds(15, 30),
                               "vtt": 500})
        self.assertEqual(calls, ["quality"])
        self.assertEqual(state["last_cumulative_volumes"], {})
        self.assertNotIn("NSE_EQ|TEST", manager.current)
        self.assertEqual(len(manager.completed["NSE_EQ|TEST"]), 1)


    def test_calendar_dispatch_wraps_real_scanner_function_without_live_wiring(self):
        key = "NSE_EQ|TEST"
        day = date(2026, 10, 15)
        schedule = {day: (time(9, 15), time(15, 30))}
        on_tick, manager, state, calls = isolated_scanner(milliseconds(15, 30))
        # In this isolated harness only, the real on_tick body runs behind
        # calendar dispatch. No live scanner module or broker is imported.
        state["SESSION_CANDLE_GATE_ENABLED"] = False
        def dispatch(stamp, price):
            active = manager.current.get(key)
            active_minute = active["minute"] if active else None
            return dispatch_offline_scanner_tick(
                key, stamp, active_minute, frozenset((key,)), schedule,
                day, day, "Synthetic test calendar", True,
                on_update=lambda: on_tick(key, {"ltp": price, "ltt": stamp,
                                                "vtt": 500}),
                on_finalize=lambda: manager.finalize_verified_session_end(
                    key, stamp, schedule, day, day, "Synthetic test calendar",
                    True),
            )
        self.assertEqual(dispatch(milliseconds(15, 45), 200), "REJECT")
        self.assertEqual(calls, [])
        self.assertEqual(state["_last_accepted_tick_ms"], {})
        self.assertEqual(state["last_cumulative_volumes"], {})
        self.assertEqual(manager.current, {})
        self.assertEqual(dispatch(milliseconds(15, 29), 100), "UPDATE")
        self.assertIn(key, manager.current)
        self.assertEqual(dispatch(milliseconds(15, 30), 200),
                         "FINALIZE_LAST_MINUTE")
        self.assertNotIn(key, manager.current)
        self.assertEqual(len(manager.completed[key]), 1)
        self.assertEqual(manager.completed[key][0].close, 100)
        self.assertEqual(calls.count("health"), 1)
        self.assertEqual(calls.count("analyse"), 0)

    def test_calendar_dispatch_rejects_closed_day_without_scanner_side_effects(self):
        key = "NSE_EQ|TEST"
        day = date(2026, 10, 15)
        on_tick, manager, state, calls = isolated_scanner(milliseconds(10, 0))
        state["SESSION_CANDLE_GATE_ENABLED"] = False
        invoked = []
        result = dispatch_offline_scanner_tick(
            key, milliseconds(10, 0), None, frozenset((key,)),
            {day: None}, day, day, "Synthetic closed date", True,
            on_update=lambda: (invoked.append("update"),
                               on_tick(key, {"ltp": 100,
                                             "ltt": milliseconds(10, 0)})),
            on_finalize=lambda: invoked.append("finalize"),
        )
        self.assertEqual(result, "REJECT")
        self.assertEqual(invoked, [])
        self.assertEqual(calls, [])
        self.assertEqual(state["_last_accepted_tick_ms"], {})
        self.assertEqual(state["last_cumulative_volumes"], {})
        self.assertEqual(manager.current, {})

    def test_explicit_scanner_calendar_entrypoint_isolated_execution(self):
        key = "NSE_EQ|TEST"
        day = date(2026, 10, 15)
        schedule = {day: (time(9, 15), time(15, 30))}
        on_tick, manager, state, calls = isolated_scanner(milliseconds(15, 30))
        state["INDICES"] = {"INDEX": "NSE_INDEX|TEST"}
        state["SESSION_CANDLE_GATE_ENABLED"] = False
        tree = ast.parse(SOURCE.read_text())
        wrapper = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                       and n.name == "on_tick_with_verified_calendar")
        exec(compile(ast.Module(body=[wrapper], type_ignores=[]),
                     str(SOURCE), "exec"), state)
        gated = state["on_tick_with_verified_calendar"]
        def tick(hour, minute, price):
            return gated(key, {"ltp": price, "ltt": milliseconds(hour, minute),
                               "vtt": 500}, schedule, day, day,
                         "Synthetic test calendar", True)
        self.assertEqual(tick(15, 45, 200), "REJECT")
        self.assertEqual(calls, [])
        self.assertEqual(tick(15, 29, 100), "UPDATE")
        self.assertEqual(tick(15, 30, 200), "FINALIZE_LAST_MINUTE")
        self.assertEqual(manager.completed[key][0].close, 100)
        self.assertEqual(calls.count("health"), 1)
        self.assertEqual(calls.count("quality"), 1)
        self.assertEqual(tick(15, 36, 300), "REJECT")
        self.assertEqual(len(manager.completed[key]), 1)
        self.assertEqual(calls.count("health"), 1)

if __name__ == "__main__":
    unittest.main()
