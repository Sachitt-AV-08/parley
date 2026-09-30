"""Attach to the real, installed WhatsApp Desktop over CDP.

WhatsApp Desktop (the current Windows build) is a WinUI3/.NET application that
renders the WhatsApp Web client inside WebView2 — i.e., inside an Edge/Chromium
runtime that speaks the Chrome DevTools Protocol. parley flips on that
debugging channel (see ``parley setup``) and then **attaches to the
already-open, already-logged-in window** and drives the very page the user is
looking at. No credentials ever leave the machine.

Transport  : Playwright ``connect_over_cdp``
Read path  : the page's webpack module cache (module raid -> Store modules)
Write path : Store message API, with a DOM-snapshot fallback for reads
"""

from __future__ import annotations

import socket
from dataclasses import dataclass

from ..errors import HostNotFoundError, NotLoggedInError, ProtocolError, StoreUnavailableError
from ..models import Chat, Contact, Message, OutboxMessage
from ..store import script

DEFAULT_PORT = 9334
DEFAULT_WHATSAPP_HOST = "web.whatsapp.com"


@dataclass
class CdpTarget:
    title: str
    url: str
    target_type: str


def port_open(port: int, host: str = "127.0.0.1", timeout: float = 0.6) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


class WebViewBackend:
    """A CDP-backed host driver. Use via :class:`Session` for pacing/retries."""

    def __init__(self, port: int = DEFAULT_PORT, host: str = "127.0.0.1", timeout_s: float = 120) -> None:
        if not port_open(port, host):
            raise HostNotFoundError(
                f"no debugging endpoint on {host}:{port}. Run `parley setup` to enable the "
                "WebView2 debugging port, then restart WhatsApp Desktop."
            )
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise ProtocolError("playwright is required for the CDP backend (pip install playwright)") from exc

        self._pw = None
        self.cdp_host = host
        self.cdp_port = port
        self.timeout_s = timeout_s
        self._browser = None
        self._page = None
        self._store_known = False  # True once the Store bootstrap has succeeded
        self._attach_retries = 40
        self._log = []
        self._pw = sync_playwright().start()
        try:
            self._attach()
        except Exception:
            self.close()
            raise

    # ------------------------------------------------------------- lifecycle
    def _attach(self) -> None:
        browser = None
        for _attempt in range(self._attach_retries):
            try:
                browser = self._pw.chromium.connect_over_cdp(f"http://{self.cdp_host}:{self.cdp_port}")
            except Exception as exc:  # pragma: no cover - transport-specific
                raise ConnectionError(f"could not connect over CDP: {type(exc).__name__}: {exc}") from exc
            for context in browser.contexts:
                for page in context.pages:
                    if self._looks_like_whatsapp(page.url):
                        self._browser = browser
                        self._page = page
                        self._page.set_default_timeout(self.timeout_s * 1000)
                        self._bootstrap_store()
                        return
            browser.close()
            raise HostNotFoundError(
                "CDP is serving, but no WhatsApp page target was open. Launch WhatsApp Desktop "
                "(keep a chat window open) and try again. On macOS/Linux - or with any Chromium "
                "browser - open web.whatsapp.com in Chrome/Edge started with "
                f"--remote-debugging-port={self.cdp_port} and the same profile you use for chat."
            )
        self._log.append(f"attach failed after {self._attach_retries} attempts")

    @staticmethod
    def _looks_like_whatsapp(url: str) -> bool:
        return "whatsapp" in (url or "").lower()

    def _bootstrap_store(self) -> bool:
        """Install the on-page Store resolver (module raid). Idempotent + lazy."""
        try:
            result = self._page.evaluate(script.RESOLVE_S_JS, script.CHUNK_REGS)
        except Exception:
            raise ProtocolError("page is unreachable over CDP") from None
        available = bool(result and result.get("available"))
        self._store_known = available
        return available

    def _require_store(self) -> bool:
        """Ensure the Store resolver is installed; returns available."""
        if not self._store_known:
            self._bootstrap_store()
        if not self._store_known:
            raise StoreUnavailableError(
                "the internal message store could not be located in this WhatsApp build "
                "(module raid + window.Store came up empty); DOM-level chats are still available"
            )
        return True

    # ---------------------------------------------------------------- status
    def status(self) -> dict:
        if not self._page:
            return {"backend": "webview", "ok": False, "reason": "detached"}
        dom = self._page.evaluate(script.DOM_STATUS_JS)
        logged_in = dom.get("loggedIn")
        st = {}
        try:
            st = self._page.evaluate(script.STATUS_JS)
            if st.get("ok") and st.get("connected") is True:
                logged_in = True if not logged_in else logged_in
        except Exception:
            st = {}
        store_available = bool(st.get("store")) or self._store_known
        read_path = "store" if store_available else "dom"
        return {
            "backend": "webview",
            "brand": "WhatsApp Desktop (CDP / WebView2)",
            "cdp": f"{self.cdp_host}:{self.cdp_port}",
            "store": store_available,
            "read_path": read_path,
            "loggedIn": logged_in,
            "me": st.get("me"),
            "url": self._page.url,
            "title": self._page.title(),
        }

    # ----------------------------------------------------------- read paths
    def _require_page_logged_in(self) -> None:
        if not self._page:
            raise HostNotFoundError("not attached")
        dom = self._page.evaluate(script.DOM_STATUS_JS)
        if dom.get("loggedIn") is False:
            raise NotLoggedInError("WhatsApp is showing a login/QR screen")

    def contacts(self) -> list[Contact]:
        self._require_page_logged_in()
        self._require_store()
        rows = self._page.evaluate(script.CONTACTS_JS, None) or []
        return [
            Contact(
                id=r["id"],
                name=r.get("name") or r["id"],
                is_group=bool(r.get("is_group", False)),
                pushname=r.get("pushname"),
                short=r.get("short"),
            )
            for r in rows
            if r and r.get("id")
        ]

    def chats(self, limit: int = 50, unread_only: bool = False) -> list[Chat]:
        self._require_page_logged_in()
        try:
            self._require_store()
            rows = self._page.evaluate(script.CHATS_JS, limit) or []
        except StoreUnavailableError:
            rows = [
                dict(r, unread=0, pinned=False, last_timestamp=None)
                for r in self._page.evaluate(script.DOM_CHATS_JS, limit) or []
            ]
        chats = [
            Chat(
                id=r["id"],
                name=r.get("name") or r["id"],
                is_group=bool(r.get("is_group", False)),
                unread=int(r.get("unread", 0) or 0),
                pinned=bool(r.get("pinned", False)),
                last_message=r.get("last_message"),
                last_timestamp=r.get("last_timestamp"),
            )
            for r in rows
            if r and r.get("id")
        ]
        if unread_only:
            chats = [c for c in chats if c.unread > 0]
        return chats

    def messages(self, chat_id: str, limit: int = 50) -> list[Message]:
        self._require_page_logged_in()
        self._require_store()
        result = self._page.evaluate(script.MESSAGES_JS, {"chatId": chat_id, "limit": limit}) or {}
        if not result.get("ok"):
            raise StoreUnavailableError(result.get("reason", "messages unavailable"))
        return [
            Message(
                id=m["id"],
                chat=m["chat"],
                author=m.get("author", ""),
                text=m.get("text", ""),
                timestamp=m.get("timestamp"),
                from_me=bool(m.get("from_me", False)),
                kind=m.get("kind", "text"),
            )
            for m in result.get("messages", [])
        ]

    # ----------------------------------------------------------- write paths
    def send(self, outbox: OutboxMessage) -> Message:
        self._require_page_logged_in()
        result = None
        try:
            self._require_store()
            result = self._page.evaluate(script.SEND_JS, {"chat": outbox.chat, "text": outbox.text})
        except Exception:
            result = None
        if result and result.get("ok"):
            return Message(
                id=f"sent-{outbox.chat}", chat=outbox.chat, author="me", text=outbox.text, from_me=True
            )
        return self.send_via_dom(outbox)

    def send_via_dom(self, outbox: OutboxMessage) -> Message:
        """Drive the visible UI: search -> open chat -> type -> Enter.

        This is the version-tolerant path: it needs no store internals and
        works on any installed WhatsApp Desktop build. The user literally sees
        parley type. Correctness is enforced twice: the conversation is
        *verified* to be the target chat before any text is typed, and the sent
        text is *confirmed* in the conversation after Enter.
        """
        page = self._page
        name = getattr(outbox, "name", "") or ""
        token = self._chat_token(outbox.chat)
        nl = name.lower()

        current = self._conv_title()
        if not (current and self._title_matches(current, token, nl)):
            opened_title = self._dom_open_chat(outbox.chat, name=name)
            if not opened_title:
                raise ProtocolError(
                    f"could not open a chat for {outbox.chat} in the UI "
                    "(no search result matched, no header change)"
                )
            if not self._title_matches(opened_title, token, nl):
                raise ProtocolError(
                    f"search opened the wrong chat - header reads {opened_title!r}; "
                    "aborting before anything was typed"
                )
            current = opened_title

        compose = page.locator(self._COMPOSE_SEL).first
        compose.wait_for(state="visible", timeout=self.timeout_s * 1000)
        compose.click()
        self._page.keyboard.type(outbox.text, delay=15)
        self._page.keyboard.press("Enter")
        # hand the message off, then confirm it visibly landed
        if not self._confirm_sent_text(outbox.text, timeout_s=8.0):
            raise ProtocolError(
                f"Enter was pressed for {outbox.chat} but the text was not confirmed "
                "in the conversation; nothing re-sent automatically"
            )
        return Message(id=f"dom-{outbox.chat}", chat=outbox.chat, author="me", text=outbox.text, from_me=True)

    _SEARCH_SEL = (
        '#pane-side input[role="textbox"], '
        'div[data-testid="chat-list-search-container"] input, '
        'div[data-testid="chat-list-search-container"], '
        'input[role="textbox"][aria-label*="Search" i], '
        'input[data-testid="chat-list-search-input"]'
    )
    _COMPOSE_SEL = (
        'div[data-testid="conversation-compose-box-input"], '
        'div[contenteditable="true"][data-tab="10"], '
        'footer div[contenteditable="true"]'
    )

    @staticmethod
    def _chat_token(chat_id: str) -> str:
        """The last-10 digits of a chat id — the stable piece that always
        appears in a contact/group row title."""
        digits = "".join(ch for ch in (chat_id or "").split("@")[0] if ch.isdigit())
        return digits[-10:]

    def _search_needles(self, chat_id: str, name: str = "") -> list[str]:
        """Ordered search-box strings to try. Names are what WhatsApp indexes
        for friends and groups; some chats (e.g. your own number) render as the
        bare number, so digits are always tried as a fallback."""
        needles = []
        if name:
            needles.append(name[:40])
        digits = "".join(ch for ch in (chat_id or "").split("@")[0] if ch.isdigit())
        if digits and digits[-10:] != (needles[0] if needles else None):
            needles.append(digits[-10:])
        return needles or [chat_id]

    @staticmethod
    def _norm(s: str) -> str:
        return (s or "").replace(" ", "").strip().lower()

    def _title_matches(self, title: str, token: str, name_lower: str = "") -> bool:
        if not title:
            return False
        t = self._norm(title)
        return bool(token and token in t) or bool(name_lower and name_lower in title.lower())

    def _conv_title(self) -> str:
        try:
            return self._page.evaluate(
                """() => {
                  const h = document.querySelector('#main header, header[data-testid="conversation-header"]');
                  if (!h) return "";
                  const el = h.querySelector('span[dir="auto"], div[data-testid="conversation-title"]');
                  return ((el && el.innerText) || h.innerText || "").split("\\n")[0].trim();
                }"""
            )
        except Exception:
            return ""

    def _scan_for_title(self, token: str, expected: str = "") -> list:
        """Scan for rows whose *title* (first line) matches the token digits or
        expected title. Phone-number searches only produce the number in the
        title of the exact contact row, so this is precise. Returns
        ``[{title, index}]`` where index aligns to a Playwright ``.nth()``."""
        if not token and not expected:
            return []
        rows = self._page.evaluate(
            """(arg) => {
              const norm = (s) => (s || "").replace(/\\s+/g, "").toLowerCase();
              const t = arg.t, exp = arg.exp;
              const matches = (title) => (t && norm(title).indexOf(norm(t)) >= 0)
                                          || (exp && title.toLowerCase().indexOf(exp.toLowerCase()) >= 0);
              const out = [];
              const nodes = document.querySelectorAll('#pane-side [role="row"], #pane-side [role="button"]');
              let i = 0;
              for (const r of nodes) {
                const title = ((r.innerText || "").split("\\n")[0] || "").trim();
                if (title && matches(title)) out.push({ title: title.slice(0, 80), index: i });
                i += 1;
              }
              return out;
            }""",
            {"t": token, "exp": expected},
        )
        return rows or []

    def _wait_search_title(self, token: str, expected: str = "", timeout_s: float = 3.0) -> str | None:
        """Poll until a matching search-result row appears; return its title."""
        import time

        page = self._page
        end = time.monotonic() + timeout_s
        while time.monotonic() < end:
            rows = self._scan_for_title(token, expected)
            if rows:
                return rows[0]["title"]
            page.wait_for_timeout(250)
        return None

    def _click_matching_row(self, token: str, expected: str = "") -> bool:
        rows = self._scan_for_title(token, expected)
        if not rows:
            return False
        try:
            self._page.locator('#pane-side [role="row"], #pane-side [role="button"]').nth(rows[0]["index"]).click(
                timeout=6000
            )
            return True
        except Exception:
            return False

    def _dom_open_chat(self, chat_id: str, name: str = "") -> str | None:
        """Search (name then digits), click the result row whose *title*
        matches, and confirm the conversation header is our target. Returns the
        new header title, or None if nothing matched.

        WhatsApp renders search two ways: inline (when a chat is already open,
        the list + header stay) or as a full-screen overlay (when no chat is
        open, ``#main`` is replaced). Both are handled. Anything short of a
        confirmed, title-checked conversation switch aborts - callers must not
        type on an unverified chat.
        """
        page = self._page
        token = self._chat_token(chat_id)
        before = self._conv_title()
        field = page.locator(self._SEARCH_SEL).first
        field.click()
        page.wait_for_timeout(300)
        for needle in self._search_needles(chat_id, name):
            page.keyboard.press("Control+A")
            page.keyboard.press("Backspace")
            page.wait_for_timeout(150)
            page.keyboard.type(needle, delay=10)
            if not self._wait_search_title(token, expected=name):
                continue
            if not self._click_matching_row(token, expected=name):
                continue
            # NOTE: do NOT press Escape here. WhatsApp Desktop treats Escape
            # after opening a chat as "go back", closing the just-opened one.
            import time

            end = time.monotonic() + 3.5
            after = ""
            while time.monotonic() < end:
                after = self._conv_title()
                if after and (self._title_matches(after, token, name.lower()) or not before):
                    break
                page.wait_for_timeout(200)
            if after and self._title_matches(after, token, name.lower()):
                return after
        # Nothing matched and we never clicked a row, so Escape is safe here:
        # it only clears the search overlay / opens the last conversation. It is
        # NOT safe after a successful click (Escape would close the chat).
        try:
            page.keyboard.press("Escape")
        except Exception:
            pass
        return None

    def _confirm_sent_text(self, text: str, timeout_s: float = 8.0) -> bool:
        """Poll the open conversation until the sent text visibly appears."""
        import time

        page = self._page
        want = self._norm(text)
        end = time.monotonic() + timeout_s
        while time.monotonic() < end:
            hits = page.evaluate(
                """(want) => {
                  const norm = (s) => (s || "").replace(/\\s+/g, "").toLowerCase();
                  const bubbles = document.querySelectorAll(
                    '#main [data-pre-plain-text], #main [data-testid="conversation-panel-messages"] .copyable-text'
                  );
                  for (const b of bubbles) {
                    const candidate = b.getAttribute('data-pre-plain-text') || b.innerText || "";
                    if (candidate && norm(candidate).includes(want)) return true;
                  }
                  return false;
                }""",
                want,
            )
            if hits:
                return True
            page.wait_for_timeout(600)
        return False

    def react(self, message_id: str, emoji: str | None) -> Message:
        self._require_page_logged_in()
        self._require_store()
        result = self._page.evaluate(script.REACT_JS, {"messageId": message_id, "emoji": emoji})
        if not result.get("ok"):
            raise ProtocolError(f"react failed: {result.get('reason', 'unknown')}")
        return Message(id=message_id, chat="", author="me", text=emoji or "", from_me=True)

    def close(self) -> None:
        if self._browser:
            try:
                self._browser.close()
            except Exception:
                pass
            self._browser = None
        if self._pw:
            try:
                self._pw.stop()
            except Exception:
                pass
            self._pw = None
        self._page = None
