# Architecture

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

1. **`parley setup`** opens the WebView2 debugging channel (user env var by default, machine-wide HKLM policy with `--admin`; `--undo` removes both) — exactly how you'd debug any WebView2 app.
2. **WebViewBackend** attaches over CDP and finds the WhatsApp page target.
3. **Reads** prefer WhatsApp's internal **Store** (`WAWebCollections`, or a webpack registry scan) — structured, fast, no screen-scraping. A DOM fallback kicks in when the store's internal name changes between builds.
4. **Writes** go through the Store's message API (`sendTextMsg` / `chat.sendMessage` with several strategy fallbacks) and, when the build exposes none, the **DOM path** drives the visible UI: search (name *and* number candidates) → click the exact row by title → **verify the conversation header switched** → type → Enter → **poll until the text visibly appears in the conversation** before reporting success.
5. **HumanPacing** guards every send so an account never looks like a spam bot.
6. **SchedulerThread** (in `parley server`) fires due entries through the same paced session.

`DemoBackend` implements the same backend protocol entirely in memory — that's what powers `--demo`, the unit tests and the CI.