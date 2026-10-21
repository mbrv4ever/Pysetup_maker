@echo off
REM ==========================================================
REM PySetup_Maker - Nuitka --onefile (1 exe)
REM ==========================================================
setlocal
cd /d "%~dp0"

if not exist "pysetup_maker.py" (
    echo FOUT: pysetup_maker.py niet gevonden.
    pause
    exit /b 1
)

if not exist "build_output" mkdir build_output

set ICON_ARG=
if exist "logo.ico" set ICON_ARG=--windows-icon-from-ico=logo.ico

python -m nuitka ^
    --standalone ^
    --onefile ^
    --enable-plugin=pyside6 ^
    --windows-console-mode=disable ^
    --include-package=core ^
    %ICON_ARG% ^
    --product-name="PySetup Maker" ^
    --product-version=0.2.0 ^
    --file-version=0.2.0 ^
    --file-description="PySetup Maker" ^
    --output-dir=build_output ^
    --output-filename=PySetup_Maker.exe ^
    --assume-yes-for-downloads ^
    --remove-output ^
    pysetup_maker.py

if errorlevel 1 (
    echo.
    echo FOUT: Nuitka build mislukt.
    pause
    exit /b 1
)

echo.
echo === Build klaar ===
echo Output: build_output\PySetup_Maker.exe
echo.
pause
endlocal
