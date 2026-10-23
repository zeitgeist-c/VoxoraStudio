"""Clean runtime probe: run with Python -I -S, never development site-packages."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import socket
import sys
import time
from unittest.mock import patch


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--models-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not sys.flags.isolated or not sys.flags.no_site:
        parser.error("run this probe with -I -S to prevent development dependency leakage")
    runtime_root = args.runtime_root.resolve()
    runtime = runtime_root / "site-packages"
    sys.path.insert(0, str(runtime))
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    os.environ["VOXORA_MODELS_DIR"] = str(args.models_root.resolve())
    os.environ["HF_HUB_OFFLINE"] = "1"
    from app import engine_pack
    started = time.perf_counter()
    with patch.object(engine_pack, "engine_root", return_value=runtime_root), \
         patch.object(socket.socket, "connect", side_effect=AssertionError("network forbidden")):
        from tts_engine import TTSEngine
        import numpy as np
        import soundfile as sf
        import torch
        assert Path(torch.__file__).is_relative_to(runtime), torch.__file__
        assert Path(np.__file__).is_relative_to(runtime), np.__file__
        engine = TTSEngine(engine_name="chatterbox", status_callback=lambda s: print(s, flush=True))
        audio, sample_rate = engine.synthesize("Merhaba.", language_id="tr")
        assert sample_rate == 24000 and audio.size and np.isfinite(audio).all()
        peak = float(np.max(np.abs(audio)))
        assert peak > 0
        args.output.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(args.output), audio, sample_rate)
        result = {"sample_rate": sample_rate, "samples": audio.size, "peak": peak,
                  "seconds": round(time.perf_counter() - started, 2), "torch": torch.__file__}
        print(json.dumps(result), flush=True)
        args.output.with_suffix(".json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
