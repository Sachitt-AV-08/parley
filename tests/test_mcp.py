"""MCP surface tests: tool functions behave, and (when the mcp SDK is present) the server exposes them."""

from __future__ import annotations

import json
from importlib import util as _util

import pytest

from parley import parley_connect

_MCP_AVAILABLE = _util.find_spec("mcp") is not None


@pytest.fixture()
def iso_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("PARLEY_DATA_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture()
def session(iso_tmp):
    return parley_connect(demo=True)


@pytest.mark.parametrize(
    "name,args,key",
    [
        ("tool_status", {}, "ok"),
        ("tool_list_chats", {}, "chats"),
        ("tool_read_messages", {"chat": "Ava"}, "messages"),
        ("tool_send_message", {"to": "Ava", "text": "from mcp test"}, "id"),
        ("tool_list_schedules", {}, "schedules"),
    ],
)
def test_tool_contract(session, name, args, key):
    import inspect

    import parley.mcp_server as m
    from parley.scheduler import Scheduler

    sig = inspect.signature(getattr(m, name))
    first = next(iter(sig.parameters))
    kwargs = {"session": session} if first == "session" else {"scheduler": Scheduler(session=session)}
    res = getattr(m, name)(**kwargs, **args)
    assert res["ok"] is True
    assert key in res


def test_send_message_resolves_by_number(session):
    import parley.mcp_server as m

    res = m.tool_send_message(session, to="15551234567", text="hi number")
    assert res["ok"] is True
    assert res["chat"].endswith("@c.us")


def test_react_then_read_message_id(session):
    import parley.mcp_server as m

    peek = m.tool_read_messages(session, chat="Ava", limit=1)
    mid = peek["messages"][0]["id"]
    res = m.tool_react_message(session, message_id=mid, emoji="🎉")
    assert res["ok"] is True
    assert res["emoji"] == "🎉"


def test_schedule_flow(session):
    import parley.mcp_server as m
    from parley.scheduler import Scheduler

    scheduler = Scheduler(session=session)
    added = m.tool_schedule_message(scheduler, to="Ava", text="scheduled mcp", at="2099-01-01T00:00:00")
    assert added["ok"] is True
    listed = m.tool_list_schedules(scheduler)
    sid = added["id"]
    assert any(s["id"] == sid for s in listed["schedules"])
    assert m.tool_cancel_schedule(scheduler, entry_id=sid)["ok"] is True


def test_bind_hides_injected_args():
    from parley.mcp_server import _bind

    def _fake(session, to, text):
        return {"ok": True, "to": to}

    bound = _bind(_fake, session=object(), scheduler=None)
    assert list(bound.__code__.co_varnames) == ["to", "text"]
    assert bound(to="x", text="y") == {"ok": True, "to": "x"}


@pytest.mark.skipif(not _MCP_AVAILABLE, reason="mcp SDK not installed")
def test_server_exposes_tools_and_calls(session):
    import asyncio

    from parley.mcp_server import build_mcp

    async def run():
        server = build_mcp(session)
        tools = await server.list_tools()
        names = [t.name for t in tools]
        assert "send_message" in names
        assert "read_messages" in names
        assert "schedule_message" in names
        res = await server.call_tool("send_message", {"to": "Ava", "text": "mcp wire test"})
        text = res.content[0].text
        assert json.loads(text)["ok"] is True

    asyncio.run(run())


def test_skill_installs(tmp_path):
    from parley.cli import main

    dest = tmp_path / "skills"
    code = main(["--json", "skill", "--force", "--dest", str(dest)])
    assert code == 0
    skill = dest / "parley" / "SKILL.md"
    assert skill.exists()
    content = skill.read_text(encoding="utf-8")
    assert "parley" in content.lower() and "guardrails" in content.lower()


@pytest.mark.skipif(not _MCP_AVAILABLE, reason="mcp SDK not installed")
def test_stdio_e2e():
    import sys

    import anyio
    from mcp.client.session import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    async def go():
        params = StdioServerParameters(
            command=sys.executable, args=["-m", "parley.cli", "--demo", "mcp"]
        )
        async with stdio_client(params) as (r, w):
            async with ClientSession(r, w) as s:
                await s.initialize()
                tools = await s.list_tools()
                names = [t.name for t in tools.tools]
                assert "send_message" in names and "schedule_message" in names
                out = await s.call_tool("send_message", {"to": "Ava", "text": "stdio e2e"})
                assert json.loads(out.content[0].text)["ok"] is True

    anyio.run(go)
