"""Version-independent contract read by the fixed launcher (protocol 1)."""
from pathlib import Path
import hashlib
import json
import re
from app_info import ASSET_NAME, INSTALLED_EXE_NAME

PROTOCOL = 1
LAUNCHER_NAME = 'GunsuLauncher.exe'


def launcher_path(paths):
    return paths.installation / 'launcher' / LAUNCHER_NAME


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def version(value):
    if not isinstance(value, str) or not re.fullmatch(r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)', value):
        raise ValueError('설치 버전 정보가 올바르지 않습니다.')
    return tuple(map(int, value.split('.')))


def read_records(paths):
    records = []
    for name in ('active.json', 'active.json.bak'):
        try:
            path = paths.installation / name
            if path.stat().st_size > 8192:
                continue
            value = json.loads(path.read_text('utf-8'))
            if isinstance(value, dict):
                records.append(value)
        except (OSError, ValueError, RecursionError):
            continue
    if not records:
        raise ValueError('설치 정보를 읽지 못했습니다. 설치 파일로 복구해 주세요.')
    return records


def read_record(paths):
    return read_records(paths)[0]


def validate_record(paths, record, require_digest=True):
    version(record['version'])
    target = Path(record['executable']).resolve()
    root = (paths.installation / 'versions').resolve()
    allowed = [(root / record['version'] / name).resolve() for name in (INSTALLED_EXE_NAME, ASSET_NAME)]
    if target not in allowed or not target.is_relative_to(root) or not target.is_file():
        raise ValueError('설치 경로가 올바르지 않습니다.')
    with target.open('rb') as stream:
        if stream.read(2) != b'MZ':
            raise ValueError('설치된 실행 파일을 확인하지 못했습니다.')
    expected = record.get('sha256')
    if require_digest and not re.fullmatch(r'[0-9a-f]{64}', expected or ''):
        raise ValueError('설치된 실행 파일의 검증 정보가 없습니다.')
    if expected and expected != digest(target):
        raise ValueError('설치된 실행 파일이 변경되었습니다.')
    return record['version'], target


def launch_choices(paths):
    choices = []
    for candidate in [candidate for record in read_records(paths) for candidate in (record, record.get('previous'))]:
        try:
            entry = validate_record(paths, candidate)
            if entry not in choices:
                choices.append(entry)
        except (OSError, ValueError, KeyError, TypeError):
            continue
    if not choices:
        raise ValueError('실행할 프로그램을 검증하지 못했습니다. 설치 파일로 복구해 주세요.')
    return choices
