@echo off
REM Builds dist\AURIX\AURIX.exe and dist\AURIX-Setup.zip  (run on Windows 10/11 inside the project folder)
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  python -m venv .venv
)
call .venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m pytest tests -q
if errorlevel 1 (
  echo Tests failed. Fix them before building.
  pause
  exit /b 1
)
pyinstaller --noconfirm --clean aurix.spec
if errorlevel 1 (
  echo Build failed.
  pause
  exit /b 1
)
powershell -NoProfile -Command "Compress-Archive -Path 'dist\AURIX\*' -DestinationPath 'dist\AURIX-Windows.zip' -Force"
echo.
echo Done:  dist\AURIX\AURIX.exe   and   dist\AURIX-Windows.zip
pause
