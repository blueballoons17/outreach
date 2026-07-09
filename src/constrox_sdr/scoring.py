"""Lead scoring: transparent, adjustable fit + intent score.

Every weight lives in config/scoring_weights.json — nothing here is
hardcoded, so Constrox can retune targeting without a code change.

Until config/scoring_weights.json's icp.sub_verticals is filled in with
real data, fit-matching runs in "neutral mode": every company gets a
component score of 50/100 for sub_vertical/size/geo match (rather than a
fabricated confident score), and a warning is recorded so it's obvious in
reporting that scores aren't meaningful yet.
"""
import json
from dataclasses import dataclass

from .paths import SCORING_WEIGHTS_PATH

PLACEHOLDER_MARKER = "[NEEDS REAL DATA"


def load_weights():
    with open(SCORING_WEIGHTS_PATH) as f:
        return json.load(f)


def _icp_configured(icp: dict) -> bool:
    sub_verticals = icp.get("sub_verticals") or []
    if not sub_verticals:
        return False
    return not any(str(v).startswith(PLACEHOLDER_MARKER) for v in sub_verticals)


@dataclass
class ScoreResult:
    fit_score: float
    intent_score: float
    total_score: float
    notes: str


def score_company_fit(company_row, weights) -> tuple[float, str]:
    icp = weights.get("icp", {})
    components = weights["fit_components"]

    if not _icp_configured(icp):
        return 50.0, "ICP not configured (scoring_weights.json icp.sub_verticals is a placeholder) — neutral fit score."

    max_points = sum(components.values())
    points = 0.0
    notes = []

    sub_verticals = {v.lower() for v in icp.get("sub_verticals", [])}
    if company_row["sub_vertical"] and company_row["sub_vertical"].lower() in sub_verticals:
        points += components["sub_vertical_match"]
    else:
        notes.append("sub_vertical did not match ICP")

    size_min = icp.get("company_size_min_employees")
    size_max = icp.get("company_size_max_employees")
    company_size = company_row["company_size"]
    if size_min is not None and size_max is not None and company_size:
        try:
            size_val = int("".join(ch for ch in company_size if ch.isdigit()) or 0)
            if size_min <= size_val <= size_max:
                points += components["company_size_match"]
            else:
                notes.append("company_size outside ICP band")
        except ValueError:
            notes.append("company_size unparseable")
    else:
        notes.append("company_size_match skipped (ICP band or company_size not set)")

    geo_target = icp.get("geo_split_target_pct", {})
    geo = company_row["geo_market"]
    if geo and geo_target.get(geo) and not str(geo_target[geo]).startswith(PLACEHOLDER_MARKER):
        points += components["geo_market_match"]
    else:
        notes.append("geo_market_match skipped (geo_split_target_pct not set for this market)")

    fit_score = round((points / max_points) * 100, 1) if max_points else 50.0
    return fit_score, "; ".join(notes) if notes else "full ICP match"


def score_company_intent(company_row, weights) -> tuple[float, str]:
    components = weights["intent_components"]
    max_points = sum(components.values())
    points = 0.0
    notes = []

    if company_row["intent_signal_1"]:
        points += components["recent_hiring_signal"]
    else:
        notes.append("no recent_hiring_signal on file")

    if company_row["intent_signal_2"]:
        points += components["expansion_or_funding_signal"]
    else:
        notes.append("no expansion_or_funding_signal on file")

    intent_score = round((points / max_points) * 100, 1) if max_points else 0.0
    return intent_score, "; ".join(notes) if notes else "both intent signals present"


def score_contact(conn, contact_id, weights=None) -> ScoreResult:
    weights = weights or load_weights()
    contact = conn.execute("SELECT * FROM contacts WHERE id = ?", (contact_id,)).fetchone()
    if not contact:
        raise ValueError(f"contact {contact_id} not found")
    company = conn.execute("SELECT * FROM companies WHERE id = ?", (contact["company_id"],)).fetchone()

    fit_score, fit_notes = score_company_fit(company, weights)
    intent_score, intent_notes = score_company_intent(company, weights)
    total = round(weights["fit_weight"] * fit_score + weights["intent_weight"] * intent_score, 1)

    return ScoreResult(
        fit_score=fit_score,
        intent_score=intent_score,
        total_score=total,
        notes=f"fit: {fit_notes} | intent: {intent_notes}",
    )


def score_all_contacts(conn, weights=None, weights_version="v1"):
    weights = weights or load_weights()
    contacts = conn.execute("SELECT id FROM contacts").fetchall()
    results = []
    for c in contacts:
        result = score_contact(conn, c["id"], weights)
        conn.execute(
            """INSERT INTO lead_scores (contact_id, fit_score, intent_score, total_score, weights_version, notes)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (c["id"], result.fit_score, result.intent_score, result.total_score, weights_version, result.notes),
        )
        results.append((c["id"], result))
    return results


def ranked_leads(conn):
    """Latest score per contact, joined with contact/company info, ranked desc."""
    return conn.execute(
        """
        SELECT c.id AS contact_id, c.first_name, c.last_name, c.title, c.email, c.phone, c.linkedin_url,
               co.name AS company_name, co.sub_vertical, co.geo_market,
               ls.fit_score, ls.intent_score, ls.total_score, ls.notes, ls.scored_at
        FROM contacts c
        JOIN companies co ON co.id = c.company_id
        JOIN lead_scores ls ON ls.contact_id = c.id
        WHERE ls.id IN (
            SELECT MAX(id) FROM lead_scores GROUP BY contact_id
        )
        ORDER BY ls.total_score DESC
        """
    ).fetchall()
