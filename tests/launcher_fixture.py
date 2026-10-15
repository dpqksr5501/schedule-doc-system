"""Launcher resource for isolated unit tests; never a production executable."""
import hashlib
from unittest.mock import patch


def use_launcher_fixture(testcase, paths):
    source = paths.installation.parent / 'unit-launcher.exe'
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(b'MZ-unit-launcher-protocol-1')
    resource = patch('installation.launcher_resource', return_value=(source, {
        'protocol': 1, 'sha256': hashlib.sha256(source.read_bytes()).hexdigest()}))
    resource.start()
    testcase.addCleanup(resource.stop)
