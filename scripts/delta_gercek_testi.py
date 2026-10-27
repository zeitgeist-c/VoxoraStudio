"""Kurulu VoxoraStudio üzerinde GERÇEK delta güncelleme testi (kapanış akışı).

Üretimdeki yolu izler:
  1. Kurulu kopyayı eski sürüme çevir (yükseltilmiş yardımcı ile).
  2. ``updater.apply_delta`` → doğrula, geçici klasöre çıkar, kapanış fişi yaz.
  3. Fişi yükseltilmiş ``--apply-delta-marker`` kipiyle tüket (bekçinin işi).
  4. Yeni sürümle birebir eşleşme doğrula.

Kullanım:
    python scripts/delta_gercek_testi.py <kurulum> <eski_paket> <delta>
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
    """Eski pakette dosyayı bul; 0.5.x'te EXE sürümlü adda olabilir."""
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
    """Kurulu kopyayı eski sürüme çevir (yükseltilmiş yardımcıyla)."""
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
            f"eski sürüme çevrilemedi: {result.read_text(encoding='utf-8-sig')}")
    payload = json.loads(result.read_text(encoding="utf-8-sig"))
    shutil.rmtree(staged, ignore_errors=True)
    if not payload.get("ok"):
        raise SystemExit(f"eski sürüme çevrilemedi: {payload}")
    print("eski sürüme çevrildi:", payload.get("written"))


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
        print("kullanım: delta_gercek_testi.py <kurulum> <eski_paket> <delta> <taban_sürüm>",
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
    print("delta dosyaları:", names)

    downgrade(root, old_pkg, names)
    print("kurulu EXE sha (eski):", sha256(root / "VoxoraStudio.exe")[:16])

    print("--- delta hazırlanıyor (fiş) ---")
    returned = updater.apply_delta(delta_file, delta_base_version)
    marker = Path(returned[0])
    print("fiş:", marker, "| var:", marker.is_file())
    print("hedef HÂLÂ eski mi:", sha256(root / "VoxoraStudio.exe")[:16])

    result = marker.with_name("pending_delta_result.json")
    # `apply_delta` hedefi `package_root()`tan alır; kaynaktan koşarken bu repo
    # olur. Testte hedefi açıkça kurulum klasörüne çeviriyoruz.
    payload = json.loads(marker.read_text(encoding="utf-8"))
    payload["target"] = str(root)
    marker.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                      encoding="utf-8")
    print("--- işçi çalışıyor (yükseltilmiş) ---")
    ok = updater.apply_pending_payload(Path(payload["staged"]),
                                       Path(payload["target"]),
                                       payload["files"], result,
                                       wait_pid=None)
    payload = json.loads(result.read_text(encoding="utf-8-sig"))
    print("sonuç:", payload)
    if not ok:
        return 1

    total = sum(1 for p in new_pkg.rglob("*")
                if p.is_file()
                and not any(part in ("state", "logs", "outputs")
                            for part in p.relative_to(new_pkg).parts))
    bad = compare_with_new(root, new_pkg)
    print(f"karşılaştırılan {total} dosya, uyuşmayan {len(bad)}")
    if bad:
        print("UYUŞMAYAN:", bad[:10])
    print("SONUC:", "TAM EŞLEŞME" if not bad else "FARK VAR")
    return 0 if not bad else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
