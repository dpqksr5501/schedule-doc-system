@echo off
chcp 65001 > nul
title 군수실 일정 통합 관리 시스템 - 단독 실행파일(.exe) 빌드
cd /d "%~dp0"

echo ========================================================
echo   [군수실 일정 통합 관리 시스템] .exe 빌드를 시작합니다.
echo ========================================================
echo.

pyinstaller --noconsole --onefile ^
  --icon="assets/app_icon.ico" ^
  --name="군수실일정관리" ^
  --add-data "index.html;." ^
  --add-data "style.css;." ^
  --add-data "app.js;." ^
  --add-data "initial_data.js;." ^
  --add-data "assets;assets" ^
  main.py

echo.
echo ========================================================
echo   빌드가 완료되었습니다!
echo   생성된 파일: dist\군수실일정관리.exe
echo ========================================================
pause
