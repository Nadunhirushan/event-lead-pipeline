"""LLM-based enrichment of leads (persona, seniority, company domain)."""
import logging
import os
import time
from collections.abc import Callable
from typing import Literal

import httpx
from dotenv import load_dotenv
from pydantic import BaseModel, Field, ValidationError

from event_leads.models import Lead

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gemini-3.5-flash"
API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
REVIEW_THRESHOLD = 0.7
BACKOFF_SECONDS = (2, 4, 8, 16, 32)  # retries for 429/5xx from Gemini

Persona = Literal[
    "data_leader", "ml_practitioner", "it_leader", "risk_leader", "business_leader", "other"
]
Seniority = Literal["c_level", "vp", "director", "manager", "individual_contributor", "unknown"]

# An LLM function takes a prompt and returns the raw text response.
LlmFn = Callable[[str], str]


class Enrichment(BaseModel):
    persona: Persona
    seniority: Seniority
    confidence: float = Field(ge=0, le=1)
    needs_review: bool = False
    company_domain: str | None = None


class EnrichedLead(BaseModel):
    lead: Lead
    enrichment: Enrichment


def build_prompt(job_title: str) -> str:
    return (
        "Classify this job title. Respond with ONLY a JSON object, no other text:\n"
        '{"persona": one of ["data_leader","ml_practitioner","it_leader","risk_leader",'
        '"business_leader","other"], "seniority": one of ["c_level","vp","director",'
        '"manager","individual_contributor","unknown"], "confidence": float between 0 and 1}\n'
        f"Job title: {job_title}"
    )


def call_gemini(prompt: str) -> str:
    """Default LLM function: calls the Gemini API. Key read from env."""
    load_dotenv()
    model = os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)
    for attempt in range(len(BACKOFF_SECONDS) + 1):
        response = httpx.post(
            API_URL.format(model=model),
            headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"]},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "responseMimeType": "application/json",
                    "maxOutputTokens": 2048,
                },
            },
            timeout=60,
        )
        retryable = response.status_code == 429 or response.status_code >= 500
        if not retryable or attempt == len(BACKOFF_SECONDS):
            break
        delay = BACKOFF_SECONDS[attempt]
        logger.warning("Gemini %d; retry %d in %ds", response.status_code, attempt + 1, delay)
        time.sleep(delay)
    response.raise_for_status()
    return response.json()["candidates"][0]["content"]["parts"][0]["text"]


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`").removeprefix("json").strip()
    return text


def parse_enrichment(text: str) -> Enrichment | None:
    try:
        return Enrichment.model_validate_json(_strip_fences(text))
    except ValidationError:
        return None


def fallback_enrichment() -> Enrichment:
    return Enrichment(persona="other", seniority="unknown", confidence=0.0)


def domain_from_email(email: str) -> str | None:
    _, _, domain = email.partition("@")
    return domain.lower() or None


def classify_title(job_title: str, llm: LlmFn = call_gemini) -> Enrichment:
    """Ask the LLM; retry once on invalid JSON; fall back to other/unknown/0."""
    prompt = build_prompt(job_title)
    for attempt in (1, 2):
        result = parse_enrichment(llm(prompt))
        if result is not None:
            return result
        logger.warning("invalid LLM JSON for title %r (attempt %d)", job_title, attempt)
    return fallback_enrichment()


def enrich_lead(lead: Lead, llm: LlmFn = call_gemini) -> EnrichedLead:
    if lead.job_title:
        result = classify_title(lead.job_title, llm)
    else:
        result = fallback_enrichment()
    result = result.model_copy(
        update={
            "needs_review": result.confidence < REVIEW_THRESHOLD,
            "company_domain": domain_from_email(lead.email),
        }
    )
    return EnrichedLead(lead=lead, enrichment=result)


def enrich_leads(leads: list[Lead], llm: LlmFn = call_gemini) -> list[EnrichedLead]:
    out: list[EnrichedLead] = []
    for i, lead in enumerate(leads, start=1):
        enriched = enrich_lead(lead, llm)
        logger.info(
            "enriched %d/%d %s -> %s/%s (%.2f)",
            i, len(leads), lead.email,
            enriched.enrichment.persona, enriched.enrichment.seniority,
            enriched.enrichment.confidence,
        )
        out.append(enriched)
    return out





