"""Synthetic offline tests; never imports scanner or Upstox clients."""
import unittest
import ast
from pathlib import Path
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from v2.backend.offline_scanner_session_policy import classify_scanner_tick

IST = ZoneInfo("Asia/Kolkata")
DAY = date(2026, 10, 15)
CALENDAR = {DAY: (time(9, 15), time(15, 30))}
KEYS = frozenset(("STOCK_TEST", "INDEX_TEST"))


def ms(hour, minute):
    return int(datetime(2026, 10, 15, hour, minute, tzinfo=IST).timestamp() * 1000)


def decide(key, stamp, active=None, schedule=CALENDAR, verified=True):
    return classify_scanner_tick(
        key, stamp, active, KEYS, schedule, DAY, DAY,
        "Illustrative, not verified NSE evidence", verified,
    )


class OfflineScannerSessionPolicyTests(unittest.TestCase):
    def test_stock_and_index_use_same_verified_window(self):
        for key in KEYS:
            with self.subTest(key=key):
                self.assertEqual(decide(key, ms(9, 15)), "UPDATE")
                self.assertEqual(decide(key, ms(15, 29)), "UPDATE")
                self.assertEqual(decide(key, ms(15, 30)), "REJECT")

    def test_unverified_missing_or_unknown_instrument_fail_closed(self):
        for key in KEYS:
            self.assertEqual(decide(key, ms(10, 0), verified=False), "REJECT")
            self.assertEqual(decide(key, ms(10, 0), schedule={}), "REJECT")
        self.assertEqual(decide("UNKNOWN", ms(10, 0)), "REJECT")

    def test_finalization_only_for_existing_final_minute(self):
        active = datetime(2026, 10, 15, 15, 29)
        for key in KEYS:
            self.assertEqual(decide(key, ms(15, 30), active), "FINALIZE_LAST_MINUTE")
            self.assertEqual(decide(key, ms(15, 36), active), "REJECT")
            self.assertEqual(decide(key, ms(15, 30),
                                    datetime(2026, 10, 15, 15, 28)), "REJECT")

    def test_explicit_closed_date_rejects_all(self):
        self.assertEqual(decide("STOCK_TEST", ms(10, 0), schedule={DAY: None}), "REJECT")


    def test_malformed_instrument_allowlists_fail_closed(self):
        for eligible in ("STOCK_TEST,INDEX_TEST", None, {"STOCK_TEST": True}, 12):
            with self.subTest(eligible=eligible):
                self.assertEqual(classify_scanner_tick(
                    "STOCK_TEST", ms(10, 0), None, eligible, CALENDAR,
                    DAY, DAY, "Synthetic calendar", True), "REJECT")

    def test_calendar_entrypoint_exists_but_live_feed_stays_on_legacy_path(self):
        root = Path(__file__).resolve().parents[1]
        scanner = ast.parse((root / "v2/backend/scanner.py").read_text())
        functions = {n.name: n for n in scanner.body
                     if isinstance(n, ast.FunctionDef)}
        self.assertIn("on_tick_with_verified_calendar", functions)
        live_tick = ast.unparse(functions["on_tick"])
        self.assertNotIn("dispatch_offline_scanner_tick", live_tick)
        self.assertNotIn("on_tick_with_verified_calendar", live_tick)
        entry = ast.unparse(functions["on_tick_with_verified_calendar"])
        self.assertIn("dispatch_offline_scanner_tick", entry)
        main = next(n for n in scanner.body if isinstance(n, ast.If)
                    and "__main__" in ast.unparse(n.test))
        self.assertIn("UpstoxLiveV3(on_tick=on_tick)", ast.unparse(main))
        self.assertNotIn("on_tick_with_verified_calendar", ast.unparse(main))


if __name__ == "__main__":
    unittest.main()
