"""
Voxora Studio - varsayılanlar.
"""
from __future__ import annotations

# TTS
DEFAULT_LANGUAGE_ID = "tr"
DEFAULT_EXAGGERATION = 0.5
DEFAULT_CFG_WEIGHT = 0.5

# Ses motoru seçenekleri
# - chatterbox: Chatterbox Multilingual V3 (16 dil + referans sesle klonlama)
# - ema: EMA Lightning (yalnız Türkçe, tek ses, ~34 MB, CPU'da bile hızlı)
ENGINE_CHATTERBOX = "chatterbox"
ENGINE_EMA = "ema"
DEFAULT_ENGINE = ENGINE_CHATTERBOX
VALID_ENGINES = (ENGINE_CHATTERBOX, ENGINE_EMA)

# Chunking
DEFAULT_MAX_CHARS_PER_CHUNK = 400

# Çıktı
DEFAULT_OUTPUT_DIR = "outputs"
DEFAULT_LOG_DIR = "logs"

# Çıktı biçimi ve kalite (Ayarlar → Çıktı → Kayıt ve Kalite)
# - wav: kayıpsız (arşiv)  - mp3: her yerde çalar  - opus: en küçük dosya
OUTPUT_FORMAT_WAV = "wav"
OUTPUT_FORMAT_MP3 = "mp3"
OUTPUT_FORMAT_OPUS = "opus"
VALID_OUTPUT_FORMATS = (OUTPUT_FORMAT_WAV, OUTPUT_FORMAT_MP3, OUTPUT_FORMAT_OPUS)
DEFAULT_OUTPUT_FORMAT = OUTPUT_FORMAT_MP3
DEFAULT_MP3_BITRATE = "320k"
DEFAULT_OPUS_BITRATE = "64k"
OUTPUT_FORMAT_EXTENSIONS = {
    OUTPUT_FORMAT_WAV: ".wav",
    OUTPUT_FORMAT_MP3: ".mp3",
    OUTPUT_FORMAT_OPUS: ".opus",
}


