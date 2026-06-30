@echo off
REM txttoTTS kurulum kontrolu - Python, CUDA/PyTorch, Paketler, Perth, ffmpeg
REM Kullanim: install_check.bat

cd /d "%~dp0"
set "PROJECT_ROOT=%CD%"
set "PYTHONPATH=%PROJECT_ROOT%"
set "PYEXE=.venv\Scripts\python.exe"

echo ============================================================
echo txttoTTS kurulum kontrolu
echo ============================================================
echo.

REM 1) Sanal ortam
if not exist "%PYEXE%" (
    echo [HATA] Sanal ortam bulunamadi.
    echo Once setup.bat calistir.
    pause
    exit /b 1
)
echo [1/7] Sanal ortam: OK (.venv)

REM 2) Python surumu
echo.
echo [2/7] Python surumu...
"%PYEXE%" --version
if errorlevel 1 (
    echo [HATA] Python calistirilamiyor.
    pause
    exit /b 1
)

REM 3) PyTorch ve CUDA
echo.
echo [3/7] PyTorch ve CUDA...
"%PYEXE%" -c "
import torch, sys
ver = torch.__version__
cuda = torch.cuda.is_available()
cuda_ver = torch.version.cuda if cuda else 'yok'
gpu = torch.cuda.get_device_name(0) if cuda else 'cpu'
device_count = torch.cuda.device_count() if cuda else 0
print(f'  torch: {ver}')
print(f'  torch.version.cuda: {cuda_ver}')
print(f'  torch.cuda.is_available: {cuda}')
if cuda:
    print(f'  GPU: {gpu}')
    print(f'  GPU sayisi: {device_count}')
    # CUDA tensor test
    t = torch.tensor([1.0], device='cuda') + 2
    print(f'  CUDA tensor test: {t.item()}')
    sys.exit(0)
else:
    sys.exit(1)
"
if errorlevel 1 (
    echo [UYARI] PyTorch CUDA aktif degil.
) else (
    echo [OK] PyTorch CUDA AKTIF
)

REM 4) Chatterbox import
echo.
echo [4/7] Chatterbox import...
"%PYEXE%" -c "
try:
    from chatterbox.mtl_tts import ChatterboxMultilingualTTS
    print('  chatterbox import: OK')
except Exception as e:
    print(f'  [HATA] chatterbox import: {e}')
    raise SystemExit(1)
"
if errorlevel 1 (
    echo [UYARI] Chatterbox import edilemedi.
)

REM 5) Perth watermarker
echo.
echo [5/7] Perth watermarker...
"%PYEXE%" -c "
try:
    import perth
    w = perth.PerthImplicitWatermarker()
    print(f'  perth watermarker: {type(w).__module__}')
except Exception as e:
    print(f'  [BILGI] perth watermarker eksik: {e}')
"
if errorlevel 1 (
    echo [BILGI] Perth watermarker kontrol edilemedi.
)

REM 6) Kritik paketler
echo.
echo [6/7] Kritik paketler...
"%PYEXE%" -c "
import sys
packages = ['numpy', 'torch', 'torchaudio', 'PyQt6', 'sounddevice', 'soundfile', 'pydub', 'send2trash']
failed = []
for name in packages:
    try:
        mod = __import__(name)
        ver = getattr(mod, '__version__', '?')
        print(f'  [OK] {name} ({ver})')
    except Exception as e:
        print(f'  [HATA] {name}: {e}')
        failed.append(name)
if failed:
    print(f'Eksik: {failed}')
    sys.exit(1)
"
if errorlevel 1 (
    echo [UYARI] Bazi paketler eksik.
)

REM 7) ffmpeg
echo.
echo [7/7] ffmpeg...
ffmpeg -version >nul 2>&1
if errorlevel 1 (
    echo [UYARI] ffmpeg bulunamadi. MP3 export icin gerekli (opsiyonel).
    echo Kurulum: winget install Gyan.FFmpeg --accept-package-agreements --accept-source-agreements
) else (
    echo [OK] ffmpeg bulundu
)

echo.
echo ============================================================
echo Kontrol tamam.
echo Programi baslatmak icin: run.bat
echo ============================================================
pause
