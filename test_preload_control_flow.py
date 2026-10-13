"""Guard startup preload against early exit before same-day Upstox fetch."""
import ast
import pathlib
import unittest

SCANNER = pathlib.Path(__file__).parent / "v2" / "backend" / "scanner.py"

class PreloadControlFlowTests(unittest.TestCase):
    def test_missing_previous_day_rows_does_not_exit_before_intraday(self):
        tree = ast.parse(SCANNER.read_text())
        preload = next(node for node in tree.body
                       if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                       and node.name == "preload_history")
        intraday_calls = [
            n for n in ast.walk(preload)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and n.func.attr == "get_intra_day_candle_data"
        ]
        self.assertTrue(intraday_calls, "current-session preload must exist")
        for node in ast.walk(preload):
            if not isinstance(node, ast.If):
                continue
            condition = ast.unparse(node.test)
            if condition == "not rows":
                self.assertFalse(any(isinstance(x, ast.Return)
                                     for statement in node.body
                                     for x in ast.walk(statement)),
                                 "empty historical rows must not skip intraday preload")
                return
        self.fail("expected historical empty-rows guard")

if __name__ == "__main__":
    unittest.main()
