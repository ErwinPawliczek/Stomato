"""Write openapi.json at the repo root. CI fails if the committed file differs."""

import json
from pathlib import Path

from ngdesign.api.app import app

Path(__file__).resolve().parents[1].joinpath("openapi.json").write_text(
    json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"
)
