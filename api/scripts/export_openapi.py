"""Export the FastAPI OpenAPI spec to a JSON file.

Usage: uv run python scripts/export_openapi.py [output_path]
Default output: openapi.json (gitignored; consumed by the web client generator).
"""

import json
import sys
from pathlib import Path

from app.main import app


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("openapi.json")
    out.write_text(json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n")
    sys.stdout.write(f"wrote {out}\n")


if __name__ == "__main__":
    main()
