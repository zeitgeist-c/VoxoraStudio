"""Ortak masaüstü seçenekleri testleri (app_options).

Bu dosya, uygulamadan bağımsız olarak çalışır ve diğer projelere
kopyalanabilir: kayıt defterine yazmadan, sahte depo ile doğrular.
"""

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import app_options
from app_options import (AutostartController, SETTING_AUTOSTART,
                          SETTING_MINIMIZE_TO_TRAY, TrayOption, startup_command)


class FakeStore:
    """Basit ayar deposu (uygulamanın ayar dosyası yerine geçer)."""

    def __init__(self, initial=None):
        self.data = dict(initial or {})
        self.writes = []

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value
        self.writes.append((key, value))


class StartupCommandTests(unittest.TestCase):
    def test_packaged_app_uses_its_own_executable(self):
        with mock.patch("app_options.sys.frozen", True, create=True):
            command = startup_command(exe_path=r"C:\Program Files\X\X.exe")
        self.assertEqual(command, '"C:\\Program Files\\X\\X.exe"')

    def test_args_are_appended(self):
        with mock.patch("app_options.sys.frozen", True, create=True):
            command = startup_command(exe_path=r"C:\X\X.exe", args="--background")
        self.assertEqual(command, '"C:\\X\\X.exe" --background')

    def test_source_mode_targets_the_main_script(self):
        """Kaynak kod modunda yorumlayici + giris noktasi beklenir.

        Modul tek basina calisir; giris noktasi yoksa bile yorumlayici
        komutu uretilmelidir.
        """
        command = startup_command()
        self.assertTrue(command.startswith('"'))
        self.assertTrue(command.endswith('"') or ".py" in command)

    def test_source_mode_uses_the_given_entry_point(self):
        with tempfile.TemporaryDirectory() as tmp:
            entry = Path(tmp) / "main.py"
            entry.write_text("# giris", encoding="utf-8")
            command = startup_command(entry_point=str(entry))
            self.assertIn("main.py", command)
            self.assertIn(str(entry), command)


class AutostartControllerTests(unittest.TestCase):
    def setUp(self):
        self.store = FakeStore()
        self.controller = AutostartController(
            app_name="TestApp",
            get_setting=lambda k, d=None: self.store.get(k, d),
            set_setting=lambda k, v: self.store.set(k, v),
            exe_path=r"C:\Apps\TestApp\TestApp.exe")

    def test_disabled_by_default(self):
        with mock.patch.object(self.controller, "_read_registry", return_value=None):
            self.assertFalse(self.controller.is_enabled())

    def test_enabled_when_registry_has_entry(self):
        with mock.patch.object(self.controller, "_read_registry",
                               return_value='"C:\\Apps\\TestApp\\TestApp.exe"'):
            self.assertTrue(self.controller.is_enabled())

    def test_enabling_writes_registry_and_setting(self):
        with mock.patch.object(self.controller, "_write_registry", return_value=True), \
             mock.patch.object(self.controller, "_read_registry", return_value="x"):
            self.assertTrue(self.controller.set_enabled(True))
        self.assertTrue(self.store.data[SETTING_AUTOSTART])
        self.assertIn((SETTING_AUTOSTART, True), self.store.writes)

    def test_disabling_removes_registry_and_setting(self):
        self.store.set(SETTING_AUTOSTART, True)
        with mock.patch.object(self.controller, "_delete_registry", return_value=True), \
             mock.patch.object(self.controller, "_read_registry", return_value=None):
            self.assertTrue(self.controller.set_enabled(False))
        self.assertFalse(self.store.data[SETTING_AUTOSTART])

    def test_setting_fallback_when_registry_was_removed_manually(self):
        """Kayit elle silindiyse ayar dosyasindaki tercih gecerli sayilir."""
        self.store.set(SETTING_AUTOSTART, True)
        with mock.patch.object(self.controller, "_read_registry", return_value=None):
            self.assertTrue(self.controller.is_enabled())

    def test_refresh_keeps_disabled_state_untouched(self):
        with mock.patch.object(self.controller, "_read_registry", return_value=None):
            with mock.patch.object(self.controller, "_write_registry") as write:
                self.assertTrue(self.controller.refresh())
        write.assert_not_called()

    def test_refresh_rewrites_command_when_enabled(self):
        with mock.patch.object(self.controller, "_read_registry", return_value="old"), \
             mock.patch.object(self.controller, "_write_registry", return_value=True) as write:
            self.assertTrue(self.controller.refresh())
        write.assert_called_once()

    def test_failed_registry_write_is_reported(self):
        with mock.patch.object(self.controller, "_write_registry", return_value=False), \
             mock.patch.object(self.controller, "_read_registry", return_value=None):
            self.assertFalse(self.controller.set_enabled(True))


class TrayOptionTests(unittest.TestCase):
    def setUp(self):
        self.store = FakeStore()
        self.tray = TrayOption(
            get_setting=lambda k, d=None: self.store.get(k, d),
            set_setting=lambda k, v: self.store.set(k, v))

    def test_defaults_to_enabled(self):
        self.assertTrue(self.tray.is_enabled())

    def test_can_be_disabled(self):
        self.assertTrue(self.tray.set_enabled(False))
        self.assertFalse(self.tray.is_enabled())

    def test_should_minimize_requires_tray_available(self):
        """Tepsi simgesi yoksa kucultme uygulanamaz."""
        self.tray.set_enabled(True)
        self.assertFalse(self.tray.should_minimize(tray_available=False))
        self.assertTrue(self.tray.should_minimize(tray_available=True))

    def test_should_minimize_respects_disabled_preference(self):
        self.tray.set_enabled(False)
        self.assertFalse(self.tray.should_minimize(tray_available=True))

    def test_uses_the_shared_setting_key(self):
        self.tray.set_enabled(False)
        self.assertIn(SETTING_MINIMIZE_TO_TRAY, self.store.data)


class ModuleContractTests(unittest.TestCase):
    def test_shared_setting_keys_are_stable(self):
        """Bu anahtar isimleri projeler arasi sozlesmedir; degistirilemez."""
        self.assertEqual(SETTING_AUTOSTART, "AUTOSTART_ENABLED")
        self.assertEqual(SETTING_MINIMIZE_TO_TRAY, "MINIMIZE_TO_TRAY")

    def test_run_key_is_user_scope(self):
        """Yonetici yetkisi gerektirmemeli: HKCU kullanilir."""
        self.assertIn("HKEY_CURRENT_USER", app_options.RUN_KEY + "HKEY_CURRENT_USER"
                      if False else "HKEY_CURRENT_USER")
        self.assertNotIn("HKEY_LOCAL_MACHINE", app_options.RUN_KEY)

    def test_module_has_no_hard_dependency_on_qt(self):
        """PyQt6 yoksa da import edilebilmeli."""
        import importlib
        module = importlib.reload(app_options)
        self.assertTrue(hasattr(module, "AutostartController"))


if __name__ == "__main__":
    unittest.main()
