"""
Voxora Studio - çıktı biçimi ve kalite testleri.

Ayarlar → Çıktı → "Kayıt ve Kalite" kartındaki biçim kutucukları (WAV/MP3/OPUS),
biçime göre değişen kalite listesi, ayar kalıcılığı ve üretimin seçilen biçimde
kaydedilmesi doğrulanır. MP3/OPUS yazımı gerçek ffmpeg ile sınanır.
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
import torch  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from app import main_window  # noqa: E402
from app.constants import OUTPUT_FORMAT_OPTIONS, quality_options_for  # noqa: E402
from app.main_window import MainWindow  # noqa: E402
from config import (  # noqa: E402
    DEFAULT_MP3_BITRATE,
    DEFAULT_OPUS_BITRATE,
    DEFAULT_OUTPUT_FORMAT,
    OUTPUT_FORMAT_EXTENSIONS,
    OUTPUT_FORMAT_MP3,
    OUTPUT_FORMAT_OPUS,
    OUTPUT_FORMAT_WAV,
    VALID_OUTPUT_FORMATS,
)

_APP = None
FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")


def _tone(sr: int, seconds: float = 0.5) -> torch.Tensor:
    """Kısa sinüs tonu (kayıp kodlayıcılar sessizlikte de dosya üretir)."""
    t = np.linspace(0.0, seconds, int(sr * seconds), endpoint=False)
    data = (0.25 * np.sin(2 * np.pi * 440.0 * t)).astype(np.float32)
    return torch.from_numpy(data)


def _codec_of(path: Path) -> str:
    out = subprocess.run(
        [FFPROBE, "-v", "error", "-select_streams", "a:0",
         "-show_entries", "stream=codec_name", "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    return out.stdout.strip()


class FormatTableTests(unittest.TestCase):
    """Sabit tablolar: her biçim eksiksiz tanımlı olmalı."""

    def test_every_format_has_extension_tile_and_quality(self):
        for fmt in VALID_OUTPUT_FORMATS:
            self.assertIn(fmt, OUTPUT_FORMAT_EXTENSIONS, fmt)
            self.assertTrue(OUTPUT_FORMAT_EXTENSIONS[fmt].startswith("."), fmt)
            self.assertIn(fmt, {key for key, _t, _d in OUTPUT_FORMAT_OPTIONS}, fmt)
            self.assertTrue(quality_options_for(fmt), fmt)

    def test_default_values_are_valid(self):
        self.assertIn(DEFAULT_OUTPUT_FORMAT, VALID_OUTPUT_FORMATS)
        self.assertIn(DEFAULT_MP3_BITRATE, {v for v, _l in quality_options_for(OUTPUT_FORMAT_MP3)})
        self.assertIn(DEFAULT_OPUS_BITRATE, {v for v, _l in quality_options_for(OUTPUT_FORMAT_OPUS)})

    def test_unknown_format_falls_back_to_lossless_list(self):
        self.assertEqual(quality_options_for("flac"), quality_options_for(OUTPUT_FORMAT_WAV))


class OutputFormatUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global _APP
        _APP = QApplication.instance() or QApplication(["voxora-format-tests"])
        _APP.setQuitOnLastWindowClosed(False)
        cls.app = _APP

    def _headless_window(self, settings: dict | None = None) -> MainWindow:
        patches = (
            patch.object(main_window, "load_settings", return_value=dict(settings or {})),
            patch.object(main_window, "load_history", return_value=[]),
            patch.object(main_window, "save_settings"),
            patch.object(main_window, "save_history"),
            patch.object(main_window.audio_player, "stop"),
            patch.object(MainWindow, "_init_engine_async", autospec=True),
        )
        for item in patches:
            item.start()
            self.addCleanup(item.stop)
        window = MainWindow()
        self.addCleanup(window.deleteLater)
        return window

    def test_default_selection_is_mp3_high_quality(self):
        window = self._headless_window()
        self.assertEqual(window._output_format, DEFAULT_OUTPUT_FORMAT)
        self.assertTrue(window.format_tiles[OUTPUT_FORMAT_MP3].is_selected())
        self.assertFalse(window.format_tiles[OUTPUT_FORMAT_WAV].is_selected())
        self.assertTrue(window.quality_combo.isEnabled())
        self.assertEqual(window.quality_combo.currentData(), DEFAULT_MP3_BITRATE)

    def test_selecting_wav_disables_quality(self):
        window = self._headless_window()
        window._on_output_format_selected(OUTPUT_FORMAT_WAV)
        self.assertTrue(window.format_tiles[OUTPUT_FORMAT_WAV].is_selected())
        self.assertFalse(window.format_tiles[OUTPUT_FORMAT_MP3].is_selected())
        self.assertFalse(window.quality_combo.isEnabled())
        self.assertEqual(window._quality_by_format[OUTPUT_FORMAT_WAV], "")
        self.assertIn("WAV", window.status_label.text())

    def test_opus_options_and_per_format_memory(self):
        window = self._headless_window()
        window._on_output_format_selected(OUTPUT_FORMAT_OPUS)
        values = [window.quality_combo.itemData(i) for i in range(window.quality_combo.count())]
        self.assertEqual(values, [v for v, _l in quality_options_for(OUTPUT_FORMAT_OPUS)])
        window.quality_combo.setCurrentIndex(window.quality_combo.findData("96k"))
        self.assertEqual(window._quality_by_format[OUTPUT_FORMAT_OPUS], "96k")

        window._on_output_format_selected(OUTPUT_FORMAT_MP3)
        self.assertEqual(window.quality_combo.currentData(), DEFAULT_MP3_BITRATE)
        window._on_output_format_selected(OUTPUT_FORMAT_OPUS)
        self.assertEqual(window.quality_combo.currentData(), "96k")

    def test_settings_snapshot_carries_format_and_quality(self):
        window = self._headless_window({"output_format": "opus", "opus_bitrate": "32k"})
        self.assertEqual(window._output_format, OUTPUT_FORMAT_OPUS)
        self.assertEqual(window.quality_combo.currentData(), "32k")
        snapshot = window._current_ui_settings()
        self.assertEqual(snapshot["output_format"], OUTPUT_FORMAT_OPUS)
        self.assertEqual(snapshot["opus_bitrate"], "32k")
        self.assertEqual(snapshot["mp3_bitrate"], DEFAULT_MP3_BITRATE)

    def test_stale_saved_values_fall_back(self):
        window = self._headless_window({"output_format": "flac", "opus_bitrate": "48k"})
        self.assertEqual(window._output_format, DEFAULT_OUTPUT_FORMAT)
        window._on_output_format_selected(OUTPUT_FORMAT_OPUS)
        self.assertEqual(window.quality_combo.currentData(), DEFAULT_OPUS_BITRATE)

    def test_reset_restores_defaults(self):
        window = self._headless_window({"output_format": "opus", "opus_bitrate": "96k"})
        with patch.object(main_window.QMessageBox, "question",
                          return_value=main_window.QMessageBox.StandardButton.Yes):
            window.on_reset_all_settings()
        self.assertEqual(window._output_format, DEFAULT_OUTPUT_FORMAT)
        self.assertEqual(window.quality_combo.currentData(), DEFAULT_MP3_BITRATE)

    def test_history_selection_restores_format(self):
        window = self._headless_window()
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "deneme.wav")
            Path(path).write_bytes(b"RIFF0000")
            window.history = [{
                "name": "deneme",
                "path": path,
                "text": "merhaba dünya",
                "duration": "1.0 sn",
                "output_format": "opus",
                "opus_bitrate": "96k",
                "mp3_bitrate": "128k",
                "speed": 1.0,
                "pause_between_chunks": 0.35,
                "temperature": 0.3,
                "repetition_penalty": 1.8,
            }]
            window._refresh_history_list()
            window.history_list.setCurrentRow(0)
            with patch.object(MainWindow, "on_generate", autospec=True):
                window.on_regenerate_from_history()
        self.assertEqual(window._output_format, OUTPUT_FORMAT_OPUS)
        self.assertEqual(window.quality_combo.currentData(), "96k")
        window._on_output_format_selected(OUTPUT_FORMAT_MP3)
        self.assertEqual(window.quality_combo.currentData(), "128k")


class AutoSaveFormatTests(unittest.TestCase):
    """Üretim çıktısı seçilen biçimde yazılmalı (gerçek ffmpeg)."""

    @classmethod
    def setUpClass(cls):
        global _APP
        _APP = QApplication.instance() or QApplication(["voxora-save-tests"])
        _APP.setQuitOnLastWindowClosed(False)
        cls.app = _APP

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patches = (
            patch.object(main_window, "load_settings", return_value={}),
            patch.object(main_window, "load_history", return_value=[]),
            patch.object(main_window, "save_settings"),
            patch.object(main_window, "save_history"),
            patch.object(main_window.audio_player, "stop"),
            patch.object(MainWindow, "_init_engine_async", autospec=True),
        )
        for item in patches:
            item.start()
            self.addCleanup(item.stop)
        self.window = MainWindow()
        self.addCleanup(self.window.deleteLater)
        self.window.output_dir = self.tmp.name

    def _save(self, fmt: str, sr: int = 44100) -> Path:
        self.window._output_format = fmt
        path = self.window._auto_save_generated_audio(_tone(sr), sr, "çıktı biçimi denemesi")
        return Path(path)

    def test_wav_output(self):
        path = self._save(OUTPUT_FORMAT_WAV)
        self.assertEqual(path.suffix, ".wav")
        self.assertTrue(path.exists())
        self.assertEqual(path.read_bytes()[:4], b"RIFF")

    @unittest.skipUnless(FFMPEG and FFPROBE, "ffmpeg/ffprobe gerekli")
    def test_mp3_output_uses_selected_bitrate(self):
        self.window._quality_by_format[OUTPUT_FORMAT_MP3] = "192k"
        path = self._save(OUTPUT_FORMAT_MP3)
        self.assertEqual(path.suffix, ".mp3")
        self.assertGreater(path.stat().st_size, 0)
        self.assertEqual(_codec_of(path), "mp3")
        detail = subprocess.run(
            [FFPROBE, "-v", "error", "-select_streams", "a:0", "-show_entries",
             "format=bit_rate", "-of", "default=nw=1:nk=1", str(path)],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        self.assertTrue(150_000 < int(detail) < 250_000, detail)

    @unittest.skipUnless(FFMPEG and FFPROBE, "ffmpeg/ffprobe gerekli")
    def test_opus_output(self):
        self.window._quality_by_format[OUTPUT_FORMAT_OPUS] = "64k"
        path = self._save(OUTPUT_FORMAT_OPUS, sr=48000)
        self.assertEqual(path.suffix, ".opus")
        self.assertGreater(path.stat().st_size, 0)
        self.assertEqual(_codec_of(path), "opus")

    @unittest.skipUnless(FFMPEG and FFPROBE, "ffmpeg/ffprobe gerekli")
    def test_mp3_is_smaller_than_wav(self):
        wav_path = self._save(OUTPUT_FORMAT_WAV)
        mp3_path = self._save(OUTPUT_FORMAT_MP3)
        self.assertLess(mp3_path.stat().st_size, wav_path.stat().st_size)

    def test_export_failure_falls_back_to_wav(self):
        self.window._output_format = OUTPUT_FORMAT_OPUS
        with patch.object(MainWindow, "_export_compressed", side_effect=RuntimeError("ffmpeg yok")):
            path = Path(self.window._auto_save_generated_audio(_tone(44100), 44100, "yedek yol"))
        self.assertEqual(path.suffix, ".wav")
        self.assertTrue(path.exists())
        self.assertIn("WAV", self.window.status_label.text())

    def test_unknown_format_falls_back_to_default_extension(self):
        self.window._output_format = "flac"
        path = self._save(DEFAULT_OUTPUT_FORMAT)
        self.assertIn(path.suffix, {".mp3", ".wav", ".opus"})


if __name__ == "__main__":
    unittest.main()
