import os
import tempfile
import unittest
from unittest.mock import patch

from v2.backend import nifty_pe_archive


class NiftyPeHistoryArchiveTests(unittest.TestCase):
    def test_history_returns_latest_records_in_chronological_order(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(nifty_pe_archive, "DB_PATH", __import__("pathlib").Path(folder) / "pe.db"), \
                 patch.dict(os.environ, {}, clear=False):
                os.environ.pop("DATABASE_URL", None)
                for day, value in [
                    ("2026-10-15", 20.0), ("2026-10-16", 19.9),
                    ("2026-10-19", 19.8), ("2026-10-20", 19.7),
                ]:
                    nifty_pe_archive.save_daily_nifty_pe({
                        "session_date": day, "value": value, "as_of": day+" 15:30",
                        "fetched_at": day+"T16:00:00+05:30", "source": "NSE Indices",
                        "basis": "trailing earnings",
                    })
                rows, storage = nifty_pe_archive.read_nifty_pe_history(limit=3)
        self.assertEqual([row["session_date"] for row in rows],
                         ["2026-10-16", "2026-10-19", "2026-10-20"])
        self.assertEqual(storage, "LOCAL_FALLBACK")
        self.assertTrue(rows[0]["value"] > rows[-1]["value"])


if __name__ == "__main__":
    unittest.main()
