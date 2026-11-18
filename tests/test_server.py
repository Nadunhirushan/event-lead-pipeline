import json

import httpx
import pytest
import respx

from event_leads import server
from event_leads.hubspot import UPSERT_URL

SAMPLE = "data/sample_event_leads.csv"


def fake_llm(prompt: str) -> str:
    conf = 0.5 if "ML Engineer" in prompt else 0.9
    seniority = "vp" if "VP" in prompt else "manager"
    return json.dumps({"persona": "data_leader", "seniority": seniority, "confidence": conf})


@pytest.fixture(autouse=True)
def patch_llm(monkeypatch):
    monkeypatch.setattr(server, "LLM", fake_llm)


def test_clean_event_leads() -> None:
    out = server.clean_event_leads(SAMPLE)
    assert (out["total_rows"], out["clean"], out["rejected_count"]) == (8, 4, 2)
    assert sorted(r["reason"] for r in out["rejected"]) == ["invalid_email", "personal_email"]


def test_enrich_event_leads() -> None:
    out = server.enrich_event_leads(SAMPLE)
    assert len(out) == 4
    by_email = {r["email"]: r for r in out}
    assert by_email["mei.tan@govtech.example"]["needs_review"] is True
    assert by_email["ravi.kumar@finco.example"]["seniority"] == "vp"
    assert by_email["ravi.kumar@finco.example"]["company_domain"] == "finco.example"


@respx.mock
def test_upload_defaults_to_dry_run() -> None:
    route = respx.post(UPSERT_URL).mock(return_value=httpx.Response(200))
    md = server.upload_event_leads(SAMPLE, "Dell World 2026")
    assert "Dell World 2026" in md and "dry run" in md and "Uploaded to HubSpot: 0" in md
    assert route.call_count == 0


@respx.mock
def test_upload_real_when_dry_run_false(monkeypatch) -> None:
    monkeypatch.setenv("HUBSPOT_TOKEN", "tok")
    route = respx.post(UPSERT_URL).mock(return_value=httpx.Response(200, json={}))
    md = server.upload_event_leads(SAMPLE, "E", dry_run=False)
    assert "Uploaded to HubSpot: 4" in md and route.call_count == 1


def test_missing_file_gives_clear_error() -> None:
    with pytest.raises(ValueError, match="not found"):
        server.clean_event_leads("nope.csv")


def test_dry_run_default_in_signature() -> None:
    import inspect

    assert inspect.signature(server.upload_event_leads).parameters["dry_run"].default is True


def test_tools_registered() -> None:
    import asyncio

    names = {t.name for t in asyncio.run(server.mcp.list_tools())}
    assert names == {
        "clean_event_leads",
        "enrich_event_leads",
        "upload_event_leads",
        "seo_audit",
        "ga4_page_traffic",
    }
