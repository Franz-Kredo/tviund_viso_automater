from __future__ import annotations

import os
from typing import TYPE_CHECKING

from dotenv import set_key
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Center, Vertical
from textual.screen import Screen
from textual.widgets import Button, Input, Label, Static

from core.exceptions import ApiKeyError, AuthError

if TYPE_CHECKING:
    from tui.app import TviundApp

_ENV_FILE = os.path.join(os.getcwd(), ".env")


class LoginScreen(Screen):
    """
    Login screen. Attempts auto-login from .env on mount.
    Falls back to an interactive email/password form.
    """

    BINDINGS = [Binding("escape", "app.quit", "Quit")]

    def compose(self) -> ComposeResult:
        yield Center(
            Vertical(
                Label("tviund.com Event Registration", id="login-title"),
                Static("", id="login-status"),
                Input(placeholder="Email", id="email-input"),
                Input(placeholder="Password", password=True, id="password-input"),
                Button("Login", variant="primary", id="login-btn"),
                id="login-box",
            )
        )

    @property
    def _app(self) -> "TviundApp":
        from tui.app import TviundApp
        return self.app  # type: ignore[return-value]

    async def on_mount(self) -> None:
        # Hide inputs initially — try silent auto-login first
        self.query_one("#email-input").display = False
        self.query_one("#password-input").display = False
        self.query_one("#login-btn").display = False
        self._set_status("Logging in from .env…")
        await self._auto_login()

    async def _auto_login(self) -> None:
        try:
            session = await self._app.auth_service.login_from_env()
            self._set_status("Logged in. Resuming pending tasks…", style="green")
            resumed = await self._app.registration_service.resume_pending_tasks(session)
            if resumed:
                self._set_status(f"Logged in. Resumed {resumed} scheduled task(s).", style="green")
            from tui.screens.events import EventsScreen
            self.app.push_screen(EventsScreen())
        except AuthError as exc:
            self._set_status(f"Auto-login failed: {exc}\nEnter credentials below.", style="yellow")
            self._show_form()
        except ApiKeyError:
            await self._app.handle_api_key_error()
        except Exception as exc:
            self._set_status(f"Error: {exc}", style="red")
            self._show_form()

    def _show_form(self) -> None:
        self.query_one("#email-input").display = True
        self.query_one("#password-input").display = True
        self.query_one("#login-btn").display = True
        self.query_one("#email-input").focus()

    def _set_status(self, message: str, style: str = "white") -> None:
        self.query_one("#login-status", Static).update(f"[{style}]{message}[/{style}]")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "login-btn":
            await self._manual_login()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id in ("email-input", "password-input"):
            await self._manual_login()

    async def _manual_login(self) -> None:
        email = self.query_one("#email-input", Input).value.strip()
        password = self.query_one("#password-input", Input).value.strip()
        if not email or not password:
            self._set_status("Please enter both email and password.", style="red")
            return
        self._set_status("Logging in…")
        try:
            session = await self._app.auth_service.login(email, password)
            # Persist credentials to .env so auto-login works next time
            set_key(_ENV_FILE, "TVIUND_EMAIL", email)
            set_key(_ENV_FILE, "TVIUND_PASSWORD", password)
            resumed = await self._app.registration_service.resume_pending_tasks(session)
            if resumed:
                self._set_status(f"Success! Resumed {resumed} scheduled task(s).", style="green")
            else:
                self._set_status("Success! Credentials saved to .env", style="green")
            from tui.screens.events import EventsScreen
            self.app.push_screen(EventsScreen())
        except AuthError as exc:
            self._set_status(f"Login failed: {exc}", style="red")
        except ApiKeyError:
            await self._app.handle_api_key_error()
        except Exception as exc:
            self._set_status(f"Unexpected error: {exc}", style="red")
