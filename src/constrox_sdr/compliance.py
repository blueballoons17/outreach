"""Phase 3 guardrails, enforced in code rather than left as policy text.

Every one of these is a hard gate the orchestrator calls before queueing an
outreach action. A failed gate does not silently drop the action — it
writes a compliance_flags row and an activity row so it shows up in the
daily summary for a human to resolve.
"""
import csv
import json
import re
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from .paths import OPERATING_HOURS_PATH, DNC_LIST_PATH

PLACEHOLDER_MARKER = "[NEEDS REAL DATA"
UNRESOLVED_FIELD_RE = re.compile(r"\{\{\w+\}\}")

_DAY_ABBR = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


@dataclass
class ComplianceResult:
    ok: bool
    flag_type: str = ""
    detail: str = ""


def load_operating_hours():
    with open(OPERATING_HOURS_PATH) as f:
        return json.load(f)


def operating_hours_ok(market: str, now: datetime = None) -> ComplianceResult:
    hours = load_operating_hours()
    window = hours.get(market)
    if not window:
        return ComplianceResult(False, "operating_hours_unconfigured", f"no operating-hours window for market {market}")

    tz = ZoneInfo(window["timezone"])
    local_now = (now or datetime.now(tz)).astimezone(tz)
    day = _DAY_ABBR[local_now.weekday()]
    if day not in window["days"]:
        return ComplianceResult(False, "outside_operating_hours", f"{day} not in allowed days for {market}")

    start_h, start_m = map(int, window["start"].split(":"))
    end_h, end_m = map(int, window["end"].split(":"))
    start_minutes = start_h * 60 + start_m
    end_minutes = end_h * 60 + end_m
    now_minutes = local_now.hour * 60 + local_now.minute

    if not (start_minutes <= now_minutes <= end_minutes):
        return ComplianceResult(
            False, "outside_operating_hours",
            f"{local_now.strftime('%H:%M')} {window['timezone']} outside {window['start']}-{window['end']} window for {market}",
        )
    return ComplianceResult(True)


def _load_dnc_set():
    emails, phones = set(), set()
    with open(DNC_LIST_PATH, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("contact_email"):
                emails.add(row["contact_email"].strip().lower())
            if row.get("phone"):
                phones.add(row["phone"].strip())
    return emails, phones


def dnc_check(contact_row) -> ComplianceResult:
    if contact_row["do_not_contact"]:
        return ComplianceResult(False, "do_not_contact_flag", "contact flagged do_not_contact in CRM")

    emails, phones = _load_dnc_set()
    email = (contact_row["email"] or "").strip().lower()
    phone = (contact_row["phone"] or "").strip()

    if email and email in emails:
        return ComplianceResult(False, "dnc_list_match", f"email {email} present on data/dnc_list.csv")
    if phone and phone in phones:
        return ComplianceResult(False, "dnc_list_match", f"phone {phone} present on data/dnc_list.csv")
    return ComplianceResult(True)


def check_content_ready(*texts: str) -> ComplianceResult:
    """Blocks send if rendered content still contains unfilled placeholders
    or unresolved merge fields — i.e. it would otherwise ship a literal
    "[NEEDS REAL DATA]" or "{{field}}" token to a prospect, or ship an
    unverifiable claim."""
    combined = "\n".join(t for t in texts if t)
    if PLACEHOLDER_MARKER in combined:
        return ComplianceResult(False, "missing_real_data", "rendered content still contains a [NEEDS REAL DATA] placeholder")
    unresolved = UNRESOLVED_FIELD_RE.findall(combined)
    if unresolved:
        return ComplianceResult(False, "unresolved_merge_field", f"unresolved merge fields: {sorted(set(unresolved))}")
    return ComplianceResult(True)


def check_unresolved_fields_only(*texts: str) -> ComplianceResult:
    """Same as check_content_ready but does not block on a literal
    "[NEEDS REAL DATA]" marker. Used for the human-executed call script,
    which deliberately carries permanent "don't improvise this" notes for
    the rep (e.g. competitor differentiation) — those are guidance to a
    human, not text that ships unattended, so they shouldn't block the
    call task from being queued. Unresolved {{merge_fields}} still block,
    since those would read as broken to the rep and prospect alike."""
    combined = "\n".join(t for t in texts if t)
    unresolved = UNRESOLVED_FIELD_RE.findall(combined)
    if unresolved:
        return ComplianceResult(False, "unresolved_merge_field", f"unresolved merge fields: {sorted(set(unresolved))}")
    return ComplianceResult(True)


CLAIM_PATTERN = re.compile(
    r"\b\d+(\.\d+)?\s?(%|percent\b|x faster\b|years?\b)|trusted by|industry.?leading|best[- ]in[- ]class",
    re.IGNORECASE,
)


def check_claims(text: str, facts: dict) -> ComplianceResult:
    """Heuristic scan for numeric/superlative claims not backed by
    facts['approved_claims']. Not a substitute for legal review — it's a
    tripwire so unverifiable claims get routed to a human instead of
    silently going out."""
    approved = " ".join(facts.get("approved_claims", [])).lower()
    for m in CLAIM_PATTERN.finditer(text or ""):
        snippet = text[max(0, m.start() - 25):m.end() + 25]
        if snippet.lower() not in approved and m.group(0).lower() not in approved:
            return ComplianceResult(
                False, "unverified_claim_needs_review",
                f"possible unverifiable claim near: '{snippet.strip()}' — not found in approved_claims",
            )
    return ComplianceResult(True)


def full_send_gate(market: str, contact_row, auto_facing_texts, human_only_texts, facts: dict,
                    now: datetime = None) -> list[ComplianceResult]:
    """Run every gate; returns the list of FAILED checks (empty = clear to send).

    auto_facing_texts: content behind channels that could go out with no
    further human authoring (email body/subject, LinkedIn message) — these
    are hard-blocked on both placeholder markers and unresolved fields.
    human_only_texts: content a human reads and speaks/edits live (the call
    script) — only blocked on unresolved merge fields, not on intentional
    "ask a human, don't fabricate" notes.
    """
    checks = [
        dnc_check(contact_row),
        operating_hours_ok(market, now),
        check_content_ready(*auto_facing_texts),
        check_unresolved_fields_only(*human_only_texts),
    ]
    for t in [*auto_facing_texts, *human_only_texts]:
        checks.append(check_claims(t, facts))
    return [c for c in checks if not c.ok]
