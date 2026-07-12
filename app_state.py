from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

APP_DIR = Path(__file__).resolve().parent
STATE_DIR = APP_DIR / "state"
SETTINGS_FILE = STATE_DIR / "settings.json"
HISTORY_FILE = STATE_DIR / "history.json"
log = logging.getLogger(__name__)


def _ensure_state_dir() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)


def load_json(path: Path, default: Any) -> Any:
    for candidate in (path, path.with_suffix(path.suffix + ".bak")):
        try:
            if candidate.exists():
                return json.loads(candidate.read_text(encoding="utf-8"))
        except Exception:
            log.exception("Durum dosyas? okunamad?: %s", candidate)
    return default


def save_json(path: Path, data: Any) -> None:
    _ensure_state_dir()
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    backup = path.with_suffix(path.suffix + ".bak")
    if path.exists():
        try:
            json.loads(path.read_text(encoding="utf-8"))
            shutil.copy2(path, backup)
        except Exception:
            log.warning("Ge?ersiz durum dosyas? yedeklenmedi: %s", path)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def load_settings() -> dict[str, Any]:
    settings = load_json(SETTINGS_FILE, {})
    return settings if isinstance(settings, dict) else {}


def save_settings(settings: dict[str, Any]) -> None:
    save_json(SETTINGS_FILE, settings)


def load_history() -> list[dict[str, Any]]:
    history = load_json(HISTORY_FILE, [])
    return history if isinstance(history, list) else []


def save_history(history: list[dict[str, Any]]) -> None:
    save_json(HISTORY_FILE, history[-100:])
