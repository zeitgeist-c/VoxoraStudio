"""OnnxEngine birim testleri (model yoksa skip)."""
from __future__ import annotations

import unittest
from pathlib import Path

from tts_engine import OnnxEngine


class OnnxEngineStructureTests(unittest.TestCase):
    def test_module_imports(self):
        # model yoksa bile import çalışmalı
        eng = OnnxEngine(model_dir="nonexistent_dir")
        self.assertFalse(eng.model_loaded)
        self.assertEqual(eng.sample_rate, 24_000)

    def test_provider_selection_cpu(self):
        # CPU ortamda model yüklenmeye çalışır (DirectML yoksa fallback)
        eng = OnnxEngine(model_dir="models", device="cpu")
        # model yüklü değilse bile attribute erişimi güvenli
        self.assertEqual(eng.sample_rate, 24_000)


@unittest.skipUnless(Path("models/chatterbox_t3.onnx").exists(), "T3 ONNX model yok")
class OnnxEngineModelTests(unittest.TestCase):
    def test_session_creates(self):
        eng = OnnxEngine(model_dir="models", device="cpu")
        self.assertTrue(eng.model_loaded)


if __name__ == "__main__":
    unittest.main()