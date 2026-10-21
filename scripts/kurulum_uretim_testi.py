"""Kurulu (Program Files) VoxoraStudio'da UI Automation ile gerçek üretim testi.

Kurulum sonrası doğrulama: ayarlar ve çıktı kullanıcı veri klasörüne yazılmalı,
program klasörüne hiçbir kullanıcı verisi düşmemeli.

Kullanım:
    python scripts/kurulum_uretim_testi.py "C:\\...\\VoxoraStudio"
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
EXE = ROOT / "VoxoraStudio.exe"

# Yeni yerleşim: kullanıcı verisi paketin DIŞINDA.
DATA = Path(os.environ["LOCALAPPDATA"]) / "VoxoraStudio"
STATE = DATA / "state"
OUT = DATA / "outputs"
LOG = DATA / "logs" / "VoxoraStudio.log"

STATE.mkdir(parents=True, exist_ok=True)
OUT.mkdir(parents=True, exist_ok=True)
for old in OUT.glob("*"):
    if old.is_file():
        old.unlink()
(STATE / "settings.json").write_text(
    json.dumps({"engine": "ema", "output_format": "mp3", "mp3_bitrate": "320k",
                "output_dir": str(OUT), "theme": "dark"},
               ensure_ascii=False, indent=2),
    encoding="utf-8")

start = LOG.stat().st_size if LOG.exists() else 0
proc = subprocess.Popen([str(EXE)], cwd=str(ROOT))
t0 = time.time()
ready = False
while time.time() - t0 < 300:
    if LOG.exists():
        text = LOG.read_text(encoding="utf-8", errors="replace")[start:]
        if "Aktif motor: EmaEngine" in text:
            ready = True
            break
    time.sleep(2)
print("EMA motor hazır:", ready)
if not ready:
    subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
    sys.exit(1)
time.sleep(8)

UIA = (
    "Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes, System.Windows.Forms;"
    "$root = [System.Windows.Automation.AutomationElement]::RootElement;"
    "$cond = New-Object System.Windows.Automation.PropertyCondition("
    "[System.Windows.Automation.AutomationElement]::ProcessIdProperty, %d);"
    "$win = $root.FindFirst([System.Windows.Automation.TreeScope]::Children, $cond);"
    "if (-not $win) { Write-Output 'WINDOW-YOK'; exit 0 };"
) % proc.pid


def powershell(script: str, timeout: int = 180) -> str:
    result = subprocess.run(["powershell", "-NoProfile", "-Command", script],
                            capture_output=True, text=True, timeout=timeout)
    return (result.stdout or "") + (result.stderr or "")


focus = powershell(
    UIA
    + "$all = $win.FindAll([System.Windows.Automation.TreeScope]::Descendants,"
    "[System.Windows.Automation.Condition]::TrueCondition);"
    "$target = $null;"
    "foreach ($e in $all) { $t = $e.Current.ControlType.ProgrammaticName;"
    " if ($t -eq 'ControlType.Edit' -or $t -eq 'ControlType.Document') { $target = $e; break } };"
    "if (-not $target) { Write-Output 'EDIT-YOK'; exit 0 };"
    "$target.SetFocus();"
    "Start-Sleep -Milliseconds 500;"
    "$ws = New-Object -ComObject WScript.Shell;"
    "[void]$ws.AppActivate(%d);"
    "Start-Sleep -Milliseconds 600;"
    "$target.SetFocus();"
    "Start-Sleep -Milliseconds 400;"
    "$ws.SendKeys('Kurulum sonrasi paketli surumden gonderilmis deneme cumlesi.');"
    "Start-Sleep -Milliseconds 600;"
    "$ws.SendKeys('^{ENTER}');"
    "Write-Output 'SENT-UIA'" % proc.pid,
)
print("UIA odak + yazma:", focus.strip().splitlines()[-1] if focus.strip() else "?")

t0 = time.time()
produced: Path | None = None
stable = 0
while time.time() - t0 < 400:
    files = sorted([p for p in OUT.glob("*")
                    if p.suffix.lower() in (".mp3", ".wav", ".opus")]) if OUT.is_dir() else []
    if files:
        produced = files[-1]
        size = produced.stat().st_size
        if size > 0 and size == stable:
            break
        stable = size
    time.sleep(3)

if produced:
    time.sleep(2)
    print(f"ÜRETİM: {produced.name} | {produced.stat().st_size} bayt")
    print("biçim (mp3 beklentisi):",
          "DOĞRU" if produced.suffix.lower() == ".mp3" else f"BEKLENMEDİK ({produced.suffix})")
    # Çıktı gerçekten kullanıcı veri klasöründe mi?
    print("çıktı veri klasöründe:", produced.resolve().is_relative_to(OUT.resolve()))
    print("çıktı program klasöründe DEĞİL:",
          not produced.resolve().is_relative_to(ROOT.resolve()))
    ffprobe = shutil.which("ffprobe")
    if ffprobe and produced.stat().st_size:
        info = subprocess.run(
            [ffprobe, "-v", "error", "-select_streams", "a:0",
             "-show_entries", "stream=codec_name:format=bit_rate,duration",
             "-of", "default=nw=1", str(produced)], capture_output=True, text=True).stdout.strip()
        print("ffprobe:", " | ".join(info.splitlines()))
    hist = STATE / "history.json"
    if hist.is_file():
        print("arşiv kaydı:", hist.read_text(encoding="utf-8", errors="replace")[:200])
else:
    print("ÜRETİM: çıktı klasöründe dosya yok")

# Program klasörüne kullanıcı verisi sızmış mı?
leaks = [p for p in ROOT.rglob("*")
         if p.name in ("settings.json", "history.json", "VoxoraStudio.log")
         and p.is_file()]
print("program klasörüne sızan kullanıcı verisi:", leaks or "YOK")

text2 = LOG.read_text(encoding="utf-8", errors="replace")[start:]
bad = [line for line in text2.splitlines() if "Traceback" in line or "[ERROR]" in line]
print("log:", "TEMİZ" if not bad else " | ".join(bad[:3]))
subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
