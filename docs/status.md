# Status

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