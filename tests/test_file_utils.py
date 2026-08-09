"""
Voxora Studio - file_utils birim testleri.
"""
from __future__ import annotations

import os
import tempfile
import unittest

from file_utils import safe_filename_from_text, safe_remove_to_trash, unique_path


class SafeRemoveToTrashTests(unittest.TestCase):
    def test_existing_file_removed(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            path = f.name
        self.assertTrue(os.path.exists(path))
        ok, err = safe_remove_to_trash(path)
        self.assertTrue(ok)
        self.assertIsNone(err)
        # send2trash kullanıldıysa Geri Dönüşüm'de; os.remove fallback ise dosya yok.
        # Her iki durumda başarı True, dosya orijinal konumda yok.

    def test_missing_file_returns_error(self):
        ok, err = safe_remove_to_trash("C:/nonexistent_path_xyz_12345.wav")
        self.assertFalse(ok)
        self.assertIsNotNone(err)

    def test_returns_tuple(self):
        result = safe_remove_to_trash("C:/nonexistent_xyz.wav")
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)

    def test_empty_path(self):
        ok, _ = safe_remove_to_trash("")
        self.assertFalse(ok)


class SafeFilenameTests(unittest.TestCase):
    def test_basic_filename(self):
        result = safe_filename_from_text("Merhaba dünya")
        self.assertTrue(result.endswith(".wav"))
        self.assertIn("merhaba", result.lower())

    def test_empty_text(self):
        result = safe_filename_from_text("")
        self.assertTrue(result.endswith(".wav"))
        self.assertIn("ses", result)

    def test_custom_suffix(self):
        result = safe_filename_from_text("Test", suffix=".mp3")
        self.assertTrue(result.endswith(".mp3"))


class UniquePathTests(unittest.TestCase):
    def test_first_call_returns_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = unique_path(tmp, "test.wav")
            self.assertEqual(p.name, "test.wav")

    def test_second_call_returns_unique(self):
        with tempfile.TemporaryDirectory() as tmp:
            unique_path(tmp, "test.wav").touch()
            p2 = unique_path(tmp, "test.wav")
            self.assertIn("_2", p2.name)


if __name__ == "__main__":
    unittest.main()
