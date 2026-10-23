"""Delta güncelleme paketini kurulu program klasörüne uygular.

Akış:
  1. ``read_manifest`` → paketin hangi sürümü hedeflediğini ve hangi taban
     sürümün üzerine uygulanabileceğini söyler.
  2. ``stage`` → dosyaları **geçici bir klasöre** çıkarır ve SHA-256 doğrular.
     Hiçbir yarım/bozuk dosya program klasörüne dokunmaz.
  3. ``apply`` → doğrulanmış dosyaları yerine taşır, silinmesi gerekenleri
     siler. Klasör içi yazma Program Files'ta yönetici izni ister; bu yüzden
     asıl uygulama adımı yükseltilmiş bir yardımcı süreçle yapılır
     (``scripts/apply_delta.py``, kurulumla birlikte ``_internal`` altına girer).

Neden böyle: program klasörü Program Files'ta ve uygulama yönetici olarak
çalışmıyor. Setup zaten yönetici izniyle çalışan bir yol sunuyor; delta ise
aynı işi 90 MB ile yapar. Yükseltilmiş yardımcı, kurulumun yaptığı işin
dosya kopyalama kısmını üstlenir; kayıt defteri/kısayol işine dokunmaz
(onlar kurulumun malıdır ve sürümden bağımsızdır).
"""
from __future__ import annotations

import json
import logging
import re
import shutil
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

log = logging.getLogger(__name__)

MANIFEST_NAME = "manifest.json"
FILES_PREFIX = "files/"


class DeltaError(Exception):
    """Kullanıcıya aynen duyurulacak delta hatası."""


@dataclass
class DeltaManifest:
    version: str
    base_version: str
    files: list[dict] = field(default_factory=list)   # path, sha256, size
    removed: list[str] = field(default_factory=list)
    total_bytes: int = 0


def _safe_member(name: str) -> bool:
    """ZIP girdisi güvenli mi (yol kaçışı yok).

    ``PurePosixPath("a/../../evil.dll").parts`` ``..`` içerir; bu yüzden
    parçalarda ``..`` aramak yeterli. Windows ayırıcıları da normalize edilir.
    """
    raw = str(name)
    if not raw or raw.startswith(("/", "\\")):
        return False
    normalized = raw.replace("\\", "/")
    if re.match(r"^[A-Za-z]:", normalized):      # C: sürücü yolu
        return False
    parts = PurePosixPath(normalized).parts
    if not parts:
        return False
    if ".." in parts:
        return False
    return True


def read_manifest(archive: Path) -> DeltaManifest:
    """Delta paketinin manifestini oku; biçim hatalarında DeltaError."""
    try:
        with zipfile.ZipFile(archive) as zf:
            if MANIFEST_NAME not in zf.namelist():
                raise DeltaError("Delta paketinde manifest yok.")
            payload = json.loads(zf.read(MANIFEST_NAME).decode("utf-8"))
    except zipfile.BadZipFile as exc:
        raise DeltaError("Delta paketi bozuk: ZIP açılamadı.") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise DeltaError("Delta manifesti okunamadı.") from exc
    try:
        manifest = DeltaManifest(
            version=str(payload["version"]),
            base_version=str(payload["base_version"]),
            files=list(payload.get("files") or []),
            removed=list(payload.get("removed") or []),
            total_bytes=int(payload.get("total_bytes") or 0),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise DeltaError("Delta manifesti eksik ya da geçersiz.") from exc
    if not manifest.files and not manifest.removed:
        raise DeltaError("Delta paketi boş: uygulanacak dosya yok.")
    for entry in manifest.files:
        if not _safe_member(str(entry.get("path") or "")):
            raise DeltaError(f"Delta içinde güvensiz yol: {entry.get('path')!r}")
    for name in manifest.removed:
        if not _safe_member(str(name)):
            raise DeltaError(f"Delta içinde güvensiz silme yolu: {name!r}")
    return manifest


def can_apply(manifest: DeltaManifest, current_version: str) -> bool:
    """Delta yalnız kendi taban sürümünün üzerine uygulanabilir."""
    return manifest.base_version == str(current_version)


def _sha256_of(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stage(archive: Path, manifest: DeltaManifest,
          stage_dir: Path | None = None) -> Path:
    """Delta dosyalarını geçici klasöre çıkar ve özetlerini doğrula.

    ``manifest.json`` de geçici klasöre yazılır: yükseltilmiş yardımcı
    (``--apply-delta``) hangi dosyaları taşıyacağını buradan okur.

    Doğrulama başarısızsa geçici klasör silinir ve ``DeltaError`` yükseltilir;
    program klasörüne hiçbir şey yazılmamış olur.
    """
    stage_dir = stage_dir or Path(tempfile.mkdtemp(prefix="voxora-delta-"))
    try:
        with zipfile.ZipFile(archive) as zf:
            for entry in manifest.files:
                name = str(entry["path"])
                member = FILES_PREFIX + name
                if member not in zf.namelist():
                    raise DeltaError(f"Delta paketinde dosya eksik: {name}")
                target = stage_dir / Path(*PurePosixPath(name).parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(member) as source, target.open("wb") as out:
                    shutil.copyfileobj(source, out, 1024 * 1024)
                expected = str(entry.get("sha256") or "")
                if expected and _sha256_of(target).lower() != expected.lower():
                    raise DeltaError(f"Delta dosyası doğrulanamadı: {name}")
        # Yardımcının okuyacağı manifest (yalnız doğrulanmış dosyalar).
        (stage_dir / MANIFEST_NAME).write_text(
            json.dumps({
                "version": manifest.version,
                "base_version": manifest.base_version,
                "files": manifest.files,
                "removed": manifest.removed,
            }, ensure_ascii=False, indent=2),
            encoding="utf-8")
    except (zipfile.BadZipFile, OSError) as exc:
        shutil.rmtree(stage_dir, ignore_errors=True)
        raise DeltaError("Delta paketi açılamadı.") from exc
    except DeltaError:
        shutil.rmtree(stage_dir, ignore_errors=True)
        raise
    return stage_dir


def apply_staged(stage_dir: Path, manifest: DeltaManifest,
                 target_root: Path) -> list[str]:
    """Hazırlanmış dosyaları hedef klasöre taşı; silinmesi gerekenleri sil.

    Çağıran tarafın yazma izni olmalı (Program Files'ta yükseltilmiş süreç).
    Dönen değer yazılan dosya adlarının listesidir.

    Yol güvenliği: her hedef ``resolve()`` edilip hedef kökün altında olduğu
    doğrulanır. ``Path.relative_to`` tek başına yetmez — ``a/b/../evil`` gibi
    bir yol ``a/b``ye göre ``../evil`` döndürür, yani kaçışı gizler.
    """
    root = target_root.resolve()
    written: list[str] = []
    for entry in manifest.files:
        name = str(entry["path"])
        source = stage_dir / Path(*PurePosixPath(name).parts)
        target = (root / Path(*PurePosixPath(name).parts)).resolve()
        if target != root and root not in target.parents:
            raise DeltaError(f"Hedef klasör dışına yazma denemesi: {name}")
        if not source.is_file():
            raise DeltaError(f"Hazırlanmış dosya eksik: {name}")
        target.parent.mkdir(parents=True, exist_ok=True)
        # Çalışan EXE kendini silemez (WinError 5): önce yerinden uzaklaştır,
        # sonra taşı, en son artığı sil. Windows çalışan bir görüntüyü silmeye
        # izin vermez ama aynı birimde YENİDEN ADLANDIRMAYA izin verir.
        stale = target.with_name(target.name + ".old")
        if stale.exists():
            try:
                stale.unlink()
            except OSError:
                pass
        if target.exists():
            try:
                target.rename(stale)
            except OSError as exc:
                raise DeltaError(
                    f"{name} değiştirilemedi (dosya kilitli olabilir): {exc}"
                ) from exc
        try:
            shutil.move(str(source), str(target))
        except OSError:
            # Geri al: eski dosya yerine dönsün, kurulum yarım kalmasın.
            if stale.exists() and not target.exists():
                stale.rename(target)
            raise
        if stale.exists():
            try:
                stale.unlink()
            except OSError:
                log.info("Delta: eski dosya sonra silinecek: %s", stale)
        written.append(name)
    for name in manifest.removed:
        target = (root / Path(*PurePosixPath(name).parts)).resolve()
        if target != root and root not in target.parents:
            log.warning("Delta: hedef dışı silme atlandı: %s", name)
            continue
        try:
            target.unlink(missing_ok=True)
        except OSError:
            log.warning("Delta: silinemedi (kilit?): %s", target)
    # Silinen dosyaların boş bıraktığı klasörleri temizle (en derinden yukarı).
    # Önemli: 0.7.0 delta'sı 5610 dosyayı siler (torch gider); dosyaları değil
    # de klasörleri bırakmak 354 boş klasörün kurulumda kalması demektir.
    # Yalnızca BOŞ klasörler silinir; silinen dosyaların üst klasörleri dışına
    # asla çıkılmaz (kullanıcı verisi, _internal kökü dokunulmaz).
    _prune_empty_parents(root, [str(name) for name in manifest.removed])
    return written


def _prune_empty_parents(root: Path, removed_names: list[str]) -> None:
    """Silinen dosyaların boş kalan üst klasörlerini kökten yukarı sil.

    ``os.scandir`` kullanılır: yol yoksa (aynı turda silinmiş olabilir) hata
    değil "boş" sayılır; ``Path.iterdir`` ise ``FileNotFoundError`` fırlatır ve
    ``OSError`` yakalayan blok temizliği sessizce yarıda keser.
    """
    import os

    def _is_empty(folder: Path) -> bool:
        try:
            with os.scandir(folder) as entries:
                return next(entries, None) is None
        except FileNotFoundError:
            return True   # zaten silinmiş -> boş say
        except OSError:
            return False  # erişilemiyor -> dokunma

    def _parents_of(name: str):
        parts = PurePosixPath(name).parts
        for depth in range(len(parts) - 1, 0, -1):
            yield root.joinpath(*parts[:depth])

    # Silinen dosyaların üst klasörlerini topla (yinelenmeden).
    candidates: set[Path] = set()
    for name in removed_names:
        for folder in _parents_of(name):
            if folder in candidates:
                break
            candidates.add(folder)
    # Post-order (önce en derin) sil: bir klasör yalnızca boş klasörler
    # içerdiğinde bile silinebilmeli — "dolu" görünmesinin sebebi içteki
    # boş klasörler olabilir. Yukarıdan tarama bu yüzden 45 klasör bırakıyordu.
    def _prune(folder: Path) -> bool:
        """Klasörü alt klasörleriyle sil; tamamen boşsa True döner."""
        try:
            children = list(folder.iterdir())
        except OSError:
            return False
        removed_all = True
        for child in children:
            if child.is_dir():
                if not _prune(child):
                    removed_all = False
            else:
                removed_all = False  # dosya var -> dokunma
        if not removed_all:
            return False
        try:
            folder.rmdir()
            return True
        except OSError:
            return False

    for folder in sorted(candidates, key=lambda p: len(p.parts), reverse=True):
        _prune(folder)
