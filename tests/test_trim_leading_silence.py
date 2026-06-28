"""
txttoTTS - başta sessizlik kırpma birim testleri.

trim_leading_silence pure helper'ı test eder. Qt bağımlılığı yok.
"""
from __future__ import annotations

import unittest

import torch

from app.main_window import trim_leading_silence

SR = 24000


def _make_wav(
    leading_silence_ms: int,
    audio_ms: int,
    trailing_silence_ms: int,
    amplitude: float = 0.5,
) -> torch.Tensor:
    n_lead = int(leading_silence_ms * SR / 1000)
    n_audio = int(audio_ms * SR / 1000)
    n_trail = int(trailing_silence_ms * SR / 1000)
    wav = torch.zeros(1, n_lead + n_audio + n_trail)
    if n_audio > 0:
        wav[0, n_lead : n_lead + n_audio] = amplitude
    return wav


class TrimLeadingSilenceTests(unittest.TestCase):
    def test_all_silent_returns_original(self):
        wav = torch.zeros(1, SR)
        out = trim_leading_silence(wav, SR)
        self.assertEqual(out.shape[-1], SR)
        self.assertIs(out, wav)

    def test_short_leading_silence_trimmed(self):
        wav = _make_wav(50, 1000, 100)
        out = trim_leading_silence(wav, SR)
        # 50 ms = 1200 sample; ilk sesli sample 1200; pre_buffer 20 ms = 480 sample
        # keep_from = 1200 - 480 = 720
        self.assertAlmostEqual(out.shape[-1], wav.shape[-1] - 720, delta=1)
        self.assertEqual(out[0, -1].item(), 0.0)  # Son sessizlik dokunulmamış
        self.assertGreater(out.abs().max().item(), 0.4)  # Asıl ses bölgesi hâlâ var

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
        wav = torch.full((1, SR), 0.001)  # Eşik (0.005) altı
        out = trim_leading_silence(wav, SR)
        self.assertEqual(out.shape[-1], wav.shape[-1])

    def test_1d_and_2d_compatible(self):
        wav_2d = _make_wav(50, 500, 0)
        out_2d = trim_leading_silence(wav_2d, SR)
        self.assertEqual(out_2d.dim(), 2)
        self.assertEqual(out_2d.shape[0], 1)
        self.assertLess(out_2d.shape[-1], wav_2d.shape[-1])

        wav_1d = _make_wav(50, 500, 0).squeeze(0)
        out_1d = trim_leading_silence(wav_1d, SR)
        self.assertEqual(out_1d.dim(), 1)
        self.assertLess(out_1d.shape[-1], wav_1d.shape[-1])

    def test_invalid_sr_returns_original(self):
        wav = _make_wav(50, 500, 0)
        self.assertIs(trim_leading_silence(wav, 0), wav)
        self.assertIs(trim_leading_silence(wav, -1), wav)
        self.assertIs(trim_leading_silence(wav, None), wav)  # type: ignore

    def test_empty_tensor_returns_original(self):
        wav = torch.zeros(1, 0)
        self.assertIs(trim_leading_silence(wav, SR), wav)

    def test_none_wav_returns_none(self):
        self.assertIsNone(trim_leading_silence(None, SR))  # type: ignore


if __name__ == "__main__":
    unittest.main()