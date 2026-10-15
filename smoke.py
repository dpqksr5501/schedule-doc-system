"""Frozen-bundle checks run only in an explicitly supplied isolated directory."""
from pathlib import Path
import json
import sys
import zipfile
from app_info import VERSION
from app_paths import AppPaths
from main import DesktopApi
from schedule_domain import empty_snapshot, event_record
from storage import atomic_bytes, encode
from branding import ASSET_FILES
from app_paths import resource_dir


def run(root):
    def progress(stage):
        atomic_bytes(Path(root) / 'smoke-progress.json', json.dumps(
            {'stage': stage}, ensure_ascii=False).encode('utf-8'))
    progress('출력 폴더와 안내문 준비')
    for filename in ASSET_FILES:
        if not (resource_dir() / filename).is_file():
            raise RuntimeError('배포 이미지가 없습니다: ' + filename)
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
        progress(view + ' HWPX 생성')
        result = api.export_document({'view': view, 'date': '2026-10-02'}, 'hwpx')
        if not result['success']:
            raise RuntimeError(result['message'])
        with zipfile.ZipFile(result['path']) as package:
            if package.testzip() or '내부 점검 메모' in package.read('Preview/PrvText.txt').decode('utf-8'):
                raise RuntimeError('배포 문서 검증 실패')
        outputs.append(result)
    progress('재시작 데이터 확인')
    restarted = DesktopApi(paths).bootstrap()
    if restarted['snapshot']['events'][0]['notes'] != '내부 점검 메모':
        raise RuntimeError('재시작 저장 검증 실패')
    report = {'success': True, 'version': VERSION, 'documents': outputs,
              'dataPath': str(paths.data), 'outputPath': str(paths.output)}
    import installation
    progress('사용자 설치 폴더에 실행 파일 준비')
    installed = installation.prepare_installation(paths)
    if installed:
        progress('바탕화면 바로가기 생성')
        installation.activate(paths, installed)
        import pythoncom
        pythoncom.CoInitialize()
        try:
            progress('바로가기 대상 실행 파일 확인')
            shortcut = installation.desktop_shortcut(paths)
            target = installation.shortcut_target(shortcut)
            if not target.samefile(installation.verified_launcher(paths)):
                diagnostic = {'actual': str(target), 'expected': str(installed),
                              'actualResolved': str(target.resolve()), 'expectedResolved': str(installed.resolve()),
                              'actualStat': list(target.stat()), 'expectedStat': list(installed.stat())}
                raise RuntimeError('바탕화면 바로가기 점검 실패: ' + json.dumps(diagnostic, ensure_ascii=False))
            report['shortcut'] = str(shortcut)
            report['installed'] = str(installed)
        finally:
            pythoncom.CoUninitialize()
    atomic_bytes(Path(root) / 'smoke-result.json', json.dumps(report, ensure_ascii=False).encode('utf-8'))
    progress('검사 완료')


def attach_ui(window, api, root, preserve=False):
    # This is a developer test of our own bridge, never a production data operation.
    def loaded():
        script = """(async () => {
          const api = window.pywebview.api;
          const info = await api.bootstrap();
          const result = {success: info.success && !info.readOnly, version:info.version,
            methods: Object.keys(api), title: document.title,
            scripts: [...document.scripts].map(s => s.src),
            csp: document.querySelector('[http-equiv="Content-Security-Policy"]').content};
          if (PRESERVE_EXISTING) {
            result.snapshot = info.snapshot;
            result.persistence = true;
          } else {
            const element = id => document.getElementById(id);
            const waitFor = async (check, description) => {
              const deadline = Date.now() + 15000;
              while (!check()) {
                if (Date.now() > deadline) throw new Error('UI 점검 시간 초과: ' + description);
                await new Promise(resolve => setTimeout(resolve, 30));
              }
            };
            await waitFor(() => !element('newBtn').disabled, '입력 준비');
            const form = element('eventForm');
            const fill = (name, value) => { form.elements.namedItem(name).value = value; };
            element('newBtn').click();
            fill('date', '2026-10-02'); fill('time', '09:00');
            fill('title', 'WebView2 연결 점검'); fill('notes', '연결 테스트 메모');
            fill('place', '대회의실'); fill('dept', '행정과');
            form.requestSubmit();
            await waitFor(() => !element('eventDialog').open && !element('saveEventBtn').disabled, '첫 일정 저장');
            // The quick-input path shares the same editor and advisory.
            element('quickInput').value = '2026/10/02 09:00 <중복 일정 점검>';
            element('quickBtn').click();
            form.requestSubmit();
            await waitFor(() => element('confirmDialog').open, '시작 시간 안내');
            const message = element('confirmMessage').textContent;
            const warned = message.includes('WebView2 연결 점검') && message.includes('대회의실') &&
              message.includes('행정과') && message.includes('2026-10-02 09:00') &&
              element('confirmYes').textContent === '이대로 저장';
            element('confirmNo').click();
            await waitFor(() => !element('saveEventBtn').disabled, '취소 후 다시 입력');
            const afterCancel = await api.bootstrap();
            const retained = element('eventDialog').open && form.elements.namedItem('title').value === '<중복 일정 점검>' &&
              afterCancel.snapshot.events.length === 1;
            form.requestSubmit();
            await waitFor(() => element('confirmDialog').open, 'Esc 취소 확인');
            element('confirmDialog').dispatchEvent(new Event('cancel', {cancelable:true}));
            await waitFor(() => !element('saveEventBtn').disabled, 'Esc 취소 후 다시 입력');
            const escapeRetained = !element('confirmDialog').open && element('eventDialog').open &&
              form.elements.namedItem('title').value === '<중복 일정 점검>';
            form.requestSubmit();
            await waitFor(() => element('confirmDialog').open, '다시 저장 확인');
            element('confirmYes').click();
            await waitFor(() => !element('eventDialog').open, '중복 허용 저장');
            const loaded = await api.bootstrap();
            result.conflictAdvisory = warned && retained && escapeRetained && loaded.snapshot.events.length === 2 &&
              loaded.snapshot.events.some(e => e.title === '<중복 일정 점검>' && e.time === '09:00');
            result.persistence = result.conflictAdvisory && loaded.snapshot.events.some(e => e.notes === '연결 테스트 메모');
          }
          result.success = result.success && result.persistence;
          const planned = await api.preview_document({view:'daily',date:'2026-10-02'});
          const expectedCount = PRESERVE_EXISTING ? info.snapshot.events.filter(e=>e.date==='2026-10-02' && e.status!=='cancelled').length : 2;
          result.documentPreview = planned.success && planned.plan.eventCount === expectedCount &&
            planned.plan.pages[0].rows[0].kind === 'daily-header' &&
            !!document.getElementById('includeAnnotation') &&
            !!document.querySelector('link[href="document.css"]');
          result.success = result.success && result.documentPreview;
          result.artwork = await Promise.all(ARTWORK_FILES.map(src => new Promise(resolve => {
            const image = new Image();
            image.onload = () => resolve(image.naturalWidth > 0 && image.naturalHeight > 0);
            image.onerror = () => resolve(false);
            image.src = src;
          })));
          result.success = result.success && result.artwork.every(Boolean);
          const ready = await api.ready();
          result.success = result.success && ready.success;
          const editing = await api.set_editing(false);
          result.success = result.success && editing.success && !!document.getElementById('newBtn');
          return result;
        })().catch(error => ({success:false,error:String(error)}))""".replace('ARTWORK_FILES', json.dumps(ASSET_FILES)).replace('PRESERVE_EXISTING', json.dumps(preserve))
        def done(result):
            result['executable'] = sys.executable
            if api._installed is not None:
                import installation
                import pythoncom
                pythoncom.CoInitialize()
                try:
                    active = installation.active_installation(api._paths)
                    shortcut = installation.shortcut_target(installation.desktop_shortcut(api._paths))
                    stable = installation.verified_launcher(api._paths)
                    result['installedLaunch'] = bool(active and active[1].samefile(sys.executable)
                                                    and shortcut.samefile(stable))
                    result['activationVerified'] = bool(active and shortcut.samefile(stable)
                        and active[0] == VERSION and active[1].read_bytes() == Path(sys.executable).read_bytes())
                    result['success'] = result['success'] and result['activationVerified']
                    result['shortcut'] = str(installation.desktop_shortcut(api._paths))
                    result['launcher'] = str(stable)
                finally:
                    pythoncom.CoUninitialize()
            atomic_bytes(Path(root) / 'ui-smoke-result.json', json.dumps(result, ensure_ascii=False).encode('utf-8'))
            api._allow_close = True
            window.destroy()
        window.evaluate_js(script, callback=done)
    window.events.loaded += loaded
