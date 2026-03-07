"""Export OpenAPI schema from FastAPI app to JSON file."""
import json
import sys
from pathlib import Path

# Add workspace to path so app module can be found
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.main import app


def main() -> None:
    schema = app.openapi()
    output = Path(__file__).resolve().parent.parent / "openapi.json"
    output.write_text(json.dumps(schema, indent=2, default=str) + "\n")
    print(f"OpenAPI schema exported to {output}")


if __name__ == "__main__":
    main()
