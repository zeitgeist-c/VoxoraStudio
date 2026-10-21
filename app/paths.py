"""Kullanıcı verisinin tek yetkili yol kaynağı.

Kurulum yapısı (v0.6.0):

  Program : ``C:\\Program Files\\VoxoraStudio``   (yalnız kod; kurulum siler/yazar)
  Veri    : ``%LOCALAPPDATA%\\VoxoraStudio``      (ayar, geçmiş, çıktı, log)

Neden ayrı: kurulum ve güncelleme program klasörünü tepeden tırnağa siler.
Kullanıcı verisi orada durursa her güncellemede kaybolur. Bu yüzden veri
program klasörünün DIŞINDA, kullanıcıya ait bir yerde tutulur ve kurulum
oraya hiç dokunmaz.

Kaynak kopyada (geliştirme) depo kökü kullanılır: ``git`` çalışma ağacı
düzeni değişmez, testler eskisi gibi çalışır.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import sys
from pathlib import Path

log = logging.getLogger(__name__)

__all__ = [
    "USER_DATA_DIRNAME",
    "package_root",
    "user_data_root",
    "state_dir",
    "logs_dir",
    "outputs_dir",
    "updates_dir",
    "ensure_user_dirs",
    "legacy_portable_packages",
    "migrate_legacy_state",
]

#: ``%LOCALAPPDATA%`` altındaki veri klasörü adı.
USER_DATA_DIRNAME = "VoxoraStudio"

#: Eski taşınabilir kurulumun state'inin durduğu göreli yol.
_LEGACY_STATE_REL = Path("_internal") / "state"

#: Göç sırasında yolu yeniden yazılacak ayar anahtarları.
_RELOCATED_KEYS = (
    "output_dir",
    "compress_output_dir",
    "audio_prompt_path",
    "voice_prompt_path",
)


def _is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def package_root() -> Path:
    """Çalışan paketin kökü: donmuş pakette EXE'nin klasörü, kaynakta depo kökü."""
    if _is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def user_data_root() -> Path:
    """Kullanıcı verisinin kökü.

    Donmuş pakette ``%LOCALAPPDATA%\\VoxoraStudio``; kaynak kopyada depo kökü.
    ``LOCALAPPDATA`` tanımsızsa (nadir) ``~/.voxorastudio``a düşer.
    """
    if not _is_frozen():
        return package_root()
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    if not base:
        return Path.home() / f".{USER_DATA_DIRNAME.lower()}"
    return Path(base) / USER_DATA_DIRNAME


def state_dir() -> Path:
    return user_data_root() / "state"


def logs_dir() -> Path:
    return user_data_root() / "logs"


def outputs_dir() -> Path:
    return user_data_root() / "outputs"


def updates_dir() -> Path:
    """İndirilen kurulum dosyalarının geçici yeri (kurulum sonrası silinir)."""
    return user_data_root() / "updates"


def ensure_user_dirs() -> None:
    """Veri klasörlerini hazırla; başarısız olursa uygulama yine açılır."""
    for directory in (state_dir(), logs_dir(), outputs_dir()):
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError:
            log.exception("Kullanıcı klasörü oluşturulamadı: %s", directory)


def legacy_portable_packages() -> list[Path]:
    """Diskte bulunan eski taşınabilir paket klasörleri (``VoxoraStudio-X.Y.Z``).

    Yalnız yaygın indirme konumlarına bakılır; tüm diski taramak yok. Dönüş
    değeri en yeniden eskiye sıralıdır (klasör değişiklik zamanına göre).
    """
    patterns: list[Path] = []
    home = Path.home()
    candidates = [
        home / "Downloads" / "Programs",
        home / "Downloads",
        home / "Masaüstü",
        home / "Desktop",
    ]
    local = os.environ.get("LOCALAPPDATA")
    if local:
        candidates.append(Path(local) / "Programs")
    for parent in candidates:
        try:
            if not parent.is_dir():
                continue
            patterns.extend(
                child for child in parent.iterdir()
                if child.is_dir() and _looks_like_legacy_package(child)
            )
        except OSError:
            continue
    def _mtime(path: Path) -> float:
        try:
            return path.stat().st_mtime
        except OSError:
            return 0.0
    return sorted(set(patterns), key=_mtime, reverse=True)


def _looks_like_legacy_package(path: Path) -> bool:
    """``VoxoraStudio-X.Y.Z`` adlı ve state'li klasör mü?"""
    from .branding import TECHNICAL_NAME

    name = path.name
    prefix = f"{TECHNICAL_NAME}-"
    if not name.startswith(prefix):
        return False
    parts = name[len(prefix):].split(".")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        return False
    return (path / _LEGACY_STATE_REL / "settings.json").is_file()


def migrate_legacy_state() -> str:
    """Eski taşınabilir paketten ayar/geçmiş devral; sonucu tek satırda döndür.

    Yalnız yeni yerleşimde ayar dosyası YOKKEN çalışır ve bir kez çalışır:
    ``state/migrated.json`` işareti yazılır. Kopyalama başarısız olursa
    işaret yazılmaz, sonraki açılışta yeniden denenir.

    Ayar içindeki paket klasörüne bakan yollar (çıktı klasörü, ses örneği)
    yeni veri köküne çevrilir; işaret ettikleri dosyalar varsa kopyalanır.
    Dönen değer kullanıcıya gösterilecek kısa metindir ("" = iş yok).
    """
    if not _is_frozen():
        return ""
    marker = state_dir() / "migrated.json"
    settings_file = state_dir() / "settings.json"
    if marker.is_file() or settings_file.is_file():
        return ""
    packages = legacy_portable_packages()
    if not packages:
        return ""
    source = packages[0]
    source_state = source / _LEGACY_STATE_REL
    try:
        state_dir().mkdir(parents=True, exist_ok=True)
        for name in ("settings.json", "history.json"):
            src = source_state / name
            if src.is_file():
                shutil.copy2(src, state_dir() / name)
        _relocate_settings(settings_file, source)
        marker.write_text(
            json.dumps({"from": str(source)}, ensure_ascii=False, indent=2),
            encoding="utf-8")
    except OSError:
        log.exception("Eski kurulum verisi devralınamadı: %s", source)
        return ""
    log.info("Eski kurulum verisi devralındı: %s", source)
    return f"Önceki kurulumunuzun ayarları devralındı ({source.name})."


def _relocate_settings(settings_file: Path, source_root: Path) -> None:
    """Eski paket köküne bakan yolları yeni veri köküne taşı.

    Eski pakette çıktı klasörü ``<paket>\\_internal\\outputs`` gibi paketin
    içindeydi (PyInstaller onedir kipi). Yeni yerleşimde kullanıcı verisi
    paketin dışında ve ``_internal`` sarmalayıcısı yok. Bu yüzden göreli yolu
    doğrudan taşımak ``VoxoraStudio\\_internal\\outputs`` gibi anlamsız bir yer
    üretirdi: ``_internal`` öneki atılır, altındaki yol veri köküne bağlanır.
    """
    try:
        settings = json.loads(settings_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(settings, dict):
        return
    root = user_data_root()
    changed = False
    for key in _RELOCATED_KEYS:
        raw = settings.get(key)
        if not raw:
            continue
        try:
            relative = Path(str(raw)).resolve().relative_to(source_root.resolve())
        except (ValueError, OSError):
            continue
        parts = relative.parts
        if parts and parts[0].lower() == "_internal":
            relative = Path(*parts[1:]) if len(parts) > 1 else Path()
        if not relative.parts:
            continue
        target = root / relative
        try:
            if target.exists():
                pass
            elif Path(str(raw)).is_dir():
                shutil.copytree(str(raw), target, dirs_exist_ok=True)
            elif Path(str(raw)).is_file():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(raw), target)
        except OSError:
            log.exception("Eski ayar yolu taşınamadı: %s", raw)
            continue
        settings[key] = str(target)
        changed = True
    if changed:
        settings_file.write_text(
            json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
