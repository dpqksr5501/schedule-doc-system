"""Fail-fast Windows release build, with an explicit resource allowlist."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys
import uuid
import zipfile
from app_info import VERSION, ASSET_NAME, PUBLIC_EXE_NAME, PUBLIC_ZIP_NAME
from branding import ASSET_FILES
from launch_registry import PROTOCOL, LAUNCHER_NAME

ROOT = Path(__file__).resolve().parent


def main():
    if os.name != 'nt':
        raise SystemExit('Windows에서 배포 파일을 빌드해 주세요.')
    subprocess.run([sys.executable, '-X', 'utf8', str(ROOT / 'run_tests.py')], cwd=ROOT, check=True)
    # A fresh work directory prevents cache/file-lock collisions between builds.
    work = ROOT / 'build' / ('package-' + uuid.uuid4().hex[:12])
    # Build a separate, version-independent launcher, then embed it in the installer.
    subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--onefile', '--noconsole',
        '--workpath', str(work / 'launcher'), '--specpath', str(ROOT / 'build'), '--noupx',
        '--name', LAUNCHER_NAME[:-4], '--icon', str(ROOT / 'assets' / 'app_icon.ico'),
        str(ROOT / 'launcher_main.py')], cwd=ROOT, check=True)
    launcher = ROOT / 'dist' / LAUNCHER_NAME
    launcher_manifest = ROOT / 'build' / 'launcher-manifest.json'
    launcher_manifest.write_text(json.dumps(dict(protocol=PROTOCOL,
        sha256=hashlib.sha256(launcher.read_bytes()).hexdigest())), 'utf-8')
    args = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--onefile', '--noconsole',
            '--workpath', str(work), '--specpath', str(ROOT / 'build'),
            '--noupx', '--name', PUBLIC_EXE_NAME[:-4], '--icon', str(ROOT / 'assets' / 'app_icon.ico'),
            '--hidden-import', 'win32com.client', '--hidden-import', 'win32com.shell.shell',
            '--hidden-import', 'win32timezone', '--hidden-import', 'pythoncom']
    args += ['--add-data', f'{launcher}{os.pathsep}assets/launcher',
             '--add-data', f'{launcher_manifest}{os.pathsep}assets/launcher']
    for name in ['index.html', 'style.css', 'document.css', 'app.js', 'schedule-core.js', '사용설명서.txt', '처음사용_5분안내.html',
                 'assets/template.hwpx', 'assets/manual.html', 'assets/app_icon.ico',
                 *ASSET_FILES]:
        source = ROOT / name
        args += ['--add-data', f'{source}{os.pathsep}{Path(name).parent}']
    args.append(str(ROOT / 'main.py'))
    subprocess.run(args, cwd=ROOT, check=True)
    executable = ROOT / 'dist' / PUBLIC_EXE_NAME
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
    # Existing apps request the English asset; end users receive the Korean file.
    compatibility_asset = ROOT / 'dist' / ASSET_NAME
    shutil.copyfile(executable, compatibility_asset)
    digest = hashlib.sha256(executable.read_bytes()).hexdigest()
    (destination / 'SHA256SUMS.txt').write_text(
        f'{digest}  {PUBLIC_EXE_NAME}\n{digest}  {ASSET_NAME}\n', encoding='utf-8')
    (destination / 'release-manifest.json').write_text(json.dumps(
        {'version': VERSION, 'asset': PUBLIC_EXE_NAME, 'compatibilityAsset': ASSET_NAME,
         'zip': PUBLIC_ZIP_NAME, 'sha256': digest, 'size': executable.stat().st_size},
        ensure_ascii=False, indent=2), encoding='utf-8')
    notes_source = ROOT / 'docs' / 'releases' / f'v{VERSION}.txt'
    notes = notes_source.read_text(encoding='utf-8') if notes_source.is_file() else (
        f'군수실 일정 관리 v{VERSION}\n\n'
        f'처음 사용하시는 분은 {PUBLIC_ZIP_NAME}을 내려받아 압축을 풀고 {PUBLIC_EXE_NAME}를 실행해 주세요.\n'
        '기존 사용자는 프로그램의 [백업 · 복원 · 업데이트]에서 [새 버전 확인]을 이용할 수 있습니다.\n'
        '업데이트 전에 [지금 백업하기]로 일정을 보관해 주세요.\n'
        'HWP 저장에는 HWPX를 열 수 있는 Windows용 한글이 필요합니다.\n')
    (destination / 'RELEASE_NOTES.txt').write_text(notes, encoding='utf-8')
    with zipfile.ZipFile(destination / PUBLIC_ZIP_NAME, 'w', zipfile.ZIP_DEFLATED) as package:
        package.write(executable, PUBLIC_EXE_NAME)
        package.write(ROOT / '사용설명서.txt', '사용설명서.txt')
        package.write(ROOT / '처음사용_5분안내.html', '처음사용_5분안내.html')
    print(f'배포 준비 완료: {executable}\nSHA256: {digest}')


if __name__ == '__main__':
    main()
