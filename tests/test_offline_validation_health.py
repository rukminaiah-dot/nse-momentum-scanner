"""Health endpoint must never serve repository contents or start broker modules."""
import io
import unittest
from unittest.mock import patch
from v2.backend.offline_validation_health import HealthHandler, main


class OfflineHealthTests(unittest.TestCase):
    def test_handler_is_only_health_route(self):
        self.assertNotIn("SimpleHTTPRequestHandler", HealthHandler.__mro__[1].__name__)
        self.assertEqual(HealthHandler.__bases__[0].__name__, "BaseHTTPRequestHandler")

    def test_requires_recovery_explicitly_disabled(self):
        with patch.dict("os.environ", {"NSE_RECOVERY_MODE": "staging",
                                       "NSE_ENABLE_VERIFIED_GAP_RECOVERY": "1"}):
            with self.assertRaises(SystemExit):
                main()


if __name__ == "__main__":
    unittest.main()
