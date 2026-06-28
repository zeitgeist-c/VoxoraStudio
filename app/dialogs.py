"""
txttoTTS - PyQt6 dialog sınıfları.

Üç bağımsız modal-olmayan pencere:
  - ModelLoadDialog: motor yükleme süreci
  - VoiceGuideDialog: referans ses kayıt rehberi
  - SynthesisDialog: üretim ilerleme + iptal
"""
from __future__ import annotations

from PyQt6.QtCore import QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

from .constants import REFERENCE_SAMPLE_TEXT

__all__ = ["ModelLoadDialog", "VoiceGuideDialog", "SynthesisDialog"]


class ModelLoadDialog(QDialog):
    """Model indirme/yükleme sürecini kullanıcıya görünür yapar."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Model hazırlanıyor")
        self.setModal(False)
        self.resize(560, 320)

        root = QVBoxLayout(self)
        self.title_label = QLabel("Ses motoru hazırlanıyor...")
        self.title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        root.addWidget(self.title_label)

        self.status_label = QLabel("İlk çalıştırmada model dosyaları indirilebilir; bu birkaç dakika sürebilir.")
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        root.addWidget(self.progress)

        self.detail = QPlainTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setMaximumBlockCount(200)
        root.addWidget(self.detail, stretch=1)

        self.close_button = QPushButton("Kapat")
        self.close_button.setEnabled(False)
        self.close_button.clicked.connect(self.accept)
        root.addWidget(self.close_button)

        self._seconds = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(1000)

    def _tick(self):
        self._seconds += 1
        self.title_label.setText(f"Ses motoru hazırlanıyor... ({self._seconds} sn)")

    def add_status(self, message: str):
        self.status_label.setText(message)
        self.detail.appendPlainText(message)

    def finish_ok(self, message: str):
        self._timer.stop()
        self.progress.setRange(0, 1)
        self.progress.setValue(1)
        self.title_label.setText("Model hazır")
        self.add_status(message)
        self.close_button.setEnabled(True)
        QTimer.singleShot(900, self.accept)

    def finish_error(self, message: str):
        self._timer.stop()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.title_label.setText("Model yüklenemedi")
        self.add_status(message)
        self.close_button.setEnabled(True)


class VoiceGuideDialog(QDialog):
    """Referans ses kaydı için kısa rehber penceresi."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Ses Örneği Rehberi")
        self.resize(640, 420)

        root = QVBoxLayout(self)
        title = QLabel("Daha iyi benzerlik için ses örneği")
        title.setStyleSheet("font-weight: bold; font-size: 15px;")
        root.addWidget(title)

        summary = QLabel("Önerilen süre: 5-20 saniye. İdeal hedef: 10-15 saniye temiz, tek kişilik konuşma.")
        summary.setWordWrap(True)
        root.addWidget(summary)

        tips = QLabel(
            "Kayıt ipuçları:\n"
            "- Tek kişi konuşsun, arka plan sessiz olsun.\n"
            "- Müzik, yankı ve mikrofon patlaması olmasın.\n"
            "- Üreteceğin tarza yakın bir tonla oku.\n"
            "- Çok hızlı okuma; doğal duraklamalar bırak."
        )
        tips.setWordWrap(True)
        root.addWidget(tips)

        sample_label = QLabel("Okunacak örnek metin")
        sample_label.setStyleSheet("font-weight: bold;")
        root.addWidget(sample_label)

        self.sample_text = QPlainTextEdit()
        self.sample_text.setPlainText(REFERENCE_SAMPLE_TEXT)
        self.sample_text.setReadOnly(True)
        root.addWidget(self.sample_text, stretch=1)

        buttons = QHBoxLayout()
        self.btn_copy = QPushButton("Metni Kopyala")
        self.btn_close = QPushButton("Tamam")
        self.btn_copy.clicked.connect(self.copy_text)
        self.btn_close.clicked.connect(self.accept)
        buttons.addWidget(self.btn_copy)
        buttons.addWidget(self.btn_close)
        root.addLayout(buttons)

    def copy_text(self):
        QApplication.clipboard().setText(REFERENCE_SAMPLE_TEXT)
        self.btn_copy.setText("Kopyalandı")


class SynthesisDialog(QDialog):
    """Ses üretim sürecini görünür yapar."""

    cancel_requested = pyqtSignal()

    def __init__(self, total_chunks: int, parent=None):
        super().__init__(parent)
        self.total_chunks = max(total_chunks, 1)
        self.setWindowTitle("Ses üretiliyor")
        self.setModal(False)
        self.resize(560, 320)

        root = QVBoxLayout(self)
        self.title_label = QLabel("Ses üretimi başladı")
        self.title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        root.addWidget(self.title_label)

        self.status_label = QLabel(f"Metin {self.total_chunks} parçaya bölündü.")
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)

        self.progress = QProgressBar()
        self.progress.setRange(0, self.total_chunks * 1000)
        self.progress.setValue(0)
        root.addWidget(self.progress)

        self.detail = QPlainTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setMaximumBlockCount(300)
        root.addWidget(self.detail, stretch=1)

        button_row = QHBoxLayout()
        self.cancel_button = QPushButton("Üretimi Durdur")
        self.cancel_button.clicked.connect(self._request_cancel)
        self.close_button = QPushButton("Kapat")
        self.close_button.setEnabled(False)
        self.close_button.clicked.connect(self.accept)
        button_row.addWidget(self.cancel_button)
        button_row.addWidget(self.close_button)
        root.addLayout(button_row)

        self._seconds = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(1000)

    def _tick(self):
        self._seconds += 1
        self.title_label.setText(f"Ses üretiliyor... ({self._seconds} sn)")

    def _request_cancel(self):
        self.cancel_button.setEnabled(False)
        self.status_label.setText("Durdurma isteği alındı. Üretim kesiliyor...")
        self.detail.appendPlainText("Durdurma isteği alındı. Gerekirse işlem zorla kesilecek.")
        self.cancel_requested.emit()

    def chunk_started(self, index: int, total: int, text: str):
        preview = text.replace("\n", " ").strip()
        if len(preview) > 120:
            preview = preview[:117] + "..."
        self.progress.setRange(0, total * 1000)
        self.progress.setValue((index - 1) * 1000)
        self.status_label.setText(f"Parça {index}/{total} işleniyor...")
        self.detail.appendPlainText(f"Parça {index}/{total} başladı: {preview}")

    def sampling_progress(
        self,
        index: int,
        total_chunks: int,
        percent: int,
        current: int,
        total_steps: int,
        elapsed: str,
        remaining: str,
        rate: str,
    ):
        value = (index - 1) * 1000 + int(percent * 10)
        self.progress.setRange(0, total_chunks * 1000)
        self.progress.setValue(min(value, total_chunks * 1000))
        rate_text = f" - {rate}" if rate else ""
        self.status_label.setText(
            f"Parça {index}/{total_chunks}: %{percent} ({current}/{total_steps}) | "
            f"Geçen: {elapsed} | Kalan: {remaining}{rate_text}"
        )

    def chunk_done(self, done: int, total: int, seconds: float):
        self.progress.setRange(0, total * 1000)
        self.progress.setValue(done * 1000)
        self.status_label.setText(f"Parça {done}/{total} tamamlandı ({seconds:.1f} sn).")
        self.detail.appendPlainText(f"Parça {done}/{total} tamamlandı: {seconds:.1f} sn")

    def finish_ok(self, message: str):
        self._timer.stop()
        self.progress.setValue(self.progress.maximum())
        self.title_label.setText("Ses hazır")
        self.status_label.setText(message)
        self.detail.appendPlainText(message)
        self.cancel_button.setEnabled(False)
        self.close_button.setEnabled(True)
        QTimer.singleShot(1100, self.accept)

    def finish_error(self, message: str):
        self._timer.stop()
        title = "Üretim durduruldu" if "durdur" in message.lower() else "Üretim başarısız"
        self.title_label.setText(title)
        self.status_label.setText(message)
        self.detail.appendPlainText(message)
        self.cancel_button.setEnabled(False)
        self.close_button.setEnabled(True)