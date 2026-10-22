"""
Voxora Studio - motor seçimi ve ortak ses boru hattı testleri.

Gerçek model yüklenmez: sahte motorlar enjekte edilir, böylece testler ağsız
ve hızlı çalışır. Torch gerekmez — ortak yüzey numpy'dır.
"""
from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from tts_engine import EmaEngineAdapter, TTSEngine, adjust_speed, trim_leading_silence


class FakeOnnxEngine:
    """EmaOnnxEngine taklidi: hız oranında sabit ses üretir."""

    def __init__(self, duration: float = 1.0, sample_rate: int = 48_000):
        self.duration = duration
        self.sample_rate = sample_rate
        self.calls: list[tuple[str, float]] = []

    def load(self):
        return self

    def synthesize(self, text, speed=1.0, **_kwargs):
        self.calls.append((text, speed))
        samples = int(abs(self.duration) / max(float(speed), 0.01) * self.sample_rate)
        return np.full(samples, 0.1, dtype=np.float32)


class DummyMultiEngine:
    """accepts_speed taşımayan motor (dispatcher time-stretch yolu)."""

    accepts_speed = False

    def __init__(self, samples: int = 4800, sample_rate: int = 24_000):
        self._samples = samples
        self.sample_rate = sample_rate
        self.calls: list[tuple[tuple, dict]] = []

    def synthesize(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return np.zeros(self._samples, dtype=np.float32)


class EmaAdapterTests(unittest.TestCase):
    def _adapter(self, fake: FakeOnnxEngine) -> EmaEngineAdapter:
        adapter = EmaEngineAdapter.__new__(EmaEngineAdapter)
        adapter._engine = fake
        adapter.sample_rate = fake.sample_rate
        adapter.device_name = "cpu"
        return adapter

    def test_synthesize_returns_mono_float32(self):
        fake = FakeOnnxEngine(duration=2.0)
        adapter = self._adapter(fake)
        wav = adapter.synthesize("Merhaba dünya.", speed=1.0)
        self.assertEqual(wav.shape, (2 * 48_000,))
        self.assertEqual(wav.dtype, np.float32)
        self.assertEqual(adapter.sample_rate, 48_000)
        self.assertEqual(fake.calls, [("Merhaba dünya.", 1.0)])

    def test_speed_is_applied_natively(self):
        fake = FakeOnnxEngine(duration=4.0)
        adapter = self._adapter(fake)
        wav = adapter.synthesize("Uzun bir cümle.", speed=2.0)
        self.assertEqual(fake.calls[0][1], 2.0)
        self.assertEqual(wav.size, 2 * 48_000)  # 4 sn / 2 = 2 sn

    def test_multilingual_parameters_are_ignored(self):
        fake = FakeOnnxEngine(duration=1.0)
        adapter = self._adapter(fake)
        wav = adapter.synthesize(
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
        self.assertEqual(wav.size, 48_000)
        self.assertEqual(fake.calls, [("Deneme", 1.0)])


class TrimLeadingSilenceTests(unittest.TestCase):
    def test_trims_leading_silence(self):
        # 300 ms sessizlik: max_trim_ms (500) altında, kırpılmalı.
        audio = np.concatenate([
            np.zeros(14_400, dtype=np.float32),
            np.full(48_000, 0.5, dtype=np.float32),
        ])
        trimmed = trim_leading_silence(audio, 48_000)
        self.assertLess(trimmed.size, audio.size)
        self.assertGreater(trimmed.size, 0)

    def test_long_silence_is_not_over_trimmed(self):
        # Kırpma üst sınırı: 1 sn sessizlik max_trim_ms (500) üstünde olduğu
        # için kasıtlı olarak DOKUNULMAZ (atak kaybını önlemek için).
        audio = np.concatenate([
            np.zeros(48_000, dtype=np.float32),
            np.full(48_000, 0.5, dtype=np.float32),
        ])
        trimmed = trim_leading_silence(audio, 48_000)
        self.assertEqual(trimmed.size, audio.size)

    def test_all_silent_returns_original(self):
        audio = np.zeros(1000, dtype=np.float32)
        out = trim_leading_silence(audio, 48_000)
        self.assertEqual(out.size, 1000)

    def test_degenerate_inputs_are_safe(self):
        self.assertIsNone(trim_leading_silence(None, 48_000))
        audio = np.zeros(0, dtype=np.float32)
        self.assertEqual(trim_leading_silence(audio, 48_000).size, 0)
        audio = np.full(100, 0.5, dtype=np.float32)
        self.assertEqual(trim_leading_silence(audio, 0).size, 100)

    def test_already_trimmed_is_unchanged(self):
        audio = np.full(1000, 0.5, dtype=np.float32)
        out = trim_leading_silence(audio, 48_000)
        self.assertEqual(out.size, audio.size)


class AdjustSpeedTests(unittest.TestCase):
    def test_unity_speed_is_noop(self):
        audio = np.ones(1000, dtype=np.float32)
        out = adjust_speed(audio, 1.0, 24_000)
        self.assertIs(out, audio)

    def test_speed_down_makes_longer(self):
        audio = np.ones(10_000, dtype=np.float32)
        with patch.dict("sys.modules", {"librosa": None}):
            out = adjust_speed(audio, 0.5, 24_000)
        self.assertGreater(out.size, audio.size)

    def test_speed_up_makes_shorter(self):
        audio = np.ones(10_000, dtype=np.float32)
        with patch.dict("sys.modules", {"librosa": None}):
            out = adjust_speed(audio, 2.0, 24_000)
        self.assertLess(out.size, audio.size)

    def test_empty_audio_is_safe(self):
        audio = np.zeros(0, dtype=np.float32)
        self.assertEqual(adjust_speed(audio, 2.0, 24_000).size, 0)


class TTSEngineSelectionTests(unittest.TestCase):
    def test_ema_is_cpu_only_and_native_speed(self):
        fake = FakeOnnxEngine()
        adapter = EmaEngineAdapter.__new__(EmaEngineAdapter)
        adapter._engine = fake
        adapter.sample_rate = 48_000
        adapter.device_name = "cpu"
        with patch.object(TTSEngine, "_select_ema", return_value=("cpu", adapter)):
            engine = TTSEngine(engine_name="ema")
        self.assertEqual(engine.engine_name, "ema")
        self.assertEqual(engine.device_name, "cpu")
        self.assertEqual(engine.display_name, "EMA Lightning")
        self.assertEqual(engine.sample_rate, 48_000)

    def test_ema_path_does_not_time_stretch(self):
        fake = FakeOnnxEngine(duration=2.0)
        adapter = EmaEngineAdapter.__new__(EmaEngineAdapter)
        adapter._engine = fake
        adapter.sample_rate = 48_000
        adapter.device_name = "cpu"
        with patch.object(TTSEngine, "_select_ema", return_value=("cpu", adapter)):
            engine = TTSEngine(engine_name="ema")
        with patch("tts_engine.adjust_speed", side_effect=AssertionError("çağrılmamalı")):
            wav, sr = engine.synthesize("Deneme", speed=1.25)
        self.assertEqual(fake.calls[0][1], 1.25)
        self.assertEqual(sr, 48_000)
        self.assertEqual(wav.dtype, np.float32)

    def test_multilingual_path_keeps_time_stretch(self):
        dummy = DummyMultiEngine(samples=10_000)
        with patch.object(TTSEngine, "_select_chatterbox", return_value=("cpu", dummy)):
            engine = TTSEngine(engine_name="chatterbox")
        with patch("tts_engine.adjust_speed", side_effect=lambda a, s, sr: a) as adjust:
            wav, sr = engine.synthesize("Deneme", speed=1.5)
        adjust.assert_called_once()
        self.assertNotIn("speed", dummy.calls[0][1])  # hız dispatcher'da uygulanır
        self.assertEqual(sr, 24_000)
        self.assertEqual(wav.size, 10_000)

    def test_unknown_engine_falls_back_to_default(self):
        engine_spec = TTSEngine(engine_name="bilinmeyen-motor")
        # Varsayılan EMA'dır; gerçek ONNX motoru yüklenir ama dil/model bilgisi doğru.
        self.assertEqual(engine_spec.engine_name, "ema")
        self.assertEqual(engine_spec.display_name, "EMA Lightning")

    def test_voxcpm2_refuses_without_cuda(self):
        with patch("app.hardware.detect",
                   return_value=SimpleNamespace(cuda=False, gpu_name="", vram_gb=0.0)):
            with self.assertRaises(RuntimeError) as ctx:
                TTSEngine(engine_name="voxcpm2")
        self.assertIn("NVIDIA", str(ctx.exception))


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
