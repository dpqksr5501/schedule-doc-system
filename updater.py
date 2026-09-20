# -*- coding: utf-8 -*-
"""
보은군 군수실 일정 통합 관리 시스템 - 자동 업데이트 (Auto-Updater) 모듈
GitHub Releases 기반 원자적 자가 교체(In-Place Self Update) 엔진
Repository: https://github.com/dpqksr5501/schedule-doc-system
"""

import os
import sys
import json
import urllib.request
import subprocess
import tempfile
import time

CURRENT_VERSION = "1.0.0"
REPO_OWNER = "dpqksr5501"
REPO_NAME = "schedule-doc-system"
GITHUB_API_URL = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/releases/latest"

def get_current_version():
    return CURRENT_VERSION

def check_for_updates():
    """
    GitHub Releases API를 호출하여 최신 버전 및 .exe 다운로드 링크를 확인합니다.
    오프라인이거나 아직 릴리즈가 없는 경우에도 절대 오류 없이 안전하게 응답.
    """
    try:
        req = urllib.request.Request(
            GITHUB_API_URL,
            headers={
                'User-Agent': f'GunsuScheduleApp/{CURRENT_VERSION}',
                'Accept': 'application/vnd.github.v3+json'
            }
        )
        with urllib.request.urlopen(req, timeout=4) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            tag_name = data.get('tag_name', '').strip() # 예: "v1.0.1" 또는 "1.0.1"
            latest_version = tag_name.lstrip('v')
            release_notes = data.get('body', '새로운 기능 개선 및 안정성 향상이 포함되어 있습니다.')

            # 첨부된 .exe 파일의 다운로드 URL 탐색
            exe_download_url = None
            for asset in data.get('assets', []):
                name = asset.get('name', '')
                if name.endswith('.exe'):
                    exe_download_url = asset.get('browser_download_url')
                    break

            has_update = _is_newer_version(latest_version, CURRENT_VERSION)

            return {
                'success': True,
                'hasUpdate': has_update,
                'currentVersion': CURRENT_VERSION,
                'latestVersion': latest_version,
                'releaseNotes': release_notes,
                'downloadUrl': exe_download_url
            }
    except urllib.error.HTTPError as e:
        if e.code == 404:
            # 아직 GitHub에 Release가 등록되지 않은 초기 상태
            return {
                'success': True,
                'hasUpdate': False,
                'currentVersion': CURRENT_VERSION,
                'message': '현재 최신 버전(v1.0.0)을 사용하고 있습니다. (등록된 릴리즈 없음)'
            }
        return {
            'success': False,
            'hasUpdate': False,
            'currentVersion': CURRENT_VERSION,
            'message': f'서버 응답 오류 (코드: {e.code})'
        }
    except Exception as e:
        return {
            'success': False,
            'hasUpdate': False,
            'currentVersion': CURRENT_VERSION,
            'message': '네트워크 연결을 확인할 수 없습니다. (오프라인 모드)'
        }

def apply_update(download_url):
    """
    새로운 버전의 .exe 파일을 다운로드하여 현재 실행 중인 파일을
    윈도우 파일 잠금을 우회하여 안전하게 교체(Swap)하고 재실행합니다.
    """
    if not download_url:
        return {'success': False, 'message': '다운로드 URL이 제공되지 않았습니다.'}

    try:
        # 현재 실행 중인 파일 경로 파악
        if getattr(sys, 'frozen', False):
            current_exe = sys.executable
        else:
            current_exe = os.path.abspath(sys.argv[0])

        # 1. 임시 디렉토리에 새 .exe 다운로드
        temp_dir = tempfile.mkdtemp()
        temp_exe = os.path.join(temp_dir, "update_new.exe")

        req = urllib.request.Request(
            download_url,
            headers={'User-Agent': f'GunsuScheduleApp/{CURRENT_VERSION}'}
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            with open(temp_exe, 'wb') as f:
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    f.write(chunk)

        # 파일 크기 검증 (최소 5MB 이상 정상 exe 여부)
        if not os.path.exists(temp_exe) or os.path.getsize(temp_exe) < 1024 * 1024:
            return {'success': False, 'message': '다운로드된 파일이 손상되었거나 완전하지 않습니다.'}

        # 2. 윈도우 원자적 스와퍼(Atomic Swapper) 배치 스크립트 생성
        # 현재 프로그램이 종료되길 1~2초 대기 후, 파일 교체 및 새 프로그램 시작
        swap_bat = os.path.join(temp_dir, "swap_and_restart.bat")
        bat_script = f"""@echo off
chcp 65001 > nul
echo [군수실 시스템] 최신 버전으로 자동 패치 중입니다...
timeout /t 1 /nobreak > nul

:retry
move /y "{temp_exe}" "{current_exe}" > nul 2>&1
if %errorlevel% neq 0 (
    timeout /t 1 /nobreak > nul
    goto retry
)

echo [군수실 시스템] 패치 완료! 프로그램을 다시 시작합니다.
start "" "{current_exe}"
del "%~f0"
exit
"""
        with open(swap_bat, 'wb') as f:
            f.write(bat_script.encode('cp949'))

        # 3. 스와퍼 스크립트를 독립 프로세스로 실행하고 현재 프로그램 즉시 종료
        subprocess.Popen(
            f'cmd.exe /c "{swap_bat}"',
            shell=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )

        # 현재 프로세스 종료 스케줄 (JS 응답 후 즉시 종료되도록)
        def exit_soon():
            time.sleep(0.5)
            os._exit(0)

        import threading
        threading.Thread(target=exit_soon, daemon=True).start()

        return {'success': True, 'message': '새 버전을 다운로드했습니다. 1초 후 자동으로 재시작됩니다!'}

    except Exception as e:
        return {'success': False, 'message': f'업데이트 적용 중 오류가 발생했습니다: {str(e)}'}

def _is_newer_version(latest, current):
    """시맨틱 버전 비교 (예: 1.0.1 > 1.0.0)"""
    try:
        def parse_v(v):
            return [int(x) for x in v.lstrip('v').split('.') if x.isdigit()]
        return parse_v(latest) > parse_v(current)
    except Exception:
        return False
