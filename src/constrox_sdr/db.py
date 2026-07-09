"""Internal CRM data store.

This is a real, functional CRM (SQLite) — not a mock. It is the system of
record until/unless Constrox connects HubSpot/Salesforce/Pipedrive, at which
point an adapter implementing the same write calls used here (see
crm_writeback.py) can be swapped in. Every commission-relevant action is
written here with a timestamp before it is considered "done", per the
Phase 3 guardrail.
"""
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from .paths import DB_PATH


def utcnow_str() -> str:
    """UTC timestamp in the same 'YYYY-MM-DD HH:MM:SS' format SQLite's
    datetime('now') produces, so python-written and SQL-default timestamps
    stay string-comparable (used by date-range filters in reporting.py)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

SCHEMA = """
CREATE TABLE IF NOT EXISTS companies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    sub_vertical TEXT,
    company_size TEXT,
    geo_market TEXT CHECK(geo_market IN ('UK', 'US', 'AU')),
    website TEXT,
    intent_signal_1 TEXT,
    intent_signal_2 TEXT,
    source TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL REFERENCES companies(id),
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    title TEXT,
    email TEXT,
    phone TEXT,
    linkedin_url TEXT,
    do_not_contact INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS lead_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contact_id INTEGER NOT NULL REFERENCES contacts(id),
    fit_score REAL NOT NULL,
    intent_score REAL NOT NULL,
    total_score REAL NOT NULL,
    weights_version TEXT,
    notes TEXT,
    scored_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS deals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contact_id INTEGER NOT NULL REFERENCES contacts(id),
    company_id INTEGER NOT NULL REFERENCES companies(id),
    stage TEXT NOT NULL DEFAULT 'New',
    deal_value REAL,
    commission_rate REAL,
    invoice_status TEXT NOT NULL DEFAULT 'not_invoiced' CHECK(invoice_status IN ('not_invoiced', 'invoiced', 'paid')),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    closed_at TEXT
);

CREATE TABLE IF NOT EXISTS activities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contact_id INTEGER REFERENCES contacts(id),
    deal_id INTEGER REFERENCES deals(id),
    channel TEXT NOT NULL CHECK(channel IN ('email', 'linkedin', 'call', 'system')),
    action TEXT NOT NULL,
    status TEXT NOT NULL,
    requires_human INTEGER NOT NULL DEFAULT 0,
    detail TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS compliance_flags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    related_type TEXT NOT NULL,
    related_id INTEGER,
    flag_type TEXT NOT NULL,
    detail TEXT,
    resolved INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_contacts_company ON contacts(company_id);
CREATE INDEX IF NOT EXISTS idx_deals_contact ON deals(contact_id);
CREATE INDEX IF NOT EXISTS idx_activities_contact ON activities(contact_id);
CREATE INDEX IF NOT EXISTS idx_activities_deal ON activities(deal_id);
"""


def init_db(db_path=DB_PATH):
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


@contextmanager
def get_conn(db_path=DB_PATH):
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()
