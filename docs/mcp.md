# MCP Integration

parley ships a **Model Context Protocol (MCP) server**, so any MCP client — Claude Desktop, Claude Code, Cursor, Copilot, or any agent framework — can read chats and send/reply/react/schedule on your real WhatsApp, locally.

```bash
pip install 'parley-wa[mcp]'     # not yet on PyPI — use installer or release wheel
parley mcp                       # serve an MCP stdio server on your live account
```

Point your client at it. Claude Desktop-style config (the command must honor the `--demo` global flag placement — it goes *before* the subcommand):

```json
{
  "mcpServers": {
    "parley": { "command": "parley", "args": ["mcp"] }
  }
}
```

For Claude Code, one command installs the bundled agent skill into `~/.claude/skills` — the skill teaches the agent the tool set, pacing and guardrails:

```bash
parley skill install
```

Exposed tools: `status`, `list_chats`, `read_messages`, `send_message`, `reply_message`, `react_message`, `schedule_message`, `list_schedules`, `cancel_schedule`, `run_due_schedules`. Everything stays on `127.0.0.1` and runs through the same paced, verified session as the CLI.

By default the MCP server is **read-only** — pass `--allow-send` to expose mutating tools. Restrict recipients with `PARLEY_ALLOW_TO="Ava,Weekend Hikers"`.