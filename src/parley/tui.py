"""Textual terminal UI (chat list + messages + composer).

Shipped as an optional extra so the core stays dependency-lean:

    pip install 'parley[tui]'
    parley --demo tui      # simulator
    parley tui             # your real local WhatsApp
"""

from __future__ import annotations

from .session import Session

TAB = "    "


def run(demo: bool | None = None) -> None:
    try:
        from textual.app import App, ComposeResult
        from textual.binding import Binding
        from textual.containers import Vertical
        from textual.widgets import Footer, Input, ListItem, ListView, RichLog
    except ImportError as exc:
        raise ImportError("the TUI needs `textual`:  pip install 'parley[tui]'") from exc

    class ParleyApp(App):
        CSS = """
            #pane { padding: 0 1; }
            #pane-label { color: $accent; text-style: bold; }
            ListView { border: round $secondary; height: 1fr; }
            RichLog { border: round $secondary; height: 2fr; }
            Input { dock: bottom; }
        """
        BINDINGS = [Binding("q", "quit", "quit")]

        def __init__(self, session: Session) -> None:
            super().__init__()
            self.session = session
            self.chat_id: str | None = None
            self.messages = RichLog(highlight=True, markup=True, wrap=True, id="messages")

        def compose(self) -> ComposeResult:
            self.chats = ListView(id="chats")
            self.input = Input(placeholder="message… (Enter to send)")
            with Vertical():
                yield self.chats
                yield self.messages
            yield self.input
            yield Footer()

        def on_mount(self) -> None:
            self.refresh_chats()

        def refresh_chats(self) -> None:
            self.chats.clear()
            for chat in self.session.chats(limit=50):
                unread = f" ({chat.unread})" if chat.unread else ""
                self.chats.append(ListItem(self._line(chat.name, unread)))

        @staticmethod
        def _line(*parts: str) -> str:
            return " ".join(parts)

        async def on_list_view_selected(self, event) -> None:
            if self.chats.index is None:
                return
            chats = self.session.chats(limit=50)
            if self.chats.index >= len(chats):
                return
            chat = chats[self.chats.index]
            self.chat_id = chat.id
            self.messages.clear()
            self.title = f"parley — {chat.name}"
            for msg in reversed(self.session.messages(chat.id, limit=80)):
                who = "you" if msg.from_me else (msg.author or "?")
                self.messages.write(f"[bold]{who}[/bold] {msg.preview(140)}")

        def on_input_submitted(self, event) -> None:
            text = event.value.strip()
            event.input.value = ""
            if not text or self.chat_id is None:
                return
            try:
                self.session.send(self.chat_id, text)
                self.messages.write(f"[bold]you[/bold] {text}")
            except Exception as exc:  # noqa: BLE001
                self.notify(str(exc), severity="error")

    ParleyApp(Session(demo=demo)).run()


if __name__ == "__main__":
    run()
