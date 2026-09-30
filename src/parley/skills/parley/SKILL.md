---
name: parley
description: Drive the user's installed WhatsApp Desktop locally — read chats/messages, send, reply, react, and schedule messages through parley's MCP or CLI. Use whenever the user asks to check, read, write, automate or schedule WhatsApp messages, or integrate WhatsApp into another tool.
---

# parley — WhatsApp automation on the user's own machine

parley attaches to the WhatsApp Desktop app already installed and logged in on
this machine over the Chrome DevTools Protocol. Everything stays on
`127.0.0.1` — no cloud, no QR, no new login.

## Quick facts

- Pacing is intentional: sends type at a human-like rate and respect a rolling
  budget so the account never looks like a bot. Do not try to bypass it.
- `send` resolves a recipient by name, group subject, number or chat id, then
  confirms the message landed in the UI before reporting success.
- If a tool returns `ok: false`, read the `error` and adapt — never retry-send
  blindly in a tight loop.
- The offline simulator (`--demo`) uses the exact same backend contract with
  scripted chats, so tests/CI never touch a real account.

## Common flows

- Unread overview: list_chats(unread_only=true), then read_messages on the
  interesting chat; call unchanged.
- Send a note: send_message(to=<name|number|group>, text=...).
- Reply to someone specific: read_messages to find the message id, then
  reply_message(message_id, text).
- React lightly: react_message(message_id, emoji).
- Queue a reminder: schedule_message(to, text, at="2026-10-02T09:00:00",
  repeat="daily"), then run_due_schedules() when the time comes (server mode
  does this automatically).

## Guardrails for agents

- Only message chats the user can message; use the fastest resolution the tool
  offers (pass display names when you know them).
- One send per user request unless told otherwise. No blast/loop sends.
- Do not reveal chat content outside this machine.
- If the live backend is unreachable, try the CLI with the same args, or note
  the SDK error instead of fabricating success.

## CLI fallback (bash/pwsh)

    parley status
    parley chat Ava
    parley send --to Ava --text "hi"
    parley schedule list
    parley --demo status   # offline simulator

The MCP server exposes the same surface as tools.