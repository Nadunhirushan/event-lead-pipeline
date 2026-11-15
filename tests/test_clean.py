from pathlib import Path

from event_leads.clean import clean_leads, load_csv

SAMPLE = Path(__file__).parent.parent / "data" / "sample_event_leads.csv"


def test_load_csv_reads_all_rows() -> None:
    assert len(load_csv(SAMPLE)) == 8


def test_sample_file() -> None:
    result = clean_leads(load_csv(SAMPLE))
    assert len(result.leads) == 4
    assert sorted(r["reason"] for r in result.rejected) == ["invalid_email", "personal_email"]


def test_normalisation_and_dedupe_keeps_fullest() -> None:
    result = clean_leads(load_csv(SAMPLE))
    priya = [l for l in result.leads if l.email == "priya.sharma@acmebank.example"]
    assert len(priya) == 1
    assert priya[0].first_name == "Priya" and priya[0].last_name == "Sharma"
    assert priya[0].phone == "+65 9123 4567"


def test_missing_email_and_empty_rows() -> None:
    rows = [{"first_name": "a", "email": ""}, {"first_name": " ", "email": ""}]
    result = clean_leads(rows)
    assert result.leads == []
    assert [r["reason"] for r in result.rejected] == ["missing_email"]
