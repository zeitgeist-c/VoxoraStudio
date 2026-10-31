"""
Voxora Studio - GPU detection helpers (Windows).

DirectML install decision: has_directml_capable_gpu() = has_amd_gpu() and not has_nvidia_gpu()

setup_env.py and smoke_test.py import from this module.
"""
from __future__ import annotations

import shutil
import subprocess

NVIDIA_MARKERS = ["nvidia", "geforce", "quadro", "tesla", "rtx", "gtx"]
AMD_MARKERS = ["amd ", "radeon", "rx ", "ati ", "arc", "adreno"]


def _list_video_controllers() -> str:
    """Windows WMI: returns Win32_VideoController names lowercased.

    On failure (no PowerShell, timeout, permissions) returns an empty string.
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
    """Is an NVIDIA graphics card present?

    Fast check via nvidia-smi first; WMI marker scan on failure.
    """
    nvidia_smi = shutil.which("nvidia-smi")
    if nvidia_smi:
        result = subprocess.run([nvidia_smi, "-L"], capture_output=True, text=True)
        if result.returncode == 0 and "GPU" in result.stdout:
            return True
    names = _list_video_controllers()
    return any(m in names for m in NVIDIA_MARKERS)


def has_amd_gpu() -> bool:
    """AMD Radeon, Intel Arc, Qualcomm Adreno detection.

    DirectML runs on all of these vendors.
    """
    names = _list_video_controllers()
    return any(m in names for m in AMD_MARKERS)


def has_directml_capable_gpu() -> bool:
    """Is installing the DirectML package needed?

    With NVIDIA, CUDA is preferred and DirectML is skipped.
    Otherwise DirectML is installed when AMD/Arc/Adreno is present.
    """
    return has_amd_gpu() and not has_nvidia_gpu()
