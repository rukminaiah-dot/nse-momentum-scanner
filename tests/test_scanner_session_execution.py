"""Execute scanner on_tick with isolated fake market inputs; no broker/database."""
import ast
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
import unittest
from zoneinfo import ZoneInfo

from v2.backend.candle_manager import CandleManager

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


if __name__ == "__main__":
    unittest.main()
