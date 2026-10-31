@echo off
REM Voxora Studio build - produce the .exe + setup file
REM Output: dist\VoxoraStudio-X.Y.Z\VoxoraStudio.exe  (fixed EXE name)
REM        dist\installer\VoxoraStudio-X.Y.Z-Setup.exe
REM
REM Why the EXE name carries no version: setup writes to a fixed folder ({autopf}\VoxoraStudio),
REM shortcuts point at VoxoraStudio.exe.'yi gosterir. Surumlu EXE adi her surumde
REM A versioned EXE name would break shortcuts and the update path on every release.

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
REM Foreign DLLs from an agent/tool PATH must not leak into the package (can break Qt startup).
set "PATH=%SystemRoot%\System32;%SystemRoot%;%SystemRoot%\System32\Wbem;%SystemRoot%\System32\WindowsPowerShell\v1.0;%CD%\.venv\Scripts"
set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"

if not exist "%PYEXE%" (
    echo [ERROR] Virtualenv not found. Run setup.bat first.
    pause
    exit /b 1
)

echo ============================================================
echo Voxora Studio .exe + setup build  (v%APP_VERSION%)
echo ============================================================
echo.

echo [1/6] Verifying required imports...
REM EMA-ONNX-only build: torch/chatterbox/torchaudio NEVER ENTER the package.
REM Downloadable engines (.vxp) bring their own libraries.
"%PYEXE%" -c "import PyQt6, sounddevice, soundfile, pydub, send2trash, numpy, onnxruntime, PyInstaller, normalizer_tr; print('[OK] All imports fine (no torch, EMA ONNX)')"
if errorlevel 1 (
    echo [ERROR] Import check failed. Run setup.bat first.
    pause
    exit /b 1
)

echo.
echo [2/6] Starting the PyInstaller build...
echo NOTE: this takes ~10-20 minutes.
echo.

REM Language catalogue is a single static module now; no extra hidden imports needed.

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
    echo [ERROR] Build failed. Check the error message above.
    pause
    exit /b 1
)

"%PYEXE%" scripts\verify_build_sources.py "build_temp\%PACKAGE_STEM%\VoxoraStudio\COLLECT-00.toc"
if errorlevel 1 exit /b 1

if not exist "dist\VoxoraStudio\%APP_EXE%" (
    echo [ERROR] Expected EXE missing: dist\VoxoraStudio\%APP_EXE%
    pause
    exit /b 1
)

echo.
echo [3/6] Versioning the package folder...
REM `move /y` can report "Access denied" on a folder target (Defender scan);
REM Python shutil.move does the same job reliably.
REM NOTE: when the target folder exists, shutil.move opens it INSIDE
REM (dist\X\VoxoraStudio\...). So the target is deleted FIRST, then moved.
"%PYEXE%" -c "import shutil;from pathlib import Path;src=Path(r'dist\VoxoraStudio');dst=Path(r'dist\%PACKAGE_STEM%');shutil.rmtree(dst, ignore_errors=True);assert not dst.exists(), 'target not deleted: '+str(dst);shutil.move(str(src), str(dst));print('package:', dst)" 
if errorlevel 1 (
    echo [ERROR] dist\VoxoraStudio -^> dist\%PACKAGE_STEM% move failed.
    pause
    exit /b 1
)

REM No user data leaks into the package (state/logs/outputs no longer live in the program folder).
if exist "dist\%PACKAGE_STEM%\_internal\state" rmdir /s /q "dist\%PACKAGE_STEM%\_internal\state"
if exist "dist\%PACKAGE_STEM%\_internal\logs" rmdir /s /q "dist\%PACKAGE_STEM%\_internal\logs"
if exist "dist\%PACKAGE_STEM%\_internal\outputs" rmdir /s /q "dist\%PACKAGE_STEM%\_internal\outputs"

echo.
echo [4/6] Compiling the setup file (Inno Setup)...
if not exist "%ISCC%" (
    echo [ERROR] Inno Setup not found. Install: winget install JRSoftware.InnoSetup
    pause
    exit /b 1
)
if not exist "dist\installer" mkdir "dist\installer"
"%ISCC%" /Qp "installer\VoxoraStudio.iss" /DAppVersion=%APP_VERSION% /DSourceDir="%CD%\dist\%PACKAGE_STEM%"
if errorlevel 1 (
    echo [ERROR] Setup file failed to compile.
    pause
    exit /b 1
)

echo.
echo [5/6] Checksum and size...
"%PYEXE%" -c "import hashlib,pathlib; p=pathlib.Path(r'dist\installer\VoxoraStudio-%APP_VERSION%-Setup.exe'); h=hashlib.sha256(p.read_bytes()).hexdigest(); print(f'{p}  {p.stat().st_size/1048576:.1f} MB'); print('SHA256', h)"

echo.
echo [6/6] Delta update package (diff against the previous version, if any)...
"%PYEXE%" scripts\make_delta_candidates.py "%APP_VERSION%"

echo.
echo ============================================================
echo Build done.
echo   Package folder : dist\%PACKAGE_STEM%\%APP_EXE%
echo   Setup file: dist\installer\VoxoraStudio-%APP_VERSION%-Setup.exe
echo ============================================================
echo.
echo Install: double-click the setup file. Program Files'a kurulur,
echo settings and outputs stay under %%LOCALAPPDATA%%\VoxoraStudio.
echo.
pause
