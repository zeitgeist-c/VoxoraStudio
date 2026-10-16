"""Sürüm klasörünü gerçek ZIP'e paketler (güncelleme asset'i).

Kullanım:
    python scripts/make_update_package.py dist/VoxoraStudio-0.3.5

Çıktı: dist/VoxoraStudio-0.3.5.zip — üst düzeyde tek VoxoraStudio-X.Y.Z/
klasörü içeren, app.updater.extract()'in açabildiği gerçek ZIP (uzatmalı
adlandırma: ProgramAdı-Sürüm.zip). Kullanıcı verisi (state/, logs/, outputs/,
.update/) bilinçli olarak paketlenmez.
"""
from __future__ import annotations

import argparse
import re
import zipfile
from pathlib import Path

VERSIONED_DIR = re.compile(r"^VoxoraStudio-\d+\.\d+\.\d+$")
EXCLUDE_TOP = {"state", "logs", "outputs", ".update"}


def _is_user_data(rel: "Path") -> bool:
    """Kullanıcı/çalışma-zamanı verisi: paket kökünde ya da _internal altında."""
    if rel.parts[0] in EXCLUDE_TOP:
        return True
    return (len(rel.parts) >= 2 and rel.parts[0] == "_internal"
            and rel.parts[1] in EXCLUDE_TOP)


def build_zip(package_dir: Path, dest: Path | None = None) -> Path:
    package_dir = package_dir.resolve()
    if not package_dir.is_dir() or not VERSIONED_DIR.match(package_dir.name):
        raise SystemExit(f"Sürümlü paket klasörü bulunamadı: {package_dir}")
    exe = package_dir / f"{package_dir.name}.exe"
    if not exe.is_file():
        raise SystemExit(f"EXE eksik: {exe}")
    dest = dest or package_dir.parent / f"{package_dir.name}.zip"
    count = 0
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED, compresslevel=1) as zf:
        for path in sorted(package_dir.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(package_dir)
            if _is_user_data(rel):
                continue
            zf.write(path, f"{package_dir.name}/{rel.as_posix()}")
            count += 1
    print(f"{dest} ({count} dosya, {dest.stat().st_size / 1_048_576:.1f} MB)")
    return dest


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("package_dir", type=Path)
    args = parser.parse_args()
    build_zip(args.package_dir)
