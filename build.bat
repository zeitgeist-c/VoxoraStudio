@echo off
REM txttoTTS PyInstaller build - .exe uretimi
REM Uyari: Olusan .exe ~2-4 GB olabilir (torch + CUDA DLL'leri icerir).
REM Cikti: dist\txttoTTS\  (tasima icin bu klasoru kopyala)

cd /d "%~dp0"
set "PROJECT_ROOT=%CD%"
set "PYTHONPATH=%PROJECT_ROOT%"

set "PYEXE=.venv\Scripts\python.exe"

if not exist "%PYEXE%" (
    echo [HATA] Sanal ortam bulunamadi. Once setup.bat calistir.
    pause
    exit /b 1
)

echo ============================================================
echo txttoTTS .exe build
echo ============================================================
echo.

echo [1/3] Gerekli import'lar dogrulaniyor...
"%PYEXE%" -c "
import torch, torchaudio, PyQt6, sounddevice, soundfile, pydub, send2trash, numpy
print('[OK] Tum import'lar basarili.')
"
if errorlevel 1 (
    echo [HATA] Import dogrulamasi basarisiz. Once setup.bat calistir.
    pause
    exit /b 1
)

echo.
echo [2/3] PyInstaller ile build baslatiliyor...
echo NOT: Bu islem ~10-20 dakika surebilir.
echo.

"%PYEXE%" -m PyInstaller ^
    --onedir ^
    --noconsole ^
    --name "txttoTTS" ^
    --icon "app\assets\txttotts.ico" ^
    --distpath "dist" ^
    --workpath "build_temp" ^
    --hidden-import "PyQt6.sip" ^
    --hidden-import "torch" ^
    --hidden-import "torchaudio" ^
    --hidden-import "sounddevice" ^
    --hidden-import "soundfile" ^
    --hidden-import "pydub" ^
    --hidden-import "send2trash" ^
    --hidden-import "numpy" ^
    --collect-all "torch" ^
    --collect-all "torchaudio" ^
    --exclude-module "matplotlib" ^
    --exclude-module "scipy" ^
    --exclude-module "PIL" ^
    --exclude-module "pandas" ^
    --exclude-module "notebook" ^
    --exclude-module "IPython" ^
    --exclude-module "setuptools" ^
    --exclude-module "pip" ^
    --exclude-module "packaging" ^
    --add-data "bin;bin" ^
    --add-data "app\assets;app\assets" ^
    "app.py"

if errorlevel 1 (
    echo [HATA] Build basarisiz. Yukaridaki hata mesajini kontrol et.
    pause
    exit /b 1
)

echo.
echo [3/3] Build tamam.
echo.
echo ============================================================
echo txttoTTS.exe olusturuldu: dist\txttoTTS\
echo ============================================================
echo.
echo Calistirmak icin: dist\txttoTTS\txttoTTS.exe
echo.
echo Baska PC'ye tasimak icin:
echo   1. dist\txttoTTS\ klasorunu USB/diske kopyala
echo   2. Hedef PC'de klasorun icindeki txttoTTS.exe'yi calistir
echo   3. NVIDIA GPU icin CUDA surucusu yuklu olmali
echo      (https://www.nvidia.com/Download/index.aspx)
echo   4. ffmpeg yoksa MP3 kayit calismaz
echo      winget install Gyan.FFmpeg --accept-package-agreements --accept-source-agreements
echo.
pause
