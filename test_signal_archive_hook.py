import os
import unittest
from unittest.mock import patch
from v2.backend.signal_archive_hook import archive_observed_signal

class ArchiveHookTests(unittest.TestCase):
    def test_disabled_without_opt_in(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(archive_observed_signal("A", "2026-10-14 10:00:00", 100, "BUY"), "DISABLED")
    def test_opt_in_requires_database_url(self):
        with patch.dict(os.environ, {"ENABLE_SIGNAL_ARCHIVE_POSTGRES": "1"}, clear=True):
            self.assertEqual(archive_observed_signal("A", "2026-10-14 10:00:00", 100, "BUY"), "MISSING_DATABASE_URL")
    def test_other_flag_value_is_disabled(self):
        with patch.dict(os.environ, {"ENABLE_SIGNAL_ARCHIVE_POSTGRES": "true"}, clear=True):
            self.assertEqual(archive_observed_signal("A", "2026-10-14 10:00:00", 100, "BUY"), "DISABLED")

if __name__ == "__main__":
    unittest.main()
