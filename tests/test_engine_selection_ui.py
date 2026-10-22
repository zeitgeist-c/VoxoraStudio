"""
Voxora Studio - motor seçimi arayüz (offscreen) testleri.

EMA ─ Chatterbox geçişinde dil kilidi, referans ses düğmeleri ve özet
metninin doğru uygulandığını doğrular. Motor gerçekten yüklenmez
(`_init_engine_async` mock'lanır).
"""
from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from app import main_window  # noqa: E402
from app.main_window import MainWindow  # noqa: E402

_APP = None


class EngineSelectionUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global _APP
        _APP = QApplication.instance() or QApplication(["voxora-engine-tests"])
        _APP.setQuitOnLastWindowClosed(False)
        cls.app = _APP

    def _headless_window(self, settings: dict | None = None) -> MainWindow:
        patches = (
            patch.object(main_window, "load_settings", return_value=dict(settings or {})),
            patch.object(main_window, "load_history", return_value=[]),
            patch.object(main_window, "save_settings"),
            patch.object(main_window, "save_history"),
            patch.object(main_window.audio_player, "stop"),
            patch.object(MainWindow, "_init_engine_async", autospec=True),
        )
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        window = MainWindow()
        self.addCleanup(window.deleteLater)
        return window

    @staticmethod
    def _select(window: MainWindow, engine: str):
        index = window.engine_combo.findData(engine)
        assert index >= 0, engine
        window.engine_combo.setCurrentIndex(index)

    def test_defaults_to_ema(self):
        """Varsayılan motor EMA'dır: paketle gelir, her bilgisayarda çalışır."""
        window = self._headless_window()
        self.assertEqual(window.engine_combo.currentData(), "ema")
        self.assertEqual(window._engine_name, "ema")
        self.assertEqual(window.language_combo.currentData(), "tr")
        self.assertFalse(window.language_combo.isEnabled())
        self.assertFalse(window.preset_combo.isEnabled())
        self.assertFalse(window.exaggeration_spin.isEnabled())
        self.assertFalse(window.btn_select_voice.isEnabled())
        self.assertIn("EMA Lightning", window.settings_summary_label.text())

    def test_switching_to_chatterbox_unlocks_language_and_clone_controls(self):
        window = self._headless_window()

        self._select(window, "chatterbox")

        self.assertEqual(window._engine_name, "chatterbox")
        self.assertTrue(window.language_combo.isEnabled())
        self.assertTrue(window.preset_combo.isEnabled())
        self.assertTrue(window.exaggeration_spin.isEnabled())
        self.assertTrue(window.speed_spin.isEnabled())
        self.assertTrue(window.pause_spin.isEnabled())
        self.assertIn("Chatterbox", window.settings_summary_label.text())
        self.assertEqual(window._current_ui_settings()["engine"], "chatterbox")

    def test_switching_back_restores_saved_multilingual_language(self):
        window = self._headless_window()
        self._select(window, "chatterbox")
        window.language_combo.setCurrentIndex(window.language_combo.findData("en"))
        self.assertEqual(window._chatterbox_language_id, "en")

        self._select(window, "ema")
        self.assertEqual(window.language_combo.currentData(), "tr")

        self._select(window, "chatterbox")
        self.assertEqual(window._engine_name, "chatterbox")
        self.assertEqual(window.language_combo.currentData(), "en")
        self.assertTrue(window.language_combo.isEnabled())

    def test_saved_ema_setting_locks_language_on_start(self):
        window = self._headless_window({"engine": "ema", "language_id": "en"})
        self.assertEqual(window.engine_combo.currentData(), "ema")
        self.assertEqual(window.language_combo.currentData(), "tr")
        self.assertFalse(window.language_combo.isEnabled())
        self.assertEqual(window._chatterbox_language_id, "en")

    def test_unknown_saved_engine_falls_back_to_ema(self):
        window = self._headless_window({"engine": "gelecek-motor"})
        self.assertEqual(window.engine_combo.currentData(), "ema")
        self.assertFalse(window.language_combo.isEnabled())

    def test_voice_warning_skipped_for_ema(self):
        window = self._headless_window({"engine": "chatterbox"})
        self.assertTrue(window._needs_voice_warning())
        self._select(window, "ema")
        self.assertFalse(window._needs_voice_warning())

    def test_engine_change_blocked_while_synthesizing(self):
        window = self._headless_window()
        window._synth_worker = SimpleNamespace(isRunning=lambda: True)
        with patch.object(main_window.QMessageBox, "information") as info:
            self._select(window, "chatterbox")
            info.assert_called_once()
        self.assertEqual(window.engine_combo.currentData(), "ema")
        self.assertEqual(window._engine_name, "ema")

    def test_voxcpm2_is_disabled_without_cuda(self):
        """CUDA'sız makinede VoxCPM2 listede görünür ama seçilemez."""
        from unittest.mock import patch as _patch

        with _patch("app.hardware.detect",
                    return_value=SimpleNamespace(cuda=False, gpu_name="", vram_gb=0.0,
                                                 disk_free_gb=500.0, ram_gb=16.0,
                                                 cpu_threads=8, other_gpu=False,
                                                 other_gpu_name="", cuda_comfortable=False)):
            window = self._headless_window()
        index = window.engine_combo.findData("voxcpm2")
        self.assertGreaterEqual(index, 0, "VoxCPM2 listede olmalı")
        item = window.engine_combo.model().item(index)
        self.assertIsNotNone(item)
        self.assertFalse(item.isEnabled(), "CUDA yokken VoxCPM2 seçilememeli")
        # Tooltip gerekçeyi taşır.
        tip = window.engine_combo.itemData(index, Qt.ItemDataRole.ToolTipRole) or ""
        self.assertIn("CUDA", tip)

    def test_voxcpm2_is_enabled_with_cuda(self):
        from unittest.mock import patch as _patch

        with _patch("app.hardware.detect",
                    return_value=SimpleNamespace(cuda=True, gpu_name="RTX 4070", vram_gb=12.0,
                                                 disk_free_gb=500.0, ram_gb=32.0,
                                                 cpu_threads=16, other_gpu=False,
                                                 other_gpu_name="", cuda_comfortable=True)):
            window = self._headless_window()
        index = window.engine_combo.findData("voxcpm2")
        self.assertGreaterEqual(index, 0)
        item = window.engine_combo.model().item(index)
        self.assertTrue(item.isEnabled(), "CUDA varken VoxCPM2 seçilebilmeli")


if __name__ == "__main__":
    unittest.main()
