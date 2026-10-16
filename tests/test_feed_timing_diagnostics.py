"""Offline regression tests for the diagnostics-only scanner change."""
import ast
import contextlib
import io
import os
from unittest.mock import patch
from pathlib import Path
from types import SimpleNamespace
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "v2/backend/scanner.py"


def diagnostic_block():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    on_tick = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                   and node.name == "on_tick")
    matches = [node for node in ast.walk(on_tick)
               if isinstance(node, ast.If)
               and isinstance(node.test, ast.Compare)
               and isinstance(node.test.left, ast.Name)
               and node.test.left.id == "after"
               and any(isinstance(item, ast.Name) and item.id == "before"
                       for item in node.test.comparators)]
    if len(matches) != 1:
        raise AssertionError("Expected exactly one candle-close gate")
    return compile(ast.fix_missing_locations(ast.Module(body=matches, type_ignores=[])),
                   str(SOURCE), "exec")


class FeedTimingDiagnosticTests(unittest.TestCase):
    def run_block(self, after, before, enabled=True):
        calls = []
        output = io.StringIO()
        namespace = {
            "after": after, "before": before,
            "os": os,
            "ts": 1_000_000, "key": "NSE_EQ|TEST",
            "time": SimpleNamespace(time=lambda: 1001.25),
            "write_candle_quality": lambda: calls.append("quality"),
            "analyse": lambda key: calls.append(("analyse", key)),
        }
        with patch.dict(os.environ, {"FEED_TIMING_DIAGNOSTICS": "1" if enabled else "0"}):
            with contextlib.redirect_stdout(output):
                exec(diagnostic_block(), namespace)
        return calls, output.getvalue()

    def test_closed_candle_emits_timing_without_changing_analysis_order(self):
        calls, output = self.run_block(after=1, before=0)
        self.assertEqual(calls, ["quality", ("analyse", "NSE_EQ|TEST")])
        self.assertIn("FEED_TIMING: NSE_EQ|TEST", output)
        self.assertIn("TICK_AGE_MS: 1250", output)
        self.assertIn("QUALITY_ANALYSIS_MS:", output)

    def test_disabled_diagnostics_still_analyses_without_logging(self):
        calls, output = self.run_block(after=1, before=0, enabled=False)
        self.assertEqual(calls, ["quality", ("analyse", "NSE_EQ|TEST")])
        self.assertEqual(output, "")

    def test_no_closed_candle_does_not_emit_or_analyse(self):
        calls, output = self.run_block(after=0, before=0)
        self.assertEqual(calls, [])
        self.assertEqual(output, "")


if __name__ == "__main__":
    unittest.main()
