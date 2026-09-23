# src/fitness_app/whoop/auth.py
"""WHOOP OAuth 2.0: authorize URL, code exchange, refresh, and the one
function everything else calls — `valid_access_token`.

WHOOP rotates refresh tokens on every refresh and invalidates the old one,
so the new pair must be persisted before anything else happens. Refreshes
are serialised through the store's lock; after taking it we re-read the row
because another caller may have refreshed first.
"""

import os
import secrets
import time
import urllib.parse
from dataclasses import dataclass

from fitness_app import http
from fitness_app.tokenstore import TokenStore, Tokens

PROVIDER = "whoop"
AUTHORIZE_URL = "https://api.prod.whoop.com/oauth/oauth2/auth"
TOKEN_URL = "https://api.prod.whoop.com/oauth/oauth2/token"
SCOPES = (
    "read:recovery read:sleep read:cycles read:workout "
    "read:profile read:body_measurement offline"
)
DEFAULT_REDIRECT_URI = "http://localhost:8765/callback"
REFRESH_MARGIN_SECONDS = 60
RELOGIN = "Not authorised with WHOOP. Run `uv run python -m fitness_app.whoop auth` first."


class ConfigError(Exception):
    """Required configuration is missing."""


class AuthError(Exception):
    """Authorisation failed; the message says what to do next."""


@dataclass(frozen=True)
class WhoopConfig:
    client_id: str
    client_secret: str
    redirect_uri: str

    @classmethod
    def from_env(cls) -> "WhoopConfig":
        required = ("WHOOP_CLIENT_ID", "WHOOP_CLIENT_SECRET")
        missing = [k for k in required if not os.environ.get(k)]
        if missing:
            raise ConfigError(f"missing environment variable(s): {', '.join(missing)}")
        return cls(
            client_id=os.environ["WHOOP_CLIENT_ID"],
            client_secret=os.environ["WHOOP_CLIENT_SECRET"],
            redirect_uri=os.environ.get("WHOOP_REDIRECT_URI", DEFAULT_REDIRECT_URI),
        )


def new_state() -> str:
    return secrets.token_urlsafe(16)


def authorize_url(config: WhoopConfig, state: str) -> str:
    query = urllib.parse.urlencode(
        {
            "response_type": "code",
            "client_id": config.client_id,
            "redirect_uri": config.redirect_uri,
            "scope": SCOPES,
            "state": state,
        }
    )
    return f"{AUTHORIZE_URL}?{query}"


def parse_redirect(pasted_url: str, expected_state: str) -> str:
    query = urllib.parse.parse_qs(urllib.parse.urlsplit(pasted_url.strip()).query)
    code = query.get("code", [None])[0]
    state = query.get("state", [None])[0]
    if not code:
        raise AuthError("the pasted URL has no `code` parameter")
    if state != expected_state:
        raise AuthError("`state` does not match this login attempt; run `auth` again")
    return code


def _tokens_from(response: dict) -> Tokens:
    try:
        return Tokens(
            access_token=response["access_token"],
            refresh_token=response["refresh_token"],
            expires_at=time.time() + float(response["expires_in"]),
        )
    except KeyError as e:
        raise AuthError(
            f"token response is missing {e}; was the `offline` scope granted?"
        ) from None


def exchange_code(config: WhoopConfig, code: str) -> Tokens:
    try:
        response = http.post_form(
            TOKEN_URL,
            {
                "grant_type": "authorization_code",
                "code": code,
                "client_id": config.client_id,
                "client_secret": config.client_secret,
                "redirect_uri": config.redirect_uri,
            },
        )
    except http.HttpError as e:
        raise AuthError(f"WHOOP rejected the code: {e.body or e}") from None
    return _tokens_from(response)


def refresh(config: WhoopConfig, tokens: Tokens) -> Tokens:
    try:
        response = http.post_form(
            TOKEN_URL,
            {
                "grant_type": "refresh_token",
                "refresh_token": tokens.refresh_token,
                "client_id": config.client_id,
                "client_secret": config.client_secret,
                "scope": "offline",
            },
        )
    except http.HttpError as e:
        raise AuthError(f"WHOOP rejected the refresh token ({e.body or e}). {RELOGIN}") from None
    return _tokens_from(response)


def _usable(tokens: Tokens | None, rejected: str | None) -> bool:
    if tokens is None or tokens.access_token == rejected:
        return False
    return tokens.expires_at - time.time() > REFRESH_MARGIN_SECONDS


def valid_access_token(
    store: TokenStore, config: WhoopConfig, rejected: str | None = None
) -> str:
    """Return an access token, refreshing (under the lock) if needed.

    `rejected` is a token the API just refused; passing it forces a refresh
    unless someone else has already replaced it.
    """
    tokens = store.load(PROVIDER)
    if tokens is None:
        raise AuthError(RELOGIN)
    if _usable(tokens, rejected):
        return tokens.access_token
    with store.refresh_lock():
        tokens = store.load(PROVIDER)  # re-read: a concurrent refresh may have landed
        if _usable(tokens, rejected):
            return tokens.access_token
        new_tokens = refresh(config, tokens)
        store.save(PROVIDER, new_tokens)
        return new_tokens.access_token
