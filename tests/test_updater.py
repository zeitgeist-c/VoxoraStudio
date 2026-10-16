"""app.updater saf-yol testleri: sürüm karşılaştırma, paket ayrıştırma, ZIP güvenliği, göç."""
from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from app import updater


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
        stem = f"VoxoraStudio-{version}"
        pkg = root / stem
        (pkg / "_internal").mkdir(parents=True)
        (pkg / f"{stem}.exe").write_bytes(b"MZfake")
        (pkg / f"{stem}.bat").write_text("@echo off\r\n", encoding="ascii")
        archive = root / f"{stem}.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            for path in pkg.rglob("*"):
                if path.is_file():
                    zf.write(path, f"{stem}/{path.relative_to(pkg).as_posix()}")
        return archive

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
            # eski klasör silinmez
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


if __name__ == "__main__":
    unittest.main()
