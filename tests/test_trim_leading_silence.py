"""
Voxora Studio - başta sessizlik kırpma birim testleri.

``trim_leading_silence`` saf yardımcısını test eder. Qt ve torch bağımlılığı
yoktur; ortak ses yüzeyi numpy'dır.
"""
from __future__ import annotations

import unittest

import numpy as np

from app.main_window import trim_leading_silence

SR = 24000


def _make_wav(
    leading_silence_ms: int,
    audio_ms: int,
    trailing_silence_ms: int,
    amplitude: float = 0.5,
    channels: int = 1,
) -> np.ndarray:
    n_lead = int(leading_silence_ms * SR / 1000)
    n_audio = int(audio_ms * SR / 1000)
    n_trail = int(trailing_silence_ms * SR / 1000)
    wav = np.zeros((channels, n_lead + n_audio + n_trail), dtype=np.float32)
    if n_audio > 0:
        wav[:, n_lead : n_lead + n_audio] = amplitude
    return wav


class TrimLeadingSilenceTests(unittest.TestCase):
    def test_all_silent_returns_original(self):
        wav = np.zeros((1, SR), dtype=np.float32)
        out = trim_leading_silence(wav, SR)
        self.assertEqual(out.shape[-1], SR)
        self.assertIs(out, wav)

    def test_short_leading_silence_trimmed(self):
        wav = _make_wav(50, 1000, 100)
        out = trim_leading_silence(wav, SR)
        # 50 ms = 1200 örnek; ilk sesli örnek 1200; pre_buffer 20 ms = 480 örnek
        # keep_from = 1200 - 480 = 720
        self.assertAlmostEqual(out.shape[-1], wav.shape[-1] - 720, delta=1)
        self.assertEqual(out[0, -1], 0.0)  # Son sessizlik dokunulmamış
        self.assertGreater(float(np.abs(out).max()), 0.4)  # Asıl ses bölgesi hâlâ var

    def test_very_long_silence_capped(self):
        wav = _make_wav(600, 1000, 0)
        out = trim_leading_silence(wav, SR)
        # max_samples = 500 ms = 12000; keep_from 12000+ olur, 0'a sıfırlanır
        self.assertEqual(out.shape[-1], wav.shape[-1])

    def test_no_leading_silence_returns_original(self):
        wav = _make_wav(0, 1000, 0)
        out = trim_leading_silence(wav, SR)
        self.assertEqual(out.shape[-1], wav.shape[-1])
        self.assertIs(out, wav)

    def test_subthreshold_noise_not_trimmed(self):
        wav = np.full((1, SR), 0.001, dtype=np.float32)  # Eşik (0.005) altı
        out = trim_leading_silence(wav, SR)
        self.assertEqual(out.shape[-1], wav.shape[-1])

    def test_1d_and_2d_compatible(self):
        wav_2d = _make_wav(50, 500, 0)
        out_2d = trim_leading_silence(wav_2d, SR)
        self.assertEqual(out_2d.ndim, 2)
        self.assertEqual(out_2d.shape[0], 1)
        self.assertLess(out_2d.shape[-1], wav_2d.shape[-1])

        wav_1d = np.zeros(wav_2d.shape[-1], dtype=np.float32)
        wav_1d[:] = wav_2d[0]
        out_1d = trim_leading_silence(wav_1d, SR)
        self.assertEqual(out_1d.ndim, 1)
        self.assertLess(out_1d.shape[-1], wav_1d.shape[-1])

    def test_invalid_sr_returns_original(self):
        wav = _make_wav(50, 500, 0)
        self.assertIs(trim_leading_silence(wav, 0), wav)
        self.assertIs(trim_leading_silence(wav, -1), wav)
        self.assertIs(trim_leading_silence(wav, None), wav)  # type: ignore

    def test_empty_array_returns_original(self):
        wav = np.zeros((1, 0), dtype=np.float32)
        self.assertIs(trim_leading_silence(wav, SR), wav)

    def test_none_wav_returns_none(self):
        self.assertIsNone(trim_leading_silence(None, SR))  # type: ignore


if __name__ == "__main__":
    unittest.main()
