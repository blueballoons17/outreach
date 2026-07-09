"""Parse the markdown template library in content/ and render merge fields.

Templates use {{field}} placeholders. Rendering never invents a value: any
field it can't resolve from facts/contact/company data is left as a
visible {{unresolved_field}} token, and the compliance gate treats both
literal "[NEEDS REAL DATA" strings and unresolved {{...}} tokens as a hard
block on sending (see compliance.check_content_ready).
"""
import json
import re
from pathlib import Path

from ..paths import CONTENT_DIR, FACTS_PATH

STEP_HEADER_RE = re.compile(r"^## Step \d+.*$", re.MULTILINE)
FIELD_RE = re.compile(r"\{\{(\w+)\}\}")


def load_facts():
    with open(FACTS_PATH) as f:
        return json.load(f)


def _parse_email_sequence(md_path: Path):
    text = md_path.read_text(encoding="utf-8")
    headers = list(STEP_HEADER_RE.finditer(text))
    steps = []
    for i, m in enumerate(headers):
        start = m.end()
        end = headers[i + 1].start() if i + 1 < len(headers) else len(text)
        block = text[start:end]
        subject_match = re.search(r"^Subject:\s*(.+)$", block, re.MULTILINE)
        body_match = re.search(r"^Body:\s*\n(.*)", block, re.DOTALL | re.MULTILINE)
        subject = subject_match.group(1).strip() if subject_match else ""
        body = body_match.group(1).strip() if body_match else ""
        body = body.split("\n---")[0].strip()
        steps.append({"step": m.group(0).strip("# ").strip(), "subject": subject, "body": body})
    return steps


EMAIL_SEQUENCE_FILES = {
    "UK": CONTENT_DIR / "email" / "uk_sequence.md",
    "US": CONTENT_DIR / "email" / "us_sequence.md",
    "AU": CONTENT_DIR / "email" / "au_sequence.md",
}


def load_email_sequence(geo_market: str):
    path = EMAIL_SEQUENCE_FILES.get(geo_market)
    if not path:
        raise ValueError(f"no email sequence for market {geo_market!r}")
    return _parse_email_sequence(path)


def render(text: str, context: dict) -> str:
    def replace(m):
        key = m.group(1)
        return str(context[key]) if key in context and context[key] not in (None, "") else "{{" + key + "}}"

    return FIELD_RE.sub(replace, text)


def build_context(contact_row, company_row, facts: dict) -> dict:
    services = facts.get("services") or []
    services_bullet_list = "\n".join(f"- {s}" for s in services) if services else "{{services_bullet_list}}"

    intent = company_row["intent_signal_1"] if company_row["intent_signal_1"] else None
    intent_fallback = intent or "is active in the " + (company_row["sub_vertical"] or "AEC") + " space"

    unsubscribe_footer = (
        f"{facts.get('company_legal_name', '')}\n"
        f"{facts.get('physical_address', '')}\n"
        f"Unsubscribe: {facts.get('unsubscribe_url', '')}"
    )

    ctx = {
        "first_name": contact_row["first_name"],
        "last_name": contact_row["last_name"],
        "title": contact_row["title"],
        "email": contact_row["email"],
        "company_name": company_row["name"],
        "sub_vertical": company_row["sub_vertical"] or "AEC",
        "intent_signal_1_or_fallback": intent_fallback,
        "services_bullet_list": services_bullet_list,
        "unsubscribe_footer": unsubscribe_footer,
        **{k: v for k, v in facts.items() if not k.startswith("_")},
    }
    ctx["value_prop_short_short"] = (ctx.get("value_prop_short") or "")[:120]
    return ctx


def render_email_step(step: dict, context: dict) -> dict:
    return {
        "step": step["step"],
        "subject": render(step["subject"], context),
        "body": render(step["body"], context),
    }


LINKEDIN_TEMPLATES_PATH = CONTENT_DIR / "linkedin" / "templates.md"
CALL_SCRIPT_PATH = CONTENT_DIR / "call" / "script.md"

SECTION_HEADER_RE = re.compile(r"^## (.+)$", re.MULTILINE)


def _parse_sections(md_path: Path):
    text = md_path.read_text(encoding="utf-8")
    headers = list(SECTION_HEADER_RE.finditer(text))
    sections = []
    for i, m in enumerate(headers):
        start = m.end()
        end = headers[i + 1].start() if i + 1 < len(headers) else len(text)
        body = text[start:end].split("\n---")[0].strip()
        sections.append({"title": m.group(1).strip(), "body": body})
    return sections


def load_linkedin_templates():
    return _parse_sections(LINKEDIN_TEMPLATES_PATH)


def render_linkedin_templates(context: dict):
    return [{"title": s["title"], "body": render(s["body"], context)} for s in load_linkedin_templates()]


def load_call_script():
    return _parse_sections(CALL_SCRIPT_PATH)


def render_call_script(context: dict):
    return [{"title": s["title"], "body": render(s["body"], context)} for s in load_call_script()]
