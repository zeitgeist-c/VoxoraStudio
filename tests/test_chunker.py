from __future__ import annotations

import unittest

from chunker import split_into_chunks


class ChunkerTests(unittest.TestCase):
    def test_empty_text_returns_empty_list(self):
        self.assertEqual(split_into_chunks("   "), [])

    def test_splits_turkish_sentences(self):
        self.assertEqual(
            split_into_chunks("Merhaba dünya. Nasılsın? İyiyim!"),
            ["Merhaba dünya. Nasılsın? İyiyim!"],
        )

    def test_splits_unicode_ellipsis(self):
        self.assertEqual(
            split_into_chunks("Bekle… Sonra devam et.", max_chars=12),
            ["Bekle…", "Sonra devam", "et."],
        )

    def test_long_sentence_is_cut_to_limit(self):
        chunks = split_into_chunks("abcde" * 10, max_chars=8)
        self.assertTrue(all(len(chunk) <= 8 for chunk in chunks))
        self.assertEqual("".join(chunks), "abcde" * 10)

    def test_year_with_dot_not_split(self):
        self.assertEqual(
            split_into_chunks("2024. yılında şirket geliri %15 arttı."),
            ["2024. yılında şirket geliri %15 arttı."],
        )

    def test_page_chapter_with_dot_not_split(self):
        self.assertEqual(
            split_into_chunks("sayfa 12. bölümde"),
            ["sayfa 12. bölümde"],
        )

    def test_decimal_number_not_split(self):
        self.assertEqual(
            split_into_chunks("Pi yaklaşık 3.14 değerindedir. Bu bir sabittir.", max_chars=35),
            ["Pi yaklaşık 3.14 değerindedir.", "Bu bir sabittir."],
        )

    def test_date_like_real_sentence_split(self):
        # "15. oldu" -> öncesi rakam olduğu için nokta cümle sonu değil.
        # İkinci cümle bağımsız: öncesi harf, sonrası büyük harf -> cümle sonu.
        self.assertEqual(
            split_into_chunks("Bugün 15. oldu. Yarın gidiyoruz.", max_chars=20),
            ["Bugün 15. oldu.", "Yarın gidiyoruz."],
        )

    def test_question_and_exclamation_unaffected_by_numbers(self):
        self.assertEqual(
            split_into_chunks("Saat 12 mi? Hayır 13! Tamam.", max_chars=12),
            ["Saat 12 mi?", "Hayır 13!", "Tamam."],
        )

    def test_existing_ellipsis_still_works(self):
        # Mevcut davranış regresyonu.
        self.assertEqual(
            split_into_chunks("Bekle… Sonra devam et.", max_chars=12),
            ["Bekle…", "Sonra devam", "et."],
        )


if __name__ == "__main__":
    unittest.main()
