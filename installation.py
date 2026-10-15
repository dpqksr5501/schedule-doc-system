"""Per-user, versioned installation. A working previous version is never replaced."""
from pathlib import Path
import hashlib
import json
import logging
import os
import re
import sys
import uuid
from app_info import ASSET_NAME, INSTALLED_EXE_NAME, VERSION
from storage import atomic_bytes, atomic_copy, atomic_replace


def executable_for(paths, version=VERSION):
    return paths.installation / 'versions' / version / INSTALLED_EXE_NAME


def _version(value):
    if not isinstance(value, str) or not re.fullmatch(r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)', value):
        raise ValueError('설치 버전 정보가 올바르지 않습니다.')
    return tuple(map(int, value.split('.')))


def _digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def active_installation(paths):
    """Accept only our own version directory, including legacy English names."""
    active = paths.installation / 'active.json'
    if not active.exists():
        return None
    try:
        if active.stat().st_size > 8192:
            raise ValueError('설치 정보가 너무 큽니다.')
        record = json.loads(active.read_text('utf-8'))
        version = record['version']
        _version(version)
        target = Path(record['executable']).resolve()
        root = (paths.installation / 'versions').resolve()
        allowed = [(root / version / name).resolve() for name in (INSTALLED_EXE_NAME, ASSET_NAME)]
        if not target.is_relative_to(root) or target not in allowed or not target.is_file():
            raise ValueError('설치 경로가 올바르지 않습니다.')
        with target.open('rb') as stream:
            if stream.read(2) != b'MZ':
                raise ValueError('설치된 실행 파일을 확인하지 못했습니다.')
        if record.get('sha256') and record['sha256'] != _digest(target):
            raise ValueError('설치된 실행 파일이 변경되었습니다.')
        return version, target
    except (OSError, ValueError, KeyError, TypeError):
        logging.warning('Active installation record could not be validated', exc_info=True)
        return None


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


def activate(paths, executable=None):
    executable = Path(executable or executable_for(paths))
    if not executable.is_file():
        raise OSError('실행 파일을 찾지 못했습니다.')
    current = active_installation(paths)
    if current and _version(current[0]) > _version(VERSION):
        raise ValueError('더 최신 버전이 설치되어 있어 기존 바로가기를 유지합니다.')
    active = paths.installation / 'active.json'
    previous = active.read_bytes() if active.exists() else None
    record = json.dumps({'version': VERSION, 'executable': str(executable), 'sha256': _digest(executable)},
                        ensure_ascii=False).encode('utf-8')
    # Stage the link first. Never let a partial COM Save replace the live shortcut.
    staged = paths.desktop / ('.GunsuSchedule-' + uuid.uuid4().hex + '.lnk')
    if os.name == 'nt':
        import pythoncom
        from win32com.shell import shell
        pythoncom.CoInitialize()
        try:
            # Unicode Shell Link API로 시스템 언어와 관계없이 한글 경로를 보존합니다.
            shortcut = pythoncom.CoCreateInstance(shell.CLSID_ShellLink, None,
                pythoncom.CLSCTX_INPROC_SERVER, shell.IID_IShellLink)
            shortcut.SetPath(str(executable.resolve()))
            shortcut.SetWorkingDirectory(str(executable.parent.resolve()))
            shortcut.SetDescription('군수실 일정 관리 - 일정 입력, 업무 메모, 한글 문서 저장')
            shortcut.SetIconLocation(str(executable.resolve()), 0)
            shortcut.QueryInterface(pythoncom.IID_IPersistFile).Save(str(staged.resolve()), 0)
            if not shortcut_target(staged).samefile(executable):
                raise OSError('바탕화면 바로가기 대상이 올바르지 않아 기존 버전을 유지합니다.')
            atomic_bytes(active, record)
            try:
                atomic_bytes(paths.desktop / '군수실 일정 관리.lnk', staged.read_bytes())
            except OSError:
                if previous is not None:
                    atomic_bytes(active, previous)
                else:
                    active.unlink(missing_ok=True)
                raise
        finally:
            pythoncom.CoUninitialize()
            try:
                staged.unlink(missing_ok=True)
            except OSError:
                pass
    else:
        atomic_bytes(active, record)


def shortcut_target(path):
    """Unicode 경로로 저장된 바로가기를 다시 읽어 실제 대상을 확인합니다."""
    import pythoncom
    from win32com.shell import shell
    link = pythoncom.CoCreateInstance(shell.CLSID_ShellLink, None,
        pythoncom.CLSCTX_INPROC_SERVER, shell.IID_IShellLink)
    link.QueryInterface(pythoncom.IID_IPersistFile).Load(str(Path(path).resolve()))
    target, _ = link.GetPath(shell.SLGP_RAWPATH)
    if not target:
        raise OSError('바탕화면 바로가기 대상이 비어 있습니다.')
    return Path(target)


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
