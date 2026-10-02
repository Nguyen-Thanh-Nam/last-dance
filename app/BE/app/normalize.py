from __future__ import annotations

import re
import ipaddress
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def normalize_name(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip()).casefold()


def normalize_domain(value: str) -> str:
    raw = value.strip().lower().rstrip(".")
    if "://" in raw:
        raw = urlsplit(raw).hostname or ""
    try:
        return ipaddress.ip_address(raw.strip("[]")).compressed
    except ValueError:
        pass
    wildcard = raw.startswith("*.")
    host = raw[2:] if wildcard else raw
    if not host or any(c in host for c in "/:@[] "):
        raise ValueError("invalid hostname")
    host = host.encode("idna").decode("ascii")
    if len(host) > 253 or any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in host.split(".")):
        raise ValueError("invalid hostname")
    return ("*." if wildcard else "") + host


def registered_domain(value: str) -> str:
    from publicsuffix2 import get_sld
    host = normalize_domain(value).removeprefix("*.")
    return get_sld(host, strict=True) or host


def normalize_url(value: str) -> str:
    parts = urlsplit(value.strip())
    if not parts.scheme or not parts.netloc:
        return value.strip()
    host = normalize_domain(parts.hostname or "")
    port = parts.port
    netloc = f"[{host}]" if ":" in host else host
    if port and not ((parts.scheme == "http" and port == 80) or (parts.scheme == "https" and port == 443)):
        netloc = f"{netloc}:{port}"
    path = parts.path or "/"
    return urlunsplit((parts.scheme.lower(), netloc, path, parts.query, ""))


def normalize_endpoint(value: str) -> str:
    normalized = normalize_url(value)
    parts = urlsplit(normalized)
    params = sorted({key for key, _ in parse_qsl(parts.query, keep_blank_values=True) if key})
    query = urlencode([(key, "") for key in params])
    return urlunsplit((parts.scheme, parts.netloc, parts.path or "/", query, ""))


def parameter_names(value: str) -> list[str]:
    return sorted({key for key, _ in parse_qsl(urlsplit(value).query, keep_blank_values=True) if key})
