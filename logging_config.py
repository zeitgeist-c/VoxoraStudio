"""
txttoTTS - loglama (konsol + dosya, UTF-8).
"""
import logging
import os

from config import DEFAULT_LOG_DIR

LOG_FILE = os.path.join(DEFAULT_LOG_DIR, "txttoTTS.log")
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
