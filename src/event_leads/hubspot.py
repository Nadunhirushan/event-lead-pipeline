"""HubSpot CRM client: batch upsert of enriched leads as contacts."""
import logging
import os
import time
from collections.abc import Iterator

import httpx
from dotenv import load_dotenv

from event_leads.enrich import EnrichedLead

logger = logging.getLogger(__name__)

UPSERT_URL = "https://api.hubapi.com/crm/v3/objects/contacts/batch/upsert"
CHUNK_SIZE = 100
BACKOFF_SECONDS = (1, 2, 4, 8)  # max 4 retries


def chunked(items: list, size: int) -> Iterator[list]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def build_input(item: EnrichedLead, event_name: str) -> dict:
    """One batch-upsert input. None values are omitted so we never blank existing data."""
    lead, enr = item.lead, item.enrichment
    props = {
        "firstname": lead.first_name,
        "lastname": lead.last_name,
        "email": lead.email,
        "company": lead.company,
        "jobtitle": lead.job_title,
        "phone": lead.phone,
        "persona": enr.persona,
        "seniority": enr.seniority,
        "event_name": event_name,
    }
    return {
        "idProperty": "email",
        "id": lead.email,
        "properties": {k: v for k, v in props.items() if v is not None},
    }


def retry_delay(response: httpx.Response, attempt: int) -> float:
    """Seconds to wait before retry number `attempt` (0-based); honours Retry-After."""
    header = response.headers.get("Retry-After")
    if header:
        try:
            return max(0.0, float(header))
        except ValueError:
            pass
    return float(BACKOFF_SECONDS[attempt])


def _should_retry(status: int) -> bool:
    return status == 429 or status >= 500


class HubSpotClient:
    def __init__(self, token: str | None = None, client: httpx.Client | None = None) -> None:
        self._token = token
        self._client = client or httpx.Client(timeout=30)

    def _auth_headers(self) -> dict[str, str]:
        load_dotenv()
        token = self._token or os.environ["HUBSPOT_TOKEN"]
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    def _post_with_retry(self, body: dict) -> httpx.Response:
        for attempt in range(len(BACKOFF_SECONDS) + 1):
            response = self._client.post(UPSERT_URL, headers=self._auth_headers(), json=body)
            if response.is_success:
                return response
            if _should_retry(response.status_code) and attempt < len(BACKOFF_SECONDS):
                delay = retry_delay(response, attempt)
                logger.warning(
                    "HubSpot %d; retry %d/%d in %.1fs",
                    response.status_code, attempt + 1, len(BACKOFF_SECONDS), delay,
                )
                time.sleep(delay)
                continue
            logger.error("HubSpot error %d: %s", response.status_code, response.text)
            response.raise_for_status()
        raise AssertionError("unreachable")  # pragma: no cover

    def batch_upsert_contacts(
        self, leads: list[EnrichedLead], event_name: str, dry_run: bool = False
    ) -> int:
        """Upsert leads in chunks of <=100. Returns number of contacts sent (0 on dry run)."""
        sent = 0
        for n, chunk in enumerate(chunked(leads, CHUNK_SIZE), start=1):
            body = {"inputs": [build_input(item, event_name) for item in chunk]}
            if dry_run:
                logger.info("[dry-run] would send chunk %d (%d contacts): %s", n, len(chunk), body)
                continue
            self._post_with_retry(body)
            sent += len(chunk)
            logger.info("upserted chunk %d (%d contacts)", n, len(chunk))
        return sent
