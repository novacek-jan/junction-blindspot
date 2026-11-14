"""Load secrets from the repo-root .env (or backend/.env). Keys are never hardcoded."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_loaded = False


def load_env() -> None:
    global _loaded
    if _loaded:
        return
    for env_file in (ROOT / ".env", ROOT / "backend" / ".env"):
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    _loaded = True
