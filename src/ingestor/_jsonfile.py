from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def read(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return dict(json.loads(path.read_text()))


def write(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data))
