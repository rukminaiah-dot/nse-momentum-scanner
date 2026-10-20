import csv
import tempfile
import unittest
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

from scripts.audit_long_horizon_history import audit


HEADERS = [
    "session_date", "cutoff_at", "close", "close_available_at", "source",
    "volume_proxy", "volume_proxy_name", "volume_available_at", "volume_source",
    "india_vix", "vix_available_at", "vix_source", "fii_net", "dii_net",
    "flows_available_at", "flows_source", "nifty_pe", "pe_basis",
    "pe_available_at", "pe_source", "news_count", "news_available_at", "news_source",
]


class LongHorizonAuditTests(unittest.TestCase):
    def write_panel(self, directory: str, *, late_vix: bool = False) -> Path:
        path = Path(directory) / "panel.csv"
        current = date(2025, 1, 1)
        days = []
        while len(days) < 230:
            if current.weekday() < 5:
                days.append(current)
            current += timedelta(days=1)
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=HEADERS)
            writer.writeheader()
            for index, day in enumerate(days):
                cutoff = datetime.combine(day, time(16, 5), timezone(timedelta(hours=5, minutes=30)))
                ordinary = (cutoff - timedelta(minutes=1)).isoformat()
                writer.writerow({
                    "session_date": day.isoformat(), "cutoff_at": cutoff.isoformat(),
                    "close": 20000 + index * 2, "close_available_at": ordinary,
                    "source": "NSE historical index data",
                    "volume_proxy": 1000000, "volume_proxy_name": "NIFTY futures volume",
                    "volume_available_at": ordinary, "volume_source": "NSE derivatives bhavcopy",
                    "india_vix": 14, "vix_available_at": (cutoff + timedelta(minutes=1)).isoformat() if late_vix and index == 0 else ordinary,
                    "vix_source": "NSE India VIX historical data",
                    "fii_net": -100, "dii_net": 150, "flows_available_at": ordinary,
                    "flows_source": "NSE FII/DII report",
                    "nifty_pe": 22, "pe_basis": "consistent basis", "pe_available_at": ordinary,
                    "pe_source": "Nifty Indices historical valuation",
                    "news_count": 0, "news_available_at": ordinary, "news_source": "timestamped RSS archive",
                })
        return path

    def test_reports_timestamped_coverage_and_never_returns_forecast_probabilities(self):
        with tempfile.TemporaryDirectory() as directory:
            report = audit(self.write_panel(directory))
        self.assertEqual(report["report_status"], "AUDIT_ONLY_NO_FORECAST")
        self.assertIsNone(report["forecast_probabilities"])
        self.assertEqual(report["model_status"], "NOT_RUN_NO_POINT_IN_TIME_MODEL_FEATURES_OR_VALIDATION")
        self.assertEqual(report["factor_coverage_by_cutoff"]["india_vix"]["available_by_cutoff"], 230)
        self.assertGreater(report["labels"]["total"], 0)
        self.assertEqual(report["close_coverage"]["complete_usable_series"], True)

    def test_rejects_a_quote_that_was_not_yet_available_at_the_cutoff(self):
        with tempfile.TemporaryDirectory() as directory:
            report = audit(self.write_panel(directory, late_vix=True))
        self.assertEqual(report["factor_coverage_by_cutoff"]["india_vix"]["available_by_cutoff"], 229)
        self.assertEqual(report["factor_coverage_by_cutoff"]["india_vix"]["missing_or_late"], 1)

    def test_rejects_timezone_naive_timestamps(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_panel(directory)
            with path.open(encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            rows[0]["cutoff_at"] = "2025-01-01T16:05:00"
            with path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=HEADERS)
                writer.writeheader()
                writer.writerows(rows)
            report = audit(path)
        self.assertFalse(report["close_coverage"]["complete_usable_series"])
        self.assertEqual(report["labels"]["total"], 0)
        self.assertEqual(report["close_coverage"]["rejected_rows_by_reason"]["missing_or_timezone_naive_cutoff"], 1)


if __name__ == "__main__":
    unittest.main()
