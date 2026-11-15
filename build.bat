@echo off
setlocal
cd /d "%~dp0"

python -m pip install -r requirements.txt -r requirements-build.txt
if errorlevel 1 exit /b 1

python -m PyInstaller --noconfirm --clean SimpleImageAnnotator.spec
if errorlevel 1 exit /b 1

echo.
echo Built dist\SimpleImageAnnotator.exe
endlocal
