from __future__ import annotations

import re
import html
from urllib.parse import urlsplit
from typing import Any

from ..normalize import normalize_name, normalize_endpoint, normalize_url
from ..schemas import ModelOutput, ModelRelationship


class RuleBasedAdapter:
    name = "rules-demo"

    def analyze(self, project: dict[str, Any], sources: list[dict[str, Any]], assets: list[dict[str, Any]]) -> ModelOutput:
        entities: list[dict[str, Any]] = [{"entity_type": "organization", "name": project["organization_name"], "source_id": None}]
        relationships: list[ModelRelationship] = []
        assets_by_source: dict[str, list[dict[str, Any]]] = {}
        for asset in assets:
            if asset.get("source_id"):
                assets_by_source.setdefault(asset["source_id"], []).append(asset)
        for source in sources:
            text = source.get("raw_content", "")
            if not text:
                continue
            products = _labels_after(text, r"(?:product|san pham)\s*[:\-]\s*([A-Z][A-Za-z0-9][A-Za-z0-9 &.\-]{1,70})")
            projects = _labels_after(text, r"(?:project|du an)\s*[:\-]\s*([A-Z][A-Za-z0-9][A-Za-z0-9 &.\-]{1,70})")
            for name in products:
                entities.append({"entity_type": "product", "name": name, "source_id": source["id"]})
                for asset in assets_by_source.get(source["id"], []):
                    if asset["asset_type"] in {"website", "endpoint", "host"}:
                        quote = _supported_product_link(text, name, asset)
                        if quote:
                            relationships.append(ModelRelationship(
                                subject_type="entity", subject_ref=f"candidate:product:{normalize_name(name)}", predicate="PRODUCT_USES_WEBSITE", relation_class="used", object_type="asset", object_ref=f"asset:{asset['id']}", evidence_source_id=source["id"], evidence_quote=quote, rationale="The same source names the product and links the technical asset; this supports use/linkage, not ownership.", confidence=0.88,
                            ))
            for name in projects:
                entities.append({"entity_type": "project", "name": name, "source_id": source["id"]})
            if source.get("source_url"):
                entities.append({"entity_type": "website", "name": source.get("title") or source["source_url"], "source_id": source["id"]})
        return ModelOutput(entities=entities, relationships=relationships, explanation="Rule-based extraction for offline demo; results are labeled as demo AI and remain evidence constrained.")


def _labels_after(text: str, pattern: str) -> list[str]:
    values: list[str] = []
    for match in re.finditer(pattern, text, flags=re.IGNORECASE):
        value = re.sub(r"\s+", " ", match.group(1)).strip(" .,:;\n\r\t")
        value = re.split(r"\s+(?:helps|is|uses|provides)\b|[.!?]", value, maxsplit=1, flags=re.IGNORECASE)[0].strip()
        if 2 < len(value) < 100 and normalize_name(value) not in {normalize_name(v) for v in values}:
            values.append(value)
    return values


def _quote(text: str, *terms: str) -> str:
    lower = text.casefold()
    positions = [lower.find(term.casefold()) for term in terms]
    if any(position < 0 for position in positions):
        return ""
    start = max(0, min(positions) - 100)
    end = min(len(text), max(positions) + max(map(len, terms)) + 120)
    return re.sub(r"\s+", " ", text[start:end]).strip()


def _supported_product_link(text: str, product: str, asset: dict) -> str:
    links = re.findall(r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', text, flags=re.I | re.S)
    urls = [html.unescape(url) for url, label in links if normalize_name(product) in normalize_name(re.sub('<[^>]+>', '', label))]
    if not links:
        candidates = re.findall(r'https?://[^\s"\'<>]+', text)
        if len(candidates) == 1 and normalize_name(product) in normalize_name(text):
            urls = [candidates[0].rstrip('.,);')]
    for url in urls:
        try:
            matched = ((asset['asset_type'] == 'host' and urlsplit(url).hostname == asset['canonical_value'])
                       or (asset['asset_type'] == 'endpoint' and normalize_endpoint(url) == asset['canonical_value'])
                       or (asset['asset_type'] == 'website' and normalize_url(url) == asset['canonical_value']))
            if matched:
                return _quote(text, product, url)
        except ValueError:
            continue
    return ''
