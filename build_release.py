"""Fail-fast Windows release build, with an explicit resource allowlist."""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys
import uuid
import zipfile
from app_info import VERSION, ASSET_NAME

ROOT = Path(__file__).resolve().parent


def main():
    if os.name != 'nt':
        raise SystemExit('Windows에서 배포 파일을 빌드해 주세요.')
    subprocess.run([sys.executable, '-X', 'utf8', str(ROOT / 'run_tests.py')], cwd=ROOT, check=True)
    # A fresh work directory prevents cache/file-lock collisions between builds.
    work = ROOT / 'build' / ('package-' + uuid.uuid4().hex[:12])
    args = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--onefile', '--noconsole',
            '--workpath', str(work), '--specpath', str(ROOT / 'build'),
            '--noupx', '--name', ASSET_NAME[:-4], '--icon', str(ROOT / 'assets' / 'app_icon.ico'),
            '--hidden-import', 'win32com.client', '--hidden-import', 'win32com.shell.shell',
            '--hidden-import', 'pythoncom']
    for name in ['index.html', 'style.css', 'document.css', 'app.js', 'schedule-core.js', '사용설명서.txt', '처음사용_5분안내.html',
                 'assets/template.hwpx', 'assets/manual.html', 'assets/app_icon.ico',
                 'assets/boeun-symbol.png', 'assets/boeun-slogan.png']:
        source = ROOT / name
        args += ['--add-data', f'{source}{os.pathsep}{Path(name).parent}']
    args.append(str(ROOT / 'main.py'))
    subprocess.run(args, cwd=ROOT, check=True)
    executable = ROOT / 'dist' / ASSET_NAME
    # 실패 후에도 검사 진행 위치와 오류를 수집할 수 있도록 기록을 보존합니다.
    directory = ROOT / 'build' / ('bundle-probe-' + uuid.uuid4().hex[:12])
    directory.mkdir(parents=True)
    try:
        subprocess.run([str(executable), '--smoke-test', str(directory)], timeout=90, check=True)
        result = json.loads((directory / 'smoke-result.json').read_text('utf-8'))
        if result.get('success') is not True:
            raise RuntimeError('실행 파일 자체 점검 실패')
    finally:
        for name in ('smoke-progress.json', 'smoke-result.json'):
            report = directory / name
            if report.exists():
                print(report.read_text('utf-8'), flush=True)
    destination = ROOT / 'release'
    destination.mkdir(exist_ok=True)
    digest = hashlib.sha256(executable.read_bytes()).hexdigest()
    (destination / 'SHA256SUMS.txt').write_text(f'{digest}  {ASSET_NAME}\n', encoding='utf-8')
    (destination / 'release-manifest.json').write_text(json.dumps(
        {'version': VERSION, 'asset': ASSET_NAME, 'sha256': digest, 'size': executable.stat().st_size}, indent=2), encoding='utf-8')
    notes_source = ROOT / 'docs' / 'releases' / f'v{VERSION}.txt'
    notes = notes_source.read_text(encoding='utf-8') if notes_source.is_file() else (
        f'군수실 일정 관리 v{VERSION}\n\n'
        f'처음 사용하시는 분은 GunsuSchedule-v{VERSION}-Windows.zip을 내려받아 압축을 풀고 실행해 주세요.\n'
        '기존 사용자는 프로그램의 [백업 · 복원 · 업데이트]에서 [새 버전 확인]을 이용할 수 있습니다.\n'
        '업데이트 전에 [지금 백업하기]로 일정을 보관해 주세요.\n'
        'HWP 저장에는 HWPX를 열 수 있는 Windows용 한글이 필요합니다.\n')
    (destination / 'RELEASE_NOTES.txt').write_text(notes, encoding='utf-8')
    with zipfile.ZipFile(destination / f'GunsuSchedule-v{VERSION}-Windows.zip', 'w', zipfile.ZIP_DEFLATED) as package:
        package.write(executable, ASSET_NAME)
        package.write(ROOT / '사용설명서.txt', '사용설명서.txt')
        package.write(ROOT / '처음사용_5분안내.html', '처음사용_5분안내.html')
    print(f'배포 준비 완료: {executable}\nSHA256: {digest}')


if __name__ == '__main__':
    main()
