import sys
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from constrox_sdr import compliance


class ContentReadyTests(unittest.TestCase):
    def test_blocks_on_placeholder_marker(self):
        result = compliance.check_content_ready("Hello, [NEEDS REAL DATA - value prop] here.")
        self.assertFalse(result.ok)
        self.assertEqual(result.flag_type, "missing_real_data")

    def test_blocks_on_unresolved_merge_field(self):
        result = compliance.check_content_ready("Hi {{first_name}}, welcome.")
        self.assertFalse(result.ok)
        self.assertEqual(result.flag_type, "unresolved_merge_field")

    def test_passes_clean_text(self):
        result = compliance.check_content_ready("Hi Alex, welcome to the sequence.")
        self.assertTrue(result.ok)


class ClaimCheckTests(unittest.TestCase):
    def test_flags_unapproved_numeric_claim(self):
        facts = {"approved_claims": []}
        result = compliance.check_claims("We cut turnaround time by 40% for clients.", facts)
        self.assertFalse(result.ok)
        self.assertEqual(result.flag_type, "unverified_claim_needs_review")

    def test_allows_claim_present_in_approved_list(self):
        facts = {"approved_claims": ["reduced turnaround time by 40% for clients"]}
        result = compliance.check_claims("We reduced turnaround time by 40% for clients.", facts)
        self.assertTrue(result.ok)

    def test_no_claim_pattern_passes(self):
        facts = {"approved_claims": []}
        result = compliance.check_claims("Would this be useful to discuss?", facts)
        self.assertTrue(result.ok)


class OperatingHoursTests(unittest.TestCase):
    def test_within_window(self):
        now = datetime(2026, 7, 6, 10, 0, tzinfo=ZoneInfo("Europe/London"))  # Monday
        result = compliance.operating_hours_ok("UK", now)
        self.assertTrue(result.ok)

    def test_outside_window_late_evening(self):
        now = datetime(2026, 7, 6, 22, 0, tzinfo=ZoneInfo("Europe/London"))
        result = compliance.operating_hours_ok("UK", now)
        self.assertFalse(result.ok)

    def test_outside_window_weekend(self):
        now = datetime(2026, 7, 11, 10, 0, tzinfo=ZoneInfo("Europe/London"))  # Saturday
        result = compliance.operating_hours_ok("UK", now)
        self.assertFalse(result.ok)


if __name__ == "__main__":
    unittest.main()
