"""Model ve motor paketi indirici.

Neden kendi indirici: ``huggingface_hub`` ilerleme çubuğunu kapatmak zorunda
kalıyoruz (konsolsuz pakette tqdm ``OSError 22`` atıyor) ve iptal/duraklatma
sunmuyor. Kullanıcı 4,6 GB indirirken ilerleme görmeli, durdurabilmeli ve
kaldığı yerden devam edebilmeli.

Desen WordArc'ta sınanmıştır:

- Her dosya ``<ad>.<revizyon>.part`` olarak iner; bitince ``os.replace`` ile
  atomik olarak yerine konur. Yarım dosya asla geçerli sayılmaz.
- Sunucu ``Range`` destekliyorsa kaldığı yerden devam eder; desteklemiyorsa
  (206 dönmezse) baştan indirir.
- Her dosya indikten sonra boyut + SHA-256 doğrulanır.
- İptal her 256 KB'lık blokta kontrol edilir; iptal edilen indirme
  ``Cancelled`` atar ve ``.part`` dosyası korunur (yeniden başlatınca devam).
- Disk alanı önceden kontrol edilir; yetmezse indirme hiç başlamaz.
"""
from __future__ import annotations
from i18n import t, set_language as ui_set_language, language as ui_language, LANGUAGES as UI_LANGUAGES

import json
import logging
import os
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

log = logging.getLogger(__name__)

__all__ = [
    "Cancelled",
    "DownloadError",
    "DownloadProgress",
    "download_file",
    "download_hf_model",
    "free_space_for",
]

_CHUNK = 256 * 1024
_TIMEOUT = 60
_USER_AGENT = "VoxoraStudio/1.0 (+https://github.com/zeitgeist-c/VoxoraStudio)"
#: Her dosya için deneme sayısı (kaldığı yerden devam ederek).
_ATTEMPTS = 3
#: İlerleme sinyali en fazla bu sıklıkta (saniye) yayınlanır.
_PROGRESS_INTERVAL = 0.15


class DownloadError(Exception):
    """Kullanıcıya gösterilecek indirme hatası."""


class Cancelled(Exception):
    """Kullanıcı indirmeyi durdurdu; hata değil, normal akış."""


@dataclass(frozen=True)
class DownloadProgress:
    """İlerleme anlık görüntüsü (motor/arayüz bunu okur)."""

    completed: int
    total: int
    speed: float          # bayt/sn
    remaining: float | None
    filename: str = ""
    phase: str = "download"   # download | verifying | connecting

    @property
    def percent(self) -> float:
        if not self.total:
            return 0.0
        return min(100.0, self.completed * 100.0 / self.total)


def free_space_for(path: Path | str, needed_bytes: int) -> None:
    """Hedef diskte yer var mı; yoksa indirme başlamadan anlaşılır hata ver."""
    probe = Path(path)
    while not probe.exists() and probe.parent != probe:
        probe = probe.parent
    try:
        free = shutil.disk_usage(probe).free
    except OSError:
        return  # ölçülemiyorsa engelleme
    # 64 MB emniyet payı: geçici dosya + arşiv açılışı.
    if free < needed_bytes + 64 * 1024 * 1024:
        raise DownloadError(
            t(f"Yeterli disk alanı yok: {needed_bytes / 1024 ** 3:.1f} GB gerekiyor, ") +
            t(f"{free / 1024 ** 3:.1f} GB boş.")
        )


def _open(url: str, offset: int = 0):
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    if offset:
        request.add_header("Range", f"bytes={offset}-")
    return urllib.request.urlopen(request, timeout=_TIMEOUT)


def download_file(
    url: str,
    destination: Path | str,
    *,
    expected_size: int = 0,
    expected_sha256: str = "",
    revision: str = "",
    should_stop=None,
    on_progress=None,
) -> Path:
    """Tek dosyayı indir, doğrula, atomik olarak yerine koy.

    Args:
        url: İndirme adresi.
        destination: Nihai dosya yolu.
        expected_size: Beklenen boyut (0 = bilinmiyor, doğrulama atlanır).
        expected_sha256: Beklenen SHA-256 ("" = doğrulama atlanır).
        revision: ``.part`` adında kullanılır; revizyon değişince eski yarım
            dosya yeniden kullanılmaz.
        should_stop: Çağrılabilir; True dönerse ``Cancelled`` atılır.
        on_progress: ``DownloadProgress`` alan çağrılabilir.

    Returns:
        Nihai dosya yolu.
    """
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_file() and _matches(target, expected_size, expected_sha256):
        return target

    part = target.with_name(f"{target.name}.{revision[:12] or 'x'}.part")
    offset = part.stat().st_size if part.is_file() else 0
    if expected_size and offset > expected_size:
        offset = 0
        part.write_bytes(b"")
    if expected_size:
        free_space_for(target, expected_size - offset)

    started = time.monotonic()
    received = 0
    last_notice = 0.0
    completed_base = offset

    def report(phase: str = "download", force: bool = False):
        nonlocal last_notice
        now = time.monotonic()
        if on_progress and (force or now - last_notice >= _PROGRESS_INTERVAL):
            elapsed = max(now - started, 0.001)
            speed = received / elapsed
            remaining = None
            if expected_size and speed > 0:
                remaining = max(0.0, (expected_size - (completed_base + received)) / speed)
            on_progress(DownloadProgress(
                completed=completed_base + received,
                total=expected_size,
                speed=speed,
                remaining=remaining,
                filename=target.name,
                phase=phase,
            ))
            last_notice = now

    def check():
        if should_stop is not None and should_stop():
            raise Cancelled()

    check()
    report("connecting", force=True)

    for attempt in range(_ATTEMPTS):
        try:
            # Boyut bilinmiyorsa (0) yine indir; "boyut yok" != "dosya tam".
            if not expected_size or offset < expected_size:
                with _open(url, offset) as response:
                    status = getattr(response, "status", 200)
                    if offset and status == 200:
                        # Sunucu Range'i yok saydı: baştan başla.
                        offset = 0
                        completed_base = 0
                        received = 0
                    elif offset and status != 206:
                        raise DownloadError(
                            t("Sunucu kaldığı yerden devam etmeyi desteklemiyor.")
                        )
                    with open(part, "ab" if offset else "wb") as sink:
                        while True:
                            check()
                            block = response.read(_CHUNK)
                            if not block:
                                break
                            sink.write(block)
                            offset += len(block)
                            received += len(block)
                            if expected_size and offset > expected_size:
                                raise DownloadError(
                                    t(f"İndirilen dosya beklenenden büyük: {target.name}")
                                )
                            report()
            report("verifying", force=True)
            _verify(part, expected_size, expected_sha256, target.name)
            os.replace(part, target)
            report("verifying", force=True)
            return target
        except Cancelled:
            raise
        except (urllib.error.URLError, TimeoutError, OSError, DownloadError) as exc:
            # Bozuk içerik bir sonraki denemede de bozuk iner: yarım dosyayı at ki
            # yeniden deneme temiz bir indirme yapsın.
            if isinstance(exc, DownloadError) and part.is_file():
                part.unlink(missing_ok=True)
                offset = 0
                completed_base = 0
                received = 0
            if attempt == _ATTEMPTS - 1:
                if isinstance(exc, DownloadError):
                    raise
                raise DownloadError(
                    t(f"İndirme tamamlanamadı: {target.name}\n{exc}")
                ) from exc
            log.warning("İndirme yeniden denenecek (%d/%d): %s", attempt + 1, _ATTEMPTS, exc)
            # İptal duyarlı bekleme (5, 10 sn).
            for _ in range(5 * (attempt + 1)):
                check()
                time.sleep(0.2)
            offset = part.stat().st_size if part.is_file() else 0
            completed_base = offset
            received = 0
    raise DownloadError(t(f"İndirme tamamlanamadı: {target.name}"))


def _matches(path: Path, expected_size: int, expected_sha256: str) -> bool:
    if expected_size and path.stat().st_size != expected_size:
        return False
    if expected_sha256:
        return _sha256(path) == expected_sha256.lower()
    return True


def _verify(path: Path, expected_size: int, expected_sha256: str, label: str) -> None:
    if not path.is_file():
        raise DownloadError(t("İndirilen dosya oluşmadı: {label}", label=label))
    if expected_size and path.stat().st_size != expected_size:
        raise DownloadError(
            t("İndirilen dosyanın boyutu tutmuyor: {label} ", label=label) +
            f"({path.stat().st_size} / {expected_size} bayt)."
        )
    if expected_sha256 and _sha256(path) != expected_sha256.lower():
        raise DownloadError(
            t("İndirilen dosya bozuk (SHA-256 tutmuyor): {label}. ", label=label) +
            t("İndirmeyi yeniden deneyin.")
        )


def _sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


# --- Hugging Face model ağırlıkları -------------------------------------------
def download_hf_model(
    repo_id: str,
    destination: Path | str,
    *,
    allow_patterns: list[str] | tuple[str, ...] | None = None,
    should_stop=None,
    on_progress=None,
) -> Path:
    """HF deposundan yalnız gereken dosyaları indir (kendi indiricimizle).

    ``huggingface_hub`` kullanılmaz: ilerleme/iptal/doğrulama bizde kalsın ve
    ağırlıklar kullanıcının seçtiği model klasörüne insin.

    Depo manifesti ``?blobs=true`` ile alınır; her dosyanın ``size`` ve
    ``lfs.sha256`` değeri oradadır. ``allow_patterns`` verilmezse tüm dosyalar
    iner (README, resim vb. dahil) — motorlar için her zaman liste verilir.
    """
    target_dir = Path(destination)
    target_dir.mkdir(parents=True, exist_ok=True)
    manifest = _hf_manifest(repo_id)
    revision = str(manifest.get("sha") or "")
    siblings = manifest.get("siblings") or []
    wanted = list(allow_patterns or [row.get("rfilename", "") for row in siblings])

    rows = []
    for row in siblings:
        name = str(row.get("rfilename") or "")
        if name not in wanted:
            continue
        size = int(row.get("size") or 0)
        sha = ""
        lfs = row.get("lfs")
        if isinstance(lfs, dict):
            sha = str(lfs.get("sha256") or "")
            size = int(lfs.get("size") or size)
        rows.append({"path": name, "size": size, "sha256": sha})
    missing = [name for name in wanted if name not in {r["path"] for r in rows}]
    if missing:
        raise DownloadError(
            "Model deposunda beklenen dosyalar yok: " + ", ".join(missing[:4])
        )
    if not rows:
        raise DownloadError(t("Model deposunda indirilecek dosya bulunamadı: {repo_id}", repo_id=repo_id))

    # Depo manifesti UZAKTAN gelir: ``rfilename`` değeri ``../`` ya da sürücü
    # yolu içerirse dosya model klasörünün dışına yazılırdı (path traversal).
    # İndirmeden önce her adı hedef kökün altına sabitle.
    for row in rows:
        row["path"] = _safe_relative(row["path"], target_dir)

    total_bytes = sum(row["size"] for row in rows)
    free_space_for(target_dir, total_bytes)

    for row in rows:
        name = row["path"]
        url = (
            f"https://huggingface.co/{repo_id}/resolve/{revision}/"
            f"{urllib.parse.quote(name)}?download=true"
        )
        download_file(
            url,
            target_dir / name,
            expected_size=row["size"],
            expected_sha256=row["sha256"],
            revision=revision,
            should_stop=should_stop,
            on_progress=on_progress,
        )
    return target_dir


def _safe_relative(name: str, root: Path) -> str:
    """Depo dosya adını doğrula: hedef kökün altında kalıyorsa adı aynen döndür.

    Hugging Face manifesti uzaktan gelir; ``rfilename`` alanı ``../x``,
    ``C:/x`` ya da UNC yolu taşıyabilir. Böyle bir ad ``target_dir / name``
    ile birleştirildiğinde dosya model klasörünün dışına yazılırdı. Geçerli
    depo adları bu kalıpları hiç içermez, bu yüzden kaçış denemesi hata sayılır
    (sessizce yeniden yazmak indirme URL'ini de bozardı).
    """
    raw = str(name)
    normalized = raw.replace("\\", "/")
    if not normalized or normalized.startswith("/") or ":" in normalized.split("/")[0]:
        raise DownloadError(t("Model deposunda geçersiz dosya yolu: {raw!r}", raw=raw))
    parts = PurePosixPath(normalized).parts
    if not parts or ".." in parts:
        raise DownloadError(t("Model deposunda kök dışına çıkan dosya yolu: {raw!r}", raw=raw))
    resolved = (root / Path(*parts)).resolve()
    root_resolved = root.resolve()
    if resolved != root_resolved and root_resolved not in resolved.parents:
        raise DownloadError(t("Model deposunda kök dışına çıkan dosya yolu: {raw!r}", raw=raw))
    return raw


def _hf_manifest(repo_id: str) -> dict:
    url = f"https://huggingface.co/api/models/{repo_id}?blobs=true"
    try:
        with _open(url) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise DownloadError(t("Model deposu bulunamadı: {repo_id}", repo_id=repo_id)) from None
        raise DownloadError(t(f"Model bilgisi alınamadı ({exc.code}): {repo_id}")) from None
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise DownloadError(
            t("Model bilgisi alınamadı: {repo_id}\n{exc}\n", repo_id=repo_id, exc=exc) +
            t("İnternet bağlantısını kontrol edin.")
        ) from exc
