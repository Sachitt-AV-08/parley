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

The installer detects `uv` → `pipx` → `pip`, installs `parley-wa` (CLI, TUI and
MCP extras) from the [latest release](#release), enables the local debugging
port, and prints the two commands to start.

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

## Why parley exists

The mainstream way to automate WhatsApp is a **cloud service** — or a library
that quietly talks to one. Your chats, your contacts, your fingerprints transit
a third party that is not WhatsApp, and a lot of accounts got flagged for it.

parley takes the opposite side:

> **It never talks to anything but your own machine.** You already trusted
> WhatsApp Desktop with your account — parley attaches to *that* process over
> the Chrome DevTools Protocol (a local debugging channel, one setting away from
> enabled), and drives the very page you're looking at. Everything stays on
> `127.0.0.1`.

The result: no new login, no re-encoding of credentials, no upload, no ban-risk
multiplier — automation for **your own account, on your own screen**, as if a
tireless human assistant with hands were sitting at your desk.

- Windows — WhatsApp Desktop renders WhatsApp Web in **WebView2** (Chromium).
  parley turns on its debugging channel with `parley setup` and connects.
- macOS / Linux — same CLI attaches to any Chromium with
  `--remote-debugging-port=9334` pointed at `web.whatsapp.com`.
- Remote / containers — `PARLEY_CDP_HOST` / `PARLEY_CDP_PORT` point parley at
  whatever machine exposes the port.

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

`--to` knows people *and* groups: pass an id (`15551234567@c.us`), a bare
number (`+1 555 123 4567`), a contact name (`Ava`) or a group subject
(`Weekend Hikers`) — parley finds the exact chat, opens it, **verifies the
header** and only then types. No wrong-chat accidents.

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

Every command supports `--json` for piping into scripts, agents and cron.
Scheduled entries live in `~/.parley/schedules.json` (override with
`PARLEY_DATA_DIR`), and `parley server` watches the queue in the background —
a scheduled blast obeys the same pacing and budget as a manual send.

## How it actually works

```
            ┌─────────────────────────── your machine ───────────────────────────┐
            │                                                                     │
  CLI/TUI   │   ┌──────────┐   ┌──────────────────┐   ┌───────────────────────┐  │
  HTTP API  │   │  parley  │──▶│   Session (paced,│──▶│ Backend (CDP attach)  │  │
  agents    │   │  Session │   │   retried)       │   │ playwright over CDP   │  │
            │   └──────────┘   └──────────────────┘   └──────────┬────────────┘  │
            │                                                     │  CDP over    │
            │   ┌──────────────────────────┐      ┌──────────────┐ │  ws://       │
            │   │ WhatsApp Desktop (WinUI3) │◀────▶│  WebView2    │◀────── localhost│
            │   │  …already logged in…       │      │  (Chromium)  │               │
            │   └──────────────────────────┘      └──────────────┘               │
            └──────────────────────────────────────────────────────────────────────┘
```

1. **`parley setup`** opens the WebView2 debugging channel (user env var by
   default, machine-wide HKLM policy with `--admin`; `--undo` removes both) —
   exactly how you'd debug any WebView2 app.
2. **WebViewBackend** attaches over CDP and finds the WhatsApp page target.
3. **Reads** prefer WhatsApp's internal **Store** (`WAWebCollections`, or a
   webpack registry scan) — structured, fast, no screen-scraping. A DOM
   fallback kicks in when the store's internal name changes between builds.
4. **Writes** go through the Store's message API (`sendTextMsg` / `chat.sendMessage`
   with several strategy fallbacks) and, when the build exposes none, the **DOM
   path** drives the visible UI: search (name *and* number candidates) → click
   the exact row by title → **verify the conversation header switched** →
   type → Enter → **poll until the text visibly appears in the conversation**
   before reporting success.
5. **HumanPacing** guards every send so an account never looks like a spam bot.
6. **SchedulerThread** (in `parley server`) fires due entries through the same
   paced session.

`DemoBackend` implements the same backend protocol entirely in memory — that's
what powers `--demo`, the unit tests and the CI.

## Give your AI agent hands on WhatsApp

parley ships a **Model Context Protocol (MCP) server**, so any MCP client —
Claude Desktop, Claude Code, Cursor, Copilot, or any agent framework — can read
chats and send/reply/react/schedule on your real WhatsApp, locally.

```bash
pip install 'parley-wa[mcp]'     # install with the MCP extra
parley mcp                       # serve an MCP stdio server on your live account
```

Point your client at it. Claude Desktop-style config (the command must honor the
`--demo` global flag placement — it goes *before* the subcommand):

```json
{
  "mcpServers": {
    "parley": { "command": "parley", "args": ["mcp"] }
  }
}
```

For Claude Code, one command installs the bundled agent skill into
`~/.claude/skills` — the skill teaches the agent the tool set, pacing and
guardrails:

```bash
parley skill install
```

Exposed tools: `status`, `list_chats`, `read_messages`, `send_message`,
`reply_message`, `react_message`, `schedule_message`, `list_schedules`,
`cancel_schedule`, `run_due_schedules`. Everything stays on `127.0.0.1` and
runs through the same paced, verified session as the CLI.

## Reliability, with receipts

Automating a store you don't own is only as good as the verifier. parley treats
"send" as **three confirmed steps**, each independently checked:

1. *Resolve* — `resolve_recipient(needle)` returns a `(chat_id, display_name)`
   you can inspect, or raises cleanly. Name, number, id and group all work.
2. *Open* — the DOM path only clicks a row whose **title** matches, then
   re-checks the **conversation header** really switched before allowing typing.
3. *Landed* — after Enter, parley polls `#main` until the exact normalized text
   appears in the conversation bubble stream. Only then is `ok: true` returned.
   Failed confirmation raises instead of silently pretending.

Measured on the author's Windows 11 box (one-time cold vs warm):

| path | cost |
|---|---|
| CDP attach + login check | ~0.8 s |
| recipient resolution | ~0.1 s |
| open an already-open chat + send + confirm | ~5 s |
| full cold path (search → open → type → confirm) | ~9 s |

Every number is paced down further by `HumanPacing` before it touches the wire.

## parley vs the status quo

| | parley | WhatsApp Cloud API | web-scraping "bots" | "tools-in-the-cloud" platforms |
|---|---|---|---|---|
| where data lives | **your machine** | Meta | random VPS | their cloud |
| new login / QR needed | no | yes (business mgr) | sometimes | yes |
| cost | **free, open source** | usage-metered | blocked fast | subscriptions |
| ban profile | low (your own desktop) | official but gated | high | high |
| offline dev / CI | **yes (`--demo`)** | no | no | no |
| self-hostable | **yes** | no | makeshift | no |

## Human by default

Blasting is how accounts get flagged. parley's `HumanPacing`:

- types for ~90 ms/character (bounded), jittered;
- sleeps a variable "network" beat before each *sent*;
- keeps a rolling burst budget (18 messages / 60 s by default).

Every value is overridable per command and per API call, because you are
the responsible party for your own account.

## Safety notes

- parley **never** sees, stores or transmits your credentials, chats, contacts
  or session state. All traffic stays on `127.0.0.1`.
- Sends are paced and budgeted by design. Read operations never write.
- Treaty: use your own account, your own device, your own automation — comply
  with local law and WhatsApp's ToS. The issues tracker is open for questions.
- If you expose the HTTP server beyond loopback, set `--token` and use TLS in
  front — and honestly, don't; keep it on `127.0.0.1`.

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

The live-store APIs are inherently version-sensitive (they call WhatsApp's own
internal module surface). parley degrades gracefully — a build bump only ever
softens a feature, never crashes the process.

## Roadmap

- **PyPI release** of `parley-wa` (one token away — `uv tool install parley-wa`)
- First-class **Python SDK docs** and a `docs/` site
- Media sends (images, voice notes) and message **download**
- Webhooks → `parley server` push channels
- A `parley as a service` mode for containers (still local-first)
- Contributions welcome — see [CONTRIBUTING](CONTRIBUTING.md)

## Contributing

```bash
uv venv && uv pip install -e '.[dev]'
uv run pytest          # green, offline, fast
uv run parley --demo chats
```

Issues, PRs and *"it works on this build"* reports are all gold. Read
[CONTRIBUTING](CONTRIBUTING.md) and the [code of conduct](CODE_OF_CONDUCT.md) first.

## Contributors

- **Sachitt** ([@Sachitt-AV-08](https://github.com/Sachitt-AV-08)) — creator, maintainer

## License

MIT © Sachitt. Made for people who automate their own machines — not for
harvesting other people's. See [LICENSE](LICENSE).