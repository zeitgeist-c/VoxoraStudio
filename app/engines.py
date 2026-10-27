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

EVEN_PACKAGE = "package"
EVEN_DOWNLOAD = "download"


@dataclass(frozen=True)
class EngineSpec:
    """Bir ses motorunun tüm yetenekleri ve dağıtım bilgisi."""

    #: Ayar dosyasında saklanan anahtar (``chatterbox``, ``ema``, ``voxcpm2``).
    key: str
    #: Arayüzde görünen ad.
    label: str
    #: Kısa açıklama (tek satır, motor kutusunun altında).
    tagline: str
    #: Okuduğu diller (ISO 639-1). Boş demet = dil seçimi yok, tek dil.
    languages: tuple[str, ...]
    #: Referans sesle klonlama.
    cloning: bool
    #: Tarif yazarak yeni ses üretme (VoxCPM2'ye özgü).
    voice_design: bool
    #: Çıktı örnekleme hızı (Hz).
    sample_rate: int
    #: Hız ayarı motorun kendi parametresiyle mi uygulanır (True) yoksa
    #: dışarıdan time-stretch ile mi (False).
    speed_native: bool
    #: Paketle birlikte mi gelir, kullanıcı mı indirir.
    delivery: str
    #: Model ağırlıklarının indirme boyutu (MB, yaklaşık).
    model_size_mb: int
    #: Motor kodunun (Python kütüphaneleri) indirme boyutu (MB).
    runtime_size_mb: int
    #: CUDA (NVIDIA sürücüsü) zorunlu mu.
    requires_cuda: bool
    #: CUDA zorunlu değilse CPU'da kullanılabilir mi.
    cpu_ok: bool
    #: Lisans adı (kullanıcıya gösterilir).
    license: str
    #: Arayüz sırası (küçük önce).
    order: int
    #: Ek uyarı (donanım/dil kısıtı).
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


#: Tüm motorlar. Sıra ``order`` ile belirlenir.
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
        # Gerçek indirme: 6 dosya = 2,99 GB (HF deposu 12,9 GB, çoğu alternatif
        # format). Runtime (torch+transformers+librosa yığını) sıkıştırılmış ~400 MB.
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

#: Varsayılan motor: paketle gelen, her bilgisayarda çalışan motor.
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
            "Bu bilgisayarda NVIDIA ekran kartı / CUDA bulunamadı. "
            "Bu motor yalnız CUDA'lı bilgisayarlarda çalışır.",
        )
    needed_gb = spec_.total_download_mb / 1000
    if disk_free_gb and disk_free_gb < needed_gb:
        return (
            False,
            f"Yeterli disk alanı yok: {needed_gb:.1f} GB gerekiyor, "
            f"{disk_free_gb:.1f} GB boş.",
        )
    if spec_.notice and not spec_.requires_cuda and cuda:
        # CUDA'lı makinede "CPU'da yavaş" uyarısı anlamsız; gerekçe değil.
        return (True, "")
    return (True, "")


def languages_for(key: str) -> tuple[str, ...]:
    return spec(key).languages


def capabilities_text(spec_: EngineSpec) -> str:
    """Kullanıcıya tek satır yetenek özeti."""
    parts: list[str] = []
    if spec_.single_language:
        parts.append("1 dil")
    else:
        parts.append(f"{len(spec_.languages)} dil")
    if spec_.voice_design:
        parts.append("ses tasarımı")
    elif spec_.cloning:
        parts.append("ses klonlama")
    parts.append(f"{spec_.sample_rate // 1000} kHz")
    return " • ".join(parts)
