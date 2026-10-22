"""EMA Lightning ONNX motoru testleri.

İki katman:
  1. Saf mantık (metin bölme, ön işlemci, kare planlama) — model gerekmez.
  2. Gerçek model varsa uçtan uca sentez — yoksa atlanır.

Gerçek model testi bu depoda çalışır çünkü ağırlıklar ``models/ema-onnx``
altında paketle gelir; başka bir kopyada yoksa test sessizce atlanır.
"""
from __future__ import annotations

import unittest
from pathlib import Path

import numpy as np

from app import ema_onnx

MODEL_DIR = Path(__file__).resolve().parents[1] / "models" / "ema-onnx"


class ChunkTextTests(unittest.TestCase):
    def test_short_text_is_one_piece(self):
        pieces = ema_onnx.chunk_text("Merhaba dünya.")
        self.assertEqual(len(pieces), 1)
        self.assertEqual(pieces[0][1], 0.0)  # son parçadan sonra duraklama yok

    def test_long_text_splits_into_several_pieces(self):
        text = "Bu uzun bir metindir. " * 40
        pieces = ema_onnx.chunk_text(text, speed=1.0)
        self.assertGreater(len(pieces), 1)

    def test_piece_ends_with_punctuation(self):
        pieces = ema_onnx.chunk_text("Bir cümle, sonra devam")
        for piece, _pause in pieces:
            self.assertIn(piece[-1], ".!?", f"parça noktalamasız: {piece!r}")

    def test_empty_text_returns_nothing(self):
        self.assertEqual(ema_onnx.chunk_text("   "), [])

    def test_punctuation_free_text_gets_period(self):
        pieces = ema_onnx.chunk_text("noktasiz metin")
        self.assertTrue(pieces[0][0].endswith("."))


class FrontendTests(unittest.TestCase):
    #: Gerçek meta.json sözlüğünün asgari kopyası (tüm harfler şart).
    VOCAB = list(" abcdefghijklmnopqrstuvwxyzçğıöşü.!?,;:'\"-")

    def test_turkish_characters_survive(self):
        frontend = ema_onnx.Frontend(self.VOCAB)
        out = frontend("Çiğdem ıslak örtü şüphe")
        for char in "çğıöşü":
            self.assertIn(char, out)

    def test_uppercase_i_becomes_dotless(self):
        frontend = ema_onnx.Frontend(self.VOCAB)
        self.assertIn("ı", frontend("ISLAK"))

    def test_dotted_capital_i_becomes_i(self):
        frontend = ema_onnx.Frontend(self.VOCAB)
        self.assertIn("i", frontend("İSTANBUL"))

    def test_unknown_characters_are_dropped(self):
        frontend = ema_onnx.Frontend(self.VOCAB)
        out = frontend("merhaba 世界 123")
        self.assertNotIn("世", out)

    def test_typography_is_normalized(self):
        frontend = ema_onnx.Frontend(self.VOCAB + list("'\"-"))
        self.assertNotIn("\u2019", frontend("deneme\u2019s"))

    def test_empty_input_returns_empty(self):
        self.assertEqual(ema_onnx.Frontend(self.VOCAB)("   "), "")


class ModelFilesTests(unittest.TestCase):
    def test_required_files_are_named(self):
        self.assertEqual(
            set(ema_onnx.FILES),
            {"text.onnx", "sound.onnx", "decoder.onnx", "meta.json"},
        )

    def test_models_ready_rejects_missing_files(self):
        self.assertFalse(ema_onnx.models_ready(Path("olmayan-klasor")))

    def test_sample_rate_is_48k(self):
        self.assertEqual(ema_onnx.SAMPLE_RATE, 48_000)


@unittest.skipUnless(
    all((MODEL_DIR / name).is_file() for name in ema_onnx.FILES),
    "EMA ONNX ağırlıkları yok (models/ema-onnx)",
)
class RealSynthesisTests(unittest.TestCase):
    """Gerçek ONNX oturumlarıyla uçtan uca sentez."""

    @classmethod
    def setUpClass(cls):
        cls.engine = ema_onnx.EmaOnnxEngine(where=MODEL_DIR).load()

    def test_synthesis_returns_audio(self):
        audio = self.engine.synthesize("Merhaba, bu bir testtir.", speed=1.0)
        self.assertEqual(audio.dtype, np.float32)
        self.assertGreater(audio.size, 0)
        self.assertEqual(audio.ndim, 1)
        # Kabaca doğru süre: cümle 1-6 saniye arasında olmalı.
        self.assertGreater(audio.size / 48_000, 0.5)
        self.assertLess(audio.size / 48_000, 10.0)

    def test_audio_is_in_normalized_range(self):
        audio = self.engine.synthesize("Ses seviyesi testi.", speed=1.0)
        self.assertGreaterEqual(float(audio.min()), -1.5)
        self.assertLessEqual(float(audio.max()), 1.5)
        self.assertGreater(float(np.abs(audio).max()), 0.01)  # sessiz değil

    def test_speed_shortens_output(self):
        slow = self.engine.synthesize("Hız testi cümlesi.", speed=0.8)
        fast = self.engine.synthesize("Hız testi cümlesi.", speed=1.2)
        self.assertGreater(slow.size, fast.size)

    def test_empty_text_raises(self):
        with self.assertRaises(ValueError):
            self.engine.synthesize("   ")

    def test_write_wav_produces_valid_file(self):
        import tempfile
        import wave

        audio = self.engine.synthesize("Dosya yazma testi.", speed=1.0)
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "test.wav"
            ema_onnx.write_wav(audio, target)
            self.assertTrue(target.is_file())
            with wave.open(str(target)) as handle:
                self.assertEqual(handle.getnchannels(), 1)
                self.assertEqual(handle.getframerate(), 48_000)
                self.assertEqual(handle.getsampwidth(), 2)
                self.assertGreater(handle.getnframes(), 0)


if __name__ == "__main__":
    unittest.main()
