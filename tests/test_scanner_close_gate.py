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
        self.assertTrue(guarded_calls, "analysis must be gated by live close result")


if __name__ == "__main__":
    unittest.main()
