"""Central visual theme and reusable UI styling for txttoTTS."""
from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtGui import QColor, QIcon, QPalette, QPixmap

ACCENT = "#7c5cff"


def asset_path(filename: str) -> str:
    """Return an asset path that works in source and PyInstaller builds."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base = Path(sys._MEIPASS) / "app" / "assets"
    else:
        base = Path(__file__).resolve().parent / "assets"
    return str(base / filename)


def application_icon() -> QIcon:
    """Return the shared txttoTTS brand icon."""
    return QIcon(asset_path("txttotts-logo.png"))


_NAV_PATHS = {
    "generate": '<path d="M12 2l1.3 4.2L17.5 7.5l-4.2 1.3L12 13l-1.3-4.2L6.5 7.5l4.2-1.3L12 2Z"/><path d="M18.5 14l.8 2.7 2.7.8-2.7.8-.8 2.7-.8-2.7-2.7-.8 2.7-.8.8-2.7Z"/>',
    "history": '<circle cx="12" cy="12" r="8"/><path d="M12 7v5l3 2"/>',
    "compress": '<path d="M8 3v5H3M16 3v5h5M8 21v-5H3M16 21v-5h5"/><path d="M8 8 4 4M16 8l4-4M8 16l-4 4M16 16l4 4"/>',
    "settings": '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06-2.83 2.83-.06-.06A1.7 1.7 0 0 0 15 19.4a1.7 1.7 0 0 0-1 .6 1.7 1.7 0 0 0-.4 1.1V21h-4v-.09A1.7 1.7 0 0 0 8.6 19.4a1.7 1.7 0 0 0-1.88.34l-.06.06-2.83-2.83.06-.06A1.7 1.7 0 0 0 4.6 15a1.7 1.7 0 0 0-.6-1 1.7 1.7 0 0 0-1.1-.4H3v-4h.09A1.7 1.7 0 0 0 4.6 8.6a1.7 1.7 0 0 0-.34-1.88l-.06-.06 2.83-2.83.06.06A1.7 1.7 0 0 0 9 4.6a1.7 1.7 0 0 0 1-.6 1.7 1.7 0 0 0 .4-1.1V3h4v.09A1.7 1.7 0 0 0 15.4 4.6a1.7 1.7 0 0 0 1.88-.34l.06-.06 2.83 2.83-.06.06A1.7 1.7 0 0 0 19.4 9c.14.37.36.71.66 1 .3.29.68.48 1.1.54H21v4h-.09A1.7 1.7 0 0 0 19.4 15Z"/>',
    "menu": '<path d="M4 7h16M4 12h16M4 17h16"/>',
}


def _line_icon(path_data: str, color: str) -> QPixmap:
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">{path_data}</svg>'''
    pixmap = QPixmap()
    pixmap.loadFromData(svg.encode("utf-8"), "SVG")
    return pixmap


def navigation_icon(name: str) -> QIcon:
    """Return a crisp icon with separate normal and selected colors."""
    path_data = _NAV_PATHS[name]
    icon = QIcon()
    icon.addPixmap(_line_icon(path_data, "#aeb5c5"), QIcon.Mode.Normal, QIcon.State.Off)
    icon.addPixmap(_line_icon(path_data, "#d8d0ff"), QIcon.Mode.Normal, QIcon.State.On)
    return icon


def menu_icon() -> QIcon:
    return QIcon(_line_icon(_NAV_PATHS["menu"], "#d8d0ff"))

def apply_application_theme(app, theme: str) -> str:
    """Apply a light, dark or system-derived theme."""
    app.setStyle("Fusion")
    if theme == "system":
        theme = "dark" if app.palette().color(QPalette.ColorRole.Window).lightness() < 128 else "light"
    if theme not in {"light", "dark"}:
        theme = "light"
    dark = theme == "dark"
    colors = {
        "window": "#0b0d12" if dark else "#f3f5fa",
        "base": "#11141b" if dark else "#ffffff",
        "alt": "#181c25" if dark else "#edf0f7",
        "text": "#f4f5f8" if dark else "#191c24",
        "button": "#1b202b" if dark else "#ffffff",
        "highlight": ACCENT if dark else "#6547e8",
    }
    palette = QPalette()
    for role, key in (
        (QPalette.ColorRole.Window, "window"), (QPalette.ColorRole.Base, "base"),
        (QPalette.ColorRole.AlternateBase, "alt"), (QPalette.ColorRole.Button, "button"),
        (QPalette.ColorRole.WindowText, "text"), (QPalette.ColorRole.Text, "text"),
        (QPalette.ColorRole.ButtonText, "text"), (QPalette.ColorRole.Highlight, "highlight"),
    ):
        palette.setColor(role, QColor(colors[key]))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(colors["alt"]))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(colors["text"]))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor("#737988"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor("#737988"))
    app.setPalette(palette)
    app.setStyleSheet(_stylesheet(theme))
    return theme


def _stylesheet(theme: str) -> str:
    dark = theme == "dark"
    bg = "#0b0d12" if dark else "#f3f5fa"
    surface = "#12151d" if dark else "#ffffff"
    surface_2 = "#191d27" if dark else "#f6f7fb"
    border = "#292e3b" if dark else "#dfe3ec"
    text = "#f4f5f8" if dark else "#191c24"
    muted = "#9ba3b4" if dark else "#667085"
    hover = "#242938" if dark else "#e9eaf5"
    danger = "#ff5d73" if dark else "#d92d4a"
    spin_up = asset_path("spin-up.svg").replace("\\", "/")
    spin_down = asset_path("spin-down.svg").replace("\\", "/")
    return f"""
    * {{ font-family: 'Segoe UI'; font-size: 10pt; }}
    QMainWindow, QDialog {{ background: {bg}; color: {text}; }}
    QWidget#appShell, QWidget#pageRoot {{ background: {bg}; }}
    QFrame#sidebar {{ background: #0f1118; border-right: 1px solid {border}; }}
    QLabel#brandTitle {{ font-size: 10pt; font-weight: 700; color: #ffffff; }}
    QLabel#brandSubtitle {{ color: {muted}; font-size: 8pt; }}
    QLabel[muted="true"] {{ color: {muted}; }}
    QLabel#pageTitle {{ font-size: 20pt; font-weight: 700; color: {text}; }}
    QLabel#pageSubtitle {{ color: {muted}; }}
    QPushButton {{ background: {surface_2}; color: {text}; border: 1px solid {border}; border-radius: 8px; padding: 8px 13px; min-height: 18px; }}
    QPushButton:hover {{ background: {hover}; border-color: #484f62; }}
    QPushButton:pressed {{ background: #30364a; }}
    QPushButton:disabled {{ color: #737988; background: {surface}; border-color: {border}; }}
    QPushButton[primary="true"] {{ background: {ACCENT}; color: white; border-color: {ACCENT}; font-weight: 700; }}
    QPushButton[primary="true"]:hover {{ background: #8c73ff; border-color: #8c73ff; }}
    QPushButton[danger="true"] {{ color: {danger}; }}
    QPushButton[nav="true"] {{ background: transparent; border: none; text-align: left; color: #aeb5c5; padding: 11px 6px; font-weight: 600; }}
    QPushButton[nav="true"]:hover {{ background: #191d28; color: white; }}
    QPushButton[nav="true"]:checked {{ background: #25203d; color: #cfc5ff; border-left: 3px solid {ACCENT}; }}
    QPushButton[nav="true"][collapsed="true"] {{ text-align: center; padding: 0; border-radius: 8px; }}
    QPushButton[nav="true"][collapsed="true"]:checked {{ background: #25203d; border-left: none; border-bottom: 2px solid {ACCENT}; }}
    QPushButton[collapsed="true"] {{ padding: 0; }}
    QGroupBox {{ background: {surface}; border: 1px solid {border}; border-radius: 12px; margin-top: 12px; padding: 18px 14px 14px; font-weight: 700; }}
    QGroupBox::title {{ subcontrol-origin: margin; left: 14px; padding: 0 6px; color: {text}; }}
    QTextEdit, QPlainTextEdit, QLineEdit, QListWidget, QComboBox, QDoubleSpinBox {{ background: {surface_2}; color: {text}; border: 1px solid {border}; border-radius: 8px; padding: 7px; selection-background-color: {ACCENT}; }}
    QTextEdit:focus, QPlainTextEdit:focus, QLineEdit:focus, QListWidget:focus, QComboBox:focus, QDoubleSpinBox:focus {{ border-color: {ACCENT}; }}
    QListWidget::item {{ padding: 9px; border-bottom: 1px solid {border}; }}
    QListWidget::item:selected {{ background: #332a57; color: white; border-radius: 5px; }}
    QComboBox::drop-down {{ border: none; width: 26px; }}
    QDoubleSpinBox {{ padding-right: 28px; }}
    QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
        subcontrol-origin: border; width: 24px; background: {surface};
        border-left: 1px solid {border};
    }}
    QDoubleSpinBox::up-button {{ subcontrol-position: top right; border-top-right-radius: 7px; border-bottom: 1px solid {border}; }}
    QDoubleSpinBox::down-button {{ subcontrol-position: bottom right; border-bottom-right-radius: 7px; }}
    QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover {{ background: {hover}; }}
    QDoubleSpinBox::up-arrow {{ image: url("{spin_up}"); width: 10px; height: 7px; }}
    QDoubleSpinBox::down-arrow {{ image: url("{spin_down}"); width: 10px; height: 7px; }}
    QProgressBar {{ background: {surface_2}; border: none; border-radius: 5px; height: 10px; text-align: center; }}
    QProgressBar::chunk {{ background: {ACCENT}; border-radius: 5px; }}
    QScrollArea {{ border: none; background: transparent; }}
    QScrollBar:vertical {{ background: transparent; width: 10px; margin: 3px; }}
    QScrollBar::handle:vertical {{ background: #454b5b; border-radius: 4px; min-height: 30px; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QFrame#statusBar {{ background: {surface}; border-top: 1px solid {border}; }}
    QFrame#voiceWarningPanel {{ background: #2b2416; border: 1px solid #735c20; border-radius: 10px; }}
    QFrame#voiceWarningPanel QLabel {{ color: #f2cf75; }}
    QToolTip {{ background: {surface_2}; color: {text}; border: 1px solid {border}; padding: 5px; }}
    """


def mark_muted(label) -> None:
    label.setProperty("muted", True)


def mark_primary(button) -> None:
    button.setProperty("primary", True)


def mark_danger(button) -> None:
    button.setProperty("danger", True)