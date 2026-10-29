"""app.updater ve app.paths testleri: sürüm, kurulum paketi, sağlama, yollar, göç."""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app import paths, updater


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
    """Güncelleme artık ZIP değil, Setup.exe arar."""

    def payload(self, tag="v0.6.0", name="VoxoraStudio-0.6.0-Setup.exe",
                digest="sha256:ab12"):
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

    def test_parses_matching_installer(self):
        info = updater.parse_release(self.payload())
        self.assertEqual(info.version, "0.6.0")
        self.assertEqual(info.asset_name, "VoxoraStudio-0.6.0-Setup.exe")
        self.assertEqual(info.sha256, "ab12")  # "sha256:" öneki soyulur
        self.assertEqual(info.size, 123)

    def test_rejects_missing_installer(self):
        with self.assertRaises(updater.UpdateError):
            updater.parse_release(self.payload(name="Other.exe"))

    def test_rejects_zip_only_release(self):
        """Eski ZIP akışıyla yayınlanmış bir sürüm kabul edilmez."""
        with self.assertRaises(updater.UpdateError):
            updater.parse_release(self.payload(name="VoxoraStudio-0.6.0.zip"))

    def test_rejects_unparseable_tag(self):
        with self.assertRaises(updater.UpdateError):
            updater.parse_release(self.payload(tag="sonsurum"))


class InstallerNameTests(unittest.TestCase):
    def test_installer_regex_accepts_only_own_setup(self):
        self.assertTrue(updater.INSTALLER_RE.match("VoxoraStudio-0.6.0-Setup.exe"))
        self.assertFalse(updater.INSTALLER_RE.match("VoxoraStudio-0.6.0.zip"))
        self.assertFalse(updater.INSTALLER_RE.match("baska-Setup.exe"))
        self.assertFalse(updater.INSTALLER_RE.match("VoxoraStudio-Setup.exe"))

    def test_silent_flags(self):
        self.assertIn("/VERYSILENT", updater.SILENT_FLAGS)
        self.assertIn("/RESTARTAPPLICATIONS", updater.SILENT_FLAGS)
        self.assertIn("/NORESTART", updater.SILENT_FLAGS)


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


class DownloadTests(unittest.TestCase):
    """Boyut/özet doğrulaması: doğrulanmamış dosya asla kalmaz."""

    def _info(self, payload: bytes, sha: str = "") -> updater.UpdateInfo:
        return updater.UpdateInfo(
            version="0.6.0",
            asset_name="VoxoraStudio-0.6.0-Setup.exe",
            download_url="https://example.test/x.exe",
            sha256=sha,
            size=len(payload),
            page_url="")

    def _patch_urlopen(self, payload: bytes):
        class FakeResponse:
            headers = {"Content-Length": str(len(payload))}

            def __init__(self):
                self._rest = payload

            def __enter__(self):
                return self

            def __exit__(self, *_exc):
                return False

            def read(self, _size=-1):
                chunk, self._rest = self._rest, b""
                return chunk

        return mock.patch.object(updater.urllib.request, "urlopen",
                                 lambda *_a, **_k: FakeResponse())

    def test_hash_mismatch_removes_file(self):
        payload = b"MZsetup-bytes"
        info = self._info(payload, sha="0" * 64)
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / info.asset_name
            with self._patch_urlopen(payload):
                with self.assertRaises(updater.UpdateError):
                    updater.download(info, dest)
            self.assertFalse(dest.exists())

    def test_hash_match_keeps_file(self):
        payload = b"MZsetup-bytes"
        info = self._info(payload, sha=hashlib.sha256(payload).hexdigest())
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / info.asset_name
            with self._patch_urlopen(payload):
                result = updater.download(info, dest)
            self.assertTrue(result.is_file())

    def test_cancel_removes_file(self):
        import threading

        payload = b"MZ" * 4096
        info = self._info(payload, sha=hashlib.sha256(payload).hexdigest())
        cancel = threading.Event()
        cancel.set()
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / info.asset_name
            with self._patch_urlopen(payload):
                with self.assertRaises(updater.UpdateError):
                    updater.download(info, dest, cancel=cancel)
            self.assertFalse(dest.exists())


class SpawnInstallerTests(unittest.TestCase):
    def test_missing_installer_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(updater.UpdateError):
                updater.spawn_installer(Path(tmp) / "yok.exe")

    def test_launches_with_silent_flags(self):
        with tempfile.TemporaryDirectory() as tmp:
            installer = Path(tmp) / "VoxoraStudio-0.6.0-Setup.exe"
            installer.write_bytes(b"MZ")
            calls = []

            def fake_runas(exe, parameters):
                calls.append((exe, parameters))
                return 4321

            with mock.patch.object(updater, "_shell_execute_runas", fake_runas), \
                 mock.patch.object(updater, "spawn_relaunch_watchdog") as watchdog:
                pid = updater.spawn_installer(installer)
            self.assertEqual(pid, 4321)
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0][0], installer)
            for flag in ("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART",
                         "/RESTARTAPPLICATIONS", "/CLOSEAPPLICATIONS"):
                self.assertIn(flag, calls[0][1])
            watchdog.assert_called_once_with(4321)

    def test_restart_false_drops_restart_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            installer = Path(tmp) / "VoxoraStudio-0.6.0-Setup.exe"
            installer.write_bytes(b"MZ")
            captured = {}

            def fake_runas(exe, parameters):
                captured["parameters"] = parameters
                return 99

            with mock.patch.object(updater, "_shell_execute_runas", fake_runas), \
                 mock.patch.object(updater, "spawn_relaunch_watchdog") as watchdog:
                updater.spawn_installer(installer, restart=False)
            self.assertNotIn("/RESTARTAPPLICATIONS", captured["parameters"])
            watchdog.assert_not_called()

    def test_uac_cancel_is_reported_not_crashed(self):
        """Kullanıcı UAC'yi reddederse anlaşılır hata; program açık kalır."""
        with tempfile.TemporaryDirectory() as tmp:
            installer = Path(tmp) / "VoxoraStudio-0.6.0-Setup.exe"
            installer.write_bytes(b"MZ")

            def fake_runas(exe, parameters):
                raise updater.UpdateError("yönetici izni verilmedi")

            with mock.patch.object(updater, "_shell_execute_runas", fake_runas), \
                 mock.patch.object(updater, "spawn_relaunch_watchdog") as watchdog:
                with self.assertRaises(updater.UpdateError):
                    updater.spawn_installer(installer)
            watchdog.assert_not_called()

    def test_runas_uses_shell_execute(self):
        """Popen yükseltme isteyen EXE'de WinError 740 verir; ShellExecute şart."""
        source = Path(updater.__file__).read_text(encoding="utf-8")
        self.assertIn("ShellExecuteExW", source)
        self.assertIn('info.lpVerb = "runas"', source)
        self.assertIn("SEE_MASK_NOCLOSEPROCESS", source)
        self.assertIn("_ERROR_CANCELLED", source)


class RelaunchWatchdogTests(unittest.TestCase):
    """Sessiz güncelleme sonrası programın gerçekten geri açılması."""

    def test_script_waits_for_setup_then_starts_exe(self):
        exe = Path(r"C:\Program Files\VoxoraStudio\VoxoraStudio.exe")
        text = updater._relaunch_script_text(1234, exe)
        self.assertIn(":wait", text)
        self.assertIn('PID eq 1234', text)
        self.assertIn("goto wait", text)
        self.assertIn(f'start "" "{exe}"', text)
        self.assertIn('del "%~f0"', text)
        # Sınırsız bekleme yok; MSYS `find`ine düşen boru yok.
        self.assertIn("GEQ 1800", text)
        self.assertNotIn("| find ", text)
        self.assertNotIn("timeout /t", text)

    def test_watchdog_written_to_temp_and_detached(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "Program"
            root.mkdir()
            (root / "VoxoraStudio.exe").write_bytes(b"MZ")
            launches = []

            def fake_popen(args, **kwargs):
                launches.append((args, kwargs))

                class Proc:
                    pass

                return Proc()

            with mock.patch("app.paths.package_root", return_value=root), \
                 mock.patch.object(updater.tempfile, "gettempdir", return_value=tmp), \
                 mock.patch.object(updater.subprocess, "Popen", fake_popen):
                script = updater.spawn_relaunch_watchdog(555)
            self.assertIsNotNone(script)
            self.assertTrue(script.is_file())
            self.assertEqual(script.parent, Path(tmp))
            body = script.read_text(encoding="ascii")
            self.assertIn("PID eq 555", body)
            self.assertEqual(len(launches), 1)
            self.assertNotIn("CREATE_NO_WINDOW", str(launches[0][1]))

    def test_watchdog_skipped_when_exe_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch("app.paths.package_root", return_value=Path(tmp)), \
                 mock.patch.object(updater.tempfile, "gettempdir", return_value=tmp):
                self.assertIsNone(updater.spawn_relaunch_watchdog(7))


class CleanupTests(unittest.TestCase):
    def test_cleanup_removes_only_own_installers(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            keep = folder / "baska.exe"
            keep.write_bytes(b"x")
            stale = folder / "VoxoraStudio-0.6.0-Setup.exe"
            stale.write_bytes(b"x")
            with mock.patch.object(updater, "updates_dir", return_value=folder):
                result = updater.cleanup_updates_dir()
            self.assertFalse(stale.exists())
            self.assertTrue(keep.is_file())      # yabancı dosyaya dokunulmaz
            self.assertIn("cleaned", result)

    def test_cleanup_noop_on_empty_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(updater, "updates_dir", return_value=Path(tmp)):
                self.assertEqual(updater.cleanup_updates_dir(), "")

    def test_run_cleanup_async_reports_work(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            with mock.patch.object(updater, "updates_dir", return_value=folder):
                self.assertFalse(updater.run_cleanup_async())
            (folder / "VoxoraStudio-0.6.0-Setup.exe").write_bytes(b"x")
            with mock.patch.object(updater, "updates_dir", return_value=folder):
                self.assertTrue(updater.run_cleanup_async())


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


class PathLayoutTests(unittest.TestCase):
    """Program klasörü ile kullanıcı verisi ayrı olmalı (güncelleme siler)."""

    def test_frozen_layout_separates_program_and_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            program = Path(tmp) / "Programs" / "VoxoraStudio"
            local = Path(tmp) / "LocalAppData"
            program.mkdir(parents=True)
            exe = program / "VoxoraStudio.exe"
            exe.write_bytes(b"MZ")
            with mock.patch.object(paths.sys, "frozen", True, create=True), \
                 mock.patch.object(paths.sys, "executable", str(exe)), \
                 mock.patch.dict(paths.os.environ, {"LOCALAPPDATA": str(local)}):
                self.assertEqual(paths.package_root(), program)
                data = paths.user_data_root()
                self.assertEqual(data, local / "VoxoraStudio")
                # Veri program klasörünün İÇİNDE olmamalı: kurulum orayı siler.
                with self.assertRaises(ValueError):
                    data.relative_to(program)
                self.assertEqual(paths.state_dir(), data / "state")
                self.assertEqual(paths.logs_dir(), data / "logs")
                self.assertEqual(paths.outputs_dir(), data / "outputs")
                self.assertEqual(paths.updates_dir(), data / "updates")
                with mock.patch.dict(paths.os.environ, {"LOCALAPPDATA": str(local)}):
                    paths.ensure_user_dirs()
                    for directory in (paths.state_dir(), paths.logs_dir(),
                                      paths.outputs_dir()):
                        self.assertTrue(directory.is_dir())

    def test_source_layout_keeps_repo_root(self):
        # Testler ve geliştirme: donmuş değil, depo kökü kullanılır.
        self.assertFalse(getattr(paths.sys, "frozen", False))
        self.assertEqual(paths.user_data_root(), paths.package_root())
        self.assertEqual(paths.state_dir(), paths.package_root() / "state")


class LegacyMigrationTests(unittest.TestCase):
    """Eski taşınabilir paket (Program Files dışı) verisi devralınmalı."""

    def _make_legacy(self, parent: Path, version="0.5.5") -> Path:
        legacy = parent / f"VoxoraStudio-{version}"
        state = legacy / "_internal" / "state"
        state.mkdir(parents=True)
        (state / "settings.json").write_text(json.dumps({
            "theme": "dark",
            "output_dir": str(legacy / "_internal" / "outputs"),
            "audio_prompt_path": str(legacy / "voices" / "ben.wav"),
        }), encoding="utf-8")
        (state / "history.json").write_text("[]", encoding="utf-8")
        (legacy / "_internal" / "outputs").mkdir(parents=True)
        (legacy / "_internal" / "outputs" / "eski.wav").write_bytes(b"RIFF")
        (legacy / "voices").mkdir()
        (legacy / "voices" / "ben.wav").write_bytes(b"RIFF")
        return legacy

    def test_detects_only_versioned_packages(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            downloads = home / "Downloads" / "Programs"
            downloads.mkdir(parents=True)
            self._make_legacy(downloads)
            (downloads / "VoxoraStudio-yeni").mkdir()
            (downloads / "BaskaProgram").mkdir()
            with mock.patch.object(paths.Path, "home", return_value=home), \
                 mock.patch.dict(paths.os.environ, {"LOCALAPPDATA": str(home / "Local")}):
                found = paths.legacy_portable_packages()
            self.assertEqual([p.name for p in found], ["VoxoraStudio-0.5.5"])

    def test_migrates_state_and_relocates_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            downloads = home / "Downloads" / "Programs"
            downloads.mkdir(parents=True)
            legacy = self._make_legacy(downloads)
            data = home / "Local" / "VoxoraStudio"
            program = home / "Program Files" / "VoxoraStudio"
            program.mkdir(parents=True)
            exe = program / "VoxoraStudio.exe"
            exe.write_bytes(b"MZ")

            with mock.patch.object(paths.sys, "frozen", True, create=True), \
                 mock.patch.object(paths.sys, "executable", str(exe)), \
                 mock.patch.object(paths.Path, "home", return_value=home), \
                 mock.patch.dict(paths.os.environ, {"LOCALAPPDATA": str(home / "Local")}):
                note = paths.migrate_legacy_state()
                self.assertIn("devralındı", note)
                self.assertEqual(paths.migrate_legacy_state(), "")  # bir kez
            settings = json.loads(
                (data / "state" / "settings.json").read_text(encoding="utf-8"))
            # `_internal` sarmalayıcısı atılır; yol yeni veri köküne bağlanır.
            self.assertEqual(settings["output_dir"], str(data / "outputs"))
            self.assertEqual(settings["audio_prompt_path"], str(data / "voices" / "ben.wav"))
            self.assertTrue((data / "outputs" / "eski.wav").is_file())
            self.assertTrue((data / "voices" / "ben.wav").is_file())
            # Paket kökünde `_internal\outputs` gibi bir yer ÜRETİLMEMELİ.
            self.assertFalse((data / "_internal").exists())
            # Eski kurulum silinmez: kullanıcı karar verir.
            self.assertTrue(legacy.is_dir())

    def test_does_not_overwrite_existing_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            downloads = home / "Downloads" / "Programs"
            downloads.mkdir(parents=True)
            self._make_legacy(downloads)
            data = home / "Local" / "VoxoraStudio"
            (data / "state").mkdir(parents=True)
            (data / "state" / "settings.json").write_text('{"theme": "light"}',
                                                          encoding="utf-8")
            program = home / "Program Files" / "VoxoraStudio"
            program.mkdir(parents=True)
            exe = program / "VoxoraStudio.exe"
            exe.write_bytes(b"MZ")
            with mock.patch.object(paths.sys, "frozen", True, create=True), \
                 mock.patch.object(paths.sys, "executable", str(exe)), \
                 mock.patch.object(paths.Path, "home", return_value=home), \
                 mock.patch.dict(paths.os.environ, {"LOCALAPPDATA": str(home / "Local")}):
                self.assertEqual(paths.migrate_legacy_state(), "")
            kept = json.loads((data / "state" / "settings.json").read_text(encoding="utf-8"))
            self.assertEqual(kept["theme"], "light")

    def test_source_copy_never_migrates(self):
        with mock.patch.object(paths.sys, "frozen", False, create=True):
            self.assertEqual(paths.migrate_legacy_state(), "")


class InstallWorkerTests(unittest.TestCase):
    """'İndir ve Kur' akışı: indirir, doğrular, kurulum yolunu bildirir."""

    def test_install_downloads_setup_and_reports_path(self):
        from app import workers  # PyQt6 bağımlılığı yalnız bu testte

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            updates = tmp_path / "updates"
            payload = b"MZkurulum"
            info = updater.UpdateInfo(
                version="0.6.0",
                asset_name="VoxoraStudio-0.6.0-Setup.exe",
                download_url="https://example.test/VoxoraStudio-0.6.0-Setup.exe",
                sha256=hashlib.sha256(payload).hexdigest(),
                size=len(payload),
                page_url="")

            def fake_download(_info, dest, progress=None, cancel=None, phase=None):
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(payload)
                if phase:
                    phase("verify")
                if progress:
                    progress(len(payload), len(payload))
                return dest

            captured = []
            worker = workers.UpdateWorker("0.5.5", mode="install", info=info)
            worker.installed.connect(lambda v, p: captured.append((v, p)))
            with mock.patch.object(updater, "updates_dir", return_value=updates), \
                 mock.patch.object(updater, "download", side_effect=fake_download):
                worker._install()

            self.assertEqual(len(captured), 1)
            version, installer = captured[0]
            self.assertEqual(version, "0.6.0")
            self.assertEqual(Path(installer), updates / info.asset_name)
            # İndirme dizini program klasörünün dışında olmalı.
            self.assertNotEqual(Path(installer).parent, paths.package_root())

    def test_failure_emits_message(self):
        from app import workers

        info = updater.UpdateInfo(version="0.6.0",
                                  asset_name="VoxoraStudio-0.6.0-Setup.exe",
                                  download_url="https://example.test/x.exe",
                                  sha256="", size=1, page_url="")
        messages = []
        worker = workers.UpdateWorker("0.5.5", mode="install", info=info)
        worker.failed.connect(messages.append)
        with mock.patch.object(updater, "download",
                               side_effect=updater.UpdateError("ağ yok")):
            worker._install()
        self.assertEqual(messages, ["ağ yok"])


if __name__ == "__main__":
    unittest.main()
