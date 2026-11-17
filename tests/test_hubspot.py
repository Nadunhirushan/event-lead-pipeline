import json

import httpx
import pytest
import respx

from event_leads import hubspot
from event_leads.enrich import EnrichedLead, Enrichment
from event_leads.hubspot import UPSERT_URL, HubSpotClient
from event_leads.models import Lead


@pytest.fixture(autouse=True)
def fast(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr(hubspot.time, "sleep", sleeps.append)
    monkeypatch.setenv("HUBSPOT_TOKEN", "tok")
    return sleeps


def item(i: int = 0) -> EnrichedLead:
    return EnrichedLead(
        lead=Lead(email=f"u{i}@acme.example", first_name="A", job_title="CDO"),
        enrichment=Enrichment(persona="data_leader", seniority="c_level", confidence=0.9),
    )


@respx.mock
def test_successful_upsert_body_and_auth() -> None:
    route = respx.post(UPSERT_URL).mock(return_value=httpx.Response(200, json={}))
    assert HubSpotClient().batch_upsert_contacts([item()], "Dell World 2026") == 1
    req = route.calls[0].request
    assert req.headers["authorization"] == "Bearer tok"
    entry = json.loads(req.content)["inputs"][0]
    assert entry["idProperty"] == "email" and entry["id"] == "u0@acme.example"
    props = entry["properties"]
    assert props["event_name"] == "Dell World 2026"
    assert props["persona"] == "data_leader" and props["seniority"] == "c_level"
    assert props["firstname"] == "A" and props["jobtitle"] == "CDO"
    assert "phone" not in props  # None values omitted


@respx.mock
def test_429_then_success_retries(fast) -> None:
    route = respx.post(UPSERT_URL).mock(
        side_effect=[httpx.Response(429), httpx.Response(200, json={})]
    )
    assert HubSpotClient().batch_upsert_contacts([item()], "E") == 1
    assert route.call_count == 2
    assert fast == [1.0]


@respx.mock
def test_retry_after_header_respected(fast) -> None:
    respx.post(UPSERT_URL).mock(
        side_effect=[httpx.Response(429, headers={"Retry-After": "7"}), httpx.Response(200)]
    )
    HubSpotClient().batch_upsert_contacts([item()], "E")
    assert fast == [7.0]


@respx.mock
def test_5xx_backoff_then_gives_up(fast) -> None:
    route = respx.post(UPSERT_URL).mock(return_value=httpx.Response(503))
    with pytest.raises(httpx.HTTPStatusError):
        HubSpotClient().batch_upsert_contacts([item()], "E")
    assert route.call_count == 5  # 1 try + 4 retries
    assert fast == [1.0, 2.0, 4.0, 8.0]


@respx.mock
def test_400_raises_without_retry(fast, caplog) -> None:
    route = respx.post(UPSERT_URL).mock(return_value=httpx.Response(400, text="bad property"))
    with pytest.raises(httpx.HTTPStatusError):
        HubSpotClient().batch_upsert_contacts([item()], "E")
    assert route.call_count == 1 and fast == []
    assert "bad property" in caplog.text


@respx.mock
def test_chunking_250_leads_is_3_calls() -> None:
    route = respx.post(UPSERT_URL).mock(return_value=httpx.Response(200, json={}))
    sent = HubSpotClient().batch_upsert_contacts([item(i) for i in range(250)], "E")
    sizes = [len(json.loads(c.request.content)["inputs"]) for c in route.calls]
    assert sizes == [100, 100, 50] and sent == 250


@respx.mock
def test_dry_run_makes_no_calls(monkeypatch) -> None:
    monkeypatch.delenv("HUBSPOT_TOKEN")
    route = respx.post(UPSERT_URL).mock(return_value=httpx.Response(200))
    assert HubSpotClient().batch_upsert_contacts([item()], "E", dry_run=True) == 0
    assert route.call_count == 0
