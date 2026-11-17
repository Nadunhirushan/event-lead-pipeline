import json

import httpx
import respx

from event_leads.hubspot import UPSERT_URL, HubSpotClient
from event_leads.pipeline import main, run_pipeline

SAMPLE = "data/sample_event_leads.csv"


def fake_llm(prompt: str) -> str:
    if "VP Risk" in prompt:
        return json.dumps({"persona": "risk_leader", "seniority": "vp", "confidence": 0.95})
    if "ML Engineer" in prompt:
        return json.dumps({"persona": "ml_practitioner", "seniority": "individual_contributor",
                           "confidence": 0.5})
    return json.dumps({"persona": "data_leader", "seniority": "manager", "confidence": 0.9})


@respx.mock
def test_run_pipeline_uploads_and_reports(monkeypatch) -> None:
    monkeypatch.setenv("HUBSPOT_TOKEN", "tok")
    route = respx.post(UPSERT_URL).mock(return_value=httpx.Response(200, json={}))
    report = run_pipeline(SAMPLE, "Dell World 2026", llm=fake_llm)
    assert (report.total_rows, report.clean, report.uploaded) == (8, 4, 4)
    assert sorted(r["reason"] for r in report.rejected) == ["invalid_email", "personal_email"]
    assert [i.lead.last_name for i in report.senior_leads] == ["Kumar"]
    assert [i.lead.last_name for i in report.needs_review] == ["Tan"]
    assert route.call_count == 1


@respx.mock
def test_dry_run_pipeline_no_http() -> None:
    route = respx.post(UPSERT_URL).mock(return_value=httpx.Response(200))
    report = run_pipeline(SAMPLE, "E", dry_run=True, llm=fake_llm, hubspot=HubSpotClient("t"))
    assert report.uploaded == 0 and report.clean == 4 and route.call_count == 0


def test_markdown_summary() -> None:
    md = run_pipeline(SAMPLE, "Dell World 2026", dry_run=True, llm=fake_llm,
                      hubspot=HubSpotClient("t")).to_markdown()
    assert "Dell World 2026" in md and "dry run" in md
    assert "Total rows: 8" in md and "invalid_email" in md and "personal_email" in md
    assert "Ravi Kumar" in md


def test_cli_dry_run(monkeypatch, capsys) -> None:
    import event_leads.pipeline as p

    orig = p.run_pipeline
    monkeypatch.setattr(p, "run_pipeline", lambda *a, **k: orig(*a, llm=fake_llm, **k))
    assert main([SAMPLE, "--event", "Dell World 2026", "--dry-run"]) == 0
    assert "Lead report: Dell World 2026" in capsys.readouterr().out
