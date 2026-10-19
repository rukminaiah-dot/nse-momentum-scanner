import ast
import unittest
from pathlib import Path

class ArchiveHealthApiContractTests(unittest.TestCase):
    def test_read_only_route_and_no_order_execution(self):
        source = Path("v2/backend/api.py").read_text()
        module = ast.parse(source)
        matches = [node for node in module.body
                   if isinstance(node, ast.FunctionDef)
                   and node.name == "get_signal_archive_health"]
        self.assertEqual(len(matches), 1)
        node = matches[0]
        self.assertTrue(any(
            isinstance(dec, ast.Call) and dec.args
            and isinstance(dec.args[0], ast.Constant)
            and dec.args[0].value == "/api/v2/signal-accuracy/archive-health"
            for dec in node.decorator_list
        ))
        function_source = ast.get_source_segment(source, node)
        self.assertIn("archive_delivery_health()", function_source)
        self.assertIn('result["order_execution_enabled"] = False', function_source)
        self.assertIn('result["archive_enabled"]', function_source)

if __name__ == "__main__":
    unittest.main()
