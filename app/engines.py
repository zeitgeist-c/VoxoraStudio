"""Ses motoru tanımları — her motorun yetenekleri ve indirme koşulları.

Neden bu modül var: arayüzde motor başına elle yazılmış ``if engine == "ema"``
dalları vardı. Üçüncü motor (VoxCPM2) gelince bu dallar çoğalır ve biri
unutulduğunda ekran yalan söyler (ör. VoxCPM2 seçiliyken dil kutusu açık kalır).

Burada her motor tek bir kayıtla tanımlanır:

- hangi dilleri okur,
- ses klonlamayı destekler mi,
- ses tasarımını (tarifle ses üretme) destekler mi,
- örnekleme hızı,
- pakette mi gömülü yoksa indirilir mi,
- hangi donanımı ister.
"""
from __future__ import annotations

from dataclasses import dataclass

from i18n import t

EVEN_PACKAGE = "package"
EVEN_DOWNLOAD = "download"


@dataclass(frozen=True)
class EngineSpec:
    """Bir ses motorunun tüm yetenekleri ve dağıtım bilgisi."""

    #: key stored in the settings file (``chatterbox``, ``ema``, ``voxcpm2``).
    key: str
    #: display name in the UI.
    label: str
    #: short description (one line, under the engine card).
    tagline: str
    #: languages it reads (ISO 639-1). Empty tuple = no language choice, single language.
    languages: tuple[str, ...]
    #: Referans sesle klonlama.
    cloning: bool
    #: generate new voices by writing a description (VoxCPM2 only).
    voice_design: bool
    #: output sample rate (Hz).
    sample_rate: int
    #: whether speed applies through the engine's own parameter (True) or
    #: via external time-stretch (False).
    speed_native: bool
    #: whether it ships with the package or the user downloads it.
    delivery: str
    #: model weight download size (MB, approximate).
    model_size_mb: int
    #: engine code (Python libraries) download size (MB).
    runtime_size_mb: int
    #: whether CUDA (NVIDIA driver) is mandatory.
    requires_cuda: bool
    #: usable on CPU when CUDA is not mandatory.
    cpu_ok: bool
    #: license name (shown to the user).
    license: str
    #: UI order (small first).
    order: int
    #: extra warning (hardware/language constraint).
    notice: str = ""

    @property
    def bundled(self) -> bool:
        """Programla birlikte gelir mi (indirme gerekmez)."""
        return self.delivery == EVEN_PACKAGE

    @property
    def single_language(self) -> bool:
        return len(self.languages) <= 1

    @property
    def total_download_mb(self) -> int:
        return self.model_size_mb + self.runtime_size_mb

    def size_label(self) -> str:
        """İnsan okunur boyut: 66 MB, 4,4 GB."""
        if self.total_download_mb >= 1000:
            return f"{self.total_download_mb / 1000:.1f} GB".replace(".", ",")
        return f"{self.total_download_mb} MB"


#: all engines. Order is set by ``order``.
ENGINES: dict[str, EngineSpec] = {
    "ema": EngineSpec(
        key="ema",
        label="EMA Lightning",
        tagline="Türkçe • tek ses • CPU'da bile çok hızlı",
        languages=("tr",),
        cloning=False,
        voice_design=False,
        sample_rate=48_000,
        speed_native=True,
        delivery=EVEN_PACKAGE,
        model_size_mb=44,
        runtime_size_mb=0,
        requires_cuda=False,
        cpu_ok=True,
        license="Apache-2.0",
        order=0,
    ),
    "chatterbox": EngineSpec(
        key="chatterbox",
        label="Chatterbox Multilingual",
        tagline="16 dil • ses klonlama • en yüksek kalite",
        languages=(
            "tr", "en", "de", "fr", "es", "it", "pt", "ru", "ja",
            "ko", "zh", "ar", "hi", "nl", "pl", "sv",
        ),
        cloning=True,
        voice_design=False,
        sample_rate=24_000,
        speed_native=False,
        delivery=EVEN_DOWNLOAD,
        # Real download: 6 files = 2.99 GB (HF repo 12.9 GB, mostly alternative
        # format). Runtime (torch+transformers+librosa stack) compressed ~400 MB.
        model_size_mb=3060,
        runtime_size_mb=400,
        requires_cuda=False,
        cpu_ok=True,
        license="MIT",
        order=1,
        notice="Bu motor paketi CPU üzerinde çalışır; uzun metinlerde üretim yavaş olabilir.",
    ),
    "voxcpm2": EngineSpec(
        key="voxcpm2",
        label="VoxCPM2",
        tagline="30 dil • ses tasarımı • 48 kHz stüdyo kalitesi",
        languages=(
            "tr", "en", "de", "fr", "es", "it", "pt", "ru", "ja", "ko", "zh", "ar",
            "hi", "nl", "pl", "sv", "da", "fi", "el", "he", "id", "km", "lo", "ms",
            "my", "no", "sw", "th", "tl", "vi",
        ),
        cloning=True,
        voice_design=True,
        sample_rate=48_000,
        speed_native=False,
        delivery=EVEN_DOWNLOAD,
        # model.safetensors 4,37 GB + audiovae.pth 360 MB = 4,62 GB.
        model_size_mb=4730,
        runtime_size_mb=420,
        requires_cuda=True,
        cpu_ok=False,
        license="Apache-2.0",
        order=2,
        notice="Yalnız NVIDIA ekran kartı olan bilgisayarlarda çalışır.",
    ),
}

#: default engine: ships with the package, runs on every computer.
DEFAULT_ENGINE = "ema"


def spec(key: str) -> EngineSpec:
    """Motor kaydı; bilinmeyen anahtar varsayılana düşer."""
    return ENGINES.get(key) or ENGINES[DEFAULT_ENGINE]


def ordered() -> tuple[EngineSpec, ...]:
    return tuple(sorted(ENGINES.values(), key=lambda e: e.order))


def keys() -> tuple[str, ...]:
    return tuple(e.key for e in ordered())


def availability(
    spec_: EngineSpec,
    *,
    cuda: bool,
    disk_free_gb: float = 0.0,
) -> tuple[bool, str]:
    """Motor bu bilgisayarda kullanılabilir mi — (uygun, gerekçe).

    Gerekçe kullanıcıya gösterilir: "NVIDIA sürücüsü bulunamadı" gibi.
    Uygun olmayan motor listede görünür ama seçilemez ve indirilemez.
    """
    if spec_.requires_cuda and not cuda:
        return (
            False,
            t("Bu bilgisayarda NVIDIA ekran kartı / CUDA bulunamadı. "
              "Bu motor yalnız CUDA'lı bilgisayarlarda çalışır."),
        )
    needed_gb = spec_.total_download_mb / 1000
    if disk_free_gb and disk_free_gb < needed_gb:
        return (
            False,
            t("Yeterli disk alanı yok: {needed:.1f} GB gerekiyor, "
              "{free:.1f} GB boş.", needed=needed_gb, free=disk_free_gb),
        )
    if spec_.notice and not spec_.requires_cuda and cuda:
        # On a CUDA machine the "slow on CPU" warning is meaningless; not a reason.
        return (True, "")
    return (True, "")


def languages_for(key: str) -> tuple[str, ...]:
    return spec(key).languages


def capabilities_text(spec_: EngineSpec) -> str:
    """Kullanıcıya tek satır yetenek özeti."""
    parts: list[str] = []
    if spec_.single_language:
        parts.append(t("1 dil"))
    else:
        parts.append(t("{n} dil", n=len(spec_.languages)))
    if spec_.voice_design:
        parts.append(t("ses tasarımı"))
    elif spec_.cloning:
        parts.append(t("ses klonlama"))
    parts.append(f"{spec_.sample_rate // 1000} kHz")
    return " • ".join(parts)
