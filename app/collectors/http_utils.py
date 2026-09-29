from __future__ import annotations

import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener, HTTPRedirectHandler

from ..scope import validate_url_scope


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch_scoped(url: str, allowed_domains: list[str], timeout: float = 8.0, max_bytes: int = 500_000, max_redirects: int = 3, delay: float = 0.0) -> tuple[str, str, str]:
    """Fetch one bounded page and validate every redirect before following it."""
    current = url
    opener = build_opener(_NoRedirect)
    for _ in range(max_redirects + 1):
        ok, reason = validate_url_scope(current, allowed_domains, require_public=True)
        if not ok:
            raise ValueError(reason)
        request = Request(current, headers={"User-Agent": "SurfaceMapResearch/0.1"}, method="GET")
        try:
            with opener.open(request, timeout=timeout) as response:
                body = response.read(max_bytes + 1)
                if len(body) > max_bytes:
                    body = body[:max_bytes]
                encoding = response.headers.get_content_charset() or "utf-8"
                return current, response.headers.get_content_type(), body.decode(encoding, errors="replace")
        except HTTPError as exc:
            if exc.code in {301, 302, 303, 307, 308} and exc.headers.get("Location"):
                from urllib.parse import urljoin

                current = urljoin(current, exc.headers["Location"])
                if delay:
                    time.sleep(delay)
                continue
            raise
        except URLError:
            raise
    raise ValueError("redirect limit exceeded")
