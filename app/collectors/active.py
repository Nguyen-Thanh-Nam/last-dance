from __future__ import annotations

from collections import deque
from time import monotonic, sleep
from urllib.parse import urljoin, urlsplit

from .base import Collector, CollectorContext, CollectorResult
from .http_utils import fetch_scoped
from .passive import _LinkParser, _extract_urls
from ..db import insert_source, upsert_asset
from ..normalize import normalize_endpoint, normalize_url, parameter_names
from ..scope import is_host_allowed


class AuthorizedHttpCollector:
    name = "authorized_http"

    def collect(self, context: CollectorContext) -> CollectorResult:
        if context.project["mode"] != "authorized":
            return CollectorResult(self.name, "skipped", "project is passive; authorized collector was not run")
        queue = deque([(context.project["official_website"], 0)])
        visited: set[str] = set()
        count = 0
        started = monotonic()
        while queue and len(visited) < context.max_pages:
            url, depth = queue.popleft()
            url = normalize_url(url)
            if url in visited or depth > context.max_depth:
                continue
            visited.add(url)
            try:
                final_url, content_type, content = fetch_scoped(url, context.project["allowed_domains"], timeout=8, delay=context.request_delay)
            except Exception:
                continue
            source_id = insert_source(context.db, context.project["id"], "authorized_http", "authorized crawl", final_url, raw_content=content, metadata={"depth": depth, "content_type": content_type})
            upsert_asset(context.db, context.project["id"], "website", final_url, final_url, "confirmed", source_id, {"http_checked": True, "depth": depth})
            count += 1
            for link in _extract_urls(content, final_url):
                link_host = urlsplit(link).hostname or ""
                if not is_host_allowed(link_host, context.project["allowed_domains"]):
                    continue
                endpoint = normalize_endpoint(link)
                upsert_asset(context.db, context.project["id"], "endpoint", endpoint, link, "discovered", source_id, {"parameter_names": parameter_names(link), "crawl_depth": depth})
                for name in parameter_names(link):
                    upsert_asset(context.db, context.project["id"], "parameter", name.casefold(), name, "discovered", source_id, {"endpoint": endpoint})
                if depth + 1 <= context.max_depth and link not in visited:
                    queue.append((link, depth + 1))
            if context.request_delay:
                sleep(context.request_delay)
        elapsed = int((monotonic() - started) * 1000)
        return CollectorResult(self.name, "ok", f"crawled {len(visited)} pages in {elapsed} ms", count)
