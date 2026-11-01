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


def _names(target: str) -> list[str]:
    """requirements_packages çıktısından paket adları (sürüm pinsiz)."""
    names = []
    for item in setup_env.requirements_packages(target):
        names.append(item.split("==", 1)[0].split(">=", 1)[0].strip().lower())
    return names


class RequirementsSelectionTests(unittest.TestCase):
    def test_directml_target_skips_plain_onnxruntime(self):
        packages = _names("directml")
        self.assertNotIn("onnxruntime", packages)
        self.assertNotIn("onnxruntime-directml", packages)

    def test_cpu_target_keeps_plain_onnxruntime(self):
        packages = _names("cpu")
        self.assertIn("onnxruntime", packages)

    def test_torch_is_never_installed_from_requirements(self):
        """torch pinini ``install_torch`` belirler; requirements'a bırakılmaz."""
        for target in ("cpu", "cuda", "directml"):
            packages = _names(target)
            self.assertNotIn("torch", packages, target)
            self.assertNotIn("torchaudio", packages, target)

    def test_torch_pin_is_two_six(self):
        """torch 2.6.0 pini chatterbox uyumu için bilinçli; değişmemeli."""
        self.assertEqual(setup_env.TORCH_VERSION, "2.6.0")

    def test_directml_version_is_pinned(self):
        """DirectML pini: pinsiz kurulum çakışmayı geri getirir."""
        self.assertEqual(setup_env.DIRECTML_PACKAGE, "onnxruntime-directml")
        self.assertEqual(setup_env.DIRECTML_VERSION, "1.24.4")


if __name__ == "__main__":
    unittest.main()
