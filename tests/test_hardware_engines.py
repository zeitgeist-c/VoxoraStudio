"""Donanım kapısı ve motor kaydı testleri.

Amaç: yanlış pozitif CUDA "var" demesin (kullanıcı 4,6 GB indirip eli boş kalır)
ve CUDA'sız makinede VoxCPM2 hiçbir yoldan seçilemesin.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from app import engines, hardware


class HardwareDetectionTests(unittest.TestCase):
    def setUp(self):
        hardware.detect(force=True)  # önbelleği temizle
        hardware._CACHE.clear()

    def test_detect_returns_profile_on_this_machine(self):
        profile = hardware.detect(force=True)
        self.assertIsInstance(profile, hardware.HardwareProfile)
        self.assertGreater(profile.cpu_threads, 0)
        self.assertGreater(profile.ram_gb, 0)
        # Bu makinede çalışan bir NVIDIA sürücüsü yok.
        self.assertFalse(profile.cuda)
        self.assertFalse(profile.cuda_comfortable)

    def test_cuda_false_when_nvidia_smi_missing(self):
        with patch.object(hardware, "_nvidia_smi_path", return_value=""):
            self.assertFalse(hardware.cuda_ready())

    def test_cuda_false_when_smi_returns_nothing(self):
        with patch.object(hardware, "_nvidia_smi_path", return_value="C:/fake/nvidia-smi.exe"), \
             patch.object(hardware, "_run", return_value=""):
            self.assertFalse(hardware.cuda_ready())

    def test_cuda_true_only_with_gpu_in_listing(self):
        with patch.object(hardware, "_nvidia_smi_path", return_value="C:/fake/nvidia-smi.exe"), \
             patch.object(hardware, "_run", return_value="GPU 0: NVIDIA GeForce RTX 4070"):
            self.assertTrue(hardware.cuda_ready())

    def test_comfortable_requires_eight_gb(self):
        small = hardware.HardwareProfile(cuda=True, gpu_name="RTX 3050", vram_gb=4.0)
        enough = hardware.HardwareProfile(cuda=True, gpu_name="RTX 4070", vram_gb=12.0)
        unknown = hardware.HardwareProfile(cuda=True, gpu_name="RTX", vram_gb=0.0)
        self.assertFalse(small.cuda_comfortable)
        self.assertTrue(enough.cuda_comfortable)
        # VRAM okunamazsa engellemiyoruz: sürücü varsa denenir.
        self.assertTrue(unknown.cuda_comfortable)

    def test_gpu_label_falls_back(self):
        self.assertEqual(hardware.HardwareProfile().gpu_label, "Yok / CPU")
        self.assertEqual(
            hardware.HardwareProfile(other_gpu=True, other_gpu_name="AMD Radeon RX 6600").gpu_label,
            "AMD Radeon RX 6600",
        )
        self.assertEqual(hardware.HardwareProfile(cuda=True).gpu_label, "NVIDIA GPU")

    def test_detect_is_cached_until_forced(self):
        first = hardware.detect(force=True)
        second = hardware.detect()
        self.assertIs(first, second)
        third = hardware.detect(force=True)
        self.assertIsNot(first, third)


class EngineRegistryTests(unittest.TestCase):
    def test_three_engines_in_order(self):
        self.assertEqual(engines.keys(), ("ema", "chatterbox", "voxcpm2"))
        self.assertEqual(engines.ordered()[0].key, "ema")

    def test_default_engine_is_bundled_and_cpu_capable(self):
        default = engines.spec(engines.DEFAULT_ENGINE)
        self.assertTrue(default.bundled)
        self.assertTrue(default.cpu_ok)
        self.assertFalse(default.requires_cuda)

    def test_only_ema_is_bundled(self):
        bundled = [e.key for e in engines.ordered() if e.bundled]
        self.assertEqual(bundled, ["ema"])

    def test_voxcpm2_requires_cuda(self):
        spec = engines.spec("voxcpm2")
        self.assertTrue(spec.requires_cuda)
        self.assertFalse(spec.cpu_ok)
        self.assertTrue(spec.voice_design)

    def test_unknown_key_falls_back_to_default(self):
        self.assertEqual(engines.spec("yok-boyle-bir-sey").key, engines.DEFAULT_ENGINE)

    def test_capabilities_text(self):
        self.assertIn("1 dil", engines.capabilities_text(engines.spec("ema")))
        self.assertIn("ses klonlama", engines.capabilities_text(engines.spec("chatterbox")))
        self.assertIn("ses tasarımı", engines.capabilities_text(engines.spec("voxcpm2")))
        self.assertIn("48 kHz", engines.capabilities_text(engines.spec("voxcpm2")))

    def test_size_label_uses_comma(self):
        self.assertEqual(engines.spec("ema").size_label(), "44 MB")
        # VoxCPM2: 4,73 GB ağırlık + 420 MB çalışma zamanı = 5,15 GB -> "5,2 GB"
        self.assertEqual(engines.spec("voxcpm2").size_label(), "5,2 GB")


class AvailabilityGateTests(unittest.TestCase):
    def test_voxcpm2_blocked_without_cuda(self):
        ok, reason = engines.availability(
            engines.spec("voxcpm2"), cuda=False, disk_free_gb=500)
        self.assertFalse(ok)
        self.assertIn("CUDA", reason)

    def test_voxcpm2_allowed_with_cuda(self):
        ok, reason = engines.availability(
            engines.spec("voxcpm2"), cuda=True, disk_free_gb=500)
        self.assertTrue(ok)
        self.assertEqual(reason, "")

    def test_voxcpm2_blocked_on_low_disk_even_with_cuda(self):
        ok, reason = engines.availability(
            engines.spec("voxcpm2"), cuda=True, disk_free_gb=2.0)
        self.assertFalse(ok)
        self.assertIn("disk", reason.lower())

    def test_ema_always_allowed(self):
        ok, reason = engines.availability(
            engines.spec("ema"), cuda=False, disk_free_gb=5.0)
        self.assertTrue(ok)
        self.assertEqual(reason, "")

    def test_chatterbox_allowed_without_cuda(self):
        ok, _ = engines.availability(
            engines.spec("chatterbox"), cuda=False, disk_free_gb=100)
        self.assertTrue(ok)

    def test_chatterbox_needs_room(self):
        ok, reason = engines.availability(
            engines.spec("chatterbox"), cuda=False, disk_free_gb=1.0)
        self.assertFalse(ok)
        self.assertIn("disk", reason.lower())


if __name__ == "__main__":
    unittest.main()
