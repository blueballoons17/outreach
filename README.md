# Constrox SDR Pipeline

An autonomous prospecting → scoring → outreach → CRM-logging pipeline for
Constrox's AEC outsourcing sales development. Built to run end-to-end
against a real internal CRM today, with clean seams to plug in Constrox's
actual CRM/ESP/LinkedIn automation/dialer once credentials are confirmed.

## Status: what's real vs. what's a placeholder

This is a working system, not a mockup — running it moves real rows
through a real database and produces real files. Two things are
intentionally not real yet, both because they require information only
Constrox can provide, and Phase 1/3 of the build spec explicitly says not
to fabricate or integrate blind:

1. **`config/constrox_facts.json`** — value prop, services, case studies,
   pricing, sender identity, unsubscribe URL are all `[NEEDS REAL DATA]`
   placeholders. **The compliance gate hard-blocks any email/LinkedIn send
   until these are filled in** — see "Guardrails" below.
2. **`config/scoring_weights.json` → `icp`** — sub-verticals, company size
   band, and UK/US/AU geo split are placeholders. Until filled in, fit
   scoring runs in "neutral mode" (every lead gets fit_score = 50) and logs
   a note saying so, rather than pretending to know Constrox's ICP.

Everything else — ingestion, scoring math, content rendering, compliance
checks, CRM writes, reporting — is fully implemented and covered by tests.

## Quick start

```bash
python3 -m unittest discover -s tests -v      # 12 tests, no dependencies beyond stdlib
python3 cli.py run --input data/sample_prospects.csv
python3 cli.py weekly-report
python3 cli.py daily-summary
python3 cli.py stale-deals
```

`data/sample_prospects.csv` is fictitious test data (`.test` domains) — use
it to see the pipeline work, then point `--input` at a real exported list.

## Pipeline flow (`src/constrox_sdr/orchestrator.py: run_pipeline`)

1. **Ingest** (`ingest.py`) — CSV → `companies` + `contacts` tables.
2. **Enrich** (`enrichment.py`) — pluggable intent-signal provider. Default
   is a pass-through (uses signals already in the CSV, invents nothing). A
   live web-search/data-provider enrichment path is stubbed with a `TODO`.
3. **Score** (`scoring.py`) — transparent fit + intent scoring, weights and
   thresholds fully adjustable in `config/scoring_weights.json`, no code
   changes needed to retune.
4. **Rank & export** — ranked CSV written to `reports/ranked_leads_*.csv`.
5. **Generate content** (`content/templates.py` + `content/*.md`) — merge
   fields filled from CRM data + `constrox_facts.json` for leads above the
   qualification threshold.
6. **Compliance gate** (`compliance.py`) — every rendered message must pass
   DNC check, operating-hours check, placeholder/unresolved-field check,
   and a claim-verification tripwire before it's queued.
7. **Queue outreach** (`outreach_queue.py`) — dry-run/human-task-queue
   adapters by default (see table below).
8. **Log to CRM** (`crm_writeback.py`) — every touch, every compliance
   block, every deal-stage change written to `data/crm.db` with a
   timestamp before it's considered done.
9. **Report** (`reporting.py`) — weekly pipeline report, daily summary,
   stale-deal alerts, all reading from the same CRM.

## Automated vs. human-required, and why

| Capability | Status | Why |
|---|---|---|
| Prospect ingestion, enrichment pass-through, lead scoring, ranked export | **Fully automated** | No external system dependency; runs entirely on local data. |
| Email/LinkedIn/call content generation | **Fully automated** | Templated + merge-fielded from CRM + facts file. |
| Compliance gate (DNC, operating hours, placeholder/claim check) | **Fully automated** | Runs before every queue action; blocks rather than guesses. |
| CRM logging (internal SQLite) | **Fully automated** | Real system of record today. |
| Email sending | **Dry-run only** (writes preview to `outbox/email/`) | No ESP/sending domain confirmed yet. Sending from an unwarmed domain risks the domain's deliverability/reputation — `outreach_queue.RealEmailAdapter` is stubbed with a `NotImplementedError` and a `TODO` for whichever provider (Instantly/Smartlead/Gmail API/etc.) gets confirmed. |
| LinkedIn connect/message | **Human task queue** (`human_tasks/linkedin_queue.csv`) | You confirmed automation should go through an approved tool, but didn't name one yet — `outreach_queue.AutomatedLinkedInAdapter` is stubbed pending that name + API credentials. Until then, a person reviews the generated message and clicks send, keeping LinkedIn's per-day action limits and ToS intact. |
| Cold calling | **Human task queue** (`human_tasks/call_list.csv`) with generated script | No dialer confirmed. Auto-dialing without a documented consent/legitimate-interest basis risks TCPA (US) / PECR (UK) violations — `outreach_queue.DialerAdapter` is stubbed pending a confirmed, consent-based dialer. |
| External CRM writeback (HubSpot/Salesforce/Pipedrive) | **Not built** | You chose the internal CRM for now. `crm_writeback.push_to_external_crm` is stubbed for whichever system gets adopted later — same call sites, no pipeline rewrite needed. |
| Sending/queueing outside a market's approved hours, or to a DNC-listed contact | **Blocked, always** | Enforced in `compliance.py`, not a policy note. |

Nothing described above requires guessing what Constrox wants — it's a
direct consequence of "no CRM/ESP/LinkedIn tool/dialer confirmed yet, no
real value prop/case studies given yet."

## Turning on real integrations

1. **Email**: pick an ESP, confirm the sending domain is warmed up, add API
   creds, implement `outreach_queue.RealEmailAdapter.send`, pass
   `email_adapter=RealEmailAdapter(...)` into `run_pipeline`.
2. **LinkedIn**: name the approved automation tool, implement
   `outreach_queue.AutomatedLinkedInAdapter`, swap it in the same way.
3. **Dialer**: confirm a consent-based dialer with an API, implement
   `outreach_queue.DialerAdapter`.
4. **External CRM**: implement `crm_writeback.push_to_external_crm` against
   the confirmed system's API and call it alongside `log_activity` (keep
   the internal DB as the audit trail even after this is live).
5. **Fill in `config/constrox_facts.json`** with the real value prop,
   services, sender identity, unsubscribe URL, booking link, and any
   case studies/approved claims — this alone unblocks real sends, since
   the compliance gate is what's currently stopping them.
6. **Fill in `config/scoring_weights.json` → `icp`** with real
   sub-verticals, company size band, and UK/US/AU geo split targets to get
   meaningful fit scores instead of the neutral 50 default.

## Reporting

- `python3 cli.py weekly-report` → `reports/weekly_report_*.md`: pipeline
  value by stage, stage-by-stage conversion, revenue + commission (paid
  invoices only, per the "commission is released on paid invoices" rule),
  and a 3x-pipeline-coverage check against
  `config/pipeline_settings.json: target_monthly_revenue_usd`.
- `python3 cli.py daily-summary` → what was auto-sent, what needs a human
  click, what closed today, what's compliance-blocked and needs review.
- `python3 cli.py stale-deals` → open deals with no activity in
  `stale_deal_days` (default 14), so nothing silently dies in the funnel.

## Project layout

```
cli.py                        entrypoint: run / weekly-report / daily-summary / stale-deals
config/                       facts, scoring weights, operating hours, pipeline targets
content/                      email/LinkedIn/call-script template library (markdown, merge-fielded)
data/sample_prospects.csv     fictitious test data; data/crm.db is the runtime CRM (gitignored)
src/constrox_sdr/
  db.py                       SQLite schema (companies, contacts, lead_scores, deals, activities, compliance_flags)
  ingest.py                   CSV → CRM
  enrichment.py                intent-signal provider interface (stub + TODO for live search)
  scoring.py                  fit + intent scoring
  content/templates.py        markdown template parser + merge-field renderer
  compliance.py               DNC / operating-hours / placeholder / claim gates
  outreach_queue.py           email/LinkedIn/call adapters (dry-run + stubbed real adapters)
  crm_writeback.py            activity logging, deal stage transitions
  orchestrator.py             run_pipeline(): ties every module together
  reporting.py                weekly report, daily summary, stale-deal alerts
tests/                        unittest suite (stdlib only, no pytest dependency)
outbox/, human_tasks/, reports/   runtime output (gitignored except structure)
```

## Known limitations (tracked, not hidden)

- US operating-hours window is a single Eastern-time default — TCPA
  call-time compliance is evaluated at the *recipient's* local time, so
  this needs per-state/timezone segmentation once real US target
  geography is known (see `config/operating_hours.json`).
- Claim-verification (`compliance.check_claims`) is a regex tripwire for
  numeric/superlative language, not a substitute for legal review — it
  routes suspicious content to `compliance_flags` for a human to check,
  it doesn't guarantee correctness.
- Enrichment is pass-through only; no live web-search/data-provider call is
  wired in yet (deliberately — see `enrichment.py`).
