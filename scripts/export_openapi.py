"""Export OpenAPI schema from FastAPI app to JSON file.

Usage: PYTHONPATH=/workspace python scripts/export_openapi.py
"""
import json
from pathlib import Path

from app.main import app


def main() -> None:
    schema = app.openapi()
    output = Path(__file__).resolve().parent.parent / "openapi.json"
    output.write_text(json.dumps(schema, indent=2, default=str) + "\n")
    print(f"OpenAPI schema exported to {output}")


if __name__ == "__main__":
    main()
