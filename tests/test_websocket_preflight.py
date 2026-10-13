"""Offline tests: live-websocket preflight fails closed."""
import unittest

from preflight_upstox_websocket import check


BASE = {
    "FIX10_NONPRODUCTION_ACK": "I_AM_IN_AN_ISOLATED_TEST",
    "UPSTOX_ACCESS_TOKEN": "fake-value-never-used",
    "FIX10_TEST_INSTRUMENT_KEY": "TEST_INSTRUMENT",
}


class PreflightTests(unittest.TestCase):
    def test_valid_isolated_configuration(self):
        self.assertEqual(check(BASE), [])

    def test_missing_acknowledgement_blocks(self):
        self.assertTrue(check({k: v for k, v in BASE.items() if k != "FIX10_NONPRODUCTION_ACK"}))

    def test_wrong_acknowledgement_blocks(self):
        self.assertTrue(check({**BASE, "FIX10_NONPRODUCTION_ACK": "yes"}))

    def test_missing_token_blocks(self):
        self.assertTrue(check({**BASE, "UPSTOX_ACCESS_TOKEN": ""}))

    def test_missing_instrument_blocks(self):
        self.assertTrue(check({**BASE, "FIX10_TEST_INSTRUMENT_KEY": ""}))

    def test_enabled_recovery_flag_blocks(self):
        for value in ("ON", "true", "1", "yes"):
            with self.subTest(value=value):
                self.assertTrue(check({**BASE, "ENABLE_VERIFIED_GAP_RECOVERY": value}))


if __name__ == "__main__":
    unittest.main()
