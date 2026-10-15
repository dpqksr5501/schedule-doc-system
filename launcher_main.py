"""Fixed launcher: select a verified app; own the update handoff and fallback."""
from pathlib import Path
import ctypes
import json
import os
import subprocess
import sys
from app_paths import AppPaths
from launch_registry import launch_choices, read_record, validate_record, PROTOCOL
from native_workers import independent_environment
from storage import atomic_bytes


def run(paths, token=None, probe=None):
    if token:
        # Use the active APP as the owner, never this launcher's executable path.
        previous = validate_record(paths, read_record(paths))[1]
        from updater import monitor_update
        return monitor_update(paths, token, expected_previous=previous, probe=probe)
    choices = launch_choices(paths)
    for index, (version, target) in enumerate(choices):
        try:
            arguments = [str(target)] + (['--upgrade-smoke-test', str(probe)] if probe else [])
            child = subprocess.Popen(arguments, env=independent_environment(),
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        except OSError:
            if index + 1 == len(choices):
                raise
            continue
        if index or version != read_record(paths)['version']:
            atomic_bytes(paths.updates / 'last_failure.txt',
                         '최신 프로그램 파일을 실행하지 못해 검증된 이전 버전을 열었습니다. 새 버전 확인으로 복구해 주세요.'.encode('utf-8'))
        if probe:
            status = child.wait(timeout=90)
            atomic_bytes(Path(probe) / 'launcher-result.json', json.dumps(dict(
                success=status == 0, protocol=PROTOCOL, selectedVersion=version,
                executable=str(target), launcher=sys.executable)).encode('utf-8'))
            return status
        return 0


def main():
    update_probe = len(sys.argv) == 4 and sys.argv[1] == '--apply-update-probe'
    probe = Path(sys.argv[2]) if update_probe or len(sys.argv) == 3 and sys.argv[1] in ('--launch-probe', '--resolve-probe') else None
    paths = AppPaths.isolated(probe) if probe else AppPaths.current()
    token = sys.argv[3] if update_probe else sys.argv[2] if len(sys.argv) == 3 and sys.argv[1] == '--apply-update' else None
    if probe and sys.argv[1] == '--resolve-probe':
        selected = launch_choices(paths)[0]
        atomic_bytes(probe / 'launcher-result.json', json.dumps(dict(success=True,
            selectedVersion=selected[0], executable=str(selected[1]), protocol=PROTOCOL)).encode('utf-8'))
        return 0
    if len(sys.argv) != 1 and probe is None and token is None:
        raise ValueError('실행기 인수가 올바르지 않습니다.')
    return run(paths, token, probe)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as error:
        if (len(sys.argv) == 3 and sys.argv[1] in ('--launch-probe', '--resolve-probe')
                or len(sys.argv) == 4 and sys.argv[1] == '--apply-update-probe'):
            atomic_bytes(Path(sys.argv[2]) / 'launcher-result.json', json.dumps(
                dict(success=False, error=str(error))).encode('utf-8'))
        elif os.name == 'nt':
            ctypes.windll.user32.MessageBoxW(None, str(error), '군수실 일정 관리 · 실행기', 0x40)
        raise SystemExit(1)
