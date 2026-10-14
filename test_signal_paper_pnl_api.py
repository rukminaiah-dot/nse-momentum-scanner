"""Dependency-free API contract inspection for the optional paper P&L route."""
import ast
import unittest
from pathlib import Path

class PaperPnlApiTests(unittest.TestCase):
    def test_paper_route_is_separate_and_read_only(self):
        source = Path("v2/backend/api.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        matches = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                   and node.name == "get_signal_paper_pnl"]
        self.assertEqual(len(matches), 1)
        route = matches[0]
        self.assertTrue(any(isinstance(d, ast.Call) and d.args and
                            isinstance(d.args[0], ast.Constant) and
                            d.args[0].value == "/api/v2/signal-accuracy/paper-pnl"
                            for d in route.decorator_list))
        self.assertIn("model_stock_pnl", ast.unparse(route))
        self.assertIn("order_execution_enabled", ast.unparse(route))
        self.assertIn("round_trip_cost_pct", ast.unparse(route))

if __name__ == "__main__":
    unittest.main()
