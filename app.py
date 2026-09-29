"""
Voxora Studio - PyQt6 uygulaması giriş noktası.

Sınıflar `app/` paketine taşındı:
  - app.constants: LANGUAGES, PRESETS, REFERENCE_SAMPLE_TEXT
  - app.dialogs: ModelLoadDialog, VoiceGuideDialog, SynthesisDialog
  - app.workers: TqdmProgressBridge, SynthWorker, EngineLoader
  - app.main_window: MainWindow
"""
from __future__ import annotations

import logging
import sys

from PyQt6.QtWidgets import QApplication

from app.branding import APP_USER_MODEL_ID, DISPLAY_NAME, TECHNICAL_NAME
from app.main_window import MainWindow
from app.theme import application_icon
from logging_config import setup_logging

log = logging.getLogger(__name__)


def _log_uncaught(exc_type, exc_value, exc_tb):
    """Yakalanmayan istisnayı loga yaz; --noconsole çalıştırmada da iz kalsın."""
    log.critical("Yakalanmayan istisna", exc_info=(exc_type, exc_value, exc_tb))


def main():
    setup_logging()
    sys.excepthook = _log_uncaught
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
        except Exception:
            log.debug("Windows AppUserModelID ayarlanamadı.", exc_info=True)
    app = QApplication([])
    app.setApplicationName(TECHNICAL_NAME)
    app.setApplicationDisplayName(DISPLAY_NAME)
    app.setWindowIcon(application_icon())
    win = MainWindow()
    win.show()
    app.exec()


if __name__ == "__main__":
    main()
