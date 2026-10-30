"""İlk açılış sihirbazı — motor seçimi.

Neden ayrı pencere: program ilk kez açıldığında hangi motorun indirileceğine
kullanıcı karar vermeli. Sessizce 3 GB indirmek kabul edilemez; hiçbir şey
söylemeden "motor yok" hatası da kabul edilemez.

Sihirbaz yalnız **bir kez** ve yalnız hiçbir motor kurulu değilken görünür
(``state/first_run.json`` işareti). "Sonra" ile geçilebilir; o zaman Üretim
ekranı "motor seçilmedi" durumunu gösterir ve Modeller sekmesine yönlendirir.

EMA programla geldiği için sihirbazın varsayılan seçeneği odur: indirme yok,
hemen kullanılabilir.
"""
from __future__ import annotations
from i18n import t, set_language as ui_set_language, language as ui_language, LANGUAGES as UI_LANGUAGES

import json
import logging
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QRadioButton,
    QVBoxLayout,
)

from . import engines as engine_registry
from . import hardware
from .theme import application_icon
from .widgets import ActionButton, SectionCard

log = logging.getLogger(__name__)

__all__ = ["FirstRunDialog", "should_show", "mark_seen"]

_MARKER_NAME = "first_run.json"


def _marker_path() -> Path:
    from app import paths as app_paths

    return app_paths.state_dir() / _MARKER_NAME


def should_show() -> bool:
    """Sihirbaz gösterilmeli mi: işaret yoksa ve kurulu indirilebilir motor yoksa."""
    from app import model_manager

    try:
        data = json.loads(_marker_path().read_text(encoding="utf-8"))
        if data.get("wizard_seen"):
            return False
    except (OSError, json.JSONDecodeError):
        pass
    for spec in engine_registry.ordered():
        if spec.bundled:
            continue
        if model_manager.state_for(spec.key).installed:
            return False
    return True


def mark_seen() -> None:
    """Sihirbaz bir kez gösterildi (kullanıcı atlasa bile tekrar sorulmaz)."""
    path = _marker_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"wizard_seen": True}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        log.exception("İlk açılış işareti yazılamadı: %s", path)


class FirstRunDialog(QDialog):
    """İlk açılışta motor seçimi.

    ``selected`` sinyali motor anahtarını taşır; çağıran indirmeyi başlatır.
    Boş string = "sonra" (indirme yok).
    """

    selected = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("firstRunDialog")
        self.setWindowIcon(application_icon())
        self.setWindowTitle(t("Voxora Studio — İlk kurulum"))
        self.setModal(False)  # ana pencere kullanılabilir kalsın
        self.resize(720, 520)
        self._choice = ""

        profile = hardware.detect()
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(16)

        step = QLabel("ADIM 1 / 1")
        step.setObjectName("dialogStep")
        root.addWidget(step)

        title = QLabel(t("Ses motorunuzu seçin"))
        title.setObjectName("dialogTitle")
        root.addWidget(title)

        lead = QLabel(
            t("Program kuruldu. Model ağırlıkları kurulum paketinde gelmez — ") +
            t("seçtiğiniz motorun dosyaları indirilir. Sonradan ") +
            t("<b>Modeller</b> sekmesinden değiştirebilir veya ikinci motoru ") +
            t("ekleyebilirsiniz.")
        )
        lead.setObjectName("dialogSubtitle")
        lead.setWordWrap(True)
        lead.setTextFormat(Qt.TextFormat.RichText)
        root.addWidget(lead)

        card = SectionCard(parent=self)
        group = QButtonGroup(self)
        group.setExclusive(True)
        first_usable = None

        for spec in engine_registry.ordered():
            usable, reason = engine_registry.availability(
                spec, cuda=profile.cuda, disk_free_gb=profile.disk_free_gb
            )
            row = QFrame()
            row.setObjectName("engineOption")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(4, 6, 4, 6)
            row_layout.setSpacing(10)

            radio = QRadioButton()
            group.addButton(radio)
            radio.setProperty("engineKey", spec.key)
            row_layout.addWidget(radio, alignment=Qt.AlignmentFlag.AlignTop)

            text_col = QVBoxLayout()
            text_col.setSpacing(2)
            name = QLabel(f"<b>{spec.label}</b>")
            name.setTextFormat(Qt.TextFormat.RichText)
            text_col.addWidget(name)
            detail = QLabel(engine_registry.capabilities_text(spec))
            detail.setObjectName("modelMeta")
            text_col.addWidget(detail)
            cost = QLabel(
                "Programla birlikte gelir — indirme yok"
                if spec.bundled
                else t("{size} — bağlantınıza göre birkaç dakika", size=spec.size_label())
            )
            cost.setObjectName("modelNote")
            text_col.addWidget(cost)
            if not usable and reason:
                warn = QLabel(reason)
                warn.setObjectName("modelWarning")
                warn.setWordWrap(True)
                text_col.addWidget(warn)
            row_layout.addLayout(text_col, stretch=1)

            radio.setEnabled(usable)
            if usable and first_usable is None:
                first_usable = spec.key
            card.content_layout.addWidget(row)

            if spec.bundled:
                radio.setChecked(True)
                self._choice = spec.key
        root.addWidget(card)

        if first_usable and not self._choice:
            self._choice = first_usable

        folder_card = SectionCard(t("Model klasörü"), t("İndirilen ağırlıklar burada tutulur."), parent=self)
        from app import paths as app_paths

        folder = QLabel(str(app_paths.models_dir()))
        folder.setObjectName("modelPath")
        folder.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        folder_card.content_layout.addWidget(folder)
        root.addWidget(folder_card)
        root.addStretch(1)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        hint = QLabel(t("İndirmeyi atlarsanız program açılır; üretim için model gerekir."))
        hint.setObjectName("modelNote")
        hint.setWordWrap(True)
        actions.addWidget(hint, stretch=1)
        self.btn_later = ActionButton(t("Sonra"), variant="ghost")
        self.btn_start = ActionButton(t("İndir ve başla"), variant="primary", icon_name="download")
        actions.addWidget(self.btn_later)
        actions.addWidget(self.btn_start)
        root.addLayout(actions)

        self.btn_later.clicked.connect(self._on_later)
        self.btn_start.clicked.connect(self._on_start)
        group.buttonToggled.connect(self._on_toggle)
        self._group = group

        # Seçili motorun kurulu olması indirmeyi gereksiz kılar.
        self._sync_start_button()

    def _on_toggle(self, button: QRadioButton, checked: bool) -> None:
        if not checked:
            return
        self._choice = str(button.property("engineKey") or "")
        self._sync_start_button()

    def _sync_start_button(self) -> None:
        from app import model_manager

        if not self._choice:
            self.btn_start.setEnabled(False)
            return
        state = model_manager.state_for(self._choice)
        if state.installed:
            self.btn_start.setText(t("Başla"))
        else:
            self.btn_start.setText(t("İndir ve başla"))
        self.btn_start.setEnabled(True)

    def _on_start(self) -> None:
        mark_seen()
        self.selected.emit(self._choice)
        self.accept()

    def _on_later(self) -> None:
        mark_seen()
        self.selected.emit("")
        self.reject()

    def selected_engine(self) -> str:
        return self._choice
