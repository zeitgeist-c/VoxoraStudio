@echo off
REM txttoTTS launcher
REM Eksik paket varsa veya NVIDIA PC'de CUDA aktif degilse kurulumu otomatik tamamlar.

cd /d "%~dp0"
set "PROJECT_ROOT=%CD%"
set "PYTHONPATH=%PROJECT_ROOT%"

set "VENV=.venv"
set "PYEXE=%VENV%\Scripts\python.exe"

if not exist "%PYEXE%" (
    echo [BILGI] Sanal ortam bulunamadi. Kurulum baslatiliyor...
    call setup.bat
    if errorlevel 1 exit /b 1
)

"%PYEXE%" -c "import numpy, torch, torchaudio, PyQt6, sounddevice, soundfile, pydub, send2trash" >nul 2>&1
if errorlevel 1 (
    echo [BILGI] Eksik paket bulundu. Kurulum/guncelleme baslatiliyor...
    call setup.bat
    if errorlevel 1 exit /b 1
)

nvidia-smi -L >nul 2>&1
if not errorlevel 1 (
    "%PYEXE%" -c "import torch, sys; cuda=torch.cuda.is_available(); gpu=torch.cuda.get_device_name(0) if cuda else '?'; print(f'cuda={cuda} gpu={gpu}'); sys.exit(0 if cuda else 1)"
    if errorlevel 1 (
        echo [UYARI] NVIDIA GPU bulundu ama PyTorch CUDA aktif degil. GPU kurulumu deneniyor...
        call setup.bat
        if errorlevel 1 exit /b 1
    ) else (
        echo [OK] PyTorch CUDA aktif
    )
)

"%PYEXE%" app.py
if errorlevel 1 (
    echo.
    echo [HATA] Program beklenmeyen bir hata ile kapandi.
    pause
)
