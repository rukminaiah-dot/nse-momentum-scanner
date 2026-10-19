"""Source-extracted live scanner decision block versus isolated offline model.

No scanner module import: only AST-selected pure decision statements are run.
This does not validate scanner startup, persistence, broker, or live orders.
"""
import ast
import pathlib
import unittest
from datetime import datetime, timedelta

from v2.backend.candles import Candle
from v2.backend.indicators import ema, momentum, atr
from v2.backend.signal_engine import generate_signal
from v2.backend.market_regime import index_signal
from v2.backend.offline_signal_parity import evaluate, five_minute_trend


SOURCE = (pathlib.Path(__file__).resolve().parents[1] /
          "v2" / "backend" / "scanner.py")


def source_decision(history, *, is_index, is_stock, primary, nifty_market):
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    analyse = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                   and n.name == "analyse")
    # Extract scanner calculation/decision statements, excluding persistence,
    # order calls and printing. The market regime mapping is a local fixture.
    begin = next(i for i, n in enumerate(analyse.body)
                 if isinstance(n, ast.Assign)
                 and any(isinstance(t, ast.Name) and t.id == "closes"
                         for t in n.targets))
    end = next(i for i, n in enumerate(analyse.body)
               if isinstance(n, ast.If) and n.lineno > analyse.body[begin].lineno
               and any(isinstance(c, ast.Call)
                       and isinstance(c.func, ast.Name)
                       and c.func.id == "save_scan_result"
                       for c in ast.walk(n)))
    code = compile(ast.fix_missing_locations(ast.Module(body=analyse.body[begin:end],
                                                         type_ignores=[])),
                   str(SOURCE), "exec")
    key = "PRIMARY" if primary else ("SECONDARY" if is_index else "STOCK")
    indices = {"NIFTY 50": "PRIMARY", "SENSEX": "SECONDARY"}
    stocks = {"TEST": "STOCK"}
    def regime(price, e9, e20, vwap):
        return index_signal(price, e9, e20, vwap)
    context = {
        "history": history, "key": key, "INDICES": indices,
        "NIFTY_200": stocks, "ema": ema, "momentum": momentum,
        "atr": atr, "generate_signal": generate_signal,
        "index_signal": regime, "five_minute_trend": five_minute_trend,
        "market_regimes": {"NIFTY 50": nifty_market},
    }
    exec(code, context)
    return {name: context[name] for name in ("signal", "ema9", "ema20",
                                              "mom", "atr_value", "rvol",
                                              "trend_5m", "market")}


class ScannerSourceDecisionParityTests(unittest.TestCase):
    def test_scanner_source_decision_matches_offline_model(self):
        start = datetime(2026, 10, 16, 9, 15)
        regimes = {
            "up": [100 + i * .04 for i in range(100)],
            "down": [120 - i * .04 for i in range(100)],
            "reversal": [100 + i * .06 if i < 50
                         else 106 - i * .06 for i in range(100)],
            "flat": [100.0] * 100,
        }
        for name, prices in regimes.items():
            candles = []
            for i, price in enumerate(prices):
                c = Candle(price, 100 + i % 7)
                c.timestamp = start + timedelta(minutes=i)
                candles.append(c)
            for n in (20, 40, 60, 100):
                history = candles[:n]
                for is_index, is_stock, primary in (
                        (True, False, True), (True, False, False),
                        (False, True, False)):
                    with self.subTest(regime=name, count=n,
                                      index=is_index, primary=primary):
                        actual = source_decision(
                            history, is_index=is_index, is_stock=is_stock,
                            primary=primary, nifty_market="NEUTRAL")
                        expected = evaluate(
                            history, session_date=start.date(),
                            is_index=is_index, is_stock=is_stock,
                            is_primary_index=primary, nifty_market="NEUTRAL")
                        self.assertEqual(actual["signal"], expected["signal"])
                        self.assertEqual(actual["trend_5m"], expected["trend_5m"])
                        self.assertAlmostEqual(actual["ema9"], expected["ema9"])
                        self.assertAlmostEqual(actual["ema20"], expected["ema20"])
                        self.assertAlmostEqual(actual["mom"], expected["momentum"])
                        self.assertEqual(actual["rvol"], expected["rvol"])
                        self.assertEqual(actual["market"], expected["market"])


if __name__ == "__main__":
    unittest.main()
