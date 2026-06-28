@echo off
REM txttoTTS setup - Python 3.11 venv + akilli GPU/CPU kurulumu

cd /d "%~dp0"

echo ============================================================
echo txttoTTS kurulum
echo ============================================================
echo.

echo [1/5] Python 3.11 kontrol...
py -3.11 --version
if errorlevel 1 (
    echo [HATA] Python 3.11 bulunamadi.
    echo Kurulum:
    echo winget install Python.Python.3.11 --accept-package-agreements --accept-source-agreements
    pause
    exit /b 1
)

echo.
echo [2/5] Internet kontrol...
py -3.11 -c "import socket; s=socket.create_connection(('pypi.org',443),8); s.close(); print('[OK] Internet erisimi var.')" 
if errorlevel 1 (
    echo [HATA] Internet baglantisi dogrulanamadi.
    echo Bu kurulum paketleri indirmek icin internet ister.
    pause
    exit /b 1
)

echo.
echo [3/5] Donanim kontrol...
py -3.11 -c "from scripts.gpu_detect import has_nvidia_gpu, has_amd_gpu, has_directml_capable_gpu; n=has_nvidia_gpu(); a=has_amd_gpu(); d=has_directml_capable_gpu(); print('[BILGI] NVIDIA GPU:', 'var' if n else 'yok'); print('[BILGI] AMD/Intel/DirectML adayi GPU:', 'var' if a else 'yok'); print('[BILGI] Kurulum hedefi:', 'cuda' if n else ('directml' if d else 'cpu'))"
if errorlevel 1 (
    echo [UYARI] Donanim kontrolu tamamlanamadi. Kurulum CPU fallback ile devam edebilir.
)

echo.
echo [4/5] Sanal ortam hazirlaniyor...
if not exist ".venv\Scripts\python.exe" (
    py -3.11 -m venv .venv
    if errorlevel 1 (
        echo [HATA] Sanal ortam olusturulamadi.
        pause
        exit /b 1
    )
)

echo.
echo [5/5] Paketler kuruluyor ve dogrulaniyor...
".venv\Scripts\python.exe" scripts\setup_env.py
if errorlevel 1 (
    echo [HATA] Kurulum basarisiz.
    pause
    exit /b 1
)

echo.
ffmpeg -version >nul 2>&1
if errorlevel 1 (
    echo [UYARI] ffmpeg bulunamadi. MP3 export calismayabilir; WAV calisir.
    echo Kurulum:
    echo winget install Gyan.FFmpeg --accept-package-agreements --accept-source-agreements
) else (
    echo [OK] ffmpeg bulundu. MP3 export hazir.
)

echo.
echo Kurulum tamam.
echo Kontrol icin: install_check.bat
echo Calistirma: run.bat
pause
