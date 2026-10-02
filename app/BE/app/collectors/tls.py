from __future__ import annotations

import json
import socket
import ssl
from urllib.parse import urlsplit

from .base import CollectorContext, CollectorResult
from ..db import insert_source, upsert_asset, insert_evidence, insert_relationship
from ..scope import authorized_target, authorized_private_lab, public_addresses


class TlsCollector:
    name = "tls"

    def collect(self, context: CollectorContext) -> CollectorResult:
        if context.project["mode"] != "authorized":
            return CollectorResult(self.name, "skipped", "project is passive")
        candidates = [context.project["official_website"]]
        candidates += [row["canonical_value"] for row in context.db.execute(
            "SELECT canonical_value FROM assets WHERE project_id=? AND asset_type='website'",
            (context.project["id"],))]
        errors, count = [], 0
        checked = set()
        for url in list(dict.fromkeys(candidates))[:context.max_pages]:
            parts = urlsplit(url)
            if parts.scheme != "https":
                continue
            target = (parts.hostname, parts.port or 443)
            if target in checked:
                continue
            checked.add(target)
            if not authorized_target(url, context.project, "tls"):
                errors.append(f"blocked TLS target: {url}")
                insert_source(context.db, context.project["id"], "probe_error", "TLS scope blocked", url,
                              metadata={"test": "tls", "error": "outside authorized TLS scope"})
                continue
            host, port = parts.hostname, parts.port or 443
            try:
                addresses = public_addresses(host, port, authorized_private_lab(context.project, url, "tls"))
                with socket.create_connection((addresses[0], port), timeout=8) as raw:
                    with ssl.create_default_context().wrap_socket(raw, server_hostname=host) as connection:
                        certificate = connection.getpeercert()
                        attributes = {"certificate": certificate, "tls_version": connection.version(),
                                      "cipher": connection.cipher(), "connected_ip": addresses[0],
                                      "verified": True, "port": port}
                content = json.dumps(attributes, sort_keys=True)
                source_id = insert_source(context.db, context.project["id"], "tls", "TLS handshake", url,
                                          raw_content=content, metadata=attributes)
                cert_id = upsert_asset(context.db, context.project["id"], "certificate", f"{host}:{port}",
                                       f"TLS certificate for {host}:{port}", "discovered", source_id, attributes)
                for kind, hostname in certificate.get("subjectAltName", []):
                    if kind != "DNS":
                        continue
                    from ..normalize import normalize_domain
                    hostname = normalize_domain(hostname)
                    asset_id = upsert_asset(context.db, context.project["id"],
                                            "wildcard" if hostname.startswith("*.") else "host",
                                            hostname, hostname, "discovered", source_id)
                    evidence_id = insert_evidence(context.db, context.project["id"], source_id, content,
                                                  "subjectAltName", 0.95)
                    insert_relationship(context.db, context.project["id"], "asset", cert_id,
                                        "certificate_contains", "asset", asset_id, "related", 0.95,
                                        "Certificate SAN is a technical observation, not ownership proof.", evidence_id)
                count += 1
            except Exception as exc:
                errors.append(f"{url}: {exc}")
                insert_source(context.db, context.project["id"], "probe_error", "TLS handshake failed", url,
                              metadata={"test": "tls", "error": str(exc)})
        return CollectorResult(self.name, "error" if errors else "ok",
                               "; ".join(errors) if errors else f"verified {count} TLS certificates", count)
