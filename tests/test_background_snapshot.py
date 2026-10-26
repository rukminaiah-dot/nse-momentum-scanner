from concurrent.futures import ThreadPoolExecutor
from threading import Event
import unittest
from v2.backend.background_snapshot import BackgroundSnapshot


class BackgroundSnapshotTests(unittest.TestCase):
    def test_concurrent_polls_start_one_scan_and_return_immediately(self):
        cache = BackgroundSnapshot(300)
        entered, release = Event(), Event()
        calls = []
        def build():
            calls.append(1)
            entered.set()
            release.wait(2)
            return {'selected':[{'symbol':'TEST'}]}
        with ThreadPoolExecutor(max_workers=12) as pool:
            results = list(pool.map(lambda _:cache.get(build, {'status':'RUNNING'}), range(24)))
        self.assertTrue(entered.wait(1))
        self.assertEqual(len(calls), 1)
        self.assertTrue(all(row['refreshing'] for row in results))
        release.set()
        cache.worker.join(2)
        result = cache.get(build, {})
        self.assertEqual(result['selected'], [{'symbol':'TEST'}])
        self.assertFalse(result['refreshing'])
        self.assertEqual(len(calls), 1)

    def test_failed_refresh_retains_last_result_and_backs_off(self):
        cache = BackgroundSnapshot(300)
        cache.result = {'indices':[{'signal':'WAIT'}]}
        def fail():
            raise ValueError('secret provider payload')
        cache.get(fail, {})
        cache.worker.join(2)
        result = cache.get(fail, {})
        self.assertEqual(result['indices'], [{'signal':'WAIT'}])
        self.assertEqual(result['refresh_error'], 'ValueError')
        self.assertNotIn('secret', str(result))
        self.assertFalse(result['refreshing'])
