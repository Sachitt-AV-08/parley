# Contributing to parley

Thanks for showing up. Everything below is short on purpose — good PRs don't
need ceremony, they need verification.

## Dev setup

```bash
uv venv && uv pip install -e '.[dev]'
uv run pytest          # green, offline, fast
uv run ruff check src tests
```

## Ground rules

1. **Run the tests before opening a PR.** `uv run pytest` must stay green.
   New behaviour gets a test — the demo backend makes this cheap: no WhatsApp
   needed.
2. **Respect the pacing.** `HumanPacing` exists so automated sends never look
   like a spam bot. Do not "helpfully" strip it out.
3. **Sends verify.** Anything that reports a message as sent must confirm it
   actually landed (DOM content confirmation, or an equivalent receipt).
   Failing open is not acceptable.
4. **Live claims need receipts.** "It works on this build" is extremely
   valuable — include the WhatsApp/WebView2 build and the exact parley version,
   and prefer the `--json` output. Keep no secrets in it.

## What kinds of PRs are welcome

- New strategies in the Store write path (version-tolerant by design).
- DOM selector robustness for newer WhatsApp renders/WebView2 builds.
- Pacing/budget options.
- Docs, samples, `--json` one-liners, recipes for cron/agents/webhooks.
- Bug reports with the reproduction bare (`parley --demo …` if possible).

## Adding a feature

- Put behaviour behind the backend protocol in `parley/backends/`, not only in
  the CLI.
- Add a `DemoBackend` implementation and a test that exercises it through
  `Session`. That instantly covers sim, CLI and CI.
- Keep CLI output plain (`--json` for machines; no emoji in stdout).

## Commit style

One logical change per commit; imperative subject line; mention the area in
the prefix (e.g. `deps: …`, `webview: …`). Don't commit unrelated formatting.

## Code of conduct

Be decent. Full text in `CODE_OF_CONDUCT.md`.