from __future__ import annotations

import re
from datetime import datetime, timezone

from core.exceptions import EventNotFoundError, ServerTimeError
from core.models import Event, Session
from core.ports import IEventPort

from .http_client import HttpClient

_SELECT = "id,title,description,location,starts_at,reg_opens_at,reg_closes_at,capacity,taken"


def _parse_dt(s: str) -> datetime:
    """Parse an ISO-8601 string and return a UTC-aware datetime."""
    s = s.replace("Z", "+00:00")
    # Pad fractional seconds to exactly 6 digits (server may return 1-5)
    s = re.sub(r"\.(\d{1,5})(?=[+\-])", lambda m: "." + m.group(1).ljust(6, "0"), s)
    dt = datetime.fromisoformat(s)
    return dt.astimezone(timezone.utc)


def _parse_event(raw: dict) -> Event:
    return Event(
        id=raw["id"],
        title=raw["title"],
        description=raw.get("description") or "",
        location=raw.get("location") or "",
        starts_at=_parse_dt(raw["starts_at"]),
        reg_opens_at=_parse_dt(raw["reg_opens_at"]),
        reg_closes_at=_parse_dt(raw["reg_closes_at"]),
        capacity=raw["capacity"],
        taken=raw["taken"],
    )


class SupabaseEventAdapter(IEventPort):
    def __init__(self, client: HttpClient) -> None:
        self._client = client

    async def list_upcoming_events(self, session: Session, since: datetime) -> list[Event]:
        since_str = since.strftime("%Y-%m-%dT%H:%M:%S.") + f"{since.microsecond // 1000:03d}Z"
        status, data = await self._client.get(
            "/rest/v1/events",
            token=session.access_token,
            params={
                "select": _SELECT,
                "starts_at": f"gte.{since_str}",
                "order": "starts_at.asc",
            },
        )
        if status != 200:
            return []
        return [_parse_event(row) for row in data]

    async def get_event(self, session: Session, event_id: str) -> Event:
        status, data = await self._client.get(
            "/rest/v1/events",
            token=session.access_token,
            params={"select": _SELECT, "id": f"eq.{event_id}"},
            extra_headers={"Accept": "application/vnd.pgrst.object+json"},
        )
        if status == 406 or data is None:
            raise EventNotFoundError(event_id)
        return _parse_event(data)

    async def get_server_time(self, session: Session) -> datetime:
        status, data = await self._client.post_rpc(
            "/rest/v1/rpc/server_time",
            token=session.access_token,
            json_body={},
        )
        if status != 200 or data is None:
            raise ServerTimeError(f"Unexpected response: HTTP {status}")
        # data is a JSON string like "2026-03-04T12:55:48.042632+00:00"
        raw: str = data if isinstance(data, str) else str(data)
        return _parse_dt(raw)
