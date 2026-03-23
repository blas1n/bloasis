"""Rate limiting configuration.

Separate module to avoid circular imports between main.py and routers.
"""

import jwt
from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address


def _rate_limit_key(request: Request) -> str:
    """Extract user ID from JWT for rate limiting, fallback to IP.

    Uses unverified decode (no signature check) — this is intentional.
    Rate limiting only needs a stable key per user, not cryptographic proof.
    """
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        try:
            token = auth_header.removeprefix("Bearer ")
            payload = jwt.decode(token, options={"verify_signature": False})
            sub = payload.get("sub")
            if isinstance(sub, str):
                return sub
        except Exception:
            pass
    result: str = get_remote_address(request)
    return result


limiter = Limiter(key_func=_rate_limit_key, default_limits=["60/minute"])
