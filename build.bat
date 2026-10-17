@echo off
REM Voxora Studio PyInstaller build - .exe uretimi
REM Hizli acilan tasinabilir klasor + es adli EXE/BAT uretir.
REM Cikti: dist\VoxoraStudio-X.Y.Z\VoxoraStudio-X.Y.Z.exe + .bat

cd /d "%~dp0"
set "PROJECT_ROOT=%CD%"
set "PYTHONPATH=%PROJECT_ROOT%"

if defined VOXORA_BUILD_PYTHON (
    set "PYEXE=%VOXORA_BUILD_PYTHON%"
) else (
    set "PYEXE=.venv\Scripts\python.exe"
)
for /f "tokens=2 delims== " %%V in ('findstr /b "__version__" app\version.py') do set "APP_VERSION=%%~V"
set "PACKAGE_STEM=VoxoraStudio-%APP_VERSION%"

if not exist "%PYEXE%" (
    echo [HATA] Sanal ortam bulunamadi. Once setup.bat calistir.
    pause
    exit /b 1
)

echo ============================================================
echo Voxora Studio .exe build
echo ============================================================
echo.

echo [1/3] Gerekli import'lar dogrulaniyor...
"%PYEXE%" -c "import torch, torchaudio, PyQt6, sounddevice, soundfile, pydub, send2trash, numpy, PyInstaller; print('[OK] Tum importlar basarili.')"
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
    --noconfirm ^
    --clean ^
    --onedir ^
    --noconsole ^
    --name "%PACKAGE_STEM%" ^
    --icon "app\assets\voxora.ico" ^
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
    --hidden-import "pkg_resources" ^
    --collect-all "perth" ^
    --exclude-module "matplotlib" ^
    --exclude-module "pandas" ^
    --exclude-module "notebook" ^
    --exclude-module "IPython" ^
    --exclude-module "pip" ^
    --copy-metadata "requests" ^
    --add-data "bin;bin" ^
    --add-data "app\assets;app\assets" ^
    "app.py"

if errorlevel 1 (
    echo [HATA] Build basarisiz. Yukaridaki hata mesajini kontrol et.
    pause
    exit /b 1
)

"%PYEXE%" scripts\make_versioned_launcher.py "dist\%PACKAGE_STEM%\%PACKAGE_STEM%.exe" --force
if errorlevel 1 (
    echo [HATA] Surumlu BAT baslaticisi olusturulamadi.
    exit /b 1
)

"%PYEXE%" scripts\make_update_package.py "dist\%PACKAGE_STEM%"
if errorlevel 1 (
    echo [HATA] Guncelleme ZIP paketi olusturulamadi.
    exit /b 1
)

echo.
echo [3/3] Build tamam.
echo.
echo ============================================================
echo %PACKAGE_STEM%.exe, %PACKAGE_STEM%.bat ve %PACKAGE_STEM%.zip olusturuldu: dist\%PACKAGE_STEM%\
echo ============================================================
echo.
echo Calistirmak icin: dist\%PACKAGE_STEM%\%PACKAGE_STEM%.bat
echo.
echo Baska PC'ye tasimak icin:
echo   1. dist\%PACKAGE_STEM%\ klasorunu USB/diske kopyala
echo   2. Hedef PC'de klasorun icindeki %PACKAGE_STEM%.bat dosyasini calistir
echo   3. NVIDIA GPU icin CUDA surucusu yuklu olmali
echo      (https://www.nvidia.com/Download/index.aspx)
echo   4. ffmpeg yoksa MP3 kayit calismaz
echo      winget install Gyan.FFmpeg --accept-package-agreements --accept-source-agreements
echo.
pause
