from __future__ import annotations

import http.client
import socket
import ssl
import time
from email.message import Message
from urllib.parse import urljoin, urlsplit

from ..scope import authorized_target, authorized_private_lab, public_addresses, validate_url_scope


def fetch_page(url: str, allowed_domains: list[str], timeout: float = 8.0,
               max_bytes: int = 500_000, max_redirects: int = 3, delay: float = 0.0,
               project: dict | None = None) -> dict:
    current = url
    redirects = []
    for _ in range(max_redirects + 1):
        ok, reason = validate_url_scope(current, allowed_domains, require_public=False)
        if not ok:
            raise ValueError(reason)
        if project is not None and not authorized_target(current, project, "http"):
            raise ValueError("target or redirect is outside authorized HTTP scope")
        parts = urlsplit(current)
        port = parts.port or (443 if parts.scheme == "https" else 80)
        addresses = public_addresses(parts.hostname, port, authorized_private_lab(project, current, "http"))
        conn = http.client.HTTPConnection(parts.hostname, port, timeout=timeout)
        try:
            conn.sock = socket.create_connection((addresses[0], port), timeout)
            tls = None
            if parts.scheme == "https":
                conn.sock = ssl.create_default_context().wrap_socket(conn.sock, server_hostname=parts.hostname)
                tls = {"version": conn.sock.version(), "cipher": conn.sock.cipher(), "certificate": conn.sock.getpeercert()}
            path = parts.path or "/"
            if parts.query:
                path += "?" + parts.query
            conn.request("GET", path, headers={"User-Agent": "SurfaceMapResearch/0.2", "Connection": "close"})
            response = conn.getresponse()
            headers = dict(response.getheaders())
            if response.status in {301, 302, 303, 307, 308} and response.getheader("Location"):
                redirects.append({"url": current, "status": response.status})
                current = urljoin(current, response.getheader("Location"))
                if delay:
                    time.sleep(delay)
                continue
            body = response.read(max_bytes + 1)
            content_header = Message()
            content_header["Content-Type"] = response.getheader("Content-Type", "text/plain")
            encoding = content_header.get_content_charset() or "utf-8"
            try:
                content = body[:max_bytes].decode(encoding, errors="replace")
            except LookupError:
                content = body[:max_bytes].decode("utf-8", errors="replace")
            return {"url": current, "content_type": content_header.get_content_type(), "content": content,
                    "status_code": response.status, "headers": headers, "tls": tls,
                    "redirects": redirects, "truncated": len(body) > max_bytes, "connected_ip": addresses[0]}
        finally:
            conn.close()
    raise ValueError("redirect limit exceeded")


def fetch_scoped(url: str, allowed_domains: list[str], timeout: float = 8.0, max_bytes: int = 500_000,
                 max_redirects: int = 3, delay: float = 0.0) -> tuple[str, str, str]:
    page = fetch_page(url, allowed_domains, timeout, max_bytes, max_redirects, delay)
    return page["url"], page["content_type"], page["content"]
