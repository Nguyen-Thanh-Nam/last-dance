from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit

from .normalize import normalize_domain


def host_from_url(url: str) -> str:
    return (urlsplit(url).hostname or "").lower().strip(".")


def is_host_allowed(host: str, allowed_domains: list[str]) -> bool:
    normalized = normalize_domain(host)
    return any(normalized == domain or normalized.endswith("." + domain) for domain in map(normalize_domain, allowed_domains))


def is_public_host(host: str) -> bool:
    host = host.strip("[]").lower()
    try:
        address = ipaddress.ip_address(host)
        return not (address.is_private or address.is_loopback or address.is_link_local or address.is_reserved or address.is_multicast)
    except ValueError:
        if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
            return False
        try:
            resolved = socket.gethostbyname(host)
            address = ipaddress.ip_address(resolved)
            return not (address.is_private or address.is_loopback or address.is_link_local or address.is_reserved or address.is_multicast)
        except (OSError, ValueError):
            # Unresolvable public names can still be recorded passively, but are not fetched actively.
            return True


def validate_url_scope(url: str, allowed_domains: list[str], require_public: bool = True) -> tuple[bool, str]:
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        return False, "only http/https URLs with a host are allowed"
    host = host_from_url(url)
    if not is_host_allowed(host, allowed_domains):
        return False, "host is outside the project allowlist"
    if require_public and not is_public_host(host):
        return False, "private, loopback, link-local, or reserved host is blocked"
    return True, "ok"
