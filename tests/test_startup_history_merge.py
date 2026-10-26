import ast
from datetime import datetime, timedelta
from pathlib import Path
from threading import Event
from types import SimpleNamespace
import unittest
from v2.backend.candle_manager import CandleManager
from v2.backend.candles import Candle


class StartupHistoryTests(unittest.TestCase):
    def test_preload_after_stream_start_preserves_active_and_existing_candles(self):
        tree = ast.parse((Path(__file__).resolve().parents[1]/'v2/backend/scanner.py').read_text())
        helper = next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='install_startup_history')
        manager = CandleManager()
        stamp = datetime(2026,10,26,10,0)
        from zoneinfo import ZoneInfo
        epoch = int(stamp.replace(tzinfo=ZoneInfo('Asia/Kolkata')).timestamp()*1000)
        manager.update('X',100,epoch)
        manager.update('X',101,epoch+60000)
        def bar(minute, close):
            candle=Candle(close,10)
            candle.timestamp=minute
            return candle
        env={'candles':manager}
        exec(compile(ast.Module(body=[helper],type_ignores=[]),'<merge>','exec'),env)
        env['install_startup_history']('X',[bar(stamp-timedelta(minutes=1),99),bar(stamp,900),bar(stamp+timedelta(minutes=2),999)])
        history,active=manager.snapshot('X')
        self.assertEqual([(x.timestamp,x.close) for x in history],[(stamp-timedelta(minutes=1),99),(stamp,100)])
        self.assertEqual(active,stamp+timedelta(minutes=1))
        closed=manager.update('X',102,epoch+120000)
        self.assertEqual(closed.close,101)

    def test_stream_starts_while_history_worker_is_still_waiting(self):
        tree=ast.parse((Path(__file__).resolve().parents[1]/'v2/backend/scanner.py').read_text())
        main=next(n for n in tree.body if isinstance(n,ast.If) and isinstance(n.test,ast.Compare) and isinstance(n.test.left,ast.Name) and n.test.left.id=='__name__')
        entered,release,connected=Event(),Event(),Event()
        def warm():
            entered.set()
            release.wait(2)
        def connect():
            self.assertTrue(entered.wait(1))
            self.assertFalse(release.is_set())
            connected.set()
        env={'__name__':'__main__','init_db':lambda:None,'load_stock_setup_states':lambda:None,
             'reset_scanner_results':lambda:None,'warm_startup_universe':warm,
             'os':SimpleNamespace(environ={}), 'configure_gap_recovery':lambda **kwargs:None,
             'UpstoxLiveV3':lambda **kwargs:SimpleNamespace(connect=connect),'on_tick':None,'_recovery_worker':None}
        try:
            exec(compile(ast.Module(body=[main],type_ignores=[]),'<startup>','exec'),env)
            self.assertTrue(connected.is_set())
        finally:
            release.set()
