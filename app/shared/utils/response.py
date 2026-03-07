"""CamelCase JSON response for FastAPI.

Automatically converts snake_case dict keys to camelCase in all API responses.
"""

from decimal import Decimal
from typing import Any

from fastapi.responses import JSONResponse


def _to_camel(name: str) -> str:
    """Convert snake_case string to camelCase."""
    parts = name.split("_")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


def _convert(obj: Any) -> Any:
    """Recursively convert dict keys to camelCase and Decimals to strings."""
    if isinstance(obj, dict):
        return {_to_camel(k): _convert(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_convert(item) for item in obj]
    if isinstance(obj, Decimal):
        return str(obj)
    return obj


class CamelJSONResponse(JSONResponse):
    """JSONResponse that converts snake_case keys to camelCase."""

    def render(self, content: Any) -> bytes:
        return super().render(_convert(content))
