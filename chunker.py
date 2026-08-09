"""
Voxora Studio - metin bölücü.

Uzun metni Chatterbox'un güvenli işleyebileceği parçalara böler.
Önce cümle sonlarını, çok uzun cümlelerde ise virgül/iki nokta/boşluk gibi
daha doğal nefes noktalarını tercih eder.
"""
from __future__ import annotations

import re

from config import DEFAULT_MAX_CHARS_PER_CHUNK

# Cümle sonu: . ! ? … (Unicode U+2026); sonrasında boşluk/newline.
# Nokta için sayı koruması: öncesi veya sonrası rakam ise cümle sonu değil.
#   - "2024. yılında" -> "2024." reddedilir (öncesi rakam).
#   - "3.14 değerindedir" -> "3." reddedilir (sonrası rakam).
#   - "Bugün 15. oldu. Yarın" -> ilk "." reddedilir (öncesi rakam), ikinci kabul.
SENTENCE_SPLIT = re.compile(
    r"(?:"
    r"(?<=[!?…])\s+"
    r"|(?<=[^\d]\.)\s+"
    r")"
)
SOFT_BREAK_CHARS = (";", ":", ",", " ")


def _split_long_sentence(sentence: str, max_chars: int) -> list[str]:
    parts: list[str] = []
    remaining = sentence.strip()
    min_good_cut = max(80, int(max_chars * 0.45))

    while len(remaining) > max_chars:
        window = remaining[:max_chars + 1]
        cut_at = -1

        for marker in SOFT_BREAK_CHARS:
            pos = window.rfind(marker)
            if pos >= min_good_cut:
                cut_at = pos + (0 if marker == " " else 1)
                break

        if cut_at < min_good_cut:
            cut_at = max_chars

        part = remaining[:cut_at].strip()
        if part:
            parts.append(part)
        remaining = remaining[cut_at:].strip()

    if remaining:
        parts.append(remaining)
    return parts


def split_into_chunks(text: str, max_chars: int = DEFAULT_MAX_CHARS_PER_CHUNK) -> list[str]:
    """
    Metni cümle bazlı böl; çok uzun cümleleri doğal nefes noktalarında kır.
    Boş metin -> [].
    """
    text = text.strip()
    if not text:
        return []

    sentences = SENTENCE_SPLIT.split(text)
    chunks: list[str] = []
    current = ""

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue

        if len(current) + len(sentence) + 1 <= max_chars:
            current = (current + " " + sentence).strip() if current else sentence
            continue

        if current:
            chunks.append(current)
            current = ""

        if len(sentence) > max_chars:
            chunks.extend(_split_long_sentence(sentence, max_chars))
        else:
            current = sentence

    if current:
        chunks.append(current)
    return chunks
