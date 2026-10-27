"""Delta güncelleme testleri: manifest, doğrulama, uygulama, taban eşleşmesi."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from app import delta

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.make_delta_package import build_delta, compare  # noqa: E402


def make_package(root: Path, version: str, files: dict[str, bytes],
                 exe: bytes | None = None) -> Path:
    """Test paketi. ``exe`` verilmezse her iki sürümde EXE aynıdır."""
    pkg = root / f"VoxoraStudio-{version}"
    pkg.mkdir(parents=True)
    (pkg / "VoxoraStudio.exe").write_bytes(exe if exe is not None
                                           else b"MZ-stable-exe")
    for name, payload in files.items():
        path = pkg / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
    return pkg


class CompareTests(unittest.TestCase):
    def test_detects_changed_added_removed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old = make_package(root, "1.0.0", {
                "_internal/a.dll": b"same",
                "_internal/b.dll": b"old",
                "_internal/gone.dll": b"bye",
            })
            new = make_package(root, "1.1.0", {
                "_internal/a.dll": b"same",
                "_internal/b.dll": b"new",
                "_internal/c.dll": b"fresh",
            })
            changed, added, removed = compare(old, new)
            self.assertEqual([name for name, _d, _s in changed], ["_internal/b.dll"])
            self.assertEqual([name for name, _d, _s in added], ["_internal/c.dll"])
            self.assertEqual(removed, ["_internal/gone.dll"])

    def test_versioned_exe_name_matches_stable_name(self):
        """0.5.x'in sürümlü EXE'si ile 0.6.0'ın sabit adı eşleşmeli."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old = root / "VoxoraStudio-0.5.5"
            old.mkdir()
            (old / "VoxoraStudio-0.5.5.exe").write_bytes(b"MZsame")
            (old / "_internal").mkdir()
            new = root / "VoxoraStudio-0.6.0"
            new.mkdir()
            (new / "VoxoraStudio.exe").write_bytes(b"MZsame")
            (new / "_internal").mkdir()
            changed, added, removed = compare(old, new)
            self.assertEqual((changed, added), ([], []))

    def test_user_data_never_compared(self):
        """Program klasöründeki state/logs/outputs delta paketine girmez.

        Eski paketlerde bu klasörler ``_internal`` altındaydı (PyInstaller
        onedir çalışma zamanı verisi); yeni yapıda kullanıcı verisi program
        klasörünün dışında, ama eski paketlerle karşılaştırma yine de bu
        dosyaları dışarıda bırakmalı.
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old = make_package(root, "1.0.0", {
                "_internal/state/settings.json": b'{"a":1}',
                "logs/x.log": b"old log",
            })
            new = make_package(root, "1.1.0", {
                "_internal/state/settings.json": b'{"a":2}',
                "logs/x.log": b"new log",
                "outputs/a.mp3": b"mp3",
            })
            changed, added, removed = compare(old, new)
            self.assertEqual((changed, added, removed), ([], [], []))


class ManifestTests(unittest.TestCase):
    def _build(self, root: Path) -> Path:
        old = make_package(root, "1.0.0", {"_internal/a.dll": b"old"})
        new = make_package(root, "1.1.0", {"_internal/a.dll": b"new"})
        return build_delta(old, new, root / "delta.vxd")

    def test_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = self._build(root)
            manifest = delta.read_manifest(archive)
            self.assertEqual(manifest.version, "1.1.0")
            self.assertEqual(manifest.base_version, "1.0.0")
            # EXE iki sürümde aynı; yalnız değişen DLL pakete girer.
            self.assertEqual([entry["path"] for entry in manifest.files],
                             ["_internal/a.dll"])
            self.assertTrue(delta.can_apply(manifest, "1.0.0"))
            self.assertFalse(delta.can_apply(manifest, "0.9.0"))

    def test_missing_manifest_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "x.vxd"
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("files/x.dll", b"x")
            with self.assertRaises(delta.DeltaError):
                delta.read_manifest(archive)

    def test_unsafe_path_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "x.vxd"
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("manifest.json", json.dumps({
                    "version": "1.1.0", "base_version": "1.0.0",
                    "files": [{"path": "../evil.dll", "sha256": "", "size": 1}],
                    "removed": [], "total_bytes": 1}))
            with self.assertRaises(delta.DeltaError):
                delta.read_manifest(archive)

    def test_bad_zip_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "x.vxd"
            archive.write_bytes(b"not a zip")
            with self.assertRaises(delta.DeltaError):
                delta.read_manifest(archive)


class StageApplyTests(unittest.TestCase):
    def _build(self, root: Path) -> Path:
        old = make_package(root, "1.0.0", {"_internal/a.dll": b"old"})
        new = make_package(root, "1.1.0", {"_internal/a.dll": b"new"})
        return build_delta(old, new, root / "delta.vxd")

    def test_stage_and_apply(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = self._build(root)
            manifest = delta.read_manifest(archive)
            staged = delta.stage(archive, manifest)
            self.assertTrue((staged / "_internal" / "a.dll").is_file())
            target = root / "installed"
            target.mkdir()
            written = delta.apply_staged(staged, manifest, target)
            self.assertIn("_internal/a.dll", written)
            self.assertEqual((target / "_internal" / "a.dll").read_bytes(), b"new")
            # EXE iki sürümde aynıydı; delta onu taşımaz, yerinde kalır.
            self.assertNotIn("VoxoraStudio.exe", written)

    def test_removed_file_deleted_on_apply(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old = make_package(root, "1.0.0", {
                "_internal/old.dll": b"bye", "_internal/a.dll": b"old"})
            new = make_package(root, "1.1.0", {"_internal/a.dll": b"new"})
            archive = build_delta(old, new, root / "delta.vxd")
            manifest = delta.read_manifest(archive)
            self.assertEqual(manifest.removed, ["_internal/old.dll"])
            target = root / "installed"
            (target / "_internal").mkdir(parents=True)
            (target / "_internal" / "old.dll").write_bytes(b"bye")
            staged = delta.stage(archive, manifest)
            delta.apply_staged(staged, manifest, target)
            self.assertFalse((target / "_internal" / "old.dll").exists())

    def test_corrupt_payload_leaves_target_untouched(self):
        """Bozuk delta program klasörüne hiç dokunmamalı."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = self._build(root)
            # Paketi bozalım: dosya içeriğini değiştir ama manifest aynı kalsın.
            broken = root / "broken.vxd"
            with zipfile.ZipFile(archive) as src, zipfile.ZipFile(broken, "w") as dst:
                for item in src.namelist():
                    payload = src.read(item)
                    if item.endswith("a.dll"):
                        payload = b"tampered"
                    dst.writestr(item, payload)
            manifest = delta.read_manifest(broken)
            target = root / "installed"
            target.mkdir()
            with self.assertRaises(delta.DeltaError):
                delta.stage(broken, manifest)
            self.assertEqual(list(target.iterdir()), [])  # hedefe dokunulmadı

    def test_apply_renames_before_replacing(self):
        """Var olan dosya önce `.old`a taşınır, sonra yenisi yerine konur.

        Regresyon: çalışan EXE kendini silemiyor (WinError 5); Windows aynı
        birimde yeniden adlandırmaya izin verir. Bu yüzden sıra "rename →
        move → artığı sil" olmalı, "unlink → move" değil.
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = self._build(root)
            manifest = delta.read_manifest(archive)
            staged = delta.stage(archive, manifest)
            target = root / "installed"
            (target / "_internal").mkdir(parents=True)
            (target / "_internal" / "a.dll").write_bytes(b"old")
            written = delta.apply_staged(staged, manifest, target)
            self.assertIn("_internal/a.dll", written)
            self.assertEqual((target / "_internal" / "a.dll").read_bytes(), b"new")
            # Artık `.old` dosyası kalmamalı.
            self.assertFalse((target / "_internal" / "a.dll.old").exists())

    def test_apply_restores_old_file_when_move_fails(self):
        """Taşıma başarısız olursa eski dosya yerine döner (yarım kurulum yok)."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = self._build(root)
            manifest = delta.read_manifest(archive)
            staged = delta.stage(archive, manifest)
            target = root / "installed"
            (target / "_internal").mkdir(parents=True)
            (target / "_internal" / "a.dll").write_bytes(b"old")
            # Hazırlanmış dosyayı sil: move başarısız olacak.
            (staged / "_internal" / "a.dll").unlink()
            with self.assertRaises(delta.DeltaError):
                delta.apply_staged(staged, manifest, target)
            # Eski dosya yerinde ve bozulmamış olmalı.
            self.assertEqual((target / "_internal" / "a.dll").read_bytes(), b"old")

    def test_stage_writes_manifest_for_helper(self):
        """Yükseltilmiş ``--apply-delta`` yardımcısı manifesti staged'de arar."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = self._build(root)
            manifest = delta.read_manifest(archive)
            staged = delta.stage(archive, manifest)
            copied = staged / "manifest.json"
            self.assertTrue(copied.is_file())
            payload = json.loads(copied.read_text(encoding="utf-8"))
            self.assertEqual(payload["version"], "1.1.0")
            self.assertEqual(payload["base_version"], "1.0.0")
            self.assertEqual([entry["path"] for entry in payload["files"]],
                             ["_internal/a.dll"])

    def test_target_escape_blocked(self):
        """Manifest hedef klasör dışına yazmayı denerse reddedilir."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = self._build(root)
            manifest = delta.read_manifest(archive)
            # Manifest'i elle kurgula: `apply_staged` yol kaçışını görmeli.
            manifest.files.append({"path": "../evil.dll", "sha256": "", "size": 1})
            staged = root / "staged"
            (staged / "_internal").mkdir(parents=True, exist_ok=True)
            (staged / "_internal" / "a.dll").write_bytes(b"new")
            target = root / "installed"
            target.mkdir()
            with self.assertRaises(delta.DeltaError):
                delta.apply_staged(staged, manifest, target)
            self.assertFalse((root / "evil.dll").exists())


class PendingDeltaTests(unittest.TestCase):
    """Delta uygulama kapanışa ertelenir (dosyalar açıkken kilitli)."""

    def test_apply_delta_writes_marker_not_files(self):
        from app import updater

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "app"
            root.mkdir()
            data = Path(tmp) / "data"
            old = make_package(Path(tmp), "1.0.0", {"_internal/a.dll": b"old"})
            new = make_package(Path(tmp), "1.1.0", {"_internal/a.dll": b"new"})
            archive = build_delta(old, new, Path(tmp) / "delta.vxd")
            installed = root / "_internal"
            installed.mkdir()
            (installed / "a.dll").write_bytes(b"old")
            with mock.patch("app.paths.package_root", return_value=root), \
                 mock.patch("app.paths.state_dir", return_value=data / "state"), \
                 mock.patch.object(updater, "package_root", return_value=root), \
                 mock.patch.object(updater, "state_dir", return_value=data / "state"):
                returned = updater.apply_delta(archive, "1.0.0")
                marker = data / "state" / "pending_delta.json"
                self.assertTrue(marker.is_file())
                self.assertEqual(returned, [str(marker)])
                # Hedef dosyaya DOKUNULMAMIŞ olmalı.
                self.assertEqual((installed / "a.dll").read_bytes(), b"old")
                payload = json.loads(marker.read_text(encoding="utf-8"))
                self.assertEqual(payload["version"], "1.1.0")
                self.assertEqual([entry["path"] for entry in payload["files"]],
                                 ["_internal/a.dll"])
                self.assertTrue(Path(payload["staged"]).is_dir())

    def test_marker_rejected_for_wrong_base(self):
        from app import updater

        with tempfile.TemporaryDirectory() as tmp:
            old = make_package(Path(tmp), "1.0.0", {"_internal/a.dll": b"old"})
            new = make_package(Path(tmp), "1.1.0", {"_internal/a.dll": b"new"})
            archive = build_delta(old, new, Path(tmp) / "delta.vxd")
            with self.assertRaises(updater.UpdateError):
                updater.apply_delta(archive, "0.9.0")

    def test_apply_marker_payload_writes_files(self):
        from app import updater

        with tempfile.TemporaryDirectory() as tmp:
            staged = Path(tmp) / "staged"
            (staged / "_internal").mkdir(parents=True)
            (staged / "_internal" / "a.dll").write_bytes(b"new")
            target = Path(tmp) / "app"
            (target / "_internal").mkdir(parents=True)
            (target / "_internal" / "a.dll").write_bytes(b"old")
            written = updater._apply_marker_payload(
                staged, target,
                [{"path": "_internal/a.dll", "sha256": "", "size": 3}], [])
            self.assertEqual(written, ["_internal/a.dll"])
            self.assertEqual((target / "_internal" / "a.dll").read_bytes(), b"new")

    def test_worker_waits_for_app_pid_before_copying(self):
        """İşçi, uygulama kapanmadan dosya kopyalamamalı (kilit yüzünden)."""
        from app import updater

        payload = {"staged": r"C:\T\st", "target": r"C:\Program Files\VoxoraStudio",
                   "files": [{"path": "_internal/base_library.zip", "sha256": "abc"}],
                   "removed": []}
        ps = updater.delta_worker_ps1(
            payload, Path(r"C:\s\pending_delta.json"), Path(r"C:\s\r.json"),
            Path(r"C:\P\VoxoraStudio.exe"), 4242)
        self.assertIn("Get-Process -Id 4242", ps)
        # Bekleme döngüsü kopyalamadan ÖNCE gelmeli.
        self.assertLess(ps.index("Get-Process -Id 4242"),
                        ps.index("Copy-Item"))
        self.assertIn("Get-FileHash", ps)
        self.assertNotIn("--apply-delta-marker", ps)
        self.assertIn("base_library.zip", ps)
        # Program, işçi bitince normal kullanıcı olarak açılmalı.
        self.assertIn("explorer.exe", ps)
        self.assertIn("Remove-Item -LiteralPath $PSCommandPath", ps)

    def test_worker_bat_requests_elevation(self):
        """İşçi yönetici olarak başlatılmalı: Program Files'a yazıyor."""
        from app import updater

        bat = updater.delta_worker_bat(Path(r"C:\T\voxora-delta-1.ps1"))
        self.assertIn("-Verb RunAs", bat)
        self.assertIn("-ExecutionPolicy", bat)
        self.assertIn("Bypass", bat)
        self.assertIn('del "%~f0"', bat)

    def test_worker_ps1_escapes_single_quotes(self):
        from app import updater

        payload = {"staged": r"C:\T\it's", "target": r"C:\P",
                   "files": [{"path": "a.dll", "sha256": "x"}], "removed": []}
        ps = updater.delta_worker_ps1(
            payload, Path(r"C:\s\m.json"), Path(r"C:\s\r.json"),
            Path(r"C:\P\V.exe"), 7)
        self.assertIn("it''s", ps)

    def test_worker_verifies_hash_before_accepting(self):
        """Kopya sonrası SHA-256 tutmazsa sonuç ok:false olmalı."""
        from app import updater

        payload = {"staged": r"C:\T\st", "target": r"C:\P",
                   "files": [{"path": "a.dll", "sha256": "deadbeef"}],
                   "removed": []}
        ps = updater.delta_worker_ps1(
            payload, Path(r"C:\s\m.json"), Path(r"C:\s\r.json"),
            Path(r"C:\P\V.exe"), 7)
        self.assertIn("dogrulama tutmadi", ps)
        self.assertIn("$ok = $false", ps)

    def test_run_pending_delta_noop_without_marker(self):
        from app import updater

        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(updater, "state_dir", return_value=Path(tmp)):
                self.assertIsNone(updater.run_pending_delta())


class DeltaNamingTests(unittest.TestCase):
    """Yayın asset adı: VoxoraStudio-<hedef>-delta-<taban>.vxd"""

    def test_name_regex(self):
        from app import updater

        match = updater.DELTA_RE.match("VoxoraStudio-0.6.0-delta-0.5.5.vxd")
        self.assertIsNotNone(match)
        self.assertEqual(match.group("target"), "0.6.0")
        self.assertEqual(match.group("base"), "0.5.5")
        # Yabancı / eksik adlar reddedilir.
        self.assertIsNone(updater.DELTA_RE.match("VoxoraStudio-0.6.0.zip"))
        self.assertIsNone(updater.DELTA_RE.match("VoxoraStudio-0.6.0-delta.vxd"))
        self.assertIsNone(updater.DELTA_RE.match("baska-0.6.0-delta-0.5.5.vxd"))

    def test_parse_release_picks_matching_delta(self):
        from app import updater

        payload = {
            "tag_name": "v0.6.0",
            "html_url": "https://github.com/x/releases/tag/v0.6.0",
            "assets": [
                {"name": "VoxoraStudio-0.6.0-Setup.exe",
                 "browser_download_url": "https://example.test/setup.exe",
                 "digest": "sha256:aa", "size": 1000},
                {"name": "VoxoraStudio-0.6.0-delta-0.5.4.vxd",
                 "browser_download_url": "https://example.test/d54.vxd",
                 "digest": "sha256:bb", "size": 100},
                {"name": "VoxoraStudio-0.6.0-delta-0.5.5.vxd",
                 "browser_download_url": "https://example.test/d55.vxd",
                 "digest": "sha256:cc", "size": 90},
            ],
        }
        info = updater.parse_release(payload, current_version="0.5.5")
        self.assertEqual(info.delta_name, "VoxoraStudio-0.6.0-delta-0.5.5.vxd")
        self.assertEqual(info.delta_base, "0.5.5")
        self.assertEqual(info.delta_size, 90)
        self.assertEqual(info.delta_sha256, "cc")

    def test_delta_ignored_for_other_base(self):
        """Taban eşleşmezse delta seçilmez; tam setup iner."""
        from app import updater

        payload = {
            "tag_name": "v0.6.0",
            "assets": [
                {"name": "VoxoraStudio-0.6.0-Setup.exe",
                 "browser_download_url": "https://example.test/setup.exe",
                 "digest": "sha256:aa", "size": 1000},
                {"name": "VoxoraStudio-0.6.0-delta-0.5.4.vxd",
                 "browser_download_url": "https://example.test/d54.vxd",
                 "digest": "sha256:bb", "size": 100},
            ],
        }
        info = updater.parse_release(payload, current_version="0.5.0")
        self.assertEqual(info.delta_base, "")
        self.assertEqual(info.delta_size, 0)


if __name__ == "__main__":
    unittest.main()
