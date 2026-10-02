from __future__ import annotations

import json
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from .base import Collector, CollectorContext, CollectorResult
from ..config import settings
from ..db import insert_evidence, insert_source, upsert_asset
from ..normalize import normalize_domain, normalize_endpoint
from ..scope import is_host_allowed


def dork_queries(domain: str) -> list[str]:
    """Return a small set of public, domain-scoped discovery queries."""
    root = normalize_domain(domain).removeprefix("*.")
    return [
        f"site:{root} filetype:pdf",
        f"site:{root} (inurl:about OR inurl:contact OR inurl:news)",
        f"site:{root} (inurl:api OR inurl:docs OR inurl:developer)",
        f"site:{root} (filetype:doc OR filetype:docx OR filetype:ppt OR filetype:pptx)",
    ]


def google_search_url(query: str) -> str:
    return "https://www.google.com/search?" + urlencode({"q": query})


class GoogleDorkCollector(Collector):
    """Run bounded, domain-scoped Google Dorks via an existing CSE JSON API."""

    name = "google_dork"

    def collect(self, context: CollectorContext) -> CollectorResult:
        # Query only the same host/domain the setup form placed in the allowlist.
        query_domain = context.project["allowed_domains"][0]
        queries = dork_queries(query_domain)
        if not (settings.google_cse_api_key and settings.google_cse_id):
            links = [{"query": query, "url": google_search_url(query)} for query in queries]
            message = (
                "Google search API is not configured. Open a domain-scoped Dork manually, or configure an existing "
                "Google Custom Search JSON API key and engine ID. GOOGLE_DORK_LINKS:" + json.dumps(links)
            )
            return CollectorResult(self.name, "skipped", message, 0)

        errors: list[str] = []
        records = 0
        successful_queries = 0
        for query in queries:
            params = urlencode({"key": settings.google_cse_api_key, "cx": settings.google_cse_id, "q": query, "num": 5})
            request = Request(
                f"https://www.googleapis.com/customsearch/v1?{params}",
                headers={"Accept": "application/json", "User-Agent": "SurfaceMapResearch/0.2"},
            )
            try:
                with urlopen(request, timeout=12) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                items = payload.get("items", [])
                if not isinstance(items, list):
                    raise ValueError("Google CSE items must be an array")
            except Exception as exc:
                detail = str(exc).replace(settings.google_cse_api_key, "[redacted]") if settings.google_cse_api_key else str(exc)
                errors.append(f"{query}: {type(exc).__name__}: {detail}")
                continue

            allowed_items = []
            for item in items[:5]:
                link = str(item.get("link", ""))
                host = (urlsplit(link).hostname or "").casefold()
                if not link.startswith(("https://", "http://")) or not is_host_allowed(host, context.project["allowed_domains"]):
                    continue
                allowed_items.append({
                    "title": str(item.get("title", ""))[:500],
                    "link": link,
                    "snippet": str(item.get("snippet", ""))[:2000],
                })

            successful_queries += 1
            content = json.dumps({"query": query, "items": allowed_items}, ensure_ascii=False)
            source_id = insert_source(
                context.db,
                context.project["id"],
                "google_dork",
                "Google Dork: " + query,
                google_search_url(query),
                raw_content=content,
                metadata={"query": query, "result_count": len(allowed_items), "search_provider": "Google Custom Search JSON API"},
            )
            for item in allowed_items:
                link = item["link"]
                host = (urlsplit(link).hostname or "").casefold()
                upsert_asset(
                    context.db, context.project["id"], "endpoint", normalize_endpoint(link), link,
                    "discovered", source_id, {"method": "google_dork", "query": query},
                )
                upsert_asset(
                    context.db, context.project["id"], "host", normalize_domain(host), host,
                    "discovered", source_id, {"method": "google_dork"},
                )
                if item["snippet"]:
                    insert_evidence(context.db, context.project["id"], source_id, item["snippet"], "Google search snippet", 0.55)
                records += 1

        if successful_queries == 0:
            return CollectorResult(self.name, "error", "Google Dork search failed: " + "; ".join(errors), 0)
        if errors:
            return CollectorResult(self.name, "error", f"{records} in-scope results; some queries failed: " + "; ".join(errors), records)
        return CollectorResult(self.name, "ok", f"Google Dork searched {successful_queries} queries; {records} in-scope results", records)
