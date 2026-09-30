"""parley — drive your installed WhatsApp Desktop locally.

Design points:

* **No cloud, no QR, no Composio.** parley attaches to the copy of WhatsApp
  Desktop that is already installed and logged in on your machine through the
  Chrome DevTools Protocol (CDP). It never re-encodes your credentials.
* **A humane by default.** Sends are paced with realistic typing + network
  delays and a per-window message budget so an account does not look like a
  bot.
* **Works cold.** `parley --demo` boots a fully scripted offline simulator with
  the exact same API, CLI and HTTP surface, so you can evaluate, develop robots
  and run CI without touching your WhatsApp account.

Try it::

    curl -fsSL https://raw.githubusercontent.com/Sachitt-AV-08/parley/main/install.sh | sh   # or the PowerShell one-liner in the README
    parley setup        # enable the local WebView2 debugging port
    parley status       # confirm the desktop app is attached
    parley chats        # list recent conversations
    parley send --to "Myself" --text "hi from parley"
    parley schedule add --to "Myself" --text "happy friday" --at "2026-10-02T09:00:00" --repeat weekly
    parley --demo tui   # or enjoy the simulator, no WhatsApp needed
"""

from .errors import (
    HostNotFoundError,
    NotLoggedInError,
    ProtocolError,
    StoreUnavailableError,
)
from .models import Chat, Contact, Message, OutboxMessage
from .pacing import HumanPacing
from .session import Session, parley_connect

__version__ = "0.3.0"

__all__ = [
    "Chat",
    "Contact",
    "Message",
    "OutboxMessage",
    "HumanPacing",
    "Session",
    "parley_connect",
    "HostNotFoundError",
    "NotLoggedInError",
    "ProtocolError",
    "StoreUnavailableError",
    "__version__",
]
