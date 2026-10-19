"""Gerçek devir testi (taklitsiz): kapanış betiği eski PID'i bekleyip yeni sürümü açar.

Regresyonlar:
- `DETACHED_PROCESS | CREATE_NEW_CONSOLE` birlikte verilemez → `WinError 87`;
  güncelleme "yeniden başlatılıyor" adımında asılı kalıyordu.
- `tasklist ... | find " PID "` PATH'e göre MSYS'in Unix `find`'ine düşüyordu;
  eşleşme olmayınca betik beklemeyi atlayıp yeni sürümü eski sürüm kapanmadan
  açıyordu.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import updater


@unittest.skipUnless(sys.platform == "win32", "Windows'a özgü devir akışı")
class LiveSwapTests(unittest.TestCase):
    def _prepare(self, tmp: Path) -> tuple[Path, Path]:
        newpkg = tmp / "VoxoraStudio-9.9.9"
        newpkg.mkdir()
        marker = tmp / "marker.txt"
        launcher = newpkg / "VoxoraStudio-9.9.9.bat"
        launcher.write_text(
            f'@echo off\r\necho yeni-surum > "{marker}"\r\n', encoding="ascii")
        return launcher, marker

    def test_swap_waits_for_old_pid_then_starts_new(self):
        with tempfile.TemporaryDirectory(prefix="voxora-swap-") as tmpdir:
            tmp = Path(tmpdir)
            launcher, marker = self._prepare(tmp)

            old = subprocess.Popen(["cmd", "/c", "ping -n 6 127.0.0.1 >NUL"])
            try:
                updater.spawn_swap(old.pid, launcher)          # gerçek çağrı
                script = launcher.with_name("voxora-swap.bat")
                self.assertTrue(script.is_file())

                time.sleep(2.5)
                self.assertFalse(marker.exists(),
                                 "Eski süreç kapanmadan yeni sürüm açılmamalı")
                self.assertTrue(script.is_file(), "Betik bekleme sırasında durmalı")

                old.terminate()
                old.wait(timeout=10)
            finally:
                if old.poll() is None:
                    old.kill()

            deadline = time.time() + 25
            while time.time() < deadline and not marker.exists():
                time.sleep(0.5)
            self.assertTrue(marker.exists(), "Eski süreç bitince yeni sürüm açılmalı")
            self.assertFalse(script.is_file(), "Betik kendini silmeli")


if __name__ == "__main__":
    unittest.main()
