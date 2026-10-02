from __future__ import annotations

import ipaddress
import json
from urllib.request import Request, urlopen

from .base import Collector, CollectorContext, CollectorResult
from .http_utils import fetch_scoped
from ..config import settings
from ..db import insert_source, upsert_asset


class RdapCollector(Collector):
    """Passive RDAP enrichment for discovered public IPs and domains."""

    name = "rdap"

    def collect(self, context: CollectorContext) -> CollectorResult:
        if not settings.enable_rdap:
            return CollectorResult(self.name, "skipped", "RDAP is opt-in; set ENABLE_RDAP=true for public enrichment")
        ip_rows = context.db.execute("SELECT canonical_value FROM assets WHERE project_id=? AND asset_type='ip'", (context.project["id"],)).fetchall()
        targets = []
        for row in ip_rows[:20]:
            try:
                address = ipaddress.ip_address(row["canonical_value"])
                if address.is_global:
                    targets.append(("ip", row["canonical_value"]))
            except ValueError:
                continue
        targets.extend(("domain", domain) for domain in context.project["allowed_domains"][:10])
        if not targets:
            return CollectorResult(self.name, "skipped", "no public IP or domain target available")
        count = 0
        errors: list[str] = []
        for target_type, target in targets:
            url = f"https://rdap.org/{target_type}/{target}"
            try:
                _, _, raw = fetch_scoped(url, ["rdap.org", "rdap.verisign.com", "rdap.arin.net", "rdap.db.ripe.net", "rdap.apnic.net", "rdap.lacnic.net", "rdap.afrinic.net", "rdap.publicinterestregistry.org"], timeout=12, max_bytes=800_000)
                payload = json.loads(raw)
            except Exception as exc:
                errors.append(f"{target}: {exc}")
                continue
            source_id = insert_source(context.db, context.project["id"], "rdap", f"RDAP {target}", url, raw_content=raw, metadata={"target": target, "target_type": target_type})
            count += 1
            name = str(payload.get("name") or payload.get("handle") or "").strip()
            if name:
                asset_type = "network" if target_type == "ip" else "registry_record"
                upsert_asset(context.db, context.project["id"], asset_type, name.casefold(), name, "discovered", source_id, {"rdap_target": target})
            for entity in payload.get("entities", []):
                handle = str(entity.get("handle") or "").strip()
                roles = ",".join(entity.get("roles") or [])
                if "registrar" in (entity.get("roles") or []):
                    upsert_asset(context.db, context.project["id"], "registrar", handle.casefold(), handle, "discovered", source_id, {"roles": roles, "rdap_target": target})
                if handle and "registrant" in roles.casefold():
                    upsert_asset(context.db, context.project["id"], "registrant", handle.casefold(), handle, "needs_review", source_id, {"roles": roles, "rdap_target": target})
            for network in payload.get("networks", []):
                handle = str(network.get("handle") or "").strip()
                if handle.upper().startswith("AS"):
                    upsert_asset(context.db, context.project["id"], "asn", handle.upper(), handle.upper(), "discovered", source_id, {"rdap_target": target, "name": network.get("name")})
        if errors and count == 0:
            return CollectorResult(self.name, "error", "; ".join(errors))
        return CollectorResult(self.name, "ok", "; ".join(errors) if errors else "RDAP enrichment collected", count)
