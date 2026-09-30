# Reliability

Automating a store you don't own is only as good as the verifier. parley treats "send" as **three confirmed steps**, each independently checked:

1. **Resolve** — `resolve_recipient(needle)` returns a `(chat_id, display_name)` you can inspect, or raises cleanly. Name, number, id and group all work.
2. **Open** — the DOM path only clicks a row whose **title** matches, then re-checks the **conversation header** really switched before allowing typing.
3. **Landed** — after Enter, parley polls `#main` until the exact normalized text appears in the conversation bubble stream. Only then is `ok: true` returned. Failed confirmation raises instead of silently pretending.

Measured on the author's Windows 11 box (one-time cold vs warm):

| path | cost |
|---|---|
| CDP attach + login check | ~0.8 s |
| recipient resolution | ~0.1 s |
| open an already-open chat + send + confirm | ~5 s |
| full cold path (search → open → type → confirm) | ~9 s |

Every number is paced down further by `HumanPacing` before it touches the wire.