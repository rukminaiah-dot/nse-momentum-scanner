"""Offline scanner recovery wiring tests; scanner imports never execute."""
import ast
import pathlib
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock

SCANNER = pathlib.Path(__file__).resolve().parents[1] / "v2/backend/scanner.py"


def scanner_function(name, namespace):
    tree = ast.parse(SCANNER.read_text())
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(SCANNER), "exec"), namespace)
    return namespace[name]


class ScannerRecoveryWiringTests(unittest.TestCase):
    def test_disabled_by_default_and_explicit_enable(self):
        state = {"_recovery_worker": None, "GapRecoveryWorker": Mock(return_value=Mock()),
                 "candles": SimpleNamespace(snapshot=Mock(), merge_verified_recovery=Mock()),
                 "fetch_recovery_rows": Mock()}
        configure = scanner_function("configure_gap_recovery", state)
        self.assertIsNone(configure(enabled=False))
        self.assertEqual(state["GapRecoveryWorker"].call_count, 0)
        worker = configure(enabled=True, fetch_rows=Mock())
        self.assertIs(worker, state["_recovery_worker"])
        self.assertEqual(state["GapRecoveryWorker"].call_count, 1)
        self.assertIs(configure(enabled=True), worker)
        self.assertEqual(state["GapRecoveryWorker"].call_count, 1)
        self.assertIsNone(configure(enabled=False))
        worker.close.assert_called_once_with(timeout=5)
        self.assertIsNone(state["_recovery_worker"])
        self.assertIsNone(configure(enabled=False))
        worker.close.assert_called_once_with(timeout=5)

    def test_scanner_staging_requires_two_explicit_flags(self):
        tree = ast.parse(SCANNER.read_text())
        main = next(n for n in tree.body if isinstance(n, ast.If)
                    and isinstance(n.test, ast.Compare)
                    and isinstance(n.test.left, ast.Name)
                    and n.test.left.id == "__name__")
        assignments = [n for n in main.body if isinstance(n, ast.Assign)
                       and any(isinstance(t, ast.Name) and t.id == "recovery_enabled"
                               for t in n.targets)]
        self.assertEqual(len(assignments), 1)
        expression = assignments[0].value
        self.assertIsInstance(expression, ast.BoolOp)
        self.assertIsInstance(expression.op, ast.And)
        self.assertEqual(len(expression.values), 2)
        keys = {n.value for n in ast.walk(expression)
                if isinstance(n, ast.Constant) and isinstance(n.value, str)}
        self.assertTrue({"NSE_RECOVERY_MODE", "staging",
                         "NSE_ENABLE_VERIFIED_GAP_RECOVERY", "1"} <= keys)

    def test_only_real_same_session_gap_enqueues(self):
        t = lambda hour, minute, day=16: datetime(2026, 10, day, hour, minute)
        worker = Mock()
        worker.request.return_value = True
        candles = SimpleNamespace(snapshot=Mock())
        state = {"_recovery_worker": worker, "candles": candles}
        request = scanner_function("request_recovery_on_gap", state)
        make = lambda minute: SimpleNamespace(timestamp=minute)
        cases = [
            ([make(t(9, 15)), make(t(9, 17))], t(9, 19), True),
            ([make(t(9, 15)), make(t(9, 16))], t(9, 17), False),
            ([make(t(9, 15, 15)), make(t(9, 17))], t(9, 19), True),
            ([make(t(9, 15)), make(t(9, 17))], t(9, 18), False),
            ([], t(9, 18), False),
            ([make(t(9, 15))], t(9, 17), True),
        ]
        for history, active, expected in cases:
            with self.subTest(history=history, active=active):
                worker.reset_mock()
                candles.snapshot.return_value = history, active
                self.assertEqual(request("X"), expected)
                self.assertEqual(worker.request.call_count, int(expected))
        state["_recovery_worker"] = None
        self.assertFalse(request("X"))

    def test_recovery_only_requested_after_live_close(self):
        tree = ast.parse(SCANNER.read_text())
        tick = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "on_tick")
        calls = [(n, p) for p in ast.walk(tick) for n in ast.iter_child_nodes(p)
                 if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                 and n.func.id == "request_recovery_on_gap"]
        self.assertEqual(len(calls), 1)
        self.assertTrue(any(isinstance(n, ast.If) and
                            any(isinstance(c, ast.Call) and isinstance(c.func, ast.Name)
                                and c.func.id == "request_recovery_on_gap"
                                for c in ast.walk(n))
                            for n in ast.walk(tick)))
