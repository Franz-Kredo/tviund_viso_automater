from __future__ import annotations

import asyncio
import json
from datetime import timedelta
from pathlib import Path
from typing import Callable

from core.exceptions import (
    AlreadyRegisteredError,
    NotRegisteredError,
    RegistrationClosedError,
    RegistrationFailedError,
)
from core.models import Event, RegistrationResult, Session
from core.ports import IEventPort, IRegistrationPort

RETRY_INTERVAL = 0.05       # 50 ms between attempts
MAX_IMMEDIATE_ATTEMPTS = 5  # max retries when registration window is already open
SCHEDULE_LEAD_TIME = 60     # seconds before reg_opens_at to start active polling
SCHEDULE_TAIL_TIME = 120    # seconds after reg_closes_at before giving up

# Persistent store for scheduled event IDs across app restarts.
PENDING_FILE = Path.home() / ".tviund" / "pending_tasks.json"

StatusCallback = Callable[[str], None]


class RegistrationService:
    def __init__(
        self,
        event_port: IEventPort,
        registration_port: IRegistrationPort,
    ) -> None:
        self._event_port = event_port
        self._reg_port = registration_port
        self._scheduled_tasks: dict[str, asyncio.Task] = {}
        self._scheduled_events: dict[str, "Event"] = {}
        self._scheduled_last_status: dict[str, str] = {}
        self._is_shutting_down = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def is_registered(self, session: Session, event_id: str) -> bool:
        regs = await self._reg_port.list_registrations(session, event_id)
        return any(r.user_id == session.user_id for r in regs)

    async def count_taken(self, session: Session, event_id: str) -> int:
        return await self._reg_port.count_registrations(session, event_id)

    async def register(
        self,
        session: Session,
        event: Event,
        on_status: StatusCallback | None = None,
    ) -> RegistrationResult:
        server_now = await self._event_port.get_server_time(session)

        if server_now > event.reg_closes_at:
            raise RegistrationClosedError(
                f"Registration for '{event.title}' closed at "
                f"{event.reg_closes_at.strftime('%Y-%m-%d %H:%M')} UTC."
            )

        if server_now >= event.reg_opens_at:
            return await self._register_immediate(session, event, on_status)

        # Registration window not yet open — schedule a background task
        self._schedule_registration(session, event, on_status)
        opens_in = (event.reg_opens_at - server_now).total_seconds()
        return RegistrationResult(
            success=True,
            status="scheduled",
            message=(
                f"Registration opens in {opens_in / 60:.1f} min "
                f"({event.reg_opens_at.strftime('%H:%M:%S')} UTC). "
                "Running in background — will attempt every 50ms starting 1 min early."
            ),
            attempt_count=0,
        )

    async def unregister(
        self,
        session: Session,
        event_id: str,
        on_status: StatusCallback | None = None,
    ) -> None:
        registered = await self.is_registered(session, event_id)
        if not registered:
            raise NotRegisteredError("You are not registered for this event.")
        await self._reg_port.unregister(session, event_id)
        if on_status:
            on_status("Successfully unregistered.")

    def get_pending_tasks(self) -> list[tuple["Event", asyncio.Task, str]]:
        """Return (event, task, last_status) for all running scheduled tasks."""
        result = []
        for event_id, task in list(self._scheduled_tasks.items()):
            event = self._scheduled_events.get(event_id)
            if event is None:
                continue
            last_status = self._scheduled_last_status.get(event_id, "")
            result.append((event, task, last_status))
        return result

    async def cancel_scheduled(self, event_id: str) -> None:
        task = self._scheduled_tasks.get(event_id)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        # _scheduled_loop's finally block removes the entry and saves;
        # no extra save needed here.

    def shutdown(self) -> None:
        """Signal that the app is exiting. Prevents the finally blocks
        from wiping the pending-tasks file during teardown."""
        self._is_shutting_down = True

    async def resume_pending_tasks(self, session: Session) -> int:
        """
        Re-schedule tasks that were persisted from a previous session.

        Reads PENDING_FILE, fetches each event, validates that the
        registration deadline has not yet passed, and re-calls
        _schedule_registration for still-valid entries.  Stale or
        missing events are silently dropped and the file is updated.

        Returns the number of tasks successfully re-scheduled.
        """
        try:
            raw = PENDING_FILE.read_text()
            ids: list[str] = json.loads(raw)
        except FileNotFoundError:
            return 0
        except (json.JSONDecodeError, ValueError):
            # Corrupt file — remove it and start fresh.
            PENDING_FILE.unlink(missing_ok=True)
            return 0

        server_now = await self._event_port.get_server_time(session)
        resumed = 0

        for event_id in ids:
            if event_id in self._scheduled_tasks and not self._scheduled_tasks[event_id].done():
                # Already running (shouldn't happen on fresh start, but be safe).
                resumed += 1
                continue

            try:
                event = await self._event_port.get_event(session, event_id)
            except Exception:
                # Event gone or network error — skip, will be removed when we save.
                continue

            deadline = event.reg_closes_at + timedelta(seconds=SCHEDULE_TAIL_TIME)
            if server_now > deadline:
                # Registration window already closed — discard.
                continue

            self._schedule_registration(session, event)
            resumed += 1

        return resumed

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    def _sync_save_pending(self) -> None:
        """
        Write the current set of scheduled event IDs to PENDING_FILE.

        Uses an atomic write (tmp → rename) to avoid corruption.
        Errors are silenced — persistence is best-effort.
        """
        ids = list(self._scheduled_events.keys())
        try:
            PENDING_FILE.parent.mkdir(parents=True, exist_ok=True)
            tmp = PENDING_FILE.with_suffix(".tmp")
            tmp.write_text(json.dumps(ids))
            tmp.replace(PENDING_FILE)
        except OSError:
            pass

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _register_immediate(
        self,
        session: Session,
        event: Event,
        on_status: StatusCallback | None = None,
    ) -> RegistrationResult:
        last_status = 0
        for attempt in range(1, MAX_IMMEDIATE_ATTEMPTS + 1):
            if on_status:
                on_status(f"Attempt {attempt}/{MAX_IMMEDIATE_ATTEMPTS}…")
            try:
                reg_status = await self._reg_port.register(session, event.id)
                if on_status:
                    on_status(f"Registered! Status: {reg_status}")
                return RegistrationResult(
                    success=True,
                    status=reg_status,
                    message=f"Registered as '{reg_status}' on attempt {attempt}.",
                    attempt_count=attempt,
                )
            except AlreadyRegisteredError:
                if on_status:
                    on_status("Already registered for this event.")
                return RegistrationResult(
                    success=True,
                    status="already_registered",
                    message="You are already registered for this event.",
                    attempt_count=attempt,
                )
            except RegistrationFailedError as exc:
                last_status = exc.last_status
                if on_status:
                    on_status(f"Attempt {attempt} failed (HTTP {last_status}).")
            except Exception as exc:
                if on_status:
                    on_status(f"Attempt {attempt} error: {exc}")
            if attempt < MAX_IMMEDIATE_ATTEMPTS:
                await asyncio.sleep(RETRY_INTERVAL)

        raise RegistrationFailedError(
            attempts=MAX_IMMEDIATE_ATTEMPTS, last_status=last_status
        )

    def _schedule_registration(
        self,
        session: Session,
        event: Event,
        on_status: StatusCallback | None = None,
    ) -> asyncio.Task:
        # Cancel any existing scheduled task for this event
        existing = self._scheduled_tasks.get(event.id)
        if existing and not existing.done():
            existing.cancel()

        # Wrap on_status to track the last status message
        self._scheduled_events[event.id] = event
        self._scheduled_last_status[event.id] = ""

        def _tracked_status(text: str) -> None:
            self._scheduled_last_status[event.id] = text
            if on_status:
                on_status(text)

        task = asyncio.create_task(
            self._scheduled_loop(session, event, _tracked_status),
            name=f"reg-{event.id}",
        )
        self._scheduled_tasks[event.id] = task
        self._sync_save_pending()
        return task

    async def _scheduled_loop(
        self,
        session: Session,
        event: Event,
        on_status: StatusCallback | None = None,
    ) -> None:
        try:
            # Phase 1: sleep until 1 minute before registration opens
            server_now = await self._event_port.get_server_time(session)
            wake_at = event.reg_opens_at - timedelta(seconds=SCHEDULE_LEAD_TIME)
            sleep_seconds = (wake_at - server_now).total_seconds()
            if sleep_seconds > 0:
                if on_status:
                    on_status(
                        f"Sleeping {sleep_seconds:.0f}s — will wake up 1 min before "
                        f"registration opens at {event.reg_opens_at.strftime('%H:%M:%S')} UTC."
                    )
                await asyncio.sleep(sleep_seconds)

            # Phase 2: active polling every 50ms
            deadline = event.reg_closes_at + timedelta(seconds=SCHEDULE_TAIL_TIME)
            attempt = 0
            if on_status:
                on_status("Active polling started.")

            while True:
                server_now = await self._event_port.get_server_time(session)

                if server_now > deadline:
                    if on_status:
                        on_status(
                            f"FAILED: Registration window has closed (after {attempt} attempt(s))."
                        )
                    return

                if server_now >= event.reg_opens_at:
                    attempt += 1
                    if on_status:
                        on_status(f"Attempt {attempt}…")
                    try:
                        reg_status = await self._reg_port.register(session, event.id)
                        if on_status:
                            on_status(f"SUCCESS: Registered as '{reg_status}' (attempt {attempt})!")
                        return
                    except AlreadyRegisteredError:
                        if on_status:
                            on_status("Already registered.")
                        return
                    except Exception as exc:
                        if on_status:
                            on_status(f"Attempt {attempt} failed: {exc}")
                else:
                    remaining = (event.reg_opens_at - server_now).total_seconds()
                    if on_status and attempt == 0:
                        on_status(f"Waiting… {remaining:.1f}s until window opens.")

                await asyncio.sleep(RETRY_INTERVAL)

        except asyncio.CancelledError:
            if on_status:
                on_status("Scheduled registration cancelled.")
            raise
        finally:
            if not self._is_shutting_down:
                self._scheduled_tasks.pop(event.id, None)
                self._scheduled_events.pop(event.id, None)
                self._scheduled_last_status.pop(event.id, None)
                self._sync_save_pending()
