"""Per-user, versioned installation. A working previous version is never replaced."""
from pathlib import Path
import hashlib
import json
import os
import sys
import uuid
from app_info import ASSET_NAME, VERSION
from storage import atomic_bytes, atomic_copy


def executable_for(paths, version=VERSION):
    return paths.installation / 'versions' / version / ASSET_NAME


def prepare_installation(paths):
    if not getattr(sys, 'frozen', False):
        return None
    source, destination = Path(sys.executable).resolve(), executable_for(paths)
    if source != destination.resolve():
        def digest(path):
            with path.open('rb') as stream:
                return hashlib.file_digest(stream, 'sha256').digest()
        if not destination.exists() or digest(destination) != digest(source):
            atomic_copy(source, destination)
    return destination


def activate(paths, executable=None):
    executable = Path(executable or executable_for(paths))
    if not executable.is_file():
        raise OSError('실행 파일을 찾지 못했습니다.')
    active = paths.installation / 'active.json'
    previous = active.read_bytes() if active.exists() else None
    record = json.dumps({'version': VERSION, 'executable': str(executable)}, ensure_ascii=False).encode('utf-8')
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
