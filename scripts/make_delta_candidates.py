"""Produce delta packages against previous versions under dist.

Last build step: compare the new version folder against every old
``VoxoraStudio-X.Y.Z`` folder under ``dist`` and produce a
``VoxoraStudio-<new>-delta-<old>.vxd`` for each.

That way a release can ship both the full setup and fast
update packages from (common) previous versions; the client picks the delta
fitting its base version, or downloads the full setup.

Usage:
    python scripts/make_delta_candidates.py <new_version>
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
        print("usage: make_delta_candidates.py <new_version>", file=sys.stderr)
        return 2
    new_version = argv[1]
    new_root = DIST / f"VoxoraStudio-{new_version}"
    if not new_root.is_dir():
        print(f"[delta] no new package, skipped: {new_root}")
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
        print("[delta] no old version to compare; no delta produced.")
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
    print(f"[delta] {produced} package produced.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
