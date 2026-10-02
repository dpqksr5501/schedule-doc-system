@echo off
chcp 65001 > nul
cd /d "%~dp0"
if exist "dist\GunsuSchedule.exe" (
  start "" "dist\GunsuSchedule.exe"
  exit /b
)
echo 개발용 실행입니다. 일반 사용자는 GitHub 배포의 GunsuSchedule.exe를 사용해 주세요.
if exist ".venv-build\Scripts\python.exe" (
  ".venv-build\Scripts\python.exe" main.py
) else (
  py -3.12 main.py
)
if errorlevel 1 (
  echo 실행 실패. 사용설명서와 위 오류를 확인해 주세요.
  pause
)
