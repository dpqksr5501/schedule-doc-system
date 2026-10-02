"""Offline regression suite: never open production APPDATA or launch Hancom."""
import subprocess
import unittest
from pathlib import Path

if __name__ == '__main__':
    root = Path(__file__).resolve().parent
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.discover(str(root / 'tests')))
    if not result.wasSuccessful():
        raise SystemExit(1)
    subprocess.run(['node', '--check', str(root / 'app.js')], check=True)
    subprocess.run(['node', str(root / 'tests' / 'core.test.cjs')], check=True)
