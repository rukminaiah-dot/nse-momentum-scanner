import unittest
from unittest.mock import patch
from v2.backend.signal_archive_delivery_health import archive_delivery_health

class DeliveryHealthTests(unittest.TestCase):
    def test_not_started_is_not_complete(self):
        with patch("v2.backend.signal_archive_delivery_health.archive_queue_status", return_value={"started": False, "failed": 0, "dropped": 0, "pending": 0}):
            result = archive_delivery_health()
        self.assertEqual(result["status"], "NOT_STARTED")
        self.assertFalse(result["historical_completeness_verified"])

    def test_failure_requires_replay_even_when_queue_empty(self):
        with patch("v2.backend.signal_archive_delivery_health.archive_queue_status", return_value={"started": True, "failed": 1, "dropped": 0, "pending": 0}):
            self.assertEqual(archive_delivery_health()["status"], "REPLAY_REQUIRED")

if __name__ == "__main__":
    unittest.main()
