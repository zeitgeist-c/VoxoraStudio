"""Yol çözümü testleri — donmuş pakette ``_internal`` kökü.

Gerçek hata: paket EMA ağırlıklarını kendi içinde bulamayıp Hugging Face'ten
indirmeye çalıştı. Sebep ``package_root()``in ``sys.executable``in klasörünü
döndürmesiydi; PyInstaller ``--add-data`` dosyaları ``_internal/`` altına koyar
ve doğru kök ``sys._MEIPASS``tir.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from app import paths


class PackageRootTests(unittest.TestCase):
    def test_source_mode_returns_repo_root(self):
        with patch.object(paths, "_is_frozen", return_value=False):
            root = paths.package_root()
        self.assertEqual(root, Path(__file__).resolve().parents[1])
        self.assertTrue((root / "app").is_dir())

    def test_frozen_mode_uses_meipass(self):
        """Donmuş pakette kök ``_MEIPASS`` olmalı, EXE klasörü değil."""
        meipass = Path(r"C:\Program Files\VoxoraStudio\_internal")
        with patch.object(paths, "_is_frozen", return_value=True), \
             patch.object(sys, "_MEIPASS", str(meipass), create=True):
            self.assertEqual(paths.package_root(), meipass)

    def test_frozen_mode_falls_back_to_exe_dir(self):
        """``_MEIPASS`` yoksa (tek dosya dışı kurulumlar) EXE klasörüne düşer."""
        fake_exe = Path(r"C:\Program Files\VoxoraStudio\VoxoraStudio.exe")
        with patch.object(paths, "_is_frozen", return_value=True), \
             patch.object(sys, "executable", str(fake_exe)), \
             patch.object(sys, "_MEIPASS", "", create=True):
            self.assertEqual(paths.package_root(), fake_exe.parent)

    def test_bundled_models_dir_is_under_package_root(self):
        with patch.object(paths, "_is_frozen", return_value=False):
            self.assertEqual(
                paths.bundled_models_dir(),
                paths.package_root() / "models",
            )

    def test_ema_weights_present_in_repo(self):
        """Paketlenecek ağırlıklar depoda gerçekten var mı (build buna dayanır)."""
        root = paths.bundled_models_dir() / "ema-onnx"
        for name in ("text.onnx", "sound.onnx", "decoder.onnx", "meta.json"):
            self.assertTrue((root / name).is_file(), f"eksik: {name}")

    def test_engine_packs_manifest_present(self):
        """Motor paketi pinleri paketlenmeli (assets/)."""
        root = paths.package_root() / "assets" / "engine_packs.json"
        self.assertTrue(root.is_file(), "assets/engine_packs.json yok")

    def test_models_and_engines_dirs_are_separate(self):
        root = Path(r"C:\Users\test")
        with patch.object(paths, "user_data_root", return_value=root):
            self.assertEqual(paths.models_dir(), root / "models")
            self.assertEqual(paths.engines_dir(), root / "engines")
            self.assertNotEqual(paths.models_dir(), paths.engines_dir())

    def test_env_override_for_models_dir(self):
        with patch.dict("os.environ", {"VOXORA_MODELS_DIR": r"D:\BenimModellerim"}):
            self.assertEqual(paths.models_dir(), Path(r"D:\BenimModellerim"))

    def test_outputs_and_state_under_user_data(self):
        root = Path(r"C:\Users\test\VoxoraStudio")
        with patch.object(paths, "user_data_root", return_value=root):
            self.assertEqual(paths.state_dir(), root / "state")
            self.assertEqual(paths.logs_dir(), root / "logs")
            self.assertEqual(paths.outputs_dir(), root / "outputs")
            self.assertEqual(paths.updates_dir(), root / "updates")


class BundledModelResolutionTests(unittest.TestCase):
    """EMA ağırlığı pakette varsa ağa HİÇ çıkılmamalı."""

    def test_resolve_prefers_bundled_copy(self):
        from app import ema_onnx

        bundled = paths.bundled_models_dir() / "ema-onnx"
        if not ema_onnx.models_ready(bundled):
            self.skipTest("paketlenmiş EMA ağırlıkları yok")
        self.assertEqual(ema_onnx.resolve_models_dir(), bundled)

    def test_no_network_when_bundled(self):
        from app import ema_onnx

        bundled = paths.bundled_models_dir() / "ema-onnx"
        if not ema_onnx.models_ready(bundled):
            self.skipTest("paketlenmiş EMA ağırlıkları yok")
        # ensure_models ağa çıkmadan mevcut klasörü döndürmeli.
        with patch("huggingface_hub.snapshot_download",
                   side_effect=AssertionError("ağa çıkılmamalı")):
            self.assertEqual(ema_onnx.ensure_models(), bundled)


if __name__ == "__main__":
    unittest.main()
