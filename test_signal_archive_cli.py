import contextlib
import io
import os
import unittest
from unittest.mock import patch
from v2.backend.signal_archive_cli import main

class SignalArchiveCliTests(unittest.TestCase):
    def test_missing_database_url_fails_without_secret(self):
        output = io.StringIO()
        with patch.dict(os.environ, {}, clear=True), contextlib.redirect_stderr(output):
            status = main(["sync"])
        self.assertEqual(status, 2)
        self.assertIn("not configured", output.getvalue())

    def test_report_requires_date(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                main(["report"])

    def test_init_rejects_report_date(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                main(["init", "--end-date", "2026-10-14"])

if __name__ == "__main__":
    unittest.main()
