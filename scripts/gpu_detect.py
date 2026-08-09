"""
Voxora Studio - GPU tespit yardımcıları (Windows).

DirectML kurulum kararı: has_directml_capable_gpu() = has_amd_gpu() and not has_nvidia_gpu()

setup_env.py ve smoke_test.py bu modülden import eder.
"""
from __future__ import annotations

import shutil
import subprocess

NVIDIA_MARKERS = ["nvidia", "geforce", "quadro", "tesla", "rtx", "gtx"]
AMD_MARKERS = ["amd ", "radeon", "rx ", "ati ", "arc", "adreno"]


def _list_video_controllers() -> str:
    """Windows WMI: Win32_VideoController adlarını küçük harf olarak döndürür.

    Hata durumunda (PowerShell yok, timeout, izin) boş string döner.
    """
    try:
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.stdout.lower()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return ""


def has_nvidia_gpu() -> bool:
    """NVIDIA ekran kartı var mı?

    Önce nvidia-smi ile hızlı kontrol; başarısızsa WMI marker taraması.
    """
    nvidia_smi = shutil.which("nvidia-smi")
    if nvidia_smi:
        result = subprocess.run([nvidia_smi, "-L"], capture_output=True, text=True)
        if result.returncode == 0 and "GPU" in result.stdout:
            return True
    names = _list_video_controllers()
    return any(m in names for m in NVIDIA_MARKERS)


def has_amd_gpu() -> bool:
    """AMD Radeon, Intel Arc, Qualcomm Adreno tespiti.

    DirectML bu üreticilerin hepsinde çalışır.
    """
    names = _list_video_controllers()
    return any(m in names for m in AMD_MARKERS)


def has_directml_capable_gpu() -> bool:
    """DirectML paketini kurmak gerekli mi?

    NVIDIA varsa CUDA tercih edilir; bu durumda DirectML atlanır.
    Aksi halde AMD/Arc/Adreno varsa DirectML kurulur.
    """
    return has_amd_gpu() and not has_nvidia_gpu()
