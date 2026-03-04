from __future__ import annotations

from core.exceptions import AuthError
from core.models import Session
from core.ports import IAuthPort

from .http_client import HttpClient


class SupabaseAuthAdapter(IAuthPort):
    def __init__(self, client: HttpClient) -> None:
        self._client = client

    async def login(self, email: str, password: str) -> Session:
        status, data = await self._client.post_no_auth(
            "/auth/v1/token",
            json_body={
                "email": email,
                "password": password,
                "gotrue_meta_security": {},
            },
            params={"grant_type": "password"},
        )
        if status != 200:
            msg = data.get("error_description") or data.get("msg") or "Login failed"
            raise AuthError(msg)
        user = data["user"]
        return Session(
            access_token=data["access_token"],
            refresh_token=data["refresh_token"],
            user_id=user["id"],
            email=user["email"],
            expires_at=data["expires_at"],
        )

    async def logout(self, session: Session) -> None:
        try:
            await self._client.post(
                "/auth/v1/logout",
                token=session.access_token,
                json_body={},
                extra_headers={"Content-Length": "0"},
            )
        except Exception:
            pass  # Best-effort logout
