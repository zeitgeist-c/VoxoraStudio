"""app.updater saf-yol testleri: sürüm karşılaştırma, paket ayrıştırma, ZIP güvenliği, göç."""
from __future__ import annotations

import json
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from app import updater


def make_package_zip(root: Path, version: str) -> Path:
    """Sahte sürüm paketi: VoxoraStudio-X.Y.Z/ kökü + EXE/BAT + ZIP asset'i."""
    stem = f"VoxoraStudio-{version}"
    pkg = root / stem
    (pkg / "_internal").mkdir(parents=True, exist_ok=True)
    (pkg / f"{stem}.exe").write_bytes(b"MZfake")
    (pkg / f"{stem}.bat").write_text("@echo off\r\n", encoding="ascii")
    archive = root / f"{stem}.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        for path in pkg.rglob("*"):
            if path.is_file():
                zf.write(path, f"{stem}/{path.relative_to(pkg).as_posix()}")
    return archive


class VersionTests(unittest.TestCase):
    def test_parse_and_compare(self):
        self.assertEqual(updater.parse_version("v0.3.10"), (0, 3, 10))
        self.assertEqual(updater.parse_version("0.3.10-beta"), (0, 3, 10))
        self.assertTrue(updater.is_newer("v0.4.0", "0.3.9"))
        self.assertTrue(updater.is_newer("0.3.10", "0.3.9"))
        self.assertFalse(updater.is_newer("0.3.4", "0.3.4"))
        self.assertFalse(updater.is_newer("0.3.3", "0.3.4"))
        with self.assertRaises(updater.UpdateError):
            updater.parse_version("yeni-sürüm")


class ReleasePayloadTests(unittest.TestCase):
    def payload(self, tag="v0.4.0", name="VoxoraStudio-0.4.0.zip", digest="sha256:ab12"):
        return {
            "tag_name": tag,
            "html_url": "https://github.com/x/releases/tag/" + tag,
            "assets": [{
                "name": name,
                "browser_download_url": "https://example.test/" + name,
                "digest": digest,
                "size": 123,
            }],
        }

    def test_parses_matching_asset(self):
        info = updater.parse_release(self.payload())
        self.assertEqual(info.version, "0.4.0")
        self.assertEqual(info.sha256, "ab12")  # "sha256:" öneki soyulur
        self.assertEqual(info.size, 123)

    def test_rejects_missing_asset(self):
        with self.assertRaises(updater.UpdateError):
            updater.parse_release(self.payload(name="Other.zip"))

    def test_rejects_unparseable_tag(self):
        with self.assertRaises(updater.UpdateError):
            updater.parse_release(self.payload(tag="sonsurum"))


class SafetyTests(unittest.TestCase):
    def test_member_paths(self):
        self.assertTrue(updater._member_is_safe("VoxoraStudio-1.0.0/app.exe"))
        self.assertTrue(updater._member_is_safe("VoxoraStudio-1.0.0/_internal/x.dll"))
        self.assertFalse(updater._member_is_safe("../evil.dll"))
        self.assertFalse(updater._member_is_safe("a/../../evil.dll"))
        self.assertFalse(updater._member_is_safe("/abs/evil.dll"))
        self.assertFalse(updater._member_is_safe("C:/evil.dll"))
        self.assertFalse(updater._member_is_safe("C:\\evil.dll"))


class StampTests(unittest.TestCase):
    def test_missing_or_old_stamp_is_old(self):
        self.assertTrue(updater.last_check_is_old(""))
        self.assertTrue(updater.last_check_is_old("not-a-date"))
        self.assertTrue(updater.last_check_is_old("2020-01-01T00:00:00"))
        self.assertFalse(updater.last_check_is_old(updater.now_stamp()))


class ExtractMigrateTests(unittest.TestCase):
    """Kardeş klasöre açma + kullanıcı verisi göçü, sahte paketle uçtan uca."""

    def _make_package_zip(self, root: Path, version: str) -> Path:
        return make_package_zip(root, version)

    def test_extract_and_migrate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old_root = root / "VoxoraStudio-0.3.4"
            old_state = old_root / "_internal" / "state"
            old_state.mkdir(parents=True)
            (old_state / "settings.json").write_text(json.dumps({
                "output_dir": str(old_root / "outputs"),
                "audio_prompt_path": str(old_root / "voices" / "ben.wav"),
                "theme": "dark",
            }), encoding="utf-8")
            (old_state / "history.json").write_text("[]", encoding="utf-8")
            (old_root / "voices").mkdir()
            (old_root / "voices" / "ben.wav").write_bytes(b"RIFFfake")
            (old_root / "outputs").mkdir()
            (old_root / "outputs" / "once.wav").write_bytes(b"RIFFold")
            (old_root / "models").mkdir()
            (old_root / "models" / "m.onnx").write_bytes(b"MODEL")

            archive = self._make_package_zip(root, "0.4.0")
            launcher = updater.extract(archive, "0.4.0", root,
                                       settings_source=old_root,
                                       state_source=old_state)
            new_root = root / "VoxoraStudio-0.4.0"
            self.assertEqual(launcher, new_root / "VoxoraStudio-0.4.0.bat")
            self.assertTrue((new_root / "VoxoraStudio-0.4.0.exe").is_file())

            settings = json.loads(
                (new_root / "_internal" / "state" / "settings.json").read_text(encoding="utf-8"))
            self.assertEqual(settings["output_dir"], str(new_root / "outputs"))
            self.assertEqual(settings["audio_prompt_path"],
                             str(new_root / "voices" / "ben.wav"))
            self.assertTrue((new_root / "voices" / "ben.wav").is_file())
            self.assertTrue((new_root / "outputs" / "once.wav").is_file())
            self.assertTrue((new_root / "models" / "m.onnx").is_file())
            # extract eski klasöre dokunmaz; silme ayrı adım (cleanup_pending)
            self.assertTrue(old_root.is_dir())

    def test_existing_new_state_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old_root = root / "VoxoraStudio-0.3.4"
            old_state = old_root / "_internal" / "state"
            old_state.mkdir(parents=True)
            (old_state / "settings.json").write_text('{"theme": "light"}', encoding="utf-8")
            archive = self._make_package_zip(root, "0.4.0")
            # hedefte önceden var olan state korunur (yarım deneme senaryosu)
            pre = root / "VoxoraStudio-0.4.0" / "_internal" / "state"
            pre.mkdir(parents=True)
            (pre / "settings.json").write_text('{"theme": "dark"}', encoding="utf-8")
            updater.extract(archive, "0.4.0", root, settings_source=old_root,
                            state_source=old_state)
            # extract hedefi silip yeniden açar; göç, boş state'e eski veriyi koyar
            data = json.loads((pre / "settings.json").read_text(encoding="utf-8"))
            self.assertEqual(data["theme"], "light")

    def test_zip_slip_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "VoxoraStudio-0.4.0.zip"
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("VoxoraStudio-0.4.0/../../evil.dll", b"x")
            with self.assertRaises(updater.UpdateError):
                updater.extract(archive, "0.4.0", root)

    def test_wrong_root_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "VoxoraStudio-0.4.0.zip"
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("Other-0.4.0/app.exe", b"MZ")
            with self.assertRaises(updater.UpdateError):
                updater.extract(archive, "0.4.0", root)


class FormatTests(unittest.TestCase):
    """Canlı indirme göstergesinin metin yardımcıları."""

    def test_format_bytes(self):
        self.assertEqual(updater.format_bytes(0), "0 B")
        self.assertEqual(updater.format_bytes(512), "512 B")
        self.assertEqual(updater.format_bytes(2048), "2.00 KB")
        self.assertEqual(updater.format_bytes(20 * 1024), "20.0 KB")
        self.assertEqual(updater.format_bytes(538 * 1024 * 1024), "538.0 MB")
        self.assertEqual(updater.format_bytes(int(1.5 * 1024 ** 3)), "1.50 GB")

    def test_format_speed(self):
        self.assertEqual(updater.format_speed(0), "—")
        self.assertEqual(updater.format_speed(12.4 * 1024 * 1024), "12.4 MB/s")

    def test_format_eta(self):
        self.assertEqual(updater.format_eta(0.2), "1 sn")
        self.assertEqual(updater.format_eta(45), "45 sn")
        self.assertEqual(updater.format_eta(192), "3 dk 12 sn")
        self.assertEqual(updater.format_eta(3600 + 5 * 60), "1 sa 05 dk")


class RateMeterTests(unittest.TestCase):
    def test_rate_over_window(self):
        meter = updater.RateMeter(window=4.0)
        meter.add(0, 0.0)
        meter.add(1_000_000, 1.0)
        meter.add(2_000_000, 2.0)
        self.assertAlmostEqual(meter.rate(), 1_000_000.0, delta=1)
        self.assertEqual(updater.RateMeter().rate(), 0.0)

    def test_old_samples_drop(self):
        meter = updater.RateMeter(window=1.5)
        meter.add(0, 0.0)
        meter.add(1000, 1.0)
        meter.add(4000, 2.0)
        meter.add(6000, 3.0)
        # pencere 1.5 sn: t=2.0'dan eskisi düşer -> (2.0, 4000) ve (3.0, 6000)
        self.assertAlmostEqual(meter.rate(), 2000.0, delta=1)


class CleanupTests(unittest.TestCase):
    """Eski sürüm klasörlerinin tespiti ve güncelleme sonrası temizliği."""

    def test_stale_package_dirs_filters(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp)
            for name in ("VoxoraStudio-0.5.0", "VoxoraStudio-0.6.0",
                         "VoxoraStudio-0.6.1", "Other", "VoxoraStudio-yeni"):
                (parent / name).mkdir()
            stale = updater.stale_package_dirs(parent, "0.6.1")
            self.assertEqual([p.name for p in stale],
                             ["VoxoraStudio-0.5.0", "VoxoraStudio-0.6.0"])

    def test_write_and_consume_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            old_root = tmp_path / "VoxoraStudio-0.5.0"
            old_state = old_root / "_internal" / "state"
            old_state.mkdir(parents=True)
            new_root = tmp_path / "VoxoraStudio-0.6.0"
            (new_root / "_internal" / "state").mkdir(parents=True)
            newer = tmp_path / "VoxoraStudio-0.6.1"
            newer.mkdir()
            unrelated = tmp_path / "Belgelerim"
            unrelated.mkdir()

            targets = updater.stale_package_dirs(tmp_path, "0.6.0")
            self.assertEqual([p.name for p in targets], ["VoxoraStudio-0.5.0"])
            with mock.patch.object(updater, "package_root", return_value=old_root), \
                 mock.patch.object(updater, "state_dir", return_value=old_state):
                marker = updater.write_cleanup_marker(new_root, targets)
            self.assertIsNotNone(marker)
            self.assertTrue(marker.is_file())

            with mock.patch.object(updater, "package_root", return_value=new_root), \
                 mock.patch.object(updater, "__version__", "0.6.0"):
                removed, remaining = updater.cleanup_pending(marker)
            self.assertEqual(removed, ["VoxoraStudio-0.5.0"])
            self.assertEqual(remaining, [])
            self.assertFalse(old_root.exists())      # eski sürüm silindi
            self.assertTrue(new_root.is_dir())       # yenisi kaldı
            self.assertTrue(newer.is_dir())          # daha yeni sürüme dokunulmaz
            self.assertTrue(unrelated.is_dir())      # alakasız klasör korundu
            self.assertFalse(marker.exists())        # fiş tükendi
            self.assertIn("VoxoraStudio-0.5.0", updater.last_cleanup_result)

    def test_consume_defers_locked_targets(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            old_root = tmp_path / "VoxoraStudio-0.5.0"
            old_root.mkdir()
            new_root = tmp_path / "VoxoraStudio-0.6.0"
            (new_root / "_internal" / "state").mkdir(parents=True)
            marker = new_root / "_internal" / "state" / updater.CLEANUP_MARKER
            marker.write_text(json.dumps({"targets": [str(old_root)]}),
                              encoding="utf-8")
            with mock.patch.object(updater, "package_root", return_value=new_root), \
                 mock.patch.object(updater, "__version__", "0.6.0"), \
                 mock.patch.object(updater, "_remove_tree", return_value=False):
                removed, remaining = updater.cleanup_pending(marker)
            self.assertEqual(removed, [])
            self.assertEqual(remaining, [str(old_root)])
            self.assertTrue(old_root.is_dir())
            self.assertTrue(marker.is_file())        # sonraki açılışta yine denenecek
            self.assertEqual(
                json.loads(marker.read_text(encoding="utf-8"))["targets"],
                [str(old_root)])

    def test_consume_ignores_unsafe_targets(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            outer = tmp_path / "VoxoraStudio-0.5.0"
            new_root = outer / "VoxoraStudio-0.6.0"      # eski (iç içe) yerleşim artığı
            (new_root / "_internal" / "state").mkdir(parents=True)
            unrelated = tmp_path / "Belgelerim"
            unrelated.mkdir()
            fake_file = tmp_path / "VoxoraStudio-1.0.0"
            fake_file.write_bytes(b"dosya")
            marker = new_root / "_internal" / "state" / updater.CLEANUP_MARKER
            marker.write_text(json.dumps({"targets": [
                str(new_root),        # kendi paketi: asla
                str(outer),           # şu anki paketi yutan ata: asla
                str(unrelated),       # kalıba uymayan ad: asla
                str(fake_file),       # klasör değil: asla
            ]}), encoding="utf-8")
            with mock.patch.object(updater, "package_root", return_value=new_root), \
                 mock.patch.object(updater, "__version__", "0.6.0"):
                removed, remaining = updater.cleanup_pending(marker)
            self.assertEqual(removed, [])
            self.assertEqual(remaining, [])
            self.assertTrue(new_root.is_dir())
            self.assertTrue(outer.is_dir())
            self.assertTrue(unrelated.is_dir())
            self.assertTrue(fake_file.is_file())
            self.assertFalse(marker.exists())            # geçersiz fiş tükendi


class SwapScriptTests(unittest.TestCase):
    def test_script_waits_starts_and_cleans_itself(self):
        launcher = Path(r"C:\X\VoxoraStudio-0.6.0\VoxoraStudio-0.6.0.bat")
        text = updater.swap_script_text(4242, launcher)
        self.assertIn(":wait", text)
        self.assertIn('PID eq 4242', text)
        self.assertIn("goto wait", text)
        self.assertIn(f'start "" "{launcher}"', text)
        self.assertIn('del "%~f0"', text)


class InstallWorkerTests(unittest.TestCase):
    """'İndir ve Kur' akışı: updater erişimi + kardeş klasör + temizlik fişi.

    Regresyon: worker, updater'a modül düzeyinde erişemediği için canlıda
    NameError ile düşüyor ve indirme hiç başlamıyordu.
    """

    def test_install_flow(self):
        from app import workers  # PyQt6 bağımlılığı yalnız bu testte

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            old_root = tmp_path / "VoxoraStudio-0.5.0"
            old_state = old_root / "_internal" / "state"
            old_state.mkdir(parents=True)
            (old_state / "settings.json").write_text(
                json.dumps({"theme": "dark"}), encoding="utf-8")
            archive = make_package_zip(tmp_path, "0.6.0")
            info = updater.UpdateInfo(
                version="0.6.0",
                asset_name="VoxoraStudio-0.6.0.zip",
                download_url="https://example.test/VoxoraStudio-0.6.0.zip",
                sha256="",
                size=123,
                page_url="")

            def fake_download(_info, dest, progress=None, cancel=None, phase=None):
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(archive, dest)
                if phase:
                    phase("verify")
                if progress:
                    progress(info.size, info.size)
                return dest

            captured = []
            worker = workers.UpdateWorker("0.5.0", mode="install", info=info)
            worker.installed.connect(lambda v, l: captured.append((v, l)))
            with mock.patch.object(updater, "package_root", return_value=old_root), \
                 mock.patch.object(updater, "state_dir", return_value=old_state), \
                 mock.patch.object(updater, "download", side_effect=fake_download):
                worker._install()

            self.assertEqual(len(captured), 1)
            version, launcher = captured[0]
            self.assertEqual(version, "0.6.0")
            new_root = tmp_path / "VoxoraStudio-0.6.0"
            self.assertEqual(Path(launcher), new_root / "VoxoraStudio-0.6.0.bat")
            self.assertTrue((new_root / "VoxoraStudio-0.6.0.exe").is_file())
            # yeni paket eskisinin İÇİNE değil YANINA açıldı
            self.assertFalse((old_root / "VoxoraStudio-0.6.0").exists())
            self.assertEqual(new_root.parent, old_root.parent)
            # kullanıcı verisi yeni pakete göçtü, eski paket henüz duruyor
            self.assertTrue((new_root / "_internal" / "state" / "settings.json").is_file())
            self.assertTrue(old_root.is_dir())
            # eski sürüm için temizlik fişi yeni paketin state'ine bırakıldı
            marker = new_root / "_internal" / "state" / updater.CLEANUP_MARKER
            self.assertTrue(marker.is_file())
            self.assertEqual(
                json.loads(marker.read_text(encoding="utf-8"))["targets"],
                [str(old_root)])


if __name__ == "__main__":
    unittest.main()
