"""PyInstaller cagrisi icin dinamik dil katalog modullerini
--hidden-import argumanlari olarak uretir (AUD-VOX-001).

Kullanim (build.bat):
  for /f "delims=" %%a in ('%PYEXE% scripts\\catalog_hidden_imports.py') do set CATALOG_ARGS=%%a
"""
import glob
import os

mods = sorted(
    os.path.splitext(os.path.basename(p))[0]
    for p in glob.glob("i18n_strings_*.py")
)
print(" ".join('--hidden-import "%s"' % m for m in mods))
