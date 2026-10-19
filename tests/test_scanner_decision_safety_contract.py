"""Static scanner safety contract; never import the side-effectful scanner."""
import ast
import pathlib
import unittest


SCANNER = (pathlib.Path(__file__).resolve().parents[1] /
           "v2" / "backend" / "scanner.py")


class ScannerDecisionSafetyContractTests(unittest.TestCase):
    def test_trading_side_effect_is_after_continuity_and_entry_guards(self):
        tree = ast.parse(SCANNER.read_text(encoding="utf-8"))
        analyse = next(node for node in tree.body
                       if isinstance(node, ast.FunctionDef)
                       and node.name == "analyse")
        calls = [(node.lineno, node.func.id) for node in ast.walk(analyse)
                 if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Name)]
        buys = [line for line, name in calls if name == "buy"]
        saves = [line for line, name in calls if name == "save_scan_result"]
        self.assertEqual(len(buys), 1)
        self.assertEqual(len(saves), 1)
        source_lines = SCANNER.read_text(encoding="utf-8").splitlines()
        def locate(fragment):
            matches = [index + 1 for index, line in enumerate(source_lines)
                       if fragment in line and analyse.lineno <= index + 1 <= analyse.end_lineno]
            self.assertGreaterEqual(len(matches), 1, fragment)
            return matches[0]
        # Guard placement is necessary but not sufficient to prove correct
        # control flow. The full decision path still needs independent replay.
        guards = [
            locate("if len(history) < 20:"),
            locate("if continuity_reason:"),
            locate('if key in NIFTY_200.values() and signal in ("BUY", "SELL"):'),
        ]
        for guard in guards:
            self.assertLess(guard, saves[0])
            self.assertLess(guard, buys[0])
        self.assertLess(saves[0], buys[0])

    def test_no_new_unconditional_order_calls(self):
        tree = ast.parse(SCANNER.read_text(encoding="utf-8"))
        analyse = next(node for node in tree.body
                       if isinstance(node, ast.FunctionDef)
                       and node.name == "analyse")
        buy_calls = [node for node in ast.walk(analyse)
                     if isinstance(node, ast.Call)
                     and isinstance(node.func, ast.Name)
                     and node.func.id == "buy"]
        self.assertEqual(len(buy_calls), 1)
        buy_line = buy_calls[0].lineno
        enclosing_if = [node for node in ast.walk(analyse)
                        if isinstance(node, ast.If)
                        and node.lineno < buy_line <= node.end_lineno]
        self.assertTrue(any("signal == 'BUY'" in ast.unparse(node.test)
                            or 'signal == "BUY"' in ast.unparse(node.test)
                            for node in enclosing_if))


if __name__ == "__main__":
    unittest.main()
