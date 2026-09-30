<p align="center">
  <img src="https://raw.githubusercontent.com/Sachitt-AV-08/parley/main/assets/parley-banner.png" alt="parley" width="100%">
</p>

<p align="center">
  <img src="https://img.shields.io/github/stars/Sachitt-AV-08/parley" alt="stars">
  <img src="https://img.shields.io/github/v/release/Sachitt-AV-08/parley" alt="release">
  <img src="https://img.shields.io/github/actions/workflow/status/Sachitt-AV-08/parley/ci.yml?branch=main" alt="CI">
  <img src="https://img.shields.io/github/license/Sachitt-AV-08/parley" alt="MIT">
  <img src="https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-blue" alt="python">
  <img src="https://img.shields.io/badge/privacy-LOCAL_ONLY-0B6B3A" alt="privacy">
</p>

<p align="center">
  <strong>Drive your installed WhatsApp Desktop — read it, send to it, reply, react, schedule.</strong><br>
  No cloud. No QR code. No new browser tab. No "scan this with your phone" ever again.<br>
  It attaches to the WhatsApp that is <em>already logged in on your machine</em>, the way DevTools attaches to a page.
</p>

<p align="center">
  CLI &nbsp;·&nbsp; Python SDK &nbsp;·&nbsp; local HTTP API &nbsp;·&nbsp; TUI &nbsp;·&nbsp; offline `--demo` simulator
</p>

---

<p align="center">
  <img src="https://raw.githubusercontent.com/Sachitt-AV-08/parley/main/assets/demo.gif" alt="parley demo" width="78%">
</p>

**One line to install on any machine:**

```sh
# Windows (PowerShell) — runs the installer: install + enable the port + next steps
irm https://raw.githubusercontent.com/Sachitt-AV-08/parley/main/install.ps1 | iex
```

```sh
# macOS / Linux
curl -fsSL https://raw.githubusercontent.com/Sachitt-AV-08/parley/main/install.sh | sh
```

The installer detects `uv` → `pipx` → `pip`, installs `parley-wa` (CLI, TUI and MCP extras) from the latest [GitHub Release](https://github.com/Sachitt-AV-08/parley/releases) (sha256 checksums included), enables the local debugging port, and prints the two commands to start. `pip install 'parley-wa'[mcp]` works **once the PyPI publish lands**; until then use the installer or a release wheel URL.

**One line to send from a script on any machine:**

```bash
pip install 'parley-wa'[mcp]      # or: pip install <release wheel URL>
parley setup            # enable the local debugging port (auto-undoable)
parley send --to Ava --text "ci is green"   # resolves Ava -> live chat -> sends -> confirms it landed
```

Or in Python:

```python
from parley import Session, parley_connect

wa = parley_connect()            # auto-attaches to the running WhatsApp Desktop
wa.send("Weekend Hikers", "who's bringing the snacks?")
for chat in wa.chats(unread_only=True):
    print(chat)
```

No WhatsApp account? The entire API runs on a fully scripted simulator:

```bash
parley --demo status
parley --demo send --to Ava --text "hi from parley"
parley --demo tui
```

---

## Threat model

parley works by enabling WebView2's remote debugging port. While it's enabled, any process running as your user can drive your logged-in WhatsApp session and read all chats. parley does not add auth to that port; it is a local-machine trust boundary. If that's not acceptable for your machine, don't run `parley setup`.

Mitigations: run `parley setup --undo` when not in use; the HTTP API requires a token and rejects browser origins; the MCP server is read-only unless `--allow-send` is set; scheduled sends honor the same human pacing budget. Not covered: malware already running as your user; untrusted content in chats (prompt injection) if you give an agent send access.

## Features

| | |
|---|---|
| `parley status` / `parley doctor` | attach health, login state, endpoint checks, reversible setup |
| `parley chats` | conversations, unread counts, pins, last message, last seen |
| `parley chat "Ava"` | full history, richest first, JSON-ready |
| `parley send --to X --text …` | sends to a **contact, group, number, or chat id** — parley resolves the recipient first |
| `parley reply --message <id>` | quoted replies where WhatsApp supports them |
| `parley react --message <id> --emoji ☕` | reactions, not read receipts |
| `parley schedule add …` | one-shot **and recurring** (hourly/daily/weekly) sends, persisted to disk |
| `parley server` | local JSON HTTP API — for agents, webhooks, cron, you name it |
| `parley tui` | a real terminal chat inside your WhatsApp |
| `--demo` | the entire surface, fully scripted, zero WhatsApp needed (also what CI tests live on) |

`--to` knows people *and* groups: pass an id (`15551234567@c.us`), a bare number (`+1 555 123 4567`), a contact name (`Ava`) or a group subject (`Weekend Hikers`) — parley finds the exact chat, opens it, **verifies the header** and only then types. No wrong-chat accidents.

## Quick tour

```bash
# enable the debugging channel (undo later with: parley setup --undo)
parley setup            # user-level env var, no admin; add --admin for HKLM
parley doctor           # confirm: process running? flag present? endpoint open?

# your real install:
parley chats
parley send --to "Weekend Hikers" --text "who's bringing the snacks?"
parley send --to "+91 98765 43210" --text "sms alternative, but over WhatsApp"
parley chat Ava --json | jq '.[0]'

# scheduled + recurring sends, right from the API:
parley schedule add --to Ava --text "morning standup reminder" \
    --at "2026-10-02T09:00:00" --repeat daily
parley schedule list
parley schedule run --once                # fire anything due, right now

# any HTTP client can use it too — `parley server` issues a token on first
# run and prints it (see `~/.parley/server.token`); pass it as a Bearer token:
export PARLEY_TOKEN="$(cat ~/.parley/server.token)"
curl -X POST localhost:8300/send -H "content-type: application/json" \
     -H "authorization: Bearer $PARLEY_TOKEN" \
     -d '{"to":"Ava","text":"via http"}'
```

Every command supports `--json` for piping into scripts, agents and cron. Scheduled entries live in `~/.parley/schedules.json` (override with `PARLEY_DATA_DIR`), and `parley server` watches the queue in the background — a scheduled send obeys the same pacing and budget as a manual send.

## Status

| Area | State |
|---|---|
| Simulator (`--demo`) | stable, unit-tested, CI |
| **Live attach (Windows WhatsApp Desktop)** | **verified — real messages sent & content-confirmed in the UI** |
| Recipient resolution (contact, group, number, id) | stable, unit-tested |
| Scheduler (one-shot + hourly/daily/weekly, JSON store) | stable, unit-tested |
| CDP attach + status + login detect | implemented |
| Store read path (chats/messages/contacts) | implemented, version-tolerant |
| DOM fallback reads + DOM send | implemented, verified |
| HTTP API (incl. `/schedule*`) | implemented, unit-tested |
| TUI | functional, rides the simulator too |
| Cross-platform (any Chromium + web.whatsapp.com) | supported |
| Tests / CI | 40+ green on Windows + Ubuntu, Python 3.10–3.13 |

The live-store APIs are inherently version-sensitive (they call WhatsApp's own internal module surface). parley degrades gracefully — a build bump only ever softens a feature, never crashes the process.

## Documentation

- [Architecture](docs/architecture.md) — CDP attach, Store vs DOM, pacing, scheduler
- [MCP Integration](docs/mcp.md) — stdio server, read-only default, `--allow-send`, `PARLEY_ALLOW_TO`
- [Reliability](docs/reliability.md) — three-step verification, timing benchmarks
- [Comparison](docs/comparison.md) — vs Cloud API, scrapers, cloud platforms
- [Human Pacing](docs/human.md) — typing, network jitter, burst budget
- [Safety](docs/safety.md) — local-only, paced, terms, loopback
- [Detailed Status](docs/status.md) — full feature matrix
- [Roadmap](docs/roadmap.md) — PyPI, media, webhooks, container mode
- [Contributing](docs/contributing.md) — dev setup, CI, reporting
- [License](docs/license.md) — MIT, contributors

---

## Contributors

- **Sachitt** ([@Sachitt-AV-08](https://github.com/Sachitt-AV-08)) — creator, maintainer

## License

MIT © Sachitt. Made for people who automate their own machines — not for harvesting other people's. See [LICENSE](LICENSE).