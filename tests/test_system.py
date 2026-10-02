import copy
import hashlib
import io
import json
import os
import sys
from pathlib import Path
import subprocess
import tempfile
import threading
import types
import unittest
from unittest.mock import Mock, patch
import urllib.error
import zipfile
import xml.etree.ElementTree as ET

from app_paths import AppPaths
from schedule_domain import empty_snapshot, event_record, parse_snapshot, validate_snapshot
from storage import SnapshotStore, atomic_bytes, atomic_copy, encode
from document_engine import HP, document_model, generate_document, validate_grid
from main import DesktopApi
import updater
import installation
import hwpx_generator
import native_workers
from hwp_validation import validate_hwp


def event(identifier='event-1', **fields):
    return event_record(dict(id=identifier, date='2026-10-02', time='09:00', title='주민 간담회',
                             attendee='gunsu', place='회의실', dept='행정과', notes='비공개 업무 메모', **fields))


def format_container(path, header=None, include_body=True):
    """A real CFB for format checks only: its body is not a rendered HWP fixture."""
    import pythoncom
    from win32com import storagecon
    mode = storagecon.STGM_READWRITE | storagecon.STGM_SHARE_EXCLUSIVE | storagecon.STGM_CREATE
    document = pythoncom.StgCreateDocfile(str(Path(path).resolve()), mode, 0)
    stream = document.CreateStream('FileHeader', mode, 0, 0)
    stream.Write(header if header is not None else b'HWP Document File'.ljust(32, b'\0') + bytes([0, 0, 0, 5]) + bytes(220))
    stream = None
    stream = document.CreateStream('DocInfo', mode, 0, 0)
    stream.Write(b'container test only')
    stream = None
    if include_body:
        body = document.CreateStorage('BodyText', mode, 0, 0)
        stream = body.CreateStream('Section0', mode, 0, 0)
        stream.Write(b'container test only')
        stream = None
        body = None
    document.Commit(0)
    document = None


@unittest.skipUnless(os.name == 'nt', 'Windows compound storage fixture')
class HwpFormatTests(unittest.TestCase):
    def test_hwp_header_and_required_streams(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'container.hwp'
            format_container(target)
            self.assertEqual(validate_hwp(target), target)
            format_container(target, include_body=False)
            with self.assertRaises(ValueError):
                validate_hwp(target)

    def test_other_ole_and_encrypted_files_are_rejected(self):
        valid_header = b'HWP Document File'.ljust(32, b'\0') + bytes([0, 0, 0, 5]) + bytes(220)
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'container.hwp'
            for header in (b'Other Compound Document'.ljust(256, b'\0'), valid_header[:36] + bytes([2]) + valid_header[37:]):
                format_container(target, header=header)
                with self.assertRaises(ValueError):
                    validate_hwp(target)


class DomainTests(unittest.TestCase):
    def test_legacy_migration(self):
        old = dict(id='old', date='2026-01-01', time='10:00', title='행사', attendee='important')
        result = parse_snapshot(json.dumps([old]))
        self.assertEqual(result['schemaVersion'], 3)
        self.assertEqual(result['events'][0]['priority'], 'important')
        self.assertEqual(result['events'][0]['attendee'], 'general')

    def test_invalid_events(self):
        for changes in [dict(date='2026-02-30'), dict(time='24:00'), dict(endTime='08:00'),
                        dict(id="x');alert(1)"), dict(title='bad\x00'), dict(status='unknown'),
                        dict(checklist=[dict(id='c', text='준비', done='yes')])]:
            raw = event()
            raw.update(changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                event_record(raw)

    def test_duplicate_active_and_trash(self):
        snapshot = empty_snapshot()
        snapshot['events'] = [event()]
        snapshot['deletedEvents'] = [event()]
        with self.assertRaises(ValueError):
            validate_snapshot(snapshot)

    def test_unknown_schema_and_nan(self):
        for raw in ['{"events":[],"schemaVersion":4}', '{"events":[],"revision":NaN}']:
            with self.assertRaises(ValueError):
                parse_snapshot(raw)

    def test_text_not_html(self):
        raw = event()
        raw['title'] = '<img src=x onerror=alert(1)> & "행사"'
        self.assertEqual(event_record(raw)['title'], raw['title'])


class IsolatedTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='schedule-test-')
        self.paths = AppPaths.isolated(self.temporary.name)
        self.store = SnapshotStore(self.paths)

    def tearDown(self):
        self.temporary.cleanup()

    def saved(self):
        snapshot = empty_snapshot()
        snapshot['events'] = [event()]
        return self.store.save(snapshot, 0)

    def test_save_restart_revision(self):
        saved = self.saved()
        self.assertEqual(saved['revision'], 1)
        self.assertEqual(SnapshotStore(self.paths).load(), saved)
        with self.assertRaises(ValueError):
            self.store.save(saved, 0)
        self.assertEqual(self.store.load(), saved)

    def test_recover_corrupt_primary_without_losing_backup(self):
        first = self.saved()
        second = copy.deepcopy(first)
        second['events'][0]['title'] = '다음 행사'
        self.store.save(second, 1)
        self.paths.database.write_bytes(b'{broken')
        fresh = SnapshotStore(self.paths)
        self.assertEqual(fresh.load()['events'][0]['title'], first['events'][0]['title'])
        self.assertTrue(fresh.recovery)
        self.assertEqual(list(self.paths.backups.glob('corrupt-*'))[0].read_bytes(), b'{broken')
        self.assertEqual(parse_snapshot(self.paths.database.with_suffix('.json.bak').read_text('utf-8'))['revision'], 1)

    def test_all_corrupt_readonly_and_valid_import(self):
        self.paths.database.write_bytes(b'broken')
        api = DesktopApi(self.paths)
        self.assertTrue(api.bootstrap()['readOnly'])
        original = self.paths.database.read_bytes()
        with self.assertLogs(level='ERROR'):
            self.assertFalse(api.save_persistent_data(encode(empty_snapshot()).decode(), 0)['success'])
        self.assertEqual(self.paths.database.read_bytes(), original)
        replacement = empty_snapshot()
        replacement['events'] = [event()]
        self.assertTrue(api.restore_data(encode(replacement).decode(), 0)['success'])
        self.assertFalse(DesktopApi(self.paths).bootstrap()['readOnly'])

    def test_future_schema_preserved_instead_of_restoring_old_backup(self):
        self.saved()
        future = dict(empty_snapshot(), schemaVersion=4)
        self.paths.database.with_suffix('.json.bak').write_bytes(encode(empty_snapshot()))
        self.paths.database.write_bytes(encode(future))
        before = self.paths.database.read_bytes()
        api = DesktopApi(self.paths)
        self.assertTrue(api.bootstrap()['readOnly'])
        self.assertEqual(self.paths.database.read_bytes(), before)
        with self.assertLogs(level='ERROR'):
            self.assertFalse(api.restore_data(encode(empty_snapshot()).decode(), 0)['success'])
        self.assertEqual(self.paths.database.read_bytes(), before)

    def test_failed_corruption_restore_stays_readonly(self):
        self.paths.database.write_bytes(b'corrupt')
        with patch('storage.atomic_bytes', side_effect=PermissionError('no write')):
            with self.assertRaises(PermissionError):
                self.store.import_snapshot(empty_snapshot(), 0)
        with self.assertRaises(ValueError):
            self.store.load()

    def test_streaming_copy_preserves_large_corrupt_file(self):
        source = self.paths.data / 'large-corrupt.json'
        source.write_bytes(b'corrupted' * 150000)
        destination = self.paths.backups / 'preserved.json'
        with patch.object(Path, 'read_bytes', side_effect=AssertionError('unbounded read')):
            atomic_copy(source, destination)
        self.assertEqual(source.read_bytes(), destination.read_bytes())

    def test_thousands_of_records_remain_valid_after_restart(self):
        snapshot = empty_snapshot()
        base = event()
        snapshot['events'] = [dict(base, id=f'event-{i}', title=f'행사 {i}') for i in range(3000)]
        self.store.save(snapshot, 0)
        fresh = SnapshotStore(self.paths).load()
        self.assertEqual(len(fresh['events']), 3000)
        self.assertEqual(fresh['events'][-1]['title'], '행사 2999')

    def test_notes_fields_and_checklist_restore(self):
        row = event()
        row.update(participants='내빈', contact='행정과 담당', preparation='인사말 준비',
                   checklist=[dict(id='check', text='자료 준비', done=True)])
        snapshot = empty_snapshot()
        snapshot['deletedEvents'] = [dict(row, deletedAt='2026-10-02')]
        saved = self.store.save(snapshot, 0)
        fresh = SnapshotStore(self.paths).load()
        self.assertEqual(fresh, saved)
        self.assertTrue(fresh['deletedEvents'][0]['checklist'][0]['done'])

    def test_atomic_failure_preserves_current(self):
        current = self.saved()
        old_bytes = self.paths.database.read_bytes()
        import storage
        replace = storage.os.replace
        def fail_primary(source, target):
            if Path(target) == self.paths.database:
                raise PermissionError('simulated file lock')
            return replace(source, target)
        with patch('storage.os.replace', side_effect=fail_primary), self.assertRaises(PermissionError):
            self.store.save(current, 1)
        self.assertEqual(self.store.load()['revision'], 1)
        self.assertEqual(self.paths.database.read_bytes(), old_bytes)
        self.assertFalse(list(self.paths.data.glob('.schedule_data.json.*')))

    def test_concurrent_revision_prevents_lost_update(self):
        current = self.saved()
        barrier = threading.Barrier(2)
        results = []
        def save():
            barrier.wait()
            try:
                self.store.save(current, 1)
                results.append(True)
            except ValueError:
                results.append(False)
        threads = [threading.Thread(target=save) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(sorted(results), [False, True])

    def test_backup_retention_and_path_traversal(self):
        snapshot = empty_snapshot()
        for revision in range(65):
            snapshot = self.store.save(snapshot, revision)
        self.assertEqual(len(self.store.list_backups()), 60)
        self.assertEqual(len(list(self.paths.backups.glob('snapshot-*.json'))), 60)
        for bad in ['../schedule_data.json', 'snapshot-../../file', 'C:\\secret.json']:
            with self.assertRaises(ValueError):
                self.store.read_backup(bad)

    def test_output_tree_manual_and_restart(self):
        api = DesktopApi(self.paths)
        self.assertEqual(Path(api.bootstrap()['outputPath']), self.paths.output)
        for folder in ['일일일정', '주간일정', '월간일정', '데이터백업']:
            self.assertTrue((self.paths.output / folder).is_dir())
        manual = (self.paths.output / '먼저_읽어주세요.html').read_text('utf-8')
        self.assertNotIn('{{', manual)
        self.assertIn('처음사용_5분안내.html', manual)
        self.assertTrue((self.paths.output / '처음사용_5분안내.html').is_file())
        current = empty_snapshot()
        current['events'] = [event()]
        self.assertTrue(api.save_persistent_data(encode(current).decode(), 0)['success'])
        self.assertEqual(DesktopApi(self.paths).bootstrap()['snapshot']['events'][0]['notes'], '비공개 업무 메모')

    def test_csv_injection_and_private_notes(self):
        snapshot = empty_snapshot()
        row = event()
        row['title'] = '=HYPERLINK("malicious")'
        snapshot['events'] = [row]
        self.store.save(snapshot, 0)
        api = DesktopApi(self.paths)
        with patch.object(api, '_show_file'):
            result = api.export_csv()
        self.assertTrue(result['success'])
        content = Path(result['path']).read_text('utf-8-sig')
        self.assertIn("'=HYPERLINK", content)
        self.assertNotIn('비공개 업무 메모', content)

    def test_each_document_format_and_notes(self):
        self.saved()
        snapshot = self.store.load()
        for view in ['daily', 'weekly', 'monthly']:
            for notes in [False, True]:
                with self.subTest(view=view, notes=notes):
                    target = self.paths.output / f'{view}-{notes}.hwpx'
                    result = generate_document(document_model(snapshot, dict(view=view, date='2026-10-02', includeNotes=notes)), target)
                    self.assertGreater(result['pages'], 0)
                    with zipfile.ZipFile(target) as package:
                        self.assertIsNone(package.testzip())
                        self.assertEqual(package.infolist()[0].filename, 'mimetype')
                        self.assertEqual(package.infolist()[0].compress_type, zipfile.ZIP_STORED)
                        self.assertNotIn('Preview/PrvImage.png', package.namelist())
                        root = ET.fromstring(package.read('Contents/section0.xml'))
                        for run in root.iter(HP + 'run'):
                            self.assertIsNone(run.find(HP + 'lineBreak'))
                        parents = {child: parent for parent in root.iter() for child in parent}
                        for line_break in root.iter(HP + 'lineBreak'):
                            self.assertEqual(parents[line_break].tag, HP + 't')
                        for table in root.iter(HP + 'tbl'):
                            validate_grid(table)
                        public = package.read('Preview/PrvText.txt').decode()
                        self.assertEqual('비공개 업무 메모' in public, notes)
                        self.assertIn('2026', public)

    def test_long_notes_paginate_and_preserve_all_lines(self):
        snapshot = empty_snapshot()
        row = event()
        row['notes'] = '\n'.join(f'준비사항 {i:03}' for i in range(500))
        snapshot['events'] = [row]
        for view in ['weekly', 'monthly']:
            target = self.paths.output / f'long-{view}.hwpx'
            result = generate_document(document_model(snapshot, dict(view=view, date='2026-10-02', includeNotes=True)), target)
            self.assertGreater(result['pages'], 2)
            with zipfile.ZipFile(target) as package:
                preview = package.read('Preview/PrvText.txt').decode()
                self.assertIn('준비사항 000', preview)
                self.assertIn('준비사항 499', preview)

    def test_unique_output_and_hwp_failure_fallback(self):
        self.saved()
        api = DesktopApi(self.paths)
        with patch.object(api, '_show_file'), patch('main.convert_bounded', return_value=(False, '한글 미설치')):
            first = api.export_document(dict(view='daily', date='2026-10-02'))
            second = api.export_document(dict(view='daily', date='2026-10-02'), 'hwpx')
        self.assertFalse(first['success'])
        self.assertTrue(first['fallback'])
        self.assertEqual(first['requestedFormat'], 'hwp')
        self.assertEqual(first['actualFormat'], 'hwpx')
        self.assertTrue(second['success'])
        self.assertNotEqual(first['path'], second['path'])
        self.assertEqual(Path(first['path']).suffix, '.hwpx')

    def test_helper_start_failure_still_returns_saved_hwpx(self):
        self.saved()
        api = DesktopApi(self.paths)
        with patch.object(api, '_show_file'), patch('main.convert_bounded', side_effect=OSError('worker unavailable')), self.assertLogs(level='ERROR'):
            result = api.export_document(dict(view='daily', date='2026-10-02'), 'hwp')
        self.assertFalse(result['success'])
        self.assertTrue(result['fallback'])
        self.assertTrue(Path(result['path']).is_file())

    def test_worker_success_cannot_pass_renamed_hwpx_as_hwp(self):
        self.saved()
        api = DesktopApi(self.paths)
        def incorrect_conversion(source, target):
            atomic_copy(source, target)
            return True, str(target)
        with patch.object(api, '_show_file'), patch('main.convert_bounded', side_effect=incorrect_conversion), self.assertLogs(level='ERROR'):
            result = api.export_document(dict(view='weekly', date='2026-10-02'))
        self.assertFalse(result['success'])
        self.assertTrue(result['fallback'])
        self.assertTrue(Path(result['path']).is_file())
        self.assertFalse(Path(result['path']).with_suffix('.hwp').exists())

    @unittest.skipUnless(os.name == 'nt', 'Windows compound storage fixture')
    def test_default_exports_are_checked_hwp_for_all_views(self):
        self.saved()
        api = DesktopApi(self.paths)
        fixture = self.paths.data / 'format-fixture.hwp'
        format_container(fixture)
        def convert(source, target):
            atomic_copy(fixture, target)
            return True, str(target)
        with patch.object(api, '_show_file'), patch('main.convert_bounded', side_effect=convert):
            for view in ('daily', 'weekly', 'monthly'):
                result = api.export_document(dict(view=view, date='2026-10-02'))
                self.assertTrue(result['success'])
                self.assertEqual(result['actualFormat'], 'hwp')
                self.assertFalse(result['fallback'])
                self.assertTrue(Path(result['path']).is_file())
                self.assertFalse(Path(result['path']).with_suffix('.hwpx').exists())

    def test_source_exception_keeps_existing_document(self):
        target = self.paths.output / 'existing.hwpx'
        atomic_bytes(target, b'previous file')
        with patch('document_engine.get_template_path', return_value='missing-template'), self.assertRaises(FileNotFoundError):
            generate_document(document_model(empty_snapshot(), dict(view='daily', date='2026-10-02')), target)
        self.assertEqual(target.read_bytes(), b'previous file')


class UpdateTests(unittest.TestCase):
    def test_release_missing_digest_cannot_apply(self):
        release = dict(tag_name='v2.0.1', body='안내', assets=[dict(name='GunsuSchedule.exe', state='uploaded',
            browser_download_url='https://github.com/dpqksr5501/schedule-doc-system/releases/download/v2.0.1/GunsuSchedule.exe', size=2048)])
        with patch('updater.urllib.request.urlopen', return_value=io.BytesIO(json.dumps(release).encode())):
            version, notes, asset = updater._fetch_release()
        self.assertIsNone(asset)
        self.assertEqual(version, '2.0.1')

    def test_release_untrusted_source_rejected(self):
        release = dict(tag_name='v2.0.1', assets=[dict(name='GunsuSchedule.exe', state='uploaded',
            browser_download_url='https://evil.example/GunsuSchedule.exe', size=2048, digest='sha256:' + '0'*64)])
        with patch('updater.urllib.request.urlopen', return_value=io.BytesIO(json.dumps(release).encode())):
            with self.assertRaises(ValueError):
                updater._fetch_release()

    def test_failed_new_process_attempts_previous_version(self):
        with tempfile.TemporaryDirectory() as root:
            paths = AppPaths.isolated(root)
            token = 'a'*32
            target = paths.installation / 'versions' / '2.0.1' / 'GunsuSchedule.exe'
            previous = paths.installation / 'versions' / '2.0.0' / 'GunsuSchedule.exe'
            atomic_bytes(target, b'MZnew')
            atomic_bytes(previous, b'MZold')
            plan = dict(version='2.0.1', target=str(target), previous=str(previous), size=5,
                        digest='sha256:' + hashlib.sha256(b'MZnew').hexdigest())
            atomic_bytes(paths.updates / (token + '.json'), json.dumps(plan).encode())
            process = Mock()
            process.poll.return_value = 1
            with patch('updater.sys.executable', str(previous)), patch('updater.subprocess.Popen', return_value=process) as popen:
                self.assertEqual(updater.monitor_update(paths, token), 1)
            self.assertTrue(Path(popen.call_args_list[-1].args[0][0]).samefile(previous))
            self.assertTrue((paths.updates / 'last_failure.txt').exists())
    def test_versions(self):
        for newer, older, expected in [('v2.10.0','2.9.9',True), ('2.0.0+build.2','2.0.0',False),
                                       ('2.0.1-rc.1','2.0.0',False), ('02.0.0','1.0.0',False),
                                       ('garbage','1.0.0',False), ('2.0.0','2.0.1',False)]:
            self.assertEqual(updater._is_newer_version(newer, older), expected)

    def test_offline_returns_failure_without_blocking_local_work(self):
        with patch('updater._fetch_release', side_effect=urllib.error.URLError('offline')):
            result = updater.check_for_updates()
        self.assertFalse(result['success'])
        self.assertIn('일정 관리', result['message'])

    def test_redirect_rejects_untrusted_host(self):
        for url in ['http://github.com/file', 'https://evil.example/file', 'https://github.com@evil.example/file']:
            with self.assertRaises(ValueError):
                updater.SafeRedirect().redirect_request(None, None, 302, '', {}, url)

    def test_download_validates_hash_and_size_and_keeps_old(self):
        payload = b'MZ' + b'body' * 1000
        asset = dict(browser_download_url='https://github.com/x/y/file', size=len(payload),
                     digest='sha256:' + hashlib.sha256(payload).hexdigest())
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / 'app.exe'
            target.write_bytes(b'old')
            for bad in ['sha256:' + '0' * 64, asset['digest']]:
                item = {**asset, 'digest': bad}
                opener = Mock()
                opener.open.return_value = io.BytesIO(payload)
                with patch('updater.urllib.request.build_opener', return_value=opener):
                    if bad != asset['digest']:
                        with self.assertRaises(ValueError):
                            updater._download(item, target)
                        self.assertEqual(target.read_bytes(), b'old')
                    else:
                        updater._download(item, target)
                        self.assertEqual(target.read_bytes(), payload)
            self.assertFalse(target.with_suffix('.download').exists())


@unittest.skipUnless(os.name == 'nt', 'Windows Unicode shortcut integration')
class InstallationTests(unittest.TestCase):
    def test_unicode_shortcut_is_readable_and_preserves_previous_on_failure(self):
        import pythoncom
        with tempfile.TemporaryDirectory() as directory:
            paths = AppPaths.isolated(Path(directory) / '한글 경로')
            paths.ensure_output()
            executable = paths.installation / 'versions' / '테스트 버전' / '일정 관리.exe'
            atomic_copy(sys.executable, executable)
            installation.activate(paths, executable)
            shortcut = paths.desktop / '군수실 일정 관리.lnk'
            pythoncom.CoInitialize()
            try:
                self.assertTrue(installation.shortcut_target(shortcut).samefile(executable))
            finally:
                pythoncom.CoUninitialize()
            active = paths.installation / 'active.json'
            original_record, original_link = active.read_bytes(), shortcut.read_bytes()
            with patch('installation.shortcut_target', side_effect=OSError('invalid link')):
                with self.assertRaises(OSError):
                    installation.activate(paths, executable)
            self.assertEqual(active.read_bytes(), original_record)
            self.assertEqual(shortcut.read_bytes(), original_link)
            self.assertFalse(list(paths.desktop.glob('.GunsuSchedule-*.lnk')))


class ComTests(unittest.TestCase):
    @unittest.skipUnless(os.name == 'nt', 'Windows compound storage fixture')
    def test_missing_security_module_uses_normal_approval_and_hwp_save(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'target.hwp'
            format_container(target)
            pythoncom = types.ModuleType('pythoncom')
            pythoncom.COINIT_APARTMENTTHREADED = 2
            pythoncom.CoInitializeEx = Mock()
            pythoncom.CoUninitialize = Mock()
            hwp = Mock()
            hwp.RegisterModule.return_value = False
            hwp.Open.return_value = True
            hwp.SaveAs.return_value = True
            client = types.ModuleType('win32com.client')
            client.DispatchEx = Mock(return_value=hwp)
            win32com = types.ModuleType('win32com')
            win32com.client = client
            with patch.dict('sys.modules', {'pythoncom': pythoncom, 'win32com': win32com, 'win32com.client': client}):
                ok, message = hwpx_generator.convert_hwpx_to_hwp('source.hwpx', target)
            self.assertTrue(ok)
            self.assertTrue(hwp.XHwpWindows.Item(0).Visible)
            hwp.Open.assert_called_once()
            hwp.SaveAs.assert_called_once_with(str(target.resolve()), 'HWP')
            hwp.Quit.assert_called_once()
            pythoncom.CoUninitialize.assert_called_once()

    def test_com_failure_always_cleans_up(self):
        pythoncom = types.ModuleType('pythoncom')
        pythoncom.COINIT_APARTMENTTHREADED = 2
        pythoncom.CoInitializeEx = Mock()
        pythoncom.CoUninitialize = Mock()
        hwp = Mock()
        hwp.RegisterModule.return_value = True
        hwp.Open.return_value = False
        client = types.ModuleType('win32com.client')
        client.DispatchEx = Mock(return_value=hwp)
        win32com = types.ModuleType('win32com')
        win32com.client = client
        with patch.dict('sys.modules', {'pythoncom': pythoncom, 'win32com': win32com, 'win32com.client': client}), self.assertLogs(level='ERROR'):
            ok, message = hwpx_generator.convert_hwpx_to_hwp('source.hwpx', 'target.hwp')
        self.assertFalse(ok)
        hwp.Quit.assert_called_once()
        pythoncom.CoUninitialize.assert_called_once()

    def test_bounded_conversion_kills_only_own_worker(self):
        process = Mock()
        process.wait.side_effect = [subprocess.TimeoutExpired('worker', 1), 0]
        with patch('native_workers.subprocess.Popen', return_value=process):
            ok, message = native_workers.convert_bounded('file.hwpx', 'file.hwp', timeout=1)
        self.assertFalse(ok)
        process.kill.assert_called_once()
        self.assertIn('대기 시간', message)


class BridgeTests(unittest.TestCase):
    def test_guard_rejects_attribute_traversal_and_callback_injection(self):
        from bridge_security import guard_dispatch
        original = Mock()
        window = types.SimpleNamespace(_functions={'bootstrap': Mock()}, _callbacks={})
        guard = guard_dispatch(original)
        with self.assertLogs(level='WARNING'):
            guard(window, '_store.save', [], '123')
            guard(window, 'bootstrap.__func__.__globals__.clear', [], '123')
            guard(window, 'bootstrap', [], "x\"];alert(1);//")
        original.assert_not_called()
        guard(window, 'bootstrap', [], '123')
        original.assert_called_once()
