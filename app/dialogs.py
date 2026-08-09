"""Voxora Studio dialog windows.

The dialogs keep their public signals, attributes and progress methods stable,
while sharing the same cards, headers and action hierarchy as the main window.
All visual styling lives in :mod:`app.theme`.
"""
from __future__ import annotations

from PyQt6.QtCore import QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QVBoxLayout,
)

from .constants import REFERENCE_SAMPLE_TEXT
from .theme import application_icon
from .widgets import ActionButton, PageHeader, SectionCard, StatusPill

__all__ = ["ModelLoadDialog", "VoiceGuideDialog", "SynthesisDialog"]


def _dialog_actions(parent: QDialog) -> tuple[QFrame, QHBoxLayout]:
    """Create the one canonical action row used by a dialog."""
    container = QFrame(parent)
    container.setObjectName("dialogActions")
    layout = QHBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)
    layout.addStretch(1)
    return container, layout


class ModelLoadDialog(QDialog):
    """Model indirme/yükleme sürecini kullanıcıya görünür yapar."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("modelLoadDialog")
        self.setWindowIcon(application_icon())
        self.setWindowTitle("Model hazırlanıyor")
        self.setModal(False)
        self.resize(600, 390)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 22)
        root.setSpacing(18)

        self.state_pill = StatusPill("Hazırlanıyor", "info", self)
        self.header = PageHeader(
            "Ses motoru hazırlanıyor...",
            "Yerel üretim motoru kullanıma hazırlanıyor.",
            self.state_pill,
            self,
        )
        self.header.setProperty("context", "dialog")
        self.title_label = self.header.title_label
        self.title_label.setObjectName("dialogTitle")
        self.header.subtitle_label.setObjectName("dialogSubtitle")
        root.addWidget(self.header)

        self.body_card = SectionCard(parent=self)
        self.body_card.setProperty("context", "dialogBody")

        self.status_label = QLabel(
            "İlk çalıştırmada model dosyaları indirilebilir; bu birkaç dakika sürebilir.",
            self.body_card,
        )
        self.status_label.setObjectName("dialogStatus")
        self.status_label.setWordWrap(True)
        self.body_card.content_layout.addWidget(self.status_label)

        self.progress = QProgressBar(self.body_card)
        self.progress.setObjectName("dialogProgress")
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        self.body_card.content_layout.addWidget(self.progress)

        self.detail = QPlainTextEdit(self.body_card)
        self.detail.setObjectName("dialogDetails")
        self.detail.setReadOnly(True)
        self.detail.setMaximumBlockCount(200)
        self.detail.setPlaceholderText("Model hazırlama ayrıntıları burada görünecek.")
        self.body_card.content_layout.addWidget(self.detail, stretch=1)
        root.addWidget(self.body_card, stretch=1)

        actions, action_layout = _dialog_actions(self)
        self.close_button = ActionButton(
            "Kapat",
            actions,
            variant="primary",
            icon_name="close",
        )
        self.close_button.setProperty("dialogAction", "close")
        self.close_button.setEnabled(False)
        self.close_button.clicked.connect(self.accept)
        action_layout.addWidget(self.close_button)
        root.addWidget(actions)

        self._seconds = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(1000)
        self.finished.connect(lambda _result: self._timer.stop())

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
        self.state_pill.setText("Hazır")
        self.state_pill.set_tone("success")
        self.add_status(message)
        self.close_button.set_icon_name("check")
        self.close_button.setEnabled(True)
        QTimer.singleShot(900, self.accept)

    def finish_error(self, message: str):
        self._timer.stop()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.title_label.setText("Model yüklenemedi")
        self.state_pill.setText("Hata")
        self.state_pill.set_tone("danger")
        self.add_status(message)
        self.close_button.setEnabled(True)


class VoiceGuideDialog(QDialog):
    """Referans ses kaydı için kısa rehber penceresi."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("voiceGuideDialog")
        self.setWindowIcon(application_icon())
        self.setWindowTitle("Ses Örneği Rehberi")
        self.resize(680, 520)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 22)
        root.setSpacing(18)

        self.header = PageHeader(
            "Daha iyi benzerlik için ses örneği",
            "Temiz ve doğal bir referans, üretilen sesin karakterini belirler.",
            parent=self,
        )
        self.header.setProperty("context", "dialog")
        self.header.title_label.setObjectName("dialogTitle")
        self.header.subtitle_label.setObjectName("dialogSubtitle")
        root.addWidget(self.header)

        guidance_card = SectionCard(
            "Kayıt standardı",
            "Önerilen süre 5–20 saniye; ideal hedef 10–15 saniye temiz, tek kişilik konuşmadır.",
            self,
        )
        guidance_card.setProperty("context", "dialogBody")
        tips = QLabel(
            "• Tek kişi konuşsun, arka plan sessiz olsun.\n"
            "• Müzik, yankı ve mikrofon patlaması olmasın.\n"
            "• Üreteceğin tarza yakın bir tonla oku.\n"
            "• Çok hızlı okuma; doğal duraklamalar bırak.",
            guidance_card,
        )
        tips.setObjectName("dialogGuidance")
        tips.setWordWrap(True)
        guidance_card.content_layout.addWidget(tips)
        root.addWidget(guidance_card)

        sample_card = SectionCard(
            "Okunacak örnek metin",
            "Kaydı alırken aşağıdaki metni doğal bir ritimle oku.",
            self,
        )
        sample_card.setProperty("context", "dialogBody")
        self.sample_text = QPlainTextEdit(sample_card)
        self.sample_text.setObjectName("dialogDetails")
        self.sample_text.setPlainText(REFERENCE_SAMPLE_TEXT)
        self.sample_text.setReadOnly(True)
        sample_card.content_layout.addWidget(self.sample_text, stretch=1)
        root.addWidget(sample_card, stretch=1)

        actions, action_layout = _dialog_actions(self)
        self.btn_copy = ActionButton(
            "Metni Kopyala",
            actions,
            variant="secondary",
            icon_name="copy",
        )
        self.btn_copy.setProperty("dialogAction", "copy")
        self.btn_close = ActionButton(
            "Tamam",
            actions,
            variant="primary",
            icon_name="check",
        )
        self.btn_close.setProperty("dialogAction", "close")
        self.btn_copy.clicked.connect(self.copy_text)
        self.btn_close.clicked.connect(self.accept)
        action_layout.addWidget(self.btn_copy)
        action_layout.addWidget(self.btn_close)
        root.addWidget(actions)

    def copy_text(self):
        QApplication.clipboard().setText(REFERENCE_SAMPLE_TEXT)
        self.btn_copy.setText("Kopyalandı")
        self.btn_copy.set_icon_name("check")


class SynthesisDialog(QDialog):
    """Ses üretim sürecini görünür yapar."""

    cancel_requested = pyqtSignal()

    def __init__(self, total_chunks: int, parent=None):
        super().__init__(parent)
        self.setObjectName("synthesisDialog")
        self.setWindowIcon(application_icon())
        self.total_chunks = max(total_chunks, 1)
        self.setWindowTitle("Ses üretiliyor")
        self.setModal(False)
        self.resize(600, 410)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 22)
        root.setSpacing(18)

        self.state_pill = StatusPill("Üretiliyor", "info", self)
        self.header = PageHeader(
            "Ses üretimi başladı",
            "Metin, yerel ses motoruyla parça parça işleniyor.",
            self.state_pill,
            self,
        )
        self.header.setProperty("context", "dialog")
        self.title_label = self.header.title_label
        self.title_label.setObjectName("dialogTitle")
        self.header.subtitle_label.setObjectName("dialogSubtitle")
        root.addWidget(self.header)

        self.body_card = SectionCard(parent=self)
        self.body_card.setProperty("context", "dialogBody")

        self.status_label = QLabel(f"Metin {self.total_chunks} parçaya bölündü.", self.body_card)
        self.status_label.setObjectName("dialogStatus")
        self.status_label.setWordWrap(True)
        self.body_card.content_layout.addWidget(self.status_label)

        self.progress = QProgressBar(self.body_card)
        self.progress.setObjectName("dialogProgress")
        self.progress.setRange(0, self.total_chunks * 1000)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.body_card.content_layout.addWidget(self.progress)

        self.detail = QPlainTextEdit(self.body_card)
        self.detail.setObjectName("dialogDetails")
        self.detail.setReadOnly(True)
        self.detail.setMaximumBlockCount(300)
        self.detail.setPlaceholderText("Üretim ayrıntıları burada görünecek.")
        self.body_card.content_layout.addWidget(self.detail, stretch=1)
        root.addWidget(self.body_card, stretch=1)

        actions, action_layout = _dialog_actions(self)
        self.cancel_button = ActionButton(
            "Üretimi Durdur",
            actions,
            variant="destructive",
            icon_name="stop",
        )
        self.cancel_button.setProperty("dialogAction", "cancel")
        self.cancel_button.clicked.connect(self._request_cancel)
        self.close_button = ActionButton(
            "Kapat",
            actions,
            variant="primary",
            icon_name="close",
        )
        self.close_button.setProperty("dialogAction", "close")
        self.close_button.setEnabled(False)
        self.close_button.clicked.connect(self.accept)
        action_layout.addWidget(self.cancel_button)
        action_layout.addWidget(self.close_button)
        root.addWidget(actions)

        self._seconds = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(1000)
        self.finished.connect(lambda _result: self._timer.stop())

    def _tick(self):
        self._seconds += 1
        self.title_label.setText(f"Ses üretiliyor... ({self._seconds} sn)")

    def _request_cancel(self):
        self.cancel_button.setEnabled(False)
        self.state_pill.setText("Durduruluyor")
        self.state_pill.set_tone("warning")
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
        self.state_pill.setText("Hazır")
        self.state_pill.set_tone("success")
        self.status_label.setText(message)
        self.detail.appendPlainText(message)
        self.cancel_button.setEnabled(False)
        self.close_button.set_icon_name("check")
        self.close_button.setEnabled(True)
        QTimer.singleShot(1100, self.accept)

    def finish_error(self, message: str):
        self._timer.stop()
        was_cancelled = "durdur" in message.lower()
        self.title_label.setText("Üretim durduruldu" if was_cancelled else "Üretim başarısız")
        self.state_pill.setText("Durduruldu" if was_cancelled else "Hata")
        self.state_pill.set_tone("warning" if was_cancelled else "danger")
        self.status_label.setText(message)
        self.detail.appendPlainText(message)
        self.cancel_button.setEnabled(False)
        self.close_button.setEnabled(True)
