"""Atomic, validated snapshot storage with revision checks and recovery history."""
from copy import deepcopy
from pathlib import Path
import json
import os
import re
import shutil
import tempfile
import threading
import uuid
from schedule_domain import MAX_BYTES, UnsupportedSchemaError, empty_snapshot, parse_snapshot, timestamp, validate_snapshot


def atomic_bytes(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix="." + path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def encode(snapshot):
    return json.dumps(snapshot, ensure_ascii=False, indent=2).encode("utf-8")


def atomic_copy(source, target):
    """Preserve even an oversized damaged file without reading it into RAM."""
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.' + target.name + '.', dir=target.parent)
    try:
        with os.fdopen(fd, 'wb') as output, Path(source).open('rb') as input_file:
            shutil.copyfileobj(input_file, output, length=1024 * 1024)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class SnapshotStore:
    def __init__(self, paths):
        self.paths = paths
        self._lock = threading.RLock()
        self._snapshot = None
        self.recovery = None
        paths.ensure_data()

    def _read(self, path):
        with Path(path).open("rb") as stream:
            content = stream.read(MAX_BYTES + 1)
        if len(content) > MAX_BYTES:
            raise ValueError("저장 파일이 허용 크기를 초과했습니다.")
        return parse_snapshot(content.decode("utf-8-sig"))

    def load(self):
        with self._lock:
            if self._snapshot is not None:
                return deepcopy(self._snapshot)
            primary = self.paths.database
            backups = sorted(self.paths.backups.glob("snapshot-*.json"), reverse=True)
            candidates = [primary, primary.with_suffix(".json.bak"), *backups]
            existing = [path for path in candidates if path.exists()]
            if not existing:
                self._snapshot = empty_snapshot()
                return deepcopy(self._snapshot)
            failures = []
            for path in existing:
                try:
                    snapshot = self._read(path)
                except UnsupportedSchemaError:
                    if path == primary:
                        raise
                    continue
                except (OSError, UnicodeError, ValueError, RecursionError) as error:
                    failures.append(str(error))
                    continue
                if path != primary:
                    # Preserve the damaged original before repairing the live snapshot.
                    if primary.exists():
                        quarantine = self.paths.backups / ("corrupt-" + uuid.uuid4().hex + ".json")
                        atomic_copy(primary, quarantine)
                    atomic_bytes(primary, encode(snapshot))
                    self.recovery = {"file": path.name, "savedAt": snapshot["savedAt"]}
                self._snapshot = snapshot
                return deepcopy(snapshot)
            raise ValueError("일정 파일과 자동 백업을 읽지 못했습니다. 원본을 보존했습니다. 백업 복원을 이용해 주세요.")

    def save(self, raw, expected_revision):
        proposed = validate_snapshot(raw)
        with self._lock:
            current = self.load()
            if type(expected_revision) is not int or expected_revision != current["revision"]:
                raise ValueError("다른 저장 작업이 먼저 완료되었습니다. 화면을 다시 불러온 뒤 저장해 주세요.")
            proposed["revision"] = current["revision"] + 1
            proposed["savedAt"] = timestamp()
            if len(encode(proposed)) > MAX_BYTES:
                raise ValueError("데이터 크기가 16MB를 초과했습니다. 지난 일정을 정리해 주세요.")
            if self.paths.database.exists():
                old = encode(current)
                history = self.paths.backups / ("snapshot-" + f'{current["revision"]:012d}' + "-" + uuid.uuid4().hex + ".json")
                atomic_bytes(history, old)
                atomic_bytes(self.paths.database.with_suffix(".json.bak"), old)
            atomic_bytes(self.paths.database, encode(proposed))
            self._snapshot = proposed
            histories = sorted(self.paths.backups.glob("snapshot-*.json"), reverse=True)
            # Cleanup is best-effort; a committed save must not be reported as a failure.
            for path in histories[60:]:
                try:
                    path.unlink()
                except OSError:
                    pass
            return deepcopy(proposed)

    def list_backups(self):
        result = []
        for path in sorted(self.paths.backups.glob("snapshot-*.json"), reverse=True):
            try:
                item = self._read(path)
                result.append({"id": path.name, "savedAt": item["savedAt"],
                               "count": len(item["events"]), "revision": item["revision"]})
            except (OSError, UnicodeError, ValueError, RecursionError):
                continue
        return result[:60]

    def read_backup(self, identifier):
        if not isinstance(identifier, str) or not re.fullmatch(r'snapshot-[0-9]{12,16}-[0-9a-f]{32}\.json', identifier):
            raise ValueError("백업 선택 정보가 올바르지 않습니다.")
        return self._read(self.paths.backups / identifier)

    def import_snapshot(self, raw, expected_revision):
        # A valid user backup can recover a store for which every automatic backup failed.
        validated = validate_snapshot(raw)
        with self._lock:
            reset = False
            try:
                self.load()
            except UnsupportedSchemaError:
                raise
            except ValueError:
                if expected_revision != 0:
                    raise
                if self.paths.database.exists():
                    atomic_copy(self.paths.database, self.paths.backups / ("corrupt-" + uuid.uuid4().hex + ".json"))
                self._snapshot = empty_snapshot()
                reset = True
            try:
                return self.save(validated, expected_revision)
            except Exception:
                if reset:
                    self._snapshot = None
                raise
