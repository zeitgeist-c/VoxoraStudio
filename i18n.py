"""VoxoraStudio 13 dil sözleşmesi: TR anahtarlı sözlük, EN default.

Mevcut UI metinleri Türkçe yazıldığından anahtar olarak orijinal Türkçe
metin kullanılır; İngilizce dahil 12 dil TABLES'ta çevrilir.
- Yeni kurulumda varsayılan İngilizce; OS dili ezmez.
- Kayıtlı açık tercih korunur.
- Bilinmeyen kod EN'ye düşer (release kapısında eksik = kırmızı).
"""

import json
import os

LANGUAGES = [
    ("en", "English"),
    ("tr", "Türkçe"),
    ("de", "Deutsch"),
    ("es", "Español"),
    ("fr", "Français"),
    ("it", "Italiano"),
    ("pt-BR", "Português (Brasil)"),
    ("ru", "Русский"),
    ("pl", "Polski"),
    ("nl", "Nederlands"),
    ("zh-CN", "简体中文"),
    ("ja", "日本語"),
    ("ko", "한국어"),
]

CODES = {code for code, _ in LANGUAGES}

_lang = "en"


def resolve(code):
    if code in CODES:
        return code
    return "en"


def set_language(code):
    global _lang
    _lang = resolve(code)


def language():
    return _lang


def t(key, _fmt=True, **kwargs):
    text = key
    table = TABLES.get(_lang)
    out = table.get(text, text) if table else text
    if not kwargs or not _fmt:
        return out
    try:
        return out.format(**kwargs)
    except (KeyError, IndexError, ValueError):
        return out


TABLES = {}

def ui_languages():
    return list(LANGUAGES)


def _load():
    global TABLES
    if TABLES:
        return
    try:
        _en = {}
        for _i in (1, 2, 3, 4, 5):
            try:
                _ad = "EN%d" % _i if _i > 1 else "EN"
                _m = __import__("i18n_strings_en%d" % _i, fromlist=[_ad])
                _p = getattr(_m, _ad, None)
                if isinstance(_p, dict):
                    _en.update(_p)
            except ImportError:
                pass
        TABLES = {"en": _en, "tr": {}}
        for _kod, _ad in (("de", "DE"), ("es", "ES"), ("fr", "FR"),
                           ("it", "IT"), ("pt-BR", "PB"), ("ru", "RU"),
                           ("pl", "PL"), ("nl", "NL"), ("zh-CN", "ZH"),
                           ("ja", "JA"), ("ko", "KO")):
            _bir = {}
            for _i in (1, 2, 3, 4, 5):
                try:
                    _m = __import__("i18n_strings_%s%d" % (_ad.lower(), _i),
                                     fromlist=["%s%d" % (_ad, _i)])
                    _parca = getattr(_m, "%s%d" % (_ad, _i), None)
                    if isinstance(_parca, dict):
                        _bir.update(_parca)
                except ImportError:
                    pass
            if _bir:
                TABLES[_kod] = _bir
    except ImportError:
        TABLES = {"en": {}, "tr": {}}


_load()
