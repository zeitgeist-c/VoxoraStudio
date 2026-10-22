"""Brand identity and legacy-name guardrails for Voxora Studio."""
from __future__ import annotations

import re
import unittest
from pathlib import Path

from app import branding


REPO_ROOT = Path(__file__).resolve().parents[1]


def _iss_section(text: str, name: str) -> str:
    """Bir .iss bölümünün yalnız yönerge satırları (yorumlar ve boşlar atılır)."""
    body = text.split(f"[{name}]", 1)[1].split("[", 1)[0]
    return "\n".join(
        line for line in body.splitlines()
        if line.strip() and not line.lstrip().startswith(";"))


class BrandingContractTests(unittest.TestCase):
    def test_canonical_product_identity(self):
        self.assertEqual(branding.DISPLAY_NAME, "Voxora Studio")
        self.assertEqual(branding.TECHNICAL_NAME, "VoxoraStudio")
        self.assertEqual(branding.APP_USER_MODEL_ID, "Voxora.Studio")
        self.assertEqual(branding.BRAND_PRIMARY, "VOXORA")
        self.assertEqual(branding.BRAND_SECONDARY, "STUDIO")
        self.assertEqual(
            branding.TECHNICAL_TAGLINE,
            "Chatterbox Multilingual • Yerel üretim",
        )
        self.assertEqual(branding.LOG_FILENAME, "VoxoraStudio.log")
        self.assertEqual(branding.__version__, "0.7.0")
        self.assertEqual(branding.PACKAGE_STEM, "VoxoraStudio-0.7.0")
        # Kurulum sabit klasore yazar; EXE adı sürüm taşımaz ki kısayollar kırılmasın.
        self.assertEqual(branding.EXECUTABLE_NAME, "VoxoraStudio.exe")

    def test_release_build_is_driven_by_authoritative_version(self):
        build_text = (REPO_ROOT / "build.bat").read_text(encoding="utf-8")
        self.assertIn('findstr /b "__version__" app\\version.py', build_text)
        self.assertIn('set "PACKAGE_STEM=VoxoraStudio-%APP_VERSION%"', build_text)
        self.assertIn("--onedir", build_text)
        self.assertIn("--noconsole", build_text)
        self.assertNotIn('--collect-all "torch"', build_text)
        self.assertNotIn('--exclude-module "setuptools"', build_text)

    def test_build_produces_installer(self):
        """Build, sürüm taşıyan bir kurulum dosyası üretmeli."""
        build_text = (REPO_ROOT / "build.bat").read_text(encoding="utf-8")
        self.assertIn("installer\\VoxoraStudio.iss", build_text)
        self.assertIn("/DAppVersion=%APP_VERSION%", build_text)
        installer = (REPO_ROOT / "installer" / "VoxoraStudio.iss").read_text(encoding="utf-8")
        # Sabit hedef klasör + sürümsüz EXE: kısayollar her sürümde aynı yeri gösterir.
        self.assertIn("DefaultDirName={autopf}\\VoxoraStudio", installer)
        self.assertIn("CloseApplications=yes", installer)
        self.assertIn("RestartApplications=yes", installer)
        # Kullanıcı verisi program klasörüne yazılmaz.
        self.assertNotIn("{app}\\state", installer)

    def test_silent_update_relaunches_app(self):
        """Sessiz (uygulama içi) güncellemeden sonra program geri açılmalı.

        Regresyon: `[Run]` satırında `skipifsilent` varken sessiz kurulum
        programı başlatmıyor, güncelleme sonrası uygulama kapalı kalıyordu.
        """
        installer = (REPO_ROOT / "installer" / "VoxoraStudio.iss").read_text(encoding="utf-8")
        run_section = _iss_section(installer, "Run")
        self.assertIn("Filename: \"{app}\\{#AppExe}\"", run_section)
        self.assertNotIn("skipifsilent", run_section)
        self.assertIn("runasoriginaluser", run_section)

    def test_install_delete_keeps_uninstaller(self):
        """Temiz kurulum davranışı kaldırma kaydını bozmamalı."""
        installer = (REPO_ROOT / "installer" / "VoxoraStudio.iss").read_text(encoding="utf-8")
        delete_section = _iss_section(installer, "InstallDelete")
        self.assertIn('"{app}\\_internal"', delete_section)
        self.assertIn('"{app}\\VoxoraStudio.exe"', delete_section)
        self.assertNotIn("unins", delete_section.lower())

    def test_installer_targets_version_independent_exe(self):
        """Kurulumun gösterdiği EXE adı sürüm taşımaz; kısayol da onu gösterir."""
        from app.branding import EXECUTABLE_NAME

        self.assertEqual(EXECUTABLE_NAME, "VoxoraStudio.exe")
        installer = (REPO_ROOT / "installer" / "VoxoraStudio.iss").read_text(encoding="utf-8")
        self.assertIn('Source: "{#SourceDir}\\VoxoraStudio.exe"', installer)
        self.assertIn("Filename: \"{app}\\{#AppExe}\"", installer)


class LegacyBrandGuardTests(unittest.TestCase):
    """Scan hand-maintained product sources, never generated/user folders."""

    _TEXT_SUFFIXES = {".py", ".md", ".txt", ".bat", ".vbs"}
    _LEGACY_ALLOWED = {
        "run.bat": {
            "TXTOTTS_*",
            "TXTOTTS_SHOW_CONSOLE",
            "TXTOTTS_HIDDEN",
        },
        "README.md": {
            "TXTOTTS_SHOW_CONSOLE",
            "TXTOTTS_HIDDEN",
        },
        "README.tr.md": {
            "TXTOTTS_SHOW_CONSOLE",
            "TXTOTTS_HIDDEN",
        },
    }

    @classmethod
    def _source_files(cls):
        roots = (REPO_ROOT, REPO_ROOT / "app", REPO_ROOT / "scripts", REPO_ROOT / "tests")
        seen = set()
        for root in roots:
            iterator = root.iterdir() if root == REPO_ROOT else root.rglob("*")
            for path in iterator:
                if not path.is_file() or path.suffix.lower() not in cls._TEXT_SUFFIXES:
                    continue
                if "__pycache__" in path.parts or path.resolve() == Path(__file__).resolve():
                    continue
                resolved = path.resolve()
                if resolved not in seen:
                    seen.add(resolved)
                    yield path

    def test_old_product_name_is_absent_from_maintained_sources(self):
        old_name = re.compile("txt" + "to" + "tts", re.IGNORECASE)
        violations = []
        for path in self._source_files():
            text = path.read_text(encoding="utf-8", errors="replace")
            if old_name.search(text):
                violations.append(path.relative_to(REPO_ROOT).as_posix())
        self.assertEqual(violations, [])

    def test_only_documented_launcher_aliases_remain(self):
        legacy_env = re.compile("TXT" + r"OTTS_[A-Z0-9_*]+")
        violations = []
        observed = {}
        for path in self._source_files():
            text = path.read_text(encoding="utf-8", errors="replace")
            matches = set(legacy_env.findall(text))
            if not matches:
                continue
            relative = path.relative_to(REPO_ROOT).as_posix()
            observed[relative] = matches
            unexpected = matches - self._LEGACY_ALLOWED.get(relative, set())
            if unexpected:
                violations.append((relative, sorted(unexpected)))

        self.assertEqual(violations, [])
        self.assertEqual(observed, self._LEGACY_ALLOWED)


if __name__ == "__main__":
    unittest.main()
