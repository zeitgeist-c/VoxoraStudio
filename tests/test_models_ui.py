"""Modeller sayfası ve ilk açılış sihirbazı testleri (offscreen)."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication  # noqa: E402

from app import engines as engine_registry  # noqa: E402
from app import first_run, model_manager  # noqa: E402
from app import main_window  # noqa: E402
from app.main_window import MainWindow  # noqa: E402

_APP = None


class _Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global _APP
        _APP = QApplication.instance() or QApplication(["voxora-models-tests"])
        _APP.setQuitOnLastWindowClosed(False)
        cls.app = _APP

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self._patches = [
            patch("app.paths.user_data_root", return_value=self.root),
            patch("app.paths.package_root", return_value=self.root),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()
        self._tmp.cleanup()

    def window(self) -> MainWindow:
        patches = (
            patch.object(main_window, "load_settings", return_value={}),
            patch.object(main_window, "load_history", return_value=[]),
            patch.object(main_window, "save_settings"),
            patch.object(main_window, "save_history"),
            patch.object(main_window.audio_player, "stop"),
            patch.object(MainWindow, "_init_engine_async", autospec=True),
            patch.object(MainWindow, "_maybe_show_first_run", autospec=True),
            patch.object(MainWindow, "_update_startup_check", autospec=True),
            patch.object(MainWindow, "_run_update_cleanup", autospec=True),
        )
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        win = MainWindow()
        self.addCleanup(win.deleteLater)
        return win


class ModelsPageTests(_Base):
    def test_page_exists_and_lists_every_engine(self):
        win = self.window()
        self.assertEqual(win.pages.count(), 5)
        win._switch_page(3, animate=False)
        self.assertEqual(win.page_header.title_label.text(), "Ses Modelleri")
        for spec in engine_registry.ordered():
            self.assertIn(spec.key, win._model_cards)

    def test_ema_card_is_installed_and_not_removable(self):
        win = self.window()
        card = win._model_cards["ema"]
        self.assertFalse(card["remove"].isEnabled())
        self.assertFalse(card["action"].isEnabled())  # indirmeye gerek yok
        self.assertIn("programla gelir", card["status"].text())

    def test_downloadable_engine_starts_not_installed(self):
        win = self.window()
        card = win._model_cards["chatterbox"]
        self.assertIn(card["status"].text(), ("İndirilmedi", "Henüz yayınlanmadı"))

    def test_models_folder_is_under_user_data(self):
        win = self.window()
        self.assertIn(str(self.root), win.model_folder_label.text())

    def test_disk_label_reports_usage(self):
        win = self.window()
        text = win.model_disk_label.text()
        self.assertIn("Kullanılan", text)

    def test_refresh_keeps_structure(self):
        win = self.window()
        win._refresh_models_page()
        for spec in engine_registry.ordered():
            self.assertIn(spec.key, win._model_cards)

    def test_install_requires_confirmation(self):
        win = self.window()
        with patch.object(main_window.QMessageBox, "question",
                          return_value=main_window.QMessageBox.StandardButton.No) as ask:
            win._on_model_install("chatterbox")
        ask.assert_called_once()
        self.assertIsNone(win._model_worker)

    def test_remove_requires_confirmation(self):
        # Kurulu gibi göster
        target = self.root / "engines" / "chatterbox"
        (target / "site-packages").mkdir(parents=True)
        (target / "installed.json").write_text(json.dumps({"engine_version": "1.0"}))
        weights = model_manager.weights_dir("chatterbox")
        weights.mkdir(parents=True)
        for name in model_manager.pins()["engines"]["chatterbox"]["weights"]["files"]:
            (weights / name).write_bytes(b"x")

        win = self.window()
        win._refresh_models_page()
        self.assertTrue(win._model_cards["chatterbox"]["remove"].isEnabled())
        with patch.object(main_window.QMessageBox, "question",
                          return_value=main_window.QMessageBox.StandardButton.No):
            win._on_model_remove("chatterbox")
        self.assertTrue(target.exists())  # iptal edildi

    def test_remove_deletes_when_confirmed(self):
        target = self.root / "engines" / "chatterbox"
        (target / "site-packages").mkdir(parents=True)
        (target / "installed.json").write_text(json.dumps({"engine_version": "1.0"}))
        win = self.window()
        with patch.object(main_window.QMessageBox, "question",
                          return_value=main_window.QMessageBox.StandardButton.Yes):
            win._on_model_remove("chatterbox")
        self.assertFalse(target.exists())

    def test_cancel_button_hidden_until_download(self):
        win = self.window()
        self.assertFalse(win.btn_model_cancel.isVisible())


class FirstRunTests(_Base):
    def test_should_show_when_nothing_installed(self):
        self.assertTrue(first_run.should_show())

    def test_mark_seen_prevents_showing_again(self):
        first_run.mark_seen()
        self.assertFalse(first_run.should_show())

    def test_should_not_show_when_engine_installed(self):
        target = self.root / "engines" / "chatterbox"
        (target / "site-packages").mkdir(parents=True)
        (target / "installed.json").write_text(json.dumps({"engine_version": "1.0"}))
        weights = model_manager.weights_dir("chatterbox")
        weights.mkdir(parents=True)
        for name in model_manager.pins()["engines"]["chatterbox"]["weights"]["files"]:
            (weights / name).write_bytes(b"x")
        self.assertFalse(first_run.should_show())

    def test_dialog_prefers_bundled_engine(self):
        dialog = first_run.FirstRunDialog()
        self.addCleanup(dialog.deleteLater)
        self.assertEqual(dialog.selected_engine(), "ema")
        self.assertEqual(dialog.btn_start.text(), "Başla")  # kurulu, indirme yok

    def test_dialog_later_emits_empty(self):
        dialog = first_run.FirstRunDialog()
        self.addCleanup(dialog.deleteLater)
        seen: list[str] = []
        dialog.selected.connect(seen.append)
        dialog._on_later()
        self.assertEqual(seen, [""])
        self.assertFalse(first_run.should_show())

    def test_dialog_start_emits_choice(self):
        dialog = first_run.FirstRunDialog()
        self.addCleanup(dialog.deleteLater)
        seen: list[str] = []
        dialog.selected.connect(seen.append)
        dialog._on_start()
        self.assertEqual(seen, ["ema"])

    def test_dialog_disables_cuda_only_engine_without_cuda(self):
        with patch("app.hardware.detect",
                   return_value=type("P", (), {
                       "cuda": False, "gpu_name": "", "vram_gb": 0.0,
                       "disk_free_gb": 500.0, "ram_gb": 16.0, "cpu_threads": 8,
                       "other_gpu": True, "other_gpu_name": "AMD",
                       "cuda_comfortable": False,
                   })()):
            dialog = first_run.FirstRunDialog()
        self.addCleanup(dialog.deleteLater)
        radios = dialog.findChildren(type(dialog.findChildren(object)[0])) if False else None
        # VoxCPM2 seçilemez olmalı
        for button in dialog._group.buttons():
            if button.property("engineKey") == "voxcpm2":
                self.assertFalse(button.isEnabled())
            if button.property("engineKey") == "chatterbox":
                self.assertTrue(button.isEnabled())


if __name__ == "__main__":
    unittest.main()
