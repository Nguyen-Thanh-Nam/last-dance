from __future__ import annotations

import ipaddress
import socket
from datetime import datetime, timezone
from urllib.parse import urlsplit

from .normalize import normalize_domain, normalize_url
from .config import settings


def host_from_url(url: str) -> str:
    return normalize_domain(urlsplit(url).hostname or "")


def is_host_allowed(host: str, allowed_domains: list[str]) -> bool:
    try:
        normalized = normalize_domain(host)
        for domain in map(normalize_domain, allowed_domains):
            if normalized == domain:
                return True
            try:
                ipaddress.ip_address(domain)
                continue
            except ValueError:
                if not domain.startswith("*.") and normalized.endswith("." + domain):
                    return True
        return False
    except ValueError:
        return False


def public_addresses(host: str, port: int = 443, allow_private: bool = False) -> list[str]:
    """Resolve all addresses, reject mixed/private answers, then pin the connection."""
    addresses = sorted({item[4][0] for item in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)})
    def allowed(address):
        ip = ipaddress.ip_address(address)
        if ip.is_global:
            return True
        return allow_private and ip.is_private and not (ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified)
    if not addresses or any(not allowed(address) for address in addresses):
        raise ValueError("private, loopback, link-local, reserved or mixed DNS target is blocked")
    return addresses


def is_public_host(host: str) -> bool:
    try:
        return bool(public_addresses(host))
    except (OSError, ValueError):
        return False


def validate_url_scope(url: str, allowed_domains: list[str], require_public: bool = True) -> tuple[bool, str]:
    try:
        parts = urlsplit(url)
        if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password:
            return False, "only HTTP(S) URLs without credentials are allowed"
        if parts.port is not None and not 1 <= parts.port <= 65535:
            return False, "invalid port"
        if not is_host_allowed(host_from_url(url), allowed_domains):
            return False, "host is outside the project allowlist"
        if require_public and not is_public_host(parts.hostname):
            return False, "private, reserved, mixed or unresolved host is blocked"
        return True, "ok"
    except ValueError:
        return False, "invalid URL"


def authorized_target(url: str, project: dict, test: str = "http") -> bool:
    if project.get("mode") != "authorized":
        return False
    try:
        host = host_from_url(url)
        if not validate_url_scope(url, project["allowed_domains"], require_public=False)[0]:
            return False
        for scope in project.get("authorized_scopes", []):
            if test not in scope.get("allowed_tests", ["http", "tls"]):
                continue
            expires = scope.get("expires_at")
            if expires and datetime.fromisoformat(expires.replace("Z", "+00:00")) <= datetime.now(timezone.utc):
                continue
            kind, value = scope["kind"], scope["value"]
            if kind == "hostname" and host == normalize_domain(value):
                return True
            if kind == "domain" and is_host_allowed(host, [value]):
                return True
            if kind in {"ip", "cidr"}:
                try:
                    if ipaddress.ip_address(host) in ipaddress.ip_network(value, strict=False):
                        return True
                except ValueError:
                    pass
        return any(normalize_url(item) == normalize_url(url) if "://" in item
                   else normalize_domain(item) == host for item in project.get("authorized_assets", []))
    except (ValueError, KeyError):
        return False


def authorized_private_lab(project: dict | None, url: str, test: str) -> bool:
    if not project or not settings.allow_private_lab:
        return False
    opted_scopes = [scope for scope in project.get("authorized_scopes", []) if scope.get("allow_private")]
    return bool(opted_scopes) and authorized_target(url, {**project, "authorized_scopes": opted_scopes, "authorized_assets": []}, test)
