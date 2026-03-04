from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen, Screen
from textual.widgets import Button, DataTable, Footer, Header, Label

from core.models import Event

if TYPE_CHECKING:
    from tui.app import TviundApp

_DT_FMT = "%Y-%m-%d %H:%M:%S"


def _fmt(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime(_DT_FMT) + " UTC"


class TaskDetailsModal(ModalScreen):
    """Read-only modal showing full details of one pending registration task."""

    BINDINGS = [Binding("escape", "pop_screen", "Close", show=True)]

    def __init__(self, event: Event, last_status: str, task: asyncio.Task) -> None:
        super().__init__()
        self._event = event
        self._last_status = last_status
        self._task = task

    def compose(self) -> ComposeResult:
        if self._task.done():
            state = "Cancelled" if self._task.cancelled() else "Done"
            state_markup = state
        else:
            state = "Running"
            state_markup = "[yellow]Running[/yellow]"

        task_id = f"{self._task.get_name()}  (id={id(self._task)})"

        yield Vertical(
            Label("[bold]Pending Task Details[/bold]", id="modal-title"),
            Label(f"[bold]Event:[/bold]       {self._event.title}"),
            Label(f"[bold]Location:[/bold]    {self._event.location or '—'}"),
            Label(f"[bold]Description:[/bold] {self._event.description or '—'}"),
            Label(f"[bold]Reg Opens:[/bold]   {_fmt(self._event.reg_opens_at)}"),
            Label(f"[bold]Reg Closes:[/bold]  {_fmt(self._event.reg_closes_at)}"),
            Label(f"[bold]Task ID:[/bold]     [cyan]{task_id}[/cyan]"),
            Label(f"[bold]Task State:[/bold]  {state_markup}"),
            Label(f"[bold]Last Status:[/bold] {self._last_status or '—'}"),
            Button("Close  [Esc]", id="modal-close-btn", variant="primary"),
            id="details-box",
        )

    async def action_pop_screen(self) -> None:
        self.app.pop_screen()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        self.app.pop_screen()


class PendingActionsScreen(Screen):
    """Lists all background-scheduled registration tasks with edit/remove controls."""

    BINDINGS = [
        Binding("escape", "pop_screen", "Back", show=True),
        Binding("r", "refresh", "Refresh", show=True),
        Binding("d", "see_details", "Details", show=True),
        Binding("e", "edit", "Edit", show=True),
        Binding("x", "remove", "Remove", show=True),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._pending: list[tuple[Event, asyncio.Task, str]] = []

    @property
    def _app(self) -> "TviundApp":
        return self.app  # type: ignore[return-value]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Label("", id="pending-status")
        yield DataTable(id="pending-table", cursor_type="row")
        yield Footer()

    async def on_mount(self) -> None:
        table = self.query_one("#pending-table", DataTable)
        table.add_columns("Event Title", "Reg Opens At (UTC)", "Task ID", "State", "Last Status")
        self._refresh_table()

    async def action_pop_screen(self) -> None:
        self.app.pop_screen()

    async def action_refresh(self) -> None:
        self._refresh_table()

    def _refresh_table(self) -> None:
        self._pending = self._app.registration_service.get_pending_tasks()
        table = self.query_one("#pending-table", DataTable)
        status_label = self.query_one("#pending-status", Label)
        table.clear()
        if not self._pending:
            status_label.update("[dim]No pending scheduled registrations.[/dim]")
            return
        for event, task, last_status in self._pending:
            if task.done():
                state_cell = "Cancelled" if task.cancelled() else "Done"
            else:
                state_cell = "[yellow]Running[/yellow]"
            task_id_cell = task.get_name()
            short_status = (last_status[:57] + "…") if len(last_status) > 60 else (last_status or "—")
            table.add_row(
                event.title,
                _fmt(event.reg_opens_at),
                task_id_cell,
                state_cell,
                short_status,
            )
        status_label.update(
            f"{len(self._pending)} pending task(s) — "
            "D=details  E=edit  X=remove  R=refresh"
        )

    def _selected_index(self) -> int | None:
        if not self._pending:
            return None
        table = self.query_one("#pending-table", DataTable)
        row = table.cursor_row
        return row if row < len(self._pending) else None

    async def action_see_details(self) -> None:
        idx = self._selected_index()
        if idx is None:
            return
        event, task, last_status = self._pending[idx]
        await self.app.push_screen(TaskDetailsModal(event, last_status, task))

    async def action_edit(self) -> None:
        idx = self._selected_index()
        if idx is None:
            return
        event, _, _ = self._pending[idx]
        from tui.screens.event_detail import EventDetailScreen
        await self.app.push_screen(EventDetailScreen(event))

    async def action_remove(self) -> None:
        idx = self._selected_index()
        if idx is None:
            return
        event, _, _ = self._pending[idx]
        await self._app.registration_service.cancel_scheduled(event.id)
        self._refresh_table()
