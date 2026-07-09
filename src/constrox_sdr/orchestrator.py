"""End-to-end pipeline: ingest -> enrich -> score -> generate content ->
compliance gate -> queue outreach -> log CRM. This is what makes the system
run autonomously rather than as a set of disconnected scripts — one call
to run_pipeline() takes a raw CSV all the way to logged, compliant,
queued outreach and a ranked lead export.

Design choice, documented here rather than buried in code: a deal moves to
stage "Contacted" the moment its first touch is *queued* on any channel
(dry-run email written to outbox/, LinkedIn/call task written to
human_tasks/), not only once a human confirms a real send. That keeps
pipeline tracking honest about "an attempt entered the funnel" without
requiring a human-in-the-loop confirmation step to update CRM state. Real
delivery/open/reply/call-outcome events (once real adapters exist) should
still be logged as their own activity rows with their own status.
"""
import csv
from datetime import datetime, timezone
from pathlib import Path

from . import compliance, crm_writeback, enrichment, ingest, scoring
from .content import templates
from .db import get_conn
from .outreach_queue import (
    DryRunEmailAdapter,
    HumanTaskQueueCallAdapter,
    HumanTaskQueueLinkedInAdapter,
)
from .paths import REPORTS_DIR


def export_ranked_csv(conn, out_path=None):
    out_path = out_path or REPORTS_DIR / f"ranked_leads_{datetime.now(timezone.utc):%Y%m%d}.csv"
    rows = scoring.ranked_leads(conn)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["contact_id", "first_name", "last_name", "title", "email", "phone",
                          "company_name", "sub_vertical", "geo_market", "fit_score", "intent_score",
                          "total_score", "notes", "scored_at"])
        for r in rows:
            writer.writerow([r["contact_id"], r["first_name"], r["last_name"], r["title"], r["email"],
                              r["phone"], r["company_name"], r["sub_vertical"], r["geo_market"],
                              r["fit_score"], r["intent_score"], r["total_score"], r["notes"], r["scored_at"]])
    return out_path


def process_lead(conn, contact_id, facts, email_adapter, linkedin_adapter, call_adapter, now=None):
    """Generate content, run the compliance gate, and queue (or flag) the
    first-touch outreach for a single scored contact. Returns a summary
    dict used for the daily/run summary."""
    contact = conn.execute("SELECT * FROM contacts WHERE id = ?", (contact_id,)).fetchone()
    company = conn.execute("SELECT * FROM companies WHERE id = ?", (contact["company_id"],)).fetchone()
    market = company["geo_market"]

    deal_id = crm_writeback.get_or_create_deal(conn, contact_id, company["id"])

    context = templates.build_context(contact, company, facts)
    email_steps = templates.load_email_sequence(market)
    first_email = templates.render_email_step(email_steps[0], context)
    linkedin_msgs = templates.render_linkedin_templates(context)
    connection_note = linkedin_msgs[0]["body"] if linkedin_msgs else ""
    call_script = templates.render_call_script(context)
    call_preview = "\n\n".join(f"{s['title']}\n{s['body']}" for s in call_script)

    auto_facing_texts = [first_email["subject"], first_email["body"], connection_note]
    human_only_texts = [call_preview]
    failures = compliance.full_send_gate(market, contact, auto_facing_texts, human_only_texts, facts, now=now)

    if failures:
        for f in failures:
            crm_writeback.log_compliance_flag(conn, "contact", contact_id, f.flag_type, f.detail)
        crm_writeback.log_activity(
            conn, contact_id, "system", "compliance_blocked", "blocked", requires_human=True,
            detail="; ".join(f"{f.flag_type}: {f.detail}" for f in failures), deal_id=deal_id,
        )
        return {"contact_id": contact_id, "status": "blocked", "reasons": [f.flag_type for f in failures]}

    email_status = email_adapter.send(contact["email"], first_email["subject"], first_email["body"], contact_id)
    crm_writeback.log_activity(conn, contact_id, "email", "sequence_step_1", email_status,
                                requires_human=isinstance(email_adapter, DryRunEmailAdapter),
                                detail=first_email["subject"], deal_id=deal_id)

    li_status = linkedin_adapter.queue_connection(contact, connection_note)
    crm_writeback.log_activity(conn, contact_id, "linkedin", "connection_request", li_status,
                                requires_human=True, detail=connection_note[:200], deal_id=deal_id)

    call_status = call_adapter.queue_call(contact, call_preview)
    crm_writeback.log_activity(conn, contact_id, "call", "discovery_call", call_status,
                                requires_human=True, detail="script queued", deal_id=deal_id)

    crm_writeback.update_deal_stage(conn, deal_id, "Contacted")
    return {"contact_id": contact_id, "status": "queued", "deal_id": deal_id}


def run_pipeline(csv_path, qualification_threshold=None, enrichment_provider=None,
                  email_adapter=None, linkedin_adapter=None, call_adapter=None, now=None):
    enrichment_provider = enrichment_provider or enrichment.NullEnrichmentProvider()
    email_adapter = email_adapter or DryRunEmailAdapter()
    linkedin_adapter = linkedin_adapter or HumanTaskQueueLinkedInAdapter()
    call_adapter = call_adapter or HumanTaskQueueCallAdapter()

    facts = templates.load_facts()
    weights = scoring.load_weights()
    threshold = qualification_threshold if qualification_threshold is not None else weights["qualification_threshold"]

    with get_conn() as conn:
        ingest_result = ingest.ingest_csv(conn, csv_path)
        enrichment.enrich_all_companies(conn, enrichment_provider)
        scoring.score_all_contacts(conn, weights)
        ranked_csv_path = export_ranked_csv(conn)

        leads = scoring.ranked_leads(conn)
        qualified = [l for l in leads if l["total_score"] >= threshold]

        results = []
        for lead in qualified:
            result = process_lead(conn, lead["contact_id"], facts, email_adapter, linkedin_adapter, call_adapter, now=now)
            results.append(result)

    return {
        "ingest": ingest_result,
        "ranked_csv": str(ranked_csv_path),
        "total_leads": len(leads),
        "qualified_leads": len(qualified),
        "queued": sum(1 for r in results if r["status"] == "queued"),
        "blocked": sum(1 for r in results if r["status"] == "blocked"),
        "results": results,
    }
