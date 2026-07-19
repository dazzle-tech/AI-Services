"""Per-identity sliding-window rate limiter backed by Redis."""
import logging
import time
from typing import Optional

from fastapi import HTTPException

from app.core.config import settings

logger = logging.getLogger(__name__)

try:
    import redis

    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False


class RateLimiter:
    """Simple sliding-window rate limiter using Redis sorted sets."""

    def __init__(
        self,
        prefix: str = "medai:ratelimit",
        max_requests: Optional[int] = None,
        window_seconds: Optional[int] = None,
    ):
        self.prefix = prefix
        self.max_requests = max_requests or settings.rate_limit_max_requests
        self.window_seconds = window_seconds or settings.rate_limit_window_seconds
        self._client = None
        self._connected = False
        self._fallback_counts: dict[str, list[float]] = {}

        if not REDIS_AVAILABLE:
            logger.warning("Redis unavailable for rate limiting; using in-process fallback")
            return

        try:
            self._client = redis.Redis(
                host=settings.redis_host,
                port=settings.redis_port,
                db=settings.redis_db,
                decode_responses=True,
                socket_connect_timeout=3,
                socket_timeout=3,
            )
            self._client.ping()
            self._connected = True
        except Exception as exc:
            logger.warning("Rate limiter Redis connection failed: %s", exc)

    def _key(self, identity_key: str) -> str:
        return f"{self.prefix}:{identity_key}"

    def check(self, identity_key: str, *, channel: str = "web") -> None:
        """
        Enforce rate limit for identity_key (user_id or phone number).

        Raises HTTPException 429 when limit exceeded.
        """
        key = self._key(f"{channel}:{identity_key}")
        now = time.time()
        window_start = now - self.window_seconds

        if self._connected and self._client:
            try:
                pipe = self._client.pipeline()
                pipe.zremrangebyscore(key, 0, window_start)
                pipe.zadd(key, {str(now): now})
                pipe.zcard(key)
                pipe.expire(key, self.window_seconds + 1)
                _, _, count, _ = pipe.execute()
                if count > self.max_requests:
                    logger.warning("Rate limit exceeded for %s (%s requests)", key, count)
                    raise HTTPException(
                        status_code=429,
                        detail="Rate limit exceeded. Please try again shortly.",
                    )
                return
            except HTTPException:
                raise
            except Exception as exc:
                logger.warning("Redis rate limit check failed: %s", exc)

        # In-process fallback
        timestamps = [t for t in self._fallback_counts.get(key, []) if t > window_start]
        timestamps.append(now)
        self._fallback_counts[key] = timestamps
        if len(timestamps) > self.max_requests:
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded. Please try again shortly.",
            )


_rate_limiter: Optional[RateLimiter] = None


def get_rate_limiter() -> RateLimiter:
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter()
    return _rate_limiter
