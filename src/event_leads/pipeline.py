"""End-to-end pipeline: clean -> enrich -> HubSpot upsert, plus CLI."""
import argparse
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field

from event_leads.clean import clean_leads, load_csv
from event_leads.enrich import EnrichedLead, LlmFn, call_gemini, enrich_leads
from event_leads.hubspot import HubSpotClient

logger = logging.getLogger(__name__)

SENIOR = {"c_level", "vp", "director"}


class Report(BaseModel):
    event_name: str = ""
    dry_run: bool = False
    total_rows: int = 0
    clean: int = 0
    rejected: list[dict] = Field(default_factory=list)
    uploaded: int = 0
    needs_review: list[EnrichedLead] = Field(default_factory=list)
    senior_leads: list[EnrichedLead] = Field(default_factory=list)

    def to_markdown(self) -> str:
        mode = " (dry run, nothing uploaded)" if self.dry_run else ""
        lines = [
            f"# Lead report: {self.event_name}{mode}",
            "",
            f"- Total rows: {self.total_rows}",
            f"- Clean leads: {self.clean}",
            f"- Rejected: {len(self.rejected)}",
            f"- Uploaded to HubSpot: {self.uploaded}",
            f"- Needs review: {len(self.needs_review)}",
            "",
            "## Senior leads (c-level / VP / director)",
        ]
        lines += [_describe(i) for i in self.senior_leads] or ["- none"]
        lines += ["", "## Needs review (low confidence)"]
        lines += [_describe(i) for i in self.needs_review] or ["- none"]
        lines += ["", "## Rejected"]
        lines += [f"- {r.get('email') or '(no email)'}: {r['reason']}" for r in self.rejected] or [
            "- none"
        ]
        return "\n".join(lines) + "\n"


def _describe(item: EnrichedLead) -> str:
    lead, enr = item.lead, item.enrichment
    name = " ".join(p for p in (lead.first_name, lead.last_name) if p) or lead.email
    return (
        f"- {name} ({lead.job_title or 'no title'}, {lead.company or 'no company'}) "
        f"- {enr.persona}/{enr.seniority}, confidence {enr.confidence:.2f}"
    )


def run_pipeline(
    csv_path: str | Path,
    event_name: str,
    dry_run: bool = False,
    llm: LlmFn = call_gemini,
    hubspot: HubSpotClient | None = None,
) -> Report:
    rows = load_csv(csv_path)
    cleaned = clean_leads(rows)
    enriched = enrich_leads(cleaned.leads, llm)
    client = hubspot or HubSpotClient()
    uploaded = client.batch_upsert_contacts(enriched, event_name, dry_run=dry_run)
    return Report(
        event_name=event_name,
        dry_run=dry_run,
        total_rows=len(rows),
        clean=len(cleaned.leads),
        rejected=cleaned.rejected,
        uploaded=uploaded,
        needs_review=[e for e in enriched if e.enrichment.needs_review],
        senior_leads=[e for e in enriched if e.enrichment.seniority in SENIOR],
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Clean, enrich and upload event leads.")
    parser.add_argument("csv_path")
    parser.add_argument("--event", required=True, help="Event name")
    parser.add_argument("--dry-run", action="store_true", help="Do not call HubSpot")
    args = parser.parse_args(argv)
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    report = run_pipeline(args.csv_path, args.event, dry_run=args.dry_run)
    sys.stdout.write(report.to_markdown())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
