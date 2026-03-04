from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from .models import Event, Registration, Session


class IAuthPort(ABC):
    @abstractmethod
    async def login(self, email: str, password: str) -> Session: ...

    @abstractmethod
    async def logout(self, session: Session) -> None: ...


class IEventPort(ABC):
    @abstractmethod
    async def list_upcoming_events(self, session: Session, since: datetime) -> list[Event]: ...

    @abstractmethod
    async def get_event(self, session: Session, event_id: str) -> Event: ...

    @abstractmethod
    async def get_server_time(self, session: Session) -> datetime: ...


class IRegistrationPort(ABC):
    @abstractmethod
    async def list_registrations(self, session: Session, event_id: str) -> list[Registration]: ...

    @abstractmethod
    async def count_registrations(self, session: Session, event_id: str) -> int: ...

    @abstractmethod
    async def register(self, session: Session, event_id: str) -> str: ...

    @abstractmethod
    async def unregister(self, session: Session, event_id: str) -> None: ...
