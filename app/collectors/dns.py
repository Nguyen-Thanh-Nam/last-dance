from __future__ import annotations

import socket

from .base import Collector, CollectorContext, CollectorResult
from ..db import insert_source, upsert_asset
from ..normalize import normalize_domain


class DnsCollector(Collector):
    name = "dns"

    def collect(self, context: CollectorContext) -> CollectorResult:
        count = 0
        errors: list[str] = []
        for domain in sorted(set(context.project["allowed_domains"] + [context.project["root_domain"]])):
            domain = normalize_domain(domain)
            source_id = insert_source(context.db, context.project["id"], "dns", f"DNS lookup: {domain}", f"dns://{domain}", metadata={"record_type": "A/AAAA"})
            upsert_asset(context.db, context.project["id"], "domain", domain, domain, "confirmed" if domain == context.project["root_domain"] else "discovered", source_id, {"method": "dns_scope"})
            count += 1
            try:
                infos = socket.getaddrinfo(domain, None)
                addresses = sorted({info[4][0] for info in infos})
                for address in addresses:
                    upsert_asset(context.db, context.project["id"], "ip", address, address, "discovered", source_id, {"domain": domain, "method": "dns_lookup"})
                    upsert_asset(context.db, context.project["id"], "dns_record", f"{domain}|A|{address}", f"{domain} A {address}", "discovered", source_id, {"domain": domain, "type": "A/AAAA", "address": address})
                    count += 2
            except OSError as exc:
                errors.append(f"{domain}: {exc}")
        if errors and count == 0:
            return CollectorResult(self.name, "error", "; ".join(errors), 0)
        return CollectorResult(self.name, "ok", "; ".join(errors) if errors else "DNS records collected", count)
