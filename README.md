<p align="center">
  <img src="https://img.shields.io/pypi/pyversions/parley" alt="Python versions">
  <img src="https://img.shields.io/github/license/Sachitt-AV-08/parley" alt="MIT">
  <img src="https://img.shields.io/github/v/release/Sachitt-AV-08/parley" alt="release">
  <img src="https://img.shields.io/github/actions/workflow/status/Sachitt-AV-08/parley/ci.yml?branch=main" alt="CI">
  <img src="https://img.shields.io/badge/privacy-local_only-0B6B3A" alt="privacy">
  <img src="https://img.shields.io/badge/live_verified-v0.1-2B9E55" alt="live verified">
</p>

<h1 align="center">parley</h1>

<p align="center">
  <strong>Drive your installed WhatsApp Desktop. Read it, send to it, reply, react.</strong><br>
  No cloud. No QR. No Composio. No new apps. Just the WhatsApp that is already
  on your machine — attached the way a browser debugger would.
</p>

<p align="center">
  CLI · HTTP API · TUI — plus a fully offline simulator so you can build and
  test robots without ever touching a real account.
</p>

---

## Why this exists (and why nothing like it did)

The mainstream way to automate WhatsApp is a cloud service (or a library that
*talks to* a cloud service). That means your chat history, your contacts and
your fingerprints transit a third party that is not WhatsApp — and a lot of
them got banned for it.

parley takes the opposite side:

> **It attaches to the WhatsApp Desktop app that is already installed and
> logged in on your machine**, the same way Chrome DevTools attaches to a page
> you're looking at. There is nothing new to log in to, nothing to upload,
> nothing to scan with a QR.

Windows WhatsApp Desktop renders the WhatsApp Web client inside **WebView2**
(Microsoft's Chromium). parley enables the local debugging port (one registry
key, fully reversible), then connects over the **Chrome DevTools Protocol**
and drives the very page you already trust, through the app's own internal
message stores.

**What you get**

| | |
|---|---|
| `parley chats` | conversations, unread counts, pins, last message |
| `parley chat "Ava"` | full history of one chat |
| `parley send --to Ava --text "…"` | send to a **contact, group, number or chat id** |
| `parley reply --message <id> --text "…"` | reply with quoting where supported |
| `parley react --message <id> --emoji 👍` | reactions, not read receipts |
| `parley schedule …` | one-shot **and recurring** scheduled sends, persisted |
| `parley server` | local JSON HTTP API for any agent/tool/webhook |
| `parley tui` | a real terminal chat UI |

**`--to` knows people and groups**: pass an id (`15551234567@c.us`), a number
(`+1 555 123 4567`), a contact name (`Ava`) or a group subject
(`Weekend Hikers`) — parley finds the chat, opens it, and verifies the header
before typing a single word.

Everything is also available through the **`--demo` simulator**, which steps
into the exact same API with scripted conversations — so you can install now,
build a bot tonight and add your real account whenever you're ready.

## Install

```bash
pip install https://github.com/Sachitt-AV-08/parley/releases/download/v0.2.0/parley_wa-0.2.0-py3-none-any.whl
# coming to PyPI as `parley-wa`; `uv tool install` also works from the URL
pip install 'parley-wa[tui]'    # optional terminal UI (once on PyPI)
```

The interactive `parley` command and the `parley` Python import both stay the
same no matter the distribution name.

Then enable the local debugging port and restart WhatsApp Desktop once:

```bash
parley setup
# quit WhatsApp Desktop fully, then reopen it — your login survives
parley doctor      # confirm the endpoint is open
parley status      # attached + logged in
```

`parley setup` sets the user **`WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS`** env var
(no admin needed); `parley setup --admin` writes the machine-wide HKLM policy
instead. `--undo` removes both. After setup, WhatsApp must be relaunched once
since WebView2 only opens its debugging channel at boot.

**Any device.** The endpoint parley attaches to is a plain Chromium debugging
port, so the same CLI works anywhere a WhatsApp Web tab exists:

* Windows — WhatsApp Desktop, as above (`parley setup`).
* macOS / Linux — start your browser with `--remote-debugging-port=9334`,
  open web.whatsapp.com in your chat profile, then `parley status`.
* Remote / containers — point `PARLEY_CDP_HOST` / `PARLEY_CDP_PORT` at the
  machine that exposes the port.

## Quick tour

```bash
# the whole box, no WhatsApp needed:
parley --demo status
parley --demo chats
parley --demo chat Ava
parley --demo send --to Ava --text "hi from parley"
parley --demo server        # poke http://127.0.0.1:8300
parley --demo tui

# then against your real install:
parley chats
parley send --to "Ava" --text "ci is green"
parley send --to "Weekend Hikers" --text "who's bringing the snacks?"
parley send --to "+91 98765 43210" --text "sms alternative, but over WhatsApp"
parley react --message "$(parley chat Ava --json | …)" --emoji 👍
curl -X POST localhost:8300/send -H 'content-type: application/json' \
     -d '{"to":"Ava","text":"via http"}'

# scheduled + recurring sends:
parley schedule add --to Ava --text "morning standup reminder" \
    --at "2026-10-02T09:00:00" --repeat daily
parley schedule list
parley schedule run --once        # fire anything due, right now
curl -X POST localhost:8300/schedule -H 'content-type: application/json' \
     -d '{"to":"Ava","text":"later","at":"2026-10-02T18:00:00","repeat":"daily"}'
```

Every command supports `--json` for piping into scripts, agents and cron.
Scheduled entries live in `~/.parley/schedules.json` (override with
`PARLEY_DATA_DIR`), and `parley server` watches the queue in the background —
a scheduled blast obeys the same human pacing and budget as a manual send.

## Architecture

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
   default, HKLM policy with `--admin`) — exactly how you'd debug any WebView2
   app.
2. **`WebViewBackend`** attaches over CDP and finds the WhatsApp page target.
3. Reads prefer the app's **internal Store** (`window.require("WAWebCollections")`
   or a webpack registry scan) — structured, fast, no screen-scraping. A **DOM
   fallback** kicks in when the internal name changes between builds.
4. Writes go through the Store's message API (`sendTextMsg`/`chat.sendMessage`
   with several strategy fallbacks), and when the build exposes no such API the
   **DOM path** drives the visible UI: search → click the exact row (title-only
   match, real coordinate click) → confirm the header switched → type → Enter.
   Nothing is typed unless the conversation is verified to be the target.
5. `HumanPacing` guards every send so an account never looks like a spam bot.
6. `SchedulerThread` (in `parley server`) fires due queue entries through the
   same paced session.

`DemoBackend` implements the same backend protocol entirely in memory, which is
what powers `--demo`, the tests and the CI.

## Human by default

Blasting is how accounts get flagged. parley's `HumanPacing`:

* types for ~90 ms/character (bounded), jittered;
* sleeps a variable "network" beat before each *sent*;
* keeps a rolling burst budget (18 messages/60 s by default).

Every value is overridable per command and per API call.

## Safety notes

* parley **never** sees, stores or transmits your credentials, chats, contacts
  or session state. All traffic stays on `127.0.0.1`.
* Sends are paced and budgeted by design.
* Read operations never write.
* Treaty: parley is for your own account, your own device, your own automation
  — comply with local law and WhatsApp's ToS. The reported issues tracker is
  open for questions.
* If you use the HTTP server, bind it to `127.0.0.1` and set `--token`.

## Status

| Area | State |
|---|---|
| Simulator (`--demo`) | stable, unit-tested, CI |
| **Live attach (Windows WhatsApp Desktop)** | **verified — first message sent & confirmed in the UI (v0.1)** |
| Recipient resolution (contact, group, number, id) | stable, unit-tested |
| Scheduler (one-shot + hourly/daily/weekly, JSON store) | stable, unit-tested |
| CDP attach + status + login detect | implemented |
| Store read path (chats/messages/contacts) | implemented, version-tolerant |
| DOM fallback reads + DOM send | implemented |
| HTTP API (+ `/schedule*` endpoints) | implemented, unit-tested |
| TUI | functional, rides the simulator too |
| Cross-platform (browser tab via CDP) | supported (any Chromium + web.whatsapp.com) |

The live-store APIs are version-sensitive by nature (they call WhatsApp's own
internal module surface). parley degrades gracefully and is designed so a
build bump only ever softens a feature — never crashes the process.

## Contributing

```bash
uv venv && uv pip install -e '.[dev]'
uv run pytest          # green, offline, fast
uv run parley --demo chats
```

Issues, PRs and *"it works on this build"* reports all welcome.

## License

MIT © Sachitt. Made for people who automate their own machines — not for
harvesting other people's.