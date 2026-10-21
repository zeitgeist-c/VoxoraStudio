"""Voxora Studio loglama yapılandırması (konsol + dosya, UTF-8)."""
import logging
import os
import sys

from app.branding import LOG_FILENAME
from app.paths import logs_dir
from config import DEFAULT_LOG_DIR

_FMT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


def _log_dir() -> str:
    """Log dizini.

    Mutlak yol verilmişse o kullanılır. Aksi hâlde kullanıcı veri klasörü:
    donmuş pakette ``%LOCALAPPDATA%\\VoxoraStudio\\logs`` (Program Files'a
    yazma izni yok), kaynak kopyada depo kökündeki ``logs/``.
    """
    if os.path.isabs(DEFAULT_LOG_DIR):
        return DEFAULT_LOG_DIR
    return str(logs_dir())


LOG_FILE = os.path.join(_log_dir(), LOG_FILENAME)


def setup_logging():
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    try:
        from logging.handlers import RotatingFileHandler

        os.makedirs(os.path.dirname(LOG_FILE) or ".", exist_ok=True)
        handlers.insert(
            0, RotatingFileHandler(LOG_FILE, maxBytes=1_048_576, backupCount=3, encoding="utf-8")
        )
    except Exception:
        # Yazılamayan konumda uygulama açılmaya devam eder; log yalnız konsola gider.
        pass
    logging.basicConfig(level=logging.INFO, format=_FMT, handlers=handlers)
