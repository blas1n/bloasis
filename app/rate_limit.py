"""Rate limiting configuration.

Separate module to avoid circular imports between main.py and routers.
"""

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address


def _rate_limit_key(request: Request) -> str:
    """Extract user ID from JWT for rate limiting, fallback to IP."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        try:
            provider = request.app.state.auth_provider
            token = auth_header.removeprefix("Bearer ")
            user = provider.verify_token(token)
            user_id: str = user.id
            return user_id
        except Exception:
            pass
    result: str = get_remote_address(request)
    return result


limiter = Limiter(key_func=_rate_limit_key, default_limits=["60/minute"])
