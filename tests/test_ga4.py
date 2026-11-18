from types import SimpleNamespace

import pytest

from event_leads import ga4


def _fake_row(page: str, sessions: str, rate: str, events: str) -> SimpleNamespace:
    return SimpleNamespace(
        dimension_values=[SimpleNamespace(value=page)],
        metric_values=[
            SimpleNamespace(value=sessions),
            SimpleNamespace(value=rate),
            SimpleNamespace(value=events),
        ],
    )


class _FakeClient:
    def __init__(self, rows: list[SimpleNamespace]) -> None:
        self.rows = rows
        self.requests: list = []

    def run_report(self, req) -> SimpleNamespace:
        self.requests.append(req)
        return SimpleNamespace(rows=self.rows)


def test_ga4_page_traffic_parses_rows(monkeypatch) -> None:
    monkeypatch.setenv("GA4_PROPERTY_ID", "12345")
    client = _FakeClient([_fake_row("/pricing", "42", "0.65", "3")])
    rows = ga4.ga4_page_traffic(start_date="7daysAgo", end_date="today", limit=5, client=client)
    assert rows == [
        {"page": "/pricing", "sessions": 42, "engagement_rate": 0.65, "key_events": 3.0}
    ]
    assert client.requests[0].property == "properties/12345"
    assert client.requests[0].limit == 5


def test_build_ga4_client_uses_service_account_file(monkeypatch, tmp_path) -> None:
    creds = tmp_path / "creds.json"
    creds.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(creds))

    called: list[str] = []
    monkeypatch.setattr(
        ga4.BetaAnalyticsDataClient,
        "from_service_account_file",
        staticmethod(lambda path: called.append(path) or "FAKE_CLIENT"),
    )
    assert ga4.build_ga4_client() == "FAKE_CLIENT"
    assert called == [str(creds)]


def test_build_ga4_client_missing_file_raises(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(tmp_path / "missing.json"))
    with pytest.raises(FileNotFoundError, match="GA4 credentials file not found"):
        ga4.build_ga4_client()
