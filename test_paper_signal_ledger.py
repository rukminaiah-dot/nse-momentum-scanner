import unittest
from datetime import datetime, timedelta
from v2.backend.paper_signal_ledger import PaperLedger, Signal

T = datetime(2026, 10, 14, 10, 0)

def s(instrument, kind, side, price, minute):
    return Signal(instrument, kind, side, price, T + timedelta(minutes=minute))

class PaperLedgerTests(unittest.TestCase):
    def test_stock_profit_and_index_loss(self):
        l = PaperLedger()
        l.record(s("RELIANCE", "stock", "BUY", 100, 0))
        l.record(s("NIFTY 50", "index", "BUY", 25000, 0))
        a = l.record(s("RELIANCE", "stock", "SELL", 110, 5))
        b = l.record(s("NIFTY 50", "index", "SELL", 24900, 6))
        self.assertEqual((a.points, a.return_pct), (10, 10))
        self.assertEqual((b.points, b.return_pct), (-100, -0.4))
        self.assertEqual(l.summary("stock")["wins"], 1)
        self.assertEqual(l.summary("index")["losses"], 1)

    def test_duplicate_and_unmatched_not_counted(self):
        l = PaperLedger()
        l.record(s("A", "stock", "SELL", 101, 0))
        l.record(s("A", "stock", "BUY", 100, 1))
        l.record(s("A", "stock", "BUY", 110, 2))
        self.assertEqual(len(l.rejected), 2)
        self.assertEqual(l.summary()["open_calls"], 1)
        self.assertEqual(l.summary()["closed_calls"], 0)
        l.record(s("A", "stock", "SELL", 100, 3))
        self.assertEqual(l.summary()["flat"], 1)

    def test_boolean_price_is_rejected_without_recording_a_signal(self):
        ledger = PaperLedger()
        for price in (True, False):
            with self.subTest(price=price):
                with self.assertRaises(ValueError):
                    ledger.record(s("A", "stock", "BUY", price, 0))
        self.assertEqual(ledger.events, [])
        self.assertEqual(ledger.summary()["open_calls"], 0)

    def test_invalid_price_and_timestamp_order(self):
        l = PaperLedger()
        with self.assertRaises(ValueError):
            l.record(s("A", "stock", "BUY", float("nan"), 0))
        l.record(s("A", "stock", "BUY", 100, 5))
        self.assertIsNone(l.record(s("A", "stock", "SELL", 101, 4)))
        self.assertEqual(l.summary()["open_calls"], 1)

if __name__ == "__main__":
    unittest.main()
