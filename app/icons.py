"""Theme-aware, dependency-free SVG icons used by Voxora Studio.

The icon engine renders its SVG when Qt asks for a pixmap.  Existing widgets
therefore pick up a theme change without every caller having to replace its
``QIcon`` manually.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtCore import QRect, QSize
from PyQt6.QtGui import QIcon, QIconEngine, QPainter, QPixmap
from PyQt6.QtWidgets import QApplication


def asset_path(filename: str) -> str:
    """Return an asset path that works in source and PyInstaller builds."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base = Path(sys._MEIPASS) / "app" / "assets"
    else:
        base = Path(__file__).resolve().parent / "assets"
    return str(base / filename)


def application_icon() -> QIcon:
    """Return the shared Voxora Studio application icon."""
    return QIcon(asset_path("voxora-logo.png"))


# All artwork uses the same 24 px grid, round caps and 1.8 px stroke.  A small
# number of aliases keeps call sites expressive without duplicating artwork.
_ICON_PATHS: dict[str, str] = {
    "add": '<path d="M12 5v14M5 12h14"/>',
    "archive": '<rect x="3" y="5" width="18" height="4" rx="1"/><path d="M5 9v10h14V9M9 13h6"/>',
    "check": '<path d="m5 12 4 4L19 6"/>',
    "chevron-down": '<path d="m6 9 6 6 6-6"/>',
    "chevron-left": '<path d="m15 18-6-6 6-6"/>',
    "chevron-right": '<path d="m9 18 6-6-6-6"/>',
    "chevron-up": '<path d="m6 15 6-6 6 6"/>',
    "clean": '<path d="m3 17 6.5-6.5 4 4L7 21H3v-4Z"/><path d="m12 8 3-3 4 4-3 3M14 20h7"/>',
    "close": '<path d="M6 6l12 12M18 6 6 18"/>',
    "compress": '<path d="M8 3v5H3M16 3v5h5M8 21v-5H3M16 21v-5h5"/><path d="M8 8 4 4M16 8l4-4M8 16l-4 4M16 16l4 4"/>',
    "copy": '<rect x="8" y="8" width="11" height="11" rx="2"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/>',
    "delete": '<path d="M4 7h16M9 7V4h6v3M7 7l1 13h8l1-13M10 11v5M14 11v5"/>',
    "download": '<path d="M12 3v12m0 0 5-5m-5 5-5-5M5 20h14"/>',
    "file-add": '<path d="M6 3h8l4 4v14H6V3Z"/><path d="M14 3v5h4M9 14h6M12 11v6"/>',
    "file-audio": '<path d="M6 3h8l4 4v14H6V3Z"/><path d="M14 3v5h4M9 16v-3l5-1v3M9 16a1.5 1.5 0 1 1 0 3 1.5 1.5 0 0 1 0-3Zm5-1a1.5 1.5 0 1 1 0 3 1.5 1.5 0 0 1 0-3Z"/>',
    "folder": '<path d="M3 7h7l2 2h9v10H3V7Z"/><path d="M3 7V5h7l2 2"/>',
    "folder-open": '<path d="M3 7h7l2 2h9l-2 10H5L3 7Z"/><path d="M3 7V5h7l2 2"/>',
    "generate": '<path d="M12 2l1.3 4.2L17.5 7.5l-4.2 1.3L12 13l-1.3-4.2L6.5 7.5l4.2-1.3L12 2Z"/><path d="M18.5 14l.8 2.7 2.7.8-2.7.8-.8 2.7-.8-2.7-2.7-.8 2.7-.8.8-2.7Z"/>',
    "history": '<circle cx="12" cy="12" r="8"/><path d="M12 7v5l3 2M5.5 5.5 3 8V3"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7h.01"/>',
    "menu": '<path d="M4 7h16M4 12h16M4 17h16"/>',
    "microphone": '<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3M8 21h8"/>',
    "paste": '<rect x="6" y="5" width="13" height="16" rx="2"/><path d="M9 5V3h7v4H9V5ZM3 8v9a2 2 0 0 0 2 2h1"/>',
    "play": '<path d="m8 5 11 7-11 7V5Z"/>',
    "queue": '<path d="M4 6h11M4 12h11M4 18h8"/><path d="m18 15 3 3-3 3M21 18h-6"/>',
    "refresh": '<path d="M20 7v5h-5M4 17v-5h5"/><path d="M6.1 8.5A7 7 0 0 1 18.8 7M5.2 17A7 7 0 0 0 17.9 15.5"/>',
    "reset": '<path d="M4 4v6h6M20 20v-6h-6"/><path d="M5.5 15a8 8 0 0 0 13.2 2M18.5 9A8 8 0 0 0 5.3 7"/>',
    "save": '<path d="M5 3h12l2 2v16H5V3Z"/><path d="M8 3v6h8V3M8 21v-7h8v7"/>',
    "search": '<circle cx="11" cy="11" r="7"/><path d="m16 16 5 5"/>',
    "settings": '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06-2.83 2.83-.06-.06A1.7 1.7 0 0 0 15 19.4a1.7 1.7 0 0 0-1 .6 1.7 1.7 0 0 0-.4 1.1V21h-4v-.09A1.7 1.7 0 0 0 8.6 19.4a1.7 1.7 0 0 0-1.88.34l-.06.06-2.83-2.83.06-.06A1.7 1.7 0 0 0 4.6 15a1.7 1.7 0 0 0-.6-1 1.7 1.7 0 0 0-1.1-.4H3v-4h.09A1.7 1.7 0 0 0 4.6 8.6a1.7 1.7 0 0 0-.34-1.88l-.06-.06 2.83-2.83.06.06A1.7 1.7 0 0 0 9 4.6a1.7 1.7 0 0 0 1-.6 1.7 1.7 0 0 0 .4-1.1V3h4v.09A1.7 1.7 0 0 0 15.4 4.6a1.7 1.7 0 0 0 1.88-.34l.06-.06 2.83 2.83-.06.06A1.7 1.7 0 0 0 19.4 9c.14.37.36.71.66 1 .3.29.68.48 1.1.54H21v4h-.09A1.7 1.7 0 0 0 19.4 15Z"/>',
    "sliders": '<path d="M4 6h16M4 12h16M4 18h16"/><circle cx="9" cy="6" r="2"/><circle cx="15" cy="12" r="2"/><circle cx="7" cy="18" r="2"/>',
    "stop": '<rect x="6" y="6" width="12" height="12" rx="2"/>',
    "upload": '<path d="M12 16V4m0 0L7 9m5-5 5 5M5 20h14"/>',
    "volume": '<path d="M4 10v4h4l5 4V6l-5 4H4Z"/><path d="M16 9a4 4 0 0 1 0 6M18.5 6.5a8 8 0 0 1 0 11"/>',
    "warning": '<path d="M12 3 2.5 20h19L12 3Z"/><path d="M12 9v5M12 17h.01"/>',
    "waveform": '<path d="M3 12h2l1.5-5 3 10 3-13 3 16 2.5-8H21"/>',
}

_ALIASES = {
    "plus": "add",
    "trash": "delete",
    "remove": "delete",
    "x": "close",
    "open": "folder-open",
    "open-folder": "folder-open",
    "select-folder": "folder",
    "redo": "refresh",
    "regenerate": "refresh",
    "sparkles": "generate",
    "audio": "waveform",
    "record": "microphone",
    "import": "upload",
}

_DEFAULT_ICON_COLORS = {
    "foreground": "#E8ECF8",
    "muted": "#98A3BA",
    "accent": "#A78BFA",
    "danger": "#FF7389",
    "contrast": "#FFFFFF",
    "disabled": "#596276",
}


def available_icons() -> tuple[str, ...]:
    """Return canonical icon names, useful for development and tests."""
    return tuple(sorted(_ICON_PATHS))


def _canonical_name(name: str) -> str:
    normalized = str(name).strip().lower().replace("_", "-")
    normalized = _ALIASES.get(normalized, normalized)
    if normalized not in _ICON_PATHS:
        choices = ", ".join(available_icons())
        raise ValueError(f"Unknown Voxora icon {name!r}. Available icons: {choices}")
    return normalized


def _application_color(role: str) -> str:
    app = QApplication.instance()
    if app is not None:
        value = app.property(f"voxoraIcon{role.title()}")
        if isinstance(value, str) and value:
            return value
    return _DEFAULT_ICON_COLORS[role]


def _svg_pixmap(name: str, color: str, size: QSize, stroke_width: float) -> QPixmap:
    width = max(1, size.width())
    height = max(1, size.height())
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 24 24" fill="none" stroke="{color}" '
        f'stroke-width="{stroke_width:g}" stroke-linecap="round" '
        f'stroke-linejoin="round">{_ICON_PATHS[name]}</svg>'
    )
    pixmap = QPixmap()
    pixmap.loadFromData(svg.encode("utf-8"), "SVG")
    return pixmap


class _ThemeIconEngine(QIconEngine):
    """Small SVG icon engine whose colors follow application properties."""

    def __init__(
        self,
        name: str,
        role: str = "foreground",
        active_role: str = "accent",
        stroke_width: float = 1.8,
        explicit_color: str | None = None,
    ) -> None:
        super().__init__()
        self.name = name
        self.role = role
        self.active_role = active_role
        self.stroke_width = stroke_width
        self.explicit_color = explicit_color

    def clone(self) -> "_ThemeIconEngine":
        return _ThemeIconEngine(
            self.name,
            self.role,
            self.active_role,
            self.stroke_width,
            self.explicit_color,
        )

    def _color(self, mode: QIcon.Mode, state: QIcon.State) -> str:
        if mode == QIcon.Mode.Disabled:
            return _application_color("disabled")
        if self.explicit_color:
            return self.explicit_color
        if mode in {QIcon.Mode.Active, QIcon.Mode.Selected} or state == QIcon.State.On:
            return _application_color(self.active_role)
        return _application_color(self.role)

    def pixmap(self, size: QSize, mode: QIcon.Mode, state: QIcon.State) -> QPixmap:
        return _svg_pixmap(
            self.name,
            self._color(mode, state),
            size,
            self.stroke_width,
        )

    def paint(
        self,
        painter: QPainter,
        rect: QRect,
        mode: QIcon.Mode,
        state: QIcon.State,
    ) -> None:
        painter.drawPixmap(rect, self.pixmap(rect.size(), mode, state))


def action_icon(
    name: str,
    *,
    role: str = "foreground",
    active_role: str = "accent",
    color: str | None = None,
    stroke_width: float = 1.8,
) -> QIcon:
    """Create a crisp inline-SVG icon that follows the active app theme.

    ``role`` and ``active_role`` accept ``foreground``, ``muted``, ``accent``
    and ``danger``.  ``color`` opts into a fixed color for exceptional uses.
    """
    canonical = _canonical_name(name)
    allowed_roles = {"foreground", "muted", "accent", "danger", "contrast"}
    if role not in allowed_roles or active_role not in allowed_roles:
        raise ValueError(
            "Icon roles must be foreground, muted, accent, danger or contrast"
        )
    return QIcon(
        _ThemeIconEngine(
            canonical,
            role=role,
            active_role=active_role,
            stroke_width=stroke_width,
            explicit_color=color,
        )
    )


# ``ui_icon`` is the concise name used by reusable widget classes. Keep
# ``action_icon`` as the descriptive public spelling for call sites.
ui_icon = action_icon


def button_icon(name: str, variant: str = "secondary") -> QIcon:
    """Return an icon whose normal/hover colors match a button variant."""
    if variant == "primary":
        return action_icon(name, role="contrast", active_role="contrast")
    if variant in {"destructive", "danger"}:
        return action_icon(name, role="danger", active_role="contrast")
    return action_icon(name, role="foreground", active_role="accent")


def navigation_icon(name: str) -> QIcon:
    """Compatibility factory for sidebar icons."""
    return action_icon(name, role="muted", active_role="accent")


def menu_icon() -> QIcon:
    """Compatibility factory for the sidebar menu icon."""
    return action_icon("menu", role="foreground", active_role="accent")


def apply_icon(widget, name: str, *, size: int = 18, role: str = "foreground") -> QIcon:
    """Attach an action icon and its metadata to a Qt button-like widget."""
    icon = action_icon(name, role=role)
    widget.setIcon(icon)
    if hasattr(widget, "setIconSize"):
        widget.setIconSize(QSize(size, size))
    widget.setProperty("voxoraIcon", _canonical_name(name))
    return icon


__all__ = [
    "action_icon",
    "application_icon",
    "apply_icon",
    "asset_path",
    "available_icons",
    "button_icon",
    "menu_icon",
    "navigation_icon",
    "ui_icon",
]
