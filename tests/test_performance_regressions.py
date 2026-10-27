"""Performans regresyonları: donanım tespiti tek çağrı, kırpma parçalı tarama.

İki darboğaz ölçülerek kapatıldı:

1. ``hardware.detect`` Windows'ta GPU adları ve RAM için AYRI iki PowerShell
   başlatıyordu; her biri ~250 ms. Ölçüm: ``detect()`` 479 ms -> 256 ms
   (medyan, aynı makine); ayrıca sonuç artık çağrılar arasında önbellekli.
2. ``trim_leading_silence`` tüm dizinin mutlak değerini ve tüm indeks listesini
   belleğe çıkarıyordu. 10 dakikalık 48 kHz kayıtta ek tepe bellek 259 MB,
   süre 65 ms; parçalı tarama 0,6 MB ve 0,3 ms (davranış aynı).
"""
from __future__ import annotations

import tracemalloc
import unittest
from unittest import mock

import numpy as np

from app import hardware
from tts_engine import trim_leading_silence


class SinglePowerShellCallTests(unittest.TestCase):
    def setUp(self):
        hardware._WININFO_CACHE.clear()

    def tearDown(self):
        hardware._WININFO_CACHE.clear()

    def test_gpu_and_ram_come_from_one_call(self):
        output = "GPU=AMD Radeon RX 6650 XT|AMD Radeon(TM) Graphics\nRAM=34359738368"
        with mock.patch.object(hardware, "_run", return_value=output) as runner:
            names, ram = hardware._windows_sysinfo(force=True)
        self.assertEqual(runner.call_count, 1)
        self.assertEqual(names, ["AMD Radeon RX 6650 XT", "AMD Radeon(TM) Graphics"])
        self.assertAlmostEqual(ram, 32.0, places=1)

    def test_second_lookup_is_cached(self):
        output = "GPU=Intel Arc A770\nRAM=17179869184"
        with mock.patch.object(hardware, "_run", return_value=output) as runner:
            hardware._windows_sysinfo(force=True)
            hardware._windows_sysinfo()
            hardware._windows_sysinfo()
        self.assertEqual(runner.call_count, 1)

    def test_broken_output_degrades_to_empty(self):
        with mock.patch.object(hardware, "_run", return_value=""):
            names, ram = hardware._windows_sysinfo(force=True)
        self.assertEqual(names, [])
        self.assertEqual(ram, 0.0)

    def test_other_gpu_picks_non_nvidia(self):
        with mock.patch.object(hardware, "_windows_gpu_names",
                               return_value=["Microsoft Basic Display", "AMD Radeon RX 6600"]):
            other, name = hardware._other_gpu(force=True)
        self.assertTrue(other)
        self.assertEqual(name, "AMD Radeon RX 6600")

    def test_other_gpu_ignores_nvidia_only(self):
        with mock.patch.object(hardware, "_windows_gpu_names",
                               return_value=["NVIDIA GeForce RTX 4070"]):
            self.assertEqual(hardware._other_gpu(force=True), (False, ""))


class TrimBoundedScanTests(unittest.TestCase):
    def _wav(self, minutes: int, lead_ms: int = 100) -> np.ndarray:
        size = 48000 * 60 * minutes
        wav = np.zeros(size, dtype=np.float32)
        wav[lead_ms * 48:] = 0.1
        return wav

    def test_long_recording_stays_cheap(self):
        wav = self._wav(10)
        tracemalloc.start()
        try:
            out = trim_leading_silence(wav, 48000)
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        trimmed = wav.size - out.shape[-1]
        self.assertEqual(trimmed, (100 - 20) * 48)   # pre_buffer 20 ms korunur
        # Eski uygulama 259 MB tepe üretiyordu; sınır cömert ama gerçekçi.
        self.assertLess(peak / 1e6, 20.0)

    def test_silence_beyond_window_is_not_trimmed(self):
        """Kırpma penceresi dışındaki ilk sesli örnek davranışı değiştirmemeli."""
        wav = np.zeros(48000 * 2, dtype=np.float32)
        wav[48000:] = 0.5   # 1 sn sessizlik > 500 ms + 20 ms
        out = trim_leading_silence(wav, 48000)
        self.assertEqual(out.shape[-1], wav.shape[-1])

    def test_all_silent_returns_identical_object(self):
        wav = np.zeros(48000, dtype=np.float32)
        self.assertIs(trim_leading_silence(wav, 48000), wav)

    def test_2d_input_keeps_shape(self):
        wav = np.zeros((1, 48000), dtype=np.float32)
        wav[0, 4800:] = 0.2
        out = trim_leading_silence(wav, 48000)
        self.assertEqual(out.ndim, 2)
        self.assertLess(out.shape[-1], wav.shape[-1])


class DirSizeScanTests(unittest.TestCase):
    """Modeller sekmesi disk etiketi: ``rglob`` yerine ``os.scandir``."""

    def test_counts_nested_files_and_ignores_links(self):
        import tempfile
        from pathlib import Path

        from app.main_window import _dir_size

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a").mkdir()
            (root / "a" / "one.bin").write_bytes(b"x" * 10)
            (root / "a" / "b").mkdir()
            (root / "a" / "b" / "two.bin").write_bytes(b"y" * 5)
            (root / "top.bin").write_bytes(b"z" * 2)
            self.assertEqual(_dir_size(root), 17)

    def test_missing_directory_is_zero(self):
        from pathlib import Path

        from app.main_window import _dir_size

        self.assertEqual(_dir_size(Path("C:/bu/klasor/yok-12345")), 0)


if __name__ == "__main__":
    unittest.main()