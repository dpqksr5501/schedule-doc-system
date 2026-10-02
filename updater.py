"""Verified GitHub updates installed side by side; no shell scripts or in-place swaps."""
from pathlib import Path
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from app_info import VERSION, ASSET_NAME, REPO_OWNER, REPO_NAME
from storage import atomic_bytes
from native_workers import self_command, independent_environment

CURRENT_VERSION = VERSION
GITHUB_API_URL = f'https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/releases/latest'
MAX_DOWNLOAD = 250 * 1024 * 1024
_UPDATE_LOCK = threading.Lock()
_STABLE = re.compile(r'v?(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?')


def get_current_version():
    return VERSION


def _version(value):
    match = _STABLE.fullmatch(value.strip()) if isinstance(value, str) else None
    if not match:
        raise ValueError('정식 버전 번호가 올바르지 않습니다.')
    return tuple(int(part) for part in match.groups())


def _is_newer_version(latest, current):
    try:
        return _version(latest) > _version(current)
    except ValueError:
        return False


def _request(url):
    return urllib.request.Request(url, headers={'User-Agent': f'GunsuSchedule/{VERSION}',
                                                'Accept': 'application/vnd.github+json'})


def _fetch_release():
    with urllib.request.urlopen(_request(GITHUB_API_URL), timeout=8) as response:
        content = response.read(2 * 1024 * 1024 + 1)
    if len(content) > 2 * 1024 * 1024:
        raise ValueError('업데이트 안내가 너무 큽니다.')
    data = json.loads(content)
    if not isinstance(data, dict) or data.get('draft') or data.get('prerelease'):
        raise ValueError('정식 배포 정보가 아닙니다.')
    version = data.get('tag_name', '').removeprefix('v')
    _version(version)
    assets = [a for a in data.get('assets', []) if a.get('name') == ASSET_NAME and a.get('state') == 'uploaded']
    asset = assets[0] if len(assets) == 1 else None
    if asset:
        url = urllib.parse.urlsplit(asset.get('browser_download_url', ''))
        expected = f'/{REPO_OWNER}/{REPO_NAME}/releases/download/{data["tag_name"]}/{ASSET_NAME}'
        if url.scheme != 'https' or url.netloc != 'github.com' or urllib.parse.unquote(url.path) != expected:
            raise ValueError('업데이트 파일의 출처가 올바르지 않습니다.')
        if type(asset.get('size')) is not int or not 1024 <= asset['size'] <= MAX_DOWNLOAD:
            raise ValueError('업데이트 파일 크기가 올바르지 않습니다.')
        if not re.fullmatch(r'sha256:[0-9a-fA-F]{64}', asset.get('digest') or ''):
            asset = None  # Missing digest: show release, but do not execute an unverifiable file.
    return version, data.get('body') or '', asset


def check_for_updates():
    base = {'currentVersion': VERSION, 'hasUpdate': False}
    try:
        version, notes, asset = _fetch_release()
        return {**base, 'success': True, 'hasUpdate': _is_newer_version(version, VERSION),
                'latestVersion': version, 'releaseNotes': str(notes)[:12000],
                'canApply': asset is not None,
                'message': '' if asset else '검증 가능한 실행 파일이 아직 없습니다. 현재 버전은 계속 사용할 수 있습니다.'}
    except urllib.error.HTTPError as error:
        return {**base, 'success': False, 'message': '배포 정보를 아직 찾지 못했습니다.' if error.code == 404 else
                f'업데이트 서버에 연결하지 못했습니다. (응답 {error.code})'}
    except (ValueError, TypeError, KeyError) as error:
        return {**base, 'success': False, 'message': '업데이트 정보를 검증하지 못했습니다. ' + str(error)}
    except Exception:
        return {**base, 'success': False, 'message': '네트워크 연결이 없어 업데이트를 확인하지 못했습니다. 일정 관리는 계속 가능합니다.'}


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        url = urllib.parse.urlsplit(newurl)
        if url.scheme != 'https' or url.netloc not in ('github.com', 'release-assets.githubusercontent.com', 'objects.githubusercontent.com'):
            raise ValueError('허용되지 않은 다운로드 이동 경로입니다.')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _download(asset, target):
    start, digest, total = time.monotonic(), hashlib.sha256(), 0
    opener = urllib.request.build_opener(SafeRedirect())
    target.parent.mkdir(parents=True, exist_ok=True)
    staged = target.with_suffix('.download')
    try:
        with opener.open(_request(asset['browser_download_url']), timeout=15) as response, staged.open('wb') as stream:
            while True:
                if time.monotonic() - start > 180:
                    raise TimeoutError('업데이트 다운로드 시간이 지났습니다.')
                chunk = response.read(65536)
                if not chunk:
                    break
                total += len(chunk)
                if total > asset['size'] or total > MAX_DOWNLOAD:
                    raise ValueError('업데이트 파일이 예상 크기를 초과했습니다.')
                digest.update(chunk)
                stream.write(chunk)
            stream.flush()
            os.fsync(stream.fileno())
        if total != asset['size'] or digest.hexdigest() != asset['digest'].split(':')[1].lower():
            raise ValueError('다운로드 파일의 크기 또는 해시가 일치하지 않습니다.')
        with staged.open('rb') as stream:
            if stream.read(2) != b'MZ':
                raise ValueError('Windows 실행 파일 형식이 아닙니다.')
        os.replace(staged, target)
    finally:
        if staged.exists():
            staged.unlink()


def prepare_update(paths):
    if os.name != 'nt' or not getattr(sys, 'frozen', False):
        return {'success': False, 'message': '배포된 Windows 실행 파일에서만 업데이트할 수 있습니다.'}
    if not _UPDATE_LOCK.acquire(blocking=False):
        return {'success': False, 'message': '이미 업데이트를 준비하고 있습니다.'}
    try:
        version, _, asset = _fetch_release()
        if not _is_newer_version(version, VERSION) or asset is None:
            raise ValueError('검증된 새 정식 버전이 없습니다.')
        target = paths.installation / 'versions' / version / ASSET_NAME
        _download(asset, target)
        token = uuid.uuid4().hex
        plan = paths.updates / (token + '.json')
        atomic_bytes(plan, json.dumps({'token': token, 'version': version, 'target': str(target),
                                     'previous': sys.executable, 'digest': asset['digest'],
                                     'size': asset['size']}).encode('utf-8'))
        subprocess.Popen(self_command('--monitor-update', token), env=independent_environment(),
                         creationflags=subprocess.CREATE_NO_WINDOW)
        return {'success': True, 'message': '검증된 새 버전을 시작합니다. 기존 버전은 복구용으로 보관합니다.'}
    except Exception as error:
        return {'success': False, 'message': '업데이트 준비 실패: ' + str(error)}
    finally:
        _UPDATE_LOCK.release()


def monitor_update(paths, token):
    if not re.fullmatch(r'[0-9a-f]{32}', token):
        raise ValueError('잘못된 업데이트 작업 번호')
    plan_path = paths.updates / (token + '.json')
    plan = json.loads(plan_path.read_text(encoding='utf-8'))
    previous = Path(plan['previous']).resolve()
    if previous != Path(sys.executable).resolve():
        raise ValueError('이전 버전의 실행 경로가 올바르지 않습니다.')
    def rollback(message):
        atomic_bytes(paths.updates / 'last_failure.txt', message.encode('utf-8'))
        try:
            if previous.is_file():
                subprocess.Popen([str(previous)], env=independent_environment(), creationflags=subprocess.CREATE_NO_WINDOW)
        except OSError:
            atomic_bytes(paths.updates / 'last_failure.txt',
                         (message + '\n바탕화면 바로가기로 기존 버전을 실행해 주세요.').encode('utf-8'))
        return 1
    _version(plan['version'])
    target = Path(plan['target']).resolve()
    expected = (paths.installation / 'versions' / plan['version'] / ASSET_NAME).resolve()
    try:
        if target != expected or target.stat().st_size != plan['size'] or ('sha256:' + hashlib.sha256(target.read_bytes()).hexdigest()) != plan['digest'].lower():
            return rollback('새 버전 파일의 검증이 실패해 기존 버전을 다시 실행했습니다.')
    except OSError:
        return rollback('새 버전 파일을 읽지 못해 기존 버전을 다시 실행했습니다.')
    # The old GUI closes normally. The new version waits for its mutex to be released.
    try:
        process = subprocess.Popen([str(target), '--update-token', token], env=independent_environment(),
                                   creationflags=subprocess.CREATE_NO_WINDOW)
    except OSError:
        return rollback('새 버전 실행이 실패해 기존 버전을 다시 실행했습니다.')
    ready = paths.updates / (token + '.ready')
    for _ in range(90):
        if ready.exists():
            return 0  # New app activates the desktop shortcut only after successful bootstrap.
        if process.poll() is not None:
            return rollback('새 버전이 시작되지 않아 기존 버전을 다시 실행했습니다.')
        time.sleep(1)
    # Do not kill a GUI that may be waiting for an institution security dialog.
    # The old shortcut remains available; this failure is shown on the next launch.
    atomic_bytes(paths.updates / 'last_failure.txt', '새 버전 시작을 확인하지 못했습니다. 바탕화면 바로가기로 기존 버전을 실행해 주세요.'.encode('utf-8'))
    return 1
