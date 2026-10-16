"""Offline structural regression for scanner's live-close analysis gate.

Avoid importing scanner: import would pull in broker/DB dependencies.
"""
import ast
import pathlib
import unittest


SCANNER = pathlib.Path(__file__).resolve().parents[1] / "v2/backend/scanner.py"


class ScannerCloseGateTests(unittest.TestCase):
    def test_tick_analysis_requires_update_close_result(self):
        tree = ast.parse(SCANNER.read_text(encoding="utf-8"))
        tick = next(node for node in tree.body
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and node.name == "on_tick")
        update_assignments = [
            node for node in ast.walk(tick)
            if isinstance(node, ast.Assign)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Attribute)
            and node.value.func.attr == "update"
            and isinstance(node.value.func.value, ast.Name)
            and node.value.func.value.id == "candles"
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
        ]
        self.assertEqual(len(update_assignments), 1)
        result_name = update_assignments[0].targets[0].id
        guards = [
            node for node in ast.walk(tick)
            if isinstance(node, ast.If)
            and isinstance(node.test, ast.Compare)
            and isinstance(node.test.left, ast.Name)
            and node.test.left.id == result_name
            and len(node.test.ops) == 1
            and isinstance(node.test.ops[0], ast.IsNot)
            and len(node.test.comparators) == 1
            and isinstance(node.test.comparators[0], ast.Constant)
            and node.test.comparators[0].value is None
        ]
        self.assertEqual(len(guards), 1)
        guarded_calls = [
            node for statement in guards[0].body
            for node in ast.walk(statement)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "analyse"
        ]
        all_analysis_calls = [
            node for node in ast.walk(tick)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "analyse"
        ]
        self.assertTrue(guarded_calls, "analysis must be gated by live close result")
        self.assertEqual(
            {id(node) for node in all_analysis_calls},
            {id(node) for node in guarded_calls},
            "every on_tick analysis call must be inside the live-close guard",
        )


    def test_scanner_does_not_bypass_completed_history_lock(self):
        tree = ast.parse(SCANNER.read_text(encoding="utf-8"))
        direct = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Attribute)
            and node.attr == "completed"
            and isinstance(node.value, ast.Name)
            and node.value.id == "candles"
        ]
        self.assertEqual(direct, [], "scanner must use synchronized candle APIs")

    def test_scanner_uses_guarded_preload_api(self):
        tree = ast.parse(SCANNER.read_text(encoding="utf-8"))
        preload = next(node for node in tree.body
                       if isinstance(node, ast.FunctionDef)
                       and node.name == "preload_history")
        calls = [
            node for node in ast.walk(preload)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "preload_completed"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "candles"
        ]
        self.assertEqual(len(calls), 1)


    def test_result_timestamp_uses_instrument_mapping_and_snapshot(self):
        tree = ast.parse(SCANNER.read_text(encoding="utf-8"))
        helper = next(node for node in tree.body
                      if isinstance(node, ast.FunctionDef)
                      and node.name == "completed_candle_time_for_symbol")
        calls = [node for node in ast.walk(helper)
                 if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Attribute)
                 and node.func.attr == "snapshot"
                 and isinstance(node.func.value, ast.Name)
                 and node.func.value.id == "candles"]
        self.assertEqual(len(calls), 1)
        self.assertTrue(any(
            isinstance(node, ast.Name) and node.id == "instrument_symbols"
            for node in ast.walk(helper)))


    def test_timestamp_helper_runtime_uses_only_matching_instrument(self):
        from datetime import datetime
        from types import SimpleNamespace

        tree = ast.parse(SCANNER.read_text(encoding="utf-8"))
        helper = next(node for node in tree.body
                      if isinstance(node, ast.FunctionDef)
                      and node.name == "completed_candle_time_for_symbol")
        module = ast.Module(body=[helper], type_ignores=[])
        ast.fix_missing_locations(module)

        class SnapshotSpy:
            def __init__(self):
                self.requested = []

            def snapshot(self, key):
                self.requested.append(key)
                return ([SimpleNamespace(timestamp=datetime(2026, 10, 16, 9, 15))]
                        if key == "instrument-A" else []), None

        spy = SnapshotSpy()
        scope = {"candles": spy, "instrument_symbols": {
            "instrument-A": "AAA", "instrument-B": "BBB"}}
        exec(compile(module, str(SCANNER), "exec"), scope)
        self.assertEqual(scope["completed_candle_time_for_symbol"]("AAA"),
                         "2026-10-16 09:15:00")
        self.assertEqual(spy.requested, ["instrument-A"])
        self.assertIsNone(scope["completed_candle_time_for_symbol"]("UNKNOWN"))
        self.assertEqual(spy.requested, ["instrument-A"])


    def test_live_close_gate_runtime_ignores_recovery_history_growth(self):
        from types import SimpleNamespace
        tree = ast.parse(SCANNER.read_text(encoding="utf-8"))
        tick = next(node for node in tree.body
                    if isinstance(node, ast.FunctionDef) and node.name == "on_tick")
        assignment = next(node for node in ast.walk(tick)
                          if isinstance(node, ast.Assign)
                          and isinstance(node.value, ast.Call)
                          and isinstance(node.value.func, ast.Attribute)
                          and node.value.func.attr == "update"
                          and isinstance(node.value.func.value, ast.Name)
                          and node.value.func.value.id == "candles")
        guard = next(node for node in ast.walk(tick)
                     if isinstance(node, ast.If)
                     and isinstance(node.test, ast.Compare)
                     and isinstance(node.test.left, ast.Name)
                     and node.test.left.id == assignment.targets[0].id
                     and isinstance(node.test.ops[0], ast.IsNot))
        # Execute the actual close-event assignment and conditional with a
        # mocked candle manager; no scanner import, broker, or DB access.
        snippet = ast.Module(body=[assignment, guard], type_ignores=[])
        ast.fix_missing_locations(snippet)

        class FakeCandles:
            def __init__(self):
                self.history_size = 1
                self.closed = None

            def update(self, *args):
                self.history_size += 1  # recovery grew history independently
                return self.closed

        fake = FakeCandles()
        analyses = []
        scope = {
            "candles": fake, "key": "X", "price": 100,
            "ts": 1, "minute_volume": 0,
            "write_candle_quality": lambda: None,
            "analyse": lambda key: analyses.append(key),
        }
        exec(compile(snippet, str(SCANNER), "exec"), scope)
        self.assertEqual(fake.history_size, 2)
        self.assertEqual(analyses, [])
        fake.closed = SimpleNamespace(timestamp="closed")
        exec(compile(snippet, str(SCANNER), "exec"), scope)
        self.assertEqual(analyses, ["X"])


if __name__ == "__main__":
    unittest.main()
