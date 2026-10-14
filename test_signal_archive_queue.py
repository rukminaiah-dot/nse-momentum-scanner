import threading
import unittest
from v2.backend.signal_archive_queue import SignalArchiveQueue

class ArchiveQueueTests(unittest.TestCase):
    def test_overflow_never_blocks_and_is_reported(self):
        archive = SignalArchiveQueue(lambda *args: "ARCHIVED_OR_ALREADY_PRESENT", max_pending=1)
        self.assertTrue(archive.submit(("A", "2026-10-14 10:00:00", 100, "BUY")))
        self.assertFalse(archive.submit(("B", "2026-10-14 10:00:00", 200, "BUY")))
        self.assertEqual(archive.status()["dropped"], 1)
        self.assertFalse(archive.status()["running"])

    def test_explicit_start_delivers_and_tracks_failures(self):
        completed = threading.Event()
        def deliver(*row):
            completed.set()
            return "ARCHIVE_FAILED"
        archive = SignalArchiveQueue(deliver, max_pending=2)
        archive.start()
        self.assertTrue(archive.submit(("A", "2026-10-14 10:00:00", 100, "BUY")))
        self.assertTrue(completed.wait(timeout=2))
        archive.pending.join()
        self.assertEqual(archive.status()["failed"], 1)
        self.assertEqual(archive.status()["delivered"], 0)

    def test_invalid_capacity(self):
        with self.assertRaises(ValueError):
            SignalArchiveQueue(lambda *args: None, max_pending=0)

if __name__ == "__main__":
    unittest.main()
