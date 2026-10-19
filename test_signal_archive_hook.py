import os
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import sys
from v2.backend import signal_archive_hook as hook
from v2.backend.signal_archive_hook import archive_observed_signal

class ArchiveHookTests(unittest.TestCase):
    def test_disabled_without_opt_in(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(archive_observed_signal("A", "2026-10-14 10:00:00", 100, "BUY"), "DISABLED")
    def test_opt_in_requires_database_url(self):
        with patch.dict(os.environ, {"ENABLE_SIGNAL_ARCHIVE_POSTGRES": "1"}, clear=True):
            self.assertEqual(archive_observed_signal("A", "2026-10-14 10:00:00", 100, "BUY"), "MISSING_DATABASE_URL")
    def test_connection_reused_and_committed(self):
        class FakeConnection:
            closed = False
            commits = 0
            def commit(self):
                self.commits += 1
            def close(self):
                self.closed = True
        connections = []
        def connect(*args, **kwargs):
            obj = FakeConnection()
            connections.append(obj)
            return obj
        with patch.dict(os.environ, {"ENABLE_SIGNAL_ARCHIVE_POSTGRES": "1",
                                     "DATABASE_URL": "postgres://example"}, clear=True), \
             patch.dict(sys.modules, {"psycopg": SimpleNamespace(connect=connect)}), \
             patch("v2.backend.signal_archive_postgres.archive_signal_rows", return_value=1):
            try:
                self.assertEqual(hook.archive_observed_signal("A", "2026-10-14 10:00:00", 100, "BUY"),
                                 "ARCHIVED_OR_ALREADY_PRESENT")
                self.assertEqual(hook.archive_observed_signal("A", "2026-10-14 10:01:00", 101, "SELL"),
                                 "ARCHIVED_OR_ALREADY_PRESENT")
                self.assertEqual(len(connections), 1)
                self.assertEqual(connections[0].commits, 2)
            finally:
                hook.close_archive_connection()

    def test_other_flag_value_is_disabled(self):
        with patch.dict(os.environ, {"ENABLE_SIGNAL_ARCHIVE_POSTGRES": "true"}, clear=True):
            self.assertEqual(archive_observed_signal("A", "2026-10-14 10:00:00", 100, "BUY"), "DISABLED")

if __name__ == "__main__":
    unittest.main()
