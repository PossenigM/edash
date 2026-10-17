"""Microsoft Graph access with delegated, read-only permissions (works with new Outlook)."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from edash.config import GraphConfig
from edash.host.platform import Platform

log = logging.getLogger(__name__)

GRAPH_URL = "https://graph.microsoft.com/v1.0"
SCOPES = ["User.Read", "Mail.Read", "Calendars.Read", "Chat.Read"]


class NotLoggedIn(Exception):
    pass


class GraphError(Exception):
    pass


class GraphAuth:
    def __init__(self, config: GraphConfig, cache_path: Path, platform: Platform, session: requests.Session):
        import msal
        from msal_extensions import PersistedTokenCache

        if not config.client_id:
            raise NotLoggedIn("sources.graph.client_id is not set (see README, 'Microsoft Graph')")
        self._app = msal.PublicClientApplication(
            config.client_id,
            authority=f"https://login.microsoftonline.com/{config.tenant}",
            token_cache=PersistedTokenCache(platform.token_persistence(cache_path)),
            http_client=session,
        )

    def token(self) -> str:
        accounts = self._app.get_accounts()
        result = self._app.acquire_token_silent(SCOPES, account=accounts[0]) if accounts else None
        if not result or "access_token" not in result:
            detail = (result or {}).get("error_description", "no cached login")
            raise NotLoggedIn(f"{detail}; run `edash-host login`")
        return result["access_token"]

    def login_interactive(self) -> str:
        return _account_name(self._app.acquire_token_interactive(SCOPES, prompt="select_account"))

    def login_device_code(self, show: Callable[[str], None]) -> str:
        flow = self._app.initiate_device_flow(scopes=SCOPES)
        if "user_code" not in flow:
            raise GraphError(flow.get("error_description", "could not start device code login"))
        show(flow["message"])
        return _account_name(self._app.acquire_token_by_device_flow(flow))


def _account_name(result: dict[str, Any]) -> str:
    if "access_token" not in result:
        raise GraphError(result.get("error_description") or result.get("error") or "login failed")
    return result.get("id_token_claims", {}).get("preferred_username", "unknown account")


class GraphClient:
    def __init__(self, auth: GraphAuth, session: requests.Session):
        self.auth = auth
        self.session = session

    def get(self, path: str, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> dict:
        url = path if path.startswith("https://") else GRAPH_URL + path
        response = self.session.get(
            url,
            params=params,
            headers={"Authorization": f"Bearer {self.auth.token()}", **(headers or {})},
            timeout=30,
        )
        if response.status_code >= 400:
            try:
                message = response.json()["error"]["message"]
            except (ValueError, KeyError, TypeError):
                message = response.text[:200]
            raise GraphError(f"HTTP {response.status_code} for {path.split('?')[0]}: {message}")
        return response.json()

    def get_all(
        self, path: str, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None, limit: int = 200
    ) -> list[dict]:
        """Follow @odata.nextLink pages until ``limit`` items."""
        page = self.get(path, params, headers)
        items = list(page.get("value", []))
        while page.get("@odata.nextLink") and len(items) < limit:
            page = self.get(page["@odata.nextLink"], headers=headers)
            items.extend(page.get("value", []))
        return items[:limit]


def parse_graph_datetime(value: str) -> datetime:
    """Graph returns ISO timestamps, sometimes without zone (then UTC) and with 7 fractional digits."""
    if "." in value:
        head, _, frac = value.partition(".")
        digits = "".join(c for c in frac if c.isdigit())
        value = f"{head}.{digits[:6]}{frac[len(digits):]}"
    dt = datetime.fromisoformat(value)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
