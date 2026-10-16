"""Offline backup helper tests: never invoke a real database or pg_dump."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "database/scripts/backup_db.py"
spec = importlib.util.spec_from_file_location("offline_backup_db", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class BackupScaffoldTests(unittest.TestCase):
    def test_missing_credentials_rejected_without_subprocess(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(module.subprocess, "run") as run:
                with self.assertRaises(ValueError):
                    module.backup(tier="daily", root=Path(directory), url="")
                run.assert_not_called()

    def test_invalid_tier_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                module.backup(tier="../outside", root=Path(directory), url="test")

    def test_successful_dump_uses_private_atomic_file(self):
        with tempfile.TemporaryDirectory() as directory:
            def fake_run(args, *, stdout, stderr, check, env):
                self.assertEqual(args[1:4], ["--format=custom", "--no-owner", "--no-privileges"])
                self.assertNotIn("synthetic", " ".join(args))
                self.assertEqual(env["PGDATABASE"], "synthetic")
                stdout.write(b"PGDMP synthetic bytes")
            with patch.object(module.subprocess, "run", side_effect=fake_run):
                path = module.backup(tier="daily", root=Path(directory), url="synthetic")
            self.assertTrue(path.exists())
            self.assertEqual(path.read_bytes(), b"PGDMP synthetic bytes")
            self.assertEqual(list(path.parent.glob("*.partial")), [])

    def test_failed_dump_removes_partial_file(self):
        with tempfile.TemporaryDirectory() as directory:
            def fail(*args, **kwargs):
                kwargs["stdout"].write(b"incomplete")
                raise subprocess.CalledProcessError(1, "synthetic")
            with patch.object(module.subprocess, "run", side_effect=fail):
                with self.assertRaises(subprocess.CalledProcessError):
                    module.backup(tier="weekly", root=Path(directory), url="synthetic")
            self.assertEqual(list(Path(directory).rglob("*.dump")), [])
            self.assertEqual(list(Path(directory).rglob("*.partial")), [])


if __name__ == "__main__":
    unittest.main()
