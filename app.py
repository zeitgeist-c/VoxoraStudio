"""
txttoTTS - PyQt6 uygulaması giriş noktası.

Sınıflar `app/` paketine taşındı:
  - app.constants: LANGUAGES, PRESETS, REFERENCE_SAMPLE_TEXT
  - app.dialogs: ModelLoadDialog, VoiceGuideDialog, SynthesisDialog
  - app.workers: TqdmProgressBridge, SynthWorker, EngineLoader
  - app.main_window: MainWindow
"""
from __future__ import annotations

import logging

from PyQt6.QtWidgets import QApplication

from app.main_window import MainWindow
from logging_config import setup_logging

log = logging.getLogger(__name__)


def main():
    setup_logging()
    app = QApplication([])
    win = MainWindow()
    win.show()
    app.exec()


if __name__ == "__main__":
    main()