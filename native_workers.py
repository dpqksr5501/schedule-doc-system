"""Short-lived native helpers; the GUI never waits indefinitely on Hancom COM."""
from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
from app_paths import resource_dir


def self_command(*arguments):
    if getattr(sys, 'frozen', False):
        return [sys.executable, *arguments]
    return [sys.executable, str(resource_dir() / 'main.py'), *arguments]


def independent_environment():
    return {**os.environ, 'PYINSTALLER_RESET_ENVIRONMENT': '1'}


def convert_bounded(hwpx_path, hwp_path, timeout=90):
    with tempfile.TemporaryDirectory(prefix='gunsu-convert-') as directory:
        result_path = Path(directory) / 'result.json'
        process = subprocess.Popen(self_command('--convert-hwp', str(hwpx_path), str(hwp_path), str(result_path)),
                                   env=independent_environment(),
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            # Terminate only our worker, never the user's existing Hwp.exe instance.
            process.kill()
            process.wait(timeout=10)
            return False, '한글 변환 대기 시간이 지났습니다. 파일 접근 승인창이 있었는지 확인해 주세요.'
        if not result_path.exists():
            return False, '한글 변환을 실행하지 못했습니다. 한글 설치 상태를 확인해 주세요.'
        try:
            result = json.loads(result_path.read_text(encoding='utf-8'))
            if type(result.get('success')) is not bool or not isinstance(result.get('message'), str):
                raise ValueError('invalid worker result')
            return result['success'], result['message']
        except (OSError, ValueError, TypeError):
            return False, '한글 변환 결과를 확인하지 못했습니다.'
