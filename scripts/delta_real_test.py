"""REAL delta-update test on an installed VoxoraStudio (shutdown flow).

Follows the production path:
  1. Roll the installed copy back to the old version (via the elevated helper).
  2. ``updater.apply_delta`` → verify, extract to temp, write the shutdown job file.
  3. Consume the job file in elevated ``--apply-delta-marker`` mode (the watcher's job).
  4. Verify byte-identical match with the new version.

Usage:
    python scripts/delta_real_test.py <install> <old_package> <delta>
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from app import delta, updater  # noqa: E402

NEW_VERSION = "0.7.0"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_in_package(pkg: Path, name: str) -> Path:
    """Find the file in the old package; on 0.5.x the EXE may carry a versioned name."""
    direct = pkg / Path(*name.replace("\\", "/").split("/"))
    if direct.is_file():
        return direct
    version = pkg.name.rsplit("-", 1)[-1]
    candidate = direct.with_name(f"{direct.stem}-{version}{direct.suffix}")
    if candidate.is_file():
        return candidate
    raise SystemExit(f"eski pakette dosya yok: {name}")


def write_downgrade_marker(staged: Path, entries: list[dict], root: Path) -> Path:
    marker = staged / "downgrade.json"
    marker.write_text(json.dumps({
        "staged": str(staged), "target": str(root), "version": "downgrade",
        "base_version": "downgrade", "files": entries, "removed": [],
    }, ensure_ascii=False), encoding="utf-8")
    return marker


def downgrade(root: Path, old_pkg: Path, names: list[str]) -> None:
    """Roll the installed copy back to the old version (via the elevated helper)."""
    staged = Path(tempfile.mkdtemp(prefix="voxora-downgrade-"))
    entries = []
    for name in names:
        source = resolve_in_package(old_pkg, name)
        target = staged / Path(*name.replace("\\", "/").split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        entries.append({"path": name, "sha256": sha256(source),
                        "size": source.stat().st_size})
    write_downgrade_marker(staged, entries, root)
    result = staged / "result.json"
    ok = updater.apply_pending_payload(staged, root, entries, result,
                                       wait_pid=None)
    if not ok:
        raise SystemExit(
            f"could not roll back to the old version: {result.read_text(encoding='utf-8-sig')}")
    payload = json.loads(result.read_text(encoding="utf-8-sig"))
    shutil.rmtree(staged, ignore_errors=True)
    if not payload.get("ok"):
        raise SystemExit(f"could not roll back to the old version: {payload}")
    print("rolled back to the old version:", payload.get("written"))


def stop_app() -> None:
    subprocess.run(["powershell", "-NoProfile", "-Command",
                    "Get-Process VoxoraStudio -ErrorAction SilentlyContinue | "
                    "Stop-Process -Force -ErrorAction SilentlyContinue"],
                   capture_output=True)
    time.sleep(3)


def compare_with_new(root: Path, new_pkg: Path) -> list[str]:
    bad: list[str] = []
    for path in new_pkg.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(new_pkg)
        if any(part in ("state", "logs", "outputs") for part in rel.parts):
            continue
        candidate = root / rel
        if not candidate.is_file() or sha256(candidate) != sha256(path):
            bad.append(str(rel))
    return bad


def main(argv: list[str]) -> int:
    if len(argv) != 5:
        print("usage: delta_real_test.py <install> <old_package> <delta> <base_version>",
              file=sys.stderr)
        return 2
    root = Path(argv[1]).resolve()
    old_pkg = Path(argv[2]).resolve()
    delta_file = Path(argv[3]).resolve()
    delta_base_version = argv[4]
    new_pkg = REPO / "dist" / f"VoxoraStudio-{NEW_VERSION}"

    print("kurulum:", root)
    print("delta  :", delta_file.name, f"{delta_file.stat().st_size/1048576:.1f} MB")
    stop_app()

    manifest = delta.read_manifest(delta_file)
    names = [entry["path"] for entry in manifest.files]
    print("delta files:", names)

    downgrade(root, old_pkg, names)
    print("kurulu EXE sha (eski):", sha256(root / "VoxoraStudio.exe")[:16])

    print("--- preparing delta (job file) ---")
    returned = updater.apply_delta(delta_file, delta_base_version)
    marker = Path(returned[0])
    print("job file:", marker, "| var:", marker.is_file())
    print("hedef HÂLÂ eski mi:", sha256(root / "VoxoraStudio.exe")[:16])

    result = marker.with_name("pending_delta_result.json")
    # `apply_delta` hedefi `package_root()`tan alır; kaynaktan koşarken bu repo
    # olur. Testte hedefi açıkça kurulum klasörüne çeviriyoruz.
    payload = json.loads(marker.read_text(encoding="utf-8"))
    payload["target"] = str(root)
    marker.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                      encoding="utf-8")
    print("--- worker running (elevated) ---")
    ok = updater.apply_pending_payload(Path(payload["staged"]),
                                       Path(payload["target"]),
                                       payload["files"], result,
                                       wait_pid=None)
    payload = json.loads(result.read_text(encoding="utf-8-sig"))
    print("result:", payload)
    if not ok:
        return 1

    total = sum(1 for p in new_pkg.rglob("*")
                if p.is_file()
                and not any(part in ("state", "logs", "outputs")
                            for part in p.relative_to(new_pkg).parts))
    bad = compare_with_new(root, new_pkg)
    print(f"compared {total} files, mismatched {len(bad)}")
    if bad:
        print("MISMATCHED:", bad[:10])
    print("SONUC:", "FULL MATCH" if not bad else "FARK VAR")
    return 0 if not bad else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
