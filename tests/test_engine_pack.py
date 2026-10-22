"""Motor paketi (.vxp) ve indirici testleri.

Gerçek ağa çıkılmaz: yerel HTTP sunucusu ve yerel dosyalarla sınanır.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
import unittest
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from app import engine_pack, downloader


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class TempEnginesDir(unittest.TestCase):
    """Testler kullanıcı veri klasörünü kirletmesin."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self._env = patch.dict(os.environ, {"VOXORA_MODELS_DIR": str(self.root / "models")})
        self._env.start()
        self._userdata = patch("app.paths.user_data_root", return_value=self.root)
        self._userdata.start()

    def tearDown(self):
        self._userdata.stop()
        self._env.stop()
        self._tmp.cleanup()


class BuildAndVerifyTests(TempEnginesDir):
    def _source(self) -> Path:
        source = self.root / "payload-src"
        (source / "chatterbox").mkdir(parents=True)
        (source / "chatterbox" / "__init__.py").write_text("VERSION = '1.0'\n", encoding="utf-8")
        (source / "torch_lite.py").write_text("x = 1\n", encoding="utf-8")
        # Pakete girmemesi gerekenler
        (source / "__pycache__").mkdir()
        (source / "__pycache__" / "junk.pyc").write_bytes(b"junk")
        return source

    def test_build_creates_manifest_with_hashes(self):
        pack = self.root / "chatterbox.vxp"
        manifest = engine_pack.build_pack(
            self._source(), pack, engine="chatterbox", engine_version="1.2.3"
        )
        self.assertEqual(manifest.engine, "chatterbox")
        self.assertEqual(manifest.engine_version, "1.2.3")
        self.assertEqual(manifest.file_count, 2)  # __pycache__ hariç
        self.assertTrue(pack.is_file())
        with zipfile.ZipFile(pack) as archive:
            names = archive.namelist()
        self.assertIn("manifest.json", names)
        self.assertIn("payload/chatterbox/__init__.py", names)
        self.assertNotIn("payload/__pycache__/junk.pyc", names)

    def test_verify_accepts_good_pack(self):
        pack = self.root / "c.vxp"
        engine_pack.build_pack(self._source(), pack, engine="chatterbox", engine_version="1.0")
        manifest = engine_pack.verify_pack(pack)
        self.assertEqual(manifest.engine, "chatterbox")

    def test_verify_rejects_corrupted_payload(self):
        pack = self.root / "c.vxp"
        engine_pack.build_pack(self._source(), pack, engine="chatterbox", engine_version="1.0")
        # ZIP'i yeniden yaz: bir dosyanın içeriğini boz, manifest eski kalsın.
        broken = self.root / "broken.vxp"
        with zipfile.ZipFile(pack) as source, zipfile.ZipFile(broken, "w") as sink:
            for name in source.namelist():
                data = source.read(name)
                if name == "payload/torch_lite.py":
                    data = b"tampered = True\n"
                sink.writestr(name, data)
        with self.assertRaises(engine_pack.EnginePackError) as ctx:
            engine_pack.verify_pack(broken)
        self.assertIn("tutmuyor", str(ctx.exception))

    def test_verify_rejects_missing_file(self):
        pack = self.root / "c.vxp"
        engine_pack.build_pack(self._source(), pack, engine="chatterbox", engine_version="1.0")
        broken = self.root / "missing.vxp"
        with zipfile.ZipFile(pack) as source, zipfile.ZipFile(broken, "w") as sink:
            for name in source.namelist():
                if name == "payload/torch_lite.py":
                    continue
                sink.writestr(name, source.read(name))
        with self.assertRaises(engine_pack.EnginePackError) as ctx:
            engine_pack.verify_pack(broken)
        self.assertIn("eksik", str(ctx.exception).lower())

    def test_verify_rejects_non_pack(self):
        fake = self.root / "fake.vxp"
        with zipfile.ZipFile(fake, "w") as archive:
            archive.writestr("hello.txt", "merhaba")
        with self.assertRaises(engine_pack.EnginePackError) as ctx:
            engine_pack.verify_pack(fake)
        self.assertIn("manifest", str(ctx.exception).lower())

    def test_verify_rejects_bad_format_version(self):
        pack = self.root / "c.vxp"
        engine_pack.build_pack(self._source(), pack, engine="chatterbox", engine_version="1.0")
        future = self.root / "future.vxp"
        with zipfile.ZipFile(pack) as source, zipfile.ZipFile(future, "w") as sink:
            for name in source.namelist():
                data = source.read(name)
                if name == "manifest.json":
                    manifest = json.loads(data)
                    manifest["format_version"] = 99
                    data = json.dumps(manifest).encode()
                sink.writestr(name, data)
        with self.assertRaises(engine_pack.EnginePackError) as ctx:
            engine_pack.verify_pack(future)
        self.assertIn("desteklenmiyor", str(ctx.exception))


class InstallTests(TempEnginesDir):
    def _pack(self, version: str = "1.0") -> Path:
        source = self.root / f"src-{version}"
        (source / "pkg").mkdir(parents=True)
        (source / "pkg" / "mod.py").write_text(f"V = '{version}'\n", encoding="utf-8")
        pack = self.root / f"chatterbox-{version}.vxp"
        engine_pack.build_pack(source, pack, engine="chatterbox", engine_version=version)
        return pack

    def test_install_places_files_and_state(self):
        pack = self._pack("1.0")
        manifest = engine_pack.install_pack(pack)
        self.assertEqual(manifest.engine_version, "1.0")
        self.assertTrue(engine_pack.is_installed("chatterbox"))
        self.assertEqual(engine_pack.installed_version("chatterbox"), "1.0")
        installed = engine_pack.site_packages_dir("chatterbox") / "pkg" / "mod.py"
        self.assertTrue(installed.is_file())
        self.assertIn("V = '1.0'", installed.read_text(encoding="utf-8"))
        state = json.loads((engine_pack.engine_root("chatterbox") / "installed.json").read_text())
        self.assertEqual(state["engine"], "chatterbox")

    def test_reinstall_replaces_previous(self):
        engine_pack.install_pack(self._pack("1.0"))
        engine_pack.install_pack(self._pack("2.0"))
        self.assertEqual(engine_pack.installed_version("chatterbox"), "2.0")
        content = (engine_pack.site_packages_dir("chatterbox") / "pkg" / "mod.py").read_text()
        self.assertIn("2.0", content)
        # Eski .old klasörü kalmamalı
        leftovers = [p for p in engine_pack.engine_root("chatterbox").parent.iterdir()
                     if ".old-" in p.name]
        self.assertEqual(leftovers, [])

    def test_remove_engine(self):
        engine_pack.install_pack(self._pack("1.0"))
        self.assertTrue(engine_pack.remove_engine("chatterbox"))
        self.assertFalse(engine_pack.is_installed("chatterbox"))
        self.assertFalse(engine_pack.remove_engine("chatterbox"))  # ikinci kez: yok

    def test_install_rejects_wrong_sha(self):
        pack = self._pack("1.0")
        with self.assertRaises(engine_pack.EnginePackError) as ctx:
            engine_pack.install_pack(pack, expected_sha256="0" * 64)
        self.assertIn("bozuldu", str(ctx.exception))
        self.assertFalse(engine_pack.is_installed("chatterbox"))

    def test_failed_install_keeps_previous(self):
        engine_pack.install_pack(self._pack("1.0"))
        # Bozuk paket: manifest var ama payload bozuk
        bad_source = self.root / "bad-src"
        (bad_source / "pkg").mkdir(parents=True)
        (bad_source / "pkg" / "mod.py").write_text("V = 'bad'\n", encoding="utf-8")
        bad = self.root / "bad.vxp"
        engine_pack.build_pack(bad_source, bad, engine="chatterbox", engine_version="9.9")
        tampered = self.root / "tampered.vxp"
        with zipfile.ZipFile(bad) as source, zipfile.ZipFile(tampered, "w") as sink:
            for name in source.namelist():
                data = source.read(name)
                if name == "payload/pkg/mod.py":
                    data = b"V = 'hacked'\n"
                sink.writestr(name, data)
        with self.assertRaises(engine_pack.EnginePackError):
            engine_pack.install_pack(tampered)
        # Eski kurulum bozulmadan duruyor
        self.assertEqual(engine_pack.installed_version("chatterbox"), "1.0")

    def test_zip_slip_is_rejected(self):
        target_root = self.root / "slip"
        for evil in ("../evil.txt", "..\\evil.txt", "C:/Windows/evil.txt", "/etc/evil"):
            with self.assertRaises(engine_pack.EnginePackError):
                engine_pack._safe_join(target_root, evil)

    def test_not_installed_when_folder_missing(self):
        self.assertEqual(engine_pack.installed_version("chatterbox"), "")
        self.assertFalse(engine_pack.is_installed("chatterbox"))


class _Handler(BaseHTTPRequestHandler):
    """Range destekli minik sunucu (gerçek indirme akışını sınamak için)."""

    payload = b""
    supports_range = True
    requested_ranges: list = []

    def do_GET(self):  # noqa: N802 (stdlib adlandırması)
        data = type(self).payload
        header = self.headers.get("Range")
        type(self).requested_ranges.append(header)
        start = 0
        if header and self.supports_range and header.startswith("bytes="):
            start = int(header.split("=", 1)[1].split("-", 1)[0] or 0)
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{len(data) - 1}/{len(data)}")
        else:
            self.send_response(200)
        body = data[start:]
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass


class DownloadTests(TempEnginesDir):
    def setUp(self):
        super().setUp()
        _Handler.payload = bytes(range(256)) * 4096  # 1 MB
        _Handler.supports_range = True
        _Handler.requested_ranges = []
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        super().tearDown()

    def test_download_writes_verified_file(self):
        target = self.root / "out" / "file.bin"
        result = downloader.download_file(
            f"{self.base}/file.bin",
            target,
            expected_size=len(_Handler.payload),
            expected_sha256=_sha(_Handler.payload),
        )
        self.assertTrue(result.is_file())
        self.assertEqual(result.read_bytes(), _Handler.payload)

    def test_download_rejects_bad_hash(self):
        with self.assertRaises(downloader.DownloadError) as ctx:
            downloader.download_file(
                f"{self.base}/file.bin",
                self.root / "bad.bin",
                expected_sha256="0" * 64,
            )
        self.assertIn("bozuk", str(ctx.exception))
        self.assertFalse((self.root / "bad.bin").exists())

    def test_download_resumes_from_part(self):
        target = self.root / "resume.bin"
        part = target.with_name(f"{target.name}.{'x' * 12}.part")
        half = len(_Handler.payload) // 2
        part.write_bytes(_Handler.payload[:half])
        downloader.download_file(
            f"{self.base}/resume.bin",
            target,
            expected_size=len(_Handler.payload),
            expected_sha256=_sha(_Handler.payload),
            revision="x" * 12,
        )
        self.assertEqual(target.read_bytes(), _Handler.payload)
        # Sunucudan Range istendi mi?
        self.assertTrue(any(r and r.startswith("bytes=") for r in _Handler.requested_ranges))

    def test_download_restarts_when_server_ignores_range(self):
        _Handler.supports_range = False
        target = self.root / "norange.bin"
        part = target.with_name(f"{target.name}.{'y' * 12}.part")
        part.write_bytes(b"stale")
        downloader.download_file(
            f"{self.base}/norange.bin",
            target,
            expected_size=len(_Handler.payload),
            expected_sha256=_sha(_Handler.payload),
            revision="y" * 12,
        )
        self.assertEqual(target.read_bytes(), _Handler.payload)

    def test_existing_valid_file_is_skipped(self):
        target = self.root / "already.bin"
        target.write_bytes(_Handler.payload)
        _Handler.requested_ranges = []
        downloader.download_file(
            f"{self.base}/already.bin",
            target,
            expected_size=len(_Handler.payload),
            expected_sha256=_sha(_Handler.payload),
        )
        self.assertEqual(_Handler.requested_ranges, [])  # ağa hiç çıkılmadı

    def test_cancel_raises_and_keeps_part(self):
        target = self.root / "cancel.bin"
        calls = {"n": 0}

        def stop():
            calls["n"] += 1
            return calls["n"] > 2

        with self.assertRaises(downloader.Cancelled):
            downloader.download_file(
                f"{self.base}/cancel.bin",
                target,
                expected_size=len(_Handler.payload),
                should_stop=stop,
                revision="z" * 12,
            )
        self.assertFalse(target.exists())

    def test_progress_is_reported(self):
        seen: list = []
        downloader.download_file(
            f"{self.base}/progress.bin",
            self.root / "progress.bin",
            expected_size=len(_Handler.payload),
            expected_sha256=_sha(_Handler.payload),
            on_progress=seen.append,
        )
        self.assertTrue(seen)
        self.assertEqual(seen[-1].total, len(_Handler.payload))
        self.assertEqual(seen[-1].completed, len(_Handler.payload))
        self.assertGreaterEqual(seen[-1].percent, 99.9)

    def test_disk_space_guard(self):
        with self.assertRaises(downloader.DownloadError) as ctx:
            downloader.free_space_for(self.root, needed_bytes=10 ** 15)
        self.assertIn("disk", str(ctx.exception).lower())


class HfModelDownloadTests(unittest.TestCase):
    """HF indiricisi: manifest ayrıştırma mantığı (ağa çıkmadan)."""

    def test_manifest_builds_rows_with_lfs_hashes(self):
        manifest = {
            "sha": "abc123def456",
            "siblings": [
                {"rfilename": "model.safetensors", "size": 100,
                 "lfs": {"sha256": "a" * 64, "size": 100}},
                {"rfilename": "config.json", "size": 20},
                {"rfilename": "README.md", "size": 5},
            ],
        }
        with patch.object(downloader, "_hf_manifest", return_value=manifest), \
             patch.object(downloader, "download_file") as fake:
            fake.return_value = Path("x")
            downloader.download_hf_model(
                "org/model",
                Path(tempfile.gettempdir()) / "voxora-hf-test",
                allow_patterns=["model.safetensors", "config.json"],
            )
        calls = fake.call_args_list
        self.assertEqual(len(calls), 2)
        urls = [c.args[0] for c in calls]
        self.assertTrue(any("model.safetensors" in u for u in urls))
        self.assertTrue(any("config.json" in u for u in urls))
        self.assertFalse(any("README.md" in u for u in urls))
        # LFS dosyası sha256 ile, küçük dosya sha olmadan doğrulanır.
        weights = [c for c in calls if "model.safetensors" in c.args[0]][0]
        self.assertEqual(weights.kwargs["expected_sha256"], "a" * 64)
        config = [c for c in calls if "config.json" in c.args[0]][0]
        self.assertEqual(config.kwargs["expected_sha256"], "")

    def test_missing_requested_file_raises(self):
        manifest = {"sha": "abc", "siblings": [{"rfilename": "other.bin", "size": 1}]}
        with patch.object(downloader, "_hf_manifest", return_value=manifest):
            with self.assertRaises(downloader.DownloadError) as ctx:
                downloader.download_hf_model(
                    "org/model",
                    Path(tempfile.gettempdir()) / "voxora-hf-test2",
                    allow_patterns=["model.safetensors"],
                )
        self.assertIn("yok", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
