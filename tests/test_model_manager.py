"""Model yöneticisi testleri — durum makinesi, pin okuma, kurulum akışı.

Gerçek ağa çıkılmaz; indirici ve paket kurucu taklit edilir. Amaç: yanlış
"kurulu" demek (kullanıcı motoru seçer, yüklenmez) ve yarım kurulumu gizlemek
gibi hataları yakalamak.
"""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import downloader, engine_pack, engines, model_manager


class ModelManagerTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self._patches = [
            patch("app.paths.user_data_root", return_value=self.root),
            patch("app.paths.package_root", return_value=self.root),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()
        self._tmp.cleanup()

    # --- pin dosyası ------------------------------------------------------
    def test_pins_file_is_readable(self):
        data = model_manager.pins()
        self.assertIn("engines", data)
        self.assertIn("chatterbox", data["engines"])
        self.assertIn("voxcpm2", data["engines"])

    def test_every_downloadable_engine_has_a_pin(self):
        for spec in engines.ordered():
            if spec.bundled:
                continue
            entry = (model_manager.pins().get("engines") or {}).get(spec.key)
            self.assertIsNotNone(entry, f"{spec.key} için pin yok")
            self.assertIn("runtime", entry)
            self.assertIn("weights", entry)
            self.assertTrue(entry["weights"]["repo_id"])

    def test_missing_pins_file_returns_empty(self):
        with patch.object(model_manager, "_manifest_path", return_value=self.root / "yok.json"):
            self.assertEqual(model_manager.pins(), {})

    # --- URL üretimi ------------------------------------------------------
    def test_urls_are_built_from_pins(self):
        runtime_url, weights_repo = model_manager.urls_for("chatterbox")
        self.assertIn("github.com", runtime_url)
        self.assertIn("engines-v1", runtime_url)
        self.assertIn(".vxp", runtime_url)
        self.assertEqual(weights_repo, "ResembleAI/chatterbox")

    def test_urls_empty_when_pack_not_published(self):
        fake_pins = {"release_repo": "x/y", "tag": "t", "engines": {
            "chatterbox": {"runtime": {"file": ""}, "weights": {"repo_id": ""}}
        }}
        with patch.object(model_manager, "pins", return_value=fake_pins):
            self.assertEqual(model_manager.urls_for("chatterbox"), ("", ""))

    # --- durum ------------------------------------------------------------
    def test_ema_is_always_installed(self):
        state = model_manager.state_for("ema")
        self.assertTrue(state.bundled)
        self.assertTrue(state.installed)
        self.assertIn("programla gelir", state.status_text())

    def test_fresh_machine_reports_not_installed(self):
        state = model_manager.state_for("chatterbox")
        self.assertFalse(state.installed)
        self.assertFalse(state.partial)
        self.assertEqual(state.status_text(), "İndirilmedi")

    def test_unpublished_pack_is_marked(self):
        fake_pins = {"release_repo": "x/y", "tag": "t", "engines": {
            "chatterbox": {"runtime": {"file": ""}, "weights": {"repo_id": ""}}
        }}
        with patch.object(model_manager, "pins", return_value=fake_pins):
            state = model_manager.state_for("chatterbox")
        self.assertFalse(state.download_available)
        self.assertEqual(state.status_text(), "Henüz yayınlanmadı")
        self.assertIn("yayınlanmadı", state.detail)

    def test_partial_install_is_visible(self):
        """Yalnız kütüphane kuruluysa durum "yarım" demeli, "kurulu" değil."""
        (self.root / "engines" / "chatterbox" / "site-packages").mkdir(parents=True)
        (self.root / "engines" / "chatterbox" / "installed.json").write_text(
            json.dumps({"engine": "chatterbox", "engine_version": "1.0"}))
        state = model_manager.state_for("chatterbox")
        self.assertTrue(state.runtime_ok)
        self.assertFalse(state.weights_ok)
        self.assertFalse(state.installed)
        self.assertTrue(state.partial)
        self.assertIn("ağırlıklar", state.status_text())

    def test_weights_only_is_partial(self):
        weights = model_manager.weights_dir("chatterbox")
        weights.mkdir(parents=True)
        for name in model_manager.pins()["engines"]["chatterbox"]["weights"]["files"]:
            (weights / name).write_bytes(b"x")
        state = model_manager.state_for("chatterbox")
        self.assertFalse(state.runtime_ok)
        self.assertTrue(state.weights_ok)
        self.assertFalse(state.installed)
        self.assertIn("motor dosyaları", state.status_text())

    def test_fully_installed(self):
        engine_pack_dir = self.root / "engines" / "chatterbox" / "site-packages"
        engine_pack_dir.mkdir(parents=True)
        (self.root / "engines" / "chatterbox" / "installed.json").write_text(
            json.dumps({"engine": "chatterbox", "engine_version": "1.0"}))
        weights = model_manager.weights_dir("chatterbox")
        weights.mkdir(parents=True)
        for name in model_manager.pins()["engines"]["chatterbox"]["weights"]["files"]:
            (weights / name).write_bytes(b"x")
        state = model_manager.state_for("chatterbox")
        self.assertTrue(state.installed)
        self.assertFalse(state.partial)
        self.assertEqual(state.status_text(), "Kurulu")

    def test_weights_dir_for_ema_prefers_bundled(self):
        bundled = self.root / "models" / "ema-onnx"
        bundled.mkdir(parents=True)
        self.assertEqual(model_manager.weights_dir("ema"), bundled)

    def test_weights_dir_for_downloadable_engine_uses_user_data(self):
        self.assertEqual(
            model_manager.weights_dir("chatterbox"),
            self.root / "models" / "chatterbox",
        )

    # --- kurulum akışı ----------------------------------------------------
    def test_install_calls_runtime_then_weights(self):
        calls: list[str] = []

        def fake_download_file(url, dest, **kwargs):
            calls.append("runtime")
            Path(dest).parent.mkdir(parents=True, exist_ok=True)
            Path(dest).write_bytes(b"pack")
            return Path(dest)

        def fake_install_pack(path, **_kwargs):
            calls.append("install")
            target = self.root / "engines" / "chatterbox"
            (target / "site-packages").mkdir(parents=True, exist_ok=True)
            (target / "installed.json").write_text(json.dumps({"engine_version": "1.0"}))
            return engine_pack.Manifest(
                engine="chatterbox", engine_version="1.0", python="3.11",
                platform="win_amd64", files=())

        def fake_hf(repo, dest, **_kwargs):
            calls.append("weights")
            target = Path(dest)
            target.mkdir(parents=True, exist_ok=True)
            for name in model_manager.pins()["engines"]["chatterbox"]["weights"]["files"]:
                (target / name).write_bytes(b"w")
            return target

        with patch.object(downloader, "download_file", side_effect=fake_download_file), \
             patch.object(engine_pack, "install_pack", side_effect=fake_install_pack), \
             patch.object(downloader, "download_hf_model", side_effect=fake_hf):
            state = model_manager.install_engine("chatterbox")

        self.assertEqual(calls, ["runtime", "install", "weights"])
        self.assertTrue(state.installed)

    def test_install_skips_runtime_when_present(self):
        """Kütüphane kuruluysa yalnız ağırlık iner (3 GB'lık paket yeniden inmez)."""
        target = self.root / "engines" / "chatterbox"
        (target / "site-packages").mkdir(parents=True)
        (target / "installed.json").write_text(json.dumps({"engine_version": "1.0"}))
        calls: list[str] = []

        def fake_hf(repo, dest, **_kwargs):
            calls.append("weights")
            t = Path(dest)
            t.mkdir(parents=True, exist_ok=True)
            for name in model_manager.pins()["engines"]["chatterbox"]["weights"]["files"]:
                (t / name).write_bytes(b"w")
            return t

        with patch.object(downloader, "download_file") as dl, \
             patch.object(downloader, "download_hf_model", side_effect=fake_hf):
            model_manager.install_engine("chatterbox")
        dl.assert_not_called()
        self.assertEqual(calls, ["weights"])

    def test_install_refuses_unpublished_engine(self):
        fake_pins = {"release_repo": "", "tag": "", "engines": {}}
        with patch.object(model_manager, "pins", return_value=fake_pins):
            with self.assertRaises(downloader.DownloadError) as ctx:
                model_manager.install_engine("chatterbox")
        self.assertIn("yayınlanmadı", str(ctx.exception))

    def test_install_of_bundled_engine_is_noop(self):
        state = model_manager.install_engine("ema")
        self.assertTrue(state.installed)

    def test_remove_refuses_bundled_engine(self):
        with self.assertRaises(downloader.DownloadError):
            model_manager.remove_engine("ema")

    def test_remove_clears_runtime_and_weights(self):
        target = self.root / "engines" / "chatterbox"
        (target / "site-packages").mkdir(parents=True)
        (target / "installed.json").write_text(json.dumps({"engine_version": "1.0"}))
        weights = model_manager.weights_dir("chatterbox")
        weights.mkdir(parents=True)
        (weights / "x.bin").write_bytes(b"x")
        model_manager.remove_engine("chatterbox")
        self.assertFalse(target.exists())
        self.assertFalse(weights.exists())

    def test_remove_keeps_weights_when_asked(self):
        target = self.root / "engines" / "chatterbox"
        (target / "site-packages").mkdir(parents=True)
        (target / "installed.json").write_text(json.dumps({"engine_version": "1.0"}))
        weights = model_manager.weights_dir("chatterbox")
        weights.mkdir(parents=True)
        (weights / "x.bin").write_bytes(b"x")
        model_manager.remove_engine("chatterbox", remove_weights=False)
        self.assertFalse(target.exists())
        self.assertTrue(weights.exists())


class VoxCpmAdapterTests(unittest.TestCase):
    def test_adapter_reports_48k_and_languages(self):
        from app import voxcpm_engine

        adapter = voxcpm_engine.VoxCpmAdapter.__new__(voxcpm_engine.VoxCpmAdapter)
        adapter.sample_rate = voxcpm_engine.SAMPLE_RATE
        adapter.device_name = "cuda"
        self.assertEqual(adapter.sample_rate, 48_000)
        self.assertFalse(adapter.accepts_speed)
        self.assertFalse(adapter.single_language)

    def test_weight_files_are_complete(self):
        from app import voxcpm_engine

        self.assertIn("model.safetensors", voxcpm_engine.WEIGHT_FILES)
        self.assertIn("audiovae.pth", voxcpm_engine.WEIGHT_FILES)
        self.assertIn("tokenizer.json", voxcpm_engine.WEIGHT_FILES)
        # Pin dosyası ile kod aynı listeyi bilmeli.
        pinned = model_manager.pins()["engines"]["voxcpm2"]["weights"]["files"]
        self.assertEqual(set(pinned), set(voxcpm_engine.WEIGHT_FILES))


if __name__ == "__main__":
    unittest.main()
