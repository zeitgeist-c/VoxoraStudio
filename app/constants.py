"""
Voxora Studio - uygulama sabitleri.

Dil listesi, referans ses örneği metni, üretim hazır ayarları ve motor seçenekleri.
"""
from __future__ import annotations

from config import (
    OUTPUT_FORMAT_MP3,
    OUTPUT_FORMAT_OPUS,
    OUTPUT_FORMAT_WAV,
)

__all__ = [
    "LANGUAGES",
    "REFERENCE_SAMPLE_TEXT",
    "PRESETS",
    "THEMES",
    "THEME_LIGHT",
    "THEME_DARK",
    "THEME_SYSTEM",
    "LANGUAGE_SAMPLES",
    "OUTPUT_FORMAT_OPTIONS",
    "OUTPUT_QUALITY_OPTIONS",
    "OUTPUT_FORMAT_HELP",
    "quality_options_for",
    "format_label",
    "WARN_CHUNK_COUNT",
    "CONFIRM_CHUNK_COUNT",
]

# Output format tiles (Settings → Output): (key, name, short description)
OUTPUT_FORMAT_OPTIONS = (
    (OUTPUT_FORMAT_WAV, "WAV", "kayıpsız · arşiv"),
    (OUTPUT_FORMAT_MP3, "MP3", "her yerde çalar"),
    (OUTPUT_FORMAT_OPUS, "OPUS", "en küçük dosya"),
)

# Quality options by format: (value, label)
OUTPUT_QUALITY_OPTIONS = {
    OUTPUT_FORMAT_WAV: (("", "Kayıpsız — kalite seçimi yok"),),
    OUTPUT_FORMAT_MP3: (
        ("128k", "Konuşma (128 kbps)"),
        ("192k", "Podcast (192 kbps)"),
        ("320k", "Yüksek kalite (320 kbps)"),
    ),
    OUTPUT_FORMAT_OPUS: (
        ("32k", "Konuşma (32 kbps)"),
        ("64k", "Dengeli (64 kbps)"),
        ("96k", "Yüksek kalite (96 kbps)"),
    ),
}

OUTPUT_FORMAT_HELP = (
    "Seçenekler biçime göre değişir — MP3: Konuşma 128 · Podcast 192 · Yüksek kalite 320 | "
    "OPUS: Konuşma 32 · Dengeli 64 · Yüksek kalite 96 | WAV: kayıpsız (seçim yok)"
)


def quality_options_for(fmt: str):
    """Biçime ait kalite seçenekleri; bilinmeyen biçimde WAV listesi döner."""
    return OUTPUT_QUALITY_OPTIONS.get(fmt, OUTPUT_QUALITY_OPTIONS[OUTPUT_FORMAT_WAV])


def format_label(fmt: str) -> str:
    """Biçim anahtarının görünen adı (wav→WAV)."""
    for key, name, _description in OUTPUT_FORMAT_OPTIONS:
        if key == fmt:
            return name
    return (fmt or "").upper()

LANGUAGES = {
    "tr": "Türkçe",
    "en": "İngilizce",
    "de": "Almanca",
    "fr": "Fransızca",
    "es": "İspanyolca",
    "it": "İtalyanca",
    "pt": "Portekizce",
    "ru": "Rusça",
    "ja": "Japonca",
    "ko": "Korece",
    "zh": "Çince",
    "ar": "Arapça",
    "hi": "Hintçe",
    "nl": "Flemenkçe",
    "pl": "Lehçe",
    "sv": "İsveççe",
}

REFERENCE_SAMPLE_TEXT = (
    "Merhaba. Bu ses örneği, konuşma tonumu ve telaffuzumu tanıtmak için hazırlanmıştır. "
    "Bugün sakin, anlaşılır ve doğal bir şekilde konuşuyorum. "
    "Kısa cümleler, farklı sesler ve net duraklamalar kullanıyorum. "
    "Bu kayıt, yeni üretilecek sesin bana daha iyi benzemesine yardımcı olabilir."
)

# Per Chatterbox Multilingual V3 recommendations (HF model card + official source):
# - cfg_weight: model default 0.5; 0.3 for fast/expressive
# - temperature: 0.55-0.75 for naturalness; 0.85+ for variety
# - repetition_penalty: model default 1.2; 1.2-1.6 for artifact risk
# - exaggeration: 0.5 neutral; 0.7+ expressive (high = faster, lower cfg)
# - speed: pipeline seviyesinde time-stretch; modeli etkilemez
# - pause: pipeline-level silence between chunks
PRESETS = {
    "Dengeli":                {"speed": 1.00, "exaggeration": 0.50, "cfg": 0.50, "temperature": 0.65, "repetition": 1.30, "pause": 0.35},
    "Hızlı üretim":           {"speed": 1.18, "exaggeration": 0.45, "cfg": 0.35, "temperature": 0.70, "repetition": 1.30, "pause": 0.20},
    "Daha doğal":             {"speed": 0.95, "exaggeration": 0.50, "cfg": 0.50, "temperature": 0.65, "repetition": 1.40, "pause": 0.45},
    "Daha ifadeli":           {"speed": 1.00, "exaggeration": 0.75, "cfg": 0.35, "temperature": 0.90, "repetition": 1.30, "pause": 0.35},
    "Anlatıcı":               {"speed": 0.90, "exaggeration": 0.40, "cfg": 0.50, "temperature": 0.40, "repetition": 1.30, "pause": 0.50},
    "Doğal kalite":           {"speed": 0.95, "exaggeration": 0.50, "cfg": 0.55, "temperature": 0.60, "repetition": 1.40, "pause": 0.45},
    "Referans sese sadık":    {"speed": 1.00, "exaggeration": 0.50, "cfg": 0.75, "temperature": 0.55, "repetition": 1.60, "pause": 0.40},
    "Sıcak Anlatıcı":         {"speed": 0.92, "exaggeration": 0.65, "cfg": 0.45, "temperature": 0.55, "repetition": 1.40, "pause": 0.50},
}

# Theme options (Settings → System)
THEME_LIGHT = "light"
THEME_DARK = "dark"
THEME_SYSTEM = "system"

THEMES = (THEME_LIGHT, THEME_DARK, THEME_SYSTEM)

# Production warning thresholds
WARN_CHUNK_COUNT = 20      # INFO warning threshold
CONFIRM_CHUNK_COUNT = 50   # User confirmation threshold

# Language sample sentences (for tooltips)
LANGUAGE_SAMPLES = {
    "tr": "Merhaba dünya",
    "en": "Hello world",
    "de": "Hallo Welt",
    "fr": "Bonjour le monde",
    "es": "Hola mundo",
    "it": "Ciao mondo",
    "pt": "Olá mundo",
    "ru": "Привет мир",
    "ja": "こんにちは世界",
    "ko": "안녕하세요 세계",
    "zh": "你好世界",
    "ar": "مرحبا بالعالم",
    "hi": "नमस्ते दुनिया",
    "nl": "Hallo wereld",
    "pl": "Witaj świecie",
    "sv": "Hej världen",
}
