"""Isolated install/upgrade failure tests; never touch the user's desktop."""
from pathlib import Path
import hashlib
import json
import logging
import os
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
from app_info import VERSION, PUBLIC_EXE_NAME, INSTALLED_EXE_NAME, ASSET_NAME
from app_paths import AppPaths
import installation
import main
from launcher_fixture import use_launcher_fixture
from launch_registry import launcher_path


class InstallationFlowTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.paths = AppPaths.isolated(Path(self.directory.name) / '한글 사용자 경로')
        self.paths.ensure_output()
        use_launcher_fixture(self, self.paths)
        self.source = Path(self.directory.name) / '새 배포' / PUBLIC_EXE_NAME
        self.source.parent.mkdir()
        self.source.write_bytes(b'MZnew-release')

    def active(self, version='2.1.3', name=ASSET_NAME):
        executable = self.paths.installation / 'versions' / version / name
        executable.parent.mkdir(parents=True, exist_ok=True)
        executable.write_bytes(b'MZprevious-release')
        record = self.paths.installation / 'active.json'
        record.write_text(json.dumps(dict(version=version, executable=str(executable),
                                         sha256=hashlib.sha256(executable.read_bytes()).hexdigest())), 'utf-8')
        return executable, record

    def prepare(self):
        with patch('installation.sys.frozen', True, create=True), patch('installation.sys.executable', str(self.source)):
            return installation.prepare_installation(self.paths)

    def test_new_install_and_repeat_use_verified_korean_target(self):
        target = self.prepare()
        self.assertEqual(target.name, INSTALLED_EXE_NAME)
        self.assertEqual(target.read_bytes(), self.source.read_bytes())
        with patch('installation.atomic_copy') as copy:
            self.assertEqual(self.prepare(), target)
        copy.assert_not_called()
        self.assertFalse((self.paths.installation / 'active.json').exists())

    def test_preparing_upgrade_preserves_old_shortcut_data_and_outputs(self):
        previous, record = self.active()
        old_record = record.read_bytes()
        shortcut = self.paths.desktop / '군수실 일정 관리.lnk'
        shortcut.write_bytes(b'old-shortcut')
        self.paths.ensure_data()
        self.paths.database.write_bytes(b'original-schedules')
        document = self.paths.output / '기존 출력 문서.hwpx'
        document.write_bytes(b'old-document')
        self.prepare()
        self.assertEqual(record.read_bytes(), old_record)
        self.assertEqual(shortcut.read_bytes(), b'old-shortcut')
        self.assertEqual(previous.read_bytes(), b'MZprevious-release')
        self.assertEqual(self.paths.database.read_bytes(), b'original-schedules')
        self.assertEqual(document.read_bytes(), b'old-document')

    def test_corrupt_copy_and_permission_failure_preserve_installed_file(self):
        target, record = self.active(VERSION, INSTALLED_EXE_NAME)
        old_file, old_record = target.read_bytes(), record.read_bytes()
        def corrupt(source, destination):
            Path(destination).write_bytes(b'MZcorrupt-copy')
        for action in (dict(side_effect=corrupt), dict(side_effect=PermissionError('locked folder'))):
            with self.subTest(action=action), patch('installation.atomic_copy', **action):
                with self.assertRaises(OSError):
                    self.prepare()
            self.assertEqual(target.read_bytes(), old_file)
            self.assertEqual(record.read_bytes(), old_record)
            self.assertFalse(list(target.parent.glob('.install-*')))

    def test_older_launcher_uses_newer_install_without_downgrade(self):
        target, record = self.active('99.0.0', INSTALLED_EXE_NAME)
        original = record.read_bytes()
        with patch('installation.atomic_copy') as copy:
            self.assertEqual(self.prepare(), target.resolve())
        copy.assert_not_called()
        with self.assertRaises(ValueError):
            installation.activate(self.paths, self.source)
        self.assertEqual(record.read_bytes(), original)

    def test_untrusted_active_path_is_never_launched(self):
        _, record = self.active('99.0.0')
        record.write_text(json.dumps(dict(version='99.0.0', executable=str(self.source))), 'utf-8')
        with self.assertLogs(level='WARNING'):
            self.assertEqual(self.prepare(), installation.executable_for(self.paths))
        record.write_text('{broken json', 'utf-8')
        with self.assertLogs(level='WARNING'):
            self.assertEqual(self.prepare(), installation.executable_for(self.paths))

    def test_readonly_data_does_not_activate_new_version(self):
        api = main.DesktopApi(self.paths)
        api._installed = self.source
        api._store.load = Mock(side_effect=ValueError('unreadable schedules'))
        with patch('main.installation.activate') as activate, self.assertLogs(level='ERROR'):
            self.assertFalse(api.ready()['success'])
        activate.assert_not_called()

    def test_launcher_releases_mutex_and_exits_before_loading_data(self):
        target = installation.executable_for(self.paths)
        instance = Mock()
        instance.acquire.return_value = True
        def launched(path, token, probe, preserve):
            instance.close.assert_called()
            self.assertEqual(path, target)
            self.assertFalse(preserve)
        with patch('main.sys.argv', [str(self.source)]), patch('main.sys.executable', str(self.source)), \
             patch('main.AppPaths.current', return_value=self.paths), \
             patch('main.installation.SingleInstance', return_value=instance), \
             patch('main.RotatingFileHandler', return_value=logging.NullHandler()), \
             patch('main.logging.basicConfig'), \
             patch('main.installation.prepare_installation', return_value=target), \
             patch('main._launch_installed', side_effect=launched) as launch, \
             patch('main.DesktopApi') as api:
            main.main()
        launch.assert_called_once()
        api.assert_not_called()

    def test_relaunch_preserves_update_token_and_uses_independent_environment(self):
        token = 'b' * 32
        with patch('subprocess.Popen') as popen:
            main._launch_installed(self.source, token)
        self.assertEqual(popen.call_args.args[0], [str(self.source), '--update-token', token])
        self.assertEqual(popen.call_args.kwargs['env']['PYINSTALLER_RESET_ENVIRONMENT'], '1')
        self.assertNotIn('shell', popen.call_args.kwargs)

    def test_editing_or_busy_window_is_not_forcibly_closed(self):
        api = main.DesktopApi(self.paths)
        with patch('main._notify'):
            api._editing = True
            self.assertFalse(api._closing())
            api._editing, api._busy = False, True
            self.assertFalse(api._closing())

    def test_windows_file_lock_retry_is_bounded(self):
        from storage import atomic_replace
        locked = PermissionError('temporary sharing lock')
        locked.winerror = 32
        with patch('storage.os.replace', side_effect=[locked, None]) as replace, patch('storage.time.sleep') as sleep:
            atomic_replace('candidate', 'installed')
        self.assertEqual(replace.call_count, 2)
        sleep.assert_called_once_with(.05)
        with patch('storage.os.replace', side_effect=locked) as replace, patch('storage.time.sleep') as sleep:
            with self.assertRaises(PermissionError):
                atomic_replace('candidate', 'installed')
        self.assertEqual(replace.call_count, 5)
        self.assertEqual(sleep.call_count, 4)
        with patch('storage.os.replace', side_effect=PermissionError('denied')), patch('storage.time.sleep') as sleep:
            with self.assertRaises(PermissionError):
                atomic_replace('candidate', 'installed')
        sleep.assert_not_called()


@unittest.skipUnless(os.name == 'nt', 'Windows shortcut transaction')
class ShortcutTransactionTests(unittest.TestCase):
    def test_shortcut_write_failure_rolls_back_active_record(self):
        import pythoncom
        from storage import atomic_bytes, atomic_copy
        with tempfile.TemporaryDirectory() as directory:
            paths = AppPaths.isolated(directory)
            paths.ensure_output()
            use_launcher_fixture(self, paths)
            executable = installation.executable_for(paths)
            atomic_copy(sys.executable, executable)
            installation.activate(paths, executable)
            record = paths.installation / 'active.json'
            shortcut = paths.desktop / '군수실 일정 관리.lnk'
            # Exercise first-time migration failure, not the steady-state pointer-only update.
            import desktop_entries
            desktop_entries.write_shortcut(shortcut, executable)
            old_record, old_link = record.read_bytes(), shortcut.read_bytes()
            def fail_link(path, content):
                if Path(path) == shortcut:
                    raise PermissionError('desktop is locked')
                return atomic_bytes(path, content)
            with patch('installation.atomic_bytes', side_effect=fail_link), self.assertRaises(PermissionError):
                installation.activate(paths, executable)
            self.assertEqual(record.read_bytes(), old_record)
            self.assertEqual(shortcut.read_bytes(), old_link)
            self.assertFalse(list(paths.desktop.glob('.GunsuSchedule-*.lnk')))
            pythoncom.CoInitialize()
            try:
                self.assertTrue(installation.shortcut_target(shortcut).samefile(executable))
            finally:
                pythoncom.CoUninitialize()
