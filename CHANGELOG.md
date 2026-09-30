# Changelog

All notable changes to parley are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project
does its best to adhere to [Semantic Versioning](https://semver.org).

## [Unreleased]

- PyPI distribution as `parley-wa` (console command and import stay `parley`).
- **MCP server** (`parley mcp`): a stdio Model Context Protocol server so AI
  agents (Claude, Cursor, Copilot, any MCP client) can list chats, read
  messages, send, reply, react and schedule on the user's real WhatsApp —
  works against `mcp>=2` and the classic `mcp<2` FastMCP API.
- **Agent skill** (`parley skill install`): installs the bundled Claude Code
  skill into `~/.claude/skills` in one command.
- `mcp` optional dependency (`pip install 'parley-wa[mcp]'`) plus `mcp` in the
  `dev` extra for CI; wheel ships the skill data.

## [0.2.0] - 2026-09-30

### Added
- **Live verified sending** against the installed WhatsApp Desktop: real
  messages sent and content-confirmed in the conversation UI before `ok`.
- **Reliable DOM send path**: multi-candidate search (contact name *and*
  number), title-only row matching with real coordinate clicks, conversation
  header verification before typing, and post-Enter content confirmation.
  Escape-only cleanup that never closes a chat opened by parley.
- **Recipient resolution** (`Session.resolve_recipient`): matches chat id,
  exact contact/group name, pushname, and phone digits (contains/endswith),
  with substring ranking — `--to` accepts names, groups, numbers or ids.
- **Scheduler** (`parley schedule`): one-shot and hourly/daily/weekly recurring
  sends persisted to `~/.parley/schedules.json` (`PARLEY_DATA_DIR` override),
  fired by `SchedulerThread` inside `parley server` with `/schedule*` HTTP
  endpoints.
- **`parley server`**: local JSON HTTP API (`/status`, `/chats`, `/chat`,
  `/send`, `/reply`, `/react`, `/schedule*`) with optional `--token`.
- **`parley setup` / `--admin` / `--undo`** and a rewritten `parley doctor`
  (process, flag, persistence and endpoint checks). `PARLEY_CDP_HOST` /
  `PARLEY_CDP_PORT` env overrides for remote/container attach.
- **Any-device attach**: macOS/Linux via a Chromium `--remote-debugging-port`
  tab, documented in the README.
- Terminal UI (`parley tui`, optional `[tui]` extra) that rides the same
  simulator and live backends.
- Offline `--demo` simulator across the whole CLI, HTTP and SDK surface.
- CI matrix (Windows + Ubuntu, Python 3.10–3.13, ruff + 40+ pytest tests) and
  GitHub Release distribution (wheel + sdist).

### Changed
- `Session.send()` now threads the resolved display name into the backend.
- CDP/DOM timing tuned: 250 ms polls, ~3 s per search candidate, ~5–9 s total
  cold path measured on Windows 11.

### Fixed
- DOM search no longer targets `#pane-side` inputs (removed in newer builds);
  it locates the real search box via accessible attributes.
- Store send strategies that raised inside `evaluate()` are caught and degrade
  to the prompted-state DOM path instead of failing the send.
- CLI exits with guidance instead of tracebacks when the optional TUI dependency
  is missing.

## [0.1.0] - 2026-09-29

Initial working scaffold: CDP attach to WhatsApp Desktop/WebView2, Store-based
reads (chats/messages/contacts), DOM fallback, message send + reaction,
`HumanPacing`, `--demo` simulator, and the CLI/HTTP surface.