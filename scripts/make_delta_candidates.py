"""dist altındaki önceki sürümlere karşı delta paketleri üretir.

Build'in son adımı: yeni sürüm klasörünü, ``dist`` altında bulunan tüm eski
``VoxoraStudio-X.Y.Z`` klasörleriyle karşılaştırır ve her biri için
``VoxoraStudio-<yeni>-delta-<eski>.vxd`` üretir.

Böylece yayına hem tam setup hem de (yaygın) önceki sürümlerden hızlı
güncelleme paketleri konabilir; istemci kendi taban sürümüne uyan delta'yı
seçer, uymuyorsa tam setup iner.

Kullanım:
    python scripts/make_delta_candidates.py <yeni_sürüm>
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.make_delta_package import build_delta  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
DIST = REPO_ROOT / "dist"
#: Delta yalnız bu kadar geriye kadar üretilir (yayın boyutu şişmesin).
MAX_BASES = 3


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("kullanım: make_delta_candidates.py <yeni_sürüm>", file=sys.stderr)
        return 2
    new_version = argv[1]
    new_root = DIST / f"VoxoraStudio-{new_version}"
    if not new_root.is_dir():
        print(f"[delta] yeni paket yok, atlandı: {new_root}")
        return 0

    def _version_key(path: Path) -> tuple:
        try:
            return tuple(int(part) for part in path.name.rsplit("-", 1)[-1].split("."))
        except ValueError:
            return (0, 0, 0)

    candidates = [
        path for path in DIST.iterdir()
        if path.is_dir()
        and path.name.startswith("VoxoraStudio-")
        and path.name != new_root.name
        and path.name.rsplit("-", 1)[-1].replace(".", "").isdigit()
        and _version_key(path) < _version_key(new_root)
    ]
    candidates.sort(key=_version_key, reverse=True)
    if not candidates:
        print("[delta] karşılaştırılacak eski sürüm yok; delta üretilmedi.")
        return 0
    produced = 0
    for base in candidates[:MAX_BASES]:
        base_version = base.name.rsplit("-", 1)[-1]
        dest = DIST / f"VoxoraStudio-{new_version}-delta-{base_version}.vxd"
        try:
            build_delta(base, new_root, dest)
            produced += 1
        except SystemExit as exc:
            print(f"[delta] {base_version}: {exc}")
    print(f"[delta] {produced} paket üretildi.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
