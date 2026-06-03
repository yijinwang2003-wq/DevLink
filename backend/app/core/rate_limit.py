import os

from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address


def rate_limit_enabled() -> bool:
    return os.getenv("DISABLE_RATE_LIMITING", "").lower() not in {"1", "true", "yes"}


limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["100/minute"],
    enabled=rate_limit_enabled(),
)


async def rate_limit_exceeded_handler(
    request: Request, exc: RateLimitExceeded
) -> JSONResponse:
    return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded"})
