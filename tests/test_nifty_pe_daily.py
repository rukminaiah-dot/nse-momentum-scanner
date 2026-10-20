import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

import sys
import types

try:
    from v2.backend import reversal_context
except ModuleNotFoundError as exc:
    if exc.name != "fastapi":
        raise
    fastapi_stub = types.ModuleType("fastapi")

    class APIRouterStub:
        def get(self, *_args, **_kwargs):
            return lambda handler: handler

    fastapi_stub.APIRouter = APIRouterStub
    sys.modules["fastapi"] = fastapi_stub
    from v2.backend import reversal_context
from v2.backend import nifty_pe_archive


IST = ZoneInfo("Asia/Kolkata")


class NiftyPeDailyTests(unittest.TestCase):
    def setUp(self):
        reversal_context._pe_cache = None
        reversal_context._pe_cache_date = None
        reversal_context._pe_last_attempt = None

    def tearDown(self):
        reversal_context._pe_cache = None
        reversal_context._pe_cache_date = None
        reversal_context._pe_last_attempt = None

    def test_source_timestamp_parser_preserves_actual_session_date(self):
        self.assertEqual(
            reversal_context._nse_pe_session_date("19-Oct-2026 15:30"),
            ("2026-10-19", "19-Oct-2026 15:30"),
        )
        self.assertEqual(
            reversal_context._nse_pe_session_date("2026-10-20T15:30:00"),
            ("2026-10-20", "2026-10-20T15:30:00+05:30"),
        )
        self.assertIsNone(reversal_context._nse_pe_session_date(""))

    def test_before_daily_close_shows_last_saved_reading_without_live_fetch(self):
        old = {"session_date": "2026-10-19", "value": 19.33,
               "as_of": "19-Oct-2026 15:30", "fetched_at": "2026-10-19T16:00:00+05:30",
               "source": "NSE Indices daily snapshot", "basis": "NSE index P/E"}
        now = datetime(2026, 10, 20, 12, 0, tzinfo=IST)
        with patch.object(reversal_context, "read_latest_nifty_pe", return_value=(old, "POSTGRESQL")), \
             patch.object(reversal_context, "_fetch_daily_nifty_pe") as fetch:
            result = reversal_context._nse_index_pe(now)
        fetch.assert_not_called()
        self.assertEqual(result["status"], "HISTORICAL")
        self.assertEqual(result["value"], 19.33)
        self.assertEqual(result["session_date"], "2026-10-19")

    def test_updates_after_close_once_per_day_and_exposes_the_source_date(self):
        now = datetime(2026, 10, 20, 16, 15, tzinfo=IST)
        saved = {"session_date": "2026-10-20", "value": 20.1,
                 "as_of": "20-Oct-2026 15:30", "fetched_at": now.isoformat(),
                 "source": "NSE Indices daily snapshot", "basis": "NSE index P/E"}
        with patch.object(reversal_context, "read_latest_nifty_pe", return_value=(None, "UNAVAILABLE")), \
             patch.object(reversal_context, "_fetch_daily_nifty_pe", return_value=saved) as fetch, \
             patch.object(reversal_context, "save_daily_nifty_pe", return_value="POSTGRESQL_AND_LOCAL"):
            result = reversal_context._nse_index_pe(now)
            again = reversal_context._nse_index_pe(now)
        fetch.assert_called_once()
        self.assertEqual(result["status"], "AVAILABLE")
        self.assertEqual(result["freshness"], "DAILY_EOD")
        self.assertEqual(result["session_date"], "2026-10-20")
        self.assertEqual(again["value"], 20.1)

    def test_refresh_failure_retains_last_daily_value_and_marks_it_historical(self):
        old = {"session_date": "2026-10-19", "value": 19.33,
               "as_of": "19-Oct-2026 15:30", "fetched_at": "2026-10-19T16:00:00+05:30",
               "source": "NSE Indices daily snapshot", "basis": "NSE index P/E"}
        now = datetime(2026, 10, 20, 16, 15, tzinfo=IST)
        with patch.object(reversal_context, "read_latest_nifty_pe", return_value=(old, "POSTGRESQL")), \
             patch.object(reversal_context, "_fetch_daily_nifty_pe", side_effect=TimeoutError), \
             patch.object(reversal_context, "save_daily_nifty_pe") as save:
            result = reversal_context._nse_index_pe(now)
        save.assert_not_called()
        self.assertEqual(result["status"], "HISTORICAL")
        self.assertEqual(result["value"], 19.33)
        self.assertEqual(result["refresh_status"], "FAILED_USING_LAST_STORED")
        self.assertEqual(result["reason"], "TimeoutError")

    def test_sqlite_archive_round_trips_daily_values(self):
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(nifty_pe_archive, "DB_PATH", Path(tmp) / "scanner.db"), \
             patch.dict(os.environ, {"DATABASE_URL": ""}):
            record = {"session_date": "2026-10-19", "value": 19.33,
                      "as_of": "19-Oct-2026 15:30", "fetched_at": "2026-10-19T16:00:00+05:30",
                      "source": "NSE Indices daily snapshot", "basis": "NSE index P/E"}
            storage = nifty_pe_archive.save_daily_nifty_pe(record)
            loaded, source = nifty_pe_archive.read_latest_nifty_pe()
        self.assertEqual(storage, "LOCAL_FALLBACK")
        self.assertEqual(source, "LOCAL_FALLBACK")
        self.assertEqual(loaded["value"], 19.33)
        self.assertEqual(loaded["session_date"], "2026-10-19")


if __name__ == "__main__":
    unittest.main()
