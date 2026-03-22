"""Rate limiting configuration.

Separate module to avoid circular imports between main.py and routers.
"""

import jwt
from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from .config import settings


def _rate_limit_key(request: Request) -> str:
    """Extract user ID from JWT for rate limiting, fallback to IP."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        try:
            token = auth_header.removeprefix("Bearer ")
            payload = jwt.decode(
                token,
                settings.supabase_jwt_secret,
                algorithms=["HS256"],
                audience="authenticated",
            )
            sub: str | None = payload.get("sub")
            if sub:
                return sub
        except (jwt.InvalidTokenError, ValueError, KeyError):
            pass
    result: str = get_remote_address(request)
    return result


limiter = Limiter(key_func=_rate_limit_key, default_limits=["60/minute"])
