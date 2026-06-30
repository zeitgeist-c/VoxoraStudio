from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path

__all__ = ["safe_filename_from_text", "unique_path", "safe_remove_to_trash"]

_SAFE_RE = re.compile(r"[^\w\-.]+", re.UNICODE)


def safe_filename_from_text(text: str, suffix: str = ".wav") -> str:
    words = text.strip().split()
    stem = "-".join(words[:7]) if words else "ses"
    stem = _SAFE_RE.sub("-", stem).strip("-_.").lower() or "ses"
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return f"{stem[:60]}_{timestamp}{suffix}"


def unique_path(directory: str | Path, filename: str) -> Path:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    candidate = directory / filename
    if not candidate.exists():
        return candidate
    stem = candidate.stem
    suffix = candidate.suffix
    for index in range(2, 1000):
        next_candidate = directory / f"{stem}_{index}{suffix}"
        if not next_candidate.exists():
            return next_candidate
    return directory / f"{stem}_{datetime.now().strftime('%f')}{suffix}"


def safe_remove_to_trash(path: str) -> tuple[bool, str | None]:
    """send2trash varsa Geri Dönüşüm'e taşı; yoksa os.remove.

    Returns:
        (ok, error_message). hata yoksa error_message None.
    """
    if not path or not path.strip():
        return False, "Dosya yolu boş."
    if not os.path.exists(path):
        return False, f"Dosya bulunamadı: {path}"
    try:
        from send2trash import send2trash
        send2trash(path)
        return True, None
    except ImportError:
        try:
            os.remove(path)
            return True, None
        except Exception as e:
            return False, str(e)
    except Exception as e:
        return False, str(e)
