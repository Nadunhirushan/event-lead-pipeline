"""Cleaning and validation of raw event lead rows."""
import csv
import logging
import re
from pathlib import Path

from pydantic import BaseModel, Field

from event_leads.models import Lead

logger = logging.getLogger(__name__)

FIELDS = ("first_name", "last_name", "email", "company", "job_title", "phone")
PERSONAL_DOMAINS = {"gmail", "yahoo", "hotmail", "outlook"}
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class CleanResult(BaseModel):
    leads: list[Lead] = Field(default_factory=list)
    rejected: list[dict] = Field(default_factory=list)


def load_csv(path: str | Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _normalize(row: dict) -> dict[str, str]:
    out = {k: (row.get(k) or "").strip() for k in FIELDS}
    out["email"] = out["email"].lower()
    out["first_name"] = out["first_name"].title()
    out["last_name"] = out["last_name"].title()
    return out


def _email_problem(email: str) -> str | None:
    if not email:
        return "missing_email"
    if not EMAIL_RE.match(email):
        return "invalid_email"
    domain = email.rsplit("@", 1)[1]
    if domain.split(".")[0] in PERSONAL_DOMAINS:
        return "personal_email"
    return None


def _filled(row: dict[str, str]) -> int:
    return sum(1 for v in row.values() if v)


def clean_leads(rows: list[dict]) -> CleanResult:
    rejected: list[dict] = []
    best: dict[str, dict[str, str]] = {}
    for raw in rows:
        row = _normalize(raw)
        if not any(row.values()):
            continue
        reason = _email_problem(row["email"])
        if reason:
            rejected.append({**row, "reason": reason})
            continue
        current = best.get(row["email"])
        if current is None or _filled(row) > _filled(current):
            best[row["email"]] = row
    leads = [Lead(**{k: (v or None) for k, v in r.items()}) for r in best.values()]
    logger.info("cleaned %d leads, rejected %d", len(leads), len(rejected))
    return CleanResult(leads=leads, rejected=rejected)
