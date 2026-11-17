from dotenv import load_dotenv

load_dotenv()  # loads GEMINI_API_KEY from .env

from event_leads.clean import clean_leads, load_csv
from event_leads.enrich import enrich_leads  # use your real function name

result = clean_leads(load_csv("data/sample_event_leads.csv"))
for item in enrich_leads(result.leads):
    print(f"{item.lead.job_title!r:40} -> {item.enrichment.persona:16} {item.enrichment.seniority:22} "
          f"conf={item.enrichment.confidence:.2f} review={item.enrichment.needs_review}")
