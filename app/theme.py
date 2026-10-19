"""Central design tokens and application styling for Voxora Studio."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPalette

from .icons import (
    action_icon,
    application_icon,
    apply_icon,
    asset_path,
    button_icon,
    menu_icon,
    navigation_icon,
    ui_icon,
)


# Brand colors live with the visual system rather than being repeated in QSS.
ACCENT = "#8B7CF6"
ACCENT_SECONDARY = "#22D3EE"

_STRUCTURE_TOKENS: dict[str, dict[str, int]] = {
    "radius": {
        "small": 7,
        "medium": 10,
        "large": 14,
        "card": 16,
        "pill": 999,
    },
    "spacing": {
        "xxs": 4,
        "xs": 6,
        "sm": 8,
        "md": 12,
        "lg": 16,
        "xl": 20,
        "xxl": 24,
    },
    "control": {
        "small_height": 30,
        "medium_height": 38,
        "large_height": 46,
        "icon_size": 18,
    },
    "motion": {
        "fast_ms": 120,
        "standard_ms": 160,
        "sidebar_ms": 180,
    },
}

_DARK_COLORS = {
    "window": "#0B0D16",
    "surface": "#121628",
    "surface_alt": "#0E1120",
    "surface_raised": "#1B2138",
    "surface_hover": "#222B47",
    "sidebar": "#0B0D16",
    "sidebar_hover": "#171C2E",
    "sidebar_active": "#171435",
    "border": "#232A44",
    "border_strong": "#3A4266",
    "divider": "#1D2233",
    "text": "#F7F8FC",
    "text_secondary": "#C0C7D8",
    "text_muted": "#8E99B0",
    "text_disabled": "#596276",
    "placeholder": "#68738A",
    "accent": "#8B7CF6",
    "accent_hover": "#9F86FA",
    "accent_pressed": "#6D5AE8",
    "accent_soft": "#171435",
    "accent_border": "#6F56C9",
    "accent_text": "#FFFFFF",
    "secondary": ACCENT_SECONDARY,
    "secondary_hover": "#67E8F9",
    "secondary_soft": "#102C38",
    "selection": "#49368C",
    "selection_text": "#FFFFFF",
    "focus": "#A78BFA",
    "danger": "#FF7389",
    "danger_hover": "#FF8EA0",
    "danger_pressed": "#E34F69",
    "danger_soft": "#351923",
    "danger_border": "#743143",
    "warning": "#F6C85F",
    "warning_soft": "#2B2415",
    "warning_border": "#70591F",
    "success": "#54D6A1",
    "success_soft": "#123126",
    "success_border": "#256A50",
    "info": "#67C7FF",
    "info_soft": "#122A3A",
    "info_border": "#255E7C",
    "scrollbar": "#3C4760",
    "scrollbar_hover": "#596783",
}

_LIGHT_COLORS = {
    "window": "#F3F5FA",
    "surface": "#FFFFFF",
    "surface_alt": "#F7F8FC",
    "surface_raised": "#EEF1F8",
    "surface_hover": "#E7EBF5",
    "sidebar": "#FBFCFF",
    "sidebar_hover": "#F0F2FA",
    "sidebar_active": "#EEE9FF",
    "border": "#DCE1EC",
    "border_strong": "#B9C2D4",
    "divider": "#E8EBF2",
    "text": "#181B26",
    "text_secondary": "#3E4658",
    "text_muted": "#667085",
    "text_disabled": "#9AA3B3",
    "placeholder": "#8A94A6",
    "accent": "#7652E8",
    "accent_hover": "#6844DB",
    "accent_pressed": "#5937C7",
    "accent_soft": "#EEE9FF",
    "accent_border": "#A993F2",
    "accent_text": "#FFFFFF",
    "secondary": "#087F9A",
    "secondary_hover": "#086A81",
    "secondary_soft": "#E4F8FC",
    "selection": "#DCD2FF",
    "selection_text": "#201742",
    "focus": "#7652E8",
    "danger": "#C93855",
    "danger_hover": "#B62845",
    "danger_pressed": "#9E213B",
    "danger_soft": "#FFF0F3",
    "danger_border": "#E9A6B3",
    "warning": "#8A6110",
    "warning_soft": "#FFF8DF",
    "warning_border": "#E4C76F",
    "success": "#167A56",
    "success_soft": "#E9F9F2",
    "success_border": "#8ACDAF",
    "info": "#176B96",
    "info_soft": "#EAF7FD",
    "info_border": "#8FCBE7",
    "scrollbar": "#B7C0D1",
    "scrollbar_hover": "#929DB1",
}

# Public snapshots are intentionally read-only by convention.  Use
# ``theme_tokens`` to receive a defensive copy for local calculations.
DARK_THEME_TOKENS = {"name": "dark", "colors": _DARK_COLORS, **_STRUCTURE_TOKENS}
LIGHT_THEME_TOKENS = {"name": "light", "colors": _LIGHT_COLORS, **_STRUCTURE_TOKENS}
THEME_TOKENS = {"dark": DARK_THEME_TOKENS, "light": LIGHT_THEME_TOKENS}


def _system_theme(app) -> str:
    """Resolve and remember the native color scheme before we replace it."""
    if app is None:
        return "dark"

    try:
        remembered = app.property("voxoraSystemTheme")
    except (AttributeError, RuntimeError):
        remembered = None

    resolved: str | None = None
    try:
        scheme = app.styleHints().colorScheme()
        scheme_name = getattr(scheme, "name", str(scheme)).lower()
        if scheme == Qt.ColorScheme.Dark or "dark" in scheme_name:
            resolved = "dark"
        elif scheme == Qt.ColorScheme.Light or "light" in scheme_name:
            resolved = "light"
    except (AttributeError, RuntimeError, TypeError):
        pass

    # Older Qt releases do not expose colorScheme().  In that case retain the
    # palette result captured before Voxora first installed its own palette.
    if resolved is None and remembered in {"dark", "light"}:
        return remembered

    if resolved is None:
        try:
            window = app.palette().color(QPalette.ColorRole.Window)
            text = app.palette().color(QPalette.ColorRole.WindowText)
            # Relative lightness is more reliable for high-contrast palettes.
            resolved = "dark" if window.lightness() < text.lightness() else "light"
        except (AttributeError, RuntimeError, TypeError):
            resolved = "dark"

    try:
        app.setProperty("voxoraSystemTheme", resolved)
    except (AttributeError, RuntimeError):
        pass
    return resolved


def resolve_theme(app, theme: str | None) -> str:
    """Resolve ``light``, ``dark`` or ``system`` to a concrete theme.

    Missing, malformed and future/unknown values deliberately fall back to the
    cinematic dark theme, which is the safe default for a fresh installation.
    """
    requested = theme.strip().lower() if isinstance(theme, str) else ""
    if requested == "system":
        return _system_theme(app)
    return requested if requested in {"dark", "light"} else "dark"


def theme_tokens(theme: str | None, app=None) -> dict[str, Any]:
    """Return a defensive token snapshot for a requested theme."""
    resolved = resolve_theme(app, theme)
    return deepcopy(THEME_TOKENS[resolved])


def current_theme(app=None) -> str:
    """Return the active resolved theme, defaulting safely to dark."""
    if app is None:
        try:
            from PyQt6.QtWidgets import QApplication

            app = QApplication.instance()
        except (ImportError, RuntimeError):
            app = None
    if app is not None:
        try:
            active = app.property("voxoraTheme")
            if active in {"dark", "light"}:
                return active
        except (AttributeError, RuntimeError):
            pass
    return "dark"


def _application_palette(colors: dict[str, str]) -> QPalette:
    palette = QPalette()
    roles = {
        QPalette.ColorRole.Window: "window",
        QPalette.ColorRole.WindowText: "text",
        QPalette.ColorRole.Base: "surface",
        QPalette.ColorRole.AlternateBase: "surface_alt",
        QPalette.ColorRole.ToolTipBase: "surface_raised",
        QPalette.ColorRole.ToolTipText: "text",
        QPalette.ColorRole.Text: "text",
        QPalette.ColorRole.Button: "surface_raised",
        QPalette.ColorRole.ButtonText: "text",
        QPalette.ColorRole.BrightText: "accent_text",
        QPalette.ColorRole.Light: "surface_hover",
        QPalette.ColorRole.Midlight: "surface_raised",
        QPalette.ColorRole.Mid: "border",
        QPalette.ColorRole.Dark: "border_strong",
        QPalette.ColorRole.Shadow: "window",
        QPalette.ColorRole.Highlight: "accent",
        QPalette.ColorRole.HighlightedText: "selection_text",
        QPalette.ColorRole.Link: "secondary",
        QPalette.ColorRole.LinkVisited: "accent",
        QPalette.ColorRole.PlaceholderText: "placeholder",
    }
    for role, token in roles.items():
        palette.setColor(role, QColor(colors[token]))

    for role in (
        QPalette.ColorRole.WindowText,
        QPalette.ColorRole.Text,
        QPalette.ColorRole.ButtonText,
        QPalette.ColorRole.PlaceholderText,
    ):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor(colors["text_disabled"]))
    palette.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.Button,
        QColor(colors["surface_alt"]),
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.Highlight,
        QColor(colors["border_strong"]),
    )
    return palette


def apply_application_theme(app, theme: str | None) -> str:
    """Apply a tokenized theme and return the resolved ``dark``/``light`` name."""
    if app is not None:
        _system_theme(app)
    resolved = resolve_theme(app, theme)
    if app is None:
        return resolved

    tokens = THEME_TOKENS[resolved]
    colors = tokens["colors"]
    app.setStyle("Fusion")
    app.setProperty("voxoraTheme", resolved)
    app.setProperty("voxoraIconForeground", colors["text"])
    app.setProperty("voxoraIconMuted", colors["text_muted"])
    app.setProperty("voxoraIconAccent", colors["accent_hover"])
    app.setProperty("voxoraIconDanger", colors["danger"])
    app.setProperty("voxoraIconContrast", colors["accent_text"])
    app.setProperty("voxoraIconDisabled", colors["text_disabled"])
    app.setPalette(_application_palette(colors))
    app.setStyleSheet(_stylesheet(resolved))

    # Theme-aware QIconEngine instances read the properties above.  Scheduling
    # a repaint makes already-mounted icons update in the same theme pass.
    try:
        for widget in app.allWidgets():
            refresh_icon = getattr(widget, "refresh_icon", None)
            if callable(refresh_icon):
                refresh_icon()
            widget.update()
    except (AttributeError, RuntimeError):
        pass
    return resolved


def _stylesheet(theme: str) -> str:
    t = THEME_TOKENS[resolve_theme(None, theme)]
    c = t["colors"]
    r = t["radius"]
    s = t["spacing"]
    h = t["control"]

    # Açılır kutu ve sayı kutusu okları: QSS alt-kontrolleri biçimlendirildiğinde
    # Qt kendi okunu çizmez; görsel verilmezse alanlar düz metin gibi görünür.
    suffix = "" if t["name"] == "dark" else "-light"
    combo_arrow = asset_path(f"spin-down{suffix}.svg").replace("\\", "/")
    spin_up_arrow = asset_path(f"spin-up{suffix}.svg").replace("\\", "/")
    spin_down_arrow = asset_path(f"spin-down{suffix}.svg").replace("\\", "/")

    return f"""
    * {{
        font-family: "Segoe UI Variable Text", "Segoe UI";
        font-size: 10pt;
    }}
    QWidget {{
        color: {c['text']};
        selection-background-color: {c['selection']};
        selection-color: {c['selection_text']};
    }}
    QWidget:disabled {{ color: {c['text_disabled']}; }}
    QMainWindow, QDialog, QMessageBox {{
        background: {c['window']};
        color: {c['text']};
    }}
    QWidget#appShell, QWidget#pageRoot {{ background: {c['window']}; }}
    QWidget#pageBody, QStackedWidget#workspacePages, QStackedWidget#pageActionStack {{
        background: transparent;
        border: none;
    }}
    QStackedWidget {{ background: transparent; border: none; }}

    /* Sidebar and brand lockup */
    QFrame#sidebar {{
        background: {c['sidebar']};
        border: none;
        border-right: 1px solid {c['divider']};
    }}
    QLabel#brandTitle {{
        color: {c['text']};
        font-size: 11pt;
        font-weight: 750;
    }}
    QLabel#brandSubtitle, QLabel#sidebarAttribution {{
        color: {c['text_muted']};
        font-size: 8pt;
        font-weight: 600;
    }}
    QPushButton[nav="true"] {{
        background: transparent;
        color: {c['text_muted']};
        border: 1px solid transparent;
        border-radius: {r['medium']}px;
        padding: {s['md'] - 2}px {s['sm'] + 1}px;
        text-align: left;
        font-weight: 650;
    }}
    QPushButton[nav="true"]:hover {{
        background: {c['sidebar_hover']};
        color: {c['text']};
        border-color: {c['border']};
    }}
    QPushButton[nav="true"]:pressed {{ background: {c['surface_hover']}; }}
    QPushButton[nav="true"]:focus {{ border-color: {c['focus']}; }}
    QPushButton[nav="true"]:checked {{
        background: {c['sidebar_active']};
        color: {c['accent_hover']};
        border-color: {c['accent_border']};
        border-left: 3px solid {c['accent']};
    }}
    QPushButton[nav="true"][collapsed="true"] {{
        padding: 0;
        text-align: center;
    }}
    QPushButton[nav="true"][collapsed="true"]:checked {{
        border-left: 1px solid {c['accent_border']};
        border-bottom: 3px solid {c['accent']};
    }}
    QPushButton[collapsed="true"] {{ padding: 0; }}

    /* Üst sekmeler (topnav) */
    QFrame#topNav {{ background: transparent; border: none; }}
    QPushButton[topnav="true"] {{
        background: transparent;
        color: {c['text_muted']};
        border: 1px solid transparent;
        border-radius: {r['medium']}px;
        padding: 7px {s['lg']}px;
        font-weight: 650;
    }}
    QPushButton[topnav="true"]:hover {{
        background: {c['sidebar_hover']};
        color: {c['text']};
    }}
    QPushButton[topnav="true"]:checked {{
        background: {c['sidebar_active']};
        color: {c['text']};
        border: 1px solid {c['accent_border']};
        border-bottom: 2px solid {c['accent']};
    }}

    /* İkincil iç navigasyon (Araçlar / Ayarlar sol menüleri) */
    QPushButton[subnav="true"] {{
        background: transparent;
        color: {c['text_muted']};
        border: 1px solid transparent;
        border-radius: {r['small']}px;
        padding: 8px 10px;
        text-align: left;
        font-weight: 650;
    }}
    QPushButton[subnav="true"]:hover {{
        background: {c['sidebar_hover']};
        color: {c['text']};
        border-color: {c['border']};
    }}
    QPushButton[subnav="true"]:checked {{
        background: {c['accent_soft']};
        color: {c['accent_hover']};
        border-color: {c['accent_border']};
    }}

    /* Typography and reusable surfaces */
    QLabel {{ background: transparent; color: {c['text']}; }}
    QLabel[muted="true"], QLabel#cardSubtitle, QLabel#pageSubtitle,
    QLabel#dialogSubtitle, QLabel#dialogStatus {{ color: {c['text_muted']}; }}
    QLabel#pageTitle {{
        color: {c['text']};
        font-size: 22pt;
        font-weight: 760;
    }}
    QLabel#pageSubtitle {{ font-size: 10pt; }}
    QLabel#cardTitle {{ color: {c['text']}; font-size: 12pt; font-weight: 700; }}
    QLabel#cardSubtitle {{ font-size: 9pt; }}
    QLabel#dialogTitle {{ color: {c['text']}; font-size: 15pt; font-weight: 750; }}
    QLabel#dialogGuidance {{ color: {c['text_secondary']}; }}
    QFrame#pageHeader, QWidget#pageHeaderActions {{ background: transparent; border: none; }}
    QFrame#sectionCard, QGroupBox {{
        background: {c['surface']};
        border: 1px solid {c['border']};
        border-radius: {r['card']}px;
    }}
    QGroupBox {{
        margin-top: 14px;
        padding: 18px 14px 14px 14px;
        font-weight: 700;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        subcontrol-position: top left;
        left: 14px;
        padding: 0 7px;
        color: {c['text']};
        background: {c['surface']};
    }}
    QFrame#waveformView, QWidget#waveformView {{
        background: {c['surface_alt']};
        border: 1px solid {c['border']};
        border-radius: {r['large']}px;
    }}

    /* Semantic status pills */
    QLabel#statusPill {{
        color: {c['text_secondary']};
        background: {c['surface_raised']};
        border: 1px solid {c['border']};
        border-radius: 12px;
        padding: 2px 9px;
        font-size: 8.5pt;
        font-weight: 700;
    }}
    QLabel#statusPill[tone="info"] {{ color: {c['info']}; background: {c['info_soft']}; border-color: {c['info_border']}; }}
    QLabel#statusPill[tone="success"] {{ color: {c['success']}; background: {c['success_soft']}; border-color: {c['success_border']}; }}
    QLabel#statusPill[tone="warning"] {{ color: {c['warning']}; background: {c['warning_soft']}; border-color: {c['warning_border']}; }}
    QLabel#statusPill[tone="danger"] {{ color: {c['danger']}; background: {c['danger_soft']}; border-color: {c['danger_border']}; }}

    /* Buttons: secondary is the safe default */
    QPushButton, QToolButton {{
        min-height: {h['medium_height'] - 18}px;
        padding: {s['sm']}px {s['lg'] - 2}px;
        color: {c['text']};
        background: {c['surface_raised']};
        border: 1px solid {c['border']};
        border-radius: {r['medium']}px;
        font-weight: 650;
    }}
    QPushButton:hover, QToolButton:hover {{
        color: {c['text']};
        background: {c['surface_hover']};
        border-color: {c['border_strong']};
    }}
    QPushButton:pressed, QToolButton:pressed {{
        background: {c['surface_alt']};
        border-color: {c['accent_border']};
        padding-top: 9px;
        padding-bottom: 7px;
    }}
    QPushButton:focus, QToolButton:focus {{ border: 2px solid {c['focus']}; }}
    QPushButton:disabled, QToolButton:disabled {{
        color: {c['text_disabled']};
        background: {c['surface_alt']};
        border-color: {c['border']};
    }}
    QPushButton#actionButton[size="small"] {{ min-height: {h['small_height'] - 14}px; padding: 6px 10px; font-size: 9pt; }}
    QPushButton#actionButton[size="large"] {{ min-height: {h['large_height'] - 18}px; padding: 10px 18px; font-size: 10.5pt; }}

    QPushButton#actionButton[variant="primary"],
    QPushButton[buttonRole="primary"], QPushButton[primary="true"] {{
        color: {c['accent_text']};
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 {c['accent']}, stop:1 {c['secondary']});
        border: 1px solid {c['accent_hover']};
        font-weight: 750;
    }}
    QPushButton#actionButton[variant="primary"]:hover,
    QPushButton[buttonRole="primary"]:hover, QPushButton[primary="true"]:hover {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 {c['accent_hover']}, stop:1 {c['secondary_hover']});
        border: 2px solid {c['accent_hover']};
    }}
    QPushButton#actionButton[variant="primary"]:pressed,
    QPushButton[buttonRole="primary"]:pressed, QPushButton[primary="true"]:pressed {{
        background: {c['accent_pressed']};
        border-color: {c['accent_pressed']};
    }}
    QPushButton#actionButton[variant="primary"]:focus,
    QPushButton[buttonRole="primary"]:focus, QPushButton[primary="true"]:focus {{
        border: 2px solid {c['accent_text']};
    }}
    QPushButton#actionButton[variant="secondary"], QPushButton[buttonRole="secondary"] {{
        color: {c['text']};
        background: {c['surface_raised']};
        border-color: {c['border_strong']};
    }}
    QPushButton#actionButton[variant="secondary"]:hover, QPushButton[buttonRole="secondary"]:hover {{
        color: {c['accent_hover']};
        background: {c['accent_soft']};
        border-color: {c['accent_border']};
    }}
    QPushButton#actionButton[variant="ghost"], QPushButton[buttonRole="ghost"] {{
        color: {c['text_secondary']};
        background: transparent;
        border-color: transparent;
    }}
    QPushButton#actionButton[variant="ghost"]:hover, QPushButton[buttonRole="ghost"]:hover {{
        color: {c['text']};
        background: {c['surface_hover']};
        border-color: {c['border']};
    }}
    QPushButton#actionButton[variant="icon"], QPushButton[buttonRole="icon"] {{
        min-width: {h['medium_height']}px;
        max-width: {h['medium_height']}px;
        padding: 0;
        background: transparent;
        border-color: transparent;
    }}
    QPushButton#actionButton[variant="icon"][size="small"] {{
        min-width: {h['small_height']}px;
        max-width: {h['small_height']}px;
    }}
    QPushButton#actionButton[variant="icon"][size="large"] {{
        min-width: {h['large_height']}px;
        max-width: {h['large_height']}px;
    }}
    QPushButton#actionButton[variant="icon"]:hover, QPushButton[buttonRole="icon"]:hover {{
        background: {c['surface_hover']};
        border-color: {c['border']};
    }}
    QPushButton#actionButton[variant="destructive"], QPushButton[buttonRole="destructive"],
    QPushButton[danger="true"] {{
        color: {c['danger']};
        background: {c['danger_soft']};
        border-color: {c['danger_border']};
    }}
    QPushButton#actionButton[variant="destructive"]:hover,
    QPushButton[buttonRole="destructive"]:hover, QPushButton[danger="true"]:hover {{
        color: {c['accent_text']};
        background: {c['danger_hover']};
        border-color: {c['danger_hover']};
    }}
    QPushButton#actionButton[variant="destructive"]:pressed,
    QPushButton[buttonRole="destructive"]:pressed, QPushButton[danger="true"]:pressed {{
        color: {c['accent_text']};
        background: {c['danger_pressed']};
        border-color: {c['danger_pressed']};
    }}
    QPushButton#actionButton[variant="secondary"]:focus,
    QPushButton#actionButton[variant="ghost"]:focus,
    QPushButton#actionButton[variant="icon"]:focus,
    QPushButton#actionButton[variant="destructive"]:focus,
    QPushButton[buttonRole="secondary"]:focus,
    QPushButton[buttonRole="ghost"]:focus,
    QPushButton[buttonRole="icon"]:focus,
    QPushButton[buttonRole="destructive"]:focus,
    QPushButton[danger="true"]:focus {{ border: 2px solid {c['focus']}; }}
    QPushButton#actionButton:disabled,
    QPushButton[buttonRole="primary"]:disabled,
    QPushButton[buttonRole="secondary"]:disabled,
    QPushButton[buttonRole="ghost"]:disabled,
    QPushButton[buttonRole="icon"]:disabled,
    QPushButton[buttonRole="destructive"]:disabled,
    QPushButton[primary="true"]:disabled, QPushButton[danger="true"]:disabled {{
        color: {c['text_disabled']};
        background: {c['surface_alt']};
        border: 1px solid {c['border']};
    }}
    QPushButton[busy="true"] {{
        color: {c['text_muted']};
        background: {c['surface_raised']};
        border-color: {c['border_strong']};
    }}
    QPushButton#actionButton[busy="true"][variant="primary"],
    QPushButton[busy="true"][buttonRole="primary"] {{
        color: {c['accent_text']};
        background: {c['accent_pressed']};
        border: 1px solid {c['accent_border']};
    }}

    /* Text, list and numeric controls */
    QTextEdit, QPlainTextEdit, QLineEdit, QListWidget, QTreeWidget, QTableWidget,
    QComboBox, QSpinBox, QDoubleSpinBox {{
        color: {c['text']};
        background: {c['surface_alt']};
        border: 1px solid {c['border']};
        border-radius: {r['medium']}px;
        padding: {s['sm']}px {s['md'] - 2}px;
    }}
    QTextEdit:hover, QPlainTextEdit:hover, QLineEdit:hover, QListWidget:hover,
    QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover {{ border-color: {c['border_strong']}; }}
    QTextEdit:focus, QPlainTextEdit:focus, QLineEdit:focus, QListWidget:focus,
    QTreeWidget:focus, QTableWidget:focus, QComboBox:focus, QSpinBox:focus,
    QDoubleSpinBox:focus {{ border: 2px solid {c['focus']}; }}
    QTextEdit:disabled, QPlainTextEdit:disabled, QLineEdit:disabled, QListWidget:disabled,
    QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled {{
        color: {c['text_disabled']};
        background: {c['surface']};
        border-color: {c['divider']};
    }}
    QListWidget::item, QTreeWidget::item {{
        color: {c['text_secondary']};
        padding: 9px 8px;
        border: none;
        border-bottom: 1px solid {c['divider']};
    }}
    QListWidget::item:hover, QTreeWidget::item:hover {{ background: {c['surface_hover']}; color: {c['text']}; }}
    QListWidget::item:selected, QTreeWidget::item:selected {{
        background: {c['selection']};
        color: {c['selection_text']};
        border-radius: {r['small']}px;
    }}
    QComboBox {{ padding-right: 30px; }}
    QComboBox::drop-down {{ border: none; width: 28px; }}
    QComboBox::down-arrow {{ image: url("{combo_arrow}"); width: 10px; height: 7px; }}
    QComboBox QAbstractItemView {{
        color: {c['text']};
        background: {c['surface_raised']};
        border: 1px solid {c['border_strong']};
        border-radius: {r['small']}px;
        padding: 5px;
        selection-background-color: {c['selection']};
        selection-color: {c['selection_text']};
    }}
    QSpinBox, QDoubleSpinBox {{ padding-right: 29px; }}
    QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
        image: url("{spin_up_arrow}");
        width: 10px;
        height: 7px;
    }}
    QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
        image: url("{spin_down_arrow}");
        width: 10px;
        height: 7px;
    }}
    QSpinBox::up-button, QSpinBox::down-button,
    QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
        subcontrol-origin: border;
        width: 25px;
        background: {c['surface']};
        border-left: 1px solid {c['border']};
    }}
    QSpinBox::up-button, QDoubleSpinBox::up-button {{
        subcontrol-position: top right;
        border-top-right-radius: {r['small']}px;
        border-bottom: 1px solid {c['border']};
    }}
    QSpinBox::down-button, QDoubleSpinBox::down-button {{
        subcontrol-position: bottom right;
        border-bottom-right-radius: {r['small']}px;
    }}
    QSpinBox::up-button:hover, QSpinBox::down-button:hover,
    QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover {{ background: {c['surface_hover']}; }}

    QCheckBox, QRadioButton {{ color: {c['text_secondary']}; spacing: 8px; }}
    QCheckBox:hover, QRadioButton:hover {{ color: {c['text']}; }}
    QCheckBox:disabled, QRadioButton:disabled {{ color: {c['text_disabled']}; }}
    QSlider::groove:horizontal {{ height: 5px; background: {c['surface_raised']}; border-radius: 2px; }}
    QSlider::sub-page:horizontal {{ background: {c['accent']}; border-radius: 2px; }}
    QSlider::handle:horizontal {{
        width: 16px;
        margin: -6px 0;
        background: {c['text']};
        border: 2px solid {c['accent']};
        border-radius: 8px;
    }}
    QSlider::handle:horizontal:hover {{ background: {c['accent_hover']}; border-color: {c['accent_hover']}; }}

    /* Progress, scrolling and menus */
    QProgressBar, QProgressBar#dialogProgress {{
        min-height: 9px;
        max-height: 9px;
        color: transparent;
        background: {c['surface_raised']};
        border: none;
        border-radius: 4px;
        text-align: center;
    }}
    QProgressBar::chunk {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 {c['accent']}, stop:1 {c['secondary']});
        border-radius: 4px;
    }}
    QScrollArea, QAbstractScrollArea::viewport {{ background: transparent; border: none; }}
    QScrollBar:vertical {{ background: transparent; width: 11px; margin: 3px; }}
    QScrollBar:horizontal {{ background: transparent; height: 11px; margin: 3px; }}
    QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
        background: {c['scrollbar']};
        border-radius: 4px;
        min-height: 30px;
        min-width: 30px;
    }}
    QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {{ background: {c['scrollbar_hover']}; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
    QMenu {{
        color: {c['text']};
        background: {c['surface_raised']};
        border: 1px solid {c['border_strong']};
        border-radius: {r['medium']}px;
        padding: {s['xs']}px;
    }}
    QMenu::item {{ padding: 7px 24px 7px 10px; border-radius: {r['small']}px; }}
    QMenu::item:selected {{ background: {c['selection']}; color: {c['selection_text']}; }}
    QMenu::separator {{ height: 1px; background: {c['divider']}; margin: 5px 8px; }}

    /* Warnings, dialogs and status chrome */
    QFrame#voiceWarningPanel {{
        background: {c['warning_soft']};
        border: 1px solid {c['warning_border']};
        border-radius: {r['large']}px;
    }}
    QFrame#voiceWarningPanel QLabel {{ color: {c['warning']}; }}
    QFrame#voiceWarningPanel QLabel#warningTitle {{ font-weight: 750; }}
    QDialog#modelLoadDialog, QDialog#voiceGuideDialog, QDialog#synthesisDialog {{
        background: {c['window']};
    }}
    QFrame#sectionCard[context="dialogBody"], QWidget#dialogBody,
    QFrame#dialogDetails, QPlainTextEdit#dialogDetails {{
        color: {c['text_secondary']};
        background: {c['surface']};
        border: 1px solid {c['border']};
        border-radius: {r['large']}px;
    }}
    QFrame#dialogActions, QWidget#dialogActions {{ background: transparent; border: none; }}
    QMessageBox QLabel {{ color: {c['text']}; min-width: 260px; }}
    QFrame#statusBar {{
        background: {c['surface']};
        border: none;
        border-top: 1px solid {c['divider']};
    }}
    QLabel#statusMessage {{ color: {c['text_secondary']}; }}
    QStatusBar {{ color: {c['text_muted']}; background: {c['surface']}; border-top: 1px solid {c['divider']}; }}
    QToolTip {{
        color: {c['text']};
        background: {c['surface_raised']};
        border: 1px solid {c['border_strong']};
        border-radius: {r['small']}px;
        padding: 6px 8px;
    }}
    """


def _repolish(widget) -> None:
    try:
        style = widget.style()
        if style is not None:
            style.unpolish(widget)
            style.polish(widget)
        widget.update()
    except (AttributeError, RuntimeError):
        pass


def mark_muted(label, muted: bool = True) -> None:
    label.setProperty("muted", bool(muted))
    _repolish(label)


def mark_button(button, variant: str = "secondary") -> None:
    """Apply a semantic variant to a plain ``QPushButton``."""
    normalized = "destructive" if variant == "danger" else variant
    if normalized not in {"primary", "secondary", "ghost", "icon", "destructive"}:
        raise ValueError(f"Unknown button variant: {variant!r}")
    button.setProperty("variant", normalized)
    button.setProperty("buttonRole", normalized)
    # Transitional properties preserve older selectors and call sites.
    button.setProperty("primary", normalized == "primary")
    button.setProperty("danger", normalized == "destructive")
    _repolish(button)


def mark_primary(button) -> None:
    mark_button(button, "primary")


def mark_secondary(button) -> None:
    mark_button(button, "secondary")


def mark_ghost(button) -> None:
    mark_button(button, "ghost")


def mark_icon(button) -> None:
    mark_button(button, "icon")


def mark_danger(button) -> None:
    mark_button(button, "destructive")


mark_destructive = mark_danger


def mark_busy(button, busy: bool = True) -> None:
    button.setProperty("busy", bool(busy))
    _repolish(button)


__all__ = [
    "ACCENT",
    "ACCENT_SECONDARY",
    "DARK_THEME_TOKENS",
    "LIGHT_THEME_TOKENS",
    "THEME_TOKENS",
    "action_icon",
    "application_icon",
    "apply_application_theme",
    "apply_icon",
    "asset_path",
    "button_icon",
    "current_theme",
    "mark_busy",
    "mark_button",
    "mark_danger",
    "mark_destructive",
    "mark_ghost",
    "mark_icon",
    "mark_muted",
    "mark_primary",
    "mark_secondary",
    "menu_icon",
    "navigation_icon",
    "resolve_theme",
    "theme_tokens",
    "ui_icon",
]
