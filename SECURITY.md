# Security Policy

## Supported versions

| Version | Supported |
|---|---|
| 0.2.x | active |
| 0.1.x | no |

## Reporting a vulnerability

parley is local-first by design: it binds to `127.0.0.1`, never sends data
off-device, and never stores credentials. Security issues therefore fall into
two buckets:

- **A bug in parley** (e.g. the HTTP server leaking data, a CDP handshake
  weakness, a path traversal in the scheduler store). Please open a private
  issue, or email `sachitt.av@gmail.com` with a subject starting with
  `[SECURITY]`, and include the reproduction.

- **Behaviour of WhatsApp itself** (store internals, DOM selectors, the WebView2
  debugging channel). This is expected — parley drives the app's own surface and
  degrades gracefully when internals change. Still report it; "it broke
  gracefully" is useful data.

I aim to triage security reports within 48 hours and ship a fix in the next
patch release.

## Good practice for users

- Keep `parley server` bound to `127.0.0.1` (default) and use `--token` if you
  must expose it.
- Pace your own sends; do not push automation against accounts you do not own.
- `parley setup --undo` removes the debugging channel when you don't need it.