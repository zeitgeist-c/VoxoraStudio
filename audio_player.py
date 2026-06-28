"""
txttoTTS - ses çalma (tensor / WAV / MP3 -> hoparlör).

sounddevice üzerinden çaldığı için MP3 codec sorunu yok.
QMediaPlayer kullanmıyoruz (Qt6'da MP3 codec ayrı kurulum gerektirir).
"""
from __future__ import annotations

import logging
import os

import numpy as np
import sounddevice as sd
import soundfile as sf
import torch

log = logging.getLogger(__name__)

# ffmpeg yoksa pydub MP3 okuyamaz; lazy import + uyarı.
try:
    from pydub import AudioSegment

    _HAS_PYDUB = True
except Exception as e:
    _HAS_PYDUB = False
    log.warning("pydub yüklenemedi: %s (MP3 çalma/kayıt devre dışı)", e)


def play_tensor(wav: torch.Tensor, sr: int, blocking: bool = False) -> None:
    """PyTorch tensor -> numpy -> sounddevice.play (dosya yazmaz, hızlı)."""
    data = wav.squeeze().detach().cpu().numpy().astype(np.float32)
    sd.play(data, samplerate=sr)
    if blocking:
        sd.wait()


def play_file(path: str, blocking: bool = False) -> None:
    """WAV: soundfile.read; MP3: pydub -> numpy. Tek API."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".wav":
        data, sr = sf.read(path, dtype="float32")
    elif ext == ".mp3":
        if not _HAS_PYDUB:
            raise RuntimeError("MP3 çalma için pydub gerekli (ve dolayısıyla ffmpeg).")
        seg = AudioSegment.from_mp3(path).set_channels(1).set_sample_width(2)
        arr = np.array(seg.get_array_of_samples(), dtype=np.float32) / 32768.0
        sr = seg.frame_rate
        data = arr
    else:
        raise ValueError(f"Desteklenmeyen format: {ext}")
    sd.play(data, samplerate=sr)
    if blocking:
        sd.wait()


def stop() -> None:
    sd.stop()


def is_playing() -> bool:
    try:
        stream = sd.get_stream()
        return bool(stream and stream.active)
    except Exception:
        return False
