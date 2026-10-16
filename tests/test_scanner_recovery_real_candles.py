"""End-to-end offline scanner gap detection with real CandleManager updates.

No scanner import, network, database, or broker calls.
"""
import ast
import pathlib
import unittest
from datetime import datetime
from unittest.mock import Mock
from zoneinfo import ZoneInfo

from v2.backend.candle_manager import CandleManager

SCANNER = pathlib.Path(__file__).resolve().parents[1] / "v2/backend/scanner.py"
IST = ZoneInfo("Asia/Kolkata")


def load_gap_hook(namespace):
    tree = ast.parse(SCANNER.read_text())
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                and n.name == "request_recovery_on_gap")
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(SCANNER), "exec"), namespace)
    return namespace["request_recovery_on_gap"]


def millis(hour, minute):
    return int(datetime(2026, 10, 16, hour, minute, tzinfo=IST).timestamp() * 1000)


class RealCandleGapHookTests(unittest.TestCase):
    def test_skipped_minutes_enqueue_only_after_live_rollover(self):
        manager = CandleManager()
        worker = Mock()
        worker.request.return_value = True
        hook = load_gap_hook({"candles": manager, "_recovery_worker": worker})
        self.assertIsNone(manager.update("X", 100, millis(9, 15)))
        self.assertFalse(hook("X"))
        self.assertIsNotNone(manager.update("X", 101, millis(9, 19)))
        self.assertTrue(hook("X"))
        worker.request.assert_called_once_with("X")
        # Recovered history must not produce a live close or another signal.
        self.assertIsNone(manager.update("X", 102, millis(9, 19)))
        self.assertTrue(hook("X"))  # Caller must invoke hook only on close.
        worker.request.assert_called_with("X")

    def test_contiguous_rollover_does_not_enqueue(self):
        manager = CandleManager()
        worker = Mock()
        hook = load_gap_hook({"candles": manager, "_recovery_worker": worker})
        manager.update("X", 100, millis(9, 15))
        manager.update("X", 101, millis(9, 16))
        self.assertFalse(hook("X"))
        worker.request.assert_not_called()

    def test_overnight_rollover_does_not_enqueue(self):
        manager = CandleManager()
        worker = Mock()
        hook = load_gap_hook({"candles": manager, "_recovery_worker": worker})
        manager.update("X", 100, millis(9, 15))
        next_day = int(datetime(2026, 10, 17, 9, 15, tzinfo=IST).timestamp() * 1000)
        manager.update("X", 101, next_day)
        self.assertFalse(hook("X"))
        worker.request.assert_not_called()
