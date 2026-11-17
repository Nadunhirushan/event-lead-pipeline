import os
import pytest
from dotenv import load_dotenv

load_dotenv()

pytestmark = pytest.mark.skipif(
    not os.getenv("GEMINI_API_KEY"), reason="needs real API key"
)

CASES = [
    ("Head of Data & Analytics", "data_leader"),
    ("ML Engineer", "ml_practitioner"),
    ("VP Risk Analytics", "risk_leader"),
]

@pytest.mark.parametrize("title,expected_persona", CASES)
def test_real_enrichment(title, expected_persona):
    from event_leads.enrich import classify_title
    result = classify_title(title)
    assert result.persona == expected_persona
