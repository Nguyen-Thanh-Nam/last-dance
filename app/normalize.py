from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def normalize_name(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip()).casefold()


def normalize_domain(value: str) -> str:
    raw = value.strip().lower()
    if "://" in raw:
        raw = urlsplit(raw).hostname or raw
    raw = raw.split("/", 1)[0].split(":", 1)[0].strip(".")
    if raw.startswith("www."):
        raw = raw[4:]
    return raw


def normalize_url(value: str) -> str:
    parts = urlsplit(value.strip())
    if not parts.scheme or not parts.netloc:
        return value.strip()
    host = (parts.hostname or "").lower()
    port = parts.port
    netloc = host
    if port and not ((parts.scheme == "http" and port == 80) or (parts.scheme == "https" and port == 443)):
        netloc = f"{host}:{port}"
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
