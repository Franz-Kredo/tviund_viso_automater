# tviund-register

A TUI (Terminal User Interface) tool for managing event registrations on tviund.com.
Built with Python 3.11+, Textual, aiohttp, and python-dotenv.
Architecture: **Hexagonal (Ports & Adapters)**.

## Quick Start

```bash
cd tviund-register
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your credentials
python main.py
```

## Architecture

```
core/       Domain models + abstract port interfaces. Zero external dependencies.
adapters/   Concrete HTTP implementations of the ports (Supabase REST API).
services/   Business logic: auth, event listing, registration scheduling/retry.
tui/        Textual TUI (the "driving" adapter): screens and widgets.
```

### Layers

| Layer | Key Files | Purpose |
|-------|-----------|---------|
| Core | `core/models.py`, `core/ports.py`, `core/exceptions.py` | Domain types and interfaces |
| Adapters | `adapters/http_client.py`, `adapters/auth_adapter.py`, `adapters/event_adapter.py`, `adapters/registration_adapter.py` | Supabase HTTP calls |
| Services | `services/auth_service.py`, `services/event_service.py`, `services/registration_service.py` | Business rules |
| TUI | `tui/app.py`, `tui/screens/`, `tui/widgets/` | Terminal UI |

## .env Variables

| Variable | Description |
|----------|-------------|
| `TVIUND_EMAIL` | Your tviund.com login email |
| `TVIUND_PASSWORD` | Your tviund.com password |
| `TVIUND_API_KEY` | Supabase public API key (auto-updated by the app if 401 is detected) |

## API Endpoints

All requests go to `https://glxfrorhsqklxvtwndcx.supabase.co`.

| Action | Method | Path | Key Headers / Body |
|--------|--------|------|--------------------|
| Login | POST | `/auth/v1/token?grant_type=password` | body: `{email, password, gotrue_meta_security:{}}` |
| Logout | POST | `/auth/v1/logout?scope=global` | returns 204 |
| List events | GET | `/rest/v1/events` | `select=...&starts_at=gte.NOW&order=starts_at.asc` |
| Get single event | GET | `/rest/v1/events?id=eq.{id}` | `Accept: application/vnd.pgrst.object+json` |
| Server time | POST | `/rest/v1/rpc/server_time` | body: `{}`, `Content-Profile: public` — returns JSON string |
| List registrations | GET | `/rest/v1/event_registrations` | `event_id=eq.{id}&status=in.(confirmed,waitlisted)` |
| Count registrations | GET | `/rest/v1/event_registrations` | `select=user_id&event_id=eq.{id}&status=in.(confirmed,waitlisted)` — count result length |
| Register | POST | `/rest/v1/event_registrations` | body: `{event_id}`, `Prefer: return=representation` |
| **Unregister** | POST | `/rest/v1/rpc/unregister_from_event` | body: `{"p_event": id}`, `Content-Profile: public` (**NOT** a DELETE) |

All authenticated requests require:
- `Authorization: Bearer {jwt_access_token}`
- `Apikey: {TVIUND_API_KEY}`
- `X-Supabase-Api-Version: 2024-01-01`

## Registration Logic

```
register(event):
  if server_now > reg_closes_at  → error: closed
  if server_now >= reg_opens_at  → immediate: up to 5 attempts × 50ms
  if server_now < reg_opens_at   → schedule background asyncio.Task:
      sleep until (reg_opens_at - 60s)
      poll every 50ms until registered or (reg_closes_at + 120s)
```

The background task posts `StatusLine` messages back to `EventDetailScreen` via
Textual's message bus so UI updates are thread/coroutine safe.

## API Key Management

On HTTP 401, `HttpClient` raises `ApiKeyError`. The app catches this globally and
pushes `ApiKeyScreen`, which lets the user enter the new key. It is saved to `.env`
via `dotenv.set_key()` and applied to the running `HttpClient` without restart.

## TUI Screens

| Screen | Key Bindings |
|--------|-------------|
| `LoginScreen` | Auto-login on mount; manual form as fallback |
| `EventsScreen` | `r`=refresh, `p`=pending actions, `Enter`=open event, `l`=logout, `q`=quit |
| `EventDetailScreen` | `r`=register, `u`=unregister, `F5`=refresh, `Esc`=back |
| `PendingActionsScreen` | `d`=details modal, `e`=edit (open EventDetailScreen), `x`=remove/cancel task, `r`=refresh, `Esc`=back |
| `TaskDetailsModal` | `Esc`/button=close |
| `ApiKeyScreen` | `Enter`/Save button=update key, `Esc`=cancel |

## Pending Actions Feature

`RegistrationService` tracks three parallel dicts keyed by `event_id`:
- `_scheduled_tasks` — the `asyncio.Task`
- `_scheduled_events` — the `Event` object for display
- `_scheduled_last_status` — last status string emitted by the task

`get_pending_tasks()` returns `list[tuple[Event, asyncio.Task, str]]` for all
tasks still present in `_scheduled_tasks` (tasks remove themselves from all
three dicts in the `finally` block of `_scheduled_loop`).

`PendingActionsScreen` (accessible via `p` from `EventsScreen`) shows a
`DataTable` of running background registrations with:
- **D** — open `TaskDetailsModal` (read-only info: title, description, timing, last status)
- **E** — open `EventDetailScreen` (full edit/control surface)
- **X** — cancel the scheduled `asyncio.Task` via `cancel_scheduled()`
- **R** — refresh the table

## Time Handling

All datetimes are UTC (`datetime.timezone.utc`). The `/rest/v1/rpc/server_time`
RPC is used as the authoritative clock to avoid local clock skew.

The server occasionally returns timestamps with fewer than 6 fractional-second
digits (e.g. `2026-03-04T12:02:19.66627+00:00`). Both `_parse_dt` helpers in
`adapters/event_adapter.py` and `adapters/registration_adapter.py` pad the
fractional part to 6 digits with a regex before calling `fromisoformat`.

## Known API Quirks

- **`taken` field in `events` table is always `0`** — the Supabase `events` table does not maintain a live count. Actual registration count must be fetched from `event_registrations` (count records with `status=in.(confirmed,waitlisted)`). Both `EventsScreen` and `EventDetailScreen` do this via `RegistrationService.count_taken()` after loading events.

## Requirements

- Python 3.11+
- `aiohttp>=3.9.0`
- `textual>=0.47.0`
- `python-dotenv>=1.0.0`
