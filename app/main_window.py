"""
txttoTTS - PyQt6 ana pencere.

Sade akış:
  - Metni yaz / panodan yapıştır
  - Üret
  - Çal / durdur / WAV-MP3 kaydet
  - Ayarlar ve ses örneği
  - Çıktı geçmişi

Dialog'lar `dialogs.py`, arka plan iş parçacıkları `workers.py`, sabitler
`constants.py` üzerinden gelir. Bu dosya yalnızca orkestrasyon ve UI kurulumu
içerir.
"""
from __future__ import annotations

import logging
import os
import re
import subprocess

import numpy as np
import soundfile as sf
from PyQt6.QtCore import QThread, QTimer, Qt
from PyQt6.QtGui import QColor, QFont, QKeySequence, QPalette, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

import audio_player
from app_state import load_history, load_settings, save_history, save_settings
import chunker
from config import DEFAULT_OUTPUT_DIR
from file_utils import safe_filename_from_text, safe_remove_to_trash, unique_path

from .constants import (
    CONFIRM_CHUNK_COUNT,
    LANGUAGE_SAMPLES,
    LANGUAGES,
    PRESETS,
    WARN_CHUNK_COUNT,
)
from .dialogs import ModelLoadDialog, SynthesisDialog, VoiceGuideDialog
from .workers import EngineLoader, SynthWorker

__all__ = ["MainWindow", "estimate_duration_range", "trim_leading_silence", "queue_split_lines", "apply_theme"]

log = logging.getLogger(__name__)


def estimate_duration_range(
    words: int, parts: int, speed: float, pause: float
) -> tuple[int, int]:
    """Saf süre tahmini (spinbox'sız, unit test edilebilir).

    Args:
        words: Kelime sayısı.
        parts: Chunk sayısı.
        speed: Konuşma hızı çarpanı (0.60-1.60).
        pause: Chunk arası duraklama (saniye).

    Returns:
        (min_saniye, max_saniye) tahmini aralığı.
    """
    if words <= 0:
        return 0, 0
    safe_speed = max(float(speed), 0.01)
    raw_min = words / 170 * 60
    raw_max = words / 130 * 60
    adj_min = raw_min / safe_speed
    adj_max = raw_max / safe_speed
    n_pauses = max(0, parts - 1)
    final_min = adj_min
    final_max = adj_max + n_pauses * float(pause)
    return max(1, round(final_min)), max(1, round(final_max))


def trim_leading_silence(
    wav: "torch.Tensor",
    sr: int,
    threshold: float = 0.005,
    max_trim_ms: int = 500,
    pre_buffer_ms: int = 20,
) -> "torch.Tensor":
    """Sentez çıktısının başındaki sessiz kısmı kırp.

    Mutlak genlik eşiği yöntemiyle ilk sesli sample'i bulur ve öncesini atar.
    Maks. ``max_trim_ms`` kırpılır; kırpma noktasından ``pre_buffer_ms`` kadar
    önce tutulur (atak geçişini yumuşatır). Tüm koşullar koruyucu: girdi
    zayıfsa (sr <= 0, boş, hepsi sessiz) orijinali döner.

    Args:
        wav: Torch tensor, shape (1, samples) veya (samples,).
        sr: Sample rate (Hz).
        threshold: Genlik eşiği (0.0-1.0 normalize).
        max_trim_ms: Bu kadar ms'den fazla kırpma; üstü sınır.
        pre_buffer_ms: Kırpma noktası öncesi korunacak tampon (ms).

    Returns:
        Kırpılmış (veya koşulsuz orijinal) torch tensor. Cihaz/dtype korunur.
    """
    import torch

    if wav is None or sr is None or sr <= 0:
        return wav
    numel = wav.shape[-1] if wav.dim() >= 1 else 0
    if numel == 0:
        return wav
    data = wav.squeeze().detach().cpu().contiguous()
    if data.dim() != 1 or data.numel() == 0:
        return wav
    abs_data = data.abs()
    if abs_data.numel() == 0:
        return wav
    above = (abs_data > threshold).nonzero(as_tuple=False).squeeze(-1)
    if above.numel() == 0:
        return wav  # Hep sessiz; olduğu gibi bırak
    first_idx = int(above[0].item())
    max_samples = int(max_trim_ms * sr / 1000)
    pre_samples = int(pre_buffer_ms * sr / 1000)
    keep_from = max(0, first_idx - pre_samples)
    if keep_from >= max_samples:
        keep_from = 0  # Çok uzun sessizlik; pre-buffer verme
    if keep_from <= 0:
        return wav
    return wav[..., keep_from:].contiguous()


def queue_split_lines(text: str) -> list[str]:
    """Çok satırlı metni dolu satırlara böler (boş olmayan, trim'li)."""
    return [line.strip() for line in text.splitlines() if line.strip()]


def apply_theme(app, theme: str) -> None:
    """Qt temasını uygula: 'light' / 'dark' / 'system'."""
    app.setStyle("Fusion")
    if theme == "system":
        palette = app.palette()
        is_dark = palette.window().color().lightness() < 128
        theme = "dark" if is_dark else "light"

    if theme == "dark":
        dark = QPalette()
        dark.setColor(QPalette.ColorRole.Window, QColor(53, 53, 53))
        dark.setColor(QPalette.ColorRole.WindowText, Qt.GlobalColor.white)
        dark.setColor(QPalette.ColorRole.Base, QColor(35, 35, 35))
        dark.setColor(QPalette.ColorRole.AlternateBase, QColor(53, 53, 53))
        dark.setColor(QPalette.ColorRole.ToolTipBase, QColor(35, 35, 35))
        dark.setColor(QPalette.ColorRole.ToolTipText, Qt.GlobalColor.white)
        dark.setColor(QPalette.ColorRole.Text, Qt.GlobalColor.white)
        dark.setColor(QPalette.ColorRole.Button, QColor(53, 53, 53))
        dark.setColor(QPalette.ColorRole.ButtonText, Qt.GlobalColor.white)
        dark.setColor(QPalette.ColorRole.BrightText, Qt.GlobalColor.red)
        dark.setColor(QPalette.ColorRole.Link, QColor(42, 130, 218))
        dark.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
        dark.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.black)
        app.setPalette(dark)
    else:
        app.setPalette(app.style().standardPalette())


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("txttoTTS - Chatterbox Türkçe")
        self.resize(1080, 760)

        self.engine = None
        self.last_wav = None
        self.last_sr = None
        self.last_output_path: str | None = None
        self.last_text: str = ""
        self.voice_prompt_path: str | None = None
        self.output_dir = self._default_output_dir()
        self.settings = load_settings()
        self.history = load_history()
        self._loader: QThread | None = None
        self._synth_worker: SynthWorker | None = None
        self._synth_dialog: SynthesisDialog | None = None
        self._synth_cancel_requested = False
        self._voice_warning_dismissed: bool = False  # Oturum-içi: modal bir daha gösterme
        self._history_query: str = ""  # Geçmiş arama filtresi
        self._queue: list[str] = []  # Toplu üretim kuyruğu
        self._queue_running: bool = False
        self.production_count: int = int(self.settings.get("production_count", 0))

        self._build_ui()
        self._load_saved_settings()
        self._refresh_history_list()
        self.update_text_info()
        self.update_settings_summary()
        self._init_engine_async()
        # İlk tema yükleme: ayar varsa uygula (comboBox sonradan setCurrentIndex tetikler)
        theme = self.settings.get("theme", "system") if self.settings else "system"
        apply_theme(QApplication.instance(), theme)

    def _build_voice_warning_panel(self) -> QFrame:
        """Referans ses örneği seçilmediğinde Üretim sekmesinde görünen uyarı paneli.

        Ses örneği seçilince gizlenir (setVisible(False)); tekrar görünür.
        Butonlar: 'Ses Örneği Seç' → dosya seçici, 'Rehber' → VoiceGuideDialog.
        """
        panel = QFrame()
        panel.setObjectName("voiceWarningPanel")
        panel.setStyleSheet(
            "QFrame#voiceWarningPanel {"
            "  background-color: #fff4d6;"
            "  border: 1px solid #e6b800;"
            "  border-radius: 4px;"
            "  padding: 6px;"
            "}"
            "QFrame#voiceWarningPanel QLabel {"
            "  color: #5a4500;"
            "}"
        )
        layout = QHBoxLayout(panel)
        layout.setContentsMargins(8, 4, 8, 4)
        icon = QLabel("⚠")
        icon.setStyleSheet("font-size: 16px;")
        text = QLabel(
            "Referans ses örneği seçmediniz. "
            "Varsayılan ses robotik olabilir; 10-15 sn kendi sesinizle örnek ekleyin."
        )
        text.setWordWrap(True)
        btn_select = QPushButton("Ses Örneği Seç")
        btn_select.clicked.connect(self.on_select_voice)
        btn_guide = QPushButton("Rehber")
        btn_guide.clicked.connect(self.on_show_voice_sample_text)
        btn_warm = QPushButton("Sıcak Anlatıcı")
        btn_warm.setToolTip("Sıcak Anlatıcı hazır ayarını uygula")
        btn_warm.clicked.connect(self._apply_warm_narrator_preset)
        layout.addWidget(icon)
        layout.addWidget(text, stretch=1)
        layout.addWidget(btn_warm)
        layout.addWidget(btn_select)
        layout.addWidget(btn_guide)
        return panel

    def _refresh_voice_warning(self):
        """voice_prompt_path'e göre banner görünürlüğünü günceller."""
        if hasattr(self, "_voice_warning"):
            self._voice_warning.setVisible(self.voice_prompt_path is None)

    def _apply_warm_narrator_preset(self):
        """Banner'daki 'Sıcak Anlatıcı' hızlı butonu."""
        idx = self.preset_combo.findText("Sıcak Anlatıcı")
        if idx >= 0:
            self.preset_combo.setCurrentIndex(idx)
        self.on_apply_preset()
        self.status_label.setText("Sıcak Anlatıcı hazır ayarı uygulandı.")

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        toolbar = QHBoxLayout()
        self.btn_paste = QPushButton("Yapıştır")
        self.btn_clean_text = QPushButton("Metni Temizle")
        self.btn_generate = QPushButton("Üret")
        self.btn_play = QPushButton("Çal")
        self.btn_stop = QPushButton("Dur")
        self.btn_save_wav = QPushButton("Kaydet WAV")
        self.btn_save_mp3 = QPushButton("Kaydet MP3")
        for button in (
            self.btn_paste,
            self.btn_clean_text,
            self.btn_generate,
            self.btn_play,
            self.btn_stop,
            self.btn_save_wav,
            self.btn_save_mp3,
        ):
            toolbar.addWidget(button)
        root.addLayout(toolbar)

        tabs = QTabWidget()
        root.addWidget(tabs, stretch=1)

        main_tab = QWidget()
        main_layout = QVBoxLayout(main_tab)
        self.text_edit = QTextEdit()
        self.text_edit.setPlaceholderText("Türkçe metni buraya yaz veya Yapıştır düğmesiyle panodaki metni al.")
        self.text_edit.setFont(QFont("Segoe UI", 11))
        self.text_stats_label = QLabel("Karakter: 0 | Kelime: 0 | Parça: 0 | Tahmini süre: 0 sn")
        self.settings_summary_label = QLabel("Türkçe | Anlatıcı | 0.90x | Varsayılan ses")
        self.settings_summary_label.setStyleSheet("color: #aaa;")
        main_layout.addWidget(self.text_stats_label)
        main_layout.addWidget(self.settings_summary_label)
        self._voice_warning = self._build_voice_warning_panel()
        main_layout.addWidget(self._voice_warning)
        main_layout.addWidget(self.text_edit, stretch=1)
        queue_box = QGroupBox("Toplu Üretim Kuyruğu")
        queue_layout = QVBoxLayout(queue_box)
        queue_buttons = QHBoxLayout()
        self.btn_queue_add = QPushButton("+ Metin Ekle")
        self.btn_queue_load = QPushButton("+ Dosyadan Yükle")
        self.btn_queue_run = QPushButton("Üret (Tümünü)")
        self.btn_queue_clear = QPushButton("Temizle")
        for b in (self.btn_queue_add, self.btn_queue_load, self.btn_queue_run, self.btn_queue_clear):
            queue_buttons.addWidget(b)
        queue_layout.addLayout(queue_buttons)
        self.queue_list = QListWidget()
        queue_layout.addWidget(self.queue_list, stretch=1)
        main_layout.addWidget(queue_box)
        tabs.addTab(main_tab, "Üretim")

        settings_tab = QWidget()
        settings_layout = QVBoxLayout(settings_tab)
        settings_box = QGroupBox("Ses Ayarları")
        settings_grid = QGridLayout(settings_box)

        self.preset_combo = QComboBox()
        for preset_name in PRESETS:
            self.preset_combo.addItem(preset_name)
        narrator_index = self.preset_combo.findText("Anlatıcı")
        if narrator_index >= 0:
            self.preset_combo.setCurrentIndex(narrator_index)
        self.btn_apply_preset = QPushButton("Seç")

        self.language_combo = QComboBox()
        for code, name in LANGUAGES.items():
            self.language_combo.addItem(f"{name} ({code})", code)
        self.language_combo.setCurrentIndex(self.language_combo.findData("tr"))
        self.language_combo.currentIndexChanged.connect(self._update_language_tooltip)
        self._update_language_tooltip()

        self.speed_spin = QDoubleSpinBox()
        self.speed_spin.setRange(0.60, 1.60)
        self.speed_spin.setSingleStep(0.05)
        self.speed_spin.setValue(0.90)
        self.speed_spin.setSuffix("x")

        self.exaggeration_spin = QDoubleSpinBox()
        self.exaggeration_spin.setRange(0.10, 1.50)
        self.exaggeration_spin.setSingleStep(0.05)
        self.exaggeration_spin.setValue(0.40)

        self.cfg_spin = QDoubleSpinBox()
        self.cfg_spin.setRange(0.10, 1.50)
        self.cfg_spin.setSingleStep(0.05)
        self.cfg_spin.setValue(0.45)

        self.temperature_spin = QDoubleSpinBox()
        self.temperature_spin.setRange(0.10, 1.50)
        self.temperature_spin.setSingleStep(0.05)
        self.temperature_spin.setValue(0.30)

        self.repetition_spin = QDoubleSpinBox()
        self.repetition_spin.setRange(1.00, 3.00)
        self.repetition_spin.setSingleStep(0.10)
        self.repetition_spin.setValue(1.80)

        self.pause_spin = QDoubleSpinBox()
        self.pause_spin.setRange(0.00, 2.00)
        self.pause_spin.setSingleStep(0.05)
        self.pause_spin.setDecimals(2)
        self.pause_spin.setValue(0.35)
        self.pause_spin.setSuffix(" sn")

        settings_grid.addWidget(QLabel("Hazır ayar"), 0, 0)
        settings_grid.addWidget(self.preset_combo, 0, 1)
        settings_grid.addWidget(self.btn_apply_preset, 0, 2, 1, 2)
        settings_grid.addWidget(QLabel("Dil"), 1, 0)
        settings_grid.addWidget(self.language_combo, 1, 1)
        settings_grid.addWidget(QLabel("Hız"), 1, 2)
        settings_grid.addWidget(self.speed_spin, 1, 3)
        settings_grid.addWidget(QLabel("İfade"), 2, 0)
        settings_grid.addWidget(self.exaggeration_spin, 2, 1)
        settings_grid.addWidget(QLabel("Netlik"), 2, 2)
        settings_grid.addWidget(self.cfg_spin, 2, 3)
        settings_grid.addWidget(QLabel("Yaratıcılık"), 3, 0)
        settings_grid.addWidget(self.temperature_spin, 3, 1)
        settings_grid.addWidget(QLabel("Tekrar azaltma"), 3, 2)
        settings_grid.addWidget(self.repetition_spin, 3, 3)
        settings_grid.addWidget(QLabel("Duraklama"), 4, 0)
        settings_grid.addWidget(self.pause_spin, 4, 1)
        settings_layout.addWidget(settings_box)

        voice_box = QGroupBox("Ses Örneği")
        voice_layout = QGridLayout(voice_box)
        self.voice_label = QLabel("Ses örneği seçilmedi; varsayılan ses kullanılacak.")
        self.voice_label.setWordWrap(True)
        self.btn_select_voice = QPushButton("Ses Örneği Seç")
        self.btn_play_voice = QPushButton("Ön Dinle")
        self.btn_sample_voice_text = QPushButton("Ses Örneği Rehberi")
        self.btn_clear_voice = QPushButton("Varsayılana Dön")
        self.btn_play_voice.setEnabled(False)
        self.btn_clear_voice.setEnabled(False)
        voice_hint = QLabel("Önerilen: 5-20 saniye temiz, tek kişilik konuşma. İdeal hedef: 10-15 saniye.")
        voice_hint.setWordWrap(True)
        voice_layout.addWidget(self.voice_label, 0, 0, 1, 4)
        voice_layout.addWidget(voice_hint, 1, 0, 1, 4)
        voice_layout.addWidget(self.btn_select_voice, 2, 0)
        voice_layout.addWidget(self.btn_play_voice, 2, 1)
        voice_layout.addWidget(self.btn_sample_voice_text, 2, 2)
        voice_layout.addWidget(self.btn_clear_voice, 2, 3)
        settings_layout.addWidget(voice_box)

        output_box = QGroupBox("Kayıt Klasörü")
        output_layout = QGridLayout(output_box)
        self.output_dir_label = QLabel("")
        self.output_dir_label.setWordWrap(True)
        self.btn_select_output_dir = QPushButton("Klasör Seç")
        self.btn_open_output_dir = QPushButton("Klasörü Aç")
        self.btn_reset_output_dir = QPushButton("Varsayılana Dön")
        output_layout.addWidget(QLabel("Varsayılan klasör"), 0, 0)
        output_layout.addWidget(self.output_dir_label, 0, 1, 1, 3)
        output_layout.addWidget(self.btn_select_output_dir, 1, 0)
        output_layout.addWidget(self.btn_open_output_dir, 1, 1)
        output_layout.addWidget(self.btn_reset_output_dir, 1, 2)
        settings_layout.addWidget(output_box)

        mp3_box = QGroupBox("MP3 Kalite")
        mp3_layout = QGridLayout(mp3_box)
        self.mp3_bitrate_combo = QComboBox()
        self.mp3_bitrate_combo.addItem("Konuşma (128 kbps)", "128k")
        self.mp3_bitrate_combo.addItem("Podcast (192 kbps)", "192k")
        self.mp3_bitrate_combo.addItem("Yüksek kalite (320 kbps)", "320k")
        mp3_layout.addWidget(QLabel("MP3 bitrate"), 0, 0)
        mp3_layout.addWidget(self.mp3_bitrate_combo, 0, 1)
        self.mp3_bitrate_combo.currentIndexChanged.connect(self._save_current_settings)
        settings_layout.addWidget(mp3_box)

        system_box = QGroupBox("Sistem")
        system_layout = QGridLayout(system_box)
        self.device_label = QLabel("Cihaz: hazırlanıyor")
        self.gpu_label = QLabel("GPU: kontrol ediliyor")
        self.btn_system_info = QPushButton("Sistem Bilgisi")
        system_layout.addWidget(self.device_label, 0, 0)
        system_layout.addWidget(self.gpu_label, 0, 1)
        system_layout.addWidget(self.btn_system_info, 0, 2)
        self.theme_combo = QComboBox()
        self.theme_combo.addItem("Açık", "light")
        self.theme_combo.addItem("Karanlık", "dark")
        self.theme_combo.addItem("Sistem", "system")
        self.theme_combo.currentIndexChanged.connect(self._on_theme_changed)
        system_layout.addWidget(QLabel("Tema"), 1, 0)
        system_layout.addWidget(self.theme_combo, 1, 1, 1, 2)
        self.btn_reset_settings = QPushButton("Tüm Ayarları Sıfırla")
        self.btn_reset_settings.setToolTip("Tüm ayarları varsayılana döndürür (geçmiş korunur)")
        self.btn_reset_settings.clicked.connect(self.on_reset_all_settings)
        system_layout.addWidget(self.btn_reset_settings, 2, 0, 1, 3)
        settings_layout.addWidget(system_box)
        settings_layout.addStretch(1)
        tabs.addTab(settings_tab, "Ayarlar")

        history_tab = QWidget()
        history_layout = QVBoxLayout(history_tab)
        history_tools = QHBoxLayout()
        self.btn_restore_history = QPushButton("Metni Geri Al")
        self.btn_regenerate_history = QPushButton("Aynı Ayarlarla Üret")
        self.btn_play_history = QPushButton("Geçmişi Çal")
        self.btn_open_history = QPushButton("Klasörde Göster")
        self.btn_delete_history = QPushButton("Geçmişten Sil")
        self.btn_bulk_delete_history = QPushButton("Toplu Sil")
        for button in (
            self.btn_restore_history,
            self.btn_regenerate_history,
            self.btn_play_history,
            self.btn_open_history,
            self.btn_delete_history,
            self.btn_bulk_delete_history,
        ):
            history_tools.addWidget(button)
        history_layout.addLayout(history_tools)
        search_row = QHBoxLayout()
        self._history_search = QLineEdit()
        self._history_search.setPlaceholderText("Geçmişte ara (ad veya metin)...")
        self._history_search.setClearButtonEnabled(True)
        search_row.addWidget(self._history_search, stretch=1)
        self._history_search.textChanged.connect(self._on_history_search_changed)
        history_layout.addLayout(search_row)
        self.history_list = QListWidget()
        history_layout.addWidget(self.history_list, stretch=1)
        tabs.addTab(history_tab, "Geçmiş")

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.status_label = QLabel("Motor yükleniyor...")
        self.stats_label = QLabel("Toplam: 0 üretim")
        status_row = QHBoxLayout()
        status_row.addWidget(self.stats_label)
        status_row.addWidget(self.status_label, stretch=1)
        status_row.addWidget(self.progress)
        root.addLayout(status_row)

        self.btn_paste.clicked.connect(self.on_paste)
        self.btn_clean_text.clicked.connect(self.on_clean_text)
        self.text_edit.textChanged.connect(self.update_text_info)
        self.language_combo.currentIndexChanged.connect(self.update_settings_summary)
        self.speed_spin.valueChanged.connect(self.update_settings_summary)
        self.speed_spin.valueChanged.connect(self.update_text_info)
        self.pause_spin.valueChanged.connect(self.update_settings_summary)
        self.pause_spin.valueChanged.connect(self.update_text_info)
        self.preset_combo.currentIndexChanged.connect(self.update_settings_summary)
        self.btn_generate.clicked.connect(self.on_generate)
        self.btn_play.clicked.connect(self.on_play)
        self.btn_stop.clicked.connect(audio_player.stop)
        self.btn_save_wav.clicked.connect(self.on_save_wav)
        self.btn_save_mp3.clicked.connect(self.on_save_mp3)
        self.btn_select_voice.clicked.connect(self.on_select_voice)
        self.btn_play_voice.clicked.connect(self.on_play_voice)
        self.btn_sample_voice_text.clicked.connect(self.on_show_voice_sample_text)
        self.btn_clear_voice.clicked.connect(self.on_clear_voice)
        self.btn_select_output_dir.clicked.connect(self.on_select_output_dir)
        self.btn_open_output_dir.clicked.connect(self.on_open_output_dir)
        self.btn_reset_output_dir.clicked.connect(self.on_reset_output_dir)
        self.btn_apply_preset.clicked.connect(self.on_apply_preset)
        self.btn_system_info.clicked.connect(self.on_show_system_info)
        self.btn_restore_history.clicked.connect(self.on_restore_history_text)
        self.btn_regenerate_history.clicked.connect(self.on_regenerate_from_history)
        self.btn_play_history.clicked.connect(self.on_play_history)
        self.btn_open_history.clicked.connect(self.on_open_history)
        self.btn_delete_history.clicked.connect(self.on_delete_history)
        self.btn_bulk_delete_history.clicked.connect(self.on_bulk_delete_history)

        self.btn_queue_add.clicked.connect(self.on_queue_add)
        self.btn_queue_load.clicked.connect(self.on_queue_load_file)
        self.btn_queue_run.clicked.connect(self.on_queue_run)
        self.btn_queue_clear.clicked.connect(self.on_queue_clear)

        self._setup_shortcuts()
        self._set_button_tooltips()

        self._set_outputs_enabled(False)
        self._set_engine_actions_enabled(False)

    def _setup_shortcuts(self):
        """Pencere kapsamı klavye kısayolları."""
        shortcuts = [
            (QKeySequence("Ctrl+Return"), self.on_generate),
            (QKeySequence.StandardKey.Save, self.on_save_wav),
            (QKeySequence("Ctrl+Shift+S"), self.on_save_mp3),
            (QKeySequence("Ctrl+Shift+V"), self.on_select_voice),
        ]
        self._shortcuts = []  # GC koruması
        for keyseq, slot in shortcuts:
            sc = QShortcut(keyseq, self)
            sc.setContext(Qt.ShortcutContext.WindowShortcut)
            sc.activated.connect(slot)
            self._shortcuts.append(sc)

    def _set_button_tooltips(self):
        """Ana işlem butonlarına kısayol ipucu ekler."""
        self.btn_generate.setToolTip("Metni ses sentezine gönder (Ctrl+Enter)")
        self.btn_save_wav.setToolTip("Son üretimi WAV olarak kaydet (Ctrl+S)")
        self.btn_save_mp3.setToolTip("Son üretimi MP3 olarak kaydet (Ctrl+Shift+S)")
        self.btn_select_voice.setToolTip("Referans ses örneği dosyası seç (Ctrl+Shift+V)")

    def _init_engine_async(self):
        """Model yükleme uzun sürebilir; ayrı thread."""
        self._model_dialog = ModelLoadDialog(self)
        self._model_dialog.add_status("Uygulama açıldı. Ses motoru hazırlanıyor.")
        self._model_dialog.show()

        self._loader = EngineLoader()
        self._loader.status.connect(self._on_engine_status)
        self._loader.ok.connect(self._on_engine_ready)
        self._loader.fail.connect(self._on_engine_failed)
        self._loader.start()

    def _on_engine_status(self, message: str):
        self.status_label.setText(message)
        if hasattr(self, "_model_dialog") and self._model_dialog:
            self._model_dialog.add_status(message)

    def _on_engine_ready(self, engine):
        self.engine = engine
        message = f"Hazır - {type(engine.engine).__name__} ({engine.device_name})"
        self.status_label.setText(message)
        self._reset_progress()
        self._set_engine_actions_enabled(True)
        self._refresh_system_labels()
        if hasattr(self, "_model_dialog") and self._model_dialog:
            self._model_dialog.finish_ok(message)

    def _on_engine_failed(self, msg: str):
        message = f"Motor yüklenemedi:\n{msg}"
        self.status_label.setText("Motor yüklenemedi.")
        self._reset_progress()
        self._set_engine_actions_enabled(False)
        self._refresh_system_labels()
        if hasattr(self, "_model_dialog") and self._model_dialog:
            self._model_dialog.finish_error(message)
        self._show_error("Hata", message)

    def _friendly_error(self, msg: str) -> str:
        lower = msg.lower()
        if "cuda" in lower or "gpu" in lower:
            return "GPU kullanılamadı veya CUDA tarafında sorun oluştu. CPU ile tekrar denenebilir."
        if "audio_prompt" in lower or "librosa" in lower or "soundfile" in lower:
            return "Ses örneği okunamadı. Daha kısa, temiz bir WAV/MP3 dosyası deneyebilirsin."
        if "memory" in lower or "out of memory" in lower:
            return "Bellek yetersiz kaldı. Metni kısaltmayı veya daha az parçayla denemeyi deneyebilirsin."
        if "unsupported language" in lower:
            return "Seçilen dil model tarafından desteklenmedi. Ayarlar sekmesinden başka bir dil seç."
        if "model" in lower or "pretrained" in lower or "snapshot" in lower:
            return "Model yüklenemedi. İnternet bağlantısı, kurulum veya model dosyaları kontrol edilmeli."
        return "İşlem tamamlanamadı. Ayrıntı aşağıda."

    def _show_error(self, title: str, msg: str):
        friendly = self._friendly_error(str(msg))
        QMessageBox.critical(self, title, f"{friendly}\n\nAyrıntı:\n{msg}")

    def closeEvent(self, event):
        settings = self._current_ui_settings()
        settings["production_count"] = self.production_count
        save_settings(settings)
        save_history(self.history)
        super().closeEvent(event)

    def on_paste(self):
        text = QApplication.clipboard().text().strip()
        if not text:
            QMessageBox.information(self, "Pano boş", "Panoda yapıştırılacak metin bulunamadı.")
            return
        self.text_edit.setPlainText(text)
        self.status_label.setText("Panodaki metin üretim alanına yapıştırıldı.")
        self.update_text_info()

    def on_clean_text(self):
        original = self.text_edit.toPlainText()
        cleaned = self._clean_text(original)
        self.text_edit.setPlainText(cleaned)
        self.status_label.setText("Metin temizlendi.")

    def _clean_text(self, text: str) -> str:
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = re.sub(r"([A-Za-zÇĞİÖŞÜçğıöşü])-\n([A-Za-zÇĞİÖŞÜçğıöşü])", r"\1\2", text)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"(?<![.!?…:;])\n(?!\n)", " ", text)
        text = re.sub(r" +\n", "\n", text)
        text = re.sub(r"\n +", "\n", text)
        return text.strip()

    def update_text_info(self):
        if not hasattr(self, "text_stats_label"):
            return
        text = self.text_edit.toPlainText().strip()
        chars = len(text)
        words = len(re.findall(r"\S+", text))
        parts = len(chunker.split_into_chunks(text)) if text else 0
        speed = self.speed_spin.value() if hasattr(self, "speed_spin") else 1.0
        pause = self.pause_spin.value() if hasattr(self, "pause_spin") else 0.0
        min_seconds, max_seconds = self._estimate_duration_range(words, parts, speed, pause)
        if words == 0:
            duration = "0 sn"
        elif max_seconds < 60:
            duration = f"{min_seconds}-{max_seconds} sn"
        else:
            duration = f"{min_seconds // 60}-{max_seconds // 60} dk"
        self.text_stats_label.setText(
            f"Karakter: {chars} | Kelime: {words} | Parça: {parts} | Tahmini süre: {duration}"
        )

    def _estimate_duration_range(
        self,
        words: int,
        parts: int = 0,
        speed: float = 1.0,
        pause: float = 0.0,
    ) -> tuple[int, int]:
        return estimate_duration_range(words, parts, speed, pause)

    def update_settings_summary(self):
        if not hasattr(self, "settings_summary_label"):
            return
        language = self.language_combo.currentText().split(" (")[0]
        preset = self.preset_combo.currentText()
        voice = "Ses örneği var" if self.voice_prompt_path else "Varsayılan ses"
        self.settings_summary_label.setText(
            f"{language} | {preset} | {self.speed_spin.value():.2f}x | Duraklama {self.pause_spin.value():.2f} sn | {voice}"
        )

    def _load_saved_settings(self):
        settings = self.settings or {}
        preset = settings.get("preset", "Anlatıcı")
        preset_index = self.preset_combo.findText(preset)
        if preset_index >= 0:
            self.preset_combo.setCurrentIndex(preset_index)
        language = settings.get("language_id", "tr")
        index = self.language_combo.findData(language)
        if index >= 0:
            self.language_combo.setCurrentIndex(index)
        self.speed_spin.setValue(float(settings.get("speed", self.speed_spin.value())))
        self.exaggeration_spin.setValue(float(settings.get("exaggeration", self.exaggeration_spin.value())))
        self.cfg_spin.setValue(float(settings.get("cfg_weight", self.cfg_spin.value())))
        self.temperature_spin.setValue(float(settings.get("temperature", self.temperature_spin.value())))
        self.repetition_spin.setValue(float(settings.get("repetition_penalty", self.repetition_spin.value())))
        self.pause_spin.setValue(float(settings.get("pause_between_chunks", self.pause_spin.value())))
        bitrate = settings.get("mp3_bitrate", "192k")
        bitrate_index = self.mp3_bitrate_combo.findData(bitrate)
        if bitrate_index >= 0:
            self.mp3_bitrate_combo.setCurrentIndex(bitrate_index)
        theme = settings.get("theme", "system")
        theme_index = self.theme_combo.findData(theme)
        if theme_index >= 0:
            self.theme_combo.setCurrentIndex(theme_index)
        output_dir = settings.get("output_dir")
        if output_dir:
            self._set_output_dir(output_dir, save=False)
        else:
            self._refresh_output_dir_label()
        voice_path = settings.get("audio_prompt_path") or settings.get("voice_prompt_path")
        if voice_path and os.path.exists(voice_path):
            self._set_voice_prompt(voice_path, save=False)
        else:
            self._refresh_voice_warning()
        self.update_settings_summary()

    def _save_current_settings(self):
        if not hasattr(self, "language_combo"):
            return
        save_settings(self._current_ui_settings())

    def _current_ui_settings(self) -> dict:
        return {
            "preset": self.preset_combo.currentText(),
            "language_id": self.language_combo.currentData(),
            "exaggeration": self.exaggeration_spin.value(),
            "cfg_weight": self.cfg_spin.value(),
            "audio_prompt_path": self.voice_prompt_path,
            "temperature": self.temperature_spin.value(),
            "repetition_penalty": self.repetition_spin.value(),
            "min_p": 0.05,
            "top_p": 1.0,
            "speed": self.speed_spin.value(),
            "pause_between_chunks": self.pause_spin.value(),
            "mp3_bitrate": self.mp3_bitrate_combo.currentData() if hasattr(self, "mp3_bitrate_combo") else "192k",
            "theme": self.theme_combo.currentData() if hasattr(self, "theme_combo") else "system",
            "output_dir": self.output_dir,
        }

    def _current_synthesis_settings(self) -> dict:
        settings = self._current_ui_settings().copy()
        settings.pop("preset", None)
        settings.pop("output_dir", None)
        return settings

    def on_apply_preset(self):
        preset = PRESETS.get(self.preset_combo.currentText())
        if not preset:
            return
        self.speed_spin.setValue(preset["speed"])
        self.exaggeration_spin.setValue(preset["exaggeration"])
        self.cfg_spin.setValue(preset["cfg"])
        self.temperature_spin.setValue(preset["temperature"])
        self.repetition_spin.setValue(preset["repetition"])
        self.pause_spin.setValue(preset.get("pause", self.pause_spin.value()))
        self.status_label.setText(f"Hazır ayar seçildi: {self.preset_combo.currentText()}")
        self.update_settings_summary()
        self._save_current_settings()

    def _default_output_dir(self) -> str:
        app_dir = os.path.dirname(os.path.abspath(__file__))
        # main_window.py app/ altında; çıktılar proje kökünde outputs/
        # Bir üst dizine çıkıp oradaki config.DEFAULT_OUTPUT_DIR'i kullan.
        project_root = os.path.dirname(app_dir)
        return os.path.join(project_root, DEFAULT_OUTPUT_DIR)

    def _refresh_output_dir_label(self):
        if hasattr(self, "output_dir_label"):
            self.output_dir_label.setText(self.output_dir)

    def _set_output_dir(self, directory: str, save: bool = True):
        directory = os.path.abspath(directory or self._default_output_dir())
        self.output_dir = directory
        os.makedirs(self.output_dir, exist_ok=True)
        self._refresh_output_dir_label()
        if save:
            self._save_current_settings()
            self.status_label.setText(f"Kayıt klasörü seçildi: {self.output_dir}")

    def on_select_output_dir(self):
        directory = QFileDialog.getExistingDirectory(self, "Varsayılan kayıt klasörünü seç", self.output_dir)
        if not directory:
            return
        self._set_output_dir(directory)

    def on_reset_output_dir(self):
        self._set_output_dir(self._default_output_dir())

    def on_open_output_dir(self):
        os.makedirs(self.output_dir, exist_ok=True)
        self._open_folder(self.output_dir)

    def _make_output_path(self, extension: str) -> str:
        os.makedirs(self.output_dir, exist_ok=True)
        return str(unique_path(self.output_dir, safe_filename_from_text(self.last_text or self.text_edit.toPlainText(), extension)))

    def _open_folder(self, folder_path: str):
        if not folder_path:
            return
        if not os.path.isdir(folder_path):
            QMessageBox.warning(self, "Klasör bulunamadı", f"Bu klasör bulunamadı:\n{folder_path}")
            return
        try:
            os.startfile(folder_path)
        except Exception as e:
            QMessageBox.warning(self, "Klasör açılamadı", f"Klasör açılamadı.\n\nAyrıntı:\n{e}")

    def _show_file_in_folder(self, file_path: str):
        if not file_path:
            QMessageBox.information(self, "Kayıt yolu yok", "Bu geçmiş kaydında açılacak dosya yolu bulunamadı.")
            return
        folder_path = os.path.dirname(file_path)
        if os.path.exists(file_path):
            try:
                subprocess.Popen(["explorer", f"/select,{os.path.normpath(file_path)}"])
                return
            except Exception:
                pass
        if os.path.isdir(folder_path):
            self._open_folder(folder_path)
            if not os.path.exists(file_path):
                self.status_label.setText("Ses dosyası bulunamadı; kayıt klasörü açıldı.")
            return
        QMessageBox.warning(self, "Dosya bulunamadı", "Bu geçmiş kaydının ses dosyası artık bulunamıyor.")

    def _refresh_system_labels(self):
        if not hasattr(self, "device_label"):
            return
        self.device_label.setText(f"Cihaz: {self.engine.device_name}" if self.engine else "Cihaz: hazırlanıyor")
        gpu_name = "Yok / CPU"
        try:
            import torch

            if torch.cuda.is_available():
                gpu_name = torch.cuda.get_device_name(0)
        except Exception:
            pass
        self.gpu_label.setText(f"GPU: {gpu_name}")

    def on_show_system_info(self):
        try:
            import torch

            torch_version = torch.__version__
            cuda_available = torch.cuda.is_available()
            cuda_version = torch.version.cuda
            gpu_name = torch.cuda.get_device_name(0) if cuda_available else "CPU"
        except Exception as e:
            torch_version = f"Hata: {e}"
            cuda_available = False
            cuda_version = "?"
            gpu_name = "?"

        ffmpeg = "Var" if self._has_ffmpeg() else "Yok"
        engine = f"{type(self.engine.engine).__name__} ({self.engine.device_name})" if self.engine else "Hazırlanıyor"
        QMessageBox.information(
            self,
            "Sistem Bilgisi",
            "\n".join(
                [
                    f"Motor: {engine}",
                    f"PyTorch: {torch_version}",
                    f"CUDA aktif: {cuda_available}",
                    f"CUDA sürümü: {cuda_version}",
                    f"GPU: {gpu_name}",
                    f"ffmpeg: {ffmpeg}",
                ]
            ),
        )

    def _has_ffmpeg(self) -> bool:
        from shutil import which

        return which("ffmpeg") is not None

    def _describe_audio_file(self, path: str) -> tuple[str, float | None]:
        try:
            info = sf.info(path)
            duration = float(info.duration)
        except Exception:
            try:
                from pydub import AudioSegment

                duration = len(AudioSegment.from_file(path)) / 1000.0
            except Exception:
                return "Ses süresi okunamadı.", None

        if duration < 3:
            note = "Çok kısa; 5-20 saniye temiz konuşma daha iyi sonuç verir."
        elif duration > 30:
            note = "Uzun; 5-20 saniyelik temiz konuşma önerilir."
        elif 5 <= duration <= 20:
            note = "İdeal aralıkta."
        else:
            note = "Kullanılabilir; 5-20 saniye aralığı en iyi sonuç verir."
        return f"{duration:.1f} sn - {note}", duration

    def _set_voice_prompt(self, file_path: str, save: bool = True):
        self.voice_prompt_path = file_path
        description, _duration = self._describe_audio_file(file_path)
        self.voice_label.setText(f"{os.path.basename(file_path)} ({description})")
        self.btn_play_voice.setEnabled(True)
        self.btn_clear_voice.setEnabled(True)
        self.update_settings_summary()
        self._refresh_voice_warning()
        if save:
            self.status_label.setText("Ses örneği seçildi; yeni üretimde bu ses karakteri kullanılacak.")
            self._save_current_settings()

    def on_select_voice(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Ses örneği seç",
            "",
            "Ses dosyası (*.wav *.mp3 *.flac *.ogg *.m4a);;Tüm dosyalar (*.*)",
        )
        if not path:
            return
        self._set_voice_prompt(path)

    def on_play_voice(self):
        if not self.voice_prompt_path:
            return
        try:
            audio_player.play_file(self.voice_prompt_path)
        except Exception as e:
            QMessageBox.warning(self, "Ses örneği çalınamadı", f"Ses örneği okunamadı.\n\nAyrıntı:\n{e}")

    def on_show_voice_sample_text(self):
        dialog = VoiceGuideDialog(self)
        dialog.exec()

    def on_clear_voice(self):
        self.voice_prompt_path = None
        self.voice_label.setText("Ses örneği seçilmedi; varsayılan ses kullanılacak.")
        self.btn_play_voice.setEnabled(False)
        self.btn_clear_voice.setEnabled(False)
        self.status_label.setText("Ses örneği kaldırıldı; varsayılan sese dönüldü.")
        self.update_settings_summary()
        self._refresh_voice_warning()
        self._save_current_settings()

    def _on_history_search_changed(self, text: str):
        self._history_query = text
        self._refresh_history_list()

    def on_queue_add(self):
        """Mevcut text_edit içeriğini kuyruğa ekle."""
        text = self.text_edit.toPlainText().strip()
        if not text:
            QMessageBox.information(self, "Boş metin", "Kuyruğa eklemek için metin alanı boş olmamalı.")
            return
        self._queue.append(text)
        self._refresh_queue_list()
        self.text_edit.clear()
        self.update_text_info()
        self.status_label.setText(f"Kuyruğa eklendi. Toplam: {len(self._queue)}")

    def on_queue_load_file(self):
        """Txt dosyasından satırları kuyruğa ekle."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Metin dosyası seç", "", "Metin dosyası (*.txt);;Tüm dosyalar (*.*)"
        )
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as f:
                content = f.read()
        except UnicodeDecodeError:
            with open(path, encoding="utf-8", errors="replace") as f:
                content = f.read()
        except Exception as e:
            QMessageBox.warning(self, "Dosya okunamadı", f"Hata:\n{e}")
            return
        added = 0
        for line in queue_split_lines(content):
            self._queue.append(line)
            added += 1
        self._refresh_queue_list()
        self.status_label.setText(f"Dosyadan {added} satır eklendi. Toplam: {len(self._queue)}")

    def on_queue_run(self):
        """Kuyruktaki tüm metinleri sırayla üret."""
        if self._queue_running:
            return
        if not self._queue:
            QMessageBox.information(self, "Kuyruk boş", "Kuyruğa metin ekleyin.")
            return
        if not self.engine:
            QMessageBox.warning(self, "Uyarı", "Motor henüz hazır değil.")
            return
        self._queue_running = True
        self.status_label.setText(f"Kuyruk başlatıldı. {len(self._queue)} metin işlenecek.")
        self._process_next_queue_item()

    def on_queue_clear(self):
        """Kuyruğu temizle (çalışıyorsa iptal etmez)."""
        if self._queue_running:
            QMessageBox.information(self, "Çalışıyor", "Kuyruk şu an çalışıyor; durdurmak için Üretimi Durdur kullanın.")
            return
        self._queue.clear()
        self._refresh_queue_list()
        self.status_label.setText("Kuyruk temizlendi.")

    def _process_next_queue_item(self):
        """Kuyruktaki bir sonraki metni text_edit'e al ve on_generate çağır."""
        if not self._queue:
            self._queue_running = False
            self.status_label.setText("Kuyruk tamamlandı.")
            return
        text = self._queue[0]  # İptalde geri eklemek için pop etmeyelim
        self.text_edit.setPlainText(text)
        self.update_text_info()
        self.status_label.setText(f"Kuyruk işleniyor: {len(self._queue)} kaldı")
        self.on_generate()  # Mevcut tek-üretim akışı

    def _refresh_queue_list(self):
        if hasattr(self, "queue_list"):
            self.queue_list.clear()
            for i, text in enumerate(self._queue, 1):
                preview = text.replace("\n", " ").strip()
                if len(preview) > 60:
                    preview = preview[:57] + "..."
                self.queue_list.addItem(f"{i}. {preview}")

    def _refresh_history_list(self):
        if not hasattr(self, "history_list"):
            return
        self.history_list.clear()
        q = self._history_query.strip().lower()
        for item in reversed(self.history[-100:]):
            name = item.get("name") or os.path.basename(item.get("path", "ses"))
            duration = item.get("duration", "?")
            file_path = item.get("path", "")
            exists = "" if os.path.exists(file_path) else " [dosya yok]"
            if q:
                name_lc = name.lower()
                text_lc = (item.get("text") or "").lower()
                if q not in name_lc and q not in text_lc:
                    continue
            extra = []
            if item.get("preset"):
                extra.append(item["preset"])
            if item.get("speed") is not None:
                extra.append(f"{item['speed']:.2f}x")
            info = f" [{' • '.join(extra)}]" if extra else ""
            self.history_list.addItem(f"{name} - {duration}{info}{exists}")

    def _selected_history_item(self) -> dict | None:
        row = self.history_list.currentRow()
        if row < 0:
            return None
        q = self._history_query.strip().lower()
        items = list(reversed(self.history[-100:]))
        if q:
            items = [
                it for it in items
                if q in ((it.get("name") or "").lower() + (it.get("text") or "").lower())
            ]
        if row >= len(items):
            return None
        return items[row]

    def _add_history_entry(self, file_path: str, text: str, duration: str):
        entry = {
            "path": file_path,
            "name": os.path.basename(file_path),
            "text": text[:240],
            "duration": duration,
            "preset": self.preset_combo.currentText(),
            "language_id": self.language_combo.currentData(),
            "exaggeration": self.exaggeration_spin.value(),
            "cfg_weight": self.cfg_spin.value(),
            "temperature": self.temperature_spin.value(),
            "repetition_penalty": self.repetition_spin.value(),
            "speed": self.speed_spin.value(),
            "pause_between_chunks": self.pause_spin.value(),
            "mp3_bitrate": self.mp3_bitrate_combo.currentData() if hasattr(self, "mp3_bitrate_combo") else "192k",
            "audio_prompt_path": self.voice_prompt_path,
        }
        self.history.append(entry)
        self.history = self.history[-100:]
        save_history(self.history)
        self._refresh_history_list()

    def on_restore_history_text(self):
        item = self._selected_history_item()
        if not item:
            return
        text = item.get("text", "")
        if not text:
            QMessageBox.information(self, "Metin yok", "Bu geçmiş kaydında geri alınacak metin bulunamadı.")
            return
        self.text_edit.setPlainText(text)
        self.status_label.setText("Geçmişteki metin üretim alanına alındı.")
        self.update_text_info()

    def on_regenerate_from_history(self):
        """Geçmişten seçili kaydın metnini + ayarlarını yükler, üretimi başlatır."""
        item = self._selected_history_item()
        if not item:
            return
        text = item.get("text", "")
        if not text:
            QMessageBox.information(self, "Metin yok", "Bu geçmiş kaydında geri alınacak metin bulunamadı.")
            return

        # Metin yükle
        self.text_edit.setPlainText(text)
        self.update_text_info()

        # Ayarları yükle (history'de yoksa mevcut değer korunur)
        if "preset" in item:
            index = self.preset_combo.findText(item["preset"])
            if index >= 0:
                self.preset_combo.setCurrentIndex(index)
        if "language_id" in item:
            index = self.language_combo.findData(item["language_id"])
            if index >= 0:
                self.language_combo.setCurrentIndex(index)
        for key, spin in (
            ("exaggeration", self.exaggeration_spin),
            ("cfg_weight", self.cfg_spin),
            ("temperature", self.temperature_spin),
            ("repetition_penalty", self.repetition_spin),
            ("speed", self.speed_spin),
            ("pause_between_chunks", self.pause_spin),
        ):
            if key in item:
                try:
                    spin.setValue(float(item[key]))
                except (TypeError, ValueError):
                    pass
        if "mp3_bitrate" in item and hasattr(self, "mp3_bitrate_combo"):
            index = self.mp3_bitrate_combo.findData(item["mp3_bitrate"])
            if index >= 0:
                self.mp3_bitrate_combo.setCurrentIndex(index)
        if "audio_prompt_path" in item and item["audio_prompt_path"]:
            path = item["audio_prompt_path"]
            if os.path.exists(path):
                self._set_voice_prompt(path, save=False)

        self.update_settings_summary()
        self.status_label.setText("Geçmiş ayarlar yüklendi; üretim başlatılıyor...")

        # Üretimi başlat
        self.on_generate()

    def on_play_history(self):
        item = self._selected_history_item()
        if not item:
            return
        file_path = item.get("path")
        if file_path and os.path.exists(file_path):
            audio_player.play_file(file_path)

    def on_open_history(self):
        item = self._selected_history_item()
        if not item:
            return
        self._show_file_in_folder(item.get("path", ""))

    def _ask_history_delete_mode(self, count: int) -> str | None:
        message = "Seçili geçmiş kaydı kaldırılsın mı?"
        if count > 1:
            message = f"{count} geçmiş kaydı kaldırılsın mı?"

        box = QMessageBox(self)
        box.setWindowTitle("Geçmişi sil")
        box.setIcon(QMessageBox.Icon.Question)
        box.setText(message)
        box.setInformativeText("Ses dosyalarını Geri Dönüşüm'e taşıyabilir veya sadece geçmiş listesinden kaldırabilirsin.")
        delete_files_button = box.addButton("Geri Dönüşüm'e Taşı", QMessageBox.ButtonRole.DestructiveRole)
        list_only_button = box.addButton("Sadece listeden kaldır", QMessageBox.ButtonRole.AcceptRole)
        cancel_button = box.addButton("Vazgeç", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(list_only_button)
        box.exec()

        clicked = box.clickedButton()
        if clicked == delete_files_button:
            return "files"
        if clicked == list_only_button:
            return "list"
        if clicked == cancel_button:
            return None
        return None

    def _delete_history_items(self, items: list[dict], delete_files: bool):
        if not items:
            return

        failures = []
        if delete_files:
            seen_paths = set()
            for item in items:
                file_path = item.get("path")
                if not file_path or file_path in seen_paths:
                    continue
                seen_paths.add(file_path)
                if not os.path.exists(file_path):
                    continue
                ok, err = safe_remove_to_trash(file_path)
                if not ok:
                    failures.append(f"{os.path.basename(file_path)}: {err}")

        target_ids = {id(item) for item in items}
        self.history = [item for item in self.history if id(item) not in target_ids]
        save_history(self.history)
        self._refresh_history_list()

        if failures:
            QMessageBox.warning(
                self,
                "Bazı dosyalar silinemedi",
                "Geçmiş listesi temizlendi ama bazı ses dosyaları silinemedi.\n\n" + "\n".join(failures[:8]),
            )
        else:
            action = "dosyalarıyla birlikte silindi" if delete_files else "listeden kaldırıldı"
            self.status_label.setText(f"{len(items)} geçmiş kaydı {action}.")

    def on_delete_history(self):
        item = self._selected_history_item()
        if not item:
            return
        mode = self._ask_history_delete_mode(1)
        if not mode:
            return
        self._delete_history_items([item], delete_files=(mode == "files"))

    def on_bulk_delete_history(self):
        if not self.history:
            QMessageBox.information(self, "Geçmiş boş", "Silinecek geçmiş kaydı yok.")
            return
        items = list(self.history)
        mode = self._ask_history_delete_mode(len(items))
        if not mode:
            return
        self._delete_history_items(items, delete_files=(mode == "files"))

    def _update_language_tooltip(self, _index: int = 0):
        code = self.language_combo.currentData()
        name = LANGUAGES.get(code, code)
        sample = LANGUAGE_SAMPLES.get(code, "")
        self.language_combo.setToolTip(f"{name}: '{sample}'")

    def on_reset_all_settings(self):
        reply = QMessageBox.question(
            self,
            "Ayarları sıfırla",
            "Tüm ayarlar varsayılana döndürülecek. Üretim geçmişi korunur.\nDevam edilsin mi?",
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        # Preset
        narrator_index = self.preset_combo.findText("Anlatıcı")
        if narrator_index >= 0:
            self.preset_combo.setCurrentIndex(narrator_index)
        # Dil
        lang_index = self.language_combo.findData("tr")
        if lang_index >= 0:
            self.language_combo.setCurrentIndex(lang_index)
        # Spin'ler (default değerler _build_ui'deki default'larla aynı)
        self.speed_spin.setValue(0.90)
        self.exaggeration_spin.setValue(0.40)
        self.cfg_spin.setValue(0.45)
        self.temperature_spin.setValue(0.30)
        self.repetition_spin.setValue(1.80)
        self.pause_spin.setValue(0.35)
        # MP3 kalite
        bitrate_idx = self.mp3_bitrate_combo.findData("192k")
        if bitrate_idx >= 0:
            self.mp3_bitrate_combo.setCurrentIndex(bitrate_idx)
        # Tema
        theme_idx = self.theme_combo.findData("system")
        if theme_idx >= 0:
            self.theme_combo.setCurrentIndex(theme_idx)
        # Voice
        self.voice_prompt_path = None
        self.voice_label.setText("Ses örneği seçilmedi; varsayılan ses kullanılacak.")
        self.btn_play_voice.setEnabled(False)
        self.btn_clear_voice.setEnabled(False)
        self._refresh_voice_warning()
        # Output dir
        self._set_output_dir(self._default_output_dir(), save=True)

        self.update_settings_summary()
        self.update_text_info()
        self.status_label.setText("Tüm ayarlar varsayılana sıfırlandı.")

    def _on_theme_changed(self, _index: int):
        theme = self.theme_combo.currentData() if hasattr(self, "theme_combo") else "system"
        apply_theme(QApplication.instance(), theme)
        self._save_current_settings()

    def _set_outputs_enabled(self, enabled: bool):
        for button in (self.btn_play, self.btn_stop, self.btn_save_wav, self.btn_save_mp3):
            button.setEnabled(enabled)

    def _set_engine_actions_enabled(self, enabled: bool):
        self.btn_generate.setEnabled(enabled)

    def _set_busy(self, busy: bool, message: str | None = None):
        self._set_engine_actions_enabled(not busy and self.engine is not None)
        if message:
            self.status_label.setText(message)
        if busy:
            self.progress.setRange(0, 0)

    def on_generate(self):
        text = self.text_edit.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "Uyarı", "Metin boş.")
            return
        if not self.engine:
            QMessageBox.warning(self, "Uyarı", "Motor henüz hazır değil.")
            return

        # Referans ses örneği yoksa kullanıcıyı uyar.
        if not self.voice_prompt_path and not self._voice_warning_dismissed:
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Icon.Warning)
            box.setWindowTitle("Referans ses örneği yok")
            box.setText(
                "Referans ses örneği seçmediniz.\n"
                "Varsayılan ses kullanılacak; ses robotik olabilir."
            )
            box.setInformativeText("Ses Örneği Seç, Yine de Üret veya İptal.")
            btn_select = box.addButton("Ses Örneği Seç", QMessageBox.ButtonRole.AcceptRole)
            btn_proceed = box.addButton("Yine de Üret", QMessageBox.ButtonRole.DestructiveRole)
            btn_cancel = box.addButton("İptal", QMessageBox.ButtonRole.RejectRole)
            box.setDefaultButton(btn_select)
            box.exec()
            clicked = box.clickedButton()
            if clicked == btn_select:
                self.on_select_voice()
                return  # Bu üretim iptal; kullanıcı ses seçtiyse bir sonraki Üret'te devam eder
            if clicked == btn_cancel:
                return
            # "Yine de Üret" -> oturumda bir daha sorma
            self._voice_warning_dismissed = True

        self.last_text = text
        self._save_current_settings()

        chunks = chunker.split_into_chunks(text)
        if not chunks:
            QMessageBox.warning(self, "Uyarı", "Metin boş.")
            return

        # Madde 3: Çok parçalı üretim uyarısı
        parts = len(chunks)
        if parts > CONFIRM_CHUNK_COUNT:
            reply = QMessageBox.question(
                self,
                "Çok parçalı üretim",
                f"{parts} parça üretilecek. Bu uzun sürer.\nDevam edilsin mi?",
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        elif parts > WARN_CHUNK_COUNT:
            QMessageBox.warning(
                self,
                "Parçalı üretim",
                f"Metin {parts} parçaya bölündü. Üretim uzun sürebilir.",
            )

        self._synth_cancel_requested = False
        self._set_busy(True, f"Üretiliyor... 0/{len(chunks)}")
        self.progress.setRange(0, len(chunks) * 1000)
        self.progress.setValue(0)

        self._synth_dialog = SynthesisDialog(len(chunks), self)
        self._synth_dialog.show()

        self._synth_worker = SynthWorker(self.engine, chunks, self._current_synthesis_settings())
        self._synth_dialog.cancel_requested.connect(self.on_cancel_synthesis)
        self._synth_worker.chunk_started.connect(self._on_synth_chunk_started)
        self._synth_worker.sampling_progress.connect(self._on_synth_sampling_progress)
        self._synth_worker.chunk_done.connect(self._on_synth_chunk_done)
        self._synth_worker.finished_ok.connect(self._on_synth_done)
        self._synth_worker.cancelled.connect(self._on_synth_cancelled)
        self._synth_worker.failed.connect(self._on_synth_failed)
        self._synth_worker.start()

    def on_cancel_synthesis(self):
        if not self._synth_worker or not self._synth_worker.isRunning():
            return
        if self._synth_cancel_requested:
            return

        self._synth_cancel_requested = True
        self._synth_worker.request_cancel()
        self.status_label.setText("Üretim durduruluyor...")
        audio_player.stop()
        if self._synth_dialog:
            self._synth_dialog.cancel_button.setEnabled(False)
            self._synth_dialog.status_label.setText("Üretim durduruluyor...")
            self._synth_dialog.detail.appendPlainText("Üretim durduruluyor; model yanıt vermezse işlem zorla kesilecek.")
        QTimer.singleShot(1200, self._force_stop_synthesis)

    def _force_stop_synthesis(self):
        if not self._synth_cancel_requested:
            return

        worker = self._synth_worker
        if worker and worker.isRunning():
            worker.request_cancel()
            worker.terminate()
            worker.wait(2500)

        self._synth_worker = None
        self._synth_cancel_requested = False
        self._reset_progress()
        self._set_busy(False, "Üretim durduruldu.")
        if self._synth_dialog:
            self._synth_dialog.finish_error("Üretim durduruldu.")

    def _on_synth_chunk_started(self, index: int, total: int, text: str):
        self.status_label.setText(f"Üretiliyor... Parça {index}/{total}")
        if self._synth_dialog:
            self._synth_dialog.chunk_started(index, total, text)

    def _on_synth_sampling_progress(
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
            f"Üretiliyor... Parça {index}/{total_chunks}: %{percent} ({current}/{total_steps}) | "
            f"Geçen: {elapsed} | Kalan: {remaining}{rate_text}"
        )
        if self._synth_dialog:
            self._synth_dialog.sampling_progress(index, total_chunks, percent, current, total_steps, elapsed, remaining, rate)

    def _on_synth_chunk_done(self, done: int, total: int, seconds: float):
        self.progress.setRange(0, total * 1000)
        self.progress.setValue(done * 1000)
        self.status_label.setText(f"Üretiliyor... {done}/{total} tamamlandı")
        if self._synth_dialog:
            self._synth_dialog.chunk_done(done, total, seconds)

    def _on_synth_done(self, wav, sr):
        if self._synth_cancel_requested:
            self._on_synth_cancelled("Üretim kullanıcı tarafından durduruldu.")
            return
        self._synth_worker = None
        wav = trim_leading_silence(wav, sr)
        self.last_wav = wav
        self.last_sr = sr
        self._set_outputs_enabled(True)
        duration_text = f"{wav.shape[-1] / sr:.1f} sn"
        self.last_output_path = self._auto_save_generated_wav(wav, sr, self.last_text or self.text_edit.toPlainText())
        self._add_history_entry(self.last_output_path, self.last_text or self.text_edit.toPlainText(), duration_text)
        message = f"Üretildi - {duration_text} @ {sr} Hz"
        self._reset_progress()
        self._set_busy(False, message)
        # Madde 1: Sayaç
        self.production_count += 1
        self.stats_label.setText(f"Toplam: {self.production_count} üretim")
        # Madde 2: Last path
        filename = os.path.basename(self.last_output_path) if self.last_output_path else "—"
        self.status_label.setText(f"{message} | Son: {filename}")
        if self._synth_dialog:
            self._synth_dialog.finish_ok(message)
        audio_player.play_tensor(wav, sr)

        # Kuyruk: tamamlanan entry'yi listeden çıkar, sonrakini başlat
        if self._queue_running and self._queue:
            self._queue.pop(0)
            self._refresh_queue_list()
            self._process_next_queue_item()

    def _on_synth_cancelled(self, msg: str):
        self._synth_worker = None
        self._synth_cancel_requested = False
        self._reset_progress()
        self._set_busy(False, msg)
        if self._synth_dialog:
            self._synth_dialog.finish_error(msg)
        # Kuyruk: iptal edildi, kalan entry'ler korunur
        if self._queue_running:
            self._queue_running = False
            self.status_label.setText(f"Kuyruk durduruldu. {len(self._queue)} metin kaldı.")

    def _on_synth_failed(self, msg: str):
        if self._synth_cancel_requested:
            self._on_synth_cancelled("Üretim kullanıcı tarafından durduruldu.")
            return
        self._synth_worker = None
        self._reset_progress()
        self._set_busy(False, "Sentez başarısız.")
        if self._synth_dialog:
            self._synth_dialog.finish_error(msg)
        self._show_error("Sentez hatası", msg)

    def _auto_save_generated_wav(self, wav, sr, text: str) -> str:
        os.makedirs(self.output_dir, exist_ok=True)
        file_path = unique_path(self.output_dir, safe_filename_from_text(text, ".wav"))
        sf.write(file_path, wav.squeeze().cpu().numpy(), sr)
        return str(file_path)

    def on_play(self):
        if self.last_wav is not None and self.last_sr is not None:
            audio_player.play_tensor(self.last_wav, self.last_sr)

    def on_save_wav(self):
        if self.last_wav is None:
            return
        default_path = self.last_output_path or self._make_output_path(".wav")
        file_path, _ = QFileDialog.getSaveFileName(self, "WAV olarak kaydet", default_path, "WAV (*.wav)")
        if not file_path:
            return
        sf.write(file_path, self.last_wav.squeeze().cpu().numpy(), self.last_sr)
        self.last_output_path = file_path
        self._add_history_entry(file_path, self.last_text or self.text_edit.toPlainText(), f"{self.last_wav.shape[-1] / self.last_sr:.1f} sn")
        self.status_label.setText(f"Kaydedildi: {file_path}")

    def on_save_mp3(self):
        if self.last_wav is None:
            return
        default_path = self._make_output_path(".mp3")
        file_path, _ = QFileDialog.getSaveFileName(self, "MP3 olarak kaydet", default_path, "MP3 (*.mp3)")
        if not file_path:
            return
        try:
            from pydub import AudioSegment

            data_np = np.clip(self.last_wav.squeeze().cpu().numpy(), -1.0, 1.0)
            data = (data_np * 32767).astype(np.int16).tobytes()
            seg = AudioSegment(data=data, sample_width=2, frame_rate=self.last_sr, channels=1)
            bitrate = self.mp3_bitrate_combo.currentData() if hasattr(self, "mp3_bitrate_combo") else "192k"
            seg.export(file_path, format="mp3", bitrate=bitrate)
            self._add_history_entry(file_path, self.last_text or self.text_edit.toPlainText(), f"{self.last_wav.shape[-1] / self.last_sr:.1f} sn")
            self.status_label.setText(f"Kaydedildi: {file_path}")
        except Exception as e:
            QMessageBox.warning(
                self,
                "MP3 kayıt başarısız",
                f"MP3 kaydı yapılamadı. WAV olarak kaydedebilirsin.\n\nAyrıntı:\n{e}",
            )

    def _reset_progress(self):
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
