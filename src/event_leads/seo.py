
import json
import httpx
from bs4 import BeautifulSoup

def seo_audit(url: str) -> dict:
    """Check basic technical SEO for one page."""
    resp = httpx.get(url, timeout=15, follow_redirects=True,
                     headers={"User-Agent": "seo-audit-bot/0.1"})
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    title = soup.title.string.strip() if soup.title and soup.title.string else ""
    desc_tag = soup.find("meta", attrs={"name": "description"})
    desc = desc_tag.get("content", "").strip() if desc_tag else ""
    canonical = soup.find("link", rel="canonical")
    robots = soup.find("meta", attrs={"name": "robots"})
    h1s = [h.get_text(strip=True) for h in soup.find_all("h1")]

    jsonld_types = []
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
            items = data if isinstance(data, list) else [data]
            jsonld_types += [str(i.get("@type")) for i in items if isinstance(i, dict)]
        except json.JSONDecodeError:
            jsonld_types.append("INVALID_JSON")

    issues = []
    if not title: issues.append("missing title")
    elif len(title) > 60: issues.append("title longer than 60 chars")
    if not desc: issues.append("missing meta description")
    elif len(desc) > 160: issues.append("meta description longer than 160 chars")
    if len(h1s) != 1: issues.append(f"expected 1 H1, found {len(h1s)}")
    if not canonical: issues.append("missing canonical link")
    if robots and "noindex" in robots.get("content", "").lower(): issues.append("page is noindex")
    if not jsonld_types: issues.append("no structured data (JSON-LD)")
    if "INVALID_JSON" in jsonld_types: issues.append("invalid JSON-LD")
    missing_alt = sum(1 for img in soup.find_all("img") if not img.get("alt"))
    if missing_alt: issues.append(f"{missing_alt} images missing alt text")

    return {"url": url, "status": resp.status_code, "title": title,
            "meta_description": desc, "h1": h1s, "jsonld_types": jsonld_types,
            "issues": issues}