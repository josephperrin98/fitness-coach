# src/fitness_app/http.py
"""Minimal HTTP helpers over urllib.

Knows nothing about authentication. Logs method, path and status only —
never headers, bodies or query strings.
"""

import json
import logging
import urllib.error
import urllib.parse
import urllib.request

log = logging.getLogger(__name__)

TIMEOUT_SECONDS = 30


class HttpError(Exception):
    """A non-2xx response (status > 0) or a network failure (status == 0)."""

    def __init__(self, status: int, path: str, body: str = ""):
        self.status = status
        self.path = path
        self.body = body
        if status == 0:
            message = f"Network error on {path}: {body}"
        else:
            message = f"HTTP {status} on {path}"
        super().__init__(message)


def _log_path(url: str) -> str:
    """Path component only, so nothing sensitive is ever logged."""
    return urllib.parse.urlsplit(url).path


def _send(req: urllib.request.Request) -> dict:
    path = _log_path(req.full_url)
    method = req.get_method()
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            log.info("%s %s -> %s", method, path, resp.status)
            raw = resp.read()
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        log.info("%s %s -> %s", method, path, e.code)
        raise HttpError(e.code, path, body) from None
    except urllib.error.URLError as e:
        raise HttpError(0, path, f"network error: {e.reason}") from None
    return json.loads(raw) if raw else {}


def get_json(url: str, params: dict | None = None, headers: dict | None = None) -> dict:
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers=headers or {}, method="GET")
    return _send(req)


def post_form(url: str, data: dict, headers: dict | None = None) -> dict:
    body = urllib.parse.urlencode(data).encode()
    merged = {"Content-Type": "application/x-www-form-urlencoded", **(headers or {})}
    req = urllib.request.Request(url, data=body, headers=merged, method="POST")
    return _send(req)
