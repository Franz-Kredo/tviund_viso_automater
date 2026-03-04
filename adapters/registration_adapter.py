from __future__ import annotations

import re
from datetime import datetime, timezone

from core.exceptions import AlreadyRegisteredError, NotRegisteredError, RegistrationFailedError
from core.models import Registration, Session
from core.ports import IRegistrationPort

from .http_client import HttpClient


def _parse_dt(s: str) -> datetime:
    s = s.replace("Z", "+00:00")
    # Pad fractional seconds to exactly 6 digits (server may return 1-5)
    s = re.sub(r"\.(\d{1,5})(?=[+\-])", lambda m: "." + m.group(1).ljust(6, "0"), s)
    dt = datetime.fromisoformat(s)
    return dt.astimezone(timezone.utc)


class SupabaseRegistrationAdapter(IRegistrationPort):
    def __init__(self, client: HttpClient) -> None:
        self._client = client

    async def list_registrations(self, session: Session, event_id: str) -> list[Registration]:
        status, data = await self._client.get(
            "/rest/v1/event_registrations",
            token=session.access_token,
            params={
                "select": "user_id,status,created_at",
                "event_id": f"eq.{event_id}",
                "status": "in.(confirmed,waitlisted)",
                "order": "created_at.asc",
            },
        )
        if status != 200 or not data:
            return []
        return [
            Registration(
                user_id=row["user_id"],
                status=row["status"],
                created_at=_parse_dt(row["created_at"]),
            )
            for row in data
        ]

    async def count_registrations(self, session: Session, event_id: str) -> int:
        status, data = await self._client.get(
            "/rest/v1/event_registrations",
            token=session.access_token,
            params={
                "select": "user_id",
                "event_id": f"eq.{event_id}",
                "status": "in.(confirmed,waitlisted)",
            },
        )
        if status != 200 or not data:
            return 0
        return len(data)

    async def register(self, session: Session, event_id: str) -> str:
        # Uses RPC function — returns {"ok": true, "status": "confirmed"}
        status, data = await self._client.post_rpc(
            "/rest/v1/rpc/register_for_event",
            token=session.access_token,
            json_body={"p_event": event_id},
        )
        if status == 409:
            raise AlreadyRegisteredError("Already registered for this event.")
        if status != 200:
            raise RegistrationFailedError(attempts=1, last_status=status)
        if isinstance(data, dict):
            if not data.get("ok"):
                raise RegistrationFailedError(attempts=1, last_status=status)
            return data.get("status", "confirmed")
        return "confirmed"

    async def unregister(self, session: Session, event_id: str) -> None:
        # Uses RPC function — returns {"ok": true, "status": "unregistered"}
        status, data = await self._client.post_rpc(
            "/rest/v1/rpc/unregister_from_event",
            token=session.access_token,
            json_body={"p_event": event_id},
        )
        if status == 200:
            if isinstance(data, dict) and data.get("ok"):
                return
        msg = ""
        if isinstance(data, dict):
            msg = data.get("message") or data.get("hint") or data.get("status") or ""
        if "not" in msg.lower() or status == 404:
            raise NotRegisteredError("You are not registered for this event.")
        raise NotRegisteredError(f"Unregister failed (HTTP {status}): {msg}")
