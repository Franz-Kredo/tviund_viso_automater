from __future__ import annotations

import os
from typing import Any

import aiohttp
from dotenv import load_dotenv

from core.exceptions import ApiKeyError

BASE_URL = "https://glxfrorhsqklxvtwndcx.supabase.co"
DEFAULT_API_KEY = "sb_publishable_9AJ3VRGb7jAVGk-ddOQ_4w_U18ZCb5a"


class HttpClient:
    """
    Thin wrapper around a single aiohttp.ClientSession.
    Handles common Supabase headers, JSON serialization, and API key management.

    Raises ApiKeyError on HTTP 401 so the TUI can prompt the user to update the key.
    """

    def __init__(self) -> None:
        load_dotenv()
        self._api_key: str = os.getenv("TVIUND_API_KEY", DEFAULT_API_KEY)
        self._session: aiohttp.ClientSession | None = None

    @property
    def api_key(self) -> str:
        return self._api_key

    @api_key.setter
    def api_key(self, value: str) -> None:
        self._api_key = value
        # Rebuild session headers immediately so next request uses the new key
        if self._session and not self._session.closed:
            self._session.headers.update({
                "Apikey": value,
                "Authorization": f"Bearer {value}",
            })

    async def start(self) -> None:
        self._session = aiohttp.ClientSession(
            base_url=BASE_URL,
            headers={
                "Apikey": self._api_key,
                "Accept": "application/json",
                "X-Supabase-Api-Version": "2024-01-01",
            },
        )

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    def _jwt_headers(self, token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    def _apikey_headers(self) -> dict[str, str]:
        """Used for unauthenticated calls (e.g. login) that use the API key as Bearer."""
        return {"Authorization": f"Bearer {self._api_key}"}

    async def _check_status(self, response: aiohttp.ClientResponse) -> None:
        if response.status == 401:
            raise ApiKeyError("HTTP 401: API key may be invalid or expired.")

    async def get(
        self,
        path: str,
        token: str,
        params: dict[str, str] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> tuple[int, Any]:
        assert self._session is not None
        headers = {**self._jwt_headers(token), **(extra_headers or {})}
        async with self._session.get(path, params=params, headers=headers) as resp:
            await self._check_status(resp)
            data = await resp.json(content_type=None)
            return resp.status, data

    async def post(
        self,
        path: str,
        token: str,
        json_body: dict[str, Any],
        extra_headers: dict[str, str] | None = None,
    ) -> tuple[int, Any]:
        assert self._session is not None
        headers = {
            "Content-Type": "application/json",
            **self._jwt_headers(token),
            **(extra_headers or {}),
        }
        async with self._session.post(path, json=json_body, headers=headers) as resp:
            await self._check_status(resp)
            if resp.status == 204:
                return resp.status, None
            data = await resp.json(content_type=None)
            return resp.status, data

    async def post_no_auth(
        self,
        path: str,
        json_body: dict[str, Any],
        params: dict[str, str] | None = None,
    ) -> tuple[int, Any]:
        """Used for /auth/v1/token — uses API key as Bearer (no JWT yet)."""
        assert self._session is not None
        headers = {
            "Content-Type": "application/json;charset=UTF-8",
            **self._apikey_headers(),
        }
        async with self._session.post(
            path, json=json_body, headers=headers, params=params
        ) as resp:
            await self._check_status(resp)
            data = await resp.json(content_type=None)
            return resp.status, data

    async def post_rpc(
        self,
        path: str,
        token: str,
        json_body: dict[str, Any],
    ) -> tuple[int, Any]:
        """POST to a Supabase RPC endpoint — requires Content-Profile: public."""
        return await self.post(
            path,
            token,
            json_body,
            extra_headers={"Content-Profile": "public"},
        )
