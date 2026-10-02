"""Frozen-bundle checks run only in an explicitly supplied isolated directory."""
from pathlib import Path
import json
import zipfile
from app_info import VERSION
from app_paths import AppPaths
from main import DesktopApi
from schedule_domain import empty_snapshot, event_record
from storage import atomic_bytes, encode


def run(root):
    paths = AppPaths.isolated(root)
    api = DesktopApi(paths)
    if not (paths.output / '처음사용_5분안내.html').is_file():
        raise RuntimeError('처음 사용 안내가 출력 폴더에 없습니다.')
    snapshot = empty_snapshot()
    snapshot['events'] = [event_record(dict(id='smoke', date='2026-10-02', time='09:00',
                                           title='배포 기능 점검', notes='내부 점검 메모'))]
    saved = api.save_persistent_data(encode(snapshot).decode('utf-8'), 0)
    if not saved['success']:
        raise RuntimeError(saved['message'])
    api._show_file = lambda path: None
    outputs = []
    for view in ('daily', 'weekly', 'monthly'):
        result = api.export_document({'view': view, 'date': '2026-10-02'}, 'hwpx')
        if not result['success']:
            raise RuntimeError(result['message'])
        with zipfile.ZipFile(result['path']) as package:
            if package.testzip() or '내부 점검 메모' in package.read('Preview/PrvText.txt').decode('utf-8'):
                raise RuntimeError('배포 문서 검증 실패')
        outputs.append(result)
    restarted = DesktopApi(paths).bootstrap()
    if restarted['snapshot']['events'][0]['notes'] != '내부 점검 메모':
        raise RuntimeError('재시작 저장 검증 실패')
    report = {'success': True, 'version': VERSION, 'documents': outputs,
              'dataPath': str(paths.data), 'outputPath': str(paths.output)}
    import installation
    installed = installation.prepare_installation(paths)
    if installed:
        installation.activate(paths, installed)
        import win32com.client
        import pythoncom
        pythoncom.CoInitialize()
        try:
            shortcut = paths.desktop / '군수실 일정 관리.lnk'
            shell = win32com.client.Dispatch('WScript.Shell')
            if Path(shell.CreateShortcut(str(shortcut)).TargetPath) != installed:
                raise RuntimeError('바탕화면 바로가기 점검 실패')
            report['shortcut'] = str(shortcut)
            report['installed'] = str(installed)
        finally:
            pythoncom.CoUninitialize()
    atomic_bytes(Path(root) / 'smoke-result.json', json.dumps(report, ensure_ascii=False).encode('utf-8'))


def attach_ui(window, api, root):
    # This is a developer test of our own bridge, never a production data operation.
    def loaded():
        script = """(async () => {
          const api = window.pywebview.api;
          const info = await api.bootstrap();
          const result = {success: info.success && !info.readOnly,
            methods: Object.keys(api), title: document.title,
            scripts: [...document.scripts].map(s => s.src),
            csp: document.querySelector('[http-equiv="Content-Security-Policy"]').content};
          const event = window.ScheduleCore.newEvent('2026-10-02');
          event.title = 'WebView2 연결 점검'; event.notes = '연결 테스트 메모';
          const snapshot = info.snapshot; snapshot.events = [event];
          const saved = await api.save_persistent_data(JSON.stringify(snapshot), snapshot.revision);
          const loaded = await api.bootstrap();
          result.persistence = saved.success && loaded.snapshot.events[0].notes === event.notes;
          result.success = result.success && result.persistence;
          const planned = await api.preview_document({view:'daily',date:'2026-10-02'});
          result.documentPreview = planned.success && planned.plan.eventCount === 1 &&
            planned.plan.pages[0].rows[0].kind === 'daily-header' &&
            !!document.getElementById('includeAnnotation') &&
            !!document.querySelector('link[href="document.css"]');
          result.success = result.success && result.documentPreview;
          const editing = await api.set_editing(false);
          result.success = result.success && editing.success && !!document.getElementById('newBtn');
          return result;
        })()"""
        def done(result):
            atomic_bytes(Path(root) / 'ui-smoke-result.json', json.dumps(result, ensure_ascii=False).encode('utf-8'))
            api._allow_close = True
            window.destroy()
        window.evaluate_js(script, callback=done)
    window.events.loaded += loaded
