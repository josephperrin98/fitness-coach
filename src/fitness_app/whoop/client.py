# src/fitness_app/whoop/client.py
"""Typed access to the WHOOP v2 API. Knows nothing about MCP.

Handles exactly one error itself: a 401 triggers one refresh and one
retry. Everything else propagates as `http.HttpError`.
"""

from datetime import datetime, timedelta, timezone

from fitness_app import http
from fitness_app.tokenstore import TokenStore
from fitness_app.whoop import auth
from fitness_app.whoop.auth import WhoopConfig

API_BASE = "https://api.prod.whoop.com/developer/v2"
PAGE_SIZE = 25
MAX_PAGES = 20


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")


class WhoopClient:
    def __init__(self, store: TokenStore, config: WhoopConfig):
        self.store = store
        self.config = config

    @staticmethod
    def _headers(token: str) -> dict:
        return {"Authorization": f"Bearer {token}"}

    def _get(self, path: str, params: dict | None = None) -> dict:
        token = auth.valid_access_token(self.store, self.config)
        try:
            return http.get_json(API_BASE + path, params, self._headers(token))
        except http.HttpError as e:
            if e.status != 401:
                raise
        token = auth.valid_access_token(self.store, self.config, rejected=token)
        return http.get_json(API_BASE + path, params, self._headers(token))

    def _paginated(self, path: str, days: int) -> list[dict]:
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=days)
        params: dict = {"start": _iso(start), "end": _iso(end), "limit": PAGE_SIZE}
        records: list[dict] = []
        for _ in range(MAX_PAGES):
            page = self._get(path, params)
            records.extend(page.get("records", []))
            next_token = page.get("next_token")
            if not next_token:
                break
            params = {**params, "nextToken": next_token}
        return records

    def get_recovery(self, days: int = 7) -> list[dict]:
        return self._paginated("/recovery", days)

    def get_sleep(self, days: int = 7) -> list[dict]:
        return self._paginated("/activity/sleep", days)

    def get_workouts(self, days: int = 7) -> list[dict]:
        return self._paginated("/activity/workout", days)

    def get_cycles(self, days: int = 7) -> list[dict]:
        return self._paginated("/cycle", days)

    def get_profile(self) -> dict:
        return self._get("/user/profile/basic")

    def get_body_measurements(self) -> dict:
        return self._get("/user/measurement/body")
