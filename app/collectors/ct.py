from __future__ import annotations

import json
from urllib.parse import quote
from urllib.request import Request, urlopen

from .base import Collector, CollectorContext, CollectorResult
from ..db import insert_source, upsert_asset
from ..normalize import normalize_domain


class CertificateTransparencyCollector(Collector):
    """Passive crt.sh lookup. CT names are candidates, never ownership proof."""

    name = "certificate_transparency"

    def collect(self, context: CollectorContext) -> CollectorResult:
        domain = normalize_domain(context.project["root_domain"])
        url = f"https://crt.sh/?q=%25.{quote(domain)}&output=json"
        try:
            request = Request(url, headers={"User-Agent": "SurfaceMapResearch/0.1"})
            with urlopen(request, timeout=12) as response:
                raw = response.read(1_500_000).decode("utf-8", errors="replace")
            records = json.loads(raw)
        except Exception as exc:
            return CollectorResult(self.name, "error", f"CT lookup failed: {exc}")
        source_id = insert_source(context.db, context.project["id"], "certificate_transparency", "crt.sh", url, raw_content=raw, metadata={"query_domain": domain, "record_count": len(records)})
        count = 0
        for record in records[:250]:
            for value in str(record.get("name_value", "")).splitlines():
                candidate = normalize_domain(value)
                if not candidate or candidate.startswith("*") or candidate == domain:
                    continue
                status = "discovered" if candidate in context.project["allowed_domains"] or candidate.endswith("." + domain) else "needs_review"
                upsert_asset(context.db, context.project["id"], "host", candidate, candidate, status, source_id, {"method": "certificate_transparency", "issuer": record.get("issuer_name"), "not_before": record.get("not_before"), "not_after": record.get("not_after")})
                count += 1
        return CollectorResult(self.name, "ok", f"collected {count} CT host candidates", count, {"source_id": source_id})
