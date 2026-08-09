"""Voxora Studio loglama yapılandırması (konsol + dosya, UTF-8)."""
import logging
import os

from app.branding import LOG_FILENAME
from config import DEFAULT_LOG_DIR

LOG_FILE = os.path.join(DEFAULT_LOG_DIR, LOG_FILENAME)
_FMT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


def setup_logging():
    os.makedirs(DEFAULT_LOG_DIR, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format=_FMT,
        handlers=[
            logging.FileHandler(LOG_FILE, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
