"""Intent-signal enrichment.

Real enrichment (recent hiring, funding/expansion news) requires a live web
search or a paid data provider (Apollo/Clay/Crunchbase/etc.) called per
company. That is an external network call this codebase intentionally does
NOT make automatically on arbitrary input — wiring it up is a one-function
change (see LiveWebSearchEnrichmentProvider.TODO below) once you've
confirmed which provider/API key to use and reviewed the cost of calling it
per-prospect at scale.

Until then, enrichment is a pass-through: if intent_signal_1 /
intent_signal_2 were already present in the ingested CSV (e.g. pulled from
Apollo/Clay before import), they're used as-is. Otherwise they stay null,
and scoring.py treats a missing intent signal as 0 evidence rather than
inventing one.
"""
from abc import ABC, abstractmethod


class EnrichmentProvider(ABC):
    @abstractmethod
    def get_intent_signals(self, company_name: str, website: str | None) -> tuple[str | None, str | None]:
        """Return (intent_signal_1, intent_signal_2) or (None, None)."""


class NullEnrichmentProvider(EnrichmentProvider):
    """Default provider: does nothing, invents nothing."""

    def get_intent_signals(self, company_name, website):
        return None, None


class LiveWebSearchEnrichmentProvider(EnrichmentProvider):
    """TODO: implement once a search/data provider is confirmed.

    Suggested approach: query a news/company-data API for recent hiring
    posts, funding announcements, or expansion press releases for
    `company_name` (scoped by `website` domain to disambiguate), and return
    two short, sourced strings. Do not summarize speculation as fact —
    every signal string should be traceable to a dated source, since it may
    end up quoted in outreach copy and is subject to the same
    no-fabrication guardrail as case studies.
    """

    def get_intent_signals(self, company_name, website):
        raise NotImplementedError(
            "Live enrichment not configured. Provide a search/data provider "
            "and implement this method, or continue using NullEnrichmentProvider."
        )


def enrich_all_companies(conn, provider: EnrichmentProvider = None):
    """Fill missing intent signals for companies that don't have any yet.

    Safe to call repeatedly — only touches companies with both signals null.
    """
    provider = provider or NullEnrichmentProvider()
    rows = conn.execute(
        "SELECT id, name, website FROM companies WHERE intent_signal_1 IS NULL AND intent_signal_2 IS NULL"
    ).fetchall()
    updated = 0
    for row in rows:
        sig1, sig2 = provider.get_intent_signals(row["name"], row["website"])
        if sig1 or sig2:
            conn.execute(
                "UPDATE companies SET intent_signal_1 = ?, intent_signal_2 = ? WHERE id = ?",
                (sig1, sig2, row["id"]),
            )
            updated += 1
    return updated
