"""Fixed launcher contract and renamed desktop migration regressions."""
from pathlib import Path
import hashlib
import json
import tempfile
import unittest
from unittest.mock import Mock, patch
from app_info import VERSION
from app_paths import AppPaths
from storage import atomic_bytes, atomic_copy
from launcher_fixture import use_launcher_fixture
from launch_registry import launcher_path, launch_choices, digest
import desktop_entries
import installation
import launcher_main
import updater


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.paths = AppPaths.isolated(Path(self.directory.name) / '사용자 이름')
        self.paths.ensure_output()
        use_launcher_fixture(self, self.paths)

    def executable(self, version, content):
        target = installation.executable_for(self.paths, version)
        atomic_bytes(target, content)
        return dict(version=version, executable=str(target), sha256=digest(target))

    def activate_current(self):
        record = self.executable(VERSION, b'MZ-current-app')
        installation.activate(self.paths, record['executable'])
        return record

    def test_launcher_accepts_future_versions_without_being_rebuilt(self):
        record = self.executable('99.7.3', b'MZ-future-app')
        atomic_bytes(self.paths.installation / 'active.json', json.dumps(record).encode())
        self.assertEqual(launch_choices(self.paths)[0][0], '99.7.3')
        with patch('launcher_main.subprocess.Popen', return_value=Mock()) as popen:
            self.assertEqual(launcher_main.run(self.paths), 0)
        self.assertEqual(Path(popen.call_args.args[0][0]), Path(record['executable']))

    def test_corrupt_active_file_falls_back_to_verified_previous(self):
        old = self.executable('2.1.3', b'MZ-known-old')
        current = self.executable(VERSION, b'MZ-known-new')
        current['previous'] = old
        atomic_bytes(self.paths.installation / 'active.json', json.dumps(current).encode())
        Path(current['executable']).write_bytes(b'MZ-corrupted-new')
        self.assertEqual(launch_choices(self.paths), [('2.1.3', Path(old['executable']).resolve())])
        with patch('launcher_main.subprocess.Popen', return_value=Mock()):
            self.assertEqual(launcher_main.run(self.paths), 0)
        self.assertTrue((self.paths.updates / 'last_failure.txt').exists())

    def test_external_path_or_bad_fallback_hash_cannot_be_launched(self):
        current = self.executable(VERSION, b'MZ-current')
        outside = self.paths.desktop / '외부.exe'
        outside.write_bytes(b'MZ-current')
        current['executable'] = str(outside)
        current['previous'] = self.executable('2.1.3', b'MZ-old')
        current['previous']['sha256'] = '0' * 64
        atomic_bytes(self.paths.installation / 'active.json', json.dumps(current).encode())
        with self.assertRaises(ValueError):
            launch_choices(self.paths)

    def test_damaged_pointer_uses_verified_last_good_record(self):
        self.activate_current()
        installation.activate(self.paths)
        (self.paths.installation / 'active.json').write_bytes(b'{damaged')
        self.assertEqual(launch_choices(self.paths)[0][0], VERSION)
        installation.activate(self.paths)
        self.assertEqual(json.loads((self.paths.installation / 'active.json').read_text('utf-8'))['version'], VERSION)

    def test_newer_launcher_protocol_is_not_downgraded(self):
        self.activate_current()
        manifest = launcher_path(self.paths).with_name('manifest.json')
        record = json.loads(manifest.read_text('utf-8'))
        record['protocol'] = 99
        manifest.write_text(json.dumps(record), 'utf-8')
        with self.assertRaises(RuntimeError):
            installation.ensure_launcher(self.paths)
        self.assertEqual(json.loads(manifest.read_text('utf-8'))['protocol'], 99)

    def test_valid_protocol_launcher_and_shortcut_are_not_rewritten(self):
        self.activate_current()
        stable = launcher_path(self.paths)
        shortcut = installation.desktop_shortcut(self.paths)
        original_launcher, original_link = stable.read_bytes(), shortcut.read_bytes()
        with patch('installation.launcher_resource') as resource, \
             patch('desktop_entries.write_shortcut') as write:
            installation.activate(self.paths)
        resource.assert_not_called()
        write.assert_not_called()
        self.assertEqual(stable.read_bytes(), original_launcher)
        self.assertEqual(shortcut.read_bytes(), original_link)

    def test_renamed_exes_and_shortcuts_converge_to_one_preserved_label(self):
        old = self.executable('2.1.3', b'MZ-old-release')
        entries = []
        for name in ('GunsuSchedule.exe', '군수실 일정 관리.exe', '아버지 일정 (최종).exe'):
            path = self.paths.desktop / name
            atomic_copy(old['executable'], path)
            entries.append(path)
        labels = ['아버지 일정.lnk', '업무용 바로가기.lnk']
        for index, name in enumerate(labels):
            desktop_entries.write_shortcut(self.paths.desktop / name, entries[index])
        unrelated = self.paths.desktop / '관계없는 프로그램.exe'
        unrelated.write_bytes(b'MZ-unrelated')
        other_link = self.paths.desktop / '다른 업무.lnk'
        desktop_entries.write_shortcut(other_link, unrelated)
        unrelated_bytes, link_bytes = unrelated.read_bytes(), other_link.read_bytes()
        self.activate_current()
        selected = installation.desktop_shortcut(self.paths)
        self.assertIn(selected.name, labels)
        self.assertTrue(installation.archive_legacy_desktop_entry(self.paths))
        self.assertFalse(any(path.exists() for path in entries))
        self.assertEqual(unrelated.read_bytes(), unrelated_bytes)
        self.assertEqual(other_link.read_bytes(), link_bytes)
        owned = desktop_entries.owned_shortcuts(self.paths, desktop_entries.known_files(self.paths))
        self.assertEqual(owned, [selected])
        self.assertTrue(installation.shortcut_target(selected).samefile(launcher_path(self.paths)))

    def test_renaming_fixed_shortcut_does_not_create_another_icon(self):
        self.activate_current()
        previous = installation.desktop_shortcut(self.paths)
        renamed = self.paths.desktop / '내가 정한 이름.lnk'
        previous.rename(renamed)
        original = renamed.read_bytes()
        installation.activate(self.paths)
        self.assertEqual(installation.desktop_shortcut(self.paths), renamed)
        self.assertEqual(renamed.read_bytes(), original)
        self.assertEqual(list(self.paths.desktop.glob('*.lnk')), [renamed])

    def test_unrelated_korean_shortcut_is_never_overwritten(self):
        unrelated = self.paths.desktop / 'other.exe'
        unrelated.write_bytes(b'MZ-not-our-app')
        reserved = self.paths.desktop / desktop_entries.DEFAULT_SHORTCUT
        desktop_entries.write_shortcut(reserved, unrelated)
        original = reserved.read_bytes()
        self.activate_current()
        self.assertNotEqual(installation.desktop_shortcut(self.paths), reserved)
        self.assertEqual(reserved.read_bytes(), original)

    def test_unrelated_network_shortcut_is_not_probed(self):
        link = self.paths.desktop / '네트워크 업무.lnk'
        link.write_bytes(b'unit shortcut')
        with patch('desktop_entries.read_shortcut', return_value=(Path(r'\\example.invalid\private\tool.exe'), '')), \
             patch('desktop_entries.owned_file') as inspect:
            self.assertEqual(desktop_entries.owned_shortcuts(self.paths, {}), [])
        inspect.assert_not_called()

    def test_successful_activation_keeps_previous_for_recovery(self):
        old = self.executable('2.1.3', b'MZ-old')
        atomic_bytes(self.paths.installation / 'active.json', json.dumps(old).encode())
        self.activate_current()
        record = json.loads((self.paths.installation / 'active.json').read_text('utf-8'))
        self.assertEqual(record['previous'], old)
        installation.activate(self.paths)
        self.assertEqual(json.loads((self.paths.installation / 'active.json').read_text('utf-8'))['previous'], old)

    def test_update_handoff_uses_fixed_launcher_and_canonical_previous_path(self):
        self.activate_current()
        with patch('updater.sys.frozen', True, create=True), \
             patch('updater.sys.executable', str(self.paths.desktop / 'renamed.exe')), \
             patch('updater._fetch_release', return_value=('99.0.0', '', {'digest':'sha256:'+'a'*64,'size':1000})), \
             patch('updater._download'), patch('updater.subprocess.Popen') as popen:
            self.assertTrue(updater.prepare_update(self.paths)['success'])
        command = popen.call_args.args[0]
        self.assertEqual(command[:2], [str(launcher_path(self.paths)), '--apply-update'])
        plan = json.loads((self.paths.updates / (command[2] + '.json')).read_text('utf-8'))
        self.assertEqual(Path(plan['previous']), installation.executable_for(self.paths).resolve())

    def test_failed_update_restores_pointer_before_launching_previous(self):
        old = self.executable(VERSION, b'MZ-old-app')
        active = self.paths.installation / 'active.json'
        original = json.dumps(old).encode()
        atomic_bytes(active, original)
        new = self.executable('99.0.0', b'MZ-new-app')
        token = 'a' * 32
        plan = dict(version=new['version'], target=new['executable'], previous=old['executable'],
                    size=Path(new['executable']).stat().st_size, digest='sha256:' + new['sha256'])
        atomic_bytes(self.paths.updates / (token + '.json'), json.dumps(plan).encode())
        def launch(arguments, **kwargs):
            process = Mock()
            process.poll.return_value = 1
            if Path(arguments[0]) == Path(new['executable']):
                atomic_bytes(active, json.dumps(new).encode())  # Simulate failure after pointer commit.
            else:
                self.assertEqual(active.read_bytes(), original)
            return process
        with patch('updater.subprocess.Popen', side_effect=launch):
            self.assertEqual(updater.monitor_update(self.paths, token, expected_previous=old['executable']), 1)
        self.assertEqual(active.read_bytes(), original)
