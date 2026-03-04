from __future__ import annotations

import os
from typing import TYPE_CHECKING

from dotenv import set_key
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Center, Vertical
from textual.screen import Screen
from textual.widgets import Button, Input, Label, Static

if TYPE_CHECKING:
    from tui.app import TviundApp

_ENV_FILE = ".env"
_ENV_KEY = "TVIUND_API_KEY"


class ApiKeyScreen(Screen):
    """
    Prompts the user to enter an updated Supabase public API key.
    Persists the new key to .env and updates the running HttpClient.
    """

    BINDINGS = [Binding("escape", "cancel", "Cancel", show=True)]

    def compose(self) -> ComposeResult:
        yield Center(
            Vertical(
                Label("[bold red]API Key Error[/bold red]", id="ak-title"),
                Static(
                    "The Supabase public API key appears to be invalid (HTTP 401).\n"
                    "Enter the new key from the tviund.com network requests:",
                    id="ak-description",
                ),
                Input(
                    value=self._current_key(),
                    placeholder="sb_publishable_…",
                    id="ak-input",
                ),
                Static("", id="ak-status"),
                Button("Save & Retry", variant="primary", id="ak-save"),
                id="ak-box",
            )
        )

    @property
    def _app(self) -> "TviundApp":
        from tui.app import TviundApp
        return self.app  # type: ignore[return-value]

    def _current_key(self) -> str:
        return self._app.http_client.api_key

    async def on_mount(self) -> None:
        self.query_one("#ak-input", Input).focus()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "ak-save":
            await self._save()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "ak-input":
            await self._save()

    async def _save(self) -> None:
        new_key = self.query_one("#ak-input", Input).value.strip()
        if not new_key:
            self.query_one("#ak-status", Static).update("[red]Key cannot be empty.[/red]")
            return

        # Update the running client immediately
        self._app.http_client.api_key = new_key

        # Persist to .env
        env_path = os.path.join(os.getcwd(), _ENV_FILE)
        set_key(env_path, _ENV_KEY, new_key)

        self.query_one("#ak-status", Static).update("[green]Key saved to .env.[/green]")
        self.app.pop_screen()

    async def action_cancel(self) -> None:
        self.app.pop_screen()
