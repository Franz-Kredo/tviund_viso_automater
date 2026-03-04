from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class Session:
    access_token: str
    refresh_token: str
    user_id: str
    email: str
    expires_at: int  # Unix timestamp (seconds)


@dataclass
class Event:
    id: str
    title: str
    description: str
    location: str
    starts_at: datetime       # always UTC
    reg_opens_at: datetime    # always UTC
    reg_closes_at: datetime   # always UTC
    capacity: int
    taken: int

    @property
    def is_full(self) -> bool:
        return self.taken >= self.capacity

    @property
    def spots_remaining(self) -> int:
        return max(0, self.capacity - self.taken)


@dataclass
class Registration:
    user_id: str
    status: str       # "confirmed" | "waitlisted"
    created_at: datetime  # always UTC


@dataclass
class RegistrationResult:
    success: bool
    status: str       # "confirmed" | "waitlisted" | "scheduled" | "already_registered" | "failed"
    message: str
    attempt_count: int
