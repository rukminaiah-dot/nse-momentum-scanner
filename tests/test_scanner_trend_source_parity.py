"""Compare isolated 5-minute trend against the actual scanner function body.

Parse source and compile ONLY the verified pure function definition. Never
import scanner.py: module initialization can reach DB and broker integrations.
"""
import ast
import pathlib
import unittest
from datetime import datetime, timedelta

from v2.backend.candles import Candle
from v2.backend.offline_signal_parity import five_minute_trend as offline_trend


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCANNER = ROOT / "v2" / "backend" / "scanner.py"


def scanner_trend_from_source():
    tree = ast.parse(SCANNER.read_text(encoding="utf-8"))
    matches = [node for node in tree.body
               if isinstance(node, ast.FunctionDef)
               and node.name == "five_minute_trend"]
    if len(matches) != 1:
        raise AssertionError("expected exactly one scanner trend function")
    fn = matches[0]
    # Deliberately disallow calls or names that could introduce side effects.
    allowed_calls = {"hasattr", "len", "sorted", "append", "date", "replace",
                     "setdefault", "all", "range", "total_seconds"}
    allowed_names = {"history", "timed", "c", "session_date", "buckets", "ts",
                     "bucket", "complete", "group", "closes", "key", "range",
                     "hasattr", "len", "sorted", "i", "latest_groups"}
    for node in ast.walk(fn):
        if isinstance(node, (ast.Import, ast.ImportFrom, ast.Global, ast.Nonlocal,
                             ast.With, ast.AsyncWith, ast.Try, ast.Raise,
                             ast.Await, ast.Yield, ast.YieldFrom)):
            raise AssertionError("unexpected side-effect-capable syntax")
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                if node.func.id not in allowed_calls:
                    raise AssertionError("unexpected scanner call")
            elif isinstance(node.func, ast.Attribute):
                if node.func.attr not in allowed_calls:
                    raise AssertionError("unexpected scanner method call")
            else:
                raise AssertionError("unexpected dynamic scanner call")
    module = ast.fix_missing_locations(ast.Module(body=[fn], type_ignores=[]))
    namespace = {"__builtins__": {"hasattr": hasattr, "len": len,
                                    "sorted": sorted, "all": all, "range": range}}
    exec(compile(module, str(SCANNER), "exec"), namespace)
    return namespace["five_minute_trend"]


def bars(start, prices):
    result = []
    for i, price in enumerate(prices):
        candle = Candle(price, 100)
        candle.timestamp = start + timedelta(minutes=i)
        result.append(candle)
    return result


class ScannerTrendSourceParityTests(unittest.TestCase):
    def test_missing_minute_in_latest_buckets_blocks_trend(self):
        scanner_trend = scanner_trend_from_source()
        start = datetime(2026, 10, 16, 9, 15)
        case = bars(start, list(range(20)))
        # Keep five candles per clock bucket, but create a one-minute hole
        # in the middle bucket so counts alone cannot claim continuity.
        case = [c for c in case if c.timestamp != start + timedelta(minutes=7)]
        self.assertEqual(scanner_trend(case), "NEUTRAL")

    def test_source_extracted_function_matches_offline_trend(self):
        scanner_trend = scanner_trend_from_source()
        start = datetime(2026, 10, 16, 9, 15)
        cases = [
            [],
            bars(start, list(range(14))),
            bars(start, list(range(15))),
            bars(start, list(range(60))),
            bars(start, list(reversed(range(60)))),
            bars(start, [100] * 60),
            bars(start, [100, 101, 99, 102, 98] * 12),
            bars(start, list(range(25)))[::-1],
            bars(start, list(range(40))) + bars(start + timedelta(days=1),
                                                list(range(30))),
        ]
        for index, case in enumerate(cases):
            with self.subTest(case=index):
                self.assertEqual(offline_trend(case), scanner_trend(case))


if __name__ == "__main__":
    unittest.main()
