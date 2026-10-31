"""Save / load tournaments as JSON (atomic write)."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from .models import Tournament


def save(t: Tournament, path: str | Path) -> None:
    path = Path(path)
    fd, tmp = tempfile.mkstemp(dir=path.parent or ".", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(t.to_dict(), f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def load(path: str | Path) -> Tournament:
    with open(path, encoding="utf-8") as f:
        return Tournament.from_dict(json.load(f))
