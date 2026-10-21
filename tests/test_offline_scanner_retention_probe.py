"""Ensure offline retention probes respect the current conservative rules."""
import contextlib
import io
import unittest
from scripts.compare_offline_scanner_retention import compare


class OfflineScannerRetentionProbeTests(unittest.TestCase):
    def test_sixty_bar_probe_has_no_marginal_ema_counterexamples(self):
        with contextlib.redirect_stdout(io.StringIO()):
            differences = compare(60, history=400)
        self.assertEqual(differences, [])

    def test_two_hundred_bar_probe_baseline(self):
        with contextlib.redirect_stdout(io.StringIO()):
            differences = compare(200, history=400)
        self.assertEqual(differences, [])

    def test_invalid_probe_configuration_fails_closed(self):
        for cap, history in ((20, 400), (60, 60), (200, 100),
                             (60.0, 400), (60, 400.0), (True, 400),
                             (60, False)):
            with self.subTest(cap=cap, history=history):
                with self.assertRaises(ValueError):
                    compare(cap, history=history)


if __name__ == "__main__":
    unittest.main()
