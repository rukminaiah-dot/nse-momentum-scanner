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

    def test_empty_history_still_loads_completed_intraday_rows(self):
        """Exercise preload with fake Upstox; no credentials or network."""
        import os
        from datetime import datetime, timedelta
        from types import SimpleNamespace
        from unittest.mock import patch
        from zoneinfo import ZoneInfo

        source = ast.parse(SCANNER.read_text())
        preload = next(n for n in source.body
                       if isinstance(n, ast.FunctionDef) and n.name == "preload_history")
        namespace = {}
        exec(compile(ast.Module(body=[preload], type_ignores=[]),
                     str(SCANNER), "exec"), namespace)
        now = datetime.now(ZoneInfo("Asia/Kolkata"))
        completed = (now - timedelta(minutes=2)).replace(second=0, microsecond=0)
        row = [completed.isoformat(), 100, 103, 99, 102, 15]
        calls = []

        class FakeApi:
            def __init__(self, client):
                pass
            def get_historical_candle_data1(self, *args):
                calls.append("historical")
                return SimpleNamespace(data=SimpleNamespace(candles=[]))
            def get_intra_day_candle_data(self, *args):
                calls.append("intraday")
                return SimpleNamespace(data=SimpleNamespace(candles=[row]))

        class FakeCandle:
            def __init__(self, price, volume):
                self.close, self.volume = price, volume

        class FakeLock:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False

        manager = SimpleNamespace(lock=FakeLock(), completed={})
        namespace.update(
            upstox_client=SimpleNamespace(
                Configuration=lambda: SimpleNamespace(access_token=None),
                ApiClient=lambda config: config, HistoryV3Api=FakeApi),
            os=os, Candle=FakeCandle, candles=manager,
            INDICES={}, NIFTY_200={"STOCK": "TEST_KEY"}, previous_closes={})
        with patch.dict(os.environ, {"UPSTOX_ACCESS_TOKEN": "offline-test"}):
            namespace["preload_history"]("TEST_KEY")
        self.assertEqual(calls, ["historical", "intraday"])
        self.assertEqual(len(manager.completed["TEST_KEY"]), 1)
        self.assertEqual(manager.completed["TEST_KEY"][0].timestamp,
                         completed.replace(tzinfo=None))

if __name__ == "__main__":
    unittest.main()
