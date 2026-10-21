"""İki sürüm arasındaki farkı taşıyan delta güncelleme paketi.

Neden: her sürümde 1.25 GB'lık paketin yalnız birkaç dosyası değişiyor.
Ölçüm (0.5.4 → 0.5.5): 7164 dosyadan **3'ü** değişmişti; kalan 1149 MB aynı
byte'lardı. Tam setup 364-382 MB indiriyor, delta ise yalnız değişenleri.

Paket biçimi (``.vxd`` — aslında ZIP):

    manifest.json          sürüm, taban sürüm, dosya listeleri, sha256'lar
    files/<göreli yol>     yeni ve değişmiş dosyalar (sıkıştırılmış)

``manifest.json`` alanları:
    version        hedef sürüm
    base_version   üzerine uygulanabileceği en yakın (veya tek) taban sürüm
    files          [{path, sha256, size}] — yazılacak/değişecek dosyalar
    removed        [path] — silinecek dosyalar
    total_bytes    files toplam boyutu (doğrulama için)

Kullanım (build tarafı):
    python scripts/make_delta_package.py <eski_paket_klasörü> <yeni_paket_klasörü>

Kullanım (uygulama tarafı): ``app.delta.apply_delta``
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

MANIFEST_NAME = "manifest.json"
FILES_PREFIX = "files/"
#: Kullanıcı/çalışma-zamanı verisi asla pakete girmez.
EXCLUDE_PARTS = {"state", "logs", "outputs", "updates", ".update"}
#: Paket kökünde bulunmaması gereken kurulum artıkları.
EXCLUDE_NAMES = {"unins000.exe", "unins000.dat"}


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def package_files(root: Path) -> dict[str, Path]:
    """Paket kökündeki taşınacak dosyalar: göreli POSIX yol -> tam yol."""
    files: dict[str, Path] = {}
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        parts = {part.lower() for part in relative.parts}
        if parts & EXCLUDE_PARTS:
            continue
        if relative.name.lower() in EXCLUDE_NAMES:
            continue
        files[relative.as_posix()] = path
    return files


def _normalize_name(name: str) -> str:
    """Sürümlü EXE/BAT adlarını sabit ada indir (sürümler arası eşleşme için).

    v0.5.x paketleri ``VoxoraStudio-0.5.5.exe`` taşıyordu; v0.6.0'dan itibaren
    ad ``VoxoraStudio.exe``. Karşılaştırma ve delta yolları sabit adı kullanır.
    """
    lowered = name.lower()
    for versioned in (".exe", ".bat"):
        if lowered.endswith(versioned):
            stem = name[: -len(versioned)]
            if stem.startswith("VoxoraStudio-") and stem.count("-") >= 1:
                suffix = stem.rsplit("-", 1)[-1]
                if suffix.replace(".", "").isdigit():
                    return f"VoxoraStudio{versioned}"
    return name


def compare(old_root: Path, new_root: Path) -> tuple[list, list, list]:
    """(değişen, eklenen, silinen) listelerini döndür.

    Dönen öğeler: değişen/eklenen ``(göreli_yol, sha256, boyut)``, silinen
    ``göreli_yol``. Dosya adları normalize edilir (bkz. `_normalize_name`).
    """
    old_files = {_normalize_name(k): v for k, v in package_files(old_root).items()}
    new_files = {_normalize_name(k): v for k, v in package_files(new_root).items()}

    changed: list[tuple[str, str, int]] = []
    added: list[tuple[str, str, int]] = []
    for name, path in new_files.items():
        digest = sha256_of(path)
        if name in old_files:
            old_path = old_files[name]
            if (old_path.stat().st_size == path.stat().st_size
                    and sha256_of(old_path) == digest):
                continue
            changed.append((name, digest, path.stat().st_size))
        else:
            added.append((name, digest, path.stat().st_size))
    removed = sorted(name for name in old_files if name not in new_files)
    return changed, added, removed


def build_delta(old_root: Path, new_root: Path, dest: Path | None = None) -> Path:
    """İki paket arasındaki farkı ``.vxd`` dosyasına yaz."""
    old_root, new_root = old_root.resolve(), new_root.resolve()
    for label, root in (("eski", old_root), ("yeni", new_root)):
        if not root.is_dir():
            raise SystemExit(f"{label} paket klasörü yok: {root}")

    old_version = _version_of(old_root)
    new_version = _version_of(new_root)
    changed, added, removed = compare(old_root, new_root)
    if not changed and not added and not removed:
        raise SystemExit("İki paket arasında fark yok; delta üretilmedi.")

    dest = dest or new_root.parent / f"VoxoraStudio-{new_version}-delta.vxd"
    new_files = {_normalize_name(k): v for k, v in package_files(new_root).items()}
    manifest = {
        "version": new_version,
        "base_version": old_version,
        "files": [{"path": name, "sha256": digest, "size": size}
                  for name, digest, size in sorted(changed + added)],
        "removed": removed,
        "total_bytes": sum(size for _n, _d, size in changed + added),
    }
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        zf.writestr(MANIFEST_NAME,
                    json.dumps(manifest, ensure_ascii=False, indent=2))
        for entry in manifest["files"]:
            source = new_files[entry["path"]]
            zf.write(source, FILES_PREFIX + entry["path"])
    mb = dest.stat().st_size / 1_048_576
    print(f"{dest}  ({len(manifest['files'])} dosya, {mb:.1f} MB)")
    print(f"  taban {old_version} -> hedef {new_version}")
    print(f"  değişen {len(changed)}, yeni {len(added)}, silinen {len(removed)}")
    return dest


def _version_of(root: Path) -> str:
    """Paket klasörü adından sürüm (``VoxoraStudio-0.6.0`` -> ``0.6.0``)."""
    name = root.name
    if "-" not in name:
        raise SystemExit(f"Sürümlü paket klasörü beklenirdi: {root}")
    version = name.rsplit("-", 1)[-1]
    if not all(part.isdigit() for part in version.split(".")):
        raise SystemExit(f"Klasör adından sürüm okunamadı: {root}")
    return version


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(
            "Kullanım: python scripts/make_delta_package.py "
            "<eski_paket_klasörü> <yeni_paket_klasörü>")
    build_delta(Path(sys.argv[1]), Path(sys.argv[2]))
