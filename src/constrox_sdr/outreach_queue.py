"""Execution-layer adapters for email, LinkedIn, and calling.

Every adapter here defaults to a dry-run / human-task-queue mode: nothing
leaves this machine, sends to a real inbox, opens LinkedIn, or dials a
number, unless a real adapter is deliberately swapped in after credentials
are confirmed (see each *_TODO class below). This matches the Phase 1/2
instruction to stub unconfirmed integrations rather than build against
systems we don't have access to yet.

- Email: DryRunEmailAdapter writes a rendered .eml-style preview file to
  outbox/email/ and logs a 'queued_dry_run' activity. Swap in a real ESP
  adapter (Instantly/Smartlead/Gmail API/etc.) once the provider + sending
  domain warmup status are confirmed.
- LinkedIn: HumanTaskQueueLinkedInAdapter appends the exact message text +
  target to human_tasks/linkedin_queue.csv for a person to send manually,
  per your answer that automation goes through an approved tool you'll
  name later. AutomatedLinkedInAdapter is a stub for that tool.
- Call: HumanTaskQueueCallAdapter appends to human_tasks/call_list.csv with
  the rendered script attached, for human dialing. DialerAdapter is a stub
  for a consent-based dialer API.
"""
import csv
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path

from .paths import OUTBOX_DIR, HUMAN_TASKS_DIR


# ---------------------------------------------------------------- email ----

class EmailAdapter(ABC):
    @abstractmethod
    def send(self, to_email: str, subject: str, body: str, contact_id: int) -> str:
        """Return an activity status string, e.g. 'sent' or 'queued_dry_run'."""


class DryRunEmailAdapter(EmailAdapter):
    def send(self, to_email, subject, body, contact_id):
        OUTBOX_DIR.joinpath("email").mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        out_path = OUTBOX_DIR / "email" / f"{ts}_contact{contact_id}.txt"
        out_path.write_text(f"To: {to_email}\nSubject: {subject}\n\n{body}\n", encoding="utf-8")
        return "queued_dry_run"


class RealEmailAdapter(EmailAdapter):
    """TODO: implement against the confirmed ESP (Instantly/Smartlead/Gmail
    API/other) once the sending domain, warmup status, and API credentials
    are confirmed. Do not send from an unwarmed domain — deliverability
    (and the domain's reputation) will suffer."""

    def __init__(self, api_key: str = None):
        self.api_key = api_key

    def send(self, to_email, subject, body, contact_id):
        raise NotImplementedError("Real email sending not configured. Use DryRunEmailAdapter until an ESP is confirmed.")


# ------------------------------------------------------------- linkedin ----

class LinkedInAdapter(ABC):
    @abstractmethod
    def queue_connection(self, contact_row, note: str) -> str: ...

    @abstractmethod
    def queue_message(self, contact_row, body: str) -> str: ...


class HumanTaskQueueLinkedInAdapter(LinkedInAdapter):
    _CSV_PATH = HUMAN_TASKS_DIR / "linkedin_queue.csv"

    def _append(self, contact_row, task_type, content):
        is_new = not self._CSV_PATH.exists()
        with open(self._CSV_PATH, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if is_new:
                writer.writerow(["queued_at", "contact_id", "first_name", "last_name", "linkedin_url", "task_type", "content", "status"])
            writer.writerow([
                datetime.now(timezone.utc).isoformat(), contact_row["id"], contact_row["first_name"],
                contact_row["last_name"], contact_row["linkedin_url"] or "", task_type, content, "pending_human_send",
            ])

    def queue_connection(self, contact_row, note):
        self._append(contact_row, "connection_request", note)
        return "queued_for_human"

    def queue_message(self, contact_row, body):
        self._append(contact_row, "message", body)
        return "queued_for_human"


class AutomatedLinkedInAdapter(LinkedInAdapter):
    """TODO: name the approved automation tool (e.g. Expandi, Dux-Soup,
    PhantomBuster, HeyReach) and implement against its API once you've
    confirmed the tool, seat, and daily action limits. Keep LinkedIn's
    commercial-use terms and per-day connection/message caps in mind —
    aggressive automation risks the Sales Navigator seat."""

    def queue_connection(self, contact_row, note):
        raise NotImplementedError("No automation tool named yet. Use HumanTaskQueueLinkedInAdapter until confirmed.")

    def queue_message(self, contact_row, body):
        raise NotImplementedError("No automation tool named yet. Use HumanTaskQueueLinkedInAdapter until confirmed.")


# ------------------------------------------------------------------ call --

class CallAdapter(ABC):
    @abstractmethod
    def queue_call(self, contact_row, script_preview: str) -> str: ...


class HumanTaskQueueCallAdapter(CallAdapter):
    _CSV_PATH = HUMAN_TASKS_DIR / "call_list.csv"

    def queue_call(self, contact_row, script_preview):
        is_new = not self._CSV_PATH.exists()
        with open(self._CSV_PATH, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if is_new:
                writer.writerow(["queued_at", "contact_id", "first_name", "last_name", "phone", "script_ref", "status"])
            writer.writerow([
                datetime.now(timezone.utc).isoformat(), contact_row["id"], contact_row["first_name"],
                contact_row["last_name"], contact_row["phone"] or "", "content/call/script.md", "pending_human_call",
            ])
        return "queued_for_human"


class DialerAdapter(CallAdapter):
    """TODO: implement against a consent-based dialer API once confirmed.
    Do not autodial numbers without a documented consent / legitimate
    interest basis (TCPA in the US, PECR in the UK)."""

    def queue_call(self, contact_row, script_preview):
        raise NotImplementedError("No dialer configured. Use HumanTaskQueueCallAdapter until confirmed.")
