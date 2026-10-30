"""
Voxora Studio - PyQt6 ana pencere.

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
from i18n import t, set_language as ui_set_language, language as ui_language, LANGUAGES as UI_LANGUAGES

import logging
import os
import re
import subprocess
import unicodedata
from pathlib import Path

import numpy as np
import soundfile as sf
from PyQt6.QtCore import QEasingCurve, QMetaObject, QPropertyAnimation, QSize, QThread, QTimer, Qt, pyqtSlot
from PyQt6.QtGui import QColor, QFont, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGraphicsOpacityEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QSystemTrayIcon,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

import audio_player
import audio_compressor
from app_state import load_history, load_settings, save_history, save_settings
import chunker
from config import (
    DEFAULT_ENGINE,
    DEFAULT_MP3_BITRATE,
    DEFAULT_OPUS_BITRATE,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_OUTPUT_FORMAT,
    OUTPUT_FORMAT_EXTENSIONS,
    OUTPUT_FORMAT_MP3,
    OUTPUT_FORMAT_OPUS,
    OUTPUT_FORMAT_WAV,
    VALID_OUTPUT_FORMATS,
)
from file_utils import safe_filename_from_text, safe_remove_to_trash, trash_available, unique_path

from .constants import (
    CONFIRM_CHUNK_COUNT,
    LANGUAGE_SAMPLES,
    LANGUAGES,
    OUTPUT_FORMAT_HELP,
    OUTPUT_FORMAT_OPTIONS,
    PRESETS,
    WARN_CHUNK_COUNT,
    format_label,
    quality_options_for,
)
from . import engines as engine_registry
from .branding import BRAND_PRIMARY, BRAND_SECONDARY, DISPLAY_NAME, __version__
from .dialogs import ModelLoadDialog, SynthesisDialog, VoiceGuideDialog
from .icons import navigation_icon
from .theme import (
    application_icon,
    apply_application_theme,
    mark_muted,
    theme_tokens,
)
from .widgets import ActionButton, FormatTile, PageHeader, SectionCard, StatusPill, WaveformView
from .workers import CompressWorker, EngineLoader, SynthWorker, UpdateWorker

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
    wav: np.ndarray,
    sr: int,
    threshold: float = 0.005,
    max_trim_ms: int = 500,
    pre_buffer_ms: int = 20,
) -> np.ndarray:
    """Sentez çıktısının başındaki sessiz kısmı kırp.

    Mutlak genlik eşiği yöntemiyle ilk sesli örneği bulur ve öncesini atar.
    Maks. ``max_trim_ms`` kırpılır; kırpma noktasından ``pre_buffer_ms`` kadar
    önce tutulur (atak geçişini yumuşatır). Tüm koşullar koruyucu: girdi
    zayıfsa (sr <= 0, boş, hepsi sessiz) orijinali döner.

    Args:
        wav: float32 mono dizi.
        sr: Sample rate (Hz).
        threshold: Genlik eşiği (0.0-1.0 normalize).
        max_trim_ms: Bu kadar ms'den fazla kırpma; üstü sınır.
        pre_buffer_ms: Kırpma noktası öncesi korunacak tampon (ms).

    Returns:
        Kırpılmış dizi (veya koşulsuz orijinal). dtype korunur.
    """
    # Tek yetkili uygulama tts_engine'de; burada geriye dönük ad korunur.
    from tts_engine import trim_leading_silence as _trim

    return _trim(
        wav,
        sr,
        threshold=threshold,
        max_trim_ms=max_trim_ms,
        pre_buffer_ms=pre_buffer_ms,
    )


def queue_split_lines(text: str) -> list[str]:
    """Çok satırlı metni dolu satırlara böler (boş olmayan, trim'li)."""
    return [line.strip() for line in text.splitlines() if line.strip()]


def format_bytes(count: int) -> str:
    """Baytı insan okunur biçime çevir: 512 B, 4,6 MB, 2,99 GB."""
    if count < 1024:
        return f"{count} B"
    if count < 1024 ** 2:
        return f"{count / 1024:.0f} KB"
    if count < 1024 ** 3:
        return f"{count / 1024 ** 2:.1f} MB".replace(".", ",")
    return f"{count / 1024 ** 3:.2f} GB".replace(".", ",")


def _as_mono(audio) -> np.ndarray:
    """Ses verisini float32 mono numpy dizisine çevir (torch tensörü de olur)."""
    if hasattr(audio, "detach"):
        audio = audio.detach().cpu().numpy()
    data = np.asarray(audio, dtype=np.float32)
    return data.reshape(-1) if data.ndim > 1 else data


def _dir_size(root: Path) -> int:
    """Klasörün toplam bayt boyutu (alt klasörler dahil).

    ``Path.rglob("*")`` 22 000 dosyalık bir motor klasöründe 1,4 s sürüyordu:
    her dosya için ayrı ``is_file()`` + ``stat()`` çağrısı ve Path nesnesi
    üretimi var. ``os.scandir`` aynı toplamı 30 ms'de veriyor (ölçüm:
    chatterbox site-packages boyutu). Modeller sekmesi her kurulum/kaldırma
    sonrası bu etiketi yeniliyor, bu yüzden fark kullanıcıya yansıyor.
    Sembolik bağlantılar izlenmez: döngü riski yok, çift sayım olmaz.
    """
    total = 0
    stack = [str(root)]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(entry.path)
                        else:
                            total += entry.stat(follow_symlinks=False).st_size
                    except OSError:
                        continue
        except OSError:
            continue
    return total


def _saved_float(settings: dict, key: str, default: float) -> float:
    """Ayar dosyasından sayısal değer oku; bozuk/eksik değerde varsayılana düş.

    Ayar dosyası elle düzenlenebilir ve eski sürümler farklı tip yazmış olabilir.
    Doğrudan ``float(...)`` çağrısı bozuk tek bir alan yüzünden pencereyi hiç
    açılmaz hâle getiriyordu (``ValueError: could not convert string to float``).
    ``bool`` bilinçli olarak reddedilir: ``True`` sessizce 1,0 sn hız olurdu.
    """
    raw = settings.get(key, default)
    if raw is None or isinstance(raw, bool):
        return float(default)
    try:
        return float(raw)
    except (TypeError, ValueError):
        log.warning("Ayar değeri sayı değil, varsayılan kullanılıyor: %s=%r", key, raw)
        return float(default)


def history_delete_dialog_texts(trash_ok: bool) -> tuple[str, str]:
    """Silme diyaloğu metinleri (saf, test edilebilir).

    Returns:
        (bilgi_metni, sil_düğmesi_etiketi).
    """
    if trash_ok:
        return (
            t("Ses dosyalarını Geri Dönüşüm'e taşıyabilir veya sadece geçmiş listesinden kaldırabilirsin."),
            t("Geri Dönüşüm'e Taşı"),
        )
    return (
        t("Geri Dönüşüm kullanılamıyor (send2trash kurulu değil); dosyalar KALICI olarak silinir."),
        t("Kalıcı Sil"),
    )


def apply_theme(app, theme: str) -> str:
    """Qt temasını uygula: light / dark / system."""
    return apply_application_theme(app, theme)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(DISPLAY_NAME)
        self.setWindowIcon(application_icon())
        self.resize(1080, 760)
        self.setMinimumSize(920, 640)

        self.engine = None
        self.last_wav = None
        self.last_sr = None
        self.last_output_path: str | None = None
        self.last_text: str = ""
        self.voice_prompt_path: str | None = None
        self.output_dir = self._default_output_dir()
        self.settings = load_settings()
        ui_set_language(self.settings.get("ui_language", "en"))
        self.history = load_history()
        # Motor seçimi: "chatterbox" (varsayılan) veya "ema"
        self._engine_name: str = DEFAULT_ENGINE
        self._engine_loading: bool = False
        # EMA aktifken seçili kalmayan Chatterbox dili burada saklanır.
        self._chatterbox_language_id: str = "tr"
        self._loader: QThread | None = None
        self._synth_worker: SynthWorker | None = None
        self._synth_dialog: SynthesisDialog | None = None
        self._synth_cancel_requested = False
        self._history_query: str = ""  # Geçmiş arama filtresi
        self._queue: list[str] = []  # Toplu üretim kuyruğu
        self._voice_warning_dismissed: bool = False  # Oturum-içi: modal bir daha gösterme
        self._queue_running: bool = False
        self.production_count: int = int(self.settings.get("production_count", 0))
        self._compress_files: list[str] = []
        self._compress_worker: CompressWorker | None = None
        self.compress_output_dir: str | None = self.settings.get("compress_output_dir") or None
        self._close_requested = False
        self._close_finalized = False
        # Çıktı biçimi/kalite (Ayarlar → Çıktı); _load_saved_settings günceller.
        self._output_format = DEFAULT_OUTPUT_FORMAT
        self._quality_by_format = {
            OUTPUT_FORMAT_WAV: "",
            OUTPUT_FORMAT_MP3: DEFAULT_MP3_BITRATE,
            OUTPUT_FORMAT_OPUS: DEFAULT_OPUS_BITRATE,
        }
        self._settings_saved_on_close = False
        self._resolved_theme = "dark"
        self._page_transition = None
        self._model_worker = None
        self._first_run_dialog = None
        self._update_worker: UpdateWorker | None = None
        self._update_manual = False
        self._update_info = None
        self._update_last_check = str(self.settings.get("update_last_check", "") or "")
        # Dil değişiminde canlı yenilenecek statik metin bağları: (setter, key, kwargs)
        self._tr_items: list[tuple] = []

        self._build_ui()
        self._load_saved_settings()
        # İlk açılış: hiç indirilebilir motor kurulu değilse sihirbazı göster.
        QTimer.singleShot(0, self._maybe_show_first_run)
        # Sistem tepsisi simgesi: t("Kapatılınca tepsiye küçült") tercihi buna
        # bağlıdır. Her zaman oluşturulur; tercih kapalıysa kullanılmaz.
        self._build_tray()
        self._refresh_history_list()
        self.update_text_info()
        self.update_settings_summary()
        self._init_engine_async()
        self._show_update_current()
        self._update_timer = QTimer(self)
        self._update_timer.setSingleShot(True)
        self._update_timer.timeout.connect(self._update_startup_check)
        self._update_timer.start(30_000)
        # Güncelleme sonrası ilk açılış: eski sürüm klasörlerini sessizce temizle.
        QTimer.singleShot(2_500, self._run_update_cleanup)
        # İlk tema yükleme: ayar varsa uygula (comboBox sonradan setCurrentIndex tetikler)
        theme = self.settings.get("theme", "dark") if self.settings else "dark"
        self._resolved_theme = apply_theme(QApplication.instance(), theme)
        self._refresh_theme_icons()

    def _bind_text(self, setter, key: str, **kwargs) -> None:
        """Statik bir metni kaydet; dil değişince ``setter`` yeniden uygulanır.

        ``setter`` bir ``setText``/``setToolTip`` benzeri çağrılabilir olmalıdır.
        Metin anahtarı Türkçe tutulur, çeviri ``t()`` üzerinden gelir; böylece
        canlı dil değişiminde yeniden kurulum gerekmez.
        """
        self._tr_items.append((setter, key, kwargs))
        setter(t(key, **kwargs))

    def _render_stats_counter(self, text: str) -> None:
        """Ust sayaci guncel production_count ile yazar (canli dil icin)."""
        self.stats_label.setText(text.format(n=self.production_count))

    def _retranslate_ui(self) -> None:
        """Açık arayüzdeki kayıtlı statik metinleri seçili dile göre yenile."""
        for setter, key, kwargs in list(self._tr_items):
            try:
                setter(t(key, **kwargs))
            except RuntimeError:
                # C++ tarafı silinmiş widget: bağ ölü, sessizce atla.
                continue

    def _refresh_dynamic_texts(self) -> None:
        """Dile bağlı dinamik metinleri (özet, sayaç, kartlar) yeniden üret."""
        for name in (
            "_refresh_text_stats",
            "update_settings_summary",
            "update_text_info",
            "_refresh_models_page",
            "_refresh_models_disk_label",
            "_refresh_system_labels",
            "_refresh_queue_list",
            "_refresh_history_list",
            "_refresh_format_tiles",
            "_refresh_quality_options",
            "_refresh_output_dir_label",
            "_show_update_current",
        ):
            method = getattr(self, name, None)
            if callable(method):
                try:
                    method()
                except (RuntimeError, AttributeError, TypeError):
                    continue

    def _build_ui(self):
        central = QWidget()
        central.setObjectName("appShell")
        self.setCentralWidget(central)
        shell = QVBoxLayout(central)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)

        # Üst gezinme çubuğu: marka solda, sekmeler yanında.
        self.topbar = QFrame()
        self.topbar.setObjectName("topNav")
        topbar_row = QHBoxLayout(self.topbar)
        topbar_row.setContentsMargins(20, 10, 20, 10)
        topbar_row.setSpacing(16)
        self.brand_logo = QLabel()
        self.brand_logo.setPixmap(application_icon().pixmap(28, 28))
        self.brand_logo.setFixedSize(30, 30)
        self.brand_logo.setToolTip(DISPLAY_NAME)
        brand_text = QLabel(f"{BRAND_PRIMARY} <span style=\"color:{'#8B7CF6'}\">•</span> {BRAND_SECONDARY}")
        brand_text.setObjectName("brandTitle")
        self.brand_version = QLabel(f"v{__version__}")
        self.brand_version.setObjectName("brandVersion")
        self.brand_version.setToolTip(t("{DISPLAY_NAME} sürümü: {__version__}", DISPLAY_NAME=DISPLAY_NAME, __version__=__version__))
        topbar_row.addWidget(self.brand_logo)
        topbar_row.addWidget(brand_text)
        topbar_row.addWidget(self.brand_version)
        topbar_row.addSpacing(14)

        nav_items = [
            ("Üretim", "generate", 0),
            ("Arşiv", "history", 1),
            ("Araçlar", "compress", 2),
            ("Modeller", "download", 3),
            ("Ayarlar", "settings", 4),
        ]
        self._nav_labels = [label for label, _, _ in nav_items]
        self._nav_icon_names = [icon_name for _, icon_name, _ in nav_items]
        self._nav_buttons = []
        for label, icon_name, index in nav_items:
            button = QPushButton(t(label))
            button.setIcon(navigation_icon(icon_name))
            button.setIconSize(QSize(17, 17))
            button.setProperty("topnav", True)
            button.setCheckable(True)
            button.clicked.connect(lambda checked=False, i=index: self._switch_page(i))
            self._bind_text(button.setText, label)
            topbar_row.addWidget(button)
            self._nav_buttons.append(button)
        self._nav_buttons[0].setChecked(True)
        topbar_row.addStretch(1)
        self.stats_label = StatusPill("", "neutral")
        self._bind_text(
            self._render_stats_counter,
            "Toplam: {n} üretim",
        )
        topbar_row.addWidget(self.stats_label)
        shell.addWidget(self.topbar)

        content = QWidget()
        content.setObjectName("pageRoot")
        root = QVBoxLayout(content)
        root.setContentsMargins(24, 14, 24, 10)
        root.setSpacing(12)
        shell.addWidget(content, stretch=1)

        self.btn_generate = ActionButton(t("Ses Üret"), variant="primary", size="large", icon_name="generate")
        self.btn_generate.setMinimumWidth(154)
        self.btn_compress_start = ActionButton(
            t("Sıkıştırmayı Başlat"), variant="primary", size="large", icon_name="compress"
        )
        self.btn_model_cancel = ActionButton(
            "Durdur", variant="secondary", size="large", icon_name="close"
        )
        self.btn_model_cancel.setVisible(False)
        self.btn_model_cancel.clicked.connect(self.on_cancel_model_install)
        self._page_action_stack = QStackedWidget()
        self._page_action_stack.setObjectName("pageActionStack")
        self._page_action_stack.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
        for action in (self.btn_generate, None, self.btn_compress_start, self.btn_model_cancel, None):
            action_page = QWidget()
            action_layout = QHBoxLayout(action_page)
            action_layout.setContentsMargins(0, 0, 0, 0)
            if action is not None:
                action_layout.addWidget(action)
            self._page_action_stack.addWidget(action_page)

        self._page_meta = (
            ("Ses Üretim Stüdyosu", "Metninizi doğal ve etkileyici bir sese dönüştürün"),
            ("Üretim Arşivi", "Seslerinizi bulun, dinleyin ve yeniden kullanın"),
            ("Araçlar", "Sıkıştırma ve sistem araçları tek merkezde"),
            ("Ses Modelleri", "Motorları indirin, kurun ve disk kullanımını yönetin"),
            ("Stüdyo Ayarları", "Ses, çıktı ve sistem tercihlerinizi yönetin"),
        )
        self.page_header = PageHeader(
            t(self._page_meta[0][0]), t(self._page_meta[0][1]), action=self._page_action_stack
        )
        root.addWidget(self.page_header)

        self.pages = QStackedWidget()
        self.pages.setObjectName("workspacePages")
        self.pages.addWidget(self._build_generate_page())
        self.pages.addWidget(self._build_history_page())
        self.pages.addWidget(self._build_compress_page())
        self.pages.addWidget(self._build_models_page())
        self.pages.addWidget(self._build_settings_page())
        root.addWidget(self.pages, stretch=1)

        status_bar = QFrame()
        status_bar.setObjectName("statusBar")
        status_row = QHBoxLayout(status_bar)
        status_row.setContentsMargins(14, 8, 14, 8)
        status_row.setSpacing(10)
        self.engine_status_pill = StatusPill("MOTOR", "info")
        self.status_label = QLabel(t("Motor yükleniyor..."))
        self.status_label.setObjectName("statusMessage")
        self.status_label.setWordWrap(True)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        self.progress.setMaximumWidth(180)
        status_row.addWidget(self.engine_status_pill)
        status_row.addWidget(self.status_label, stretch=1)
        status_row.addWidget(self.progress)
        root.addWidget(status_bar)

        self._connect_ui_signals()
        self._setup_shortcuts()
        self._set_button_tooltips()
        self._set_outputs_enabled(False)
        self._set_engine_actions_enabled(False)

    def _make_scroll_page(self, body: QWidget) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(body)
        return scroll

    def _build_generate_page(self) -> QScrollArea:
        body = QWidget()
        body.setObjectName("pageBody")
        main_layout = QHBoxLayout(body)
        main_layout.setContentsMargins(0, 0, 0, 8)
        main_layout.setSpacing(14)

        # Sol kolon: metin stüdyosu (ana odak)
        left_col = QVBoxLayout()
        left_col.setSpacing(14)
        editor_card = SectionCard("Metin", t("Metni yazın ya da yapıştırın; üretim tek tıkla."))
        editor_toolbar = QHBoxLayout()
        editor_toolbar.setSpacing(8)
        self.text_stats_label = QLabel(t("0 karakter • 0 kelime • 0 parça • ~0 sn"))
        self.text_stats_label.setObjectName("statusMessage")
        mark_muted(self.text_stats_label)
        self.settings_summary_label = QLabel(t("Türkçe • Anlatıcı • 0.90x • Varsayılan ses"))
        mark_muted(self.settings_summary_label)
        self.settings_summary_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.settings_summary_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.settings_summary_label.setMinimumWidth(0)
        self.settings_summary_label.setWordWrap(True)
        self.btn_paste = ActionButton(t("Yapıştır"), variant="ghost", size="small", icon_name="paste")
        self.btn_clean_text = ActionButton("Temizle", variant="ghost", size="small", icon_name="clean")
        self.text_stats_label.setMinimumWidth(0)
        self.text_stats_label.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        editor_toolbar.addWidget(self.text_stats_label)
        editor_toolbar.addWidget(self.settings_summary_label, stretch=1)
        editor_toolbar.addWidget(self.btn_paste)
        editor_toolbar.addWidget(self.btn_clean_text)
        editor_card.content_layout.addLayout(editor_toolbar)
        self.text_edit = QTextEdit()
        self.text_edit.setPlaceholderText(t("Metni buraya yazın ya da Yapıştır ile panodan alın.\nHer dolu satır ayrı bir ses olarak üretilebilir."))
        self.text_edit.setFont(QFont("Segoe UI", 11))
        editor_card.content_layout.addWidget(self.text_edit, stretch=1)
        left_col.addWidget(editor_card, stretch=3)

        queue_card = SectionCard(t("Toplu Üretim Kuyruğu"), t("Kuyruğa eklediğiniz her satır sırayla üretilir."))
        queue_buttons = QHBoxLayout()
        queue_buttons.setSpacing(8)
        self.btn_queue_add = ActionButton("Metin Ekle", variant="secondary", size="small", icon_name="add")
        self.btn_queue_load = ActionButton(t("Dosyadan Yükle"), variant="secondary", size="small", icon_name="upload")
        self.btn_queue_run = ActionButton(t("Tümünü Üret"), variant="secondary", size="small", icon_name="queue")
        self.btn_queue_clear = ActionButton("Temizle", variant="ghost", size="small", icon_name="delete")
        for button in (self.btn_queue_add, self.btn_queue_load, self.btn_queue_run, self.btn_queue_clear):
            queue_buttons.addWidget(button)
        queue_buttons.addStretch(1)
        queue_card.content_layout.addLayout(queue_buttons)
        self.queue_list = QListWidget()
        self.queue_list.setMinimumHeight(90)
        queue_card.content_layout.addWidget(self.queue_list, stretch=1)
        left_col.addWidget(queue_card, stretch=1)

        # Sağ kolon: ses profili + sonuç
        right_col = QVBoxLayout()
        right_col.setSpacing(14)
        voice_card = SectionCard("Ses Profili", t("Referans ses yoksa varsayılan ses kullanılır."))
        self.voice_card = voice_card
        self.voice_label = QLabel(t("Ses örneği seçilmedi"))
        self.voice_label.setWordWrap(True)
        mark_muted(self.voice_label)
        voice_row = QHBoxLayout()
        voice_row.setSpacing(6)
        self.btn_select_voice = ActionButton(t("Seç"), variant="secondary", size="small", icon_name="microphone")
        self.btn_select_voice.setToolTip(t("Referans ses örneği dosyası seç (Ctrl+Shift+V)"))
        self.btn_play_voice = ActionButton("Dinle", variant="ghost", size="small", icon_name="play")
        self.btn_clear_voice = ActionButton(t("Kaldır"), variant="ghost", size="small", icon_name="close")
        self.btn_play_voice.setEnabled(False)
        self.btn_clear_voice.setEnabled(False)
        voice_row.addWidget(self.btn_select_voice)
        voice_row.addWidget(self.btn_play_voice)
        voice_row.addWidget(self.btn_clear_voice)
        voice_row.addStretch(1)
        self.btn_sample_voice_text = ActionButton("Rehber", variant="ghost", size="small", icon_name="info")
        voice_row.addWidget(self.btn_sample_voice_text)
        voice_card.content_layout.addWidget(self.voice_label)
        voice_card.content_layout.addLayout(voice_row)
        voice_row2 = QHBoxLayout()
        voice_row2.setSpacing(6)
        voice_row2.addStretch(1)
        right_col.addWidget(voice_card)

        # Ses tasarımı yalnız VoxCPM2'de var: referans ses olmadan tarifle ses.
        self.voice_design_card = SectionCard(
            t("Ses Tasarımı"),
            t("Referans ses olmadan, tarifle yeni bir ses üretin (yalnız VoxCPM2)."),
        )
        design_row = QHBoxLayout()
        design_row.setSpacing(8)
        self.voice_design_edit = QLineEdit()
        self.voice_design_edit.setPlaceholderText(
            t("Örn: Genç bir kadın, sıcak ve sakin ton, hafif yavaş")
        )
        self.voice_design_edit.setToolTip(
            t("Yazdığınız tarif üretilen metnin başına parantez içinde eklenir.\n") +
            t("Cinsiyet, yaş, ton, duygu ve hız belirtebilirsiniz.")
        )
        design_row.addWidget(self.voice_design_edit, stretch=1)
        self.btn_design_clear = ActionButton(
            "Temizle", variant="ghost", size="small", icon_name="delete"
        )
        self.btn_design_clear.clicked.connect(self.voice_design_edit.clear)
        design_row.addWidget(self.btn_design_clear)
        self.voice_design_card.content_layout.addLayout(design_row)
        self.voice_design_card.setVisible(False)
        right_col.addWidget(self.voice_design_card)

        playback_card = SectionCard(t("Sonuç"), t("Üretim tamamlandığında ses burada görünür."))
        self.waveform_view = WaveformView()
        self.waveform_view.setMinimumHeight(70)
        playback_card.content_layout.addWidget(self.waveform_view)
        self.playback_hint = QLabel(t("Henüz ses üretilmedi."))
        mark_muted(self.playback_hint)
        self.playback_hint.setWordWrap(True)
        playback_card.content_layout.addWidget(self.playback_hint)
        self.btn_play = ActionButton("Oynat", variant="secondary", size="small", icon_name="play")
        self.btn_stop = ActionButton("Durdur", variant="ghost", size="small", icon_name="stop")
        self.btn_save_wav = ActionButton("WAV", variant="secondary", size="small", icon_name="save")
        self.btn_save_mp3 = ActionButton("MP3", variant="secondary", size="small", icon_name="download")
        playback_actions = QHBoxLayout()
        playback_actions.addWidget(self.btn_play)
        playback_actions.addWidget(self.btn_stop)
        playback_actions.addStretch(1)
        playback_actions.addWidget(self.btn_save_wav)
        playback_actions.addWidget(self.btn_save_mp3)
        playback_card.content_layout.addLayout(playback_actions)
        right_col.addWidget(playback_card)
        right_col.addStretch(1)

        main_layout.addLayout(left_col, stretch=3)
        main_layout.addLayout(right_col, stretch=1)
        return self._make_scroll_page(body)

    def _build_settings_page(self) -> QScrollArea:
        """Ayarlar A: sol kategori menüsü + tek kategori kartı sağda."""
        settings_tab = QWidget()
        settings_tab.setObjectName("pageBody")
        settings_layout = QHBoxLayout(settings_tab)
        settings_layout.setContentsMargins(0, 0, 0, 8)
        settings_layout.setSpacing(14)

        cat_card = SectionCard("Kategoriler", t("Ayar grubunu seçin."))
        cat_list = QVBoxLayout()
        cat_list.setSpacing(6)
        self._settings_cat_buttons = []
        cat_items = [("Ses", "sliders", 0), (t("Çıktı"), "folder", 1), (t("Görünüm"), "settings", 2), (t("Güncelleme"), "upload", 3), (t("Sıfırla"), "reset", 4)]
        for label, icon_name, index in cat_items:
            button = QPushButton(label)
            button.setIcon(navigation_icon(icon_name))
            button.setIconSize(QSize(17, 17))
            button.setProperty("subnav", True)
            button.setCheckable(True)
            button.clicked.connect(lambda checked=False, i=index: self._switch_settings_cat(i))
            cat_list.addWidget(button)
            self._settings_cat_buttons.append(button)
        self._settings_cat_buttons[0].setChecked(True)
        cat_list.addStretch(1)
        cat_card.content_layout.addLayout(cat_list)
        settings_layout.addWidget(cat_card)

        self._settings_stack = QStackedWidget()

        # Kategori 0: Ses
        voice_panel = QWidget()
        voice_col = QVBoxLayout(voice_panel)
        voice_col.setContentsMargins(0, 0, 0, 0)
        voice_col.setSpacing(14)
        settings_card = SectionCard(t("Ses Ayarları"), t("Ses motorunu seçin; profil veya ayrıntılı ayarla üretim karakterini belirleyin."))
        settings_panel = QWidget()
        settings_grid = QGridLayout(settings_panel)
        settings_grid.setContentsMargins(0, 0, 0, 0)
        settings_grid.setHorizontalSpacing(14)
        settings_grid.setVerticalSpacing(12)

        self.engine_combo = QComboBox()
        # Motor listesi app.engines kaydından gelir; donanıma uymayan motor
        # listede görünür ama seçilemez (kapalı öğe + gerekçe tooltip'te).
        self._populate_engine_combo()
        self.engine_combo.currentIndexChanged.connect(self._on_engine_changed)

        self.preset_combo = QComboBox()
        for preset_name in PRESETS:
            self.preset_combo.addItem(preset_name)
        narrator_index = self.preset_combo.findText("Anlatıcı")
        if narrator_index >= 0:
            self.preset_combo.setCurrentIndex(narrator_index)
        self.btn_apply_preset = ActionButton("Uygula", variant="secondary", size="small", icon_name="check")

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

        settings_grid.addWidget(QLabel("Ses motoru"), 0, 0)
        settings_grid.addWidget(self.engine_combo, 0, 1)
        lbl_hazır_ayar_lbl = QLabel()
        self._bind_text(lbl_hazır_ayar_lbl.setText, "Hazır ayar")
        settings_grid.addWidget(lbl_hazır_ayar_lbl, 1, 0)
        settings_grid.addWidget(self.preset_combo, 1, 1)
        settings_grid.addWidget(self.btn_apply_preset, 1, 2, 1, 2)
        settings_grid.addWidget(QLabel("Dil"), 2, 0)
        settings_grid.addWidget(self.language_combo, 2, 1)
        lbl_hız_lbl = QLabel()
        self._bind_text(lbl_hız_lbl.setText, "Hız")
        settings_grid.addWidget(lbl_hız_lbl, 2, 2)
        settings_grid.addWidget(self.speed_spin, 2, 3)
        lbl_i_fade_lbl = QLabel()
        self._bind_text(lbl_i_fade_lbl.setText, "İfade")
        settings_grid.addWidget(lbl_i_fade_lbl, 3, 0)
        settings_grid.addWidget(self.exaggeration_spin, 3, 1)
        settings_grid.addWidget(QLabel("Netlik"), 3, 2)
        settings_grid.addWidget(self.cfg_spin, 3, 3)
        lbl_yaratıcılık_lbl = QLabel()
        self._bind_text(lbl_yaratıcılık_lbl.setText, "Yaratıcılık")
        settings_grid.addWidget(lbl_yaratıcılık_lbl, 4, 0)
        settings_grid.addWidget(self.temperature_spin, 4, 1)
        settings_grid.addWidget(QLabel("Tekrar azaltma"), 4, 2)
        settings_grid.addWidget(self.repetition_spin, 4, 3)
        settings_grid.addWidget(QLabel("Duraklama"), 5, 0)
        settings_grid.addWidget(self.pause_spin, 5, 1)
        settings_grid.setColumnStretch(1, 1)
        settings_grid.setColumnStretch(3, 1)
        settings_card.content_layout.addWidget(settings_panel)
        voice_col.addWidget(settings_card)
        voice_col.addStretch(1)
        self._settings_stack.addWidget(voice_panel)

        # Kategori 1: Çıktı
        output_panel = QWidget()
        output_col = QVBoxLayout(output_panel)
        output_col.setContentsMargins(0, 0, 0, 0)
        output_col.setSpacing(14)
        output_card = SectionCard(t("Kayıt ve Kalite"), t("Otomatik çıktı klasörünü, çıktı biçimini ve kalitesini belirleyin."))
        output_panel_grid = QGridLayout()
        output_panel_grid.setContentsMargins(0, 0, 0, 0)
        output_panel_grid.setSpacing(8)
        self.output_dir_label = QLabel("")
        self.output_dir_label.setWordWrap(True)
        self.btn_select_output_dir = ActionButton(t("Klasör Seç"), variant="secondary", size="small", icon_name="folder")
        self.btn_open_output_dir = ActionButton(t("Klasörü Aç"), variant="ghost", size="small", icon_name="folder-open")
        self.btn_reset_output_dir = ActionButton(t("Varsayılana Dön"), variant="ghost", size="small", icon_name="reset")
        lbl_varsayılan_klasör_lbl = QLabel()
        self._bind_text(lbl_varsayılan_klasör_lbl.setText, "Varsayılan klasör")
        output_panel_grid.addWidget(lbl_varsayılan_klasör_lbl, 0, 0)
        output_panel_grid.addWidget(self.output_dir_label, 0, 1, 1, 3)
        output_panel_grid.addWidget(self.btn_select_output_dir, 1, 0)
        output_panel_grid.addWidget(self.btn_open_output_dir, 1, 1)
        output_panel_grid.addWidget(self.btn_reset_output_dir, 1, 2)
        self.format_tiles: dict[str, FormatTile] = {}
        format_row = QHBoxLayout()
        format_row.setContentsMargins(0, 0, 0, 0)
        format_row.setSpacing(9)
        for format_key, format_title, format_description in OUTPUT_FORMAT_OPTIONS:
            tile = FormatTile(format_title, format_description)
            tile.clicked.connect(lambda fmt=format_key: self._on_output_format_selected(fmt))
            self.format_tiles[format_key] = tile
            format_row.addWidget(tile)
        self.quality_combo = QComboBox()
        self.quality_combo.currentIndexChanged.connect(self._on_output_quality_changed)
        format_help = QLabel(OUTPUT_FORMAT_HELP)
        format_help.setWordWrap(True)
        mark_muted(format_help)
        format_box = QVBoxLayout()
        format_box.setContentsMargins(0, 0, 0, 0)
        format_box.setSpacing(7)
        format_box.addLayout(format_row)
        format_box.addWidget(self.quality_combo)
        format_box.addWidget(format_help)
        format_label_widget = QLabel()
        self._bind_text(format_label_widget.setText, "Çıktı biçimi")
        format_label_widget.setAlignment(Qt.AlignmentFlag.AlignTop)
        output_panel_grid.addWidget(format_label_widget, 2, 0)
        output_panel_grid.addLayout(format_box, 2, 1, 1, 3)
        self.output_format_note = QLabel(t("Her üretim seçilen biçimde çıktı klasörüne kaydedilir; eski kayıtlar değişmez."))
        self.output_format_note.setWordWrap(True)
        mark_muted(self.output_format_note)
        output_panel_grid.addWidget(self.output_format_note, 3, 1, 1, 3)
        output_panel_grid.setColumnStretch(3, 1)
        output_card.content_layout.addLayout(output_panel_grid)

        compress_out_card = SectionCard(t("Sıkıştırma Çıktısı"), t("Sıkıştırılmış dosyalar için varsayılan konum."))
        self.compress_output_label = QLabel(t("(boş = orijinal dosyanın yanına kaydet)"))
        self.compress_output_label.setWordWrap(True)
        mark_muted(self.compress_output_label)
        compress_out_row = QHBoxLayout()
        compress_out_row.addWidget(self.compress_output_label, stretch=1)
        self.btn_compress_output_dir = ActionButton(t("Seç"), variant="secondary", size="small", icon_name="folder")
        self.btn_compress_output_dir.clicked.connect(self.on_compress_select_output_dir)
        self.btn_compress_clear_output = ActionButton("Temizle", variant="ghost", size="small", icon_name="close")
        self.btn_compress_clear_output.clicked.connect(self.on_compress_clear_output_dir)
        compress_out_row.addWidget(self.btn_compress_output_dir)
        compress_out_row.addWidget(self.btn_compress_clear_output)
        compress_out_card.content_layout.addLayout(compress_out_row)
        output_col.addWidget(output_card)
        output_col.addWidget(compress_out_card)
        output_col.addStretch(1)
        self._settings_stack.addWidget(output_panel)

        # Kategori 2: Görünüm
        look_panel = QWidget()
        look_col = QVBoxLayout(look_panel)
        look_col.setContentsMargins(0, 0, 0, 0)
        look_col.setSpacing(14)
        look_card = SectionCard(t("Görünüm"), t("Tema ve arayüz tercihleri."))
        look_grid = QGridLayout()
        look_grid.setContentsMargins(0, 0, 0, 0)
        look_grid.setSpacing(8)
        self.theme_combo = QComboBox()
        self.theme_combo.addItem(t("Karanlık"), "dark")
        self.theme_combo.addItem(t("Açık"), "light")
        self.theme_combo.addItem("Sistem", "system")
        self.theme_combo.currentIndexChanged.connect(self._on_theme_changed)
        look_grid.addWidget(QLabel("Tema"), 0, 0)
        look_grid.addWidget(self.theme_combo, 0, 1, 1, 2)
        look_grid.setColumnStretch(1, 1)

        # Ortak masaüstü seçenekleri: otomatik başlat + tepsiye küçült.
        from app_options import (AutostartController, TrayOption,
                                  build_settings_widgets)

        self._autostart_controller = AutostartController(
            app_name="VoxoraStudio",
            get_setting=lambda k, d=None: self.settings.get(k, d),
            set_setting=self._set_option,
            entry_point=str(Path(__file__).resolve().parent.parent / "app.py"))
        self._tray_option = TrayOption(
            get_setting=lambda k, d=None: self.settings.get(k, d),
            set_setting=self._set_option)
        self._autostart_cb, self._tray_cb = build_settings_widgets(
            self._autostart_controller, self._tray_option)
        lbl_windows_başlangıcı_lbl = QLabel()
        self._bind_text(lbl_windows_başlangıcı_lbl.setText, "Windows başlangıcı")
        look_grid.addWidget(lbl_windows_başlangıcı_lbl, 1, 0)
        look_grid.addWidget(self._autostart_cb, 1, 1, 1, 2)
        lbl_kapatma_davranışı_lbl = QLabel()
        self._bind_text(lbl_kapatma_davranışı_lbl.setText, "Kapatma davranışı")
        look_grid.addWidget(lbl_kapatma_davranışı_lbl, 2, 0)
        look_grid.addWidget(self._tray_cb, 2, 1, 1, 2)
        self.ui_lang_combo = QComboBox()
        for _kod, _ad in UI_LANGUAGES:
            self.ui_lang_combo.addItem(_ad, _kod)
        self.ui_lang_combo.setCurrentIndex(
            max(0, self.ui_lang_combo.findData(ui_language())))
        self.ui_lang_combo.currentIndexChanged.connect(self._on_ui_language_changed)
        lbl_arayüz_dili_lbl = QLabel()
        self._bind_text(lbl_arayüz_dili_lbl.setText, "Arayüz dili")
        look_grid.addWidget(lbl_arayüz_dili_lbl, 3, 0)
        look_grid.addWidget(self.ui_lang_combo, 3, 1, 1, 2)

        look_card.content_layout.addLayout(look_grid)
        look_col.addWidget(look_card)
        look_col.addStretch(1)
        self._settings_stack.addWidget(look_panel)

        # Kategori 3: Güncelleme
        update_panel = QWidget()
        update_col = QVBoxLayout(update_panel)
        update_col.setContentsMargins(0, 0, 0, 0)
        update_col.setSpacing(14)
        update_card = SectionCard(t("Güncelleme"), t("Yeni sürümleri denetleyin ve tek tıkla kurun."))
        update_grid = QGridLayout()
        update_grid.setContentsMargins(0, 0, 0, 0)
        update_grid.setSpacing(8)
        self.update_status_label = QLabel("")
        self.update_status_label.setWordWrap(True)
        self.update_stats_label = QLabel("")
        self.update_stats_label.setWordWrap(True)
        mark_muted(self.update_stats_label)
        self.btn_update_check = ActionButton(t("Güncellemeleri Denetle"), variant="secondary", icon_name="refresh")
        self.btn_update_install = ActionButton(t("İndir ve Kur"), variant="primary", icon_name="download")
        self.btn_update_cancel = ActionButton(t("Vazgeç"), variant="ghost", icon_name="close")
        self.btn_update_check.clicked.connect(self.on_update_check)
        self.btn_update_install.clicked.connect(self.on_update_install)
        self.btn_update_cancel.clicked.connect(self.on_update_cancel)
        self.btn_update_install.setVisible(False)
        self.btn_update_cancel.setVisible(False)
        self.update_progress = QProgressBar()
        self.update_progress.setRange(0, 1000)
        self.update_progress.setVisible(False)
        update_grid.addWidget(self.update_status_label, 0, 0, 1, 3)
        update_grid.addWidget(self.update_stats_label, 1, 0, 1, 3)
        update_grid.addWidget(self.btn_update_check, 2, 0)
        update_grid.addWidget(self.btn_update_install, 2, 1)
        update_grid.addWidget(self.btn_update_cancel, 2, 2)
        update_grid.addWidget(self.update_progress, 3, 0, 1, 3)
        update_grid.setColumnStretch(0, 1)
        update_card.content_layout.addLayout(update_grid)
        update_col.addWidget(update_card)
        update_col.addStretch(1)
        self._settings_stack.addWidget(update_panel)

        # Kategori 4: Sıfırla
        reset_panel = QWidget()
        reset_col = QVBoxLayout(reset_panel)
        reset_col.setContentsMargins(0, 0, 0, 0)
        reset_col.setSpacing(14)
        reset_card = SectionCard(t("Sıfırlama"), t("Tüm ayarları varsayılana döndürür; geçmiş korunur."))
        self.btn_reset_settings = ActionButton(t("Tüm Ayarları Sıfırla"), variant="destructive", icon_name="reset")
        self.btn_reset_settings.setToolTip(t("Tüm ayarları varsayılana döndürür (geçmiş korunur)"))
        self.btn_reset_settings.clicked.connect(self.on_reset_all_settings)
        reset_card.content_layout.addWidget(self.btn_reset_settings)
        reset_col.addWidget(reset_card)
        reset_col.addStretch(1)
        self._settings_stack.addWidget(reset_panel)

        settings_layout.addWidget(self._settings_stack, stretch=1)
        return self._make_scroll_page(settings_tab)

    def _switch_settings_cat(self, index: int):
        if 0 <= index < self._settings_stack.count():
            self._settings_stack.setCurrentIndex(index)
            for i, button in enumerate(self._settings_cat_buttons):
                button.setChecked(i == index)

    def _build_history_page(self) -> QWidget:
        """Arşiv B: liste solda, seçili kaydın detayı sağda."""
        history_tab = QWidget()
        history_tab.setObjectName("pageBody")
        history_layout = QHBoxLayout(history_tab)
        history_layout.setContentsMargins(0, 0, 0, 8)
        history_layout.setSpacing(14)

        list_card = SectionCard(t("Arşiv"), t("Kayıt seçin; ayrıntısı sağda açılır."))
        self._history_search = QLineEdit()
        self._history_search.setPlaceholderText(t("Ara (ad veya metin)…"))
        self._history_search.setClearButtonEnabled(True)
        self._history_search.textChanged.connect(self._on_history_search_changed)
        list_card.content_layout.addWidget(self._history_search)
        self.history_list = QListWidget()
        self.history_list.itemSelectionChanged.connect(self._on_history_selection_changed)
        list_card.content_layout.addWidget(self.history_list, stretch=1)
        history_layout.addWidget(list_card, stretch=2)

        detail_card = SectionCard(t("Kayıt Ayrıntısı"), t("Seçili üretimin özeti ve eylemleri."))
        self._history_detail_name = QLabel(t("Kayıt seçilmedi"))
        self._history_detail_name.setObjectName("cardTitle")
        self._history_detail_name.setWordWrap(True)
        detail_card.content_layout.addWidget(self._history_detail_name)
        self._history_detail_wave = WaveformView()
        self._history_detail_wave.setMinimumHeight(64)
        self._history_detail_wave.setProperty("hasData", False)
        detail_card.content_layout.addWidget(self._history_detail_wave)
        self._history_detail_meta = QLabel("")
        self._history_detail_meta.setWordWrap(True)
        self._history_detail_meta.setTextFormat(Qt.TextFormat.RichText)
        mark_muted(self._history_detail_meta)
        detail_card.content_layout.addWidget(self._history_detail_meta)
        detail_actions = QGridLayout()
        detail_actions.setSpacing(8)
        self.btn_regenerate_history = ActionButton(t("Yeniden Üret"), variant="primary", icon_name="generate")
        self.btn_restore_history = ActionButton("Metni Geri Al", variant="secondary", icon_name="refresh")
        self.btn_play_history = ActionButton(t("Çal"), variant="secondary", icon_name="play")
        self.btn_open_history = ActionButton(t("Klasörde Göster"), variant="ghost", icon_name="folder-open")
        self.btn_delete_history = ActionButton("Sil", variant="destructive", icon_name="delete")
        self.btn_bulk_delete_history = ActionButton("Toplu Sil", variant="ghost", icon_name="delete")
        detail_actions.addWidget(self.btn_regenerate_history, 0, 0)
        detail_actions.addWidget(self.btn_restore_history, 0, 1)
        detail_actions.addWidget(self.btn_play_history, 0, 2)
        detail_actions.addWidget(self.btn_open_history, 1, 0)
        detail_actions.addWidget(self.btn_delete_history, 1, 1)
        detail_actions.addWidget(self.btn_bulk_delete_history, 1, 2)
        detail_card.content_layout.addLayout(detail_actions)
        detail_card.content_layout.addStretch(1)
        history_layout.addWidget(detail_card, stretch=3)
        return history_tab

    def _build_compress_page(self) -> QScrollArea:
        """Araçlar A: sol araç listesi + seçilen aracın sayfası sağda."""
        compress_tab = QWidget()
        compress_tab.setObjectName("pageBody")
        compress_layout = QHBoxLayout(compress_tab)
        compress_layout.setContentsMargins(0, 0, 0, 8)
        compress_layout.setSpacing(14)

        tools_card = SectionCard(t("Araçlar"), t("Bir araç seçin."))
        tools_list = QVBoxLayout()
        tools_list.setSpacing(6)
        self._tool_buttons = []
        tool_items = [
            (t("Sıkıştır (Opus)"), "compress", 0),
            ("Sistem Bilgisi", "info", 1),
        ]
        for label, icon_name, index in tool_items:
            button = QPushButton(label)
            button.setIcon(navigation_icon(icon_name))
            button.setIconSize(QSize(17, 17))
            button.setProperty("subnav", True)
            button.setCheckable(True)
            button.clicked.connect(lambda checked=False, i=index: self._switch_tool(i))
            tools_list.addWidget(button)
            self._tool_buttons.append(button)
        self._tool_buttons[0].setChecked(True)
        tools_list.addStretch(1)
        tools_card.content_layout.addLayout(tools_list)
        compress_layout.addWidget(tools_card)

        # Araç yığını
        self._tool_stack = QStackedWidget()
        self._tool_stack.setObjectName("toolStack")

        # Araç 0: Sıkıştır
        compress_body = QWidget()
        compress_col = QVBoxLayout(compress_body)
        compress_col.setContentsMargins(0, 0, 0, 0)
        compress_col.setSpacing(14)

        self.compress_files_card = SectionCard(
            "Kaynak Dosyalar",
            t("WAV, MP3, FLAC veya OGG dosyalarını listeye ekleyin."),
        )
        compress_buttons = QHBoxLayout()
        compress_buttons.setSpacing(8)
        self.btn_compress_add = ActionButton("Dosya Ekle", variant="secondary", size="small", icon_name="file-add")
        self.btn_compress_clear = ActionButton("Listeyi Temizle", variant="ghost", size="small", icon_name="delete")
        compress_buttons.addWidget(self.btn_compress_add)
        compress_buttons.addWidget(self.btn_compress_clear)
        compress_buttons.addStretch(1)
        self.compress_files_card.content_layout.addLayout(compress_buttons)
        self.compress_file_list = QListWidget()
        self.compress_file_list.setMinimumHeight(120)
        self.compress_files_card.content_layout.addWidget(self.compress_file_list)
        compress_col.addWidget(self.compress_files_card)

        options_card = SectionCard(t("Sıkıştırma Ayarları"), t("Konuşma için dengeli Opus kalitesini ve çıktı konumunu seçin."))
        bitrate_row = QHBoxLayout()
        bitrate_row.addWidget(QLabel("Bitrate:"))
        self.compress_bitrate_combo = QComboBox()
        for label, val in [(t("Düşük (32 kbps)"), "32k"), ("Normal (48 kbps)", "48k"), (t("Yüksek (64 kbps)"), "64k"), (t("Çok yüksek (96 kbps)"), "96k")]:
            self.compress_bitrate_combo.addItem(label, val)
        self.compress_bitrate_combo.setCurrentIndex(1)
        bitrate_row.addWidget(self.compress_bitrate_combo)
        bitrate_row.addStretch()
        self.compress_bitrate_combo.currentIndexChanged.connect(self._save_current_settings)
        options_card.content_layout.addLayout(bitrate_row)

        compress_col.addWidget(options_card)

        results_card = SectionCard(t("Sonuçlar"))
        self.compress_results = QListWidget()
        self.compress_results.setMinimumHeight(100)
        self.compress_results.setMaximumHeight(180)
        results_card.content_layout.addWidget(self.compress_results)
        compress_col.addWidget(results_card)
        compress_col.addStretch(1)
        self._tool_stack.addWidget(compress_body)

        # Araç 1: Sistem bilgisi
        sys_body = QWidget()
        sys_col = QVBoxLayout(sys_body)
        sys_col.setContentsMargins(0, 0, 0, 0)
        sys_col.setSpacing(14)
        sys_card = SectionCard("Sistem", "Motor, GPU, CUDA ve ffmpeg durumu.")
        self.device_label = QLabel(t("Cihaz: hazırlanıyor"))
        self.gpu_label = QLabel("GPU: kontrol ediliyor")
        self.btn_system_info = ActionButton(t("Ayrıntılı Bilgi"), variant="secondary", icon_name="info")
        sys_card.content_layout.addWidget(self.device_label)
        sys_card.content_layout.addWidget(self.gpu_label)
        sys_card.content_layout.addWidget(self.btn_system_info)
        sys_col.addWidget(sys_card)
        sys_col.addStretch(1)
        self._tool_stack.addWidget(sys_body)

        compress_layout.addWidget(self._tool_stack, stretch=1)
        return self._make_scroll_page(compress_tab)

    def _build_models_page(self) -> QScrollArea:
        """Modeller sayfası: motorları indir/kaldır, disk kullanımını gör.

        Kart başına bir motor. Üç durum vardır ve üçü de ayrı görünür:
        kurulu, indirilmedi, yarım (kütüphane var ağırlık yok ya da tersi).
        Donanıma uymayan motor kartı görünür ama eylem düğmesi kapalıdır —
        kullanıcı "neden yok" diye sormasın, gerekçeyi kartta okusun.
        """
        from app import engines as engine_registry
        from app import hardware, model_manager

        profile = hardware.detect()
        body = QWidget()
        body.setObjectName("pageBody")
        col = QVBoxLayout(body)
        col.setContentsMargins(0, 0, 0, 8)
        col.setSpacing(14)

        self._model_cards: dict[str, dict] = {}

        for spec in engine_registry.ordered():
            state = model_manager.state_for(spec.key)
            usable, reason = engine_registry.availability(
                spec, cuda=profile.cuda, disk_free_gb=profile.disk_free_gb
            )
            card = SectionCard(spec.label, engine_registry.capabilities_text(spec))
            row = QHBoxLayout()
            row.setSpacing(10)

            info = QVBoxLayout()
            info.setSpacing(3)
            size_label = QLabel(t("İndirme boyutu: {size}", size=state.size_label))
            size_label.setObjectName("modelMeta")
            info.addWidget(size_label)
            note = QLabel(spec.notice or spec.tagline)
            note.setObjectName("modelNote")
            note.setWordWrap(True)
            info.addWidget(note)
            if not usable and reason:
                warn = QLabel(reason)
                warn.setObjectName("modelWarning")
                warn.setWordWrap(True)
                info.addWidget(warn)
            row.addLayout(info, stretch=1)

            status = StatusPill(state.status_text(), "neutral")
            row.addWidget(status)
            row.addSpacing(6)

            progress = QProgressBar()
            progress.setRange(0, 100)
            progress.setValue(0)
            progress.setTextVisible(False)
            progress.setMaximumWidth(140)
            progress.setVisible(False)
            row.addWidget(progress)

            action = ActionButton(t("İndir"), variant="primary", size="small", icon_name="download")
            action.setEnabled(usable and state.download_available and not state.installed)
            action.clicked.connect(lambda _c=False, key=spec.key: self._on_model_install(key))
            row.addWidget(action)

            remove = ActionButton(t("Kaldır"), variant="secondary", size="small", icon_name="delete")
            remove.setEnabled(state.installed and not spec.bundled)
            remove.clicked.connect(lambda _c=False, key=spec.key: self._on_model_remove(key))
            row.addWidget(remove)

            card.content_layout.addLayout(row)
            col.addWidget(card)
            self._model_cards[spec.key] = {
                "status": status,
                "action": action,
                "remove": remove,
                "progress": progress,
                "note": note,
                "card": card,
            }

        # Model klasörü + disk durumu
        folder_card = SectionCard(t("Model klasörü"), t("İndirilen ağırlıklar burada tutulur."))
        folder_row = QHBoxLayout()
        folder_row.setSpacing(10)
        from app import paths as app_paths

        self.model_folder_label = QLabel(str(app_paths.models_dir()))
        self.model_folder_label.setObjectName("modelPath")
        self.model_folder_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        folder_row.addWidget(self.model_folder_label, stretch=1)
        self.btn_model_open = ActionButton(t("Klasörü aç"), variant="secondary", size="small", icon_name="folder")
        self.btn_model_open.clicked.connect(self.on_open_models_folder)
        folder_row.addWidget(self.btn_model_open)
        self.btn_model_refresh = ActionButton("Yenile", variant="ghost", size="small", icon_name="refresh")
        self.btn_model_refresh.clicked.connect(self._refresh_models_page)
        folder_row.addWidget(self.btn_model_refresh)
        folder_card.content_layout.addLayout(folder_row)

        self.model_disk_label = QLabel("")
        self.model_disk_label.setObjectName("modelMeta")
        folder_card.content_layout.addWidget(self.model_disk_label)
        col.addWidget(folder_card)
        col.addStretch(1)

        self._refresh_models_disk_label()
        return self._make_scroll_page(body)

    def _refresh_models_disk_label(self) -> None:
        """Disk kullanımı: pakette gelen + indirilen ağırlıklar."""
        if not hasattr(self, "model_disk_label"):
            return
        from app import engines as engine_registry
        from app import hardware, model_manager

        used = 0
        parts: list[str] = []
        for spec in engine_registry.ordered():
            root = model_manager.weights_dir(spec.key)
            size = _dir_size(root) if root.is_dir() else 0
            if size:
                used += size
                parts.append(f"{spec.label}: {size / 1024 ** 2:.0f} MB")
        free = hardware.free_disk_gb()
        head = t("Kullanılan: {mb} MB", mb=f"{used / 1024 ** 2:.0f}")
        if parts:
            head += "  (" + " · ".join(parts) + ")"
        if free:
            head += t("    Boş alan: {free:g} GB", free=free)
        self.model_disk_label.setText(head)

    def _refresh_models_page(self) -> None:
        """Kart durumlarını yeniden ölç (kurulum sonrası çağrılır)."""
        if not hasattr(self, "_model_cards"):
            return
        from app import engines as engine_registry
        from app import hardware, model_manager

        profile = hardware.detect(force=True)
        for spec in engine_registry.ordered():
            widgets = self._model_cards.get(spec.key)
            if not widgets:
                continue
            state = model_manager.state_for(spec.key)
            usable, reason = engine_registry.availability(
                spec, cuda=profile.cuda, disk_free_gb=profile.disk_free_gb
            )
            widgets["status"].setText(state.status_text())
            widgets["status"].set_tone(
                "success" if state.installed else ("warning" if state.partial else "neutral")
            )
            busy = widgets["progress"].isVisible()
            widgets["action"].setEnabled(
                usable and state.download_available and not state.installed and not busy
            )
            widgets["remove"].setEnabled(state.installed and not spec.bundled and not busy)
            if not usable and reason:
                widgets["note"].setText(reason)
            elif not state.download_available and state.detail:
                widgets["note"].setText(state.detail)
            else:
                widgets["note"].setText(spec.notice or spec.tagline)
        self._refresh_models_disk_label()

    def on_open_models_folder(self) -> None:
        from app import paths as app_paths

        target = app_paths.models_dir()
        try:
            target.mkdir(parents=True, exist_ok=True)
        except OSError:
            self._show_error(t("Klasör açılamadı"), t("{target} oluşturulamadı.", target=target))
            return
        self._open_folder(str(target))

    def _on_model_install(self, engine: str) -> None:
        """İndirmeyi arka planda başlat; ilerlemeyi karta yaz."""
        from app import engines as engine_registry
        from app.workers import ModelInstallWorker

        widgets = self._model_cards.get(engine)
        spec = engine_registry.spec(engine)
        if widgets is None:
            return
        from app import hardware

        profile = hardware.detect()
        usable, reason = engine_registry.availability(
            spec, cuda=profile.cuda, disk_free_gb=profile.disk_free_gb
        )
        if not usable:
            QMessageBox.information(self, t("Bu motor kullanılamaz"), reason)
            return
        if self._model_worker is not None and self._model_worker.isRunning():
            QMessageBox.information(
                self, t("İndirme sürüyor"),
                t("Önce süren indirmenin bitmesini bekleyin."),
            )
            return
        answer = QMessageBox.question(
            self,
            f"{spec.label} indirilsin mi?",
            f"Toplam indirme: {spec.size_label()}\n\n" +
            t("İndirme sırasında programı kullanmaya devam edebilirsiniz. ") +
            t("Durdurursanız kaldığı yerden devam eder."),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        widgets["progress"].setValue(0)
        widgets["progress"].setVisible(True)
        widgets["action"].setEnabled(False)
        widgets["status"].setText(t("İndiriliyor…"))
        widgets["status"].set_tone("info")
        self.btn_model_cancel.setVisible(True)
        self.status_label.setText(t("{label} indiriliyor…", label=spec.label))

        worker = ModelInstallWorker(engine)
        worker.progress.connect(self._on_model_progress)
        worker.message.connect(self._on_model_message)
        worker.ok.connect(self._on_model_installed)
        worker.failed.connect(self._on_model_failed)
        worker.cancelled.connect(self._on_model_cancelled)
        worker.finished.connect(self._on_model_worker_finished)
        self._model_worker = worker
        worker.start()

    def _on_model_progress(self, done: int, total: int, speed: float, remaining: float) -> None:
        if not hasattr(self, "_model_cards"):
            return
        for widgets in self._model_cards.values():
            if widgets["progress"].isVisible():
                if total > 0:
                    widgets["progress"].setRange(0, 100)
                    widgets["progress"].setValue(int(done * 100 / total))
                else:
                    widgets["progress"].setRange(0, 0)  # belirsiz
                widgets["status"].setText(f"%{done * 100 / total:.0f}" if total else t("İndiriliyor…"))
                break
        if total > 0:
            text = t("İndiriliyor: {done} / {total}", done=format_bytes(done), total=format_bytes(total))
            if speed > 0:
                text += f" · {format_bytes(int(speed))}/sn"
            if remaining:
                text += f" · kalan ~{int(remaining // 60)}:{int(remaining % 60):02d}"
            self.status_label.setText(text)

    def _on_model_message(self, text: str) -> None:
        self.status_label.setText(text)

    def _on_model_installed(self, engine: str, detail: str) -> None:
        self.btn_model_cancel.setVisible(False)
        widgets = self._model_cards.get(engine, {})
        if widgets:
            widgets["progress"].setVisible(False)
            widgets["progress"].setRange(0, 100)
        self._refresh_models_page()
        from app import engines as engine_registry

        self.status_label.setText(t("{label} kuruldu.", label=engine_registry.spec(engine).label))

    def _on_model_failed(self, engine: str, message: str) -> None:
        self.btn_model_cancel.setVisible(False)
        widgets = self._model_cards.get(engine, {})
        if widgets:
            widgets["progress"].setVisible(False)
        self._refresh_models_page()
        self.status_label.setText(t("İndirme tamamlanamadı."))
        self._show_error(t("İndirme hatası"), message)

    def _on_model_cancelled(self, engine: str) -> None:
        self.btn_model_cancel.setVisible(False)
        widgets = self._model_cards.get(engine, {})
        if widgets:
            widgets["progress"].setVisible(False)
        self._refresh_models_page()
        self.status_label.setText(t("İndirme durduruldu; kaldığı yerden devam eder."))

    def _on_model_worker_finished(self) -> None:
        # Sonuç sinyali run() dönmeden gelir. QThread'i ancak finished sonrası
        # bırak; aksi halde pencere kapanırken çalışan iş parçacığı yok edilir.
        worker = self.sender()
        if self._model_worker is worker:
            self._model_worker = None
        if worker is not None:
            worker.deleteLater()
        self._on_background_worker_finished()

    def on_cancel_model_install(self) -> None:
        if self._model_worker is not None and self._model_worker.isRunning():
            self._model_worker.request_cancel()
            self.status_label.setText(t("İndirme durduruluyor…"))

    def _on_model_remove(self, engine: str) -> None:
        from app import engines as engine_registry
        from app import model_manager

        spec = engine_registry.spec(engine)
        answer = QMessageBox.question(
            self,
            t("{label} kaldırılsın mı?", label=spec.label),
            t("Motor dosyaları ve indirilen model ağırlıkları silinecek.\n\n") +
            t("Ürettiğiniz sesler ve ayarlarınız korunur. Yeniden kullanmak ") +
            "isterseniz tekrar indirmeniz gerekir.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            model_manager.remove_engine(engine)
        except Exception as exc:
            self._show_error(t("Kaldırılamadı"), str(exc))
            return
        # Aktif motor kaldırıldıysa güvenli olana dön.
        if self._engine_name == engine:
            self._engine_name = engine_registry.DEFAULT_ENGINE
            if hasattr(self, "engine_combo"):
                index = self.engine_combo.findData(engine_registry.DEFAULT_ENGINE)
                if index >= 0:
                    self.engine_combo.blockSignals(True)
                    self.engine_combo.setCurrentIndex(index)
                    self.engine_combo.blockSignals(False)
            self._apply_engine_ui_state(self._engine_name)
            self._init_engine_async()
        self._refresh_models_page()
        self.status_label.setText(t("{label} kaldırıldı.", label=spec.label))

    def _switch_tool(self, index: int):
        if 0 <= index < self._tool_stack.count():
            self._tool_stack.setCurrentIndex(index)
            for i, button in enumerate(self._tool_buttons):
                button.setChecked(i == index)

    def _connect_ui_signals(self) -> None:
        self.btn_paste.clicked.connect(self.on_paste)
        self.btn_clean_text.clicked.connect(self.on_clean_text)
        self.text_edit.textChanged.connect(self.update_text_info)
        self.language_combo.currentIndexChanged.connect(self.update_settings_summary)
        self.language_combo.currentIndexChanged.connect(self._on_language_changed)
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

        self.btn_compress_add.clicked.connect(self.on_compress_add_files)
        self.btn_compress_clear.clicked.connect(self.on_compress_clear)
        self.btn_compress_start.clicked.connect(self.on_compress_start)

    def _switch_page(self, index: int, *, animate: bool = True):
        """Show a workspace page and synchronize the sidebar selection."""
        if index < 0 or index >= self.pages.count():
            return
        previous_index = self.pages.currentIndex()
        self.pages.setCurrentIndex(index)
        self._page_action_stack.setCurrentIndex(index)
        title, subtitle = self._page_meta[index]
        self.page_header.set_text(title, subtitle)
        for button_index, button in enumerate(self._nav_buttons):
            button.setChecked(button_index == index)

        if not animate or previous_index == index:
            return
        if self._page_transition is not None:
            self._page_transition.stop()
            previous_page = getattr(self, "_transition_page", None)
            if previous_page is not None:
                previous_page.setGraphicsEffect(None)

        page = self.pages.currentWidget()
        effect = QGraphicsOpacityEffect(page)
        page.setGraphicsEffect(effect)
        animation = QPropertyAnimation(effect, b"opacity", self)
        animation.setStartValue(0.68)
        animation.setEndValue(1.0)
        animation.setDuration(150)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._page_transition = animation
        self._transition_page = page

        def finish_transition():
            page.setGraphicsEffect(None)
            if self._page_transition is animation:
                self._page_transition = None

        animation.finished.connect(finish_transition)
        animation.start()

    def _refresh_widget_style(self, widget: QWidget):
        widget.style().unpolish(widget)
        widget.style().polish(widget)
        widget.update()

    def _refresh_theme_icons(self):
        """Refresh logo and semantic icons after a palette transition."""
        if hasattr(self, "brand_logo"):
            self.brand_logo.setPixmap(application_icon().pixmap(34, 34))
        for button in self.findChildren(ActionButton):
            button.refresh_icon()
        if hasattr(self, "_nav_buttons"):
            for button, icon_name in zip(self._nav_buttons, self._nav_icon_names):
                button.setIcon(navigation_icon(icon_name))
        self._refresh_compress_result_colors()

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
        self.btn_generate.setToolTip(t("Metni ses sentezine gönder (Ctrl+Enter)"))
        self.btn_save_wav.setToolTip(t("Son üretimi WAV olarak kaydet (Ctrl+S)"))
        self.btn_save_mp3.setToolTip(t("Son üretimi MP3 olarak kaydet (Ctrl+Shift+S)"))
        self.btn_select_voice.setToolTip(t("Referans ses örneği dosyası seç (Ctrl+Shift+V)"))

    # ---- motor seçimi -----------------------------------------------------

    def _populate_engine_combo(self):
        """Motor kutusunu kayıttan doldur; donanıma uymayan öğeyi kilitle.

        Kullanıcı VoxCPM2'yi CUDA'sız bir makinede göremez demek yanlış olur:
        görmeli ki "neden yok" sorusu doğmasın. Bu yüzden liste tamdır ama
        uygun olmayan öğe gri ve seçilemez; gerekçe tooltip'te yazar.
        """
        from app import hardware

        profile = hardware.detect()
        combo = self.engine_combo
        combo.clear()
        for spec in engine_registry.ordered():
            ok, reason = engine_registry.availability(
                spec, cuda=profile.cuda, disk_free_gb=profile.disk_free_gb
            )
            label = spec.label
            if not spec.bundled:
                label += f" — {spec.size_label()}"
            combo.addItem(label, spec.key)
            index = combo.count() - 1
            notes = [spec.tagline]
            if spec.notice:
                notes.append(spec.notice)
            if reason:
                notes.append(reason)
            combo.setItemData(index, "\n".join(notes), Qt.ItemDataRole.ToolTipRole)
            if not ok:
                item = combo.model().item(index)
                if item is not None:
                    item.setEnabled(False)
        combo.setToolTip(
            t("Motor değişince model arka planda yeniden yüklenir.\n") +
            t("Gri öğeler bu bilgisayarda çalışamaz; nedeni üzerine gelince görünür.")
        )

    def _on_engine_changed(self, _index: int = 0):
        """Ayarlar'daki motor değişti: arayüzü uygula ve motoru yeniden yükle."""
        if not hasattr(self, "engine_combo"):
            return
        name = self.engine_combo.currentData()
        if name not in engine_registry.keys() or name == self._engine_name:
            return
        spec = engine_registry.spec(name)
        from app import hardware

        profile = hardware.detect()
        ok, reason = engine_registry.availability(
            spec, cuda=profile.cuda, disk_free_gb=profile.disk_free_gb
        )
        if not ok:
            QMessageBox.information(self, t("Bu motor kullanılamaz"), reason)
            self._revert_engine_combo()
            return
        if self._synth_worker and self._synth_worker.isRunning():
            QMessageBox.information(
                self,
                t("Üretim sürüyor"),
                t("Motor değiştirmek için süren üretimin bitmesini bekleyin."),
            )
            self._revert_engine_combo()
            return
        if spec.single_language:
            # Tek dilli motor: çıkarken dili geri yüklemek için sakla.
            self._chatterbox_language_id = self.language_combo.currentData() or "tr"
        self._engine_name = name
        self._apply_engine_ui_state(name)
        self._save_current_settings()
        self.status_label.setText(t("Ses motoru değiştiriliyor..."))
        self._init_engine_async()

    def _revert_engine_combo(self):
        """Seçiciyi geçerli motora geri al (sinyal tetiklemeden)."""
        index = self.engine_combo.findData(self._engine_name)
        if index >= 0:
            self.engine_combo.blockSignals(True)
            self.engine_combo.setCurrentIndex(index)
            self.engine_combo.blockSignals(False)

    def _on_language_changed(self, _index: int = 0):
        """Dil tercihini izle (tek dilli motorda dil kilitlidir)."""
        if not engine_registry.spec(self._engine_name).single_language:
            self._chatterbox_language_id = self.language_combo.currentData() or "tr"

    def _chatterbox_only_widgets(self) -> tuple:
        """Yalnız çok dilli/klonlayan motorlarda anlamlı ayar widget'ları."""
        return (
            self.preset_combo,
            self.btn_apply_preset,
            self.exaggeration_spin,
            self.cfg_spin,
            self.temperature_spin,
            self.repetition_spin,
        )

    def _apply_engine_ui_state(self, engine_name: str):
        """Seçili motora göre arayüzü ayarla.

        Tek dilli motor (EMA): dil kilitlenir, referans ses düğmeleri ve
        örnekleme parametreleri kapanır; hız ve duraklama geçerli kalır.
        Çok dilli motor: dil açılır, ses profili kullanılabilir.
        """
        spec = engine_registry.spec(engine_name)
        self._engine_name = spec.key
        simple = spec.single_language

        preferred = spec.languages[0] if simple else self._chatterbox_language_id
        index = self.language_combo.findData(preferred)
        if index >= 0 and self.language_combo.currentIndex() != index:
            self.language_combo.blockSignals(True)
            self.language_combo.setCurrentIndex(index)
            self.language_combo.blockSignals(False)
        self._update_language_tooltip()
        self.language_combo.setEnabled(not simple)

        for widget in self._chatterbox_only_widgets():
            widget.setEnabled(not simple)

        if hasattr(self, "voice_design_card"):
            self.voice_design_card.setVisible(bool(spec.voice_design))
        if hasattr(self, "voice_card"):
            if not spec.cloning:
                self.voice_card.set_text(
                    "Ses Profili",
                    t("{label} sabit bir sesle okur; referans ses kullanılmaz.", label=spec.label),
                )
                self.voice_label.setText(t("{label} — sabit ses (referans gerekmez)", label=spec.label))
            else:
                self.voice_card.set_text(
                    "Ses Profili", t("Referans ses yoksa varsayılan ses kullanılır.")
                )
                if self.voice_prompt_path:
                    self._set_voice_prompt(self.voice_prompt_path, save=False)
                else:
                    self.voice_label.setText(t("Ses örneği seçilmedi"))

        has_voice = bool(self.voice_prompt_path)
        self.btn_select_voice.setEnabled(spec.cloning)
        self.btn_sample_voice_text.setEnabled(spec.cloning)
        self.btn_play_voice.setEnabled(spec.cloning and has_voice)
        self.btn_clear_voice.setEnabled(spec.cloning and has_voice)
        self.update_settings_summary()

    def _needs_voice_warning(self) -> bool:
        """Referans ses uyarısı yalnız klonlayan motorda ve ses örneği yokken."""
        return (
            engine_registry.spec(self._engine_name).cloning
            and not self.voice_prompt_path
            and not self._voice_warning_dismissed
        )

    def _refresh_engine_combo_enabled(self, busy: bool | None = None):
        """Motor seçici yalnız boştayken ve yükleme bitince kullanılabilir."""
        if not hasattr(self, "engine_combo"):
            return
        if busy is None:
            busy = bool(self._synth_worker and self._synth_worker.isRunning())
        self.engine_combo.setEnabled(not busy and not self._engine_loading)

    # ---- motor yaşam döngüsü ---------------------------------------------

    def _init_engine_async(self):
        """Model yükleme uzun sürebilir; ayrı thread."""
        self._engine_loading = True
        self._refresh_engine_combo_enabled(busy=False)
        self._model_dialog = ModelLoadDialog(self)
        spec = engine_registry.spec(self._engine_name)
        self._model_dialog.add_status(t("Uygulama açıldı. {label} hazırlanıyor.", label=spec.label))
        self._model_dialog.show()

        self._loader = EngineLoader(engine_name=self._engine_name)
        self._loader.status.connect(self._on_engine_status)
        self._loader.ok.connect(self._on_engine_ready)
        self._loader.fail.connect(self._on_engine_failed)
        self._loader.start()
        self._loader.finished.connect(self._on_background_worker_finished)

    def _on_engine_status(self, message: str):
        self.status_label.setText(message)
        self.engine_status_pill.setText("HAZIRLANIYOR")
        self.engine_status_pill.set_tone("info")
        if hasattr(self, "_model_dialog") and self._model_dialog:
            self._model_dialog.add_status(message)

    def _on_engine_ready(self, engine):
        self.engine = engine
        self._engine_loading = False
        self._engine_name = getattr(engine, "engine_name", self._engine_name)
        self._apply_engine_ui_state(self._engine_name)
        self._refresh_engine_combo_enabled(busy=False)
        display = getattr(engine, "display_name", type(engine.engine).__name__)
        message = t("Hazır - {display} ({device})", display=display, device=engine.device_name)
        self.status_label.setText(message)
        self.engine_status_pill.setText("HAZIR")
        self.engine_status_pill.set_tone("success")
        self._reset_progress()
        self._set_engine_actions_enabled(True)
        self._refresh_system_labels()
        if hasattr(self, "_model_dialog") and self._model_dialog:
            self._model_dialog.finish_ok(message)

    def _on_engine_failed(self, msg: str):
        message = t("Motor yüklenemedi:\n{msg}", msg=msg)
        self._engine_loading = False
        self._refresh_engine_combo_enabled(busy=False)
        self.status_label.setText(t("Motor yüklenemedi."))
        self.engine_status_pill.setText("HATA")
        self.engine_status_pill.set_tone("danger")
        self._reset_progress()
        self._set_engine_actions_enabled(False)
        self._refresh_system_labels()
        if hasattr(self, "_model_dialog") and self._model_dialog:
            self._model_dialog.finish_error(message)
        self._show_error("Hata", message)

    def _friendly_error(self, msg: str) -> str:
        lower = msg.lower()
        if "cuda" in lower or "gpu" in lower:
            if engine_registry.spec(self._engine_name).requires_cuda:
                return t("Bu motor NVIDIA / CUDA gerektirir. CPU ile çalıştırılamaz.")
            return t("GPU kullanılamadı veya CUDA tarafında sorun oluştu. CPU ile tekrar denenebilir.")
        if "audio_prompt" in lower or "librosa" in lower or "soundfile" in lower:
            return t("Ses örneği okunamadı. Daha kısa, temiz bir WAV/MP3 dosyası deneyebilirsin.")
        if "memory" in lower or "out of memory" in lower:
            return t("Bellek yetersiz kaldı. Metni kısaltmayı veya daha az parçayla denemeyi deneyebilirsin.")
        if "unsupported language" in lower:
            return t("Seçilen dil model tarafından desteklenmedi. Ayarlar sekmesinden başka bir dil seç.")
        if "connection" in lower or "max retries" in lower or "timed out" in lower or "offline" in lower:
            return t("İnternet bağlantısı kurulamadı. Model ilk kez indirilecekse bağlantı gerekir; sonraki çalıştırmalar çevrimdışı olabilir.")
        if "model" in lower or "pretrained" in lower or "snapshot" in lower:
            return t("Model yüklenemedi. İnternet bağlantısı, kurulum veya model dosyaları kontrol edilmeli.")
        return t("İşlem tamamlanamadı. Ayrıntı aşağıda.")

    def _show_error(self, title: str, msg: str):
        friendly = self._friendly_error(str(msg))
        QMessageBox.critical(self, title, t("{friendly}\n\nAyrıntı:\n{msg}", friendly=friendly, msg=msg))

    def closeEvent(self, event):
        # Ortak tercih: t("Kapatılınca tepsiye küçült"). Tepsi simgesi yoksa
        # küçültme uygulanamaz (kullanıcı uygulamayı kaybeder) → kapanır.
        if not self._close_finalized and self._should_minimize_to_tray():
            self._save_before_close()
            event.ignore()
            self.hide()
            return
        if self._close_finalized:
            self._save_before_close()
            audio_player.stop()
            event.accept()
            return
        workers = [self._loader, self._synth_worker, self._compress_worker, self._model_worker]
        running = any(worker and worker.isRunning() for worker in workers)
        if self._update_worker is not None and self._update_worker.isRunning() \
                and not self._close_requested:
            # İndirme/yazım ortada yarım kalmasın; kullanıcı kapatıyorsa vazgeç.
            self._update_worker.request_cancel()
            self._update_worker.wait(5000)
        if running and not self._close_requested:
            reply = QMessageBox.question(
                self,
                t("İşlemler devam ediyor"),
                t("Arka plan işlemleri güvenli şekilde durdurulduktan sonra program kapatılacak. Devam edilsin mi?"),
            )
            if reply != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self._close_requested = True
            self._queue_running = False
            if self._synth_worker and self._synth_worker.isRunning():
                self._synth_cancel_requested = True
                self._synth_worker.request_cancel()
            if self._compress_worker and self._compress_worker.isRunning():
                self._compress_worker.request_cancel()
            if self._model_worker and self._model_worker.isRunning():
                self._model_worker.request_cancel()
            self.status_label.setText(t("Çalışan işlem tamamlanınca program kapatılacak..."))
            event.ignore()
            return
        if running:
            event.ignore()
            return
        self._close_finalized = True
        self._save_before_close()
        audio_player.stop()
        event.accept()

    def _save_before_close(self):
        if self._settings_saved_on_close:
            return
        settings = self._current_ui_settings()
        settings["production_count"] = self.production_count
        save_settings(settings)
        save_history(self.history)
        self._settings_saved_on_close = True

    def _on_background_worker_finished(self):
        if self._close_requested:
            workers = [self._loader, self._synth_worker, self._compress_worker, self._model_worker]
            if not any(worker and worker.isRunning() for worker in workers):
                self._close_finalized = True
                self.close()

    def on_paste(self):
        text = QApplication.clipboard().text().strip()
        if not text:
            QMessageBox.information(self, t("Pano boş"), t("Panoda yapıştırılacak metin bulunamadı."))
            return
        self.text_edit.setPlainText(text)
        self.status_label.setText(t("Panodaki metin üretim alanına yapıştırıldı."))
        self.update_text_info()

    def on_clean_text(self):
        original = self.text_edit.toPlainText()
        cleaned = self._clean_text(original)
        self.text_edit.setPlainText(cleaned)
        self.status_label.setText(t("Metin temizlendi."))

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
            t("{chars} karakter • {words} kelime • {parts} parça • ~{duration}", chars=chars, words=words, parts=parts, duration=duration)
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
        speed = self.speed_spin.value()
        pause = self.pause_spin.value()
        spec = engine_registry.spec(self._engine_name)
        if spec.single_language:
            self.settings_summary_label.setText(
                f"{spec.label} • {language} • {speed:.2f}x • " +
                f"Duraklama {pause:.2f} sn • Tek ses"
            )
            return
        preset = self.preset_combo.currentText()
        if spec.cloning:
            voice = t("Ses örneği var") if self.voice_prompt_path else t("Varsayılan ses")
        else:
            voice = t("Ses tasarımı")
        self.settings_summary_label.setText(
            f"{spec.label} • {language} • {preset} • {speed:.2f}x • " +
            f"Duraklama {pause:.2f} sn • {voice}"
        )

    def _load_saved_settings(self):
        settings = self.settings or {}
        # Ortak masaüstü seçenekleri: kutular kayıtlı durumu gösterir.
        controller = getattr(self, "_autostart_controller", None)
        if controller is not None:
            self._autostart_cb.setChecked(controller.is_enabled())
        tray_option = getattr(self, "_tray_option", None)
        if tray_option is not None:
            self._tray_cb.setChecked(tray_option.is_enabled())
        preset = settings.get("preset", t("Anlatıcı"))
        preset_index = self.preset_combo.findText(preset)
        if preset_index >= 0:
            self.preset_combo.setCurrentIndex(preset_index)
        language = settings.get("language_id", "tr")
        index = self.language_combo.findData(language)
        if index >= 0:
            self.language_combo.setCurrentIndex(index)
        self.speed_spin.setValue(_saved_float(settings, "speed", self.speed_spin.value()))
        self.exaggeration_spin.setValue(
            _saved_float(settings, "exaggeration", self.exaggeration_spin.value()))
        self.cfg_spin.setValue(_saved_float(settings, "cfg_weight", self.cfg_spin.value()))
        self.temperature_spin.setValue(
            _saved_float(settings, "temperature", self.temperature_spin.value()))
        self.repetition_spin.setValue(
            _saved_float(settings, "repetition_penalty", self.repetition_spin.value()))
        self.pause_spin.setValue(
            _saved_float(settings, "pause_between_chunks", self.pause_spin.value()))
        fmt = str(settings.get("output_format") or DEFAULT_OUTPUT_FORMAT)
        self._output_format = fmt if fmt in VALID_OUTPUT_FORMATS else DEFAULT_OUTPUT_FORMAT
        self._quality_by_format = {
            OUTPUT_FORMAT_WAV: "",
            OUTPUT_FORMAT_MP3: str(settings.get("mp3_bitrate") or DEFAULT_MP3_BITRATE),
            OUTPUT_FORMAT_OPUS: str(settings.get("opus_bitrate") or DEFAULT_OPUS_BITRATE),
        }
        self._refresh_format_tiles()
        self._refresh_quality_options()
        theme = settings.get("theme", "dark")
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

        # Sıkıştırma ayarları
        self.compress_output_dir = settings.get("compress_output_dir") or None
        if self.compress_output_dir and hasattr(self, "compress_output_label"):
            self.compress_output_label.setText(self.compress_output_dir)
            self.compress_output_label.setProperty("muted", False)
            self._refresh_widget_style(self.compress_output_label)
        cb = settings.get("compress_bitrate")
        if cb and hasattr(self, "compress_bitrate_combo"):
            idx = self.compress_bitrate_combo.findData(cb)
            if idx >= 0:
                self.compress_bitrate_combo.setCurrentIndex(idx)

        # Ses motoru (ema | chatterbox | voxcpm2) ve çok dilli motorun dil tercihi
        engine = str(settings.get("engine", engine_registry.DEFAULT_ENGINE))
        if engine not in engine_registry.keys():
            engine = engine_registry.DEFAULT_ENGINE
        else:
            # Kayıtlı motor artık bu donanımda çalışamıyorsa (ör. VoxCPM2
            # CUDA'sız makinede) varsayılana düş: açılışta hata ile karşılaşma.
            from app import hardware

            profile = hardware.detect()
            ok, _reason = engine_registry.availability(
                engine_registry.spec(engine),
                cuda=profile.cuda,
                disk_free_gb=profile.disk_free_gb,
            )
            if not ok:
                engine = engine_registry.DEFAULT_ENGINE
        self._chatterbox_language_id = str(
            settings.get("chatterbox_language_id") or settings.get("language_id", "tr")
        )
        if hasattr(self, "engine_combo"):
            engine_index = self.engine_combo.findData(engine)
            if engine_index >= 0:
                self.engine_combo.blockSignals(True)
                self.engine_combo.setCurrentIndex(engine_index)
                self.engine_combo.blockSignals(False)
        self._apply_engine_ui_state(engine)

        self.update_settings_summary()

    def _save_current_settings(self):
        if not hasattr(self, "language_combo"):
            return
        save_settings(self._current_ui_settings())

    def _set_option(self, key: str, value) -> None:
        """Tek bir ayarı kaydet (ortak masaüstü seçenekleri için)."""
        settings = dict(self.settings)
        settings[key] = value
        save_settings(settings)
        self.settings = settings

    def _maybe_show_first_run(self) -> None:
        """İlk açılış sihirbazını göster (yalnız bir kez, motor yoksa).

        ``exec()`` DEĞİL ``show()``: modal çağrı ana olay döngüsünü iç içe
        çalıştırır ve sihirbaz açıkken programın geri kalanı kilitlenir. Model
        yükleme ve güncelleme denetimi arka planda sürmeli. Sihirbaz modal
        değildir; kullanıcı ana pencereyi kullanmaya devam edebilir.
        """
        from app import first_run

        try:
            if not first_run.should_show():
                return
            dialog = first_run.FirstRunDialog(self)
            dialog.setModal(False)
            dialog.selected.connect(self._on_first_run_selected)
            dialog.finished.connect(dialog.deleteLater)
            dialog.show()
            dialog.raise_()
            dialog.activateWindow()
            self._first_run_dialog = dialog
        except Exception:
            # Sihirbaz açılamazsa program yine çalışsın; Modeller sekmesi var.
            log.exception("İlk açılış sihirbazı açılamadı")

    def _on_first_run_selected(self, engine: str) -> None:
        """Sihirbazda motor seçildi: kurulu değilse indir, sonra etkinleştir."""
        from app import engines as engine_registry
        from app import model_manager

        if not engine:
            self.status_label.setText(
                t("Motor seçilmedi. Modeller sekmesinden indirebilirsiniz.")
            )
            return
        spec = engine_registry.spec(engine)
        state = model_manager.state_for(spec.key)
        index = self.engine_combo.findData(spec.key)
        if index >= 0:
            self.engine_combo.blockSignals(True)
            self.engine_combo.setCurrentIndex(index)
            self.engine_combo.blockSignals(False)
        if state.installed:
            self._engine_name = spec.key
            self._apply_engine_ui_state(spec.key)
            self._save_current_settings()
            self._init_engine_async()
            return
        # İndirme Modeller sekmesinde ilerler; kullanıcı oraya yönlendirilir.
        self._switch_page(3, animate=False)
        self._on_model_install(spec.key)

    def _build_tray(self):
        """Sistem tepsisi simgesi: göster / ayarlar / çık.

        "Kapatılınca tepsiye küçült" tercihi bu simgeye bağlıdır; simge
        olmadan küçültme uygulanamaz.
        """
        from PyQt6.QtGui import QAction
        from PyQt6.QtWidgets import QMenu, QSystemTrayIcon

        if getattr(self, "_tray_icon", None) is not None:
            return self._tray_icon

        tray = QSystemTrayIcon(application_icon(), self)
        menu = QMenu()
        show_action = QAction(t("Voxora Studio'yu göster"), self)
        show_action.triggered.connect(self._restore_from_tray)
        settings_action = QAction("Ayarlar", self)
        settings_action.triggered.connect(self._open_settings)
        quit_action = QAction(t("Çıkış"), self)
        quit_action.triggered.connect(self._quit_from_tray)
        menu.addAction(show_action)
        menu.addAction(settings_action)
        menu.addSeparator()
        menu.addAction(quit_action)
        tray.setContextMenu(menu)
        tray.activated.connect(self._on_tray_activated)
        tray.show()
        self._tray_icon = tray
        return tray

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._restore_from_tray()

    def _restore_from_tray(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _open_settings(self):
        self._restore_from_tray()
        labels = getattr(self, "_nav_labels", [])
        if "Ayarlar" in labels:
            self._switch_page(labels.index("Ayarlar"))

    def _quit_from_tray(self):
        self._close_finalized = True
        self._save_before_close()
        audio_player.stop()
        if getattr(self, "_tray_icon", None) is not None:
            self._tray_icon.hide()
        QApplication.quit()

    def _should_minimize_to_tray(self) -> bool:
        """Kapatma olayında pencereyi gizlemeli miyiz?

        Tepsi simgesi yoksa küçültme uygulanamaz: kullanıcı uygulamayı
        kaybeder ve geri getiremez.
        """
        tray = getattr(self, "_tray_icon", None)
        tray_available = tray is not None and tray.isVisible()
        option = getattr(self, "_tray_option", None)
        if option is None:
            return False
        return option.should_minimize(tray_available=tray_available)

    def _current_ui_settings(self) -> dict:
        return {
            "engine": self.engine_combo.currentData() if hasattr(self, "engine_combo") else DEFAULT_ENGINE,
            "chatterbox_language_id": self._chatterbox_language_id,
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
            "output_format": getattr(self, "_output_format", DEFAULT_OUTPUT_FORMAT),
            "mp3_bitrate": (getattr(self, "_quality_by_format", None) or {}).get(OUTPUT_FORMAT_MP3, DEFAULT_MP3_BITRATE),
            "opus_bitrate": (getattr(self, "_quality_by_format", None) or {}).get(OUTPUT_FORMAT_OPUS, DEFAULT_OPUS_BITRATE),
            "theme": self.theme_combo.currentData() if hasattr(self, "theme_combo") else "dark",
            "output_dir": self.output_dir,
            "compress_output_dir": self.compress_output_dir if hasattr(self, "compress_output_dir") else None,
            "compress_bitrate": self.compress_bitrate_combo.currentData() if hasattr(self, "compress_bitrate_combo") else "48k",
            "update_last_check": self._update_last_check,
        }

    def _apply_voice_design(self, text: str) -> str:
        """Ses tasarımı tarifini metnin başına parantez içinde ekle.

        Yalnız ses tasarımı destekleyen motorlarda ve tarif doluysa uygulanır.
        Kullanıcı metne zaten parantezle başladıysa dokunulmaz.
        """
        if not hasattr(self, "voice_design_edit"):
            return text
        if not engine_registry.spec(self._engine_name).voice_design:
            return text
        description = self.voice_design_edit.text().strip()
        if not description or text.lstrip().startswith("("):
            return text
        return f"({description}){text}"

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
        self.status_label.setText(t("Hazır ayar seçildi: {name}", name=self.preset_combo.currentText()))
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
            self.status_label.setText(t("Kayıt klasörü seçildi: {d}", d=self.output_dir))

    def on_select_output_dir(self):
        directory = QFileDialog.getExistingDirectory(self, t("Varsayılan kayıt klasörünü seç"), self.output_dir)
        if not directory:
            return
        self._set_output_dir(directory)

    def on_reset_output_dir(self):
        self._set_output_dir(self._default_output_dir())

    def on_open_output_dir(self):
        os.makedirs(self.output_dir, exist_ok=True)
        self._open_folder(self.output_dir)

    # --- Çıktı biçimi ve kalite (Ayarlar → Çıktı) -------------------------
    def _refresh_format_tiles(self):
        """Kutucukların seçim durumunu güncel biçime göre tazele."""
        for key, tile in getattr(self, "format_tiles", {}).items():
            tile.set_selected(key == self._output_format)

    def _refresh_quality_options(self):
        """Kalite listesini seçili biçime göre yeniden kur."""
        combo = getattr(self, "quality_combo", None)
        if combo is None:
            return
        options = quality_options_for(self._output_format)
        values = {value for value, _label in options}
        defaults = {
            OUTPUT_FORMAT_MP3: DEFAULT_MP3_BITRATE,
            OUTPUT_FORMAT_OPUS: DEFAULT_OPUS_BITRATE,
        }
        current = self._quality_by_format.get(self._output_format) or defaults.get(self._output_format, "")
        if current not in values:
            current = defaults.get(self._output_format, "")
        if current not in values:
            current = options[0][0]
        combo.blockSignals(True)
        combo.clear()
        for value, label in options:
            combo.addItem(label, value)
        index = combo.findData(current)
        combo.setCurrentIndex(index if index >= 0 else 0)
        combo.setEnabled(self._output_format != OUTPUT_FORMAT_WAV)
        combo.blockSignals(False)
        self._quality_by_format[self._output_format] = combo.currentData() or ""

    def _on_output_format_selected(self, fmt: str):
        if fmt not in VALID_OUTPUT_FORMATS or fmt == self._output_format:
            return
        self._output_format = fmt
        self._refresh_format_tiles()
        self._refresh_quality_options()
        self._save_current_settings()
        detail = t("kayıpsız") if fmt == OUTPUT_FORMAT_WAV else self.quality_combo.currentText()
        self.status_label.setText(t("Çıktı biçimi: {fmt} — {detail}", fmt=format_label(fmt), detail=detail))

    def _on_output_quality_changed(self, _index: int):
        combo = getattr(self, "quality_combo", None)
        if combo is None:
            return
        self._quality_by_format[self._output_format] = combo.currentData() or ""
        self._save_current_settings()

    def _make_output_path(self, extension: str) -> str:
        os.makedirs(self.output_dir, exist_ok=True)
        return str(unique_path(self.output_dir, safe_filename_from_text(self.last_text or self.text_edit.toPlainText(), extension)))

    def _open_folder(self, folder_path: str):
        if not folder_path:
            return
        if not os.path.isdir(folder_path):
            QMessageBox.warning(self, t("Klasör bulunamadı"), t("Bu klasör bulunamadı:\n{folder_path}", folder_path=folder_path))
            return
        try:
            os.startfile(folder_path)
        except Exception as e:
            QMessageBox.warning(self, t("Klasör açılamadı"), t("Klasör açılamadı.\n\nAyrıntı:\n{e}", e=e))

    def _show_file_in_folder(self, file_path: str):
        if not file_path:
            QMessageBox.information(self, t("Kayıt yolu yok"), t("Bu geçmiş kaydında açılacak dosya yolu bulunamadı."))
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
                self.status_label.setText(t("Ses dosyası bulunamadı; kayıt klasörü açıldı."))
            return
        QMessageBox.warning(self, t("Dosya bulunamadı"), t("Bu geçmiş kaydının ses dosyası artık bulunamıyor."))

    def _refresh_system_labels(self):
        if not hasattr(self, "device_label"):
            return
        if self.engine:
            self.device_label.setText(
                t("Cihaz: {dev} • Motor: {eng}", dev=self.engine.device_name, eng=self.engine.display_name)
            )
        else:
            self.device_label.setText(t("Cihaz: hazırlanıyor"))
        from app import hardware

        profile = hardware.detect()
        self.gpu_label.setText(t("GPU: {label}", label=profile.gpu_label))
        if not profile.cuda:
            self.gpu_label.setText(t("GPU: {label} • Ses üretimi: CPU (CUDA yok)", label=profile.gpu_label))

    def on_show_system_info(self):
        from app import engines as engine_registry
        from app import hardware

        profile = hardware.detect(force=True)
        ffmpeg = "Var" if self._has_ffmpeg() else "Yok"
        engine = (
            f"{self.engine.display_name} • {type(self.engine.engine).__name__} " +
            f"({self.engine.device_name})"
            if self.engine
            else t("Hazırlanıyor")
        )
        lines = [
            f"Motor: {engine}",
            f"GPU: {profile.gpu_label}",
            t("CUDA: {durum}", durum=t("hazır") if profile.cuda else t("yok")),
        ]
        if profile.vram_gb:
            lines.append(f"VRAM: {profile.vram_gb:g} GB")
        if profile.ram_gb:
            lines.append(f"RAM: {profile.ram_gb:g} GB")
        if profile.cpu_threads:
            lines.append(t("İşlemci: {threads} iş parçacığı", threads=profile.cpu_threads))
        if profile.disk_free_gb:
            lines.append(t("Boş disk: {gb} GB", gb=f"{profile.disk_free_gb:g}"))
        lines.append(f"ffmpeg: {ffmpeg}")
        lines.append("")
        lines.append("Motorlar:")
        for spec in engine_registry.ordered():
            ok, reason = engine_registry.availability(
                spec, cuda=profile.cuda, disk_free_gb=profile.disk_free_gb
            )
            if spec.bundled:
                state = "kurulu (paketle gelir)"
            elif ok:
                state = f"indirilebilir — {spec.size_label()}"
            else:
                state = t("kullanılamaz")
            lines.append(f"  • {spec.label}: {state}")
            if not ok and reason:
                lines.append(f"    {reason}")
        QMessageBox.information(self, "Sistem Bilgisi", "\n".join(lines))

    def _has_ffmpeg(self) -> bool:
        from shutil import which

        if which("ffmpeg"):
            return True
        try:
            from audio_player import _bundled_bin
            return _bundled_bin("ffmpeg.exe") is not None
        except Exception:
            return False

    def _describe_audio_file(self, path: str) -> tuple[str, float | None]:
        try:
            info = sf.info(path)
            duration = float(info.duration)
        except Exception:
            try:
                from pydub import AudioSegment

                duration = len(AudioSegment.from_file(path)) / 1000.0
            except Exception:
                return t("Ses süresi okunamadı."), None

        if duration < 3:
            note = t("Çok kısa; 5-20 saniye temiz konuşma daha iyi sonuç verir.")
        elif duration > 30:
            note = t("Uzun; 5-20 saniyelik temiz konuşma önerilir.")
        elif 5 <= duration <= 20:
            note = t("İdeal aralıkta.")
        else:
            note = t("Kullanılabilir; 5-20 saniye aralığı en iyi sonuç verir.")
        return f"{duration:.1f} sn - {note}", duration

    def _set_voice_prompt(self, file_path: str, save: bool = True):
        self.voice_prompt_path = file_path
        description, _duration = self._describe_audio_file(file_path)
        self.voice_label.setText(t("{name} ({desc})", name=os.path.basename(file_path), desc=description))
        self.btn_play_voice.setEnabled(True)
        self.btn_clear_voice.setEnabled(True)
        self.update_settings_summary()
        if save:
            self.status_label.setText(t("Ses örneği seçildi; yeni üretimde bu ses karakteri kullanılacak."))
            self._save_current_settings()

    def on_select_voice(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            t("Ses örneği seç"),
            "",
            t("Ses dosyası (*.wav *.mp3 *.flac *.ogg *.opus *.m4a);;Tüm dosyalar (*.*)"),
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
            QMessageBox.warning(self, t("Ses örneği çalınamadı"), t("Ses örneği okunamadı.\n\nAyrıntı:\n{e}", e=e))

    def on_show_voice_sample_text(self):
        dialog = VoiceGuideDialog(self)
        dialog.exec()

    def on_clear_voice(self):
        self.voice_prompt_path = None
        self.voice_label.setText(t("Ses örneği seçilmedi; varsayılan ses kullanılacak."))
        self.btn_play_voice.setEnabled(False)
        self.btn_clear_voice.setEnabled(False)
        self.status_label.setText(t("Ses örneği kaldırıldı; varsayılan sese dönüldü."))
        self.update_settings_summary()
        self._save_current_settings()

    def _on_history_search_changed(self, text: str):
        self._history_query = text
        self._refresh_history_list()

    def on_queue_add(self):
        """Mevcut text_edit içeriğini kuyruğa ekle."""
        text = self.text_edit.toPlainText().strip()
        if not text:
            QMessageBox.information(self, t("Boş metin"), t("Kuyruğa eklemek için metin alanı boş olmamalı."))
            return
        self._queue.append(text)
        self._refresh_queue_list()
        self.text_edit.clear()
        self.update_text_info()
        self.status_label.setText(t("Kuyruğa eklendi. Toplam: {n}", n=len(self._queue)))

    def on_queue_load_file(self):
        """Txt dosyasından satırları kuyruğa ekle."""
        path, _ = QFileDialog.getOpenFileName(
            self, t("Metin dosyası seç"), "", t("Metin dosyası (*.txt);;Tüm dosyalar (*.*)")
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
            QMessageBox.warning(self, t("Dosya okunamadı"), f"Hata:\n{e}")
            return
        added = 0
        for line in queue_split_lines(content):
            self._queue.append(line)
            added += 1
        self._refresh_queue_list()
        self.status_label.setText(t("Dosyadan {a} satır eklendi. Toplam: {n}", a=added, n=len(self._queue)))

    def on_queue_run(self):
        """Kuyruktaki tüm metinleri sırayla üret."""
        if self._queue_running:
            return
        if not self._queue:
            QMessageBox.information(self, t("Kuyruk boş"), t("Kuyruğa metin ekleyin."))
            return
        if not self.engine:
            QMessageBox.warning(self, t("Uyarı"), t("Motor henüz hazır değil."))
            return
        self._queue_running = True
        self.status_label.setText(t("Kuyruk başlatıldı. {n} metin işlenecek.", n=len(self._queue)))
        self._process_next_queue_item()

    def on_queue_clear(self):
        """Kuyruğu temizle (çalışıyorsa iptal etmez)."""
        if self._queue_running:
            QMessageBox.information(self, t("Çalışıyor"), t("Kuyruk şu an çalışıyor; durdurmak için Üretimi Durdur kullanın."))
            return
        self._queue.clear()
        self._refresh_queue_list()
        self.status_label.setText(t("Kuyruk temizlendi."))

    def _process_next_queue_item(self):
        """Kuyruktaki bir sonraki metni text_edit'e al ve on_generate çağır."""
        if not self._queue:
            self._queue_running = False
            self.status_label.setText(t("Kuyruk tamamlandı."))
            return
        text = self._queue[0]  # İptalde geri eklemek için pop etmeyelim
        self.text_edit.setPlainText(text)
        self.update_text_info()
        self.status_label.setText(t("Kuyruk işleniyor: {n} kaldı", n=len(self._queue)))
        if not self.on_generate():  # Mevcut tek-üretim akışı; başlatılamazsa kilit açılır
            self._queue_running = False
            self.status_label.setText(t("Kuyruk durduruldu. {n} metin kaldı.", n=len(self._queue)))

    def _refresh_queue_list(self):
        if hasattr(self, "queue_list"):
            self.queue_list.clear()
            for i, text in enumerate(self._queue, 1):
                preview = text.replace("\n", " ").strip()
                if len(preview) > 60:
                    preview = preview[:57] + "..."
                self.queue_list.addItem(f"{i}. {preview}")

    @staticmethod
    def _history_search_key(value: str) -> str:
        """TR'ye duyarlı arama anahtarı: İ/ı katlanır, birleşik işaretler atılır."""
        text = unicodedata.normalize("NFKD", (value or "").casefold())
        return "".join(ch for ch in text if not unicodedata.combining(ch)).replace(t("ı"), "i")

    def _history_matches(self, item: dict, query_key: str) -> bool:
        """Liste, seçim ve toplu silme aynı süzme kuralını kullanır."""
        return (
            query_key in self._history_search_key(item.get("name") or "")
            or query_key in self._history_search_key(item.get("text") or "")
        )

    def _refresh_history_list(self):
        if not hasattr(self, "history_list"):
            return
        self.history_list.clear()
        q = self._history_search_key(self._history_query.strip())
        for item in reversed(self.history[-100:]):
            name = item.get("name") or os.path.basename(item.get("path", "ses"))
            duration = item.get("duration", "?")
            file_path = item.get("path", "")
            exists = "" if os.path.exists(file_path) else " [dosya yok]"
            if q and not self._history_matches(item, q):
                continue
            extra = []
            if item.get("preset"):
                extra.append(item["preset"])
            if item.get("speed") is not None:
                extra.append(f"{item['speed']:.2f}x")
            info = f" [{' • '.join(extra)}]" if extra else ""
            self.history_list.addItem(f"{name} - {duration}{info}{exists}")

    def _on_history_selection_changed(self):
        item = self._selected_history_item()
        if item is None:
            self._history_detail_name.setText(t("Kayıt seçilmedi"))
            self._history_detail_meta.setText("")
            self._history_detail_wave.clear()
            return
        name = item.get("name") or os.path.basename(item.get("path", "ses"))
        self._history_detail_name.setText(name)
        exists = os.path.exists(item.get("path", ""))
        rows = [
            (t("Süre"), item.get("duration", "?")),
            ("Ayarlar", " • ".join(p for p in (
                item.get("preset"), item.get("language_id"),
                f"{item['speed']:.2f}x" if item.get("speed") is not None else None,
            ) if p)),
            ("Tarih", item.get("ts", "—")),
            ("Dosya", item.get("path", "—") + ("" if exists else "  (dosya yok)")),
        ]
        self._history_detail_meta.setText(
            "<br>".join(f"<b>{k}:</b> {v}" for k, v in rows if v))
        self._history_detail_wave.clear()

    def _selected_history_item(self) -> dict | None:
        row = self.history_list.currentRow()
        if row < 0:
            return None
        q = self._history_search_key(self._history_query.strip())
        items = list(reversed(self.history[-100:]))
        if q:
            items = [it for it in items if self._history_matches(it, q)]
        if row >= len(items):
            return None
        return items[row]

    def _add_history_entry(self, file_path: str, text: str, duration: str):
        entry = {
            "path": file_path,
            "name": os.path.basename(file_path),
            "text": text,
            "duration": duration,
            "preset": self.preset_combo.currentText(),
            "language_id": self.language_combo.currentData(),
            "exaggeration": self.exaggeration_spin.value(),
            "cfg_weight": self.cfg_spin.value(),
            "temperature": self.temperature_spin.value(),
            "repetition_penalty": self.repetition_spin.value(),
            "speed": self.speed_spin.value(),
            "pause_between_chunks": self.pause_spin.value(),
            "output_format": getattr(self, "_output_format", DEFAULT_OUTPUT_FORMAT),
            "mp3_bitrate": (getattr(self, "_quality_by_format", None) or {}).get(OUTPUT_FORMAT_MP3, DEFAULT_MP3_BITRATE),
            "opus_bitrate": (getattr(self, "_quality_by_format", None) or {}).get(OUTPUT_FORMAT_OPUS, DEFAULT_OPUS_BITRATE),
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
            QMessageBox.information(self, "Metin yok", t("Bu geçmiş kaydında geri alınacak metin bulunamadı."))
            return
        self.text_edit.setPlainText(text)
        self.status_label.setText(t("Geçmişteki metin üretim alanına alındı."))
        self.update_text_info()

    def on_regenerate_from_history(self):
        """Geçmişten seçili kaydın metnini + ayarlarını yükler, üretimi başlatır."""
        item = self._selected_history_item()
        if not item:
            return
        text = item.get("text", "")
        if not text:
            QMessageBox.information(self, "Metin yok", t("Bu geçmiş kaydında geri alınacak metin bulunamadı."))
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
        if item.get("mp3_bitrate"):
            self._quality_by_format[OUTPUT_FORMAT_MP3] = str(item["mp3_bitrate"])
        if item.get("opus_bitrate"):
            self._quality_by_format[OUTPUT_FORMAT_OPUS] = str(item["opus_bitrate"])
        if item.get("output_format") in VALID_OUTPUT_FORMATS:
            self._output_format = item["output_format"]
        self._refresh_format_tiles()
        self._refresh_quality_options()
        if "audio_prompt_path" in item and item["audio_prompt_path"]:
            path = item["audio_prompt_path"]
            if os.path.exists(path):
                self._set_voice_prompt(path, save=False)

        self.update_settings_summary()
        self.status_label.setText(t("Geçmiş ayarlar yüklendi; üretim başlatılıyor..."))

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
        message = t("Seçili geçmiş kaydı kaldırılsın mı?")
        if count > 1:
            message = t("{count} geçmiş kaydı kaldırılsın mı?", count=count)

        box = QMessageBox(self)
        box.setWindowTitle(t("Geçmişi sil"))
        box.setIcon(QMessageBox.Icon.Question)
        box.setText(message)
        info_text, delete_label = history_delete_dialog_texts(trash_available())
        box.setInformativeText(info_text)
        delete_files_button = box.addButton(delete_label, QMessageBox.ButtonRole.DestructiveRole)
        list_only_button = box.addButton(t("Sadece listeden kaldır"), QMessageBox.ButtonRole.AcceptRole)
        cancel_button = box.addButton(t("Vazgeç"), QMessageBox.ButtonRole.RejectRole)
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
        failed_paths = set()
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
                    failed_paths.add(file_path)

        target_ids = {id(item) for item in items if not delete_files or item.get("path") not in failed_paths}
        self.history = [item for item in self.history if id(item) not in target_ids]
        save_history(self.history)
        self._refresh_history_list()

        if failures:
            QMessageBox.warning(
                self,
                t("Bazı dosyalar silinemedi"),
                t("Geçmiş listesi temizlendi ama bazı ses dosyaları silinemedi.\n\n") + "\n".join(failures[:8]),
            )
        else:
            action = t("dosyalarıyla birlikte silindi") if delete_files else t("listeden kaldırıldı")
            self.status_label.setText(t("{n} geçmiş kaydı {action}.", n=len(items), action=action))

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
            QMessageBox.information(self, t("Geçmiş boş"), t("Silinecek geçmiş kaydı yok."))
            return
        q = self._history_search_key(self._history_query.strip())
        items = [it for it in self.history if self._history_matches(it, q)] if q else list(self.history)
        if not items:
            QMessageBox.information(self, t("Sonuç yok"), t("Filtreyle eşleşen geçmiş kaydı yok."))
            return
        mode = self._ask_history_delete_mode(len(items))
        if not mode:
            return
        self._delete_history_items(items, delete_files=(mode == "files"))

    def _update_language_tooltip(self, _index: int = 0):
        code = self.language_combo.currentData()
        name = LANGUAGES.get(code, code)
        sample = LANGUAGE_SAMPLES.get(code, "")
        self.language_combo.setToolTip(t("{name}: '{sample}'", name=name, sample=sample))

    def on_reset_all_settings(self):
        reply = QMessageBox.question(
            self,
            t("Ayarları sıfırla"),
            t("Tüm ayarlar varsayılana döndürülecek. Üretim geçmişi korunur.\nDevam edilsin mi?"),
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
        # Çıktı biçimi ve kalite
        self._output_format = DEFAULT_OUTPUT_FORMAT
        self._quality_by_format = {
            OUTPUT_FORMAT_WAV: "",
            OUTPUT_FORMAT_MP3: DEFAULT_MP3_BITRATE,
            OUTPUT_FORMAT_OPUS: DEFAULT_OPUS_BITRATE,
        }
        self._refresh_format_tiles()
        self._refresh_quality_options()
        # Tema
        theme_idx = self.theme_combo.findData("dark")
        if theme_idx >= 0:
            self.theme_combo.setCurrentIndex(theme_idx)
        # Voice
        self.voice_prompt_path = None
        self.voice_label.setText(t("Ses örneği seçilmedi; varsayılan ses kullanılacak."))
        self.btn_play_voice.setEnabled(False)
        self.btn_clear_voice.setEnabled(False)
        # Ses motoru (önizleme; gerçek yükleme en sonda)
        engine_index = self.engine_combo.findData(DEFAULT_ENGINE)
        engine_changed = bool(engine_index >= 0 and self.engine_combo.currentData() != DEFAULT_ENGINE)
        if engine_index >= 0:
            self.engine_combo.blockSignals(True)
            self.engine_combo.setCurrentIndex(engine_index)
            self.engine_combo.blockSignals(False)
        self._chatterbox_language_id = "tr"
        self._apply_engine_ui_state(DEFAULT_ENGINE)
        # Output dir
        self._set_output_dir(self._default_output_dir(), save=True)

        self.update_settings_summary()
        self.update_text_info()
        self.status_label.setText(t("Tüm ayarlar varsayılana sıfırlandı."))
        if engine_changed:
            self._init_engine_async()

    # ---- güncelleme -------------------------------------------------------

    def _updates_possible(self) -> bool:
        from . import updater
        return updater.updates_possible()

    def _run_update_cleanup(self):
        """Güncelleme sonrası indirme kalıntılarını arka planda sil."""
        from . import updater
        try:
            if updater.run_cleanup_async(on_done=self._notify_cleanup_done):
                log.info("Güncelleme sonrası indirme kalıntısı temizliği başlatıldı")
        except Exception:
            log.exception("Güncelleme temizliği başlatılamadı")

    def _notify_cleanup_done(self):
        # Temizlik iş parçacığından gelir: kuyruklu çağrıyla ana iş parçacığına taşı.
        QMetaObject.invokeMethod(self, "on_update_cleanup_done",
                                 Qt.ConnectionType.QueuedConnection)

    @pyqtSlot()
    def on_update_cleanup_done(self):
        self._show_update_current()

    def _update_startup_check(self):
        # İlk sessiz denetim açılıştan 30 sn sonra; sonra günde bir kez,
        # kaynak kopyada hiç.
        if not self._updates_possible():
            return
        from . import updater
        if not updater.last_check_is_old(self._update_last_check):
            return
        self._run_update_check(manual=False)

    def on_update_check(self):
        self._run_update_check(manual=True)

    def _run_update_check(self, manual: bool):
        if self._update_worker is not None and self._update_worker.isRunning():
            return
        if not self._updates_possible():
            if manual:
                self._show_update_error(t("Güncelleme yalnız paketlenmiş programda kullanılabilir."))
            return
        self._update_manual = manual
        if manual:
            self._show_update_checking()
        self._update_worker = UpdateWorker(__version__)
        self._update_worker.checked.connect(self._on_update_checked)
        self._update_worker.failed.connect(self._on_update_failed)
        self._update_worker.start()

    def _on_update_checked(self, info):
        from . import updater
        self._update_last_check = updater.now_stamp()
        self.settings["update_last_check"] = self._update_last_check
        self._save_current_settings()
        if info is None:
            if self._update_manual:
                self.update_status_label.setText(t("En güncel sürümdesiniz ({v}).", v=__version__))
                self.btn_update_check.setEnabled(True)
            return
        self._update_info = info
        self._render_update_offer()
        self.status_label.setText(
            t("Yeni sürüm {ver} çıktı — Ayarlar ▸ Güncelleme", ver=info.version))

    def _render_update_offer(self):
        """Bekleyen sürüm teklifi (indirme başlamadan önceki durum)."""
        from . import updater
        info = self._update_info
        if info is None:
            return
        self.update_status_label.setText(
            t("Yeni sürüm {ver} hazır ({size}). ", ver=info.version, size=updater.format_bytes(info.size)) +
            t("Program kapanıp yerinde güncellenecek; ayarlar ve çıktılar korunur."))
        self.update_stats_label.setText("")
        self.update_progress.setVisible(False)
        self.btn_update_check.setVisible(False)
        self.btn_update_install.setVisible(True)
        self.btn_update_install.setEnabled(True)
        self.btn_update_cancel.setVisible(True)
        self.btn_update_cancel.setEnabled(True)

    def _on_update_failed(self, message: str):
        if self._update_worker is not None and self._update_worker.is_cancelled():
            return
        self._show_update_error(message)

    def _show_update_error(self, message: str):
        self.update_status_label.setText(message)
        self.update_stats_label.setText("")
        self.btn_update_check.setVisible(True)
        self.btn_update_check.setEnabled(True)
        self.btn_update_install.setVisible(False)
        self.btn_update_cancel.setVisible(False)
        self.update_progress.setVisible(False)

    def _show_update_checking(self):
        self.update_status_label.setText(t("Denetleniyor…"))
        self.update_stats_label.setText("")
        self.btn_update_check.setEnabled(False)

    def _show_update_current(self):
        """Boşta satır: kurulu sürüm, son denetleme ve varsa son temizlik izi."""
        from . import updater
        if self._update_info is not None:
            return  # ekranda zaten bir teklif var; gömmeyelim
        self.update_stats_label.setText("")
        if self._update_last_check and not updater.last_check_is_old(self._update_last_check):
            when = self._update_last_check.replace("T", " ")
            text = t("Güncel — sürüm {__version__}. Son denetim: {when}.", __version__=__version__, when=when)
        else:
            text = t("Kurulu sürüm: {__version__}.", __version__=__version__)
        if updater.last_cleanup_result:
            text = f"{text} {updater.last_cleanup_result}."
        self.update_status_label.setText(text)

    def on_update_install(self):
        if self._update_info is None or not self._updates_possible():
            return
        if self._update_worker is not None and self._update_worker.isRunning():
            return
        self._update_worker = UpdateWorker(__version__, mode="install",
                                           info=self._update_info)
        self._update_worker.progress.connect(self._on_update_progress)
        self._update_worker.phase.connect(self._on_update_phase)
        self._update_worker.failed.connect(self._on_update_failed)
        self._update_worker.installed.connect(self._on_update_installed)
        self.update_status_label.setText(t("Güncelleme indiriliyor…"))
        self.update_stats_label.setText(t("Sunucuya bağlanılıyor…"))
        self.update_progress.setVisible(True)
        self.update_progress.setRange(0, 0)
        self.btn_update_cancel.setVisible(True)
        self.btn_update_cancel.setEnabled(True)
        self.btn_update_install.setEnabled(False)
        self._update_worker.start()

    def on_update_cancel(self):
        running = self._update_worker is not None and self._update_worker.isRunning()
        if running:
            self._update_worker.request_cancel()
        self.update_progress.setVisible(False)
        self.update_stats_label.setText("")
        if self._update_info is not None:
            self._render_update_offer()
            if running:
                self.update_stats_label.setText(t("İndirme iptal edildi."))
        else:
            self._show_update_current()
        self.btn_update_check.setEnabled(True)

    def _on_update_progress(self, done: int, total: int, speed: float):
        from . import updater
        if total > 0:
            self.update_progress.setRange(0, 1000)
            self.update_progress.setValue(min(1000, round(done * 1000 / total)))
            percent = round(done * 100 / total)
            parts = [f"{updater.format_bytes(done)} / {updater.format_bytes(total)} (%{percent})"]
        else:
            parts = [f"{updater.format_bytes(done)} indirildi"]
        parts.append(updater.format_speed(speed))
        if total > done > 0 and speed > 0:
            parts.append(f"kalan ~{updater.format_eta((total - done) / speed)}")
        self.update_stats_label.setText("  •  ".join(parts))

    def _on_update_phase(self, phase: str):
        if phase == "verify":
            self.update_progress.setRange(0, 1000)
            self.update_progress.setValue(1000)
            self.update_status_label.setText(t("İndirme tamamlandı; paket doğrulanıyor…"))
            self.update_stats_label.setText(
                t("Sağlama toplamı denetleniyor, birkaç dakika sürebilir."))
            self.btn_update_cancel.setEnabled(False)

    def _on_update_installed(self, version: str, launcher: str):
        self.update_progress.setRange(0, 1000)
        self.update_progress.setValue(1000)
        self.update_status_label.setText(
            t("Sürüm {version} indirildi. Kurulum başlatılıyor…", version=version))
        self.update_stats_label.setText(
            t("Program kapanacak; kurulum yerinde güncelleyip bitince programı yeniden açacak."))
        self.status_label.setText(t("Sürüm {v} indirildi; kurulum başlatılıyor.", v=version))
        self._launch_update_installer(launcher)

    def _launch_update_installer(self, launcher: str):
        """İndirilen kurulumu sessiz kipte başlat, sonra kendi kapanışımızı tamamla.

        v0.6.0 kalıbı: kurulum (Inno Setup) Restart Manager ile çalışan
        uygulamayı kapatır, {app} altını yerinde günceller ve bağımsız bekçiyle
        programı yeniden açar. v0.5.x'in swap betiği ve kardeş klasör akışı
        kaldırıldı — çağrılırsa AttributeError olur ve Qt slot yakalanmayan
        istisnada süreci düşürür (canlıda sessiz çökme).
        """
        if self._close_finalized:
            return  # kapanış zaten kurala bağlandı; kurulum çalışıyor
        from . import updater
        try:
            updater.spawn_installer(Path(launcher))
        except (updater.UpdateError, OSError) as exc:
            # Kurulum başlatılamazsa program kapanmamalı: kullanıcıya indirilen
            # dosyanın yerini söyle, asılı kalmasın.
            log.exception("Kurulum başlatılamadı")
            self.status_label.setText(t("Güncelleme indirildi; kurulum başlatılamadı."))
            self._show_update_error(t("Kurulum başlatılamadı; kurulum dosyasını elle çalıştırabilirsiniz."))
            QMessageBox.warning(
                self,
                t("Güncelleme indirildi"),
                t("Güncelleme indirildi ancak kurulum başlatılamadı.\n\n") +
                t("Ayrıntı: {exc}\n\n", exc=exc) +
                t("Kurulum dosyasını şuradan elle çalıştırabilirsiniz:\n") +
                f"{launcher}",
            )
            return
        if self._update_worker is not None:
            self._update_worker.wait(5000)
        self._close_requested = True
        self._queue_running = False
        if self._synth_worker and self._synth_worker.isRunning():
            self._synth_cancel_requested = True
            self._synth_worker.request_cancel()
        if self._compress_worker and self._compress_worker.isRunning():
            self._compress_worker.request_cancel()
        self.close()

    def _on_theme_changed(self, _index: int):
        theme = self.theme_combo.currentData() if hasattr(self, "theme_combo") else "dark"
        self._resolved_theme = apply_theme(QApplication.instance(), theme)
        self._refresh_theme_icons()
        self._save_current_settings()

    def _on_ui_language_changed(self, _index: int):
        kod = self.ui_lang_combo.currentData() if hasattr(self, "ui_lang_combo") else "en"
        ui_set_language(kod or "en")
        self._set_option("ui_language", kod or "en")
        self._retranslate_ui()
        self._refresh_dynamic_texts()

    def _set_outputs_enabled(self, enabled: bool):
        for button in (self.btn_play, self.btn_stop, self.btn_save_wav, self.btn_save_mp3):
            button.setEnabled(enabled)

    def _set_engine_actions_enabled(self, enabled: bool):
        self.btn_generate.setEnabled(enabled)

    def _set_busy(self, busy: bool, message: str | None = None):
        if isinstance(self.btn_generate, ActionButton):
            if busy:
                self.btn_generate.set_busy(True, t("Üretiliyor"))
            else:
                self.btn_generate.set_busy(False)
                self._set_engine_actions_enabled(self.engine is not None)
        else:
            self._set_engine_actions_enabled(not busy and self.engine is not None)
        if message:
            self.status_label.setText(message)
        if busy:
            self.engine_status_pill.setText(t("ÇALIŞIYOR"))
            self.engine_status_pill.set_tone("info")
            self.progress.setRange(0, 0)
        elif self.engine is not None:
            self.engine_status_pill.setText("HAZIR")
            self.engine_status_pill.set_tone("success")
        self._refresh_engine_combo_enabled(busy=busy)

    def on_generate(self) -> bool:
        text = self.text_edit.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, t("Uyarı"), t("Metin boş."))
            return False
        if not self.engine:
            QMessageBox.warning(self, t("Uyarı"), t("Motor henüz hazır değil."))
            return False
        if self._synth_worker and self._synth_worker.isRunning():
            QMessageBox.information(
                self, t("Üretim sürüyor"), t("Devam eden üretim bitmeden yeni üretim başlatılamaz.")
            )
            return False

        # Referans ses örneği yoksa kullanıcıyı uyar (EMA tek sesle okur; gerekmez).
        if self._needs_voice_warning():
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Icon.Warning)
            box.setWindowTitle(t("Referans ses örneği yok"))
            box.setText(
                t("Referans ses örneği seçmediniz.\n") +
                t("Varsayılan ses kullanılacak; ses robotik olabilir.")
            )
            box.setInformativeText("Ses Örneği Seç, Yine de Üret veya İptal.")
            btn_select = box.addButton(t("Ses Örneği Seç"), QMessageBox.ButtonRole.AcceptRole)
            box.addButton(t("Yine de Üret"), QMessageBox.ButtonRole.DestructiveRole)
            btn_cancel = box.addButton(t("İptal"), QMessageBox.ButtonRole.RejectRole)
            box.setDefaultButton(btn_select)
            box.exec()
            clicked = box.clickedButton()
            if clicked == btn_select:
                self.on_select_voice()
                return False  # Bu üretim iptal; kullanıcı ses seçtiyse bir sonraki Üret'te devam eder
            if clicked == btn_cancel:
                return False
            # t("Yine de Üret") -> oturumda bir daha sorma
            self._voice_warning_dismissed = True

        self.last_text = text
        self._save_current_settings()

        # Ses tasarımı (yalnız VoxCPM2): tarif metnin başına eklenir.
        text = self._apply_voice_design(text)
        chunks = chunker.split_into_chunks(text)
        if not chunks:
            QMessageBox.warning(self, t("Uyarı"), t("Metin boş."))
            return False

        # Madde 3: Çok parçalı üretim uyarısı
        parts = len(chunks)
        if parts > CONFIRM_CHUNK_COUNT:
            reply = QMessageBox.question(
                self,
                t("Çok parçalı üretim"),
                t("{parts} parça üretilecek. Bu uzun sürer.\nDevam edilsin mi?", parts=parts),
            )
            if reply != QMessageBox.StandardButton.Yes:
                return False
        elif parts > WARN_CHUNK_COUNT:
            QMessageBox.warning(
                self,
                t("Parçalı üretim"),
                t("Metin {parts} parçaya bölündü. Üretim uzun sürebilir.", parts=parts),
            )

        self._synth_cancel_requested = False
        self._set_busy(True, t("Üretiliyor... 0/{n}", n=len(chunks)))
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
        self._synth_worker.finished.connect(self._on_background_worker_finished)
        self._synth_worker.start()
        return True

    def on_cancel_synthesis(self):
        if not self._synth_worker or not self._synth_worker.isRunning():
            return
        if self._synth_cancel_requested:
            return

        self._synth_cancel_requested = True
        self._synth_worker.request_cancel()
        self.status_label.setText(t("Üretim durduruluyor..."))
        audio_player.stop()
        if self._synth_dialog:
            self._synth_dialog.cancel_button.setEnabled(False)
            self._synth_dialog.status_label.setText(t("Üretim durduruluyor..."))
            self._synth_dialog.detail.appendPlainText("Üretim durduruluyor; model yanıt vermezse işlem zorla kesilecek.")

    def _on_synth_chunk_started(self, index: int, total: int, text: str):
        self.status_label.setText(t("Üretiliyor... Parça {i}/{n}", i=index, n=total))
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
            t("Üretiliyor... Parça {index}/{total_chunks}: %{percent} ({current}/{total_steps}) | ", index=index, total_chunks=total_chunks, percent=percent, current=current, total_steps=total_steps) +
            t("Geçen: {elapsed} | Kalan: {remaining}{rate_text}", elapsed=elapsed, remaining=remaining, rate_text=rate_text)
        )
        if self._synth_dialog:
            self._synth_dialog.sampling_progress(index, total_chunks, percent, current, total_steps, elapsed, remaining, rate)

    def _on_synth_chunk_done(self, done: int, total: int, seconds: float):
        self.progress.setRange(0, total * 1000)
        self.progress.setValue(done * 1000)
        self.status_label.setText(t("Üretiliyor... {d}/{n} tamamlandı", d=done, n=total))
        if self._synth_dialog:
            self._synth_dialog.chunk_done(done, total, seconds)

    def _on_synth_done(self, wav, sr):
        if self._synth_cancel_requested:
            self._on_synth_cancelled(t("Üretim kullanıcı tarafından durduruldu."))
            return
        self._synth_worker = None
        wav = trim_leading_silence(wav, sr)
        self.last_wav = wav
        self.last_sr = sr
        self.waveform_view.set_data(wav)
        self._set_outputs_enabled(True)
        duration_text = f"{len(wav) / sr:.1f} sn"
        self.last_output_path = None
        save_error = None
        try:
            self.last_output_path = self._auto_save_generated_audio(wav, sr, self.last_text or self.text_edit.toPlainText())
            self._add_history_entry(self.last_output_path, self.last_text or self.text_edit.toPlainText(), duration_text)
        except Exception as exc:
            save_error = str(exc)
            log.exception("Otomatik kayit basarisiz")

        message = t("Üretildi - {duration_text} @ {sr} Hz", duration_text=duration_text, sr=sr)
        self._reset_progress()
        self._set_busy(False, message)
        # Madde 1: Sayaç
        self.production_count += 1
        self.stats_label.setText(t("Toplam: {n} üretim", n=self.production_count))
        # Madde 2: Last path
        filename = os.path.basename(self.last_output_path) if self.last_output_path else "—"
        self.status_label.setText(t("{msg} | Son: {name}", msg=message, name=filename))
        if self.last_output_path:
            self.playback_hint.setText(t("{name} • {dur} • {sr} Hz", name=filename, dur=duration_text, sr=sr))
        elif save_error:
            self.playback_hint.setText(t("Ses hazır; otomatik kayıt tamamlanamadı: {err}", err=save_error))
        else:
            self.playback_hint.setText(t("Ses hazır • {dur} • {sr} Hz", dur=duration_text, sr=sr))
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
            self.status_label.setText(t("Kuyruk durduruldu. {n} metin kaldı.", n=len(self._queue)))

    def _on_synth_failed(self, msg: str):
        if self._synth_cancel_requested:
            self._on_synth_cancelled(t("Üretim kullanıcı tarafından durduruldu."))
            return
        self._synth_worker = None
        self._reset_progress()
        self._set_busy(False, t("Sentez başarısız."))
        if self._synth_dialog:
            self._synth_dialog.finish_error(msg)
        self._show_error(t("Sentez hatası"), msg)

        # Kuyruk: hata sonrası kilit açılır (kalan metinler korunur).
        if self._queue_running:
            self._queue_running = False
            self.status_label.setText(t("Kuyruk durduruldu (hata). {n} metin kaldı.", n=len(self._queue)))

    def _auto_save_generated_audio(self, wav, sr, text: str) -> str:
        """Üretimi seçilen biçimde çıktı klasörüne yaz (Ayarlar → Çıktı).

        WAV kayıpsız yazılır; MP3/OPUS pydub + ffmpeg ile üretilir. Dönüştürme
        başarısız olursa (ffmpeg yok/hatalı) aynı adla WAV kaydedilir ve durum
        çubuğuna not düşülür; üretim hiçbir durumda kaybolmaz.
        """
        fmt = self._output_format if self._output_format in VALID_OUTPUT_FORMATS else DEFAULT_OUTPUT_FORMAT
        extension = OUTPUT_FORMAT_EXTENSIONS.get(fmt, ".wav")
        os.makedirs(self.output_dir, exist_ok=True)
        file_path = unique_path(self.output_dir, safe_filename_from_text(text, extension))
        if fmt == OUTPUT_FORMAT_WAV:
            sf.write(file_path, _as_mono(wav), sr)
            return str(file_path)
        default_bitrate = DEFAULT_MP3_BITRATE if fmt == OUTPUT_FORMAT_MP3 else DEFAULT_OPUS_BITRATE
        bitrate = self._quality_by_format.get(fmt) or default_bitrate
        try:
            self._export_compressed(wav, sr, file_path, fmt, bitrate)
            return str(file_path)
        except Exception as exc:
            log.warning("Sıkıştırılmış çıktı yazılamadı (%s): %s", fmt, exc)
            fallback = file_path.with_suffix(".wav")
            sf.write(fallback, _as_mono(wav), sr)
            self.status_label.setText(
                t("{fmt} yazılamadı; WAV olarak kaydedildi: {name}", fmt=format_label(fmt), name=fallback.name))
            return str(fallback)

    def _export_compressed(self, wav, sr, file_path: Path, fmt: str, bitrate: str) -> None:
        """pydub + ffmpeg ile mp3/opus yaz (otomatik ve elle kaydın ortak yolu)."""
        from pydub import AudioSegment

        data_np = np.clip(_as_mono(wav), -1.0, 1.0)
        data = (data_np * 32767).astype(np.int16).tobytes()
        segment = AudioSegment(data=data, sample_width=2, frame_rate=sr, channels=1)
        segment.export(str(file_path), format="mp3" if fmt == OUTPUT_FORMAT_MP3 else "opus",
                       bitrate=bitrate)

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
        sf.write(file_path, _as_mono(self.last_wav), self.last_sr)
        self.last_output_path = file_path
        self._add_history_entry(file_path, self.last_text or self.text_edit.toPlainText(), f"{len(self.last_wav) / self.last_sr:.1f} sn")
        self.status_label.setText(t("Kaydedildi: {path}", path=file_path))

    def on_save_mp3(self):
        if self.last_wav is None:
            return
        default_path = self._make_output_path(".mp3")
        file_path, _ = QFileDialog.getSaveFileName(self, "MP3 olarak kaydet", default_path, "MP3 (*.mp3)")
        if not file_path:
            return
        try:
            bitrate = self._quality_by_format.get(OUTPUT_FORMAT_MP3) or DEFAULT_MP3_BITRATE
            self._export_compressed(self.last_wav, self.last_sr, Path(file_path), OUTPUT_FORMAT_MP3, bitrate)
            self._add_history_entry(file_path, self.last_text or self.text_edit.toPlainText(), f"{len(self.last_wav) / self.last_sr:.1f} sn")
            self.status_label.setText(t("Kaydedildi: {path}", path=file_path))
        except Exception as e:
            QMessageBox.warning(
                self,
                t("MP3 kayıt başarısız"),
                t("MP3 kaydı yapılamadı. WAV olarak kaydedebilirsin.\n\nAyrıntı:\n{e}", e=e),
            )

    def on_compress_add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, t("Sıkıştırılacak ses dosyalarını seç"), "",
            t("Ses dosyası (*.wav *.mp3 *.flac *.ogg *.opus);;Tüm dosyalar (*.*)")
        )
        if not paths:
            return
        for path in paths:
            if path not in self._compress_files:
                self._compress_files.append(path)
                size = os.path.getsize(path) if os.path.exists(path) else 0
                size_str = f"{size / 1_048_576:.1f} MB" if size > 0 else "?"
                self.compress_file_list.addItem(f"{os.path.basename(path)}  ({size_str})")
        self.status_label.setText(t("Sıkıştırma listesi: {n} dosya", n=len(self._compress_files)))

    def on_compress_clear(self):
        self._compress_files.clear()
        self.compress_file_list.clear()
        self.compress_results.clear()
        self.status_label.setText(t("Sıkıştırma listesi temizlendi."))

    def on_compress_select_output_dir(self):
        directory = QFileDialog.getExistingDirectory(self, t("Sıkıştırılmış dosyalar için çıktı klasörü seç"), self.compress_output_dir or "")
        if not directory:
            return
        self.compress_output_dir = directory
        self.compress_output_label.setText(directory)
        self.compress_output_label.setProperty("muted", False)
        self._refresh_widget_style(self.compress_output_label)
        self._save_current_settings()

    def on_compress_clear_output_dir(self):
        self.compress_output_dir = None
        self.compress_output_label.setText(t("(boş = orijinal dosyanın yanına kaydet)"))
        mark_muted(self.compress_output_label)
        self._refresh_widget_style(self.compress_output_label)
        self.compress_output_label.setWordWrap(True)
        self._save_current_settings()

    def on_compress_start(self):
        if self._compress_worker and self._compress_worker.isRunning():
            QMessageBox.information(
                self, t("Sıkıştırma sürüyor"), t("Devam eden sıkıştırma bitmeden yenisi başlatılamaz.")
            )
            return
        if not self._compress_files:
            QMessageBox.information(self, t("Liste boş"), t("Önce sıkıştırılacak dosyaları ekleyin."))
            return
        if not audio_compressor.ffmpeg_available():
            QMessageBox.warning(self, t("FFmpeg bulunamadı"),
                               t("Sistemde FFmpeg bulunamadı. Sıkıştırma yapılamaz.\n\n") +
                               t("FFmpeg kurmak için:\n")
                               + t("winget install Gyan.FFmpeg --accept-package-agreements --accept-source-agreements"))
            return

        if isinstance(self.btn_compress_start, ActionButton):
            self.btn_compress_start.set_busy(True, t("Sıkıştırılıyor"))
        else:
            self.btn_compress_start.setEnabled(False)
        self.btn_compress_add.setEnabled(False)
        self.btn_compress_clear.setEnabled(False)
        self.compress_results.clear()
        self.status_label.setText(t("Sıkıştırma başlatıldı..."))
        self._compress_ok_count = 0
        self._compress_fail_count = 0

        bitrate = self.compress_bitrate_combo.currentData()
        self._compress_worker = CompressWorker(
            list(self._compress_files), bitrate=bitrate, channels=1, output_dir=self.compress_output_dir
        )
        self._compress_worker.file_done.connect(self._on_compress_file_done)
        self._compress_worker.all_finished.connect(self._on_compress_finished)
        self._compress_worker.cancelled.connect(self._on_compress_cancelled)
        self._compress_worker.finished.connect(self._on_background_worker_finished)
        self._compress_worker.start()

    def _on_compress_file_done(self, result: audio_compressor.CompressionResult):
        name = result.input_path.name
        if result.ok:
            self._compress_ok_count += 1
            orig_mb = result.original_size / 1_048_576
            comp_mb = result.compressed_size / 1_048_576
            pct = (1 - result.ratio) * 100 if result.ratio else 0
            output_str = f"  → {result.output_path}" if result.output_path else ""
            self._append_compress_result(
                t("✓ {name}  {orig_mb:.1f} MB → {comp_mb:.1f} MB  (%{pct:.0f} küçüldü)", name=name, orig_mb=orig_mb, comp_mb=comp_mb, pct=pct),
                "success",
            )
            if output_str:
                self._append_compress_result(output_str, "muted")
            log.info(
                "Opus sıkıştırma başarılı: %s (%.1f MB → %.1f MB, %s, %.1f sn)",
                name, orig_mb, comp_mb, result.bitrate, result.duration_seconds,
            )
        else:
            self._compress_fail_count += 1
            self._append_compress_result(f"✗ {name}  — {result.error}", "danger")
            log.warning("Opus sıkıştırma başarısız: %s — %s", name, result.error)

    def _append_compress_result(self, text: str, tone: str) -> None:
        self.compress_results.addItem(text)
        item = self.compress_results.item(self.compress_results.count() - 1)
        item.setData(Qt.ItemDataRole.UserRole, tone)
        self._style_compress_result_item(item)

    def _style_compress_result_item(self, item) -> None:
        colors = theme_tokens(self._resolved_theme)["colors"]
        token = {
            "success": "success",
            "danger": "danger",
            "muted": "text_muted",
        }.get(item.data(Qt.ItemDataRole.UserRole), "text_secondary")
        item.setForeground(QColor(colors[token]))

    def _refresh_compress_result_colors(self) -> None:
        if not hasattr(self, "compress_results"):
            return
        for index in range(self.compress_results.count()):
            self._style_compress_result_item(self.compress_results.item(index))

    def _on_compress_finished(self):
        if isinstance(self.btn_compress_start, ActionButton):
            self.btn_compress_start.set_busy(False)
        else:
            self.btn_compress_start.setEnabled(True)
        self.btn_compress_add.setEnabled(True)
        self.btn_compress_clear.setEnabled(True)
        total = self._compress_ok_count + self._compress_fail_count
        msg = t("✓ {ok} başarılı", ok=self._compress_ok_count)
        if self._compress_fail_count > 0:
            msg += t(", ✗ {fail} başarısız", fail=self._compress_fail_count)
        self.status_label.setText(t("Sıkıştırma tamamlandı: {msg}", msg=msg))
        QMessageBox.information(
            self,
            t("Sıkıştırma tamamlandı"),
            t("Sıkıştırma tamamlandı.\n\n{msg}\n\nToplam: {total} dosya", msg=msg, total=total),
        )

    def _on_compress_cancelled(self):
        if isinstance(self.btn_compress_start, ActionButton):
            self.btn_compress_start.set_busy(False)
        else:
            self.btn_compress_start.setEnabled(True)
        self.btn_compress_add.setEnabled(True)
        self.btn_compress_clear.setEnabled(True)
        self.status_label.setText(t("Sıkıştırma güvenli şekilde durduruldu."))

    def _reset_progress(self):
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
