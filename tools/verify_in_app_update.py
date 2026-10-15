"""Run an old EXE's actual embedded update monitor against a real new EXE.

Only process arguments are redirected to an explicit isolated smoke-test root.
The legacy monitor's ready/poll/rollback algorithm is executed unchanged.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import types

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PyInstaller.archive.readers import CArchiveReader
from app_info import VERSION, ASSET_NAME, INSTALLED_EXE_NAME
from app_paths import AppPaths
from installation import active_installation, desktop_shortcut, shortcut_target, verified_launcher
from desktop_entries import write_shortcut, owned_shortcuts, known_files
from native_workers import independent_environment
from storage import atomic_bytes, atomic_copy
from schedule_domain import parse_snapshot


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(previous, current, root, scenario, entry_name=ASSET_NAME,
        shortcut_name='군수실 일정 관리.lnk', monitor='legacy'):
    previous, current, root = previous.resolve(), current.resolve(), root.resolve()
    root.mkdir(parents=True, exist_ok=False)
    paths = AppPaths.isolated(root)
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    subprocess.run([str(previous), '--smoke-test', str(root)], check=True, timeout=90,
                   env=independent_environment(), creationflags=flags)
    if Path(entry_name).name != entry_name or Path(shortcut_name).name != shortcut_name:
        raise ValueError('검사 파일 이름에 경로를 넣을 수 없습니다.')
    original_link = paths.desktop / '군수실 일정 관리.lnk'
    renamed_link = paths.desktop / shortcut_name
    if original_link != renamed_link:
        original_link.rename(renamed_link)
    old_record = (paths.installation / 'active.json').read_bytes()
    old_active = json.loads(old_record)
    desktop_entry = paths.desktop / entry_name
    atomic_copy(previous, desktop_entry)
    # The renamed shortcut may point to a renamed EXE, not the managed copy.
    write_shortcut(renamed_link, desktop_entry)
    duplicate_exe = paths.desktop / '또 다른 복사본.exe'
    atomic_copy(previous, duplicate_exe)
    write_shortcut(paths.desktop / '중복으로 만든 바로가기.lnk', duplicate_exe)
    unrelated = paths.desktop / '다른 프로그램.exe'
    unrelated.write_bytes(b'MZ-unrelated-application')
    write_shortcut(paths.desktop / '다른 프로그램.lnk', unrelated)
    unrelated_before = {str(p): digest(p) for p in (unrelated, paths.desktop / '다른 프로그램.lnk')}
    atomic_copy(paths.database, paths.database.with_suffix('.json.bak'))
    if scenario in ('fixture', 'corrupt'):
        content = (json.dumps({'test_event': '보은군민의날', 'timestamp': 20260920}, ensure_ascii=False).encode()
                   if scenario == 'fixture' else b'unknown corrupt user data')
        paths.database.write_bytes(content)
        paths.database.with_suffix('.json.bak').write_bytes(content)
    original_data = paths.database.read_bytes()
    document = paths.output / '사용자가 보관한 문서.txt'
    document.write_text('기존 문서 보존 검사', 'utf-8')
    atomic_copy(paths.database, paths.output / '데이터백업' / '기존 일정백업.json')
    preserved_data = {}
    if scenario == 'valid':
        history = paths.backups / ('snapshot-000000000001-' + 'b' * 32 + '.json')
        atomic_copy(paths.database, history)
        preserved_data = {str(p): digest(p) for p in (paths.database, paths.database.with_suffix('.json.bak'), history)}
    preserved = {str(path): digest(path) for path in paths.output.rglob('*') if path.is_file()
                 and path.name not in ('사용설명서.txt', '먼저_읽어주세요.html', '처음사용_5분안내.html')}
    token = 'a' * 32
    target = paths.installation / 'versions' / VERSION / (INSTALLED_EXE_NAME if monitor == 'fixed' else ASSET_NAME)
    atomic_copy(current, target)
    plan = dict(token=token, version=VERSION, target=str(target), previous=str(desktop_entry),
                size=target.stat().st_size, digest='sha256:' + digest(target))
    atomic_bytes(paths.updates / (token + '.json'), json.dumps(plan).encode())
    # Execute the exact code object shipped in the old executable, not a rewrite.
    archive = CArchiveReader(str(previous))
    pyz = archive.open_embedded_archive('PYZ.pyz')
    legacy = types.ModuleType('legacy_updater')
    exec(pyz.extract('updater'), legacy.__dict__)
    legacy.sys = types.SimpleNamespace(executable=str(desktop_entry))
    rollbacks, children = [], []
    def launch(arguments, **kwargs):
        if Path(arguments[0]).resolve() == target.resolve():
            child = subprocess.Popen([str(target), '--update-smoke-test', str(root), token], **kwargs)
            children.append(child)
            return child
        if Path(arguments[0]).resolve() == desktop_entry.resolve():
            rollbacks.append(arguments)
            return types.SimpleNamespace()
        raise AssertionError('Unexpected process launch: ' + repr(arguments))
    legacy.subprocess = types.SimpleNamespace(Popen=launch, CREATE_NO_WINDOW=flags)
    print(f'{monitor} monitor → {VERSION} ({scenario}, {entry_name}, {shortcut_name})', flush=True)
    if monitor == 'legacy':
        status = legacy.monitor_update(paths, token)
    else:
        # Exercise the new, actual frozen launcher's update handoff in isolation.
        archive = CArchiveReader(str(current))
        for name in ('GunsuLauncher.exe', 'launcher-manifest.json'):
            destination = paths.installation / 'launcher' / ('manifest.json' if name.endswith('.json') else name)
            key = next(k for k in archive.toc if k.replace('\\', '/') == 'assets/launcher/' + name)
            atomic_bytes(destination, archive.extract(key))
        old_active['sha256'] = digest(old_active['executable'])
        atomic_bytes(paths.installation / 'active.json', json.dumps(old_active).encode())
        old_record = (paths.installation / 'active.json').read_bytes()
        plan['previous'] = old_active['executable']
        atomic_bytes(paths.updates / (token + '.json'), json.dumps(plan).encode())
        process = subprocess.run([str(verified_launcher(paths)), '--apply-update-probe', str(root), token],
                                 timeout=110, env=independent_environment(), creationflags=flags)
        status = process.returncode
        if (root / 'monitor-rollback.json').exists():
            rollbacks.append(json.loads((root / 'monitor-rollback.json').read_text('utf-8')))
    for child in children:
        child.wait(timeout=90)
    if scenario == 'corrupt':
        assert status == 1 and len(rollbacks) == 1
        assert not (root / 'ui-smoke-result.json').exists(), 'Unusable new GUI must not open'
        assert (paths.installation / 'active.json').read_bytes() == old_record
        assert paths.database.read_bytes() == original_data
        assert desktop_entry.exists(), 'Failed update must preserve the old desktop entry'
        assert not (paths.updates / (token + '.ready')).exists()
    else:
        assert status == 0 and not rollbacks, 'Legacy monitor incorrectly rolled back the update'
        deadline = time.monotonic() + 90
        while not (root / 'ui-smoke-result.json').exists():
            if time.monotonic() >= deadline:
                raise TimeoutError('Update UI report timed out')
            time.sleep(.1)
        report = json.loads((root / 'ui-smoke-result.json').read_text('utf-8'))
        assert report['success'] and report['activationVerified'] and report['version'] == VERSION
        if scenario == 'valid':
            assert paths.database.read_bytes() == original_data, 'Existing data changed'
            assert report['snapshot'] == parse_snapshot(original_data.decode('utf-8-sig')), 'Loaded schedule or memo differs'
        else:
            assert any(p.read_bytes() == original_data for p in paths.backups.glob('legacy-self-test-*'))
        active = active_installation(paths)
        selected = desktop_shortcut(paths)
        assert selected.name == shortcut_name, 'The renamed label was not preserved'
        stable = verified_launcher(paths)
        assert shortcut_target(selected).samefile(stable)
        subprocess.run([str(current), '--migrate-smoke-test', str(root)], check=True, timeout=90,
                       env=independent_environment(), creationflags=flags)
        assert not desktop_entry.exists() and not duplicate_exe.exists(), 'Duplicate EXEs remain'
        assert any(digest(p) == digest(previous) for p in (paths.updates / 'desktop-entries').rglob('*.exe'))
        assert owned_shortcuts(paths, known_files(paths)) == [selected]
        launcher_hash = digest(stable)
        # Reopen through the actual fixed launcher, not a versioned app path.
        (root / 'ui-smoke-result.json').rename(root / 'update-ui-result.json')
        subprocess.run([str(stable), '--launch-probe', str(root)], check=True, timeout=100,
                       env=independent_environment(), creationflags=flags)
        deadline = time.monotonic() + 90
        while not (root / 'ui-smoke-result.json').exists():
            if time.monotonic() >= deadline:
                raise TimeoutError('Reopen result timed out')
            time.sleep(.2)
        reopened = json.loads((root / 'ui-smoke-result.json').read_text('utf-8'))
        assert reopened['success'] and reopened['installedLaunch'] and reopened['version'] == VERSION
        assert json.loads((root / 'launcher-result.json').read_text('utf-8'))['selectedVersion'] == VERSION
        # Rename the surviving shortcut again: the app must keep it without creating another icon.
        renamed_again = paths.desktop / '사용자가 다시 바꾼 이름.lnk'
        selected.rename(renamed_again)
        subprocess.run([str(stable), '--launch-probe', str(root)], check=True, timeout=100,
                       env=independent_environment(), creationflags=flags)
        assert desktop_shortcut(paths).name == renamed_again.name
        assert owned_shortcuts(paths, known_files(paths)) == [renamed_again]
        assert digest(stable) == launcher_hash, 'The fixed launcher was unnecessarily replaced'
        # A damaged active EXE must select the verified previous version.
        canonical = active_installation(paths)[1]
        atomic_bytes(canonical, b'damaged-current-executable')
        subprocess.run([str(stable), '--resolve-probe', str(root)], check=True, timeout=30,
                       env=independent_environment(), creationflags=flags)
        assert json.loads((root / 'launcher-result.json').read_text('utf-8'))['selectedVersion'] == old_active['version']
        (root / 'launcher-result.json').replace(root / 'launcher-fallback-result.json')
        atomic_copy(current, canonical)
        subprocess.run([str(stable), '--resolve-probe', str(root)], check=True, timeout=30,
                       env=independent_environment(), creationflags=flags)
        assert json.loads((root / 'launcher-result.json').read_text('utf-8'))['selectedVersion'] == VERSION
        if scenario == 'valid':
            assert paths.database.read_bytes() == original_data
    for filename, expected in preserved.items():
        assert digest(filename) == expected, 'Existing output document changed: ' + filename
    for filename, expected in {**preserved_data, **unrelated_before}.items():
        assert digest(filename) == expected, 'Original data, backup, or unrelated desktop file changed: ' + filename
    result = dict(success=True, scenario=scenario, version=VERSION, rollbackCount=len(rollbacks),
                  legacyExecutableSha256=digest(previous), newExecutableSha256=digest(current),
                  preservedDocuments=len(preserved), preservedDataFiles=len(preserved_data),
                  entryName=entry_name, shortcutName=shortcut_name, monitor=monitor,
                  testedReopen=scenario != 'corrupt')
    atomic_bytes(root / 'in-app-update-result.json', json.dumps(result, indent=2).encode())
    print(json.dumps(result, indent=2), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--previous-exe', type=Path, required=True)
    parser.add_argument('--current-exe', type=Path, required=True)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--scenario', choices=('valid', 'fixture', 'corrupt'), default='valid')
    parser.add_argument('--entry-name', default=ASSET_NAME)
    parser.add_argument('--shortcut-name', default='군수실 일정 관리.lnk')
    parser.add_argument('--monitor', choices=('legacy','fixed'), default='legacy')
    args = parser.parse_args()
    run(args.previous_exe, args.current_exe, args.root, args.scenario, args.entry_name, args.shortcut_name, args.monitor)
