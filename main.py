"""Native entry point. All business services are usable without importing pywebview."""
from pathlib import Path
import csv
import html
import io
import json
import logging
from logging.handlers import RotatingFileHandler
import os
import re
import sys
import threading
import time
import uuid
from app_info import APP_NAME, VERSION
from app_paths import AppPaths, resource_dir
from schedule_domain import parse_snapshot, timestamp, validate_snapshot
from storage import SnapshotStore, atomic_bytes, encode
from document_engine import document_model, generate_document
from document_layout import build_plan
import installation
import updater
from native_workers import convert_bounded
from hwp_validation import validate_hwp


class DesktopApi:
    def __init__(self, paths=None):
        self._paths = paths or AppPaths.current()
        self._store = SnapshotStore(self._paths)
        self._window = None
        self._lock = threading.RLock()
        self._busy = False
        self._output_error = ''
        self._installed = None
        self._update_token = None
        self._last_output = None
        self._editing = False
        self._allow_close = False
        try:
            self._ensure_output()
        except OSError as error:
            self._output_error = '바탕화면 출력 폴더를 만들지 못했습니다. 폴더 권한을 확인해 주세요. ' + str(error)

    def _ensure_output(self):
        self._paths.ensure_output()
        manual = (resource_dir() / 'assets' / 'manual.html').read_text(encoding='utf-8')
        manual = manual.replace('{{OUTPUT_PATH}}', html.escape(str(self._paths.output)))
        manual = manual.replace('{{DATA_PATH}}', html.escape(str(self._paths.data)))
        manual = manual.replace('{{APP_PATH}}', html.escape(str(self._paths.installation)))
        atomic_bytes(self._paths.output / '먼저_읽어주세요.html', manual.encode('utf-8'))
        plain = (resource_dir() / '사용설명서.txt').read_text(encoding='utf-8-sig')
        atomic_bytes(self._paths.output / '사용설명서.txt', plain.encode('utf-8-sig'))
        quick = (resource_dir() / '처음사용_5분안내.html').read_bytes()
        atomic_bytes(self._paths.output / '처음사용_5분안내.html', quick)

    def _failure(self, error):
        logging.exception('Desktop operation failed')
        return {'success': False, 'message': str(error)}

    def bootstrap(self):
        result = {'success': True, 'version': VERSION, 'outputPath': str(self._paths.output),
                  'dataPath': str(self._paths.data), 'appPath': str(self._paths.installation),
                  'outputError': self._output_error, 'recovery': None, 'readOnly': False}
        try:
            result['snapshot'] = self._store.load()
            result['recovery'] = self._store.recovery
        except Exception as error:
            from schedule_domain import empty_snapshot
            result.update(snapshot=empty_snapshot(), readOnly=True, recoveryError=str(error))
        failure = self._paths.updates / 'last_failure.txt'
        if failure.exists():
            result['updateWarning'] = failure.read_text(encoding='utf-8')
        return result

    def ready(self):
        try:
            if self._update_token and self.bootstrap()['readOnly']:
                raise ValueError('새 버전에서 일정 데이터를 읽지 못해 기존 바로가기를 유지합니다.')
            if self._installed is not None:
                installation.activate(self._paths, self._installed)
            if self._update_token:
                atomic_bytes(self._paths.updates / (self._update_token + '.ready'), b'ready')
                failure = self._paths.updates / 'last_failure.txt'
                try:
                    failure.unlink(missing_ok=True)
                except OSError:
                    logging.warning('Previous update notice could not be removed')
            return {'success': True}
        except Exception as error:
            return self._failure(error)

    def save_persistent_data(self, content, expected_revision):
        try:
            with self._lock:
                if self._busy:
                    raise ValueError('문서 저장 또는 업데이트가 끝난 뒤 다시 저장해 주세요.')
                snapshot = self._store.save(parse_snapshot(content), expected_revision)
            return {'success': True, 'snapshot': snapshot}
        except Exception as error:
            return self._failure(error)

    def restore_data(self, content, expected_revision):
        try:
            with self._lock:
                if self._busy:
                    raise ValueError('진행 중인 작업이 끝난 뒤 복원해 주세요.')
                snapshot = self._store.import_snapshot(parse_snapshot(content), expected_revision)
            return {'success': True, 'snapshot': snapshot}
        except Exception as error:
            return self._failure(error)

    def preview_restore(self, content):
        try:
            snapshot = parse_snapshot(content)
            dates = sorted(e['date'] for e in snapshot['events'])
            return {'success': True, 'count': len(snapshot['events']), 'trashCount': len(snapshot['deletedEvents']),
                    'savedAt': snapshot['savedAt'], 'firstDate': dates[0] if dates else '', 'lastDate': dates[-1] if dates else ''}
        except Exception as error:
            return self._failure(error)

    def backup_data(self):
        try:
            self._ensure_output()
            snapshot = self._store.load()
            path = self._paths.output / '데이터백업' / ('일정데이터_' + self._stamp() + '.json')
            atomic_bytes(path, encode(snapshot))
            self._last_output = path
            self._show_file(path)
            return {'success': True, 'path': str(path), 'message': '일정과 업무 메모를 함께 백업했습니다.'}
        except Exception as error:
            return self._failure(error)

    def list_backups(self):
        return {'success': True, 'items': self._store.list_backups()}

    def get_backup(self, identifier):
        try:
            return {'success': True, 'content': encode(self._store.read_backup(identifier)).decode('utf-8')}
        except Exception as error:
            return self._failure(error)

    def preview_document(self, request):
        try:
            snapshot = self._store.load()
            return {'success': True, 'plan': build_plan(document_model(snapshot, request)), 'revision': snapshot['revision']}
        except Exception as error:
            return self._failure(error)

    def export_document(self, request, file_format='hwp'):
        if not self._lock.acquire(blocking=False):
            return {'success': False, 'message': '다른 저장 작업이 진행 중입니다.'}
        try:
            if self._busy:
                raise ValueError('이미 문서를 저장하고 있습니다.')
            self._busy = True
            if file_format not in ('hwpx', 'hwp'):
                raise ValueError('출력 파일 형식이 올바르지 않습니다.')
            self._ensure_output()
            model = document_model(self._store.load(), request)
            folder = {'daily': '일일일정', 'weekly': '주간일정', 'monthly': '월간일정'}[model['view']]
            filename = folder + '_' + model['start'] + '_' + self._stamp() + '.hwpx'
            path = self._paths.output / folder / filename
            result = generate_document(model, path)
            fallback = False
            warning = ''
            if file_format == 'hwp':
                target = path.with_suffix('.hwp')
                try:
                    ok, warning = convert_bounded(path, target)
                    if ok:
                        validate_hwp(target)
                except Exception:
                    logging.exception('HWP conversion or validation failed; preserve intermediate HWPX')
                    ok, warning = False, '한글 변환 결과를 확인하지 못했습니다. 한글 설치와 파일 접근 승인을 확인해 주세요.'
                if ok:
                    intermediate = path
                    path = target
                    try:
                        intermediate.unlink()
                    except OSError:
                        logging.warning('HWP saved; intermediate HWPX could not be removed: %s', intermediate)
                else:
                    fallback = True
                    # Keep only valid output; an incomplete HWP is not a usable fallback.
                    if target.exists():
                        try:
                            target.unlink()
                        except OSError:
                            logging.warning('Incomplete HWP could not be removed: %s', target)
            self._last_output = path
            self._show_file(path)
            return {'success': not fallback, 'path': str(path), 'filename': path.name, 'pages': result['pages'],
                    'requestedFormat': file_format, 'actualFormat': path.suffix[1:],
                    'fallback': fallback, 'message': ('HWP 저장에 실패했습니다. ' + warning +
                    '\n작업 내용은 HWPX 중간 문서로 보관했습니다. 한글에서 열어 [다른 이름으로 저장] → [한글 문서 (*.hwp)]를 선택해 주세요.') if fallback else
                    f'{folder} {file_format.upper()} 문서를 저장했습니다.'}
        except Exception as error:
            return self._failure(error)
        finally:
            self._busy = False
            self._lock.release()

    def export_csv(self):
        try:
            self._ensure_output()
            stream = io.StringIO(newline='')
            writer = csv.writer(stream)
            writer.writerow(['일자', '시작', '종료', '행사명', '장소', '주관부서', '참석 구분', '중요도', '상태'])
            for event in sorted(self._store.load()['events'], key=lambda e: (e['date'], e['time'])):
                values = [event[k] for k in ('date', 'time', 'endTime', 'title', 'place', 'dept', 'attendee', 'priority', 'status')]
                values[6:] = [{'gunsu': '군수님 참석', 'v_gunsu': '부군수님 참석', 'general': '일반 행사'}[event['attendee']],
                              {'normal': '일반', 'important': '중요'}[event['priority']],
                              {'confirmed': '확정', 'tentative': '미확정', 'cancelled': '취소'}[event['status']]]
                writer.writerow(["'" + v if v.lstrip().startswith(('=', '+', '-', '@')) else v for v in values])
            path = self._paths.output / ('전체일정_' + self._stamp() + '.csv')
            atomic_bytes(path, stream.getvalue().encode('utf-8-sig'))
            self._last_output = path
            self._show_file(path)
            return {'success': True, 'path': str(path), 'message': '전체 일정 목록을 저장했습니다. 내부 메모는 포함하지 않았습니다.'}
        except Exception as error:
            return self._failure(error)

    def open_export_folder(self):
        try:
            self._ensure_output()
            if os.name == 'nt':
                os.startfile(self._paths.output)
            return {'success': True}
        except Exception as error:
            return self._failure(error)

    def open_last_output(self):
        if self._last_output is None or not self._last_output.is_file():
            return {'success': False, 'message': '아직 저장한 문서가 없습니다.'}
        self._show_file(self._last_output)
        return {'success': True}

    def open_manual(self):
        try:
            self._ensure_output()
            if os.name == 'nt':
                os.startfile(self._paths.output / '먼저_읽어주세요.html')
            return {'success': True}
        except Exception as error:
            return self._failure(error)

    def check_update(self):
        return updater.check_for_updates()

    def apply_update(self):
        with self._lock:
            if self._busy:
                return {'success': False, 'message': '현재 작업이 끝난 뒤 업데이트해 주세요.'}
            self._busy = True
        result = updater.prepare_update(self._paths)
        if result['success'] and self._window is not None:
            def close_later():
                time.sleep(1)
                self._allow_close = True
                self._window.destroy()
            threading.Thread(target=close_later, daemon=True).start()
        else:
            self._busy = False
        return result

    def _stamp(self):
        return timestamp().replace(':', '').replace('-', '').replace('+0900', '') + '_' + uuid.uuid4().hex[:8]

    def _show_file(self, path):
        if os.name == 'nt':
            import subprocess
            try:
                subprocess.Popen(['explorer.exe', '/select,', str(path)])
            except OSError:
                logging.exception('Output saved but Explorer could not be opened')

    def set_editing(self, value):
        if type(value) is not bool:
            return {'success': False, 'message': '잘못된 편집 상태'}
        self._editing = value
        return {'success': True}

    def _closing(self):
        if self._allow_close:
            return True
        if self._busy or not self._lock.acquire(blocking=False):
            _notify('저장 작업이 진행 중입니다. 완료된 뒤 프로그램을 닫아 주세요.')
            return False
        self._lock.release()
        if self._editing:
            _notify('일정 입력 창이 열려 있습니다. 먼저 저장하거나 입력 창의 닫기를 눌러 주세요.')
            return False
        return True


def _notify(message):
    if os.name == 'nt':
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, message, APP_NAME, 0x40)
    else:
        print(message)


def main():
    # Worker dispatch precedes WebView imports so helpers never open another GUI.
    if len(sys.argv) == 3 and sys.argv[1] == '--smoke-test':
        from smoke import run
        run(sys.argv[2])
        return
    if len(sys.argv) == 5 and sys.argv[1] == '--convert-hwp':
        from hwpx_generator import convert_hwpx_to_hwp
        ok, message = convert_hwpx_to_hwp(sys.argv[2], sys.argv[3])
        atomic_bytes(sys.argv[4], json.dumps({'success': ok, 'message': message}).encode('utf-8'))
        return
    ui_smoke = Path(sys.argv[2]) if len(sys.argv) == 3 and sys.argv[1] == '--ui-smoke-test' else None
    paths = AppPaths.isolated(ui_smoke) if ui_smoke else AppPaths.current()
    paths.ensure_data()
    handler = RotatingFileHandler(paths.data / 'application.log', maxBytes=1024 * 1024, backupCount=3, encoding='utf-8')
    logging.basicConfig(level=logging.INFO, handlers=[handler], format='%(asctime)s %(levelname)s %(message)s')
    if len(sys.argv) == 3 and sys.argv[1] == '--monitor-update':
        updater.monitor_update(paths, sys.argv[2])
        return
    token = sys.argv[2] if len(sys.argv) == 3 and sys.argv[1] == '--update-token' else None
    if token is not None and not re.fullmatch(r'[0-9a-f]{32}', token):
        raise ValueError('잘못된 업데이트 작업 정보')
    instance = installation.SingleInstance()
    deadline = time.monotonic() + (20 if token else 0)
    while not ui_smoke and not instance.acquire():
        if time.monotonic() >= deadline:
            _notify('일정 관리 프로그램이 이미 실행 중입니다. 작업 표시줄에서 열린 창을 확인해 주세요.')
            return
        time.sleep(0.5)
    try:
        import webview
        api = DesktopApi(paths)
        try:
            api._installed = installation.prepare_installation(paths) if not ui_smoke else None
        except Exception:
            logging.exception('Per-user installation failed')
            _notify('바탕화면 실행 바로가기를 준비하지 못했습니다. 내려받은 실행 파일로 계속 사용할 수 있습니다.')
        api._update_token = token
        # Edge's native message bridge works with file URLs. Avoid a local HTTP
        # listener, which can be blocked by institution firewalls.
        api._window = webview.create_window(f'{APP_NAME} · v{VERSION}', url=(resource_dir() / 'index.html').as_uri(),
                                            width=1380, height=920, min_size=(940, 650),
                                            text_select=True, zoomable=True)
        from bridge_security import expose
        expose(api._window, api)
        api._window.events.closing += api._closing
        if ui_smoke:
            from smoke import attach_ui
            attach_ui(api._window, api, ui_smoke)
        # LocalStorage is only a legacy migration source, never the canonical database.
        webview.start(gui='edgechromium', debug=False, private_mode=False,
                      storage_path=str(paths.data / 'webview'))
    except Exception:
        logging.exception('Application startup failed')
        if ui_smoke:
            raise
        _notify('프로그램을 시작하지 못했습니다. Microsoft Edge WebView2 설치와 폴더 권한을 확인해 주세요.\n'
                '오류 기록: ' + str(paths.data / 'application.log'))
    finally:
        instance.close()


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        if len(sys.argv) == 3 and sys.argv[1] in ('--smoke-test', '--ui-smoke-test'):
            # 검사 중에는 대화상자가 CI를 멈추지 않도록 오류를 파일로 남깁니다.
            import traceback
            root = Path(sys.argv[2])
            root.mkdir(parents=True, exist_ok=True)
            name = 'ui-smoke-result.json' if sys.argv[1] == '--ui-smoke-test' else 'smoke-result.json'
            atomic_bytes(root / name, json.dumps(
                {'success': False, 'error': str(error), 'traceback': traceback.format_exc()},
                ensure_ascii=False).encode('utf-8'))
            raise SystemExit(1)
        _notify('프로그램 준비 중 오류가 발생했습니다. 사용자 폴더의 접근 권한을 확인해 주세요.\n' + str(error))
