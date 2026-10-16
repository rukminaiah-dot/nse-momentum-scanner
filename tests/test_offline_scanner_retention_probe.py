"""Ensure the offline retention comparison exercises its negative controls."""
import contextlib
import io
import unittest
from scripts.compare_offline_scanner_retention import compare


class OfflineScannerRetentionProbeTests(unittest.TestCase):
    def test_sixty_bar_negative_controls_remain_visible(self):
        with contextlib.redirect_stdout(io.StringIO()):
            differences = compare(60, history=400)
        self.assertEqual(set(differences), {
            ("high_seed_tiny_uptrend", "primary_index", 400, "HOLD", "BUY"),
            ("high_seed_tiny_uptrend", "secondary_index", 400, "HOLD", "BUY"),
            ("low_seed_tiny_downtrend", "primary_index", 400, "HOLD", "SELL"),
            ("low_seed_tiny_downtrend", "secondary_index", 400, "HOLD", "SELL"),
        })

    def test_two_hundred_bar_probe_baseline(self):
        with contextlib.redirect_stdout(io.StringIO()):
            differences = compare(200, history=400)
        self.assertEqual(differences, [])


if __name__ == "__main__":
    unittest.main()
