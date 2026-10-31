"""VoxoraStudio 13-language contract: TR-keyed dictionary, EN default.

Current UI texts are written in Turkish, so the original Turkish
text is used as the key; 12 languages including English are translated in TABLES.
- Fresh installs default to English; the OS language never wins.
- A saved explicit preference is kept.
- Unknown codes fall back to EN (missing = red at the release gate).
"""

import json
import os

import i18n_strings_tables

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
for _code, _parts in {
    "en": ("EN", "EN2", "EN3", "EN4", "EN5"),
    "de": ("DE1", "DE2", "DE3", "DE4", "DE5"),
    "es": ("ES1", "ES2", "ES3", "ES4", "ES5"),
    "fr": ("FR1", "FR2", "FR3", "FR4", "FR5"),
    "it": ("IT1", "IT2", "IT3", "IT4", "IT5"),
    "pt-BR": ("PB1", "PB2", "PB3", "PB4", "PB5"),
    "ru": ("RU1", "RU2", "RU3", "RU4", "RU5"),
    "pl": ("PL1", "PL2", "PL3", "PL4", "PL5"),
    "nl": ("NL1", "NL2", "NL3", "NL4", "NL5"),
    "zh-CN": ("ZH1", "ZH2", "ZH3", "ZH4", "ZH5"),
    "ja": ("JA1", "JA2", "JA3", "JA4", "JA5"),
    "ko": ("KO1", "KO2", "KO3", "KO4", "KO5"),
}.items():
    _merged = {}
    for _part in _parts:
        _merged.update(getattr(i18n_strings_tables, _part))
    TABLES[_code] = _merged
TABLES["tr"] = {}

# Packaging audit hook: a catalogue module that fails to import is listed here.
LOAD_ERRORS = []

def ui_languages():
    return list(LANGUAGES)



