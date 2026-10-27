"""Bağımlılık regresyonları: DirectML/onnxruntime çakışması ve paket seçimi.

``onnxruntime-directml`` aynı ``onnxruntime`` modülünü sağlar. Kurulum betiği
her iki paketi de kurunca iki dist-info aynı 620 dosyayı paylaşıyordu; modül
DirectML sürümünde kalırken metadata düz sürümü gösteriyor, ``pip install -r
requirements.txt`` DirectML wheel'ini ezip ``DmlExecutionProvider``'ı
kaldırıyordu. ``requirements_packages`` bu yüzden DirectML hedefinde düz
``onnxruntime`` paketini atlar.
"""
from __future__ import annotations

import unittest

from scripts import setup_env


class RequirementsSelectionTests(unittest.TestCase):
    def test_directml_target_skips_plain_onnxruntime(self):
        packages = [p.lower() for p in setup_env.requirements_packages("directml")]
        self.assertNotIn("onnxruntime", packages)
        self.assertNotIn("onnxruntime-directml", packages)

    def test_cpu_target_keeps_plain_onnxruntime(self):
        packages = [p.lower() for p in setup_env.requirements_packages("cpu")]
        self.assertIn("onnxruntime", packages)

    def test_torch_is_never_installed_from_requirements(self):
        """torch pinini ``install_torch`` belirler; requirements'a bırakılmaz."""
        for target in ("cpu", "cuda", "directml"):
            packages = [p.lower() for p in setup_env.requirements_packages(target)]
            self.assertNotIn("torch", packages, target)
            self.assertNotIn("torchaudio", packages, target)

    def test_torch_pin_is_two_six(self):
        """torch 2.6.0 pini chatterbox uyumu için bilinçli; değişmemeli."""
        self.assertEqual(setup_env.TORCH_VERSION, "2.6.0")


if __name__ == "__main__":
    unittest.main()
