"""Model yöneticisi — indirilebilir motorların kurulum durumu.

Bir motorun kullanılabilir olması iki parçaya bağlıdır:

1. **çalışma zamanı** (``.vxp``): Python kütüphaneleri, ``engines/<motor>``
   altına kurulur ve ``sys.path``e eklenir.
2. **ağırlıklar**: Hugging Face'ten ``models/<motor>`` altına iner.

İkisi ayrı tutulur çünkü güncelleme sırasında kütüphane değişir ama 3 GB'lık
ağırlık yeniden inmez (ya da tersi). Kullanıcıya ise tek bir "kurulu / kurulu
değil" durumu gösterilir.

Bu modül arayüz bilmez: ilerleme ve iptal çağrılabilir olarak dışarıdan verilir,
böylece hem GUI hem komut satırı aynı yolu kullanır.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from app import downloader, engine_pack, engines as engine_registry

log = logging.getLogger(__name__)

__all__ = [
    "EngineState",
    "LOCAL_ENGINE",
    "pins",
    "urls_for",
    "state_for",
    "install_engine",
    "remove_engine",
    "weights_dir",
    "runtime_installed",
]

#: Dosyaları pakette gelen motor (indirme gerekmez).
LOCAL_ENGINE = "ema"

MANIFEST_NAME = "engine_packs.json"


def _manifest_path() -> Path:
    """Pin dosyası: donmuş pakette ``_internal/assets``, kaynakta ``assets``."""
    from app import paths as app_paths

    bundled = app_paths.package_root() / "assets" / MANIFEST_NAME
    if bundled.is_file():
        return bundled
    # Geliştirme: depo kökü/assets
    return Path(__file__).resolve().parent.parent / "assets" / MANIFEST_NAME


def pins() -> dict:
    """Sürüm pinleri (yoksa boş sözlük — arayüz "henüz yayınlanmadı" der)."""
    try:
        return json.loads(_manifest_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        log.warning("Motor paketi pin dosyası okunamadı: %s", _manifest_path())
        return {}


def _pin_for(engine: str) -> dict:
    return (pins().get("engines") or {}).get(engine) or {}


def urls_for(engine: str) -> tuple[str, str]:
    """(runtime paket URL'i, ağırlık deposu kimliği).

    Paket henüz yayınlanmadıysa URL boş döner; arayüz bunu "henüz hazır değil"
    olarak gösterir, indirmeye kalkışmaz.
    """
    data = pins()
    entry = _pin_for(engine)
    runtime = entry.get("runtime") or {}
    file_name = str(runtime.get("file") or "")
    repo = str(data.get("release_repo") or "")
    tag = str(data.get("tag") or "")
    url = ""
    if file_name and repo and tag:
        url = f"https://github.com/{repo}/releases/download/{tag}/{file_name}"
    weights = str((entry.get("weights") or {}).get("repo_id") or "")
    return url, weights


def weights_dir(engine: str) -> Path:
    """Ağırlık klasörü: pakette gelen motor için paket içi, diğerleri kullanıcıda."""
    from app import paths as app_paths

    if engine == LOCAL_ENGINE:
        bundled = app_paths.bundled_models_dir() / "ema-onnx"
        if bundled.is_dir():
            return bundled
    return app_paths.models_dir() / engine


def runtime_installed(engine: str) -> bool:
    """Motor çalışma zamanı kurulu mu? (Pakette gelen motor her zaman hazır.)"""
    if engine == LOCAL_ENGINE:
        return True
    return engine_pack.is_installed(engine)


def _weights_ready(engine: str) -> bool:
    entry = _pin_for(engine)
    wanted = (entry.get("weights") or {}).get("files") or []
    if not wanted:
        return False
    root = weights_dir(engine)
    return all((root / name).is_file() for name in wanted)


@dataclass(frozen=True)
class EngineState:
    """Bir motorun bu bilgisayardaki durumu (arayüz bunu okur)."""

    engine: str
    label: str
    bundled: bool
    runtime_ok: bool
    weights_ok: bool
    size_label: str
    download_available: bool
    detail: str = ""

    @property
    def installed(self) -> bool:
        """Motor kullanıma hazır mı."""
        return self.runtime_ok and self.weights_ok

    @property
    def partial(self) -> bool:
        """Yarım kurulum: bir parça var, öteki yok."""
        return (self.runtime_ok or self.weights_ok) and not self.installed

    def status_text(self) -> str:
        if self.bundled:
            return "Kurulu (programla gelir)"
        if self.installed:
            return "Kurulu"
        if self.partial:
            missing = "ağırlıklar" if self.runtime_ok else "motor dosyaları"
            return f"Yarım kurulum — {missing} eksik"
        if not self.download_available:
            return "Henüz yayınlanmadı"
        return "İndirilmedi"


def state_for(engine: str) -> EngineState:
    """Tek motorun durumunu ölç (ağa çıkmaz)."""
    spec = engine_registry.spec(engine)
    runtime_ok = runtime_installed(engine)
    weights_ok = _weights_ready(engine) if engine != LOCAL_ENGINE else runtime_ok
    url, weights_repo = urls_for(engine)
    available = bool(url and weights_repo) or spec.bundled
    detail = ""
    if not spec.bundled and not url:
        detail = (
            "Motor paketi bu sürümde henüz yayınlanmadı; "
            "yayınlandığında buradan indirilebilir."
        )
    elif spec.notice:
        detail = spec.notice
    return EngineState(
        engine=spec.key,
        label=spec.label,
        bundled=spec.bundled,
        runtime_ok=runtime_ok,
        weights_ok=weights_ok,
        size_label=spec.size_label(),
        download_available=available,
        detail=detail,
    )


def install_engine(
    engine: str,
    *,
    on_progress=None,
    should_stop=None,
) -> EngineState:
    """Motoru indir ve kur: önce çalışma zamanı paketi, sonra ağırlıklar.

    Sıra önemli: ağırlıklar 3 GB, kütüphane ~400 MB. Kütüphane önce inerse
    kullanıcı daha erken geri bildirim görür ve bozuk bir pakette 3 GB boşa
    indirilmemiş olur.

    Herhangi bir adım iptal edilir ya da başarısız olursa yarım kalan dosyalar
    korunur (``.part``); yeniden çağrıldığında kaldığı yerden devam eder.
    """
    spec = engine_registry.spec(engine)
    if spec.bundled:
        return state_for(engine)
    url, weights_repo = urls_for(engine)
    if not url or not weights_repo:
        raise downloader.DownloadError(
            f"{spec.label} motoru bu sürümde henüz yayınlanmadı."
        )
    entry = _pin_for(engine)
    runtime = entry.get("runtime") or {}
    weights = entry.get("weights") or {}

    def announce(phase: str, done: int = 0, total: int = 0):
        if on_progress:
            on_progress(downloader.DownloadProgress(
                completed=done, total=total, speed=0.0, remaining=None,
                filename=phase, phase="download",
            ))

    # 1) Çalışma zamanı paketi
    if not engine_pack.is_installed(engine):
        announce(f"{spec.label} motor dosyaları indiriliyor")
        pack_path = engine_pack.engine_root(engine).parent / f".{engine}.vxp.download"
        downloader.download_file(
            url,
            pack_path,
            expected_size=int(runtime.get("size") or 0),
            expected_sha256=str(runtime.get("sha256") or ""),
            revision=str(runtime.get("file") or ""),
            should_stop=should_stop,
            on_progress=on_progress,
        )
        announce(f"{spec.label} motor dosyaları kuruluyor")
        engine_pack.install_pack(
            pack_path,
            expected_sha256=str(runtime.get("sha256") or "") or None,
        )
        pack_path.unlink(missing_ok=True)

    # 2) Ağırlıklar
    if not _weights_ready(engine):
        announce(f"{spec.label} model ağırlıkları indiriliyor")
        downloader.download_hf_model(
            weights_repo,
            weights_dir(engine),
            allow_patterns=weights.get("files") or None,
            should_stop=should_stop,
            on_progress=on_progress,
        )

    log.info("%s motoru kuruldu", spec.label)
    return state_for(engine)


def remove_engine(engine: str, *, remove_weights: bool = True) -> None:
    """Motoru kaldır. Ağırlıklar isteğe bağlı (3 GB'ı yeniden indirmemek için)."""
    spec = engine_registry.spec(engine)
    if spec.bundled:
        raise downloader.DownloadError(
            f"{spec.label} programla birlikte gelir ve kaldırılamaz."
        )
    engine_pack.remove_engine(engine)
    if remove_weights:
        import shutil

        root = weights_dir(engine)
        if root.is_dir():
            try:
                shutil.rmtree(root)
            except OSError:
                log.exception("Model ağırlıkları silinemedi: %s", root)
