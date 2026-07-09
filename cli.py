#!/usr/bin/env python3
"""Constrox SDR pipeline CLI.

Examples:
    python cli.py run --input data/sample_prospects.csv
    python cli.py weekly-report
    python cli.py daily-summary
    python cli.py stale-deals
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from constrox_sdr import reporting
from constrox_sdr.db import get_conn
from constrox_sdr.orchestrator import run_pipeline


def cmd_run(args):
    result = run_pipeline(args.input)
    print(f"Ingested: {result['ingest'].companies_created} new companies, "
          f"{result['ingest'].contacts_created} new contacts "
          f"({result['ingest'].rows_skipped} rows skipped)")
    if result["ingest"].errors:
        print("Ingest warnings:")
        for e in result["ingest"].errors:
            print(f"  - {e}")
    print(f"Scored leads: {result['total_leads']} total, {result['qualified_leads']} above threshold")
    print(f"Outreach: {result['queued']} queued, {result['blocked']} blocked by compliance")
    print(f"Ranked lead export: {result['ranked_csv']}")


def cmd_weekly_report(args):
    with get_conn() as conn:
        path = reporting.write_weekly_report(conn)
    print(f"Weekly report written to {path}")


def cmd_daily_summary(args):
    with get_conn() as conn:
        summary = reporting.daily_summary(conn)
    print(summary)


def cmd_stale_deals(args):
    with get_conn() as conn:
        stale = reporting.stale_deals(conn)
    if not stale:
        print("No stale deals.")
        return
    for d in stale:
        print(f"deal {d['id']} | contact {d['contact_id']} | stage {d['stage']} | "
              f"last activity {d['last_activity_at']}")


def main():
    parser = argparse.ArgumentParser(description="Constrox SDR pipeline")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="Run the full ingest->score->outreach pipeline")
    p_run.add_argument("--input", required=True, help="Path to prospect CSV")
    p_run.set_defaults(func=cmd_run)

    p_weekly = sub.add_parser("weekly-report", help="Generate the weekly pipeline report")
    p_weekly.set_defaults(func=cmd_weekly_report)

    p_daily = sub.add_parser("daily-summary", help="Print today's summary: sent, needs-human, closed/stalled")
    p_daily.set_defaults(func=cmd_daily_summary)

    p_stale = sub.add_parser("stale-deals", help="List deals with no activity in the configured stale window")
    p_stale.set_defaults(func=cmd_stale_deals)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
