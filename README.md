# event-lead-pipeline

Cleans, deduplicates, and LLM-enriches raw event lead CSVs (persona, seniority, company domain), then batch-upserts them to HubSpot and generates a sales-ready markdown report.
Exposed both as a CLI and as an MCP stdio server (`clean_event_leads`, `enrich_event_leads`, `upload_event_leads`).

<!-- Replace with your own recording/screenshot, e.g. ![Demo](docs/demo.gif) -->
> *Screenshot / GIF placeholder — add `docs/demo.gif` showing a CLI or MCP dry run.*

## Why

Event lead lists take days to clean by hand; this does it in minutes and is safe to rerun.

## Architecture

```
CSV ──▶ clean (clean.py) ──▶ enrich (enrich.py: Gemini + Pydantic) ──▶ HubSpot batch upsert (hubspot.py) ──▶ Report (pipeline.py)
                                                                                                                  ▲
                                                                                 MCP stdio server (server.py) ────┘
```

- [`src/event_leads/models.py`](src/event_leads/models.py) — Pydantic `Lead` model.
- [`src/event_leads/clean.py`](src/event_leads/clean.py) — `load_csv` & `clean_leads`: strips whitespace, lowercases emails, title-cases names, skips empty rows, rejects missing/invalid/personal emails (`gmail`, `yahoo`, `hotmail`, `outlook`), and deduplicates by email keeping the most complete row.
- [`src/event_leads/enrich.py`](src/event_leads/enrich.py) — `classify_title` & `enrich_leads`: classifies `job_title` via Gemini (`GEMINI_MODEL`, default `gemini-3.5-flash-lite`) into `Enrichment` (`persona`, `seniority`, `confidence`), derives `company_domain`, and sets `needs_review`.
- [`src/event_leads/hubspot.py`](src/event_leads/hubspot.py) — `HubSpotClient.batch_upsert_contacts`: sends chunks of up to 100 contacts to HubSpot's batch upsert endpoint.
- [`src/event_leads/pipeline.py`](src/event_leads/pipeline.py) — `run_pipeline` & CLI: orchestrates `clean → enrich → upsert` and builds `Report.to_markdown()`.
- [`src/event_leads/server.py`](src/event_leads/server.py) — FastMCP stdio server exposing `clean_event_leads`, `enrich_event_leads`, and `upload_event_leads`.

## Design Decisions

- **Idempotent upsert by email:** HubSpot batch upsert uses `idProperty: "email"`, and `None` fields are omitted from `properties` so reruns update contacts without blanking existing CRM values.
- **Exponential backoff with `Retry-After`:** HubSpot requests retry on `429` and `5xx` with `1, 2, 4, 8s` backoff (honouring the `Retry-After` header; other `4xx` errors log the response body and raise). Gemini requests retry on `429` and `5xx` with `2, 4, 8, 16, 32s` backoff.
- **Schema-validated LLM output + human review:** Responses are validated against the Pydantic `Enrichment` model (`Literal` types + `0–1` confidence). Invalid JSON triggers one retry before falling back to `other` / `unknown` / `0.0`, and any lead with `confidence < 0.7` is flagged `needs_review=True`.
- **`dry_run` on by default:** The MCP `upload_event_leads` tool defaults to `dry_run=True`, logging what would be sent without calling HubSpot unless explicitly disabled.
- **Secrets in env:** `GEMINI_API_KEY`, `GEMINI_MODEL`, and `HUBSPOT_TOKEN` are loaded from `.env` via `python-dotenv` and are never logged or committed.
- **All network calls mocked in tests:** Unit tests inject a fake `LlmFn` and mock `httpx` requests with `respx` (and patch `time.sleep`). Live Gemini tests in `tests/test_enrich_integration.py` skip automatically when `GEMINI_API_KEY` is unset.

## How to Run

### Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

Create `.env` in the project root:

```env
GEMINI_API_KEY=your-gemini-key
HUBSPOT_TOKEN=your-hubspot-private-app-token
# Optional:
# GEMINI_MODEL=gemini-3.5-flash-lite
```

### CLI

```powershell
# Dry run (cleans & enriches, makes no HubSpot writes)
python -m event_leads.pipeline data/sample_event_leads.csv --event "Dell World 2026" --dry-run

# Live upload to HubSpot
python -m event_leads.pipeline data/sample_event_leads.csv --event "Dell World 2026"
```

### MCP Server

Add to your MCP config (e.g. `~/.gemini/config/mcp_config.json`):

```json
{
  "mcpServers": {
    "event-leads": {
      "command": "E:\\H2O Project\\event-lead-pipeline\\event-lead-pipeline\\.venv\\Scripts\\python.exe",
      "args": ["-m", "event_leads.server"],
      "cwd": "E:\\H2O Project\\event-lead-pipeline\\event-lead-pipeline"
    }
  }
}
```

Exposed tools:
- `clean_event_leads(csv_path)` — returns counts and rejected rows with reasons (no network calls).
- `enrich_event_leads(csv_path)` — cleans and enriches leads via Gemini (no HubSpot writes).
- `upload_event_leads(csv_path, event_name, dry_run=True)` — runs the full pipeline and returns the markdown sales report.

### Tests & Lint

```powershell
ruff check .
pytest -q --deselect tests/test_enrich_integration.py
```

Cleans, deduplicates, and LLM-enriches raw event lead CSVs (persona, seniority, company domain), then batch-upserts them to HubSpot and generates a sales-ready markdown report.
Exposed both as a CLI and as an MCP stdio server (`clean_event_leads`, `enrich_event_leads`, `upload_event_leads`).

<!-- Replace with your own recording/screenshot, e.g. ![Demo](docs/demo.gif) -->
> *Screenshot / GIF placeholder — add `docs/demo.gif` showing a CLI or MCP dry run.*

## Why

Event lead lists take days to clean by hand; this does it in minutes and is safe to rerun.

## Architecture

```
CSV ──▶ clean (clean.py) ──▶ enrich (enrich.py: Gemini + Pydantic) ──▶ HubSpot batch upsert (hubspot.py) ──▶ Report (pipeline.py)
                                                                                                                  ▲
                                                                                 MCP stdio server (server.py) ────┘
```

- [`src/event_leads/models.py`](src/event_leads/models.py) — Pydantic `Lead` model.
- [`src/event_leads/clean.py`](src/event_leads/clean.py) — `load_csv` & `clean_leads`: strips whitespace, lowercases emails, title-cases names, skips empty rows, rejects missing/invalid/personal emails (`gmail`, `yahoo`, `hotmail`, `outlook`), and deduplicates by email keeping the most complete row.
- [`src/event_leads/enrich.py`](src/event_leads/enrich.py) — `classify_title` & `enrich_leads`: classifies `job_title` via Gemini (`GEMINI_MODEL`, default `gemini-3.5-flash-lite`) into `Enrichment` (`persona`, `seniority`, `confidence`), derives `company_domain`, and sets `needs_review`.
- [`src/event_leads/hubspot.py`](src/event_leads/hubspot.py) — `HubSpotClient.batch_upsert_contacts`: sends chunks of up to 100 contacts to HubSpot's batch upsert endpoint.
- [`src/event_leads/pipeline.py`](src/event_leads/pipeline.py) — `run_pipeline` & CLI: orchestrates `clean → enrich → upsert` and builds `Report.to_markdown()`.
- [`src/event_leads/server.py`](src/event_leads/server.py) — FastMCP stdio server exposing `clean_event_leads`, `enrich_event_leads`, and `upload_event_leads`.

## Design Decisions

- **Idempotent upsert by email:** HubSpot batch upsert uses `idProperty: "email"`, and `None` fields are omitted from `properties` so reruns update contacts without blanking existing CRM values.
- **Exponential backoff with `Retry-After`:** HubSpot requests retry on `429` and `5xx` with `1, 2, 4, 8s` backoff (honouring the `Retry-After` header; other `4xx` errors log the response body and raise). Gemini requests retry on `429` and `5xx` with `2, 4, 8, 16, 32s` backoff.
- **Schema-validated LLM output + human review:** Responses are validated against the Pydantic `Enrichment` model (`Literal` types + `0–1` confidence). Invalid JSON triggers one retry before falling back to `other` / `unknown` / `0.0`, and any lead with `confidence < 0.7` is flagged `needs_review=True`.
- **`dry_run` on by default:** The MCP `upload_event_leads` tool defaults to `dry_run=True`, logging what would be sent without calling HubSpot unless explicitly disabled.
- **Secrets in env:** `GEMINI_API_KEY`, `GEMINI_MODEL`, and `HUBSPOT_TOKEN` are loaded from `.env` via `python-dotenv` and are never logged or committed.
- **All network calls mocked in tests:** Unit tests inject a fake `LlmFn` and mock `httpx` requests with `respx` (and patch `time.sleep`). Live Gemini tests in `tests/test_enrich_integration.py` skip automatically when `GEMINI_API_KEY` is unset.

## How to Run

### Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

Create `.env` in the project root:

```env
GEMINI_API_KEY=your-gemini-key
HUBSPOT_TOKEN=your-hubspot-private-app-token
# Optional:
# GEMINI_MODEL=gemini-3.5-flash-lite
```

### CLI

```powershell
# Dry run (cleans & enriches, makes no HubSpot writes)
python -m event_leads.pipeline data/sample_event_leads.csv --event "Dell World 2026" --dry-run

# Live upload to HubSpot
python -m event_leads.pipeline data/sample_event_leads.csv --event "Dell World 2026"
```

### MCP Server

Add to your MCP config (e.g. `~/.gemini/config/mcp_config.json`):

```json
{
  "mcpServers": {
    "event-leads": {
      "command": "E:\\H2O Project\\event-lead-pipeline\\event-lead-pipeline\\.venv\\Scripts\\python.exe",
      "args": ["-m", "event_leads.server"],
      "cwd": "E:\\H2O Project\\event-lead-pipeline\\event-lead-pipeline"
    }
  }
}
```

Exposed tools:
- `clean_event_leads(csv_path)` — returns counts and rejected rows with reasons (no network calls).
- `enrich_event_leads(csv_path)` — cleans and enriches leads via Gemini (no HubSpot writes).
- `upload_event_leads(csv_path, event_name, dry_run=True)` — runs the full pipeline and returns the markdown sales report.

### Tests & Lint

```powershell
ruff check .
pytest -q --deselect tests/test_enrich_integration.py
```
