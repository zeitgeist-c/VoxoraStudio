"""Motor paketi (.vxp) — indirilebilir motor çalışma zamanı.

Neden ayrı paket: Chatterbox ve VoxCPM2 ``torch``, ``transformers``,
``diffusers`` gibi yüzlerce megabaytlık kütüphaneler ister. Bunları program
klasörüne gömmek kurulum dosyasını iki katına çıkarır ve kullanıcı hiç
kullanmayacağı motoru indirmek zorunda kalır. Sistem Python'una ``pip install``
çalıştırmak ise yönetici izni, bozuk ortam ve geri alınamaz kurulum riski
demektir.

Bu yüzden motor kütüphaneleri ayrı bir arşivde yayınlanır ve kullanıcının kendi
veri klasörüne açılır::

    %LOCALAPPDATA%\\VoxoraStudio\\engines\\chatterbox\\site-packages\\...

Program klasörüne ve sistem Python'una dokunulmaz; güncelleme program
klasörünü silip yeniden yazdığında motor paketi yerinde kalır. Motor
yüklenirken bu klasör ``sys.path``e eklenir.

Paket biçimi (``.vxp``, aslında ZIP)::

    manifest.json            — sürüm, dosya listesi, boyut, sha256
    payload/<göreli yol>     — dosyalar

Kurulum iki aşamalıdır: önce geçici klasöre açılır ve **her dosyanın**
SHA-256'sı doğrulanır; ancak tamamı doğruysa canlı klasöre taşınır. Bozuk ya da
yarım inmiş bir paket asla kurulu sayılmaz.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import tempfile
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

__all__ = [
    "FORMAT_VERSION",
    "MANIFEST_NAME",
    "PAYLOAD_PREFIX",
    "EnginePackError",
    "Manifest",
    "installed_version",
    "is_installed",
    "site_packages_dir",
    "engine_root",
    "remove_engine",
    "verify_pack",
    "install_pack",
    "build_pack",
    "add_engine_to_path",
]

#: Manifest biçim sürümü. Okunamayan sürüm reddedilir (sessiz yanlış kurulum yok).
FORMAT_VERSION = 1
MANIFEST_NAME = "manifest.json"
PAYLOAD_PREFIX = "payload/"

#: Aynı anda kurulabilecek en büyük paket (güvenlik sınırı, 8 GB).
MAX_PACK_BYTES = 8 * 1024 ** 3

_CHUNK = 1 << 20  # 1 MB


class EnginePackError(Exception):
    """Kullanıcıya gösterilecek motor paketi hatası."""


# --- manifest -----------------------------------------------------------------
@dataclass(frozen=True)
class Manifest:
    """Bir motor paketinin içindekiler."""

    engine: str
    engine_version: str
    python: str
    platform: str
    files: tuple[dict, ...] = field(repr=False)
    total_bytes: int = 0
    created: str = ""
    format_version: int = FORMAT_VERSION

    @property
    def file_count(self) -> int:
        return len(self.files)

    def to_dict(self) -> dict:
        return {
            "format_version": self.format_version,
            "engine": self.engine,
            "engine_version": self.engine_version,
            "python": self.python,
            "platform": self.platform,
            "created": self.created,
            "total_bytes": self.total_bytes,
            "files": list(self.files),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Manifest":
        version = int(data.get("format_version", 0) or 0)
        if version != FORMAT_VERSION:
            raise EnginePackError(
                f"Motor paketi biçimi desteklenmiyor (paket {version}, "
                f"program {FORMAT_VERSION}). Programı güncelleyin."
            )
        files = data.get("files")
        if not isinstance(files, list) or not files:
            raise EnginePackError("Motor paketi manifest dosyası bozuk: dosya listesi yok.")
        for row in files:
            if not isinstance(row, dict) or not row.get("path"):
                raise EnginePackError("Motor paketi manifest bozuk: dosya kaydı eksik.")
        return cls(
            engine=str(data.get("engine") or ""),
            engine_version=str(data.get("engine_version") or ""),
            python=str(data.get("python") or ""),
            platform=str(data.get("platform") or ""),
            files=tuple(files),
            total_bytes=int(data.get("total_bytes") or 0),
            created=str(data.get("created") or ""),
            format_version=version,
        )


# --- konumlar -----------------------------------------------------------------
def engine_root(engine: str) -> Path:
    """Bir motorun kurulu olduğu klasör."""
    from app import paths as app_paths

    return app_paths.engines_dir() / engine


def site_packages_dir(engine: str) -> Path:
    """Motorun Python paketlerinin bulunduğu klasör (``sys.path``e eklenir)."""
    return engine_root(engine) / "site-packages"


def _state_file(engine: str) -> Path:
    return engine_root(engine) / "installed.json"


def installed_version(engine: str) -> str:
    """Kurulu motor paketinin sürümü; kurulu değilse boş string."""
    state = _state_file(engine)
    try:
        data = json.loads(state.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    version = str(data.get("engine_version") or "")
    # Dosyalar gerçekten duruyor mu: elle silinmiş klasörü "kurulu" sayma.
    packages = site_packages_dir(engine)
    if not version or not packages.is_dir():
        return ""
    return version


def is_installed(engine: str) -> bool:
    return bool(installed_version(engine))


def remove_engine(engine: str) -> bool:
    """Kurulu motor paketini sil. Kullanıcı verisi (modeller) ayrı yerde, etkilenmez."""
    root = engine_root(engine)
    if not root.is_dir():
        return False
    try:
        shutil.rmtree(root)
    except OSError:
        log.exception("Motor paketi silinemedi: %s", root)
        raise EnginePackError(
            f"Motor paketi silinemedi: {root}\n"
            "Programı kapatıp yeniden deneyin."
        ) from None
    return True


def add_engine_to_path(engine: str) -> bool:
    """Motor paketini içe aktarma yoluna ekle (bir kez, idempotent).

    Dönen değer: paket gerçekten varsa True.
    """
    import sys

    target = site_packages_dir(engine)
    if not target.is_dir():
        return False
    entry = str(target)
    if entry not in sys.path:
        sys.path.insert(0, entry)
        log.info("Motor paketi içe aktarma yoluna eklendi: %s", entry)
    return True


# --- doğrulama ----------------------------------------------------------------
def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(_CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_pack(pack_path: Path | str, progress=None) -> Manifest:
    """Paketi açmadan doğrula: ZIP bütünlüğü + manifest + her dosyanın sha256'sı.

    İndirme bittikten sonra çağrılır. Bozuksa ``EnginePackError`` atar ve
    paket hiçbir yere kurulmaz.
    """
    path = Path(pack_path)
    if not path.is_file():
        raise EnginePackError(f"Motor paketi bulunamadı: {path}")
    size = path.stat().st_size
    if size == 0:
        raise EnginePackError("Motor paketi boş.")
    if size > MAX_PACK_BYTES:
        raise EnginePackError("Motor paketi beklenenden büyük; indirme bozulmuş olabilir.")
    with zipfile.ZipFile(path) as archive:
        bad = archive.testzip()
        if bad:
            raise EnginePackError(f"Motor paketi bozuk (ilk hatalı dosya: {bad}).")
        try:
            raw = archive.read(MANIFEST_NAME)
        except KeyError:
            raise EnginePackError(
                "Motor paketi manifest içermiyor; dosya bir motor paketi değil."
            ) from None
        try:
            manifest = Manifest.from_dict(json.loads(raw.decode("utf-8")))
        except json.JSONDecodeError as exc:
            raise EnginePackError(f"Motor paketi manifest okunamadı: {exc}") from None

        names = set(archive.namelist())
        total = len(manifest.files)
        for index, row in enumerate(manifest.files, start=1):
            origin = f"{PAYLOAD_PREFIX}{row['path']}"
            if origin not in names:
                raise EnginePackError(
                    f"Motor paketi eksik: {row['path']} arşivde yok."
                )
            expected = str(row.get("sha256") or "")
            if not expected:
                raise EnginePackError(
                    f"Motor paketi manifest bozuk: {row['path']} için sha256 yok."
                )
            digest = hashlib.sha256()
            with archive.open(origin) as handle:
                for block in iter(lambda: handle.read(_CHUNK), b""):
                    digest.update(block)
            if digest.hexdigest() != expected:
                raise EnginePackError(
                    f"Motor paketi bozuk: {row['path']} özeti tutmuyor."
                )
            if progress and (index % 50 == 0 or index == total):
                progress("Paket doğrulanıyor", index, total)
    return manifest


# --- kurulum ------------------------------------------------------------------
def install_pack(
    pack_path: Path | str,
    *,
    progress=None,
    expected_sha256: str | None = None,
) -> Manifest:
    """Paketi kullanıcı veri klasörüne kur.

    Sıra güvenlik odaklıdır:
      1. paket dosyasının kendi SHA-256'sı (verildiyse) doğrulanır,
      2. geçici klasöre açılır ve **her dosya** yeniden doğrulanır,
      3. eski kurulum ``.old-*`` adına taşınır, yenisi yerine konur,
      4. yalnız o zaman eski klasör silinir.

    Herhangi bir adımda hata olursa eski kurulum olduğu gibi kalır.
    """
    path = Path(pack_path)
    if expected_sha256:
        actual = _sha256_file(path)
        if actual.lower() != expected_sha256.lower():
            raise EnginePackError(
                "Motor paketi indirirken bozuldu (SHA-256 tutmuyor). "
                "İndirmeyi yeniden deneyin."
            )
    if progress:
        progress("Paket doğrulanıyor", 0, 1)
    manifest = verify_pack(path, progress=progress)
    if not manifest.engine:
        raise EnginePackError("Motor paketi hangi motora ait olduğunu bildirmiyor.")

    target = engine_root(manifest.engine)
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{manifest.engine}-", dir=target.parent))
    # Payload doğrudan site-packages altına açılır: motor yüklenirken sys.path'e
    # eklenen klasör burasıdır.
    packages_dir = staging / "site-packages"

    try:
        with zipfile.ZipFile(path) as archive:
            members = [n for n in archive.namelist() if n.startswith(PAYLOAD_PREFIX)]
            for name in members:
                relative = name[len(PAYLOAD_PREFIX):]
                if not relative or relative.endswith("/"):
                    continue
                destination = _safe_join(packages_dir, relative)
                destination.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(name) as source, open(destination, "wb") as sink:
                    shutil.copyfileobj(source, sink, _CHUNK)

        # Açılan dosyaları yeniden doğrula: disk hatası/yer sıkıntısı sessiz kalmasın.
        total = manifest.file_count
        for index, row in enumerate(manifest.files, start=1):
            target_file = _safe_join(packages_dir, row["path"])
            if not target_file.is_file():
                raise EnginePackError(f"Kurulum eksik kaldı: {row['path']}")
            if _sha256_file(target_file) != str(row["sha256"]):
                raise EnginePackError(f"Kurulum bozuk: {row['path']} özeti tutmuyor.")
            if progress and (index % 50 == 0 or index == total):
                progress("Kuruluyor", index, total)

        state = {
            "engine": manifest.engine,
            "engine_version": manifest.engine_version,
            "installed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "file_count": manifest.file_count,
            "total_bytes": manifest.total_bytes,
        }
        (staging / "installed.json").write_text(
            json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        old = None
        if target.exists():
            old = target.with_name(f"{target.name}.old-{os.getpid()}")
            if old.exists():
                shutil.rmtree(old, ignore_errors=True)
            os.replace(target, old)
        try:
            os.replace(staging, target)
        except OSError:
            # Yeni klasör yerine konamadıysa eskisini geri getir.
            if old is not None and not target.exists():
                os.replace(old, target)
            raise
        if old is not None:
            shutil.rmtree(old, ignore_errors=True)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    log.info(
        "Motor paketi kuruldu: %s %s (%d dosya)",
        manifest.engine, manifest.engine_version, manifest.file_count,
    )
    return manifest


def _safe_join(root: Path, relative: str) -> Path:
    """Arşiv yolunu kökün altında tut (zip-slip koruması).

    ``..`` içeren yol ``resolve()`` sonrası kökün dışına çıkıyorsa reddedilir.
    Windows sürücü harfi (``C:``) ve UNC yolları da reddedilir.
    """
    cleaned = relative.replace("\\", "/")
    if cleaned.startswith("/") or ":" in cleaned.split("/")[0]:
        raise EnginePackError(f"Motor paketinde geçersiz yol: {relative}")
    candidate = (root / cleaned).resolve()
    root_resolved = root.resolve()
    if candidate != root_resolved and root_resolved not in candidate.parents:
        raise EnginePackError(f"Motor paketinde kök dışına çıkan yol: {relative}")
    return candidate


# --- üretim (build zamanı) ----------------------------------------------------
def build_pack(
    source_dir: Path | str,
    output_path: Path | str,
    *,
    engine: str,
    engine_version: str,
    python: str = "3.11",
    platform: str = "win_amd64",
) -> Manifest:
    """Bir klasörü ``.vxp`` paketine çevir (sürüm üretimi sırasında çağrılır)."""
    source = Path(source_dir)
    if not source.is_dir():
        raise EnginePackError(f"Kaynak klasör yok: {source}")
    rows: list[dict] = []
    total = 0
    for file_path in sorted(source.rglob("*")):
        if not file_path.is_file():
            continue
        # PyInstaller/pip artıkları pakete girmez.
        if "__pycache__" in file_path.parts or file_path.suffix in (".pyc", ".pyo"):
            continue
        relative = file_path.relative_to(source).as_posix()
        size = file_path.stat().st_size
        rows.append({
            "path": relative,
            "size": size,
            "sha256": _sha256_file(file_path),
        })
        total += size
    if not rows:
        raise EnginePackError("Kaynak klasör boş; paket üretilemez.")
    manifest = Manifest(
        engine=engine,
        engine_version=engine_version,
        python=python,
        platform=platform,
        created=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        files=tuple(rows),
        total_bytes=total,
    )
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        archive.writestr(
            MANIFEST_NAME,
            json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2),
        )
        for row in rows:
            archive.write(source / row["path"], f"{PAYLOAD_PREFIX}{row['path']}")
    log.info(
        "Motor paketi üretildi: %s (%d dosya, %.1f MB)",
        output, manifest.file_count, output.stat().st_size / (1024 ** 2),
    )
    return manifest
