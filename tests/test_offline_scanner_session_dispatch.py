"""Offline dispatch contract tests; no scanner import or live side effects."""
import unittest
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from v2.backend.offline_scanner_session_dispatch import dispatch_offline_scanner_tick

DAY = date(2026, 10, 15)
IST = ZoneInfo("Asia/Kolkata")
CALENDAR = {DAY: (time(9, 15), time(15, 30))}
KEYS = frozenset(("STOCK", "INDEX"))


def ms(hour, minute):
    return int(datetime(2026, 10, 15, hour, minute, tzinfo=IST).timestamp() * 1000)


class OfflineScannerDispatchTests(unittest.TestCase):
    def setUp(self):
        self.events = []
        self.state = {"candles": 0, "volume": 0, "health": 0,
                      "trade_updates": 0, "signals": 0, "finalized": 0}

    def update(self):
        for name in ("candles", "volume", "health", "trade_updates", "signals"):
            self.state[name] += 1
        self.events.append("UPDATE")

    def finalize(self):
        self.state["finalized"] += 1
        self.events.append("FINALIZE")

    def dispatch(self, key, stamp, active=None, schedule=CALENDAR, verified=True):
        return dispatch_offline_scanner_tick(
            key, stamp, active, KEYS, schedule, DAY, DAY,
            "Illustrative synthetic calendar", verified,
            on_update=self.update, on_finalize=self.finalize,
        )

    def test_rejections_leave_every_simulated_state_counter_unchanged(self):
        for key, stamp, schedule, verified in (
            ("STOCK", ms(15, 45), CALENDAR, True),
            ("INDEX", ms(15, 45), CALENDAR, True),
            ("STOCK", ms(10, 0), CALENDAR, False),
            ("INDEX", ms(10, 0), {}, True),
            ("UNKNOWN", ms(10, 0), CALENDAR, True),
            ("STOCK", ms(10, 0), {DAY: None}, True),
        ):
            with self.subTest(key=key, stamp=stamp, verified=verified):
                before = dict(self.state)
                self.assertEqual(self.dispatch(key, stamp, schedule=schedule,
                                               verified=verified), "REJECT")
                self.assertEqual(self.state, before)
        self.assertEqual(self.events, [])

    def test_valid_stock_and_index_ticks_dispatch_update_once(self):
        for key in KEYS:
            self.assertEqual(self.dispatch(key, ms(10, 0)), "UPDATE")
        self.assertEqual(self.events, ["UPDATE", "UPDATE"])
        self.assertEqual(self.state["candles"], 2)
        self.assertEqual(self.state["finalized"], 0)

    def test_close_dispatches_finalize_only(self):
        active = datetime(2026, 10, 15, 15, 29)
        self.assertEqual(self.dispatch("STOCK", ms(15, 30), active),
                         "FINALIZE_LAST_MINUTE")
        self.assertEqual(self.state["finalized"], 1)
        self.assertEqual(self.state["candles"], 0)
        self.assertEqual(self.state["volume"], 0)
        self.assertEqual(self.state["signals"], 0)
        self.assertEqual(self.events, ["FINALIZE"])


    def test_explicit_early_close_blocks_after_hours_without_state_changes(self):
        early = {DAY: (time(9, 15), time(13, 0))}
        self.assertEqual(self.dispatch("STOCK", ms(12, 59), schedule=early), "UPDATE")
        before = dict(self.state)
        self.assertEqual(self.dispatch("STOCK", ms(13, 1), schedule=early), "REJECT")
        self.assertEqual(self.state, before)

    def test_expired_calendar_rejects_next_day(self):
        next_day = int(datetime(2026, 10, 16, 10, 0, tzinfo=IST).timestamp() * 1000)
        before = dict(self.state)
        self.assertEqual(self.dispatch("INDEX", next_day), "REJECT")
        self.assertEqual(self.state, before)

    def test_close_grace_expiry_does_not_finalize_or_update(self):
        active = datetime(2026, 10, 15, 15, 29)
        before = dict(self.state)
        self.assertEqual(self.dispatch("STOCK", ms(15, 36), active), "REJECT")
        self.assertEqual(self.state, before)

if __name__ == "__main__":
    unittest.main()
