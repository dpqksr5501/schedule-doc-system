"""Resolve Windows redirected folders; never store data in the onefile bundle."""
from dataclasses import dataclass
from pathlib import Path
import ctypes
import os
import sys
import uuid


def resource_dir():
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))


def desktop_directory():
    if os.name != "nt":
        return Path.home() / "Desktop"
    # FOLDERID_Desktop also resolves OneDrive and institution folder redirection.
    identifier = (ctypes.c_byte * 16).from_buffer_copy(
        uuid.UUID("B4BFCC3A-DB2C-424C-B029-7FE99A87C641").bytes_le
    )
    shell = ctypes.WinDLL("shell32", use_last_error=True)
    ole = ctypes.WinDLL("ole32", use_last_error=True)
    shell.SHGetKnownFolderPath.argtypes = [ctypes.c_void_p, ctypes.c_uint32,
                                         ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
    shell.SHGetKnownFolderPath.restype = ctypes.c_long
    ole.CoTaskMemFree.argtypes = [ctypes.c_void_p]
    pointer = ctypes.c_void_p()
    result = shell.SHGetKnownFolderPath(ctypes.byref(identifier), 0, None,
                                        ctypes.byref(pointer))
    if result != 0:
        raise OSError("Windows 바탕화면 위치를 확인하지 못했습니다.")
    try:
        return Path(ctypes.wstring_at(pointer))
    finally:
        ole.CoTaskMemFree(pointer)


@dataclass(frozen=True)
class AppPaths:
    data: Path
    desktop: Path
    installation: Path

    @classmethod
    def current(cls):
        return cls(
            Path(os.environ.get("APPDATA", str(Path.home()))) / "GunsuSchedule",
            desktop_directory(),
            Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "GunsuSchedule",
        )

    @classmethod
    def isolated(cls, root):
        root = Path(root)
        return cls(root / "data", root / "Desktop", root / "installed")

    @property
    def output(self):
        return self.desktop / "군수실_일정_출력문서"

    @property
    def database(self):
        return self.data / "schedule_data.json"

    @property
    def backups(self):
        return self.data / "backups"

    @property
    def updates(self):
        return self.installation / "updates"

    def ensure_data(self):
        self.data.mkdir(parents=True, exist_ok=True)
        self.backups.mkdir(parents=True, exist_ok=True)

    def ensure_output(self):
        self.output.mkdir(parents=True, exist_ok=True)
        for name in ("일일일정", "주간일정", "월간일정", "데이터백업"):
            (self.output / name).mkdir(exist_ok=True)
