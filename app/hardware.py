"""Donanım tespiti — hangi ses motorunun bu bilgisayarda çalışabileceğini belirler.

Neden ayrı bir modül: motor seçimi ve model indirme kapısı aynı bilgiye bakıyor.
Tek yerde toplanmazsa iki ekran farklı hüküm verir ("indirilebilir" görünen motor
sonra yüklenemez). Buradaki tespit tek yetkili kaynaktır.

Kurallar:
- Hiçbir fonksiyon istisna fırlatmaz. Sürücü yok, PowerShell kapalı, WMI bozuk —
  hepsi "yok" sayılır ve program çalışmaya devam eder.
- CUDA kararı ``nvidia-smi -L`` ile verilir: sürücü varsa komut döner. WMI'daki
  kart adı yanıltıcı olabilir (eski sürücü kalıntısı, sanal GPU), bu yüzden ilk
  kapı çalışan sürücüdür.
- Yanlış pozitif pahalıdır: CUDA "var" denip sonra yüklenemezse kullanıcı 4,6 GB
  indirip eli boş kalır. Şüphede "yok" tarafına düşülür.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from functools import lru_cache

log = logging.getLogger(__name__)

__all__ = [
    "HardwareProfile",
    "detect",
    "cuda_ready",
    "nvidia_name",
    "nvidia_vram_gb",
    "total_ram_gb",
    "free_disk_gb",
    "summary",
]

#: CUDA'lı bir motor için gereken en az VRAM (GB). VoxCPM2 kartında ~8 GB ister;
#: Windows masaüstü 1-1,5 GB yediği için 8'in altındaki kart "sınırda" sayılır.
CUDA_COMFORT_VRAM_GB = 8.0

#: nvidia-smi çağrısı için üst sınır. Sürücü yoksa komut hemen döner; takılan bir
#: sürücüde program açılışını kilitlememek için kısa tutulur.
_SMI_TIMEOUT = 12


@dataclass(frozen=True)
class HardwareProfile:
    """Bu bilgisayarın ses motoru açısından fotoğrafı."""

    #: Çalışan bir NVIDIA sürücüsü var mı (``nvidia-smi`` yanıt veriyor mu).
    cuda: bool = False
    #: Sürücünün bildirdiği kart adı ("" = bilinmiyor).
    gpu_name: str = ""
    #: Toplam VRAM, GB (0.0 = bilinmiyor).
    vram_gb: float = 0.0
    #: NVIDIA dışı bir GPU görüldü mü (AMD / Intel / Qualcomm).
    other_gpu: bool = False
    other_gpu_name: str = ""
    #: Sistem RAM'i, GB.
    ram_gb: float = 0.0
    #: Mantıksal işlemci sayısı.
    cpu_threads: int = 0
    #: Kullanıcı veri diskinde boş alan, GB.
    disk_free_gb: float = 0.0
    #: Tespit sırasında oluşan notlar (kullanıcıya değil, loga).
    notes: tuple[str, ...] = field(default=(), repr=False)

    @property
    def cuda_comfortable(self) -> bool:
        """CUDA var ve VRAM rahat mı? 8 GB altı kart OOM riski taşır."""
        return self.cuda and (self.vram_gb <= 0 or self.vram_gb >= CUDA_COMFORT_VRAM_GB)

    @property
    def gpu_label(self) -> str:
        if self.cuda and self.gpu_name:
            return self.gpu_name
        if self.cuda:
            return "NVIDIA GPU"
        if self.other_gpu and self.other_gpu_name:
            return self.other_gpu_name
        return "Yok / CPU"


def _run(args: list[str], timeout: int = _SMI_TIMEOUT) -> str:
    """Komutu çalıştır, stdout döndür; her türlü hatada boş string."""
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            # noconsole pakette alt süreç konsol penceresi açmasın.
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError, ValueError) as exc:
        log.debug("komut çalışmadı (%s): %s", args[0] if args else "?", exc)
        return ""
    if result.returncode != 0:
        return ""
    return (result.stdout or "").strip()


@lru_cache(maxsize=1)
def _nvidia_smi_path() -> str:
    """nvidia-smi yolu; yoksa boş. Sistem PATH'inde olmayabilir (yaygın)."""
    found = shutil.which("nvidia-smi")
    if found:
        return found
    candidates = [
        r"C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe",
        r"C:\Windows\System32\nvidia-smi.exe",
    ]
    program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
    candidates.append(os.path.join(program_files, "NVIDIA Corporation", "NVSMI", "nvidia-smi.exe"))
    for path in candidates:
        if os.path.isfile(path):
            return path
    return ""


def _query_smi(fields: str) -> str:
    """``nvidia-smi --query-gpu`` tek satır yanıtı."""
    exe = _nvidia_smi_path()
    if not exe:
        return ""
    return _run([exe, f"--query-gpu={fields}", "--format=csv,noheader,nounits"])


def cuda_ready() -> bool:
    """Çalışan NVIDIA sürücüsü var mı.

    ``nvidia-smi -L`` kartları listeler. Sürücü kurulu değilse komut yoktur ya da
    hata döner. Yalnız bu sinyal kullanılır: kart adından CUDA çıkarmak yanıltıcı.
    """
    exe = _nvidia_smi_path()
    if not exe:
        return False
    listing = _run([exe, "-L"])
    return "GPU" in listing.upper()


def nvidia_name() -> str:
    line = _query_smi("name")
    return line.splitlines()[0].strip() if line else ""


def nvidia_vram_gb() -> float:
    line = _query_smi("memory.total")
    if not line:
        return 0.0
    try:
        return round(float(line.splitlines()[0].strip()) / 1024.0, 1)
    except (TypeError, ValueError):
        return 0.0


def _other_gpu(force: bool = False) -> tuple[bool, str]:
    """NVIDIA dışı GPU (AMD/Intel/Qualcomm) — DirectML adayı."""
    if os.name != "nt":
        return (False, "")
    names = _windows_gpu_names(force=force)
    if not names:
        return (False, "")
    excluded = ("microsoft", "remote", "basic display", "virtual")
    for name in names:
        lower = name.lower()
        if any(word in lower for word in excluded):
            continue
        if "nvidia" in lower:
            continue
        # AMD Radeon / Intel Arc / Iris / Qualcomm Adreno
        if any(word in lower for word in ("amd", "radeon", "arc", "iris", "intel", "adreno", "qualcomm")):
            return (True, name)
    return (False, "")


#: Tek PowerShell çağrısında okunan Windows sistem bilgisi (GPU adları + RAM).
#: ``detect`` iki ayrı CIM sorgusu yapıyordu; her PowerShell başlatması ~250 ms
#: sürüyor ve pencere açılışında bu bedel iki kez ödeniyordu.
_WININFO_CMD = (
    "$ErrorActionPreference='SilentlyContinue';"
    "$g=(Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name) -join '|';"
    "$r=(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory;"
    "Write-Output ('GPU=' + $g); Write-Output ('RAM=' + $r)"
)
_WININFO_CACHE: dict[str, tuple[list[str], float]] = {}


def _windows_gpu_names(force: bool = False) -> list[str]:
    return _windows_sysinfo(force=force)[0]


def _windows_ram_gb(force: bool = False) -> float:
    return _windows_sysinfo(force=force)[1]


def _windows_sysinfo(force: bool = False) -> tuple[list[str], float]:
    """(GPU adları, toplam RAM GB) — tek PowerShell çağrısı, önbellekli.

    Sürücü yoksa, PowerShell kapalıysa ya da çıktı bozuksa ``([], 0.0)``.
    """
    cached = _WININFO_CACHE.get("data")
    if cached is not None and not force:
        return cached
    raw = _run(["powershell", "-NoProfile", "-Command", _WININFO_CMD], timeout=15)
    names: list[str] = []
    ram_gb = 0.0
    for line in (raw or "").splitlines():
        text = line.strip()
        if text.startswith("GPU="):
            names = [part.strip() for part in text[4:].split("|") if part.strip()]
        elif text.startswith("RAM="):
            try:
                ram_gb = round(float(text[4:].strip()) / 1024 ** 3, 1)
            except (TypeError, ValueError):
                ram_gb = 0.0
    data = (names, ram_gb)
    _WININFO_CACHE["data"] = data
    return data


def total_ram_gb(force: bool = False) -> float:
    if os.name != "nt":
        try:
            pages = os.sysconf("SC_PHYS_PAGES")
            size = os.sysconf("SC_PAGE_SIZE")
            return round(pages * size / 1024 ** 3, 1)
        except (AttributeError, ValueError, OSError):
            return 0.0
    return _windows_ram_gb(force=force)


def free_disk_gb(path: str | None = None) -> float:
    """Kullanıcı veri diskinde boş alan. Model indirmeden önce kapı olarak kullanılır."""
    try:
        from app import paths as app_paths

        target = path or str(app_paths.user_data_root())
    except Exception:  # paths yüklenemezse ev dizinine bak
        target = path or os.path.expanduser("~")
    probe = target
    while probe and not os.path.isdir(probe):
        parent = os.path.dirname(probe)
        if parent == probe:
            break
        probe = parent
    try:
        usage = shutil.disk_usage(probe or os.path.expanduser("~"))
        return round(usage.free / 1024 ** 3, 1)
    except OSError:
        return 0.0


def detect(force: bool = False) -> HardwareProfile:
    """Donanım fotoğrafını döndür.

    Sonuç oturum boyunca önbelleklenir: motor değiştirmek her seferinde sürücü
    sorgusu yapmasın. ``force=True`` yeniden ölçer (kullanıcı "Yenile" derse).
    """
    if not force:
        cached = _CACHE.get("profile")
        if cached is not None:
            return cached
    notes: list[str] = []
    cuda = cuda_ready()
    name = ""
    vram = 0.0
    if cuda:
        name = nvidia_name()
        vram = nvidia_vram_gb()
        if not name:
            notes.append("nvidia-smi kart adı vermedi")
        if vram <= 0:
            notes.append("VRAM okunamadı")
    other, other_name = _other_gpu(force=force)
    profile = HardwareProfile(
        cuda=cuda,
        gpu_name=name,
        vram_gb=vram,
        other_gpu=other,
        other_gpu_name=other_name,
        ram_gb=total_ram_gb(force=force),
        cpu_threads=os.cpu_count() or 0,
        disk_free_gb=free_disk_gb(),
        notes=tuple(notes),
    )
    _CACHE["profile"] = profile
    log.info(
        "Donanım: cuda=%s gpu=%r vram=%sGB diger_gpu=%r ram=%sGB is_parcacigi=%s disk=%sGB",
        profile.cuda, profile.gpu_name, profile.vram_gb, profile.other_gpu_name,
        profile.ram_gb, profile.cpu_threads, profile.disk_free_gb,
    )
    return profile


_CACHE: dict[str, HardwareProfile] = {}


def summary(profile: HardwareProfile | None = None) -> str:
    """Kullanıcıya gösterilecek tek satır (Araçlar ▸ Sistem Bilgisi)."""
    data = profile or detect()
    parts = [f"GPU: {data.gpu_label}"]
    if data.cuda:
        parts.append("CUDA hazır")
        if data.vram_gb:
            parts.append(f"{data.vram_gb:g} GB VRAM")
    elif data.other_gpu:
        parts.append("CUDA yok")
    if data.ram_gb:
        parts.append(f"{data.ram_gb:g} GB RAM")
    if data.cpu_threads:
        parts.append(f"{data.cpu_threads} iş parçacığı")
    return " • ".join(parts)
