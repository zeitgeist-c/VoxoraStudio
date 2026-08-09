"""Reusable, theme-driven widgets used throughout Voxora Studio.

The widgets in this module deliberately keep visual decisions in the central
application stylesheet.  Object names and dynamic properties form the styling
contract, while the classes provide behavior, layout and accessibility.
"""
from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from typing import Any

from PyQt6.QtCore import (
    QEasingCurve,
    QEvent,
    QLineF,
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
    pyqtProperty,
)
from PyQt6.QtGui import QBrush, QColor, QFocusEvent, QIcon, QLinearGradient, QPainter, QPen
from PyQt6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QStyle,
    QStyleOption,
    QVBoxLayout,
    QWidget,
)

__all__ = [
    "ActionButton",
    "SectionCard",
    "PageHeader",
    "StatusPill",
    "WaveformView",
]


def _repolish(widget: QWidget) -> None:
    """Refresh selectors after a dynamic property changes."""
    style = widget.style()
    if style is not None:
        style.unpolish(widget)
        style.polish(widget)
    widget.update()


def _load_ui_icon(name: str | None) -> QIcon:
    """Resolve an SVG-backed UI icon while allowing icons.py to be optional.

    ``app.icons`` is intentionally imported lazily: source checkouts created
    before the icon module landed can still open the UI, and packaged builds do
    not fail solely because an optional glyph is unavailable.
    """
    if not name:
        return QIcon()
    try:
        from .icons import ui_icon

        icon = ui_icon(name)
    except (ImportError, AttributeError, KeyError, RuntimeError, TypeError, ValueError):
        return QIcon()
    return icon if isinstance(icon, QIcon) else QIcon()


class ActionButton(QPushButton):
    """A semantic button with consistent variants, sizes and busy state."""

    VARIANTS = frozenset({"primary", "secondary", "ghost", "icon", "destructive"})
    SIZES = frozenset({"small", "medium", "large"})
    _HEIGHTS = {"small": 30, "medium": 38, "large": 46}
    _ICON_SIZES = {"small": 15, "medium": 18, "large": 20}

    def __init__(
        self,
        text: str = "",
        parent: QWidget | None = None,
        *,
        variant: str = "secondary",
        size: str = "medium",
        icon_name: str | None = None,
    ) -> None:
        super().__init__(text, parent)
        self.setObjectName("actionButton")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._variant = "secondary"
        self._size = "medium"
        self._icon_name: str | None = None
        self._busy = False
        self._enabled_before_busy = True
        self._text_before_busy = text
        self._glow_strength = 0.0

        self._glow = QGraphicsDropShadowEffect(self)
        self._glow.setOffset(0, 3)
        self._glow.setBlurRadius(1)
        self._glow.setColor(QColor(124, 92, 255, 0))
        self._glow.setEnabled(False)
        self.setGraphicsEffect(self._glow)

        self._glow_animation = QPropertyAnimation(self, b"glowStrength", self)
        self._glow_animation.setDuration(160)
        self._glow_animation.setEasingCurve(QEasingCurve.Type.OutCubic)

        self.set_variant(variant)
        self.set_size(size)
        self.set_icon_name(icon_name)

    def variant(self) -> str:
        return self._variant

    def set_variant(self, variant: str) -> None:
        if variant not in self.VARIANTS:
            allowed = ", ".join(sorted(self.VARIANTS))
            raise ValueError(f"Unknown button variant {variant!r}; expected one of: {allowed}")
        self._variant = variant
        self.setProperty("variant", variant)
        # buttonRole keeps compatibility with existing and transitional QSS.
        self.setProperty("buttonRole", variant)
        if variant != "primary":
            self._set_glow_strength(0.0)
        self._apply_width_for_variant()
        _repolish(self)

    def size_name(self) -> str:
        return self._size

    def set_size(self, size: str) -> None:
        if size not in self.SIZES:
            allowed = ", ".join(sorted(self.SIZES))
            raise ValueError(f"Unknown button size {size!r}; expected one of: {allowed}")
        self._size = size
        self.setProperty("size", size)
        self.setMinimumHeight(self._HEIGHTS[size])
        side = self._ICON_SIZES[size]
        self.setIconSize(QSize(side, side))
        self._apply_width_for_variant()
        _repolish(self)

    def _apply_width_for_variant(self) -> None:
        if self._variant == "icon":
            width = self._HEIGHTS[self._size]
            self.setMinimumWidth(width)
            self.setMaximumWidth(width)
        else:
            self.setMinimumWidth(0)
            self.setMaximumWidth(16777215)

    def icon_name(self) -> str | None:
        return self._icon_name

    def set_icon_name(self, icon_name: str | None) -> None:
        self._icon_name = icon_name
        self.setProperty("iconName", icon_name or "")
        self.refresh_icon()

    def refresh_icon(self) -> None:
        """Reload the named icon after a light/dark palette transition."""
        self.setIcon(_load_ui_icon(getattr(self, "_icon_name", None)))

    def is_busy(self) -> bool:
        return self._busy

    def set_busy(self, busy: bool, text: str | None = None) -> None:
        """Enter or leave a disabled busy state without losing prior state."""
        busy = bool(busy)
        if busy == self._busy:
            if busy and text is not None:
                self.setText(text)
            return

        if busy:
            self._enabled_before_busy = self.isEnabled()
            self._text_before_busy = self.text()
            self._busy = True
            self.setProperty("busy", True)
            if text is not None:
                self.setText(text)
            super().setEnabled(False)
            self._animate_glow(0.0, immediate=True)
        else:
            self._busy = False
            self.setProperty("busy", False)
            self.setText(self._text_before_busy)
            super().setEnabled(self._enabled_before_busy)
            self._sync_glow()
        _repolish(self)

    @pyqtProperty(float)
    def glowStrength(self) -> float:  # noqa: N802 - Qt property naming convention
        return self._glow_strength

    @glowStrength.setter
    def glowStrength(self, value: float) -> None:  # noqa: N802
        self._set_glow_strength(value)

    def _set_glow_strength(self, value: float) -> None:
        strength = max(0.0, min(float(value), 1.0))
        if not self.isEnabled() or self._variant != "primary":
            strength = 0.0
        self._glow_strength = strength
        self._glow.setEnabled(strength > 0.01)
        self._glow.setBlurRadius(5.0 + 15.0 * strength)
        self._glow.setColor(QColor(124, 92, 255, round(105 * strength)))

    def _animate_glow(self, target: float, *, immediate: bool = False) -> None:
        if not self.isEnabled() or self._variant != "primary":
            target = 0.0
        self._glow_animation.stop()
        if immediate:
            self._set_glow_strength(target)
            return
        self._glow_animation.setStartValue(self._glow_strength)
        self._glow_animation.setEndValue(target)
        self._glow_animation.start()

    def _sync_glow(self) -> None:
        active = self.isEnabled() and self._variant == "primary" and (self.underMouse() or self.hasFocus())
        self._animate_glow(0.72 if active else 0.0)

    def enterEvent(self, event) -> None:  # noqa: N802
        super().enterEvent(event)
        self._sync_glow()

    def leaveEvent(self, event) -> None:  # noqa: N802
        super().leaveEvent(event)
        self._sync_glow()

    def focusInEvent(self, event: QFocusEvent) -> None:  # noqa: N802
        super().focusInEvent(event)
        self._sync_glow()

    def focusOutEvent(self, event: QFocusEvent) -> None:  # noqa: N802
        super().focusOutEvent(event)
        self._sync_glow()

    def changeEvent(self, event: QEvent) -> None:  # noqa: N802
        super().changeEvent(event)
        if not hasattr(self, "_glow_animation"):
            return
        if event.type() == QEvent.Type.EnabledChange:
            if not self.isEnabled():
                self._animate_glow(0.0, immediate=True)
            else:
                self._sync_glow()
        elif event.type() in {QEvent.Type.PaletteChange, QEvent.Type.StyleChange}:
            self.refresh_icon()


class SectionCard(QFrame):
    """A titled surface with a public layout for page-specific content."""

    def __init__(
        self,
        title: str = "",
        subtitle: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("sectionCard")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        self.root_layout = QVBoxLayout(self)
        self.root_layout.setContentsMargins(20, 18, 20, 20)
        self.root_layout.setSpacing(12)

        self.title_label = QLabel(title, self)
        self.title_label.setObjectName("cardTitle")
        self.title_label.setWordWrap(True)
        self.title_label.setVisible(bool(title))
        self.root_layout.addWidget(self.title_label)

        self.subtitle_label = QLabel(subtitle, self)
        self.subtitle_label.setObjectName("cardSubtitle")
        self.subtitle_label.setWordWrap(True)
        self.subtitle_label.setVisible(bool(subtitle))
        self.root_layout.addWidget(self.subtitle_label)

        self.content_layout = QVBoxLayout()
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(12)
        self.root_layout.addLayout(self.content_layout)

    def set_title(self, title: str) -> None:
        self.title_label.setText(title)
        self.title_label.setVisible(bool(title))

    def set_subtitle(self, subtitle: str) -> None:
        self.subtitle_label.setText(subtitle)
        self.subtitle_label.setVisible(bool(subtitle))

    def set_text(self, title: str, subtitle: str = "") -> None:
        """Update both card heading strings atomically."""
        self.set_title(title)
        self.set_subtitle(subtitle)


class PageHeader(QFrame):
    """A responsive title/subtitle block with an optional action area."""

    def __init__(
        self,
        title: str,
        subtitle: str = "",
        action: QWidget | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("pageHeader")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(18)

        copy = QVBoxLayout()
        copy.setContentsMargins(0, 0, 0, 0)
        copy.setSpacing(4)
        self.title_label = QLabel(title, self)
        self.title_label.setObjectName("pageTitle")
        self.title_label.setWordWrap(True)
        copy.addWidget(self.title_label)

        self.subtitle_label = QLabel(subtitle, self)
        self.subtitle_label.setObjectName("pageSubtitle")
        self.subtitle_label.setWordWrap(True)
        self.subtitle_label.setVisible(bool(subtitle))
        copy.addWidget(self.subtitle_label)
        root.addLayout(copy, stretch=1)

        self.actions = QWidget(self)
        self.actions.setObjectName("pageHeaderActions")
        self.actions_layout = QHBoxLayout(self.actions)
        self.actions_layout.setContentsMargins(0, 0, 0, 0)
        self.actions_layout.setSpacing(8)
        root.addWidget(self.actions, alignment=Qt.AlignmentFlag.AlignTop)
        self.actions.setVisible(False)
        if action is not None:
            self.add_action(action)

    def set_title(self, title: str) -> None:
        self.title_label.setText(title)

    def set_subtitle(self, subtitle: str) -> None:
        self.subtitle_label.setText(subtitle)
        self.subtitle_label.setVisible(bool(subtitle))

    def set_text(self, title: str, subtitle: str = "") -> None:
        """Update both navigation-dependent header strings atomically."""
        self.set_title(title)
        self.set_subtitle(subtitle)

    def add_action(self, action: QWidget) -> None:
        self.actions_layout.addWidget(action)
        self.actions.setVisible(True)


class StatusPill(QLabel):
    """Compact semantic status label styled through its ``tone`` property."""

    TONES = frozenset({"neutral", "info", "success", "warning", "danger"})

    def __init__(
        self,
        text: str = "",
        tone: str = "neutral",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(text, parent)
        self.setObjectName("statusPill")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(24)
        self._tone = "neutral"
        self.set_tone(tone)

    def tone(self) -> str:
        return self._tone

    def set_tone(self, tone: str) -> None:
        if tone not in self.TONES:
            allowed = ", ".join(sorted(self.TONES))
            raise ValueError(f"Unknown status tone {tone!r}; expected one of: {allowed}")
        self._tone = tone
        self.setProperty("tone", tone)
        _repolish(self)


class WaveformView(QWidget):
    """A static waveform preview with a deterministic empty-state pattern."""

    _MAX_STORED_SAMPLES = 16_384
    _PLACEHOLDER = (
        0.12, 0.20, 0.32, 0.48, 0.30, 0.56, 0.76, 0.44,
        0.62, 0.88, 0.52, 0.72, 0.40, 0.64, 0.34, 0.50,
        0.26, 0.42, 0.18, 0.30, 0.14, 0.24, 0.10, 0.16,
    )

    def __init__(self, data: Any = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("waveformView")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setMinimumHeight(84)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._samples: tuple[float, ...] = ()
        self.set_data(data)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(440, 96)

    def data(self) -> tuple[float, ...]:
        return self._samples

    def clear(self) -> None:
        self.set_data(None)

    def set_data(self, data: Any) -> None:
        samples = self._coerce_samples(data)
        if samples:
            peak = max(abs(sample) for sample in samples)
            if peak > 0.0:
                samples = [sample / peak for sample in samples]
        self._samples = tuple(samples)
        self.setProperty("hasData", bool(self._samples))
        _repolish(self)

    @classmethod
    def _coerce_samples(cls, data: Any) -> list[float]:
        if data is None or isinstance(data, (str, bytes, bytearray, Mapping)):
            return []

        value = data
        # Tensor-like values are detached and moved to CPU without importing
        # torch. Each operation is optional and failures fall back to iteration.
        for operation in ("detach", "cpu"):
            method = getattr(value, operation, None)
            if callable(method):
                try:
                    value = method()
                except (RuntimeError, TypeError, ValueError):
                    return []

        flatten = getattr(value, "reshape", None)
        if callable(flatten):
            try:
                value = flatten(-1)
            except (RuntimeError, TypeError, ValueError):
                pass

        total = cls._safe_length(value)
        if total and total > cls._MAX_STORED_SAMPLES and hasattr(value, "__getitem__"):
            step = max(1, math.ceil(total / cls._MAX_STORED_SAMPLES))
            try:
                value = value[::step]
            except (IndexError, RuntimeError, TypeError, ValueError):
                pass

        to_list = getattr(value, "tolist", None)
        if callable(to_list):
            try:
                value = to_list()
            except (RuntimeError, TypeError, ValueError):
                return []

        samples: list[float] = []
        iterators = [iter((value,))]
        inspected = 0
        inspection_limit = cls._MAX_STORED_SAMPLES * 8
        while iterators and len(samples) < cls._MAX_STORED_SAMPLES and inspected < inspection_limit:
            try:
                item = next(iterators[-1])
            except StopIteration:
                iterators.pop()
                continue
            except (RuntimeError, TypeError, ValueError):
                iterators.pop()
                continue
            inspected += 1
            if isinstance(item, (str, bytes, bytearray, Mapping)):
                continue
            if isinstance(item, Iterable):
                if len(iterators) >= 64:
                    continue
                try:
                    iterators.append(iter(item))
                except (RuntimeError, TypeError, ValueError):
                    pass
                continue
            scalar = getattr(item, "item", None)
            if callable(scalar):
                try:
                    item = scalar()
                except (RuntimeError, TypeError, ValueError):
                    continue
            try:
                sample = float(item)
            except (RuntimeError, TypeError, ValueError, OverflowError):
                continue
            samples.append(sample if math.isfinite(sample) else 0.0)
        return samples

    @staticmethod
    def _safe_length(value: Any) -> int | None:
        try:
            return len(value)
        except (RuntimeError, TypeError, ValueError, OverflowError):
            return None

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        option = QStyleOption()
        option.initFrom(self)
        self.style().drawPrimitive(QStyle.PrimitiveElement.PE_Widget, option, painter, self)

        bounds = QRectF(self.rect()).adjusted(14.0, 12.0, -14.0, -12.0)
        if bounds.width() <= 1.0 or bounds.height() <= 1.0:
            return

        center_y = bounds.center().y()
        guide = self.palette().color(self.foregroundRole())
        guide.setAlpha(32)
        painter.setPen(QPen(guide, 1.0))
        painter.drawLine(QLineF(bounds.left(), center_y, bounds.right(), center_y))

        if self._samples:
            amplitudes = self._bucket_amplitudes(self._samples, max(1, round(bounds.width())))
            accent = self.palette().highlight().color()
            opacity = 220
        else:
            amplitudes = self._PLACEHOLDER
            accent = self.palette().color(self.foregroundRole())
            opacity = 76

        gradient = QLinearGradient(bounds.left(), 0.0, bounds.right(), 0.0)
        first = QColor(accent)
        first.setAlpha(opacity)
        second = QColor(accent)
        second.setAlpha(max(28, opacity - 45))
        gradient.setColorAt(0.0, first)
        gradient.setColorAt(0.52, second)
        gradient.setColorAt(1.0, first)

        count = len(amplitudes)
        if count == 0:
            return
        gap = bounds.width() / count
        pen_width = max(1.2, min(3.0, gap * 0.58))
        painter.setPen(QPen(QBrush(gradient), pen_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        half_height = bounds.height() * 0.46
        for index, amplitude in enumerate(amplitudes):
            x = bounds.left() + (index + 0.5) * gap
            height = max(1.5, min(abs(amplitude), 1.0) * half_height)
            painter.drawLine(QLineF(x, center_y - height, x, center_y + height))

    @staticmethod
    def _bucket_amplitudes(samples: tuple[float, ...], target: int) -> list[float]:
        count = len(samples)
        target = min(max(1, target), count)
        if target == count:
            return [abs(sample) for sample in samples]
        amplitudes: list[float] = []
        for bucket in range(target):
            start = bucket * count // target
            end = max(start + 1, (bucket + 1) * count // target)
            amplitudes.append(max(abs(sample) for sample in samples[start:end]))
        return amplitudes
