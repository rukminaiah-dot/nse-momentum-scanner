"""Offline scanner guard regression: inspect execution ordering, no Upstox imports."""
import ast
from pathlib import Path
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "v2/backend/scanner.py"


class ScannerSessionGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = ast.parse(SOURCE.read_text())
        cls.on_tick = next(n for n in cls.tree.body
                           if isinstance(n, ast.FunctionDef) and n.name == "on_tick")

    def test_session_guard_precedes_trade_volume_and_feed_health(self):
        body = self.on_tick.body
        guarded = next(i for i, n in enumerate(body)
                       if isinstance(n, ast.If)
                       and "SESSION_CANDLE_GATE_ENABLED" in ast.unparse(n.test))
        health = next(i for i, n in enumerate(body)
                      if isinstance(n, ast.Expr)
                      and "record_feed_health(" in ast.unparse(n))
        trade = next(i for i, n in enumerate(body)
                     if isinstance(n, ast.Assign)
                     and any(isinstance(t, ast.Name) and t.id == "trade"
                             for t in n.targets))
        volume = next(i for i, n in enumerate(body)
                      if isinstance(n, ast.Assign)
                      and any(isinstance(t, ast.Name) and t.id == "cumulative"
                              for t in n.targets))
        self.assertLess(guarded, health)
        self.assertLess(guarded, trade)
        self.assertLess(guarded, volume)

    def test_finalization_returns_without_running_signal_analysis(self):
        guard = next(n for n in self.on_tick.body if isinstance(n, ast.If)
                     and "SESSION_CANDLE_GATE_ENABLED" in ast.unparse(n.test))
        self.assertTrue(any(isinstance(n, ast.Return) for n in ast.walk(guard)))
        self.assertTrue(any(isinstance(n, ast.Call)
                            and isinstance(n.func, ast.Attribute)
                            and n.func.attr == "finalize_last_regular_minute"
                            for n in ast.walk(guard)))

    def test_default_flag_requires_explicit_opt_in(self):
        self.assertIn('os.getenv("ENABLE_NSE_SESSION_CANDLE_GATE") == "1"',
                      SOURCE.read_text())


if __name__ == "__main__":
    unittest.main()
