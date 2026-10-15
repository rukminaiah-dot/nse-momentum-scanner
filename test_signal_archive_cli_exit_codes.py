import contextlib
import io
import os
import sqlite3
import sys
import types
import unittest
from unittest.mock import patch

from v2.backend.signal_archive_cli import main


class SignalArchiveCliFailureTests(unittest.TestCase):
    def _run(self, action, *, sync=None, verify=None):
        """Exercise CLI exit status with a fake connection, never a real database."""
        class FakeConnection:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False

        fake_psycopg = types.ModuleType("psycopg")
        fake_psycopg.Error = type("FakePgError", (Exception,), {})
        fake_psycopg.connect = lambda *args, **kwargs: FakeConnection()
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.dict(sys.modules, {"psycopg": fake_psycopg}), \
             patch.dict(os.environ, {"DATABASE_URL": "placeholder-not-a-real-url"}), \
             patch("v2.backend.signal_archive_sync.sync_observed_signals", side_effect=sync) if isinstance(sync, Exception) else patch("v2.backend.signal_archive_sync.sync_observed_signals", return_value=sync), \
             patch("v2.backend.signal_archive_health.compare_archive_keys", return_value=verify), \
             contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main([action])
        return code, stdout.getvalue(), stderr.getvalue()

    def test_duplicate_source_rows_exit_nonzero(self):
        code, out, err = self._run("sync", sync=ValueError("duplicate SQLite candle keys"))
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("duplicate SQLite candle keys", err)
        self.assertNotIn("placeholder-not-a-real-url", err)

    def test_missing_sqlite_file_exit_nonzero(self):
        code, out, err = self._run("sync", sync=sqlite3.OperationalError("unable to open database file"))
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("sqlite", err.lower())
        self.assertNotIn("placeholder-not-a-real-url", err)

    def test_inconclusive_verification_exit_nonzero(self):
        result = {"available_source_reconciliation_verified": False,
                  "missing_from_archive": [], "mismatched_archive_values": []}
        code, out, err = self._run("verify", verify=result)
        self.assertEqual(code, 3)
        self.assertIn('"available_source_reconciliation_verified": false', out)
        self.assertEqual(err, "")

    def test_verified_reconciliation_exits_zero(self):
        result = {"available_source_reconciliation_verified": True,
                  "missing_from_archive": [], "mismatched_archive_values": []}
        code, _, err = self._run("verify", verify=result)
        self.assertEqual(code, 0)
        self.assertEqual(err, "")


if __name__ == "__main__":
    unittest.main()
