@echo off
chcp 65001 > nul
cd /d "%~dp0"
if exist ".venv-build\Scripts\python.exe" (
  ".venv-build\Scripts\python.exe" -X utf8 build_release.py
) else (
  py -3.12 -X utf8 build_release.py
)
if errorlevel 1 (
  echo.
  echo 빌드 실패. 위 오류를 확인해 주세요. 배포 파일을 사용하지 마세요.
  pause
  exit /b 1
)
echo.
echo 완성 파일: dist\GunsuSchedule.exe
echo 배포 묶음: release\GunsuSchedule-v2.0.0-Windows.zip
pause
