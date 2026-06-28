from __future__ import annotations

import json
from pathlib import Path
from typing import Any

APP_DIR = Path(__file__).resolve().parent
STATE_DIR = APP_DIR / "state"
SETTINGS_FILE = STATE_DIR / "settings.json"
HISTORY_FILE = STATE_DIR / "history.json"


def _ensure_state_dir() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)


def load_json(path: Path, default: Any) -> Any:
    try:
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path: Path, data: Any) -> None:
    _ensure_state_dir()
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_settings() -> dict[str, Any]:
    return load_json(SETTINGS_FILE, {})


def save_settings(settings: dict[str, Any]) -> None:
    save_json(SETTINGS_FILE, settings)


def load_history() -> list[dict[str, Any]]:
    history = load_json(HISTORY_FILE, [])
    return history if isinstance(history, list) else []


def save_history(history: list[dict[str, Any]]) -> None:
    save_json(HISTORY_FILE, history[-100:])
