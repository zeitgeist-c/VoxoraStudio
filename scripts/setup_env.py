from __future__ import annotations

import socket
import subprocess
import sys
from pathlib import Path

from scripts.gpu_detect import has_amd_gpu, has_directml_capable_gpu, has_nvidia_gpu

ROOT = Path(__file__).resolve().parents[1]
PYTHON = Path(sys.executable)
REQUIREMENTS = ROOT / "requirements.txt"

# Windows + pip icin guncel PyTorch CUDA wheel kaynaklari.
# NVIDIA varsa sirasiyla denenir; dogrulanamazsa CPU wheel'e dusulur.
CUDA_INDEXES = [
    ("CUDA 12.8", "https://download.pytorch.org/whl/cu128"),
    ("CUDA 12.6", "https://download.pytorch.org/whl/cu126"),
    ("CUDA 11.8", "https://download.pytorch.org/whl/cu118"),
]
CPU_INDEX = "https://download.pytorch.org/whl/cpu"
DIRECTML_PACKAGE = "onnxruntime-directml"


def run(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
    print("[cmd]", " ".join(args))
    return subprocess.run(args, cwd=ROOT, check=check)


def pip_install(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
    return run([str(PYTHON), "-m", "pip", "install", *args], check=check)


def check_internet() -> None:
    """Internetli kurulum varsayilir; pip indirmeleri oncesi hizli kontrol."""
    try:
        with socket.create_connection(("pypi.org", 443), timeout=8):
            pass
    except OSError as e:
        raise RuntimeError(
            "Internet baglantisi dogrulanamadi. Paketleri indirmek icin internet gerekli."
        ) from e
    print("[OK] Internet erisimi var.")


def selected_install_target() -> str:
    if has_nvidia_gpu():
        return "cuda"
    if has_directml_capable_gpu():
        return "directml"
    return "cpu"


def print_hardware_report(target: str) -> None:
    print("[BILGI] Donanim kontrolu:")
    print(f"  NVIDIA GPU: {'var' if has_nvidia_gpu() else 'yok'}")
    print(f"  AMD/Intel/DirectML adayi GPU: {'var' if has_amd_gpu() else 'yok'}")
    print(f"  Secilen kurulum yolu: {target}")


def torch_cuda_available() -> bool:
    code = (
        "import torch; "
        "print(torch.__version__); "
        "print('cuda_available=', torch.cuda.is_available()); "
        "print('cuda_version=', torch.version.cuda); "
        "print('device=', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'cpu')"
    )
    result = subprocess.run([str(PYTHON), "-c", code], cwd=ROOT, capture_output=True, text=True)
    print(result.stdout.strip())
    if result.stderr.strip():
        print(result.stderr.strip())
    return result.returncode == 0 and "cuda_available= True" in result.stdout


def torch_import_ok() -> bool:
    result = subprocess.run([str(PYTHON), "-c", "import torch, torchaudio"], cwd=ROOT)
    return result.returncode == 0


def install_torch(target: str) -> None:
    if target == "cuda":
        for label, index_url in CUDA_INDEXES:
            print(f"[BILGI] {label} destekli PyTorch kurulumu deneniyor...")
            result = pip_install(["--upgrade", "torch", "torchaudio", "--index-url", index_url], check=False)
            if result.returncode != 0:
                print(f"[UYARI] {label} kurulumu basarisiz. Sonraki secenek denenecek.")
                continue
            if torch_cuda_available():
                print(f"[OK] PyTorch GPU/CUDA hazir: {label}")
                return
            print(f"[UYARI] {label} kuruldu ama CUDA aktif gorunmedi.")

        print("[UYARI] CUDA kurulumlari calismadi. CPU PyTorch'a dusuluyor.")

    print("[BILGI] CPU PyTorch kuruluyor...")
    pip_install(["--upgrade", "torch", "torchaudio", "--index-url", CPU_INDEX])
    if not torch_import_ok():
        raise RuntimeError("PyTorch kurulumu dogrulanamadi.")
    print("[OK] CPU PyTorch hazir.")


def install_directml_if_needed(target: str) -> None:
    if target != "directml":
        print("[setup] DirectML paketi atlandi (NVIDIA/CPU yolu secildi).")
        return

    print("[BILGI] AMD/Intel GPU icin DirectML paketi kuruluyor...")
    pip_install(["--upgrade", DIRECTML_PACKAGE])
    code = (
        "import onnxruntime as ort; "
        "providers=ort.get_available_providers(); "
        "print('onnx providers=', providers); "
        "raise SystemExit(0 if 'DmlExecutionProvider' in providers else 1)"
    )
    result = subprocess.run([str(PYTHON), "-c", code], cwd=ROOT)
    if result.returncode == 0:
        print("[OK] DirectML provider dogrulandi.")
    else:
        print("[UYARI] DirectML provider dogrulanamadi. Program CPU fallback ile calisabilir.")


def install_project_requirements() -> None:
    skip = {"torch", "torchaudio", DIRECTML_PACKAGE}
    packages: list[str] = []

    for raw in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        clean = line.split("#", 1)[0].strip()
        if not clean:
            continue
        name = (
            clean.split("==", 1)[0]
            .split(">=", 1)[0]
            .split("<=", 1)[0]
            .split("~=", 1)[0]
            .strip()
            .lower()
        )
        if name in skip:
            print(f"[setup] skip: {name}")
            continue
        packages.append(clean)

    if packages:
        print("[BILGI] Proje paketleri kuruluyor...")
        pip_install(["--upgrade", *packages])


def verify_imports() -> None:
    print("[BILGI] Import testi...")
    code = (
        "import numpy, torch, torchaudio, PyQt6, sounddevice, soundfile, pydub, send2trash; "
        "print('imports OK'); "
        "print('cuda_available=', torch.cuda.is_available()); "
        "print('device=', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'cpu')"
    )
    run([str(PYTHON), "-c", code])


def main() -> int:
    print("[BILGI] Python:", PYTHON)
    check_internet()
    target = selected_install_target()
    print_hardware_report(target)
    pip_install(["--upgrade", "pip"])
    install_torch(target)
    install_directml_if_needed(target)
    install_project_requirements()
    verify_imports()
    print(f"[OK] Kurulum tamamlandi. Aktif kurulum yolu: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
