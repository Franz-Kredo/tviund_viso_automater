from __future__ import annotations

import weakref
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Callable

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Label, Log, Static

from core.exceptions import (
    ApiKeyError,
    AuthError,
    NotRegisteredError,
    RegistrationClosedError,
    RegistrationFailedError,
)
from core.models import Event

if TYPE_CHECKING:
    from tui.app import TviundApp

_DT_FMT = "%Y-%m-%d %H:%M:%S"


def _fmt(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime(_DT_FMT) + " UTC"


class StatusLine(Message):
    """Posted from background tasks to safely update the status log."""

    def __init__(self, text: str) -> None:
        self.text = text
        super().__init__()


class EventDetailScreen(Screen):
    """Full event detail view with Register / Unregister controls."""

    BINDINGS = [
        Binding("escape", "pop_screen", "Back", show=True),
        Binding("r", "register", "Register", show=True),
        Binding("u", "unregister", "Unregister", show=True),
        Binding("f5", "refresh_view", "Refresh", show=True),
    ]

    def __init__(self, event: Event) -> None:
        super().__init__()
        self.event = event

    @property
    def _app(self) -> "TviundApp":
        from tui.app import TviundApp
        return self.app  # type: ignore[return-value]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Vertical(
            Label("", id="ev-title"),
            Label("", id="ev-description"),
            Horizontal(
                Label("", id="ev-location"),
                Label("", id="ev-starts"),
                id="ev-row1",
            ),
            Horizontal(
                Label("", id="ev-reg-opens"),
                Label("", id="ev-reg-closes"),
                id="ev-row2",
            ),
            Label("", id="ev-capacity"),
            Label("", id="ev-reg-status"),
            Horizontal(
                Button("Register  [R]", id="btn-register", variant="success"),
                Button("Unregister  [U]", id="btn-unregister", variant="error"),
                id="ev-buttons",
            ),
            Static("[bold]Status log:[/bold]", id="log-header"),
            Log(id="status-log", highlight=True),
            id="detail-layout",
        )
        yield Footer()

    async def on_mount(self) -> None:
        await self._refresh_view()

    def on_status_line(self, message: StatusLine) -> None:
        self._append_status(message.text)

    def _append_status(self, text: str) -> None:
        ts = datetime.now(tz=timezone.utc).strftime("%H:%M:%S")
        log = self.query_one("#status-log", Log)
        log.write_line(f"[{ts}] {text}")

    def _make_status_callback(self) -> "Callable[[str], None]":
        """Return a weakref-safe callback that posts StatusLine only while this screen is mounted.

        The returned closure holds a weak reference to *self* so that when the
        screen is popped and garbage-collected the background task's on_status
        calls become harmless no-ops — no MessagePumpClosed errors, no dangling
        strong references keeping the screen alive in memory.
        """
        screen_ref: weakref.ref[EventDetailScreen] = weakref.ref(self)

        def _post(text: str) -> None:
            screen = screen_ref()
            if screen is not None and screen.is_mounted:
                screen.post_message(StatusLine(text))

        return _post

    async def _refresh_view(self) -> None:
        try:
            session = self._app.auth_service.require_session()
            ev = await self._app.event_service.get_event(session, self.event.id)
            self.event = ev

            self.query_one("#ev-title", Label).update(f"[bold]{ev.title}[/bold]")
            self.query_one("#ev-description", Label).update(ev.description or "No description.")
            self.query_one("#ev-location", Label).update(f"Location: {ev.location or '—'}")
            self.query_one("#ev-starts", Label).update(f"  |  Starts: {_fmt(ev.starts_at)}")
            self.query_one("#ev-reg-opens", Label).update(f"Reg opens:  {_fmt(ev.reg_opens_at)}")
            self.query_one("#ev-reg-closes", Label).update(
                f"  |  Reg closes: {_fmt(ev.reg_closes_at)}"
            )
            ev.taken = await self._app.registration_service.count_taken(session, ev.id)
            capacity_str = (
                f"[red]FULL ({ev.taken}/{ev.capacity})[/red]"
                if ev.is_full
                else f"Spots: {ev.taken}/{ev.capacity} ({ev.spots_remaining} remaining)"
            )
            self.query_one("#ev-capacity", Label).update(capacity_str)

            registered = await self._app.registration_service.is_registered(
                session, ev.id
            )
            scheduled = ev.id in self._app.registration_service._scheduled_tasks and (
                not self._app.registration_service._scheduled_tasks[ev.id].done()
            )
            if scheduled:
                reg_label = "[yellow]SCHEDULED (background)[/yellow]"
            elif registered:
                reg_label = "[green]REGISTERED[/green]"
            else:
                reg_label = "[dim]Not registered[/dim]"
            self.query_one("#ev-reg-status", Label).update(f"Your status: {reg_label}")

        except Exception as exc:
            self._append_status(f"Refresh error: {exc}")

    async def action_pop_screen(self) -> None:
        self.app.pop_screen()

    async def action_refresh_view(self) -> None:
        await self._refresh_view()

    async def action_register(self) -> None:
        try:
            session = self._app.auth_service.require_session()
            result = await self._app.registration_service.register(
                session=session,
                event=self.event,
                on_status=self._make_status_callback(),
            )
            self._append_status(result.message)
            await self._refresh_view()
        except RegistrationClosedError as exc:
            self._append_status(f"[red]{exc}[/red]")
        except RegistrationFailedError as exc:
            self._append_status(f"[red]{exc}[/red]")
        except AuthError as exc:
            self._append_status(f"[red]Auth error: {exc}[/red]")
        except ApiKeyError:
            await self._app.handle_api_key_error()
        except Exception as exc:
            self._append_status(f"[red]Unexpected error: {exc}[/red]")

    async def action_unregister(self) -> None:
        try:
            session = self._app.auth_service.require_session()
            await self._app.registration_service.unregister(
                session=session,
                event_id=self.event.id,
                on_status=self._make_status_callback(),
            )
            self._append_status("[green]Successfully unregistered.[/green]")
            await self._refresh_view()
        except NotRegisteredError as exc:
            self._append_status(f"[yellow]{exc}[/yellow]")
        except AuthError as exc:
            self._append_status(f"[red]Auth error: {exc}[/red]")
        except ApiKeyError:
            await self._app.handle_api_key_error()
        except Exception as exc:
            self._append_status(f"[red]Unexpected error: {exc}[/red]")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-register":
            await self.action_register()
        elif event.button.id == "btn-unregister":
            await self.action_unregister()
