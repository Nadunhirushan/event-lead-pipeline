"""MCP server exposing the event-lead pipeline as tools (stdio transport)."""
import logging
import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from event_leads.clean import clean_leads, load_csv
from event_leads.enrich import LlmFn, call_gemini, enrich_leads
from event_leads.pipeline import run_pipeline

logger = logging.getLogger(__name__)

mcp = FastMCP("event-leads")

# LLM used for enrichment; looked up at call time so tests can replace it.
LLM: LlmFn = call_gemini


def _load(csv_path: str) -> list[dict]:
    if not Path(csv_path).is_file():
        raise ValueError(f"CSV file not found: {csv_path}")
    return load_csv(csv_path)


@mcp.tool()
def clean_event_leads(csv_path: str) -> dict:
    """Clean and validate an event leads CSV. Makes no network calls and changes nothing.

    Use this first to see how good the raw data is. Strips whitespace, lowercases emails,
    title-cases names, removes duplicates (keeping the most complete row), and rejects
    rows with a missing or invalid email or a personal email (gmail/yahoo/hotmail/outlook).

    Args:
        csv_path: Path to the CSV file (columns: first_name, last_name, email, company,
            job_title, phone).

    Returns:
        total_rows, clean count, rejected count, and the rejected rows with a `reason`
        (missing_email, invalid_email or personal_email).
    """
    rows = _load(csv_path)
    result = clean_leads(rows)
    return {
        "total_rows": len(rows),
        "clean": len(result.leads),
        "rejected_count": len(result.rejected),
        "rejected": [
            {"email": r.get("email", ""), "reason": r["reason"]} for r in result.rejected
        ],
    }


@mcp.tool()
def enrich_event_leads(csv_path: str) -> list[dict]:
    """Clean an event leads CSV, then classify each lead's job title with an LLM.

    Use this to preview personas and seniority before uploading. Calls the Gemini API
    (uses API quota) but does NOT write to HubSpot.

    Args:
        csv_path: Path to the CSV file.

    Returns:
        One entry per clean lead with email, name, company, job_title, company_domain,
        persona (data_leader, ml_practitioner, it_leader, risk_leader, business_leader,
        other), seniority (c_level, vp, director, manager, individual_contributor,
        unknown), confidence (0-1) and needs_review (true when confidence < 0.7).
    """
    leads = clean_leads(_load(csv_path)).leads
    out = []
    for item in enrich_leads(leads, LLM):
        lead, enr = item.lead, item.enrichment
        out.append(
            {
                "email": lead.email,
                "name": " ".join(p for p in (lead.first_name, lead.last_name) if p),
                "company": lead.company,
                "job_title": lead.job_title,
                "company_domain": enr.company_domain,
                "persona": enr.persona,
                "seniority": enr.seniority,
                "confidence": enr.confidence,
                "needs_review": enr.needs_review,
            }
        )
    return out


@mcp.tool()
def upload_event_leads(csv_path: str, event_name: str, dry_run: bool = True) -> str:
    """Run the full pipeline (clean, enrich, upload to HubSpot) and return a sales report.

    SAFE BY DEFAULT: dry_run is True, which enriches leads but sends nothing to HubSpot.
    Only set dry_run=False when the user has explicitly asked to upload for real, because
    it creates or updates live CRM contacts.

    Args:
        csv_path: Path to the CSV file.
        event_name: Event the leads came from (stored on each contact as event_name).
        dry_run: If True (default), do not call HubSpot.

    Returns:
        A markdown report: totals, rejected rows, uploaded count, leads needing review,
        and senior leads (c-level, VP, director).
    """
    _load(csv_path)  # clear error if the file is missing
    report = run_pipeline(csv_path, event_name, dry_run=dry_run, llm=LLM)
    return report.to_markdown()


def main() -> None:
    # stdout carries the MCP protocol, so logs must go to stderr.
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    mcp.run()


if __name__ == "__main__":
    main()
