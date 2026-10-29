"""Güvenlik regresyonları: uzak manifest yol kaçışı, motor adı, delta fişi.

Dört gerçek açık kanıtlanmış ve burada kilitlenmiştir:

1. ``downloader.download_hf_model`` Hugging Face manifestindeki ``rfilename``
   değerini doğrulamıyordu; ``../kacis.bin`` model klasörünün dışına yazılıyordu.
2. ``engine_pack.engine_root`` motor adını doğrulamıyordu; manifestteki
   ``../../kacis`` kurulumu kullanıcı veri kökünün dışına taşıyordu.
3. ``engine_pack.install_pack`` arşivdeki manifest DIŞI payload girdilerini de
   açıyordu; imzasız bir ``*.pth`` motor klasörüne düşüp Python açılışında kod
   çalıştırabilirdi.
4. ``updater.run_pending_delta`` kullanıcının yazabildiği ``state/`` içindeki
   fişi doğrulamadan YÖNETİCİ yetkili işçiye veriyordu (yerel yetki yükseltme).
"""
from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from app import downloader, engine_pack, updater


class HuggingFacePathTraversalTests(unittest.TestCase):
    def _manifest(self, name: str) -> dict:
        return {"sha": "rev1", "siblings": [
            {"rfilename": "ok.bin", "size": 10},
            {"rfilename": name, "size": 10},
        ]}

    def test_parent_segments_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(downloader, "_hf_manifest",
                                   return_value=self._manifest("../kacis.bin")), \
                    mock.patch.object(downloader, "download_file"), \
                    mock.patch.object(downloader, "free_space_for"):
                with self.assertRaises(downloader.DownloadError):
                    downloader.download_hf_model("x/y", tmp,
                                                 allow_patterns=["../kacis.bin"])

    def test_drive_and_absolute_paths_are_rejected(self):
        for evil in ("C:/Windows/evil.bin", "/abs.bin", "a/../../b.bin"):
            with tempfile.TemporaryDirectory() as tmp:
                with mock.patch.object(downloader, "_hf_manifest",
                                       return_value=self._manifest(evil)), \
                        mock.patch.object(downloader, "download_file"), \
                        mock.patch.object(downloader, "free_space_for"):
                    with self.assertRaises(downloader.DownloadError):
                        downloader.download_hf_model("x/y", tmp,
                                                     allow_patterns=[evil])

    def test_normal_nested_name_still_downloads(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = {"sha": "rev1", "siblings": [
                {"rfilename": "sub/model.bin", "size": 4},
            ]}
            seen = {}

            def fake_download(url, dest, **kwargs):
                seen["dest"] = Path(dest)
                return dest

            with mock.patch.object(downloader, "_hf_manifest",
                                   return_value=manifest), \
                    mock.patch.object(downloader, "download_file",
                                      side_effect=fake_download), \
                    mock.patch.object(downloader, "free_space_for"):
                downloader.download_hf_model("x/y", tmp,
                                             allow_patterns=["sub/model.bin"])
            self.assertEqual(seen["dest"], Path(tmp) / "sub" / "model.bin")


class EngineNameValidationTests(unittest.TestCase):
    def test_engine_root_rejects_traversal(self):
        for evil in ("../../kacis", "..\\kacis", "C:/Windows/Temp/kacis", "", "a/b"):
            with self.assertRaises(engine_pack.EnginePackError, msg=repr(evil)):
                engine_pack.engine_root(evil)

    def test_engine_root_accepts_known_key(self):
        root = engine_pack.engine_root("chatterbox")
        self.assertEqual(root.name, "chatterbox")

    def test_install_rejects_pack_with_traversal_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = tmp_path / "src"
            source.mkdir()
            (source / "a.py").write_text("x = 1\n", encoding="utf-8")
            good = tmp_path / "good.vxp"
            engine_pack.build_pack(source, good, engine="chatterbox",
                                   engine_version="1.0")
            with zipfile.ZipFile(good) as archive:
                members = {name: archive.read(name) for name in archive.namelist()}
            manifest = json.loads(members["manifest.json"])
            manifest["engine"] = "../../kacis"
            members["manifest.json"] = json.dumps(manifest).encode("utf-8")
            evil = tmp_path / "evil.vxp"
            with zipfile.ZipFile(evil, "w") as archive:
                for name, body in members.items():
                    archive.writestr(name, body)
            with self.assertRaises(engine_pack.EnginePackError):
                engine_pack.install_pack(evil)
            self.assertFalse((tmp_path / "kacis").exists())


class InstallPackManifestWhitelistTests(unittest.TestCase):
    def test_payload_not_in_manifest_is_not_extracted(self):
        """Manifest dışı ``*.pth`` motor klasörüne inmemeli."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = tmp_path / "src"
            source.mkdir()
            (source / "a.py").write_text("x = 1\n", encoding="utf-8")
            base = tmp_path / "base.vxp"
            engine_pack.build_pack(source, base, engine="chatterbox",
                                   engine_version="1.0")
            with zipfile.ZipFile(base) as archive:
                members = {name: archive.read(name) for name in archive.namelist()}
            members["payload/zararli.pth"] = b"import os\n"
            evil = tmp_path / "evil.vxp"
            with zipfile.ZipFile(evil, "w") as archive:
                for name, body in members.items():
                    archive.writestr(name, body)
            engines = tmp_path / "engines"
            with mock.patch("app.paths.engines_dir", return_value=engines):
                manifest = engine_pack.install_pack(evil)
            installed = engines / manifest.engine / "site-packages"
            self.assertTrue((installed / "a.py").is_file())
            self.assertFalse((installed / "zararli.pth").exists())


class PendingDeltaValidationTests(unittest.TestCase):
    def setUp(self):
        self.app_root = Path(tempfile.mkdtemp(prefix="voxora-app-"))
        # ``staged`` yalnız bu kökün altında geçerli sayılır; testte geçici
        # klasörü açıkça buraya sabitliyoruz ki makinenin TMPDIR'ından bağımsız
        # olsun (Windows'ta her mkdtemp zaten TMPDIR altında olurdu).
        self.temp_root = Path(tempfile.mkdtemp(prefix="voxora-temp-"))
        self.staged = self.temp_root / "staged"
        self.staged.mkdir()
        # EXE kontrolü geçsin: işçi kurulumu sahte.
        (self.app_root / "VoxoraStudio.exe").write_bytes(b"")
        self.patchers = (
            mock.patch.object(updater, "package_root", return_value=self.app_root),
            mock.patch.object(updater.tempfile, "gettempdir",
                              return_value=str(self.temp_root)),
        )
        for patcher in self.patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

    def _payload(self, **overrides) -> dict:
        payload = {
            "staged": str(self.staged),
            "target": str(self.app_root),
            "version": "0.7.3",
            "base_version": "0.7.2",
            "files": [{"path": "_internal/a.dll", "sha256": "a" * 64}],
            "removed": ["_internal/eski.dll"],
        }
        payload.update(overrides)
        return payload

    def test_valid_payload_passes(self):
        self.assertEqual(updater.validate_pending_delta(self._payload()), "")

    def test_foreign_target_is_rejected(self):
        payload = self._payload(target="C:/Windows/System32/drivers/etc")
        self.assertIn("program folder", updater.validate_pending_delta(payload))

    def test_staged_outside_temp_is_rejected(self):
        payload = self._payload(staged=str(self.app_root / "x"))
        self.assertIn("temp folder", updater.validate_pending_delta(payload))

    def test_traversal_in_file_list_is_rejected(self):
        payload = self._payload(files=[
            {"path": "../../Windows/System32/kotu.dll", "sha256": "a" * 64}])
        self.assertIn("Unsafe path", updater.validate_pending_delta(payload))

    def test_absolute_removed_path_is_rejected(self):
        payload = self._payload(removed=["C:/Windows/System32/kritik.dll"])
        self.assertIn("Unsafe", updater.validate_pending_delta(payload))

    def test_bad_digest_is_rejected(self):
        payload = self._payload(files=[{"path": "a.dll", "sha256": "deadbeef"}])
        self.assertIn("sha256", updater.validate_pending_delta(payload))

    def test_run_pending_delta_drops_poisoned_marker(self):
        state = Path(tempfile.mkdtemp(prefix="voxora-state-"))
        marker = state / "pending_delta.json"
        marker.write_text(json.dumps(self._payload(
            target="C:/Windows/System32")), encoding="utf-8")
        with mock.patch.object(updater, "state_dir", return_value=state), \
                mock.patch.object(updater, "write_delta_worker") as writer:
            self.assertIsNone(updater.run_pending_delta())
        writer.assert_not_called()
        self.assertFalse(marker.exists())


if __name__ == "__main__":
    unittest.main()
