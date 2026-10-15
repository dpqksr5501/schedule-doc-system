"""Migrate desktop entry points by identity, preserving labels and originals."""
from pathlib import Path
import json
import logging
import os
import time
from app_info import VERSION, ASSET_NAME, INSTALLED_EXE_NAME
from launch_registry import digest, version, launcher_path
from storage import atomic_bytes, atomic_copy

DEFAULT_SHORTCUT = '군수실 일정 관리.lnk'


def read_shortcut(path):
    import pythoncom
    from win32com.shell import shell
    pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)
    try:
        link = pythoncom.CoCreateInstance(shell.CLSID_ShellLink, None,
            pythoncom.CLSCTX_INPROC_SERVER, shell.IID_IShellLink)
        link.QueryInterface(pythoncom.IID_IPersistFile).Load(str(Path(path).resolve()))
        target, _ = link.GetPath(shell.SLGP_RAWPATH)
        if not target:
            raise OSError('바탕화면 바로가기 대상이 비어 있습니다.')
        return Path(os.path.expandvars(target)), link.GetArguments()
    finally:
        pythoncom.CoUninitialize()


def write_shortcut(path, target):
    import pythoncom
    from win32com.shell import shell
    pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)
    try:
        link = pythoncom.CoCreateInstance(shell.CLSID_ShellLink, None,
            pythoncom.CLSCTX_INPROC_SERVER, shell.IID_IShellLink)
        link.SetPath(str(Path(target).resolve()))
        link.SetWorkingDirectory(str(Path(target).parent.resolve()))
        link.SetDescription('군수실 일정 관리 - 일정 입력, 업무 메모, 한글 문서 저장')
        link.SetIconLocation(str(Path(target).resolve()), 0)
        link.QueryInterface(pythoncom.IID_IPersistFile).Save(str(Path(path).resolve()), 0)
    finally:
        pythoncom.CoUninitialize()


def regular_file(path):
    try:
        return (path.is_file() and not path.is_symlink()
                and not getattr(path.stat(), 'st_file_attributes', 0) & 0x400)
    except OSError:
        return False


def known_files(paths):
    """Size first, then SHA256. Never infer identity from a desktop filename."""
    catalog = {}
    for name in (ASSET_NAME, INSTALLED_EXE_NAME):
        for path in (paths.installation / 'versions').glob('*/' + name):
            try:
                if version(path.parent.name) <= version(VERSION) and regular_file(path):
                    catalog.setdefault(path.stat().st_size, set()).add(digest(path))
            except (OSError, ValueError):
                continue
    launcher = launcher_path(paths)
    if regular_file(launcher):
        catalog.setdefault(launcher.stat().st_size, set()).add(digest(launcher))
    return catalog


def owned_file(path, catalog):
    try:
        return (regular_file(path) and path.stat().st_size in catalog
                and digest(path) in catalog[path.stat().st_size])
    except OSError:
        return False


def owned_shortcuts(paths, catalog):
    results = []
    for path in paths.desktop.iterdir():
        if path.suffix.lower() != '.lnk' or not regular_file(path):
            continue
        try:
            target, arguments = read_shortcut(path)
            if not target.is_absolute() or (target.drive.startswith('\\\\') and not target.is_relative_to(paths.desktop)):
                continue  # Do not probe an unrelated network shortcut while identifying local app entries.
            if not arguments and owned_file(target, catalog):
                results.append(path)
        except Exception:
            # An unrelated or malformed shortcut is never modified.
            continue
    return sorted(results, key=lambda p: p.name.casefold())


def choose_shortcut(paths, preferred=None, origin=None):
    if isinstance(preferred, str) and Path(preferred).name == preferred:
        preferred_path = paths.desktop / preferred
        try:
            target, arguments = read_shortcut(preferred_path)
            if regular_file(preferred_path) and not arguments and target.resolve() == launcher_path(paths).resolve():
                return preferred_path
        except Exception:
            pass
    links = owned_shortcuts(paths, known_files(paths))
    for name in (preferred,):
        selected = next((p for p in links if p.name == name), None)
        if selected:
            return selected
    if origin:
        for link in links:
            try:
                if read_shortcut(link)[0].resolve() == Path(origin).resolve():
                    return link
            except (OSError, ValueError, TypeError):
                continue
    selected = next((p for p in links if p.name == DEFAULT_SHORTCUT), None)
    if selected:
        return selected
    if links:
        return links[0]  # Keep a user's renamed label instead of creating a duplicate.
    for index in range(1000):
        name = DEFAULT_SHORTCUT if not index else f'군수실 일정 관리 ({index}).lnk'
        path = paths.desktop / name
        if not path.exists():
            return path
    raise OSError('바탕화면에 새 바로가기를 준비하지 못했습니다.')


def archive_one(paths, path):
    original = digest(path)
    backup = paths.updates / 'desktop-entries' / original / path.name
    if not backup.exists():
        atomic_copy(path, backup)
    if digest(backup) != original:
        raise OSError('복구용 사본을 확인하지 못해 원본을 유지합니다.')
    for attempt in range(30):
        if not path.exists():
            return backup
        if digest(path) != original or digest(backup) != original:
            raise OSError('대기 중 파일이 변경되어 원본을 유지합니다.')
        try:
            path.unlink()
            return backup
        except PermissionError:
            if attempt == 29:
                raise
            time.sleep(.5)


def migrate(paths, record):
    selected = paths.desktop / record.get('shortcutName', DEFAULT_SHORTCUT)
    if selected.parent.resolve() != paths.desktop.resolve():
        raise ValueError('바로가기 위치가 올바르지 않습니다.')
    target, arguments = read_shortcut(selected)
    if arguments or not target.samefile(launcher_path(paths)):
        raise OSError('대표 바로가기의 실행기 연결을 확인하지 못했습니다.')
    catalog = known_files(paths)
    duplicates = [p for p in owned_shortcuts(paths, catalog) if p != selected]
    duplicates += [p for p in paths.desktop.iterdir() if p.suffix.lower() == '.exe' and owned_file(p, catalog)]
    report = {'shortcut': selected.name, 'archived': [], 'pending': []}
    for path in duplicates:
        try:
            backup = archive_one(paths, path)
            report['archived'].append({'name': path.name, 'backup': str(backup)})
        except OSError as error:
            report['pending'].append({'name': path.name, 'message': str(error)})
            logging.warning('Desktop entry retained for next launch: %s', path, exc_info=True)
    atomic_bytes(paths.updates / 'desktop-migration.json', json.dumps(report, ensure_ascii=False).encode('utf-8'))
    return report
