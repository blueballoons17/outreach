"""Weekly pipeline report, stale-deal alerting, and daily summary — the
"what got sent, what needs a human, what closed/stalled" surface required
by Phase 3.

Commission accrual only ever counts invoice_status = 'paid' deals, per the
instruction that commission is released on paid invoices, not closed-won
alone.
"""
import json
from datetime import datetime, timedelta, timezone

from .paths import PIPELINE_SETTINGS_PATH, REPORTS_DIR

# Match SQLite's datetime('now') format ('YYYY-MM-DD HH:MM:SS') so
# string-range comparisons against created_at/closed_at columns are valid
# regardless of whether a given row's timestamp was set by SQL or by
# db.utcnow_str() in Python.
_TS_FMT = "%Y-%m-%d %H:%M:%S"

OPEN_STAGES_ORDER = [
    "New", "Contacted", "Replied", "Discovery Scheduled",
    "Discovery Completed", "Proposal Sent", "Closed Won", "Closed Lost",
]


def load_settings():
    with open(PIPELINE_SETTINGS_PATH) as f:
        return json.load(f)


def pipeline_value_by_stage(conn):
    rows = conn.execute(
        "SELECT stage, COUNT(*) AS n, COALESCE(SUM(deal_value), 0) AS value FROM deals GROUP BY stage"
    ).fetchall()
    return {r["stage"]: {"count": r["n"], "value": r["value"]} for r in rows}


def stage_conversion(conn):
    """% of all deals that have ever reached each stage or later, using
    stage order as a proxy funnel (a deal 'reached' a stage if its current
    stage index >= that stage's index, or it's Closed Won past any stage)."""
    total = conn.execute("SELECT COUNT(*) AS n FROM deals").fetchone()["n"]
    if total == 0:
        return {}
    rows = conn.execute("SELECT stage FROM deals").fetchall()
    stage_index = {s: i for i, s in enumerate(OPEN_STAGES_ORDER)}
    conversion = {}
    for stage in OPEN_STAGES_ORDER:
        idx = stage_index[stage]
        reached = sum(
            1 for r in rows
            if r["stage"] == "Closed Won" or (r["stage"] in stage_index and stage_index[r["stage"]] >= idx)
        )
        conversion[stage] = round(100 * reached / total, 1)
    return conversion


def revenue_and_commission(conn, default_commission_rate):
    row = conn.execute(
        """SELECT COALESCE(SUM(deal_value), 0) AS revenue,
                  COALESCE(SUM(deal_value * COALESCE(commission_rate, ?)), 0) AS commission
           FROM deals WHERE invoice_status = 'paid'""",
        (default_commission_rate,),
    ).fetchone()
    return row["revenue"], row["commission"]


def open_pipeline_value(conn):
    row = conn.execute(
        "SELECT COALESCE(SUM(deal_value), 0) AS v FROM deals WHERE stage NOT IN ('Closed Won', 'Closed Lost')"
    ).fetchone()
    return row["v"]


def coverage_check(conn, settings):
    open_value = open_pipeline_value(conn)
    target = settings["target_monthly_revenue_usd"] * settings["pipeline_coverage_multiplier"]
    return {
        "open_pipeline_value": open_value,
        "required_for_3x_coverage": target,
        "coverage_met": open_value >= target,
        "shortfall": max(0, target - open_value),
    }


def stale_deals(conn, days=None):
    settings = load_settings()
    days = days if days is not None else settings["stale_deal_days"]
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime(_TS_FMT)

    deals = conn.execute(
        "SELECT * FROM deals WHERE stage NOT IN ('Closed Won', 'Closed Lost')"
    ).fetchall()
    stale = []
    for d in deals:
        last_activity = conn.execute(
            "SELECT MAX(created_at) AS last FROM activities WHERE deal_id = ?", (d["id"],)
        ).fetchone()["last"]
        reference = last_activity or d["created_at"]
        if reference < cutoff:
            stale.append({**dict(d), "last_activity_at": last_activity})
    return stale


def write_weekly_report(conn, out_path=None):
    settings = load_settings()
    out_path = out_path or REPORTS_DIR / f"weekly_report_{datetime.now(timezone.utc):%Y%m%d}.md"

    by_stage = pipeline_value_by_stage(conn)
    conversion = stage_conversion(conn)
    revenue, commission = revenue_and_commission(conn, settings["default_commission_rate"])
    coverage = coverage_check(conn, settings)
    stale = stale_deals(conn, settings["stale_deal_days"])

    lines = [
        f"# Weekly Pipeline Report — {datetime.now(timezone.utc):%Y-%m-%d}",
        "",
        "## Pipeline value by stage",
        "| Stage | Deals | Value |",
        "|---|---|---|",
    ]
    for stage in OPEN_STAGES_ORDER:
        s = by_stage.get(stage, {"count": 0, "value": 0})
        lines.append(f"| {stage} | {s['count']} | ${s['value']:,.0f} |")

    lines += ["", "## Stage-by-stage conversion (% of all deals that reached this stage)"]
    for stage in OPEN_STAGES_ORDER:
        lines.append(f"- {stage}: {conversion.get(stage, 0)}%")

    lines += [
        "",
        "## Revenue & commission (paid invoices only)",
        f"- Revenue recognized (paid): ${revenue:,.0f}",
        f"- Commission accrued (paid, at deal-specific or default {settings['default_commission_rate']*100:.0f}% rate): ${commission:,.0f}",
        "",
        "## 3x pipeline coverage check",
        f"- Open pipeline value: ${coverage['open_pipeline_value']:,.0f}",
        f"- Required for {settings['pipeline_coverage_multiplier']}x monthly target (${settings['target_monthly_revenue_usd']:,.0f}): ${coverage['required_for_3x_coverage']:,.0f}",
        f"- Coverage met: {'YES' if coverage['coverage_met'] else 'NO'}"
        + ("" if coverage["coverage_met"] else f" (shortfall ${coverage['shortfall']:,.0f})"),
        "",
        f"## Stale deals (no activity in {settings['stale_deal_days']}+ days)",
    ]
    if stale:
        for d in stale:
            lines.append(f"- deal {d['id']} (contact {d['contact_id']}, stage {d['stage']}) — last activity: {d['last_activity_at'] or 'never'}")
    else:
        lines.append("- none")

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out_path


def daily_summary(conn, date=None):
    date = date or datetime.now(timezone.utc).date()
    day_start = f"{date} 00:00:00"
    day_end = f"{date} 23:59:59"

    sent = conn.execute(
        """SELECT channel, action, status, COUNT(*) AS n FROM activities
           WHERE created_at BETWEEN ? AND ? AND requires_human = 0
           GROUP BY channel, action, status""",
        (day_start, day_end),
    ).fetchall()

    needs_human = conn.execute(
        """SELECT channel, action, COUNT(*) AS n FROM activities
           WHERE created_at BETWEEN ? AND ? AND requires_human = 1
           GROUP BY channel, action""",
        (day_start, day_end),
    ).fetchall()

    closed = conn.execute(
        """SELECT id, contact_id, stage FROM deals
           WHERE closed_at BETWEEN ? AND ?""",
        (day_start, day_end),
    ).fetchall()

    blocked = conn.execute(
        """SELECT contact_id, detail FROM activities
           WHERE created_at BETWEEN ? AND ? AND action = 'compliance_blocked'""",
        (day_start, day_end),
    ).fetchall()

    lines = [f"Daily summary for {date}", ""]
    lines.append("Sent/automated:")
    lines += [f"  - {r['channel']}/{r['action']}: {r['n']} ({r['status']})" for r in sent] or ["  - none"]
    lines.append("Needs human action:")
    lines += [f"  - {r['channel']}/{r['action']}: {r['n']}" for r in needs_human] or ["  - none"]
    lines.append("Closed today:")
    lines += [f"  - deal {r['id']} (contact {r['contact_id']}): {r['stage']}" for r in closed] or ["  - none"]
    lines.append("Compliance-blocked (needs review):")
    lines += [f"  - contact {r['contact_id']}: {r['detail']}" for r in blocked] or ["  - none"]

    return "\n".join(lines)
