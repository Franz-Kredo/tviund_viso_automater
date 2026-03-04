from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Label

from core.exceptions import ApiKeyError, AuthError
from core.models import Event

if TYPE_CHECKING:
    from tui.app import TviundApp

_DT_FMT = "%Y-%m-%d %H:%M"


def _fmt(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime(_DT_FMT) + " UTC"


class EventsScreen(Screen):
    """Lists all upcoming events with key registration info."""

    BINDINGS = [
        Binding("r", "refresh", "Refresh", show=True),
        Binding("p", "pending", "Pending", show=True),
        Binding("l", "logout", "Logout", show=True),
        Binding("q", "app.quit", "Quit", show=True),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._events: list[Event] = []

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Label("Loading events…", id="events-status")
        yield DataTable(id="events-table", cursor_type="row")
        yield Footer()

    @property
    def _app(self) -> "TviundApp":
        from tui.app import TviundApp
        return self.app  # type: ignore[return-value]

    async def on_mount(self) -> None:
        table = self.query_one("#events-table", DataTable)
        table.add_columns(
            "Title",
            "Location",
            "Starts At (UTC)",
            "Reg Opens (UTC)",
            "Reg Closes (UTC)",
            "Spots",
        )
        await self._load_events()

    async def action_refresh(self) -> None:
        await self._load_events()

    async def action_pending(self) -> None:
        from tui.screens.pending_actions import PendingActionsScreen
        await self.app.push_screen(PendingActionsScreen())

    async def action_logout(self) -> None:
        await self._app.auth_service.logout()
        from tui.screens.login import LoginScreen
        await self.app.push_screen(LoginScreen())

    async def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Fired when user presses Enter on a row in the DataTable."""
        idx = event.cursor_row
        if idx < len(self._events):
            ev = self._events[idx]
            from tui.screens.event_detail import EventDetailScreen
            await self.app.push_screen(EventDetailScreen(ev))

    async def _load_events(self) -> None:
        status = self.query_one("#events-status", Label)
        table = self.query_one("#events-table", DataTable)
        status.update("Loading events…")
        try:
            session = self._app.auth_service.require_session()
            events = await self._app.event_service.list_upcoming_events(session)
            self._events = events
            table.clear()
            if not events:
                status.update("No upcoming events found.")
                return
            counts = await asyncio.gather(
                *[
                    self._app.registration_service.count_taken(session, ev.id)
                    for ev in events
                ],
                return_exceptions=True,
            )
            for ev, count in zip(events, counts):
                if isinstance(count, int):
                    ev.taken = count
            for ev in events:
                if ev.is_full:
                    spots = Text(f"FULL {ev.taken}/{ev.capacity}", style="bold red")
                else:
                    spots = Text(f"{ev.taken}/{ev.capacity}")
                table.add_row(
                    ev.title,
                    ev.location or "—",
                    _fmt(ev.starts_at),
                    _fmt(ev.reg_opens_at),
                    _fmt(ev.reg_closes_at),
                    spots,
                )
            status.update(f"{len(events)} upcoming event(s) — press Enter to open, R to refresh")
        except AuthError as exc:
            status.update(f"[red]Session error: {exc}[/red]")
        except ApiKeyError:
            await self._app.handle_api_key_error()
        except Exception as exc:
            status.update(f"[red]Error loading events: {exc}[/red]")
