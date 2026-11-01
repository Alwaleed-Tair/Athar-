"""
Tiny in-memory throttles (single-process server). Used for login lockout,
e-mail resend cooldown and the public contact form.
"""
import threading
import time
from collections import defaultdict, deque

_LOCK = threading.Lock()
_FAILURES: dict[str, deque] = defaultdict(deque)
_HITS: dict[str, deque] = defaultdict(deque)


def login_locked(key: str, max_failures: int, window: int) -> int:
    """Seconds still locked (0 if not locked)."""
    now = time.time()
    with _LOCK:
        q = _FAILURES[key]
        while q and now - q[0] > window:
            q.popleft()
        if len(q) >= max_failures:
            return int(window - (now - q[0])) + 1
    return 0


def record_login_failure(key: str) -> None:
    with _LOCK:
        _FAILURES[key].append(time.time())


def clear_login_failures(key: str) -> None:
    with _LOCK:
        _FAILURES.pop(key, None)


def allow(key: str, limit: int, window: int) -> bool:
    """Generic sliding-window limiter: at most `limit` hits per `window` s."""
    now = time.time()
    with _LOCK:
        q = _HITS[key]
        while q and now - q[0] > window:
            q.popleft()
        if len(q) >= limit:
            return False
        q.append(now)
        return True


def reset_all() -> None:  # used by tests
    with _LOCK:
        _FAILURES.clear()
        _HITS.clear()
