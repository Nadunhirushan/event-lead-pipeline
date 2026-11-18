"""Google Analytics 4 (GA4) Data API helpers."""
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import (
    DateRange,
    Dimension,
    Metric,
    OrderBy,
    RunReportRequest,
)

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _resolve_credentials_path() -> Path:
    load_dotenv()
    raw = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "credentials.json")
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def build_ga4_client() -> BetaAnalyticsDataClient:
    """Create a GA4 client from GOOGLE_APPLICATION_CREDENTIALS or credentials.json."""
    creds_path = _resolve_credentials_path()
    if not creds_path.is_file():
        raise FileNotFoundError(f"GA4 credentials file not found: {creds_path}")
    return BetaAnalyticsDataClient.from_service_account_file(str(creds_path))


def ga4_page_traffic(
    start_date: str = "28daysAgo",
    end_date: str = "today",
    limit: int = 20,
    client: BetaAnalyticsDataClient | None = None,
) -> list[dict]:
    """Sessions, engagement rate and key events per page from GA4."""
    load_dotenv()
    ga4 = client or build_ga4_client()
    property_id = os.environ["GA4_PROPERTY_ID"]
    req = RunReportRequest(
        property=f"properties/{property_id}",
        dimensions=[Dimension(name="pagePath")],
        metrics=[
            Metric(name="sessions"),
            Metric(name="engagementRate"),
            Metric(name="keyEvents"),
        ],
        date_ranges=[DateRange(start_date=start_date, end_date=end_date)],
        order_bys=[OrderBy(metric=OrderBy.MetricOrderBy(metric_name="sessions"), desc=True)],
        limit=limit,
    )
    resp = ga4.run_report(req)
    rows = [
        {
            "page": r.dimension_values[0].value,
            "sessions": int(r.metric_values[0].value),
            "engagement_rate": float(r.metric_values[1].value),
            "key_events": float(r.metric_values[2].value),
        }
        for r in resp.rows
    ]
    logger.info("fetched %d GA4 page rows for property %s", len(rows), property_id)
    return rows
