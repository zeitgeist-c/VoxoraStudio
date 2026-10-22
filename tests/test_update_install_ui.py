"""
Voxora Studio - güncelleme kurulum akışı regresyon testleri (v0.6.0).

v0.6.0'da ZIP+swap akışı kaldırılıp Inno Setup akışına geçildi; ancak
`main_window._on_update_installed` eski `updater.spawn_swap` çağrısını
taşıyordu. Çağrıya ulaşan tek yol "İndir ve Kur" olduğu için testler
göremedi; Qt, slot içindeki yakalanmayan istisnada süreci düşürüyor —
yani kullanıcıda uygulama sessizce kapanıyordu.

Bu dosya üç şeyi kilitler:
1. `installed` sinyali `updater.spawn_installer`'ı çağırmalı (elle kurulum
   dosyasıyla, sessiz kipte).
2. Kurulum başlatılamazsa uygulama AÇIK kalmalı ve kullanıcı bilgilendirilmeli.
3. Kaynakta kaldırılmış updater simgelerine çağrı kalmamalı (statik tarama).
"""
from __future__ import annotations

import os
import re
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication  # noqa: E402

from app import main_window, updater  # noqa: E402
from app.main_window import MainWindow  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]

#: v0.6.0'da kaldırıldı; kaynakta çağrısı kalan her kullanım ölü koddur ve
#: çalışma anında AttributeError ile süreci düşürür.
REMOVED_UPDATER_SYMBOLS = (
    "spawn_swap",
    "swap_script_text",
    "stale_package_dirs",
    "write_cleanup_marker",
    "cleanup_pending",
    "cleanup_after_update",
)

_APP = None


class UpdateInstallUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global _APP
        _APP = QApplication.instance() or QApplication(["voxora-update-tests"])
        _APP.setQuitOnLastWindowClosed(False)
        cls.app = _APP

    def _headless_window(self) -> MainWindow:
        patches = (
            patch.object(main_window, "load_settings", return_value={}),
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

    def test_installed_slot_launches_setup_installer(self):
        window = self._headless_window()
        launcher = "C:/tmp/VoxoraStudio-9.9.9-Setup.exe"
        with patch.object(updater, "spawn_installer", return_value=4242) as spawn, \
                patch.object(window, "close") as close:
            window._update_worker = None
            window._on_update_installed("9.9.9", launcher)
        spawn.assert_called_once()
        self.assertEqual(spawn.call_args.args[0], Path(launcher))
        close.assert_called_once_with()
        self.assertTrue(window._close_requested)
        self.assertIn("9.9.9", window.update_status_label.text())

    def test_installer_failure_keeps_app_open(self):
        window = self._headless_window()
        with patch.object(updater, "spawn_installer",
                          side_effect=updater.UpdateError("izin verilmedi")), \
                patch.object(main_window.QMessageBox, "warning") as warn, \
                patch.object(window, "close") as close:
            window._update_worker = None
            window._on_update_installed("9.9.9", "C:/tmp/yok-Setup.exe")
        warn.assert_called_once()
        close.assert_not_called()
        self.assertFalse(window._close_requested)

    def test_no_dead_updater_calls_in_sources(self):
        """Kaldırılmış updater simgelerinin çağrısı kaynakta yaşamamalı."""
        offenders: list[str] = []
        for py in sorted((REPO_ROOT / "app").rglob("*.py")) + [REPO_ROOT / "app.py"]:
            text = py.read_text(encoding="utf-8")
            for name in REMOVED_UPDATER_SYMBOLS:
                for match in re.finditer(rf"\b{name}\b", text):
                    line = text[:match.start()].count("\n") + 1
                    offenders.append(f"{py.relative_to(REPO_ROOT)}:{line} {name}")
        self.assertEqual(offenders, [], "ölü çağrılar: " + "; ".join(offenders))


if __name__ == "__main__":
    unittest.main()
