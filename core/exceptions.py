class TviundError(Exception):
    """Base exception for the tviund-register tool."""


class AuthError(TviundError):
    """Login failure or session expired."""


class ApiKeyError(TviundError):
    """HTTP 401 — the Supabase public API key is invalid or has changed."""


class RegistrationNotOpenError(TviundError):
    """reg_opens_at is in the future."""


class RegistrationClosedError(TviundError):
    """reg_closes_at is in the past."""


class AlreadyRegisteredError(TviundError):
    """User already has a confirmed or waitlisted registration."""


class NotRegisteredError(TviundError):
    """User has no registration to remove."""


class RegistrationFailedError(TviundError):
    """All retry attempts exhausted without success."""

    def __init__(self, attempts: int, last_status: int) -> None:
        self.attempts = attempts
        self.last_status = last_status
        super().__init__(
            f"Registration failed after {attempts} attempt(s) (last HTTP {last_status})"
        )


class EventNotFoundError(TviundError):
    """Event ID does not exist."""


class ServerTimeError(TviundError):
    """Could not retrieve server time."""
