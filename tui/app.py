from __future__ import annotations

from textual.app import App
from textual.binding import Binding

from adapters.auth_adapter import SupabaseAuthAdapter
from adapters.event_adapter import SupabaseEventAdapter
from adapters.http_client import HttpClient
from adapters.registration_adapter import SupabaseRegistrationAdapter
from core.exceptions import ApiKeyError
from services.auth_service import AuthService
from services.event_service import EventService
from services.registration_service import RegistrationService


class TviundApp(App):
    """Root Textual application — wires infrastructure and manages screens."""

    TITLE = "tviund.com Event Registration"
    SUB_TITLE = "GMT+0"

    BINDINGS = [
        Binding("q", "quit", "Quit", show=True),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.http_client = HttpClient()

        auth_adapter = SupabaseAuthAdapter(self.http_client)
        event_adapter = SupabaseEventAdapter(self.http_client)
        reg_adapter = SupabaseRegistrationAdapter(self.http_client)

        self.auth_service = AuthService(auth_port=auth_adapter)
        self.event_service = EventService(event_port=event_adapter)
        self.registration_service = RegistrationService(
            event_port=event_adapter,
            registration_port=reg_adapter,
        )

    async def on_mount(self) -> None:
        await self.http_client.start()
        from tui.screens.login import LoginScreen
        await self.push_screen(LoginScreen())

    async def on_unmount(self) -> None:
        self.registration_service.shutdown()
        if self.auth_service.is_authenticated:
            await self.auth_service.logout()
        await self.http_client.close()

    async def action_quit(self) -> None:
        self.exit()

    async def handle_api_key_error(self) -> None:
        """Called when any adapter raises ApiKeyError — prompts user to update key."""
        from tui.screens.api_key import ApiKeyScreen
        await self.push_screen(ApiKeyScreen())
