"""Denetim regresyonları: varsayılan motor, bozuk ayar, ses çalma biçimleri.

Üç gerçek hata kanıtlanmış ve burada kilitlenmiştir:

1. ``config.DEFAULT_ENGINE`` "chatterbox" idi; arayüz "Ayarları sıfırla"da bu
   sabiti kullanıyor. EMA ile çalışan kullanıcı sıfırlama sonrası indirilebilir
   motora düşüyor, 3,4 GB indirme ekranıyla kalıyordu (``app.engines`` varsayılanı
   "ema" olduğu hâlde).
2. Ayar dosyasındaki bozuk bir sayısal alan (``"speed": "hizli"``) pencereyi hiç
   açılmaz hâle getiriyordu: ``float("hizli")`` -> ``ValueError``.
3. ``audio_player.play_file`` yalnız ``.wav``/``.mp3`` tanıyordu; uygulamanın
   kendi OPUS çıktısını geçmişten çalmak ``ValueError`` atıyordu.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np  # noqa: E402
from PyQt6.QtWidgets import QApplication, QMessageBox  # noqa: E402

import audio_player  # noqa: E402
import config  # noqa: E402
from app import engines as engine_registry  # noqa: E402
from app import main_window  # noqa: E402
from app.main_window import MainWindow  # noqa: E402

_APP = None


def _qapp() -> QApplication:
    global _APP
    _APP = QApplication.instance() or QApplication(["voxora-audit-tests"])
    _APP.setQuitOnLastWindowClosed(False)
    return _APP


class DefaultEngineContractTests(unittest.TestCase):
    def test_config_default_matches_engine_registry(self):
        self.assertEqual(config.DEFAULT_ENGINE, engine_registry.DEFAULT_ENGINE)

    def test_config_default_is_the_bundled_engine(self):
        spec = engine_registry.spec(config.DEFAULT_ENGINE)
        self.assertTrue(spec.bundled, "varsayılan motor indirme gerektirmemeli")

    def test_config_lists_every_registered_engine(self):
        self.assertEqual(set(config.VALID_ENGINES), set(engine_registry.keys()))


class BrokenSettingsTests(unittest.TestCase):
    def setUp(self):
        _qapp()

    def _window(self, settings: dict) -> MainWindow:
        patches = (
            patch.object(main_window, "load_settings", return_value=dict(settings)),
            patch.object(main_window, "load_history", return_value=[]),
            patch.object(main_window, "save_settings"),
            patch.object(main_window, "save_history"),
            patch.object(main_window.audio_player, "stop"),
            patch.object(MainWindow, "_init_engine_async", autospec=True),
        )
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        window = MainWindow()
        self.addCleanup(window.deleteLater)
        return window

    def test_non_numeric_setting_does_not_break_startup(self):
        window = self._window({"speed": "hizli", "temperature": None,
                               "repetition_penalty": True})
        self.assertGreater(window.speed_spin.value(), 0.0)
        self.assertGreater(window.temperature_spin.value(), 0.0)
        self.assertGreater(window.repetition_spin.value(), 0.0)

    def test_numeric_string_is_still_honoured(self):
        window = self._window({"speed": "1.25"})
        self.assertAlmostEqual(window.speed_spin.value(), 1.25, places=3)

    def test_reset_keeps_bundled_engine(self):
        window = self._window({})
        self.assertEqual(window.engine_combo.currentData(), config.DEFAULT_ENGINE)
        self._select(window, "chatterbox")
        with patch.object(main_window.QMessageBox, "question",
                          return_value=QMessageBox.StandardButton.Yes):
            window.on_reset_all_settings()
        self.assertEqual(window.engine_combo.currentData(), config.DEFAULT_ENGINE)

    @staticmethod
    def _select(window: MainWindow, engine: str) -> None:
        index = window.engine_combo.findData(engine)
        assert index >= 0, engine
        window.engine_combo.setCurrentIndex(index)


class PlayFileFormatTests(unittest.TestCase):
    """Gerçek kodlayıcı çıktısıyla sınanır; ``sd.play`` casuslanır."""

    @classmethod
    def setUpClass(cls):
        cls.ffmpeg = shutil.which("ffmpeg")

    def _tone(self, folder: Path, name: str, codec_args: list[str]) -> Path:
        target = folder / name
        base = folder / "base.wav"
        if not base.exists():
            subprocess.run(
                [self.ffmpeg, "-y", "-f", "lavfi", "-i",
                 "sine=frequency=440:duration=0.25", "-ar", "24000", str(base)],
                capture_output=True, check=True,
            )
        subprocess.run([self.ffmpeg, "-y", "-i", str(base), *codec_args, str(target)],
                       capture_output=True, check=True)
        return target

    def test_opus_and_flac_and_ogg_play(self):
        if not self.ffmpeg:
            self.skipTest("ffmpeg yok")
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            cases = {
                "tone.opus": ["-c:a", "libopus"],
                "tone.flac": [],
                "tone.ogg": ["-c:a", "libvorbis"],
            }
            calls: list[tuple[int, int]] = []
            with patch.object(audio_player.sd, "play",
                              side_effect=lambda data, samplerate: calls.append(
                                  (len(data), int(samplerate)))):
                for name, args in cases.items():
                    path = self._tone(folder, name, args)
                    audio_player.play_file(str(path))
            self.assertEqual(len(calls), len(cases))
            for samples, rate in calls:
                self.assertGreater(samples, 0)
                self.assertEqual(rate, 24000)

    def test_unknown_extension_without_pydub_raises_clear_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bozuk.xyz"
            path.write_bytes(b"not audio")
            with patch.object(audio_player, "_HAS_PYDUB", False), \
                    patch.object(audio_player, "AudioSegment", None):
                with self.assertRaises(RuntimeError):
                    audio_player.play_file(str(path))

    def test_wav_still_plays_through_soundfile(self):
        with tempfile.TemporaryDirectory() as tmp:
            import soundfile as sf

            path = Path(tmp) / "tone.wav"
            sf.write(str(path), np.zeros(4000, dtype=np.float32), 24000)
            calls = []
            with patch.object(audio_player.sd, "play",
                              side_effect=lambda data, samplerate: calls.append(len(data))):
                audio_player.play_file(str(path))
            self.assertEqual(calls, [4000])


if __name__ == "__main__":
    unittest.main()
