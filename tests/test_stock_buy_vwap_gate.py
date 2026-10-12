"""Regression checks for the stock BUY VWAP/volume safety gate."""
import unittest

from v2.backend.signal_engine import generate_signal


class StockBuyValidationTests(unittest.TestCase):
    def test_missing_vwap_never_qualifies_buy(self):
        self.assertNotEqual(generate_signal(105, 103, 101, None, 0.5, 2.0, "BULLISH"), "BUY")

    def test_missing_rvol_never_qualifies_buy(self):
        self.assertNotEqual(generate_signal(105, 103, 101, 102, 0.5, None, "BULLISH"), "BUY")

    def test_below_vwap_never_qualifies_buy(self):
        self.assertNotEqual(generate_signal(105, 103, 101, 106, 0.5, 2.0, "BULLISH"), "BUY")

    def test_valid_stock_conditions_qualify(self):
        self.assertEqual(generate_signal(105, 103, 101, 102, 0.5, 2.0, "BEARISH"), "BUY")

    def test_low_rvol_never_qualifies_buy(self):
        self.assertNotEqual(generate_signal(105, 103, 101, 102, 0.5, 0.9, "BULLISH"), "BUY")


if __name__ == "__main__":
    unittest.main()
