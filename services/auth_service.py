from __future__ import annotations

import os
import time

from dotenv import load_dotenv

from core.exceptions import AuthError
from core.models import Session
from core.ports import IAuthPort


class AuthService:
    def __init__(self, auth_port: IAuthPort) -> None:
        self._port = auth_port
        self._session: Session | None = None

    async def login_from_env(self) -> Session:
        """Load credentials from .env and log in."""
        load_dotenv()
        email = os.getenv("TVIUND_EMAIL", "").strip()
        password = os.getenv("TVIUND_PASSWORD", "").strip()
        if not email or not password:
            raise AuthError("TVIUND_EMAIL and TVIUND_PASSWORD must be set in .env")
        return await self.login(email, password)

    async def login(self, email: str, password: str) -> Session:
        session = await self._port.login(email, password)
        self._session = session
        return session

    async def logout(self) -> None:
        if self._session:
            await self._port.logout(self._session)
            self._session = None

    @property
    def session(self) -> Session | None:
        return self._session

    @property
    def is_authenticated(self) -> bool:
        return self._session is not None

    def require_session(self) -> Session:
        if self._session is None:
            raise AuthError("Not logged in.")
        # Warn if token is within 60 seconds of expiry
        if time.time() > self._session.expires_at - 60:
            raise AuthError("Session has expired. Please log in again.")
        return self._session
