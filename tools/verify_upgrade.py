"""Verify real previous/new Windows EXEs in an explicit, isolated test root.

Never use the real APPDATA or desktop. Requires a prior release EXE locally.
The old EXE creates the schedules, backups, documents and desktop shortcut;
the new EXE must preserve them and switch only the installed shortcut.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app_info import VERSION, INSTALLED_EXE_NAME
from app_paths import AppPaths
from storage import atomic_bytes
from installation import shortcut_target
from schedule_domain import parse_snapshot
from native_workers import independent_environment


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(previous, current, root):
    previous, current, root = previous.resolve(), current.resolve(), root.resolve()
    if previous == current or not previous.is_file() or not current.is_file():
        raise ValueError('서로 다른 이전/새 실행 파일을 지정해 주세요.')
    root.mkdir(parents=True, exist_ok=False)
    paths = AppPaths.isolated(root)
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    def execute(executable, mode):
        subprocess.run([str(executable), mode, str(root)], check=True, timeout=90,
                       env=independent_environment(), creationflags=flags)
    print('이전 EXE로 일정·문서·설치·바로가기 준비', flush=True)
    execute(previous, '--smoke-test')
    old_install = json.loads((paths.installation / 'active.json').read_text('utf-8'))
    previous_version = old_install['version']
    if previous_version == VERSION:
        raise ValueError('이전 버전 EXE를 지정해 주세요.')
    execute(previous, '--ui-smoke-test')
    report_path = root / 'ui-smoke-result.json'
    old_ui = json.loads(report_path.read_text('utf-8'))
    if not old_ui['success']:
        raise AssertionError('이전 버전 WebView2 검사 실패')
    report_path.rename(root / 'previous-ui-result.json')
    snapshot_bytes = paths.database.read_bytes()
    snapshot = parse_snapshot(snapshot_bytes.decode('utf-8-sig'))
    if not snapshot['events'] or not any(e.get('notes') for e in snapshot['events']):
        raise AssertionError('일정과 업무 메모가 있는 이전 버전 자료가 필요합니다.')
    document = paths.output / '사용자가_보관한_추가문서.txt'
    document.write_bytes('기존 문서 보존 확인용 견본'.encode('utf-8'))
    backup = paths.output / '데이터백업' / '기존_전체일정백업.json'
    backup.write_bytes(snapshot_bytes)
    documents = [p for p in paths.output.rglob('*') if p.is_file() and p.name not in
                 ('먼저_읽어주세요.html', '사용설명서.txt', '처음사용_5분안내.html')]
    automatic_backups = [p for p in paths.backups.rglob('*') if p.is_file()]
    if not automatic_backups:
        raise AssertionError('이전 버전 자동 백업이 없습니다.')
    preserved = [paths.database, paths.database.with_suffix('.json.bak'),
                 Path(old_install['executable']), *documents, *automatic_backups]
    before = {str(p): digest(p) for p in preserved}
    import pythoncom
    pythoncom.CoInitialize()
    try:
        old_target = shortcut_target(paths.desktop / '군수실 일정 관리.lnk')
        if not old_target.samefile(old_install['executable']):
            raise AssertionError('이전 버전 바로가기가 올바르지 않습니다.')
    finally:
        pythoncom.CoUninitialize()
    print(f'{previous_version} → {VERSION} 실제 설치·재실행·데이터 조회', flush=True)
    execute(current, '--upgrade-smoke-test')
    deadline = time.monotonic() + 90
    while not report_path.exists():
        if time.monotonic() >= deadline:
            raise TimeoutError('새 버전 시작 결과를 확인하지 못했습니다.')
        time.sleep(.2)
    result = json.loads(report_path.read_text('utf-8'))
    if not result['success'] or not result.get('installedLaunch') or result.get('version') != VERSION:
        raise AssertionError('새 버전 실행 또는 바로가기 전환이 실패했습니다.')
    if result.get('snapshot') != snapshot:
        raise AssertionError('새 버전에서 읽은 일정·메모·설정·휴지통이 이전 자료와 다릅니다.')
    for filename, expected in before.items():
        if digest(Path(filename)) != expected:
            raise AssertionError('기존 파일이 변경되었습니다: ' + filename)
    active = json.loads((paths.installation / 'active.json').read_text('utf-8'))
    if active['version'] != VERSION or Path(active['executable']).name != INSTALLED_EXE_NAME:
        raise AssertionError('활성 버전이나 한글 실행 파일명이 올바르지 않습니다.')
    report = dict(success=True, previousVersion=previous_version, version=VERSION,
                  schedules=len(snapshot['events']), documents=len(documents),
                  automaticBackups=len(automatic_backups), preservedFiles=len(before),
                  allPreservedHashes=before, shortcutBefore=str(old_target), shortcutAfter=active['executable'],
                  newExecutableSha256=digest(current))
    atomic_bytes(root / 'upgrade-result.json', json.dumps(report, ensure_ascii=False, indent=2).encode('utf-8'))
    print(json.dumps({k:v for k,v in report.items() if k != 'allPreservedHashes'}, ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--previous-exe', type=Path, required=True)
    parser.add_argument('--current-exe', type=Path, required=True)
    parser.add_argument('--root', type=Path, required=True)
    args = parser.parse_args()
    run(args.previous_exe, args.current_exe, args.root)
