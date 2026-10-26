import ast
from pathlib import Path
from types import SimpleNamespace
import unittest


class PreloadedIndexPublicationTests(unittest.TestCase):
    def test_indices_publish_before_stock_loop_finishes_without_live_signal(self):
        source = (Path(__file__).resolve().parents[1] / 'v2/backend/scanner.py').read_text()
        tree = ast.parse(source)
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'publish_preloaded_price')
        calls = []
        history = [SimpleNamespace(close=100+i) for i in range(20)]
        env = dict(INDICES={'NIFTY 50':'INDEX'}, NIFTY_200={'STOCK':'EQ'},
                   candles=SimpleNamespace(snapshot=lambda key:(history,None)),
                   instrument_symbols={'INDEX':'NIFTY 50','EQ':'STOCK'}, previous_closes={'INDEX':118},
                   ema=lambda bars,n:bars[-1],momentum=lambda bars:1,
                   five_minute_trend=lambda bars:'NEUTRAL',save_scan_result=lambda *args:calls.append(args))
        exec(compile(ast.Module(body=[function],type_ignores=[]), '<publication>', 'exec'),env)
        env['publish_preloaded_price']('INDEX')
        self.assertEqual(calls[0][0:2], ('NIFTY 50',119))
        self.assertEqual(calls[0][5:], ('PREVIOUS SESSION',None,'WAITING',118))
        env['publish_preloaded_price']('EQ')
        self.assertEqual(calls[1][5:], ('HISTORICAL_PRELOAD','NEUTRAL','WAITING',None))
        history.clear()
        env['publish_preloaded_price']('INDEX')
        self.assertEqual(len(calls),2)
        startup=source.split('if __name__ == "__main__":',1)[1]
        self.assertIn('Thread(target=warm_startup_universe, daemon=True).start()', startup)
        self.assertIn('publish_preloaded_price(key)', source.split('def warm_startup_instrument(key):',1)[1].split('def warm_startup_universe',1)[0])
