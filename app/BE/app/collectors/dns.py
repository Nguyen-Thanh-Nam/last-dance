from __future__ import annotations

import ipaddress
import json
import uuid

import dns.resolver

from .base import Collector, CollectorContext, CollectorResult
from ..db import insert_source, upsert_asset, insert_evidence, insert_relationship
from ..normalize import normalize_domain


class DnsCollector(Collector):
    name = "dns"

    def collect(self, context: CollectorContext) -> CollectorResult:
        resolver = dns.resolver.Resolver()
        resolver.lifetime = 3
        count, errors = 0, []
        domains = sorted(set(context.project["allowed_domains"] + [context.project["root_domain"]]))[:context.max_pages]
        for domain in domains:
            domain = normalize_domain(domain)
            host_id = upsert_asset(context.db, context.project["id"], "host", domain, domain, "discovered")
            # A random label detects possible wildcard DNS; it is never promoted to an asset.
            wildcard = False
            try:
                wildcard = bool(resolver.resolve(f"wildcard-{uuid.uuid4().hex[:12]}.{domain}", "A"))
            except dns.resolver.NXDOMAIN:
                pass
            except (dns.resolver.NoAnswer, dns.resolver.NoNameservers, dns.exception.Timeout) as exc:
                errors.append(f"{domain} wildcard check: {exc}")
            for record_type in ("A", "AAAA", "CNAME", "MX", "NS"):
                try:
                    answer = resolver.resolve(domain, record_type)
                    values = [record.to_text() for record in answer]
                except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
                    continue
                except (dns.resolver.NoNameservers, dns.exception.Timeout) as exc:
                    errors.append(f"{domain} {record_type}: {exc}")
                    continue
                raw = json.dumps({"hostname": domain, "type": record_type, "values": values})
                source_id = insert_source(context.db, context.project["id"], "dns", f"DNS {record_type}: {domain}",
                                          f"dns://{domain}/{record_type}", raw_content=raw,
                                          metadata={"record_type": record_type, "ttl": answer.rrset.ttl,
                                                    "wildcard_detected": wildcard, "interaction": "dns"})
                for value in values:
                    upsert_asset(context.db, context.project["id"], "dns_record", f"{domain}|{record_type}|{value}",
                                 f"{domain} {record_type} {value}", "discovered", source_id,
                                 {"domain": domain, "type": record_type, "value": value, "wildcard_detected": wildcard})
                    if record_type in {"A", "AAAA"}:
                        address = str(ipaddress.ip_address(value))
                        target_id = upsert_asset(context.db, context.project["id"], "ip", address, address,
                                                 "discovered", source_id, {"domain": domain})
                        predicate = "resolves_to"
                    elif record_type == "CNAME":
                        hostname = normalize_domain(value)
                        target_id = upsert_asset(context.db, context.project["id"], "host", hostname, hostname,
                                                 "discovered", source_id)
                        predicate = "aliases_to"
                    else:
                        count += 1
                        continue
                    evidence_id = insert_evidence(context.db, context.project["id"], source_id, raw, record_type, 0.95)
                    insert_relationship(context.db, context.project["id"], "asset", host_id, predicate,
                                        "asset", target_id, "related", 0.95,
                                        "DNS observation does not prove IP or third-party infrastructure ownership.", evidence_id)
                    count += 1
        return CollectorResult(self.name, "error" if errors else "ok",
                               "; ".join(errors) if errors else "DNS A/AAAA/CNAME/MX/NS collected", count)
