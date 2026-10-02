from __future__ import annotations

import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from .base import Collector, CollectorContext, CollectorResult
from .http_utils import fetch_scoped
from ..db import insert_source, upsert_asset
from ..normalize import normalize_domain, normalize_endpoint, normalize_url, parameter_names


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []
        self.title = ""
        self._in_title = False
        self.text: list[str] = []

    def handle_starttag(self, tag, attrs):
        attrs_map = dict(attrs)
        if tag.lower() == "a" and attrs_map.get("href"):
            self.links.append(attrs_map["href"])
        self._in_title = tag.lower() == "title"

    def handle_endtag(self, tag):
        if tag.lower() == "title":
            self._in_title = False

    def handle_data(self, data):
        self.text.append(data)
        if self._in_title:
            self.title += data


def _extract_urls(content: str, base_url: str) -> list[str]:
    parser = _LinkParser()
    parser.feed(content)
    candidates = parser.links + re.findall(r"https?://[^\s\"'<>]+", content)
    result: list[str] = []
    for candidate in candidates:
        url = normalize_url(urljoin(base_url, candidate.strip().rstrip(".,);")))
        if url.startswith(("http://", "https://")):
            result.append(url)
    return sorted(set(result))


class PassiveWebCollector(Collector):
    name = "passive_web"

    def collect(self, context: CollectorContext) -> CollectorResult:
        project = context.project
        official = project["official_website"]
        try:
            final_url, content_type, content = fetch_scoped(official, project["allowed_domains"], timeout=8, delay=context.request_delay)
        except Exception as exc:
            return CollectorResult(self.name, "error", f"official website fetch failed: {exc}")
        parser = _LinkParser()
        parser.feed(content)
        source_id = insert_source(context.db, project["id"], "website", "official website", final_url, parser.title.strip(), content, {"content_type": content_type})
        count = 0
        host = urlsplit(final_url).hostname or ""
        port = urlsplit(final_url).port or (443 if urlsplit(final_url).scheme == "https" else 80)
        upsert_asset(context.db, project["id"], "service", f"http|{host}|{port}", f"HTTP {host}:{port}", "confirmed", source_id, {"scheme": urlsplit(final_url).scheme, "port": port})
        upsert_asset(context.db, project["id"], "website", normalize_url(final_url), final_url, "confirmed", source_id, {"content_type": content_type})
        upsert_asset(context.db, project["id"], "host", normalize_domain(host), host, "discovered", source_id)
        count += 2
        for url in _extract_urls(content, final_url):
            endpoint = normalize_endpoint(url)
            upsert_asset(context.db, project["id"], "endpoint", endpoint, url, "discovered", source_id, {"parameter_names": parameter_names(url)})
            for name in parameter_names(url):
                upsert_asset(context.db, project["id"], "parameter", name.casefold(), name, "discovered", source_id, {"endpoint": endpoint})
            link_host = urlsplit(url).hostname or ""
            if link_host:
                status = "related" if link_host.casefold().endswith(tuple("." + d for d in project["allowed_domains"])) or link_host.casefold() in project["allowed_domains"] else "needs_review"
                upsert_asset(context.db, project["id"], "host", normalize_domain(link_host), link_host, status, source_id)
            count += 1
        # A sitemap URL is recorded as a candidate; it is not fetched in passive mode.
        sitemap = urljoin(final_url, "/sitemap.xml")
        upsert_asset(context.db, project["id"], "endpoint", normalize_endpoint(sitemap), sitemap, "discovered", source_id, {"kind": "sitemap_candidate"})
        return CollectorResult(self.name, "ok", "official website parsed", count + 1, {"source_id": source_id})
