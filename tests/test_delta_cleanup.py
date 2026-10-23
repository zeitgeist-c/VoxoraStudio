"""Delta temizliği: silinen dosyaların boş klasörleri de silinmeli.

Gerçek hata: 0.6.1 → 0.7.0 deltası 5610 dosyayı siler (torch gider) ama
``apply_staged`` yalnız dosyaları siliyordu; 354 boş klasör kurulumda
kalıyordu. 544 KB artık — küçük ama kirli, ve "torch yok" iddiasını bozar.
"""
from __future__ import annotations

import unittest
from pathlib import Path

from app import delta


class RemovedDirsCleanupTests(unittest.TestCase):
    def _apply(self, tmp_path: Path) -> Path:
        root = tmp_path / "installed"
        (root / "lib" / "torch" / "cuda").mkdir(parents=True)
        (root / "lib" / "torch" / "cuda" / "a.pyd").write_bytes(b"old")
        (root / "lib" / "torch" / "b.py").write_bytes(b"old")
        (root / "lib" / "keep").mkdir()
        (root / "lib" / "keep" / "c.py").write_bytes(b"keep")

        stage = tmp_path / "staged"
        (stage / "lib").mkdir(parents=True)
        (stage / "lib" / "new.py").write_bytes(b"new")

        manifest = delta.DeltaManifest(
            version="2", base_version="1",
            files=[{"path": "lib/new.py", "sha256": "", "size": 3}],
            removed=["lib/torch/cuda/a.pyd", "lib/torch/b.py"],
            total_bytes=3)
        delta.apply_staged(stage, manifest, root)
        return root

    def test_empty_dirs_removed_after_file_delete(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = self._apply(Path(tmp))
            self.assertFalse((root / "lib" / "torch").exists(),
                             "boş torch klasörü silinmeli")
            self.assertFalse((root / "lib" / "torch" / "cuda").exists())

    def test_non_empty_and_unrelated_dirs_kept(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = self._apply(Path(tmp))
            self.assertTrue((root / "lib" / "keep" / "c.py").is_file())
            self.assertTrue((root / "lib").is_dir())
            self.assertTrue((root / "lib" / "new.py").is_file())


if __name__ == "__main__":
    unittest.main()
