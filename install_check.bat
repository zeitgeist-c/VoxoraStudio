@echo off
REM txttoTTS kurulum kontrolu - paketler, GPU/DirectML ve ffmpeg durumu

cd /d "%~dp0"

set "PYEXE=.venv\Scripts\python.exe"

echo ============================================================
echo txttoTTS kurulum kontrolu
echo ============================================================
echo.

if not exist "%PYEXE%" (
    echo [HATA] Sanal ortam bulunamadi.
    echo Once setup.bat calistir.
    pause
    exit /b 1
)

"%PYEXE%" smoke_test.py --no-units
if errorlevel 1 (
    echo.
    echo [HATA] Kurulum kontrolu basarisiz.
    echo Duzeltmek icin setup.bat yeniden calistirilabilir.
    pause
    exit /b 1
)

echo.
echo [OK] Kurulum kontrolu basarili.
echo Programi baslatmak icin run.bat calistir.
pause
