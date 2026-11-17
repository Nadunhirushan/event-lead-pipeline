import json

import httpx
import respx

from event_leads.enrich import (
    call_gemini,
    classify_title,
    domain_from_email,
    enrich_lead,
    enrich_leads,
)
from event_leads.models import Lead

GOOD = json.dumps({"persona": "data_leader", "seniority": "director", "confidence": 0.9})
LOW = json.dumps({"persona": "other", "seniority": "unknown", "confidence": 0.4})


class FakeLlm:
    def __init__(self, *responses: str) -> None:
        self.responses = list(responses)
        self.calls = 0

    def __call__(self, prompt: str) -> str:
        self.calls += 1
        return self.responses.pop(0)


def lead(title: str | None = "Head of Data") -> Lead:
    return Lead(email="a@acme.example", job_title=title)


def test_valid_json() -> None:
    llm = FakeLlm(GOOD)
    e = enrich_lead(lead(), llm).enrichment
    assert (e.persona, e.seniority, e.confidence) == ("data_leader", "director", 0.9)
    assert not e.needs_review
    assert e.company_domain == "acme.example"
    assert llm.calls == 1


def test_invalid_then_valid_retries_once() -> None:
    llm = FakeLlm("not json", GOOD)
    assert enrich_lead(lead(), llm).enrichment.persona == "data_leader"
    assert llm.calls == 2


def test_invalid_twice_falls_back() -> None:
    llm = FakeLlm("nope", '{"persona": "wizard", "seniority": "vp", "confidence": 1}')
    e = enrich_lead(lead(), llm).enrichment
    assert (e.persona, e.seniority, e.confidence) == ("other", "unknown", 0.0)
    assert e.needs_review
    assert llm.calls == 2


def test_low_confidence_needs_review() -> None:
    assert enrich_lead(lead(), FakeLlm(LOW)).enrichment.needs_review


def test_confidence_out_of_range_is_invalid() -> None:
    bad = json.dumps({"persona": "other", "seniority": "vp", "confidence": 1.5})
    assert classify_title("x", FakeLlm(bad, GOOD)).persona == "data_leader"


def test_code_fenced_json_accepted() -> None:
    assert classify_title("x", FakeLlm(f"```json\n{GOOD}\n```")).seniority == "director"


def test_missing_title_skips_llm() -> None:
    llm = FakeLlm()
    e = enrich_lead(lead(None), llm).enrichment
    assert llm.calls == 0 and e.needs_review and e.persona == "other"


def test_domain_from_email() -> None:
    assert domain_from_email("X@Foo.Com") == "foo.com"
    assert domain_from_email("nodomain") is None


def test_enrich_leads_batch() -> None:
    result = enrich_leads([lead(), lead("Analyst")], FakeLlm(GOOD, LOW))
    assert [r.enrichment.needs_review for r in result] == [False, True]


@respx.mock
def test_call_gemini_uses_env(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("GEMINI_MODEL", "my-model")
    route = respx.post(
        "https://generativelanguage.googleapis.com/v1beta/models/my-model:generateContent"
    ).mock(
        return_value=httpx.Response(
            200, json={"candidates": [{"content": {"parts": [{"text": GOOD}]}}]}
        )
    )
    assert call_gemini("hi") == GOOD
    assert route.calls[0].request.headers["x-goog-api-key"] == "test-key"


@respx.mock
def test_call_gemini_retries_on_429(monkeypatch) -> None:
    from event_leads import enrich

    sleeps: list[float] = []
    monkeypatch.setattr(enrich.time, "sleep", sleeps.append)
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    route = respx.post(url__regex=r"https://generativelanguage\.googleapis\.com/.*").mock(
        side_effect=[
            httpx.Response(429),
            httpx.Response(503),
            httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": GOOD}]}}]}),
        ]
    )
    assert call_gemini("hi") == GOOD
    assert route.call_count == 3 and sleeps == [2, 4]
