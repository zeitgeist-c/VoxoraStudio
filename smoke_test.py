r"""
Voxora Studio smoke test - hafif ve --full modlu.

Default (light): unit test suite + import + ortam.
--full: light + TTS motor + sentez (ağ bağımlı).

Çalıştırma:
  .venv\Scripts\python.exe smoke_test.py             # light
  .venv\Scripts\python.exe smoke_test.py --full      # full (TTS motor + sentez)
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import traceback
from pathlib import Path


# Kritik: yoksa smoke fail.
CRITICAL_IMPORTS = (
    "numpy", "torch", "torchaudio", "PyQt6", "sounddevice", "soundfile",
    "pydub", "send2trash", "PyInstaller", "ema_lightning", "normalizer_tr",
)
# Bilgilendirici: yoksa uyarı (kullanıcı isteğe bağlı).
INFO_IMPORTS = ("onnxruntime",)
# Yerel modüller: yoksa smoke fail.
LOCAL_IMPORTS = ("chunker", "tts_engine", "file_utils", "config", "app.branding")


def _section(title: str) -> None:
    print("\n" + "=" * 60)
    print(f"[{title}]")
    print("=" * 60)


def run_unit_tests() -> bool:
    """tests/ dizinindeki unittest keşfi."""
    _section("1/4 Unit test suite")
    result = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
    )
    return result.returncode == 0


def check_critical_imports() -> bool:
    """Kritik paket importları."""
    _section("2/4 Kritik import'lar")
    failed = []
    for name in CRITICAL_IMPORTS:
        try:
            mod = __import__(name)
            ver = getattr(mod, "__version__", "?")
            print(f"  OK: {name} ({ver})")
        except Exception as e:
            print(f"  [HATA] {name}: {e}")
            failed.append(name)
    if failed:
        print(f"Eksik paketler: {failed}. Düzeltme: setup.bat çalıştır.")
    return not failed


def check_local_imports() -> bool:
    """Yerel modül importları."""
    print("\n  Yerel modüller:")
    failed = []
    for name in LOCAL_IMPORTS:
        try:
            __import__(name)
            print(f"    OK: {name}")
        except Exception as e:
            print(f"    [HATA] {name}: {e}")
            failed.append(name)
    return not failed


def check_environment() -> bool:
    """GPU, DirectML, ffmpeg, Perth, Chatterbox bilgisi."""
    _section("3/4 Ortam bilgisi")
    try:
        import torch
        print(f"  torch: {torch.__version__}")
        print(f"  CUDA: {torch.cuda.is_available()}")
        if torch.cuda.is_available():
            print(f"  GPU: {torch.cuda.get_device_name(0)}")
            print(f"  CUDA versiyon: {torch.version.cuda}")
            t = torch.tensor([1.0], device="cuda") + 2
            print(f"  CUDA tensor test: {t.item()}")
    except Exception as e:
        print(f"  torch error: {e}")

    for name in INFO_IMPORTS:
        try:
            __import__(name)
        except Exception as e:
            print(f"  [BİLGİ] {name} yok: {e}")
            continue

        try:
            import onnxruntime as ort
            providers = ort.get_available_providers()
            print(f"  onnx providers: {providers}")
            try:
                from scripts.gpu_detect import has_directml_capable_gpu
                hardware_candidate = has_directml_capable_gpu()
                actual = "DmlExecutionProvider" in providers
                print(
                    "  DirectML: "
                    f"donanım_adayı={hardware_candidate}, provider_kurulu={actual}"
                )
            except Exception as e:
                print(f"  [BİLGİ] gpu_detect atlandı: {e}")
        except Exception as e:
            print(f"  onnxruntime error: {e}")

    try:
        import perth
        w = perth.PerthImplicitWatermarker()
        print(f"  perth watermarker: {type(w).__module__}")
    except Exception as e:
        print(f"  [BİLGİ] perth watermarker yok: {e}")

    try:
        from chatterbox.mtl_tts import ChatterboxMultilingualTTS
        print("  chatterbox import: OK")
    except Exception as e:
        print(f"  [BİLGİ] chatterbox import: {e}")

    try:
        import ema_lightning
        print(f"  ema-lightning import: OK ({ema_lightning.__version__})")
    except Exception as e:
        print(f"  [BİLGİ] ema-lightning import: {e}")

    bundled_ffmpeg = Path(__file__).resolve().parent / "bin" / "ffmpeg.exe"
    ffmpeg = "Var" if shutil.which("ffmpeg") or bundled_ffmpeg.is_file() else "Yok"
    print(f"  ffmpeg: {ffmpeg}")
    return True


def run_integration_test(keep_output: bool) -> bool:
    """TTS motor + kısa sentez (ağır)."""
    _section("4/4 TTS entegrasyon (--full)")
    out_path = None
    try:
        from config import DEFAULT_OUTPUT_DIR
        from tts_engine import TTSEngine
        import soundfile as sf
        print("Motor yükleniyor (ilk çalışma model indirebilir)...")
        engine = TTSEngine()
        print(f"  engine: {type(engine.engine).__name__} device: {engine.device_name}")
        text = "Merhaba dünya. Bu bir Türkçe ses sentezi testidir."
        print(f"Sentez: '{text}'...")
        wav, sr = engine.synthesize(text)
        os.makedirs(DEFAULT_OUTPUT_DIR, exist_ok=True)
        out_path = os.path.join(DEFAULT_OUTPUT_DIR, "smoke_test.wav")
        sf.write(out_path, wav.squeeze().cpu().numpy(), sr)
        seconds = round(wav.shape[-1] / sr, 2)
        print(f"OK: {out_path} ({seconds} sn @ {sr} Hz)")
        return True
    except Exception:
        print("[HATA] Entegrasyon başarısız:")
        traceback.print_exc()
        return False
    finally:
        if out_path and os.path.exists(out_path) and not keep_output:
            try:
                os.remove(out_path)
                print(f"  (çıktı silindi: {out_path})")
            except Exception:
                pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Voxora Studio smoke test")
    parser.add_argument("--full", action="store_true",
                        help="TTS motor + sentez dahil et (ağır, network gerekir)")
    parser.add_argument("--no-units", action="store_true",
                        help="Unit test suite atla")
    parser.add_argument("--keep-output", action="store_true",
                        help="smoke_test.wav çıktısını silme (sadece --full ile)")
    args = parser.parse_args()

    failures = 0

    if not args.no_units:
        if not run_unit_tests():
            failures += 1
            print("[HATA] Unit test'ler başarısız.")
    if not check_critical_imports():
        failures += 1
    if not check_local_imports():
        failures += 1
    check_environment()
    if args.full:
        if not run_integration_test(args.keep_output):
            failures += 1

    _section("ÖZET")
    if failures == 0:
        print("TÜM KONTROLLER BAŞARILI.")
        return 0
    print(f"{failures} BAŞARISIZLIK VAR.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
