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


if __name__ == "__main__":
    unittest.main()
