"""
Voxora Studio - EMA motoru ve motor seçimi birim testleri.

Gerçek model yüklenmez: EMA yerine sahte bir `say()` nesnesi enjekte edilir,
böylece testler ağsız ve hızlı çalışır.
"""
from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import torch

from tts_engine import EmaEngine, TTSEngine


class FakeEMA:
    """EMA.say() taklidi: süre/hız oranında sabit ses üretir."""

    def __init__(self, duration: float = 1.0, sample_rate: int = 48_000):
        self.duration = duration
        self.sample_rate = sample_rate
        self.calls: list[tuple[str, float]] = []

    def say(self, text, speed=1.0, seed=None, sample_rate=None, path=None):
        self.calls.append((text, speed))
        samples = int(abs(self.duration) / max(float(speed), 0.01) * self.sample_rate)
        audio = np.full(samples, 0.1, dtype=np.float32)
        return SimpleNamespace(
            audio=audio,
            sample_rate=self.sample_rate,
            duration=samples / self.sample_rate,
            seed=0,
            words=(),
        )


class DummyChatterboxEngine:
    """accepts_speed taşımayan motor (dispatcher time-stretch yolu)."""

    def __init__(self, samples: int = 4800, sample_rate: int = 24_000):
        self._samples = samples
        self._sample_rate = sample_rate
        self.calls: list[tuple[tuple, dict]] = []

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    def synthesize(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return torch.zeros(1, self._samples)


class EmaEngineTests(unittest.TestCase):
    def test_synthesize_returns_mono_tensor_and_sample_rate(self):
        fake = FakeEMA(duration=2.0)
        engine = EmaEngine(model=fake)
        wav = engine.synthesize("Merhaba dünya.", speed=1.0)
        self.assertEqual(wav.shape, (1, 2 * 48_000))
        self.assertEqual(wav.dtype, torch.float32)
        self.assertEqual(engine.sample_rate, 48_000)
        self.assertEqual(fake.calls, [("Merhaba dünya.", 1.0)])

    def test_speed_is_applied_natively(self):
        fake = FakeEMA(duration=4.0)
        engine = EmaEngine(model=fake)
        wav = engine.synthesize("Uzun bir cümle.", speed=2.0)
        self.assertEqual(fake.calls[0][1], 2.0)
        self.assertEqual(wav.shape[-1], 2 * 48_000)  # 4 sn / 2 = 2 sn

    def test_empty_audio_falls_back_to_short_silence(self):
        fake = FakeEMA(duration=0.0)
        engine = EmaEngine(model=fake)
        wav = engine.synthesize("...")
        self.assertEqual(wav.shape[-1], int(48_000 * 0.25))
        self.assertTrue(torch.all(wav == 0))

    def test_chatterbox_parameters_are_ignored(self):
        fake = FakeEMA(duration=1.0)
        engine = EmaEngine(model=fake)
        wav = engine.synthesize(
            "Deneme",
            language_id="en",
            exaggeration=0.9,
            cfg_weight=0.1,
            audio_prompt_path="ornek.wav",
            temperature=0.2,
            repetition_penalty=3.0,
            min_p=0.1,
            top_p=0.9,
            speed=1.0,
        )
        self.assertEqual(wav.shape[-1], 48_000)
        self.assertEqual(fake.calls, [("Deneme", 1.0)])


class TTSEngineSelectionTests(unittest.TestCase):
    def test_ema_selection_uses_ema_engine_on_cpu(self):
        stub = SimpleNamespace(sample_rate=48_000, accepts_speed=True)
        with (
            patch("tts_engine.EmaEngine", return_value=stub) as ema_cls,
            patch("torch.cuda.is_available", return_value=False),
        ):
            engine = TTSEngine(engine_name="ema")
        self.assertEqual(engine.engine_name, "ema")
        self.assertEqual(engine.device_name, "cpu")
        self.assertEqual(engine.display_name, "EMA Lightning")
        ema_cls.assert_called_once()
        self.assertEqual(ema_cls.call_args.kwargs.get("device"), "cpu")

    def test_ema_selection_prefers_cuda_when_available(self):
        stub = SimpleNamespace(sample_rate=48_000, accepts_speed=True)
        with (
            patch("tts_engine.EmaEngine", return_value=stub) as ema_cls,
            patch("torch.cuda.is_available", return_value=True),
        ):
            engine = TTSEngine(engine_name="ema")
        self.assertEqual(engine.device_name, "cuda")
        self.assertEqual(ema_cls.call_args.kwargs.get("device"), "cuda")

    def test_invalid_engine_falls_back_to_chatterbox(self):
        dummy = DummyChatterboxEngine()
        with patch.object(TTSEngine, "_select_chatterbox_engine", return_value=("cpu", dummy)):
            engine = TTSEngine(engine_name="bilinmeyen-motor")
        self.assertEqual(engine.engine_name, "chatterbox")
        self.assertEqual(engine.display_name, "Chatterbox Multilingual")

    def test_chatterbox_path_keeps_time_stretch(self):
        dummy = DummyChatterboxEngine(samples=10_000)
        with patch.object(TTSEngine, "_select_chatterbox_engine", return_value=("cpu", dummy)):
            engine = TTSEngine()
        with patch.object(TTSEngine, "_adjust_speed", wraps=engine._adjust_speed) as adjust:
            wav, sr = engine.synthesize("Deneme", speed=1.0)
        adjust.assert_called_once()
        self.assertNotIn("speed", dummy.calls[0][1])  # speed motor yerine dispatcher'da uygulanır
        self.assertEqual(sr, 24_000)
        self.assertEqual(wav.shape, (1, 10_000))

    def test_ema_path_skips_time_stretch(self):
        fake = FakeEMA(duration=2.0)
        with (
            patch("tts_engine.EmaEngine", return_value=EmaEngine(model=fake)),
            patch("torch.cuda.is_available", return_value=False),
        ):
            engine = TTSEngine(engine_name="ema")
        with patch.object(TTSEngine, "_adjust_speed", side_effect=AssertionError("çağrılmamalı")) as adjust:
            wav, sr = engine.synthesize("Deneme", speed=1.25)
        adjust.assert_not_called()
        self.assertEqual(fake.calls[0][1], 1.25)
        self.assertEqual(sr, 48_000)


class EngineLoaderTests(unittest.TestCase):
    def test_loader_forwards_engine_name_to_dispatcher(self):
        from app.workers import EngineLoader

        recorded: dict = {}

        def fake_tts(**kwargs):
            recorded.update(kwargs)
            return SimpleNamespace()

        with patch("app.workers.TTSEngine", side_effect=fake_tts):
            loader = EngineLoader(engine_name="ema")
            loader.run()

        self.assertEqual(recorded.get("engine_name"), "ema")

    def test_loader_defaults_to_no_engine_override(self):
        from app.workers import EngineLoader

        recorded: dict = {}

        def fake_tts(**kwargs):
            recorded.update(kwargs)
            return SimpleNamespace()

        with patch("app.workers.TTSEngine", side_effect=fake_tts):
            loader = EngineLoader()
            loader.run()

        self.assertIsNone(recorded.get("engine_name"))


if __name__ == "__main__":
    unittest.main()
