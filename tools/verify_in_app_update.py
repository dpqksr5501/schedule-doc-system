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
from app_info import VERSION, ASSET_NAME
from app_paths import AppPaths
from installation import active_installation, archive_legacy_desktop_entry, shortcut_target
from native_workers import independent_environment
from storage import atomic_bytes, atomic_copy


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(previous, current, root, scenario):
    previous, current, root = previous.resolve(), current.resolve(), root.resolve()
    root.mkdir(parents=True, exist_ok=False)
    paths = AppPaths.isolated(root)
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    subprocess.run([str(previous), '--smoke-test', str(root)], check=True, timeout=90,
                   env=independent_environment(), creationflags=flags)
    old_record = (paths.installation / 'active.json').read_bytes()
    desktop_entry = paths.desktop / ASSET_NAME
    atomic_copy(previous, desktop_entry)
    atomic_copy(paths.database, paths.database.with_suffix('.json.bak'))
    if scenario in ('fixture', 'corrupt'):
        content = (json.dumps({'test_event': '보은군민의날', 'timestamp': 20260920}, ensure_ascii=False).encode()
                   if scenario == 'fixture' else b'unknown corrupt user data')
        paths.database.write_bytes(content)
        paths.database.with_suffix('.json.bak').write_bytes(content)
    original_data = paths.database.read_bytes()
    preserved = {str(path): digest(path) for path in paths.output.rglob('*') if path.is_file()
                 and path.name not in ('사용설명서.txt', '먼저_읽어주세요.html', '처음사용_5분안내.html')}
    token = 'a' * 32
    target = paths.installation / 'versions' / VERSION / ASSET_NAME
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
    print(f'Legacy monitor → {VERSION} ({scenario})', flush=True)
    status = legacy.monitor_update(paths, token)
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
        report = json.loads((root / 'ui-smoke-result.json').read_text('utf-8'))
        assert report['success'] and report['activationVerified'] and report['version'] == VERSION
        if scenario == 'valid':
            assert paths.database.read_bytes() == original_data, 'Existing data changed'
        else:
            assert any(p.read_bytes() == original_data for p in paths.backups.glob('legacy-self-test-*'))
        import pythoncom
        pythoncom.CoInitialize()
        try:
            active = active_installation(paths)
            assert shortcut_target(paths.desktop / '군수실 일정 관리.lnk').samefile(active[1])
        finally:
            pythoncom.CoUninitialize()
        assert archive_legacy_desktop_entry(paths), 'Duplicate Desktop EXE was not archived'
        assert not desktop_entry.exists(), 'Only the Korean shortcut should remain'
        assert any(digest(p) == digest(previous) for p in (paths.updates / 'desktop-entries').glob('*.exe'))
        pythoncom.CoInitialize()
        try:
            reopen = shortcut_target(paths.desktop / '군수실 일정 관리.lnk')
        finally:
            pythoncom.CoUninitialize()
        # Reopen the remaining Korean shortcut's verified target.
        (root / 'ui-smoke-result.json').rename(root / 'update-ui-result.json')
        subprocess.run([str(reopen), '--upgrade-smoke-test', str(root)], check=True, timeout=90,
                       env=independent_environment(), creationflags=flags)
        deadline = time.monotonic() + 90
        while not (root / 'ui-smoke-result.json').exists():
            if time.monotonic() >= deadline:
                raise TimeoutError('Reopen result timed out')
            time.sleep(.2)
        reopened = json.loads((root / 'ui-smoke-result.json').read_text('utf-8'))
        assert reopened['success'] and reopened['installedLaunch'] and reopened['version'] == VERSION
        if scenario == 'valid':
            assert paths.database.read_bytes() == original_data
    for filename, expected in preserved.items():
        assert digest(filename) == expected, 'Existing output document changed: ' + filename
    result = dict(success=True, scenario=scenario, version=VERSION, rollbackCount=len(rollbacks),
                  legacyExecutableSha256=digest(previous), newExecutableSha256=digest(current),
                  preservedDocuments=len(preserved), testedReopen=scenario != 'corrupt')
    atomic_bytes(root / 'in-app-update-result.json', json.dumps(result, indent=2).encode())
    print(json.dumps(result, indent=2), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--previous-exe', type=Path, required=True)
    parser.add_argument('--current-exe', type=Path, required=True)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--scenario', choices=('valid', 'fixture', 'corrupt'), default='valid')
    args = parser.parse_args()
    run(args.previous_exe, args.current_exe, args.root, args.scenario)
