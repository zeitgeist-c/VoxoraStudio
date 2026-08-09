"""Sürümlü Voxora Studio EXE'sinin yanına eş adlı BAT başlatıcısı üretir."""

from __future__ import annotations

import argparse
from pathlib import Path
import re


VERSIONED_EXE = re.compile(r"^.+-\d+\.\d+\.\d+\.exe$", re.IGNORECASE)


def launcher_text(exe_name: str) -> str:
    if any(char in exe_name for char in ('"', '%', '\r', '\n')):
        raise ValueError("unsafe executable filename")
    return (
        "@echo off\r\n"
        "setlocal\r\n"
        "cd /d \"%~dp0\"\r\n"
        f"start \"Voxora Studio\" \"%~dp0{exe_name}\" %*\r\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("exe", type=Path)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    exe = args.exe.resolve()
    if not exe.is_file() or not VERSIONED_EXE.match(exe.name):
        parser.error(f"Sürümlü EXE bulunamadı: {exe}")
    bat = exe.with_suffix(".bat")
    if bat.exists() and not args.force:
        parser.error(f"BAT zaten var (--force kullanın): {bat}")
    bat.write_text(launcher_text(exe.name), encoding="utf-8", newline="")
    print(bat)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
