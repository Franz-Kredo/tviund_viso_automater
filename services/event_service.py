from __future__ import annotations

from datetime import datetime

from core.models import Event, Session
from core.ports import IEventPort


class EventService:
    def __init__(self, event_port: IEventPort) -> None:
        self._port = event_port

    async def list_upcoming_events(self, session: Session) -> list[Event]:
        """Fetch upcoming events using authoritative server time as the 'since' cutoff."""
        server_now = await self._port.get_server_time(session)
        return await self._port.list_upcoming_events(session, since=server_now)

    async def get_event(self, session: Session, event_id: str) -> Event:
        return await self._port.get_event(session, event_id)

    async def get_server_time(self, session: Session) -> datetime:
        return await self._port.get_server_time(session)
