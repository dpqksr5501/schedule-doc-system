"""Versioned app installation, fixed launcher, and identity-based desktop migration."""
from pathlib import Path
import json
import logging
import os
import re
import sys
import uuid
from app_info import ASSET_NAME, INSTALLED_EXE_NAME, VERSION
from app_paths import resource_dir
from storage import atomic_bytes, atomic_copy, atomic_replace
from launch_registry import (PROTOCOL, launcher_path, digest as _digest, version as _version,
                             read_record, read_records, validate_record)
import desktop_entries


def executable_for(paths, version=VERSION):
    return paths.installation / 'versions' / version / INSTALLED_EXE_NAME


def active_installation(paths):
    if not any((paths.installation / name).exists() for name in ('active.json', 'active.json.bak')):
        return None
    try:
        for record in read_records(paths):
            try:
                return validate_record(paths, record, require_digest=False)
            except (OSError, ValueError, KeyError, TypeError):
                continue
        raise ValueError('설치 기록을 검증하지 못했습니다.')
    except (OSError, ValueError, KeyError, TypeError):
        logging.warning('Active installation record could not be validated', exc_info=True)
        return None


def launcher_resource():
    root = resource_dir() / 'assets' / 'launcher'
    return root / 'GunsuLauncher.exe', json.loads((root / 'launcher-manifest.json').read_text('utf-8'))


def verified_launcher(paths):
    target = launcher_path(paths)
    record = json.loads(target.with_name('manifest.json').read_text('utf-8'))
    if type(record.get('protocol')) is not int or record['protocol'] != PROTOCOL or record.get('sha256') != _digest(target):
        raise ValueError('실행기 검증에 실패했습니다.')
    with target.open('rb') as stream:
        if stream.read(2) != b'MZ':
            raise ValueError('실행기 형식이 올바르지 않습니다.')
    return target


def ensure_launcher(paths):
    try:
        return verified_launcher(paths)  # An installed protocol-1 launcher stays fixed across app versions.
    except (OSError, ValueError, KeyError, TypeError):
        pass
    try:
        existing = json.loads(launcher_path(paths).with_name('manifest.json').read_text('utf-8'))
        if type(existing.get('protocol')) is int and existing['protocol'] > PROTOCOL:
            raise RuntimeError('더 최신 실행기가 설치되어 있습니다. 최신 설치 파일로 복구해 주세요.')
    except (OSError, ValueError, TypeError):
        pass
    source, record = launcher_resource()
    if type(record.get('protocol')) is not int or record['protocol'] != PROTOCOL or record.get('sha256') != _digest(source):
        raise ValueError('설치 파일에 포함된 실행기를 검증하지 못했습니다.')
    with source.open('rb') as stream:
        if stream.read(2) != b'MZ':
            raise ValueError('실행기 형식이 올바르지 않습니다.')
    target = launcher_path(paths)
    staged = target.with_name('.launcher-' + uuid.uuid4().hex + '.exe')
    try:
        atomic_copy(source, staged)
        if _digest(staged) != record['sha256']:
            raise OSError('실행기 복사 결과가 원본과 다릅니다.')
        atomic_replace(staged, target)
        atomic_bytes(target.with_name('manifest.json'), json.dumps(record).encode('utf-8'))
    finally:
        staged.unlink(missing_ok=True)
    return verified_launcher(paths)


def prepare_installation(paths):
    if not getattr(sys, 'frozen', False):
        return None
    active = active_installation(paths)
    if active and _version(active[0]) > _version(VERSION):
        return active[1]
    source, destination = Path(sys.executable).resolve(), executable_for(paths)
    if source != destination.resolve():
        with source.open('rb') as stream:
            if stream.read(2) != b'MZ':
                raise ValueError('설치할 실행 파일 형식이 올바르지 않습니다.')
        digest = _digest(source)
        if not destination.exists() or _digest(destination) != digest:
            # Verify a separate candidate before replacing any installed file.
            staged = destination.with_name('.install-' + uuid.uuid4().hex + '.exe')
            try:
                atomic_copy(source, staged)
                if _digest(staged) != digest:
                    raise OSError('프로그램 복사 결과가 원본과 다릅니다. 기존 버전을 유지합니다.')
                atomic_replace(staged, destination)
            finally:
                staged.unlink(missing_ok=True)
    return destination


def desktop_shortcut(paths):
    name = read_record(paths).get('shortcutName', desktop_entries.DEFAULT_SHORTCUT)
    path = paths.desktop / name
    if path.parent.resolve() != paths.desktop.resolve():
        raise ValueError('바로가기 위치가 올바르지 않습니다.')
    return path


def activate(paths, executable=None, token=None):
    executable = Path(executable or executable_for(paths))
    if not executable.is_file():
        raise OSError('실행 파일을 찾지 못했습니다.')
    current = active_installation(paths)
    if current and _version(current[0]) > _version(VERSION):
        raise ValueError('더 최신 버전이 설치되어 있어 기존 바로가기를 유지합니다.')
    active = paths.installation / 'active.json'
    original = active.read_bytes() if active.exists() else None
    try:
        old_record = read_record(paths)
    except (OSError, ValueError, KeyError, TypeError):
        old_record = {}
    launcher = ensure_launcher(paths)
    origin = None
    if token and re.fullmatch(r'[0-9a-f]{32}', token):
        try:
            plan = paths.updates / (token + '.json')
            if plan.stat().st_size <= 8192:
                origin = json.loads(plan.read_text('utf-8')).get('previous')
        except (OSError, ValueError, TypeError):
            pass
    shortcut = desktop_entries.choose_shortcut(paths, old_record.get('shortcutName'), origin)
    record = dict(version=VERSION, executable=str(executable), sha256=_digest(executable),
                  launcherProtocol=PROTOCOL, shortcutName=shortcut.name)
    if current and current[0] != VERSION:
        record['previous'] = dict(version=current[0], executable=str(current[1]), sha256=_digest(current[1]))
    elif old_record.get('previous'):
        try:
            previous_version, previous_target = validate_record(paths, old_record['previous'])
            record['previous'] = dict(version=previous_version, executable=str(previous_target), sha256=_digest(previous_target))
        except (OSError, ValueError, KeyError, TypeError):
            pass
    validate_record(paths, record)
    if current:
        backup = dict(old_record, version=current[0], executable=str(current[1]), sha256=_digest(current[1]))
        atomic_bytes(active.with_suffix('.json.bak'), json.dumps(backup, ensure_ascii=False).encode('utf-8'))
    if shortcut.exists() and shortcut_target(shortcut).samefile(launcher):
        # Steady state: update only the small active pointer. Do not replace
        # a user's renamed shortcut or a running launcher on every app update.
        atomic_bytes(active, json.dumps(record, ensure_ascii=False).encode('utf-8'))
        return
    staged = paths.desktop / ('.GunsuSchedule-' + uuid.uuid4().hex + '.lnk')
    try:
        desktop_entries.write_shortcut(staged, launcher)
        if not shortcut_target(staged).samefile(launcher):
            raise OSError('바탕화면 바로가기 대상이 올바르지 않아 기존 버전을 유지합니다.')
        atomic_bytes(active, json.dumps(record, ensure_ascii=False).encode('utf-8'))
        try:
            atomic_bytes(shortcut, staged.read_bytes())
        except OSError:
            if original is not None:
                atomic_bytes(active, original)
            else:
                active.unlink(missing_ok=True)
            raise
    finally:
        staged.unlink(missing_ok=True)


def shortcut_target(path):
    return desktop_entries.read_shortcut(path)[0]


def archive_legacy_desktop_entry(paths):
    """After ready, migrate all positively identified desktop entries regardless of name."""
    current = active_installation(paths)
    if not current or current[0] != VERSION or current[1].resolve() != executable_for(paths).resolve():
        return False
    verified_launcher(paths)
    report = desktop_entries.migrate(paths, read_record(paths))
    return bool(report['archived']) and not report['pending']


class SingleInstance:
    def __init__(self):
        self.handle = None

    def acquire(self):
        if os.name != 'nt':
            return True
        import ctypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
        kernel.CreateMutexW.restype = ctypes.c_void_p
        self.handle = kernel.CreateMutexW(None, False, 'Local\\GunsuSchedule-' + os.environ.get('USERNAME', 'user'))
        error = ctypes.get_last_error()
        if not self.handle:
            raise OSError('프로그램 중복 실행을 확인하지 못했습니다.')
        if error == 183:
            self.close()
            return False
        return True

    def close(self):
        if self.handle:
            import ctypes
            kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            kernel.CloseHandle.argtypes = [ctypes.c_void_p]
            kernel.CloseHandle(self.handle)
            self.handle = None
