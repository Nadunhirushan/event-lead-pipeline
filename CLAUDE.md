# Event Lead Pipeline
Python 3.11+. Package in src/event_leads. Tests in tests/ with pytest.
Rules:
- Type hints everywhere. Pydantic v2 for data models.
- Use httpx for HTTP. Never print secrets. Read keys from env via python-dotenv.
- Use the logging module, not print.
- Every new function gets a pytest test. Mock all network calls (respx for httpx).
- Keep functions small and pure where possible.