import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from constrox_sdr.db import get_conn
from constrox_sdr import scoring


class ScoringTests(unittest.TestCase):
    def setUp(self):
        self.db_path = Path(__file__).resolve().parent / "_test_scoring.db"
        if self.db_path.exists():
            self.db_path.unlink()

    def tearDown(self):
        if self.db_path.exists():
            self.db_path.unlink()

    def _insert_company_contact(self, conn, **company_overrides):
        company = {
            "name": "Test Co", "sub_vertical": "Structural Engineering", "company_size": "50",
            "geo_market": "UK", "website": "https://test.example", "intent_signal_1": None,
            "intent_signal_2": None,
        }
        company.update(company_overrides)
        cur = conn.execute(
            "INSERT INTO companies (name, sub_vertical, company_size, geo_market, website, intent_signal_1, intent_signal_2) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            tuple(company.values()),
        )
        company_id = cur.lastrowid
        cur = conn.execute(
            "INSERT INTO contacts (company_id, first_name, last_name) VALUES (?, 'Test', 'Contact')",
            (company_id,),
        )
        return cur.lastrowid

    def test_neutral_fit_score_when_icp_unconfigured(self):
        weights = scoring.load_weights()
        self.assertTrue(weights["icp"]["sub_verticals"][0].startswith("[NEEDS REAL DATA"))
        with get_conn(self.db_path) as conn:
            contact_id = self._insert_company_contact(conn)
            result = scoring.score_contact(conn, contact_id, weights)
        self.assertEqual(result.fit_score, 50.0)

    def test_intent_score_reflects_signal_presence(self):
        weights = scoring.load_weights()
        with get_conn(self.db_path) as conn:
            no_signal = self._insert_company_contact(conn)
            both_signals = self._insert_company_contact(conn, intent_signal_1="hiring", intent_signal_2="funding")
            r_none = scoring.score_contact(conn, no_signal, weights)
            r_both = scoring.score_contact(conn, both_signals, weights)
        self.assertEqual(r_none.intent_score, 0.0)
        self.assertEqual(r_both.intent_score, 100.0)
        self.assertGreater(r_both.total_score, r_none.total_score)

    def test_total_score_is_weighted_combination(self):
        weights = scoring.load_weights()
        with get_conn(self.db_path) as conn:
            contact_id = self._insert_company_contact(conn, intent_signal_1="hiring", intent_signal_2="funding")
            result = scoring.score_contact(conn, contact_id, weights)
        expected = round(weights["fit_weight"] * result.fit_score + weights["intent_weight"] * result.intent_score, 1)
        self.assertEqual(result.total_score, expected)


if __name__ == "__main__":
    unittest.main()
