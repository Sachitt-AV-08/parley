"""Human pacing: turn slow, spammy automation into believable behavior.

Anything that would raise flags with WhatsApp or its users — typing an entire
message in one burst, blasting many messages in a minute, instant replies to
every ping — is dialed down here. The defaults are conservative; tune freely.
"""

from __future__ import annotations

import random
import threading
import time
from collections import deque

DEFAULT_TYPING_PER_CHAR = 0.09  # seconds per character while "typing"
DEFAULT_TYPING_MAX = 3.5  # never "type" longer than this
DEFAULT_NETWORK = 0.6  # base "sent!" delay
DEFAULT_WINDOW_SECONDS = 60  # rate limiter window
DEFAULT_WINDOW_BUDGET = 18  # max messages per window


class BudgetExceeded(RuntimeError):
    """The per-window message budget was exhausted; slow down."""


class HumanPacing:
    """Enforces typing delays and a rolling message budget.

    Thread-safe so the HTTP server and TUI can share one session safely.
    """

    def __init__(
        self,
        typing_per_char: float = DEFAULT_TYPING_PER_CHAR,
        typing_max: float = DEFAULT_TYPING_MAX,
        network: float = DEFAULT_NETWORK,
        window_seconds: int = DEFAULT_WINDOW_SECONDS,
        window_budget: int = DEFAULT_WINDOW_BUDGET,
        seed: int | None = None,
    ) -> None:
        self.typing_per_char = typing_per_char
        self.typing_max = typing_max
        self.network = network
        self.window_seconds = window_seconds
        self.window_budget = window_budget
        self._rng = random.Random(seed)
        self._lock = threading.Lock()
        self._marks: deque[float] = deque(maxlen=window_budget + 1)

    def budget_remaining(self, now: float | None = None) -> int:
        now = time.monotonic() if now is None else now
        with self._lock:
            while self._marks and now - self._marks[0] > self.window_seconds:
                self._marks.popleft()
            return max(0, self.window_budget - len(self._marks))

    def typing_delay(self, text: str) -> float:
        return max(0.3, min(self.typing_per_char * len(text), self.typing_max))

    def _reserve(self, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        with self._lock:
            while self._marks and now - self._marks[0] > self.window_seconds:
                self._marks.popleft()
            if len(self._marks) >= self.window_budget:
                raise BudgetExceeded(
                    f"message budget exhausted ({self.window_budget}/"
                    f"{self.window_seconds}s); wait a bit"
                )
            self._marks.append(now)

    def before_send(self, text: str) -> None:
        """Called right before handing bytes to the host: reserve budget, sleep typing + network."""
        self._reserve()
        typing = self.typing_delay(text) * self._jitter(0.82, 1.18)
        network = self.network * self._jitter(0.7, 1.3)
        time.sleep(typing + network)

    def _jitter(self, low: float, high: float) -> float:
        return self._rng.uniform(low, high)


def now() -> float:
    return time.time()
