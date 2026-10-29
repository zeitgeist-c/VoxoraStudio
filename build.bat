@echo off
REM Voxora Studio build - .exe + kurulum dosyasi uretimi
REM Cikti: dist\VoxoraStudio-X.Y.Z\VoxoraStudio.exe  (sabit EXE adi)
REM        dist\installer\VoxoraStudio-X.Y.Z-Setup.exe
REM
REM EXE adi neden surumsuz: kurulum sabit klasore ({autopf}\VoxoraStudio) yazar,
REM kisayollar VoxoraStudio.exe'yi gosterir. Surumlu EXE adi her surumde
REM kisayollari ve guncelleme yolunu kirardi.

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
set "APP_EXE=VoxoraStudio.exe"
REM Ajan/arac PATH'indeki yabanci DLL'ler pakete sizmasin (Qt acilisini bozabilir).
set "PATH=%SystemRoot%\System32;%SystemRoot%;%SystemRoot%\System32\Wbem;%SystemRoot%\System32\WindowsPowerShell\v1.0;%CD%\.venv\Scripts"
set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"

if not exist "%PYEXE%" (
    echo [HATA] Sanal ortam bulunamadi. Once setup.bat calistir.
    pause
    exit /b 1
)

echo ============================================================
echo Voxora Studio .exe + kurulum build  (v%APP_VERSION%)
echo ============================================================
echo.

echo [1/5] Gerekli import'lar dogrulaniyor...
REM EMA-ONNX-only build: torch/chatterbox/torchaudio PAKETE GIRMEZ.
REM Indirilebilir motorlar (.vxp) kendi kutuphanelerini getirir.
"%PYEXE%" -c "import PyQt6, sounddevice, soundfile, pydub, send2trash, numpy, onnxruntime, PyInstaller, normalizer_tr; print('[OK] Tum importlar basarili (torch yok, EMA ONNX)')"
if errorlevel 1 (
    echo [HATA] Import dogrulamasi basarisiz. Once setup.bat calistir.
    pause
    exit /b 1
)

echo.
echo [2/5] PyInstaller ile build baslatiliyor...
echo NOT: Bu islem ~10-20 dakika surebilir.
echo.

REM Dinamik dil kataloglarini hidden-import olarak ekle (AUD-VOX-001).
for /f "delims=" %%a in ('"%PYEXE%" scripts\catalog_hidden_imports.py') do set CATALOG_ARGS=%%a

"%PYEXE%" -m PyInstaller ^
    --noconfirm ^
    --clean ^
    --onedir ^
    --noconsole ^
    --name "VoxoraStudio" ^
    --icon "app\assets\voxora.ico" ^
    --distpath "dist" ^
    --workpath "build_temp\%PACKAGE_STEM%" ^
    --hidden-import "PyQt6.sip" ^
    --hidden-import "sounddevice" ^
    --hidden-import "soundfile" ^
    --hidden-import "pydub" ^
    --hidden-import "send2trash" ^
    --hidden-import "numpy" ^
    --hidden-import "onnxruntime" ^
    %CATALOG_ARGS% ^
    --collect-all "normalizer_tr" ^
    --exclude-module "matplotlib" ^
    --exclude-module "pandas" ^
    --exclude-module "notebook" ^
    --exclude-module "IPython" ^
    --exclude-module "pip" ^
    --exclude-module "torch" ^
    --exclude-module "torchaudio" ^
    --exclude-module "chatterbox" ^
    --exclude-module "perth" ^
    --exclude-module "diffusers" ^
    --exclude-module "transformers" ^
    --exclude-module "librosa" ^
    --exclude-module "numba" ^
    --exclude-module "scipy" ^
    --exclude-module "sklearn" ^
    --exclude-module "ema_lightning" ^
    --copy-metadata "requests" ^
    --add-data "bin;bin" ^
    --add-data "app\assets;app\assets" ^
    --add-data "assets;assets" ^
    --add-data "models\ema-onnx;models\ema-onnx" ^
    "app.py"

if errorlevel 1 (
    echo [HATA] Build basarisiz. Yukaridaki hata mesajini kontrol et.
    pause
    exit /b 1
)

"%PYEXE%" scripts\verify_build_sources.py "build_temp\%PACKAGE_STEM%\VoxoraStudio\COLLECT-00.toc"
if errorlevel 1 exit /b 1

if not exist "dist\VoxoraStudio\%APP_EXE%" (
    echo [HATA] Beklenen EXE yok: dist\VoxoraStudio\%APP_EXE%
    pause
    exit /b 1
)

echo.
echo [3/5] Paket klasoru surumleniyor...
REM `move /y` klasor hedefte "Erisim engellendi" verebiliyor (Defender taramasi);
REM Python shutil.move ayni isi guvenilir yapar.
REM DIKKAT: hedef klasor onceden varsa shutil.move onu IC ICE acar
REM (dist\X\VoxoraStudio\...). Bu yuzden hedef ONCE silinir, sonra tasinir.
"%PYEXE%" -c "import shutil;from pathlib import Path;src=Path(r'dist\VoxoraStudio');dst=Path(r'dist\%PACKAGE_STEM%');shutil.rmtree(dst, ignore_errors=True);assert not dst.exists(), 'hedef silinemedi: '+str(dst);shutil.move(str(src), str(dst));print('paket:', dst)" 
if errorlevel 1 (
    echo [HATA] dist\VoxoraStudio -^> dist\%PACKAGE_STEM% tasinamadi.
    pause
    exit /b 1
)

REM Kullanici verisi pakete sizmaz (state/logs/outputs artik program klasorunde degil).
if exist "dist\%PACKAGE_STEM%\_internal\state" rmdir /s /q "dist\%PACKAGE_STEM%\_internal\state"
if exist "dist\%PACKAGE_STEM%\_internal\logs" rmdir /s /q "dist\%PACKAGE_STEM%\_internal\logs"
if exist "dist\%PACKAGE_STEM%\_internal\outputs" rmdir /s /q "dist\%PACKAGE_STEM%\_internal\outputs"

echo.
echo [4/5] Kurulum dosyasi derleniyor (Inno Setup)...
if not exist "%ISCC%" (
    echo [HATA] Inno Setup bulunamadi. Kur: winget install JRSoftware.InnoSetup
    pause
    exit /b 1
)
if not exist "dist\installer" mkdir "dist\installer"
"%ISCC%" /Qp "installer\VoxoraStudio.iss" /DAppVersion=%APP_VERSION% /DSourceDir="%CD%\dist\%PACKAGE_STEM%"
if errorlevel 1 (
    echo [HATA] Kurulum dosyasi derlenemedi.
    pause
    exit /b 1
)

echo.
echo [5/6] Saglama toplami ve boyut...
"%PYEXE%" -c "import hashlib,pathlib; p=pathlib.Path(r'dist\installer\VoxoraStudio-%APP_VERSION%-Setup.exe'); h=hashlib.sha256(p.read_bytes()).hexdigest(); print(f'{p}  {p.stat().st_size/1048576:.1f} MB'); print('SHA256', h)"

echo.
echo [6/6] Delta guncelleme paketi (varsa onceki surumle fark)...
"%PYEXE%" scripts\make_delta_candidates.py "%APP_VERSION%"

echo.
echo ============================================================
echo Build tamam.
echo   Paket klasoru : dist\%PACKAGE_STEM%\%APP_EXE%
echo   Kurulum dosyasi: dist\installer\VoxoraStudio-%APP_VERSION%-Setup.exe
echo ============================================================
echo.
echo Kurulum: kurulum dosyasini cift tiklayin. Program Files'a kurulur,
echo ayarlar ve ciktilar %%LOCALAPPDATA%%\VoxoraStudio altinda tutulur.
echo.
pause
