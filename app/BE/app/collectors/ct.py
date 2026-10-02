from __future__ import annotations

import json
from urllib.parse import quote
from urllib.request import Request, urlopen

from .base import Collector, CollectorContext, CollectorResult
from .http_utils import fetch_scoped
from ..db import insert_source, upsert_asset, insert_evidence, insert_relationship
from ..normalize import normalize_domain


class CertificateTransparencyCollector(Collector):
    """Passive crt.sh lookup. CT names are candidates, never ownership proof."""

    name = "certificate_transparency"

    def collect(self, context: CollectorContext) -> CollectorResult:
        domain = normalize_domain(context.project["root_domain"])
        url = f"https://crt.sh/?q=%25.{quote(domain)}&output=json"
        try:
            _, _, raw = fetch_scoped(url, ["crt.sh"], timeout=12, max_bytes=1_500_000)
            records = json.loads(raw)
            if not isinstance(records, list):
                raise ValueError("CT response must be an array")
        except Exception as exc:
            return CollectorResult(self.name, "error", f"CT lookup failed: {exc}")
        source_id = insert_source(context.db, context.project["id"], "certificate_transparency", "crt.sh", url, raw_content=raw, metadata={"query_domain": domain, "record_count": len(records)})
        count = 0
        for record in records[:250]:
            cert_value = str(record.get("id") or __import__("hashlib").sha256(json.dumps(record, sort_keys=True).encode()).hexdigest())
            cert_id = upsert_asset(context.db, context.project["id"], "certificate", "ct:" + cert_value, "CT certificate " + cert_value, "discovered", source_id, record)
            evidence_id = insert_evidence(context.db, context.project["id"], source_id, json.dumps(record), "ct-record:" + cert_value, 0.65)
            for value in str(record.get("name_value", "")).splitlines():
                candidate = normalize_domain(value)
                if not candidate:
                    continue
                status = "discovered" if candidate in context.project["allowed_domains"] or candidate.endswith("." + domain) else "needs_review"
                asset_id = upsert_asset(context.db, context.project["id"], "wildcard" if candidate.startswith("*.") else "host", candidate, candidate, status, source_id, {"method": "certificate_transparency", "issuer": record.get("issuer_name"), "not_before": record.get("not_before"), "not_after": record.get("not_after")})
                insert_relationship(context.db, context.project["id"], "asset", cert_id, "certificate_contains", "asset", asset_id, "related", 0.65, "Historical CT SAN does not establish current availability or ownership.", evidence_id)
                count += 1
        return CollectorResult(self.name, "ok", f"collected {count} CT host candidates", count, {"source_id": source_id})
