"""Static read-only scanner safety contract; never import the side-effectful scanner."""
import ast
import pathlib
import unittest

SCANNER = (pathlib.Path(__file__).resolve().parents[1] /
           "v2" / "backend" / "scanner.py")


class ScannerDecisionSafetyContractTests(unittest.TestCase):
    def test_scanner_never_calls_trade_engine_or_broker_order_methods(self):
        tree = ast.parse(SCANNER.read_text(encoding="utf-8"))
        source = SCANNER.read_text(encoding="utf-8")
        forbidden = {"buy", "sell", "place_order", "submit_order", "modify_order", "cancel_order"}
        calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
                 and ((isinstance(node.func, ast.Name) and node.func.id in forbidden)
                      or (isinstance(node.func, ast.Attribute) and node.func.attr in forbidden))]
        self.assertEqual(calls, [])
        self.assertNotIn("trade_engine", source)

    def test_scanner_persists_only_research_setup_and_candle_rows(self):
        tree = ast.parse(SCANNER.read_text(encoding="utf-8"))
        analyse = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                       and node.name == "analyse")
        calls = [node.func.id for node in ast.walk(analyse)
                 if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)]
        self.assertIn("save_scan_result", calls)
        self.assertIn("save_stock_setup", calls)
        self.assertNotIn("buy", calls)
        self.assertNotIn("sell", calls)

    def test_stock_data_gates_persist_specific_wait_rows(self):
        tree = ast.parse(SCANNER.read_text(encoding="utf-8"))
        analyse = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                       and node.name == "analyse")
        wait_calls = [node for node in ast.walk(analyse) if isinstance(node, ast.Call)
                      and isinstance(node.func, ast.Name)
                      and node.func.id == "persist_stock_setup_wait"]
        self.assertEqual(len(wait_calls), 3)
        self.assertIn("latest 1-minute candle is stale or future-dated",
                      SCANNER.read_text(encoding="utf-8"))
        self.assertIn("require six consecutive completed bars",
                      SCANNER.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
