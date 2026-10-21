"""Conservative signal filter checks; thresholds are not profitability claims."""
import unittest

from v2.backend.signal_engine import generate_signal


class SignalEngineTests(unittest.TestCase):
    def test_stock_requires_observed_relative_volume(self):
        self.assertEqual(
            generate_signal(100, 100.2, 100.0, None, 0.2, None,
                            require_volume=True),
            "HOLD",
        )

    def test_stock_requires_volume_above_average_buffer(self):
        self.assertEqual(
            generate_signal(100, 100.2, 100.0, None, 0.2, 1.0,
                            require_volume=True),
            "HOLD",
        )
        self.assertEqual(
            generate_signal(100, 100.2, 100.0, None, 0.2, 1.19,
                            require_volume=True),
            "HOLD",
        )

    def test_stock_buy_needs_spread_trend_and_elevated_volume(self):
        self.assertEqual(
            generate_signal(100, 100.2, 100.0, None, 0.2, 1.2,
                            require_volume=True),
            "BUY",
        )

    def test_marginal_ema_cross_is_filtered(self):
        self.assertEqual(
            generate_signal(100, 100.03, 100.0, None, 0.2, 1.8,
                            require_volume=True),
            "HOLD",
        )

    def test_index_can_use_price_confirmation_without_traded_volume(self):
        self.assertEqual(
            generate_signal(100, 100.2, 100.0, None, 0.2, None),
            "BUY",
        )

    def test_opposite_alignment_does_not_pass_from_volume_alone(self):
        self.assertEqual(
            generate_signal(100, 100.0, 100.2, None, 0.2, 1.8,
                            require_volume=True),
            "HOLD",
        )


if __name__ == "__main__":
    unittest.main()
