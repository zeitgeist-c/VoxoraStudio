"""
txttoTTS - uygulama sabitleri.

Dil listesi, referans ses örneği metni ve üretim hazır ayarları.
"""
from __future__ import annotations

__all__ = [
    "LANGUAGES",
    "REFERENCE_SAMPLE_TEXT",
    "PRESETS",
    "THEMES",
    "THEME_LIGHT",
    "THEME_DARK",
    "THEME_SYSTEM",
    "LANGUAGE_SAMPLES",
    "WARN_CHUNK_COUNT",
    "CONFIRM_CHUNK_COUNT",
]

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

# Chatterbox Multilingual V3 önerilerine göre (HF model kartı + resmi kaynak kodu):
# - cfg_weight: model default 0.5; hızlı/ekspresif için 0.3
# - temperature: 0.55-0.75 arası doğallık; 0.85+ çeşitlilik
# - repetition_penalty: model default 1.2; artifact riski için 1.2-1.6
# - exaggeration: 0.5 nötr; 0.7+ ekspresif (yüksek = hızlanır, cfg düşürülmeli)
# - speed: pipeline seviyesinde time-stretch; modeli etkilemez
# - pause: pipeline seviyesinde chunk arası sessizlik
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

# Tema seçenekleri (Ayarlar → Sistem)
THEME_LIGHT = "light"
THEME_DARK = "dark"
THEME_SYSTEM = "system"

THEMES = (THEME_LIGHT, THEME_DARK, THEME_SYSTEM)

# Üretim uyarı eşikleri
WARN_CHUNK_COUNT = 20      # INFO uyarı eşiği
CONFIRM_CHUNK_COUNT = 50   # Kullanıcı onayı eşiği

# Dil örnek cümleler (tooltip için)
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