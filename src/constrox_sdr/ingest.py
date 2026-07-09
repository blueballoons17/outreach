"""Ingest a prospect list (CSV export from CRM, Apollo/Clay/similar, or manual)
into the internal CRM.

Expected CSV columns (extra columns are ignored, missing optional columns
are fine):

    company_name, sub_vertical, company_size, geo_market, website,
    first_name, last_name, title, email, phone, linkedin_url, source,
    intent_signal_1, intent_signal_2

geo_market must be one of UK / US / AU.
"""
import csv
import sqlite3
from dataclasses import dataclass

REQUIRED_COLUMNS = {"company_name", "first_name", "last_name", "geo_market"}


@dataclass
class IngestResult:
    companies_created: int = 0
    companies_reused: int = 0
    contacts_created: int = 0
    rows_skipped: int = 0
    errors: list = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []


def _get_or_create_company(conn, row) -> int:
    existing = conn.execute(
        "SELECT id FROM companies WHERE name = ? AND geo_market = ?",
        (row["company_name"], row["geo_market"]),
    ).fetchone()
    if existing:
        return existing["id"], False

    cur = conn.execute(
        """INSERT INTO companies
           (name, sub_vertical, company_size, geo_market, website, intent_signal_1, intent_signal_2, source)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            row["company_name"],
            row.get("sub_vertical") or None,
            row.get("company_size") or None,
            row["geo_market"],
            row.get("website") or None,
            row.get("intent_signal_1") or None,
            row.get("intent_signal_2") or None,
            row.get("source") or "csv_import",
        ),
    )
    return cur.lastrowid, True


def ingest_csv(conn, csv_path) -> IngestResult:
    result = IngestResult()
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"CSV missing required columns: {sorted(missing)}")

        for i, row in enumerate(reader, start=2):  # header is row 1
            row = {k: (v or "").strip() for k, v in row.items()}
            if not row.get("company_name") or not row.get("first_name"):
                result.rows_skipped += 1
                result.errors.append(f"row {i}: missing company_name or first_name")
                continue
            if row["geo_market"] not in ("UK", "US", "AU"):
                result.rows_skipped += 1
                result.errors.append(f"row {i}: geo_market '{row['geo_market']}' not in UK/US/AU")
                continue

            company_id, created = _get_or_create_company(conn, row)
            if created:
                result.companies_created += 1
            else:
                result.companies_reused += 1

            existing_contact = None
            if row.get("email"):
                existing_contact = conn.execute(
                    "SELECT id FROM contacts WHERE email = ?", (row["email"],)
                ).fetchone()
            if existing_contact:
                continue

            conn.execute(
                """INSERT INTO contacts
                   (company_id, first_name, last_name, title, email, phone, linkedin_url)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    company_id,
                    row["first_name"],
                    row["last_name"],
                    row.get("title") or None,
                    row.get("email") or None,
                    row.get("phone") or None,
                    row.get("linkedin_url") or None,
                ),
            )
            result.contacts_created += 1

    return result
