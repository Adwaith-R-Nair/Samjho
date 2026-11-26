"""Call limits for the public demo link: protect strangers' phones, the caller ID and the budget.

Per number: 1 call per 30 min and 3 per 24 h, keyed by a salted hash (the raw number is never stored).
Per IP: 3 calls per hour. Global: 2 calls at once and 40 per 24 h. The owner's own numbers skip the per number
and per IP limits (they still count toward the global ones). All state is in memory: a restart resets it.
"""

import hashlib
import hmac
import os
import secrets
import threading
import time
from collections import deque
from collections.abc import Callable, Iterable

HOUR = 3600
DAY = 24 * HOUR


class CallLimiter:
    def __init__(
        self,
        *,
        owner_numbers: Iterable[str] = (),
        salt: bytes | None = None,
        clock: Callable[[], float] = time.time,
        number_cooldown: float = 30 * 60,
        number_per_day: int = 3,
        ip_per_hour: int = 3,
        max_concurrent: int = 2,
        global_per_day: int = 40,
        ring_hold_secs: float = 90,
    ) -> None:
        self._salt = salt or os.urandom(16)
        self._owners = {self.key(n) for n in owner_numbers if n}
        self._clock = clock
        self.number_cooldown = number_cooldown
        self.number_per_day = number_per_day
        self.ip_per_hour = ip_per_hour
        self.max_concurrent = max_concurrent
        self.global_per_day = global_per_day
        self.ring_hold_secs = ring_hold_secs
        self._numbers: dict[str, deque[float]] = {}
        self._ips: dict[str, deque[float]] = {}
        self._calls: deque[float] = deque()
        self._active: dict[str, float] = {}  # reservation id -> expiry
        self._lock = threading.Lock()

    def key(self, number: str) -> str:
        return hmac.new(self._salt, number.encode(), hashlib.sha256).hexdigest()

    def is_owner(self, number: str) -> bool:
        return self.key(number) in self._owners

    @staticmethod
    def _recent(times: deque[float], now: float, window: float) -> int:
        while times and now - times[0] >= window:
            times.popleft()
        return len(times)

    def _active_count(self, now: float) -> int:
        for rid in [r for r, exp in self._active.items() if exp <= now]:
            del self._active[rid]
        return len(self._active)

    def reserve(self, number: str, ip: str) -> tuple[str | None, str]:
        """Checks every limit and records the call. Returns (reservation id, "") or (None, reason)."""
        with self._lock:
            now = self._clock()
            owner = self.is_owner(number)
            num = self._numbers.setdefault(self.key(number), deque())
            ip_times = self._ips.setdefault(ip, deque())
            self._recent(num, now, DAY)
            if not owner:
                if num and now - num[-1] < self.number_cooldown:
                    mins = int((self.number_cooldown - (now - num[-1])) // 60) + 1
                    return None, f"This number was called recently. Try again in {mins} min."
                if len(num) >= self.number_per_day:
                    return None, "This number has had its demo calls for today."
                if self._recent(ip_times, now, HOUR) >= self.ip_per_hour:
                    return None, "Too many calls from this network. Try again in an hour."
            if self._active_count(now) >= self.max_concurrent:
                return None, "Two demo calls are already running. Try again in a few minutes."
            if self._recent(self._calls, now, DAY) >= self.global_per_day:
                return None, "The demo has used its calls for today. Typing still works."
            num.append(now)
            ip_times.append(now)
            self._calls.append(now)
            rid = secrets.token_hex(8)
            # Held until the call is answered (then held for the call) or the ring times out.
            self._active[rid] = now + self.ring_hold_secs
            return rid, ""

    def hold(self, rid: str, secs: float) -> None:
        """The call connected: keep its slot for up to `secs`."""
        with self._lock:
            if rid in self._active:
                self._active[rid] = self._clock() + secs

    def release(self, rid: str) -> None:
        with self._lock:
            self._active.pop(rid, None)

    def active(self) -> int:
        with self._lock:
            return self._active_count(self._clock())
