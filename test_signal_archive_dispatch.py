import unittest
from unittest.mock import patch
from v2.backend import signal_archive_dispatch as dispatch

class DispatchTests(unittest.TestCase):
    def test_lazy_start_and_queue_submission(self):
        class FakeQueue:
            def __init__(self, deliver, max_pending):
                self.deliver = deliver
                self.capacity = max_pending
                self.started = False
                self.rows = []
            def start(self):
                self.started = True
            def submit(self, row):
                self.rows.append(row)
                return True
            def status(self):
                return {"pending": len(self.rows), "dropped": 0, "failed": 0}
        with patch.object(dispatch, "_dispatcher", None), \
             patch.object(dispatch, "SignalArchiveQueue", FakeQueue):
            self.assertFalse(dispatch.archive_queue_status()["started"])
            row = ("A", "2026-10-14 10:00:00", 100, "BUY")
            self.assertTrue(dispatch.submit_observation(row))
            self.assertTrue(dispatch.archive_queue_status()["started"])
            self.assertTrue(dispatch._dispatcher.started)
            self.assertEqual(dispatch._dispatcher.rows, [row])
            self.assertEqual(dispatch._dispatcher.capacity, 512)

if __name__ == "__main__":
    unittest.main()
