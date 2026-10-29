"""Ortak Windows masaüstü seçenekleri — otomatik başlatma + tepsiye küçült.

Bu modül, Windows masaüstü uygulamalarının Ayarlar ekranında sunması
gereken iki standart seçeneği bir arada toplar:

    1. "Windows'ta otomatik başlat"  → HKCU\\...\\Run kaydı
    2. "Kapatılınca tepsiye küçült"    → kapanış davranışı tercihi

Tasarım kuralları:
- Kütüphane bağımsız: yalnız standart kütüphane (winreg, os, sys) ve
  isteğe bağlı PyQt6. PyQt6 yoksa yalnız iş mantığı çalışır.
- Uygulamanın kendi ayar deposu kullanılır (callable get/set); modül
  dosya formatı dayatmaz.
- Kayıt yeri HKCU (kullanıcı başına) — yönetici yetkisi gerekmez, kurulum
  gerektirmez, kullanıcı kendi tercihidir.

Kullanım (PyQt6 ile):

    from app_options import AutostartController, TrayOption

    controller = AutostartController(
        app_name="NetSonar",
        get_setting=lambda k, d=None: settings.get(k, d),
        set_setting=lambda k, v: settings.update({k: v}),
    )
    box = QCheckBox("Windows'ta otomatik başlat")
    box.setChecked(controller.is_enabled())
    box.toggled.connect(controller.set_enabled)
"""

from __future__ import annotations
from i18n import t, set_language as ui_set_language, language as ui_language, LANGUAGES as UI_LANGUAGES

import logging
import os
import sys
from dataclasses import dataclass
from typing import Callable, Optional

log = logging.getLogger("AppOptions")

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"

# Ayar anahtarı adları — uygulamalar arasında ortak sözleşme.
SETTING_AUTOSTART = "AUTOSTART_ENABLED"
SETTING_MINIMIZE_TO_TRAY = "MINIMIZE_TO_TRAY"


# ─── Otomatik başlatma (HKCU Run) ──────────────────────────────────

def _winreg():
    """winreg modülünü döndürür; Windows dışında None."""
    if os.name != "nt":
        return None
    try:
        import winreg
        return winreg
    except ImportError:  # pragma: no cover
        return None


def startup_command(exe_path: str = "", args: str = "",
                    entry_point: str = "") -> str:
    """Otomatik başlatma komutunu kurar.

    Paketlenmiş uygulama: "<exe>" (veya "<exe> <args>")
    Kaynak kod modu: "<python> "<main.py>" (veya ek args)

    `entry_point` verilirse kaynak kod modunda o giriş noktası kullanılır;
    verilmezse `main.py` bulunmaya çalışılır. Bulunamazsa boş string döner
    (çağıran bunu "başlangıç kaydı oluşturulamadı" saymalıdır).
    """
    if getattr(sys, "frozen", False) or exe_path:
        # Paketlenmis uygulama (veya acikca verilen exe): exe yeter.
        exe = exe_path or sys.executable
        command = f'"{exe}"'
        if args:
            command += f" {args}"
        return command

    # Kaynak kod modu: yorumlayıcı + giriş noktası
    exe = exe_path or sys.executable
    main_py = entry_point or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "main.py")
    if os.path.exists(main_py):
        command = f'"{exe}" "{main_py}"'
    else:
        command = f'"{exe}"'
    if args:
        command += f" {args}"
    return command


class AutostartController:
    """HKCU Run kaydını yönetir: etkin mi, aç/kapa.

    Uygulamanın ayar deposuna da yazar; böylece "kapalı" tercihi hem
    kayıt defterinde hem ayar dosyasında tutarlıdır. Kayıt defteri
    elle silinirse bir sonraki açılışta ayardan geri yüklenir.
    """

    def __init__(self, app_name: str,
                 get_setting: Optional[Callable[[str, object], object]] = None,
                 set_setting: Optional[Callable[[str, object], None]] = None,
                 exe_path: str = "", args: str = "", entry_point: str = ""):
        self.app_name = app_name
        self._get = get_setting or (lambda key, default=None: default)
        self._set = set_setting or (lambda key, value: None)
        self._exe_path = exe_path
        self._args = args
        self._entry_point = entry_point

    def _command(self) -> str:
        return startup_command(self._exe_path, self._args, self._entry_point)

    # -- kayıt defteri ------------------------------------------------
    def _read_registry(self) -> Optional[str]:
        winreg = _winreg()
        if winreg is None:
            return None
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                                 winreg.KEY_READ)
            try:
                value, _ = winreg.QueryValueEx(key, self.app_name)
                return str(value)
            finally:
                winreg.CloseKey(key)
        except FileNotFoundError:
            return None
        except OSError as exc:
            log.warning("Baslangic kaydi okunamadi: %s", exc)
            return None

    def _write_registry(self, command: str) -> bool:
        winreg = _winreg()
        if winreg is None:
            return False
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                                 winreg.KEY_SET_VALUE)
            try:
                winreg.SetValueEx(key, self.app_name, 0, winreg.REG_SZ,
                                  command)
            finally:
                winreg.CloseKey(key)
            return True
        except OSError as exc:
            log.error("Baslangic kaydi yazilamadi: %s", exc)
            return False

    def _delete_registry(self) -> bool:
        winreg = _winreg()
        if winreg is None:
            return False
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                                 winreg.KEY_SET_VALUE)
            try:
                winreg.DeleteValue(key, self.app_name)
            except FileNotFoundError:
                pass
            finally:
                winreg.CloseKey(key)
            return True
        except OSError as exc:
            log.error("Baslangic kaydi silinemedi: %s", exc)
            return False

    # -- genel API ----------------------------------------------------
    def is_enabled(self) -> bool:
        """Otomatik başlatma açık mı?

        Kayıt defteri esas kaynaktır; kayıt yoksa ayar deposundaki tercihe
        bakılır (kayıt elle silinmiş olabilir).
        """
        if self._read_registry() is not None:
            return True
        return bool(self._get(SETTING_AUTOSTART, False))

    def set_enabled(self, enabled: bool) -> bool:
        """Tercihi uygular ve doğrular. Başarılıysa True."""
        enabled = bool(enabled)
        if enabled:
            command = self._command()
            if not command:
                log.error("Baslangic komutu olusturulamadi")
                return False
            ok = self._write_registry(command)
        else:
            ok = self._delete_registry()
        self._set(SETTING_AUTOSTART, enabled)
        verified = self.is_enabled() == enabled
        if not verified:
            log.warning("Baslangic tercihi dogrulanamadi (istenen=%s)", enabled)
        return bool(ok and verified)

    def refresh(self) -> bool:
        """Kayıt defterini mevcut komutla tazeler (kurulum/güncelleme sonrası).

        Tercih kapalıysa hiçbir şey yapmaz.
        """
        if not self.is_enabled():
            return True
        command = self._command()
        if not command:
            return False
        return self._write_registry(command)

    def current_command(self) -> Optional[str]:
        return self._read_registry()


# ─── Tepsiye küçültme ──────────────────────────────────────────────

@dataclass
class TrayOption:
    """Kapatılınca tepsiye küçült tercihi.

    Uygulamanın kapanış davranışı şu sırayı izler:
      1. Tercih kapalıysa → uygulama gerçekten kapanır.
      2. Tercih açıksa ve tepsi simgesi varsa → pencere gizlenir, uygulama
         arka planda çalışmaya devam eder.
      3. Tercih açıksa ama tepsi simgesi yoksa → kullanıcı uygulamayı
         kaybeder; bu yüzden geri düşüş olarak uygulama kapanır.
    """

    get_setting: Callable[[str, object], object]
    set_setting: Callable[[str, object], None]

    def is_enabled(self) -> bool:
        return bool(self._get(SETTING_MINIMIZE_TO_TRAY, True))

    def set_enabled(self, enabled: bool) -> bool:
        enabled = bool(enabled)
        self._set(SETTING_MINIMIZE_TO_TRAY, enabled)
        return self.is_enabled() == enabled

    def should_minimize(self, tray_available: bool) -> bool:
        """Kapatma olayında pencereyi gizlemeli miyiz?"""
        return self.is_enabled() and tray_available

    def _get(self, key: str, default=None):
        return self.get_setting(key, default)

    def _set(self, key: str, value) -> None:
        self.set_setting(key, value)


# ─── PyQt6 arayüz yardımcıları ─────────────────────────────────────

def build_settings_widgets(autostart: AutostartController, tray: TrayOption,
                           parent=None):
    """İki standart seçeneği PyQt6 onay kutuları olarak üretir.

    Döner: (autostart_checkbox, tray_checkbox)

    Kullanım:
        ac_cb, tray_cb = build_settings_widgets(autostart, tray)
        ac_cb.toggled.connect(autostart.set_enabled)
        tray_cb.toggled.connect(tray.set_enabled)
    """
    from PyQt6.QtWidgets import QCheckBox  # noqa: PLC0415

    autostart_box = QCheckBox(t("Windows'ta otomatik başlat"), parent)
    autostart_box.setChecked(autostart.is_enabled())
    autostart_box.toggled.connect(autostart.set_enabled)

    tray_box = QCheckBox(t("Kapatılınca tepsiye küçült"), parent)
    tray_box.setChecked(tray.is_enabled())
    tray_box.toggled.connect(tray.set_enabled)

    return autostart_box, tray_box
