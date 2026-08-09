"""Offscreen component and MainWindow smoke tests for Voxora Studio."""
from __future__ import annotations

import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QApplication, QLabel, QScrollArea
except ImportError as exc:  # pragma: no cover - exercised only in minimal environments
    QT_AVAILABLE = False
    QT_SKIP_REASON = f"PyQt6 kullanılamıyor: {exc}"
else:
    QT_AVAILABLE = True
    QT_SKIP_REASON = ""

    from app import main_window
    from app.icons import action_icon, application_icon, available_icons, ui_icon
    from app.main_window import MainWindow
    from app.theme import (
        apply_application_theme,
        current_theme,
        resolve_theme,
        theme_tokens,
    )
    from app.widgets import ActionButton, PageHeader, SectionCard, StatusPill, WaveformView


_APP = None


@unittest.skipUnless(QT_AVAILABLE, QT_SKIP_REASON)
class VoxoraUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global _APP
        _APP = QApplication.instance() or QApplication(["voxora-tests"])
        _APP.setQuitOnLastWindowClosed(False)
        cls.app = _APP

    def tearDown(self):
        apply_application_theme(self.app, "dark")
        self.app.processEvents()

    def test_known_icons_render_and_unknown_names_fail(self):
        expected = {"generate", "history", "compress", "settings", "play", "stop", "close"}
        self.assertTrue(expected.issubset(set(available_icons())))
        for name in expected:
            icon = action_icon(name)
            self.assertFalse(icon.isNull(), name)
            self.assertFalse(icon.pixmap(24, 24).isNull(), name)
        self.assertFalse(ui_icon("plus").pixmap(18, 18).isNull())
        with self.assertRaises(ValueError):
            action_icon("definitely-unknown")
        with self.assertRaises(ValueError):
            action_icon("play", role="invalid")

    def test_application_icon_is_populated(self):
        icon = application_icon()
        self.assertFalse(icon.isNull())
        self.assertFalse(icon.pixmap(32, 32).isNull())

    def test_action_button_variants_icons_and_busy_state(self):
        for variant in sorted(ActionButton.VARIANTS):
            button = ActionButton("Eylem", variant=variant, icon_name="play")
            self.assertEqual(button.variant(), variant)
            self.assertEqual(button.property("variant"), variant)
            self.assertFalse(button.icon().isNull())
            button.deleteLater()

        button = ActionButton("Ses Üret", variant="primary", size="large", icon_name="generate")
        self.assertEqual(button.size_name(), "large")
        button.set_busy(True, "Üretiliyor")
        self.assertTrue(button.is_busy())
        self.assertFalse(button.isEnabled())
        self.assertEqual(button.text(), "Üretiliyor")
        button.set_busy(False)
        self.assertFalse(button.is_busy())
        self.assertTrue(button.isEnabled())
        self.assertEqual(button.text(), "Ses Üret")
        with self.assertRaises(ValueError):
            button.set_variant("unknown")
        button.deleteLater()

    def test_card_header_and_status_contracts(self):
        card = SectionCard("Başlık", "Alt başlık")
        card.content_layout.addWidget(QLabel("İçerik"))
        self.assertEqual(card.title_label.text(), "Başlık")
        self.assertEqual(card.subtitle_label.text(), "Alt başlık")
        card.set_text("Yeni", "Açıklama")
        self.assertEqual(card.title_label.text(), "Yeni")

        action = ActionButton("Başlat", variant="primary")
        header = PageHeader("Sayfa", "Açıklama", action=action)
        self.assertFalse(header.actions.isHidden())
        header.set_text("Yeni Sayfa", "Yeni açıklama")
        self.assertEqual(header.title_label.text(), "Yeni Sayfa")
        self.assertEqual(header.subtitle_label.text(), "Yeni açıklama")

        for tone in sorted(StatusPill.TONES):
            pill = StatusPill("Durum", tone)
            self.assertEqual(pill.tone(), tone)
            self.assertEqual(pill.property("tone"), tone)
            pill.deleteLater()
        with self.assertRaises(ValueError):
            StatusPill("Durum", "unknown")
        card.deleteLater()
        header.deleteLater()

    def test_waveform_normalizes_real_data_and_clears(self):
        waveform = WaveformView([-2.0, 0.0, 1.0, float("nan")])
        self.assertEqual(waveform.data(), (-1.0, 0.0, 0.5, 0.0))
        self.assertTrue(waveform.property("hasData"))
        self.assertTrue(waveform.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents))
        waveform.clear()
        self.assertEqual(waveform.data(), ())
        self.assertFalse(waveform.property("hasData"))
        waveform.deleteLater()

    def test_theme_resolution_defaults_and_application(self):
        self.assertEqual(resolve_theme(None, None), "dark")
        self.assertEqual(resolve_theme(None, "unknown"), "dark")
        self.assertEqual(resolve_theme(None, " DARK "), "dark")
        self.assertEqual(resolve_theme(None, "light"), "light")
        self.assertIn(resolve_theme(self.app, "system"), {"dark", "light"})

        snapshot = theme_tokens(None)
        self.assertEqual(snapshot["name"], "dark")
        snapshot["colors"]["window"] = "changed"
        self.assertNotEqual(theme_tokens("dark")["colors"]["window"], "changed")

        self.assertEqual(apply_application_theme(self.app, None), "dark")
        self.assertEqual(current_theme(self.app), "dark")
        self.assertEqual(self.app.property("voxoraTheme"), "dark")
        self.assertTrue(self.app.styleSheet())
        self.assertEqual(apply_application_theme(self.app, "light"), "light")
        self.assertEqual(current_theme(self.app), "light")
        self.assertIn(apply_application_theme(self.app, "system"), {"dark", "light"})

    def test_main_window_headless_smoke(self):
        expected_titles = (
            "Ses Üretim Stüdyosu",
            "Üretim Arşivi",
            "Ses Sıkıştırma",
            "Stüdyo Ayarları",
        )
        with (
            patch.object(main_window, "load_settings", return_value={}) as load_settings,
            patch.object(main_window, "load_history", return_value=[]) as load_history,
            patch.object(main_window, "save_settings") as save_settings,
            patch.object(main_window, "save_history") as save_history,
            patch.object(main_window.audio_player, "stop"),
            patch.object(MainWindow, "_init_engine_async", autospec=True) as init_engine,
        ):
            window = MainWindow()
            self.assertEqual(window.windowTitle(), "Voxora Studio")
            self.assertEqual(window.pages.count(), 4)
            self.assertEqual(tuple(title for title, _ in window._page_meta), expected_titles)
            self.assertFalse(window.windowIcon().isNull())
            self.assertEqual(window._resolved_theme, "dark")
            self.assertEqual(window.theme_combo.currentData(), "dark")
            self.assertEqual(window.page_header.title_label.text(), expected_titles[0])
            load_settings.assert_called_once_with()
            load_history.assert_called_once_with()
            init_engine.assert_called_once_with(window)

            for index, title in enumerate(expected_titles):
                window._switch_page(index, animate=False)
                self.assertEqual(window.pages.currentIndex(), index)
                self.assertEqual(window._page_action_stack.currentIndex(), index)
                self.assertEqual(window.page_header.title_label.text(), title)
                self.assertTrue(window._nav_buttons[index].isChecked())

            window._switch_page(0, animate=False)
            self.assertIn(window.btn_generate, window._page_action_stack.currentWidget().findChildren(ActionButton))
            window._switch_page(2, animate=False)
            self.assertIn(
                window.btn_compress_start,
                window._page_action_stack.currentWidget().findChildren(ActionButton),
            )
            self.assertIsInstance(window.pages.currentWidget(), QScrollArea)

            # Dar görünümde kaynak listesi karttan taşmamalı; buton ve liste
            # aynı içerik kolonunda başlamalıdır.
            window.resize(1080, 760)
            window.show()
            self.app.processEvents()
            card = window.compress_files_card
            list_top_left = window.compress_file_list.mapTo(card, window.compress_file_list.rect().topLeft())
            list_bottom_left = window.compress_file_list.mapTo(card, window.compress_file_list.rect().bottomLeft())
            button_top_left = window.btn_compress_add.mapTo(card, window.btn_compress_add.rect().topLeft())
            self.assertEqual(list_top_left.x(), button_top_left.x())
            self.assertLessEqual(list_bottom_left.y(), card.contentsRect().bottom())

            self.assertFalse(window._sidebar_collapsed)
            window._toggle_sidebar()
            window._sidebar_animation.setCurrentTime(window._sidebar_animation.duration())
            self.assertTrue(window._sidebar_collapsed)
            self.assertTrue(all(button.text() == "" for button in window._nav_buttons))
            self.assertEqual(window.sidebar.property("collapsed"), True)
            self.assertEqual(window.sidebar.width(), window._sidebar_collapsed_width)

            window.waveform_view.set_data([-1.0, -0.25, 0.5, 1.0])
            self.assertEqual(window.waveform_view.data(), (-1.0, -0.25, 0.5, 1.0))
            self.assertTrue(window.waveform_view.property("hasData"))

            save_settings.reset_mock()
            save_history.reset_mock()
            window.close()
            save_settings.assert_called_once()
            save_history.assert_called_once_with([])
            window.deleteLater()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
