import time
from collections import defaultdict
from threading import Lock

from fastapi import HTTPException, Request, status


class InMemoryRateLimiter:
    """Fixed-window limiter keyed by client IP. Process-local by design — the
    API runs as a single Uvicorn worker (see docker/entrypoint.sh), so this
    is accurate without needing Redis. Host-level fail2ban is the recommended
    second layer (see README)."""

    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: dict[str, list[float]] = defaultdict(list)
        self._lock = Lock()

    def check(self, key: str) -> None:
        now = time.monotonic()
        cutoff = now - self.window_seconds
        with self._lock:
            hits = self._hits[key]
            while hits and hits[0] < cutoff:
                hits.pop(0)
            if len(hits) >= self.max_requests:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="too many requests, try again later",
                )
            hits.append(now)

    def reset(self) -> None:
        """Test-only escape hatch — the limiter is a process-local singleton,
        so without this every test sharing a client IP would drain the same
        bucket across the whole session."""
        with self._lock:
            self._hits.clear()


login_rate_limiter = InMemoryRateLimiter(max_requests=10, window_seconds=60)
register_rate_limiter = InMemoryRateLimiter(max_requests=5, window_seconds=300)


def rate_limit_dependency(limiter: InMemoryRateLimiter):
    def _dependency(request: Request) -> None:
        client_ip = request.client.host if request.client else "unknown"
        limiter.check(client_ip)

    return _dependency
