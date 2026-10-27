"""
Voxora Studio - ses çalma (dizi / WAV / MP3 -> hoparlör).

sounddevice üzerinden çaldığı için MP3 codec sorunu yok.
QMediaPlayer kullanmıyoruz (Qt6'da MP3 codec ayrı kurulum gerektirir).

Ses verisi numpy float32'dir; torch bağımlılığı kaldırıldı (bkz. tts_engine).
"""
from __future__ import annotations

import logging

import numpy as np
import sounddevice as sd
import soundfile as sf

from file_utils import bundled_bin as _bundled_bin

log = logging.getLogger(__name__)


# ffmpeg yoksa pydub MP3 okuyamaz; lazy import + uyarı.
try:
    from pydub import AudioSegment

    _HAS_PYDUB = True
    # Exe içine gömülü ffmpeg varsa pydub'a bildir
    _ffmpeg = _bundled_bin("ffmpeg.exe")
    _ffprobe = _bundled_bin("ffprobe.exe")
    if _ffmpeg:
        AudioSegment.converter = _ffmpeg
        log.info("ffmpeg bundled: %s", _ffmpeg)
    if _ffprobe:
        AudioSegment.ffprobe = _ffprobe
        log.info("ffprobe bundled: %s", _ffprobe)
except Exception as e:
    _HAS_PYDUB = False
    log.warning("pydub yüklenemedi: %s (MP3 çalma/kayıt devre dışı)", e)


def _as_mono_float32(audio) -> np.ndarray:
    """Herhangi bir ses girdisini (numpy/torch/liste) float32 mono diziye çevir."""
    if hasattr(audio, "detach"):  # torch tensörü geldiyse
        audio = audio.detach().cpu().numpy()
    data = np.asarray(audio, dtype=np.float32)
    if data.ndim > 1:
        data = data.reshape(-1)
    return data


def play_tensor(wav, sr: int, blocking: bool = False) -> None:
    """Ses dizisi -> sounddevice.play (dosya yazmaz, hızlı).

    Adı geriye dönük uyumluluk için korundu; artık numpy bekler, torch
    tensörü de kabul edilir.
    """
    sd.play(_as_mono_float32(wav), samplerate=sr)
    if blocking:
        sd.wait()


def _read_via_pydub(path: str) -> tuple[np.ndarray, int]:
    """pydub (ffmpeg) ile çöz: soundfile'ın tanımadığı kaplar için yedek yol."""
    if not _HAS_PYDUB:
        raise RuntimeError("Ses çözülemedi; pydub/ffmpeg gerekli.")
    seg = AudioSegment.from_file(path).set_channels(1).set_sample_width(2)
    arr = np.array(seg.get_array_of_samples(), dtype=np.float32) / 32768.0
    return arr, int(seg.frame_rate)


def play_file(path: str, blocking: bool = False) -> None:
    """WAV/FLAC/OGG/OPUS/MP3 çal → hoparlör. Tek API.

    Ayrıştırma sırası: önce ``soundfile`` (WAV/FLAC/OGG/OPUS), olmazsa ``pydub``
    + ffmpeg (MP3, M4A vb.). Eskiden yalnız ``.wav`` ve ``.mp3`` tanınıyordu;
    OPUS uygulamanın kendi çıktı biçimi olduğu hâlde geçmişte "Çal" düğmesi
    ``ValueError: Desteklenmeyen format: .opus`` ile sessizce düşüyordu.
    """
    try:
        data, sr = sf.read(path, dtype="float32")
    except Exception:
        data, sr = _read_via_pydub(path)
    sd.play(data, samplerate=sr)
    if blocking:
        sd.wait()


def stop() -> None:
    sd.stop()
