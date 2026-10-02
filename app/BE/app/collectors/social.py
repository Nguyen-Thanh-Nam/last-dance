from __future__ import annotations

import re
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import urlsplit

from .base import Collector, CollectorContext, CollectorResult
from .passive import _extract_urls
from .http_utils import fetch_scoped
from ..db import insert_evidence, insert_relationship, insert_social_post, insert_source, upsert_asset, upsert_entity, upsert_social_account
from ..normalize import normalize_domain, normalize_endpoint, normalize_name, normalize_url, parameter_names
from ..scope import is_host_allowed


PLATFORM_HOSTS = {
    "facebook": {"facebook.com", "www.facebook.com", "m.facebook.com"},
    "linkedin": {"linkedin.com", "www.linkedin.com"},
    "youtube": {"youtube.com", "www.youtube.com", "youtu.be"},
    "github": {"github.com", "www.github.com"},
    "instagram": {"instagram.com", "www.instagram.com"},
    "tiktok": {"tiktok.com", "www.tiktok.com"},
    "x": {"x.com", "twitter.com"},
    "threads": {"threads.net"},
    "reddit": {"reddit.com", "www.reddit.com"},
    "telegram": {"t.me", "telegram.me"},
    "discord": {"discord.com", "discord.gg"},
    "zalo": {"zalo.me", "oa.zalo.me"},
    "medium": {"medium.com", "www.medium.com"},
}
MANUAL_ONLY = {"facebook", "linkedin", "instagram", "tiktok", "x", "threads", "reddit", "telegram", "discord", "zalo"}


class SocialOSINTCollector(Collector):
    name = "social_osint"

    def collect(self, context: CollectorContext) -> CollectorResult:
        accounts = list(context.project.get("known_social_accounts", []))
        seen = {normalize_url(record["url"]) for record in accounts}
        discovered = 0
        for source in context.db.execute("SELECT source_url,raw_content FROM sources WHERE project_id=? AND source_type IN ('website','authorized_http') ORDER BY collected_at DESC", (context.project["id"],)):
            if not is_host_allowed(urlsplit(source["source_url"] or "").hostname or "", context.project["allowed_domains"]):
                continue
            for url in _extract_urls(source["raw_content"], source["source_url"]):
                platform = _platform_from_url(url)
                path = urlsplit(url).path.strip("/").casefold().split("/")
                excluded = {"share", "sharer", "sharer.php", "intent", "login", "signin", "dialog", "l.php", "watch", "embed", "status", "p", "reel", "reels", "hashtag"}
                if platform == "unknown" or not path[0] or excluded.intersection(path) or url in seen or discovered >= 20:
                    continue
                accounts.append({"url": url, "platform": platform})
                seen.add(url)
                discovered += 1
        if not accounts:
            return CollectorResult(self.name, "skipped", "no social profile links found in saved website sources")
        total = 0
        errors: list[str] = []
        for record in accounts:
            try:
                total += self._collect_account(context, record)
            except Exception as exc:
                errors.append(f"{record.get('url', '')}: {exc}")
        if errors and total == 0:
            return CollectorResult(self.name, "error", "; ".join(errors))
        message = f"social records collected; {discovered} profile links discovered from website snapshots"
        return CollectorResult(self.name, "ok", "; ".join(errors) if errors else message, total)

    def _collect_account(self, context: CollectorContext, record: dict[str, Any]) -> int:
        profile_url = str(record.get("url", "")).strip()
        if not profile_url:
            raise ValueError("missing profile URL")
        platform = str(record.get("platform") or _platform_from_url(profile_url)).casefold()
        if platform not in PLATFORM_HOSTS:
            raise ValueError(f"unsupported platform: {platform}")
        host = (urlsplit(profile_url).hostname or "").lower()
        if host not in PLATFORM_HOSTS[platform]:
            raise ValueError("profile URL host does not match declared platform")
        manual_text = str(record.get("verification_evidence") or record.get("content") or "").strip()
        source_type = "social_manual" if manual_text or platform in MANUAL_ONLY else "social_public"
        source_url = profile_url
        page_content = manual_text
        title = f"{platform} profile"
        if not page_content and platform not in MANUAL_ONLY:
            try:
                source_url, _, page_content = fetch_scoped(profile_url, list(PLATFORM_HOSTS[platform]), timeout=10)
                title_match = re.search(r"<title[^>]*>(.*?)</title>", page_content, flags=re.IGNORECASE | re.DOTALL)
                title = re.sub(r"\s+", " ", title_match.group(1)).strip() if title_match else title
            except (HTTPError, URLError, OSError, ValueError) as exc:
                page_content = f"Public fetch failed: {exc}. Manual export is supported."
                source_type = "social_manual"
        source_id = insert_source(context.db, context.project["id"], source_type, f"{platform} profile", source_url, title, page_content, {"platform": platform, "collection_mode": "manual" if source_type == "social_manual" else "public_page"})
        official_source = None
        for candidate in context.db.execute("SELECT * FROM sources WHERE project_id=? AND source_type IN ('website','authorized_http','demo_fixture')", (context.project["id"],)):
            candidate_host = urlsplit(candidate["source_url"] or "").hostname or ""
            if is_host_allowed(candidate_host, context.project["allowed_domains"]) and normalize_url(profile_url) in _extract_urls(candidate["raw_content"], candidate["source_url"]):
                official_source = candidate
                break
        official_evidence = official_source is not None
        verification_status = "confirmed" if official_evidence else "needs_review"
        reason = "official website backlink or explicit verification evidence" if official_evidence else ("platform page captured; backlink/ownership evidence is missing" if source_type == "social_public" else "manual record requires reviewer verification")
        account_id = upsert_social_account(context.db, context.project["id"], platform, str(record.get("handle", "")), profile_url, verification_status, reason, source_id)
        organization_id = upsert_entity(context.db, context.project["id"], "organization", normalize_name(context.project["organization_name"]), context.project["organization_name"], source_id=source_id)
        if official_evidence or manual_text:
            proof_source = official_source["id"] if official_evidence else source_id
            quote = _first_evidence(official_source["raw_content"], profile_url) if official_evidence else manual_text[:500]
            evidence_id = insert_evidence(context.db, context.project["id"], proof_source, quote, "official-snapshot-backlink" if official_evidence else "manual-assertion", 0.92 if official_evidence else 0.5)
            insert_relationship(context.db, context.project["id"], "entity", organization_id, "OFFICIAL_SOCIAL_ACCOUNT", "social_account", account_id, "confirmed" if official_evidence else "needs_review", 0.92 if official_evidence else 0.5, reason, evidence_id, "used")
        total = 1
        posts = record.get("posts", [])
        for post in posts:
            permalink = str(post.get("permalink", "")).strip()
            if not permalink:
                continue
            content = str(post.get("content", ""))
            post_source_id = insert_source(context.db, context.project["id"], "social_post", f"{platform} public post", permalink, raw_content=content, metadata={"platform": platform, "published_at": post.get("published_at")})
            post_id = insert_social_post(context.db, context.project["id"], account_id, permalink, content, post.get("published_at"), post_source_id)
            for url in _extract_urls(content, permalink):
                endpoint = normalize_endpoint(url)
                endpoint_id = upsert_asset(context.db, context.project["id"], "endpoint", endpoint, url, "discovered", post_source_id, {"method": "social_post", "parameter_names": parameter_names(url)})
                host_name = urlsplit(url).hostname or ""
                if host_name:
                    host_id = upsert_asset(context.db, context.project["id"], "host", normalize_domain(host_name), host_name, "related" if host_name.endswith("." + context.project["root_domain"]) else "needs_review", post_source_id, {"method": "social_post"})
                    if "product" in content.casefold():
                        product_name = _product_name(content)
                        if product_name:
                            product_id = upsert_entity(context.db, context.project["id"], "product", normalize_name(product_name), product_name, "discovered", post_source_id)
                            quote = _first_evidence(content, host_name)
                            evidence_id = insert_evidence(context.db, context.project["id"], post_source_id, quote, "social-post", 0.82)
                            insert_relationship(context.db, context.project["id"], "social_post", post_id, "POST_MENTIONS_PRODUCT", "entity", product_id, "related", 0.82, "A public post names the product; this does not prove ownership of linked infrastructure.", evidence_id, "mentioned")
                            insert_relationship(context.db, context.project["id"], "social_post", post_id, "POST_LINKS_TO_ENDPOINT", "asset", endpoint_id, "related", 0.82, "The public post links this endpoint; ownership remains a separate claim.", evidence_id, "mentioned")
                total += 1
        return total


def _platform_from_url(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower()
    for platform, hosts in PLATFORM_HOSTS.items():
        if host in hosts:
            return platform
    return "unknown"


def _is_official_evidence(project: dict[str, Any], *texts: str) -> bool:
    domain = project["root_domain"].casefold()
    return any(domain in text.casefold() and ("official" in text.casefold() or "official website" in text.casefold() or "links" in text.casefold() or "link" in text.casefold()) for text in texts if text)


def _first_evidence(text: str, term: str) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    index = compact.casefold().find(term.casefold())
    return compact[max(0, index - 100): index + len(term) + 180] if index >= 0 else compact[:500]


def _product_name(content: str) -> str | None:
    match = re.search(r"product\s*[:\-]\s*([A-Z][A-Za-z0-9 &.\-]{2,70}?)(?:\s+helps|\s+is|[.!?])", content, flags=re.IGNORECASE)
    return match.group(1).strip() if match else None
