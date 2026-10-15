"""Regression cases from the 2.1.3 in-app upgrade failure."""
from pathlib import Path
import json
import logging
import tempfile
import unittest
from unittest.mock import Mock, patch
import main
import installation
import sys
from storage import atomic_copy
from app_info import ASSET_NAME, VERSION
from app_paths import AppPaths
from schedule_domain import empty_snapshot
from storage import SnapshotStore, encode


FIXTURE = json.dumps({'test_event': '보은군민의날', 'timestamp': 20260920}, ensure_ascii=False).encode()


class UpdateRegressionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.paths = AppPaths.isolated(self.directory.name)
        self.paths.ensure_data()

    def test_known_test_payload_is_archived_before_initialization(self):
        self.paths.database.write_bytes(FIXTURE)
        self.paths.database.with_suffix('.json.bak').write_bytes(FIXTURE)
        store = SnapshotStore(self.paths)
        self.assertEqual(store.load()['events'], [])
        self.assertEqual(store.recovery['kind'], 'legacySelfTest')
        self.assertEqual(list(self.paths.backups.glob('legacy-self-test-*'))[0].read_bytes(), FIXTURE)
        self.assertEqual(self.paths.database.with_suffix('.json.bak').read_bytes(), FIXTURE)
        self.assertEqual(SnapshotStore(self.paths).load(), store.load())

    def test_similar_or_mixed_unknown_payload_is_never_reset(self):
        for payload in (FIXTURE.replace(b'20260920', b'20260921'), FIXTURE[:-1] + b', "unknown": "preserve"}'):
            self.paths.database.write_bytes(payload)
            with self.assertRaises(ValueError):
                SnapshotStore(self.paths).load()
            self.assertEqual(self.paths.database.read_bytes(), payload)
        self.paths.database.write_bytes(FIXTURE)
        self.paths.database.with_suffix('.json.bak').write_bytes(b'unknown corruption')
        with self.assertRaises(ValueError):
            SnapshotStore(self.paths).load()
        self.assertEqual(self.paths.database.read_bytes(), FIXTURE)

    def test_valid_backup_has_priority_over_test_payload(self):
        snapshot = empty_snapshot()
        snapshot['revision'] = 7
        self.paths.database.write_bytes(FIXTURE)
        self.paths.database.with_suffix('.json.bak').write_bytes(encode(snapshot))
        self.assertEqual(SnapshotStore(self.paths).load(), snapshot)
        self.assertEqual(list(self.paths.backups.glob('corrupt-*'))[0].read_bytes(), FIXTURE)

    def test_failed_archive_never_replaces_primary(self):
        self.paths.database.write_bytes(FIXTURE)
        with patch('storage.atomic_copy', side_effect=PermissionError('locked backup')):
            with self.assertRaises(PermissionError):
                SnapshotStore(self.paths).load()
        self.assertEqual(self.paths.database.read_bytes(), FIXTURE)

    def test_watched_update_process_is_not_replaced_by_relay(self):
        token = 'b' * 32
        self.paths.database.write_bytes(b'unknown corruption')
        instance = Mock()
        instance.acquire.return_value = True
        target = main.installation.executable_for(self.paths)
        with patch('main.sys.argv', ['GunsuSchedule.exe', '--update-token', token]), \
             patch('main.sys.executable', str(target.with_name('GunsuSchedule.exe'))), \
             patch('main.AppPaths.current', return_value=self.paths), \
             patch('main.installation.SingleInstance', return_value=instance), \
             patch('main.RotatingFileHandler', return_value=logging.NullHandler()), \
             patch('main.logging.basicConfig'), \
             patch('main.installation.prepare_installation', return_value=target), \
             patch('main._launch_installed') as relay, \
             patch('webview.create_window') as window, self.assertLogs(level='ERROR'):
            main.main()
        relay.assert_not_called()
        window.assert_not_called()
        self.assertEqual((self.paths.updates / (token + '.failed')).read_bytes(), b'data-unreadable')
        self.assertFalse((self.paths.installation / 'active.json').exists())
        self.assertEqual(self.paths.database.read_bytes(), b'unknown corruption')
        instance.close.assert_called_once()

    def test_update_does_not_start_when_editing_or_data_unreadable(self):
        api = main.DesktopApi(self.paths)
        with patch('main.updater.prepare_update') as prepare:
            api._editing = True
            self.assertFalse(api.apply_update()['success'])
            api._editing = False
            self.paths.database.write_bytes(b'unknown corruption')
            self.assertFalse(api.apply_update()['success'])
        prepare.assert_not_called()

    def test_failed_update_disables_automatic_retry_until_manual_success(self):
        api = main.DesktopApi(self.paths)
        with patch('main.sys.frozen', True, create=True):
            self.assertTrue(api.ready()['automaticUpdate'])
            self.paths.updates.mkdir(parents=True)
            (self.paths.updates / 'last_failure.txt').write_text('startup failed')
            self.assertFalse(api.ready()['automaticUpdate'])
            api._update_token = 'b' * 32
            self.assertNotIn('updateWarning', api.bootstrap())
            self.assertFalse(api.ready()['automaticUpdate'])
            self.assertFalse((self.paths.updates / 'last_failure.txt').exists())

    def prepare_desktop_archive(self):
        self.paths.ensure_output()
        previous = self.paths.desktop / ASSET_NAME
        previous.write_bytes(b'MZoriginal-old-app')
        old_managed = self.paths.installation / 'versions' / '2.1.3' / ASSET_NAME
        atomic_copy(previous, old_managed)
        source = installation.executable_for(self.paths)
        atomic_copy(sys.executable, source)
        installation.activate(self.paths, source)
        return previous, old_managed, source

    def test_duplicate_desktop_exe_is_archived_and_korean_shortcut_remains(self):
        previous, old_managed, source = self.prepare_desktop_archive()
        previous.write_bytes(b'MZunrelated-user-app')
        self.assertFalse(installation.archive_legacy_desktop_entry(self.paths))
        previous.write_bytes(old_managed.read_bytes())
        self.assertTrue(installation.archive_legacy_desktop_entry(self.paths))
        self.assertFalse(previous.exists())
        self.assertEqual(list((self.paths.updates / 'desktop-entries').glob('*.exe'))[0].read_bytes(), old_managed.read_bytes())
        import pythoncom
        pythoncom.CoInitialize()
        try:
            self.assertTrue(installation.shortcut_target(self.paths.desktop / '군수실 일정 관리.lnk').samefile(source))
        finally:
            pythoncom.CoUninitialize()

    def test_same_version_desktop_copy_is_also_archived(self):
        previous, _, source = self.prepare_desktop_archive()
        atomic_copy(source, previous)
        self.assertTrue(installation.archive_legacy_desktop_entry(self.paths))
        self.assertFalse(previous.exists())

    def test_missing_shortcut_or_archive_failure_preserves_desktop_exe(self):
        previous, _, _ = self.prepare_desktop_archive()
        original = previous.read_bytes()
        with patch('installation.shortcut_target', side_effect=FileNotFoundError('missing link')):
            with self.assertRaises(FileNotFoundError):
                installation.archive_legacy_desktop_entry(self.paths)
        self.assertEqual(previous.read_bytes(), original)
        with patch('installation.atomic_copy', side_effect=PermissionError('archive folder locked')):
            with self.assertRaises(PermissionError):
                installation.archive_legacy_desktop_entry(self.paths)
        self.assertEqual(previous.read_bytes(), original)

    def test_locked_desktop_exe_retries_boundedly_and_keeps_recovery_copy(self):
        previous, _, _ = self.prepare_desktop_archive()
        original = previous.read_bytes()
        with patch.object(Path, 'unlink', side_effect=PermissionError('running old monitor')) as unlink, \
             patch('installation.time.sleep') as sleep, self.assertLogs(level='WARNING'):
            self.assertFalse(installation.archive_legacy_desktop_entry(self.paths))
        self.assertEqual(unlink.call_count, 30)
        self.assertEqual(sleep.call_count, 29)
        self.assertEqual(previous.read_bytes(), original)
        self.assertEqual(list((self.paths.updates / 'desktop-entries').glob('*.exe'))[0].read_bytes(), original)
        self.assertTrue(installation.archive_legacy_desktop_entry(self.paths))

    def test_changed_archive_during_retry_keeps_desktop_original(self):
        previous, _, _ = self.prepare_desktop_archive()
        original = previous.read_bytes()
        def change_backup(_):
            list((self.paths.updates / 'desktop-entries').glob('*.exe'))[0].write_bytes(b'changed')
        with patch.object(Path, 'unlink', side_effect=PermissionError('locked')), \
             patch('installation.time.sleep', side_effect=change_backup):
            with self.assertRaises(OSError):
                installation.archive_legacy_desktop_entry(self.paths)
        self.assertEqual(previous.read_bytes(), original)

    def test_optional_archive_helper_failure_never_opens_error_dialog_or_gui(self):
        with patch('main.sys.argv', ['app.exe', '--archive-desktop-entry']), \
             patch('main.AppPaths.current', return_value=self.paths), \
             patch('main.RotatingFileHandler', return_value=logging.NullHandler()), \
             patch('main.logging.basicConfig'), \
             patch('main.installation.archive_legacy_desktop_entry', side_effect=PermissionError('locked')), \
             patch('main._notify') as notify, patch('webview.create_window') as window, \
             self.assertLogs(level='WARNING'):
            main.main()
        notify.assert_not_called()
        window.assert_not_called()
