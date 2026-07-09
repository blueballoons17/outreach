"""Every touch — sent, opened, replied, queued-for-human, call outcome —
gets written here with a timestamp before it's considered done. This is
the log the weekly report and commission accounting read from.

log_activity() writes to the internal SQLite CRM (real, functional today).
External CRM adapters (HubSpot/Salesforce/Pipedrive) are stubbed below:
implement push_to_external_crm() for the confirmed system once API
credentials exist, and call it alongside log_activity() so the internal DB
stays the audit trail even after an external CRM is wired in.
"""
from .db import utcnow_str


def log_activity(conn, contact_id, channel, action, status, requires_human=False, detail="", deal_id=None):
    conn.execute(
        """INSERT INTO activities (contact_id, deal_id, channel, action, status, requires_human, detail, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (contact_id, deal_id, channel, action, status, int(requires_human), detail, utcnow_str()),
    )


def log_compliance_flag(conn, related_type, related_id, flag_type, detail):
    conn.execute(
        """INSERT INTO compliance_flags (related_type, related_id, flag_type, detail)
           VALUES (?, ?, ?, ?)""",
        (related_type, related_id, flag_type, detail),
    )


def get_or_create_deal(conn, contact_id, company_id, commission_rate=None):
    existing = conn.execute(
        "SELECT * FROM deals WHERE contact_id = ? AND stage NOT IN ('Closed Won', 'Closed Lost')",
        (contact_id,),
    ).fetchone()
    if existing:
        return existing["id"]
    cur = conn.execute(
        "INSERT INTO deals (contact_id, company_id, stage, commission_rate) VALUES (?, ?, 'New', ?)",
        (contact_id, company_id, commission_rate),
    )
    return cur.lastrowid


def update_deal_stage(conn, deal_id, stage, deal_value=None, invoice_status=None):
    fields = ["stage = ?", "updated_at = ?"]
    params = [stage, utcnow_str()]
    if deal_value is not None:
        fields.append("deal_value = ?")
        params.append(deal_value)
    if invoice_status is not None:
        fields.append("invoice_status = ?")
        params.append(invoice_status)
    if stage in ("Closed Won", "Closed Lost"):
        fields.append("closed_at = ?")
        params.append(utcnow_str())
    params.append(deal_id)
    conn.execute(f"UPDATE deals SET {', '.join(fields)} WHERE id = ?", params)


def push_to_external_crm(*args, **kwargs):
    """TODO: implement once Constrox confirms an external CRM + API
    credentials (HubSpot private app token / Salesforce connected app /
    Pipedrive API token). Until then, the internal SQLite CRM in db.py is
    the system of record and this function intentionally does nothing."""
    raise NotImplementedError(
        "No external CRM configured. Internal CRM (data/crm.db) is source of truth. "
        "Implement this against the confirmed CRM's API once credentials are available."
    )
