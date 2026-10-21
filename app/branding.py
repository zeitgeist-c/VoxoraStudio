"""Voxora Studio product identity shared across the application."""
from __future__ import annotations

from .version import __version__

DISPLAY_NAME = "Voxora Studio"
TECHNICAL_NAME = "VoxoraStudio"
APP_USER_MODEL_ID = "Voxora.Studio"

BRAND_PRIMARY = "VOXORA"
BRAND_SECONDARY = "STUDIO"
TECHNICAL_TAGLINE = "Chatterbox Multilingual • Yerel üretim"

LOG_FILENAME = f"{TECHNICAL_NAME}.log"
PACKAGE_STEM = f"{TECHNICAL_NAME}-{__version__}"
#: EXE adı BİLİNÇLİ olarak sürüm taşımaz. Kurulum sabit klasöre
#: (``{autopf}\VoxoraStudio``) yazar ve kısayollar bu adı gösterir; sürümlü ad
#: her güncellemede kısayolları ve güncelleme yolunu kırardı.
EXECUTABLE_NAME = f"{TECHNICAL_NAME}.exe"
#: Sürümlü paket klasörü adı (yalnız build çıktısı; kurulum bunu kullanmaz).
PACKAGE_FOLDER = PACKAGE_STEM
INSTALLER_NAME = f"{PACKAGE_STEM}-Setup.exe"

__all__ = [
    "APP_USER_MODEL_ID",
    "BRAND_PRIMARY",
    "BRAND_SECONDARY",
    "DISPLAY_NAME",
    "EXECUTABLE_NAME",
    "INSTALLER_NAME",
    "LOG_FILENAME",
    "PACKAGE_FOLDER",
    "PACKAGE_STEM",
    "TECHNICAL_NAME",
    "TECHNICAL_TAGLINE",
    "__version__",
]
