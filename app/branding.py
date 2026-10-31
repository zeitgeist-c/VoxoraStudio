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
#: the EXE name DELIBERATELY carries no version. Setup writes to the fixed folder
#: (``{autopf}\VoxoraStudio``) and shortcuts show that name; a versioned name
#: a versioned name would break shortcuts and the update path on every update.
EXECUTABLE_NAME = f"{TECHNICAL_NAME}.exe"
#: versioned package folder name (build output only; setup does not use it).
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
