"""
Chatterbox Multilingual V3 ONNX export.

Plan 17: T3 backbone export (iskelet).
Plan 18: S3Gen export.
Plan 19: Vocoder export.

Kullanım:
    python scripts/export_onnx.py
    python scripts/export_onnx.py --output models/ --components t3
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import torch


def export_t3(model, output_dir: Path, device: str = "cpu") -> Path:
    """T3 backbone'i ONNX'e export et.

    Whisper/llama benzeri autoregressive modelin tek-adım forward'u.
    Döngü OnnxEngine'de Python tarafında çalışır; sadece backbone export.

    Plan 17'de tam implementasyon yapılacak (Bash ortamında, chatterbox-tts
    API'sinin T3HuggingfaceBackend.forward incelenmesi gerekli).
    """
    raise NotImplementedError(
        "T3 export Plan 17 uygulama adımında tamamlanacak. "
        "Gerekli: chatterbox-tts API'sinin (T3HuggingfaceBackend.forward) "
        "incelenmesi, dynamic_axes tanımı, KV-cache unwrap."
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Chatterbox ONNX export")
    parser.add_argument("--output", default="models/", help="Çıktı klasörü")
    parser.add_argument("--components", nargs="+", default=["t3"])
    parser.add_argument("--device", default="cpu", help="PyTorch cihaz (export için cpu önerilir)")
    args = parser.parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("Chatterbox modeli yükleniyor...")
    try:
        from chatterbox.mtl_tts import ChatterboxMultilingualTTS
    except ImportError as e:
        print(f"[HATA] chatterbox-tts yüklenemedi: {e}")
        return 1
    model = ChatterboxMultilingualTTS.from_pretrained(device=args.device)

    for component in args.components:
        print(f"Exporting {component}...")
        if component == "t3":
            path = export_t3(model, output_dir, args.device)
        elif component == "s3gen":
            print("[HATA] S3Gen export henüz uygulanmadı (Plan 18).")
            return 1
        elif component == "vocoder":
            print("[HATA] Vocoder export henüz uygulanmadı (Plan 19).")
            return 1
        else:
            print(f"[HATA] Bilinmeyen bileşen: {component}")
            return 1
        print(f"  -> {path}")

    print("Tamamlandı.")
    return 0


if __name__ == "__main__":
    sys.exit(main())