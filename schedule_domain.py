"""Validate and migrate all data crossing the desktop bridge."""
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import json
import re
import uuid

SCHEMA_VERSION = 3
MAX_BYTES = 16 * 1024 * 1024
MAX_EVENTS = 30000
DEFAULT_SETTINGS = {"orgName": "보은군", "leaderTitle": "군수님",
                    "subLeaderTitle": "부군수님", "fontSize": "normal"}
KST = timezone(timedelta(hours=9))


class UnsupportedSchemaError(ValueError):
    """An intact future schema must never trigger a restore of older data."""


def timestamp():
    return datetime.now(KST).isoformat(timespec="seconds")


def today():
    return datetime.now(KST).date().isoformat()


def text(value, label, maximum, required=False):
    if not isinstance(value, str):
        raise ValueError(f"{label}: 글자로 입력해 주세요.")
    value = value.strip()
    if required and not value:
        raise ValueError(f"{label}을 입력해 주세요.")
    if len(value) > maximum:
        raise ValueError(f"{label}: {maximum:,}자 이내로 입력해 주세요.")
    if any(not (ord(c) in (9, 10, 13) or 32 <= ord(c) <= 0xD7FF
                    or 0xE000 <= ord(c) <= 0xFFFD or 0x10000 <= ord(c) <= 0x10FFFF)
           for c in value):
        raise ValueError(f"{label}: 사용할 수 없는 제어 문자가 있습니다.")
    return value


def valid_date(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        raise ValueError("날짜는 연-월-일 형식으로 입력해 주세요.")
    parsed = date.fromisoformat(value)
    if not 1900 <= parsed.year <= 2199:
        raise ValueError('일정 날짜는 1900년부터 2199년 사이로 입력해 주세요.')
    return value


def valid_time(value, optional=False):
    if optional and value == "":
        return ""
    if not isinstance(value, str) or not re.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]", value):
        raise ValueError("시간은 00:00부터 23:59 사이로 입력해 주세요.")
    return value


def event_record(raw, trash=False):
    if not isinstance(raw, dict):
        raise ValueError("일정 항목 형식이 올바르지 않습니다.")
    identifier = raw.get("id")
    if not isinstance(identifier, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", identifier):
        raise ValueError("일정 고유번호가 올바르지 않습니다.")
    attendee = raw.get("attendee", "general")
    priority = raw.get("priority", "normal")
    if attendee == "important":  # v1 stored importance in the attendee field.
        attendee, priority = "general", "important"
    if attendee not in ("gunsu", "v_gunsu", "general") or priority not in ("normal", "important"):
        raise ValueError("참석 구분 또는 중요도가 올바르지 않습니다.")
    status = raw.get("status", "confirmed")
    if status not in ("confirmed", "tentative", "cancelled"):
        raise ValueError("일정 상태가 올바르지 않습니다.")
    checks = raw.get("checklist", [])
    if not isinstance(checks, list) or len(checks) > 40:
        raise ValueError("준비 확인 목록은 40개까지 사용할 수 있습니다.")
    checked = []
    ids = set()
    for check in checks:
        if not isinstance(check, dict) or type(check.get("done", False)) is not bool:
            raise ValueError("확인 목록 형식이 올바르지 않습니다.")
        check_id = check.get("id", uuid.uuid4().hex)
        if not isinstance(check_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", check_id) or check_id in ids:
            raise ValueError("확인 목록의 고유번호가 중복되거나 잘못되었습니다.")
        ids.add(check_id)
        checked.append({"id": check_id, "text": text(check.get("text", ""), "확인 사항", 500, True),
                        "done": check.get("done", False)})
    result = {"id": identifier, "date": valid_date(raw.get("date")),
              "time": valid_time(raw.get("time")),
              "endTime": valid_time(raw.get("endTime", ""), True),
              "attendee": attendee, "priority": priority, "status": status,
              "checklist": checked}
    if result["endTime"] and result["endTime"] <= result["time"]:
        raise ValueError("종료 시간은 시작 시간보다 늦게 입력해 주세요.")
    for key, label, maximum in (("title", "행사명", 500), ("place", "장소", 300),
                                 ("dept", "주관부서", 200), ("annotation", "출력 주석", 600), ("participants", "참석 예정자", 2000),
                                 ("preparation", "진행·준비사항", 3000), ("contact", "담당자", 300),
                                 ("notes", "업무 메모", 6000)):
        result[key] = text(raw.get(key, ""), label, maximum, key == "title")
    result["updatedAt"] = text(raw.get("updatedAt", ""), "수정 시각", 50)
    if trash:
        result["deletedAt"] = text(raw.get("deletedAt", ""), "삭제 시각", 50)
    return result


def empty_snapshot():
    return {"schemaVersion": SCHEMA_VERSION, "revision": 0, "savedAt": "",
            "events": [], "deletedEvents": [], "settings": deepcopy(DEFAULT_SETTINGS)}


def validate_snapshot(raw):
    if isinstance(raw, list):  # Older native patch stored only the event array.
        raw = {"events": raw, "deletedEvents": [], "settings": {}}
    if not isinstance(raw, dict) or "events" not in raw:
        raise ValueError("일정 백업 형식이 올바르지 않습니다.")
    schema = raw.get("schemaVersion", 1)
    if type(schema) is not int or schema not in (1, 2, SCHEMA_VERSION):
        raise UnsupportedSchemaError("이 데이터는 다른 버전에서 작성되었습니다. 프로그램 버전을 확인해 주세요.")
    result = empty_snapshot()
    active_ids = set()
    for key in ("events", "deletedEvents"):
        records = raw.get(key, [])
        if not isinstance(records, list) or len(records) > MAX_EVENTS:
            raise ValueError("일정 데이터의 개수 또는 형식이 올바르지 않습니다.")
        for record in records:
            event = event_record(record, key == "deletedEvents")
            if event["id"] in active_ids:
                raise ValueError("중복된 일정 고유번호가 있습니다.")
            active_ids.add(event["id"])
            result[key].append(event)
    settings = raw.get("settings", {})
    if not isinstance(settings, dict):
        raise ValueError("설정 형식이 올바르지 않습니다.")
    for key in ("orgName", "leaderTitle", "subLeaderTitle"):
        if key in settings:
            result["settings"][key] = text(settings[key], "기관·직위명", 80, True)
    if settings.get("fontSize", "normal") not in ("normal", "large"):
        raise ValueError("화면 글자 크기 설정이 올바르지 않습니다.")
    result["settings"]["fontSize"] = settings.get("fontSize", "normal")
    revision = raw.get("revision", 0)
    if type(revision) is not int or not 0 <= revision < 2 ** 53:
        raise ValueError("저장 순서 정보가 올바르지 않습니다.")
    result["revision"] = revision
    result["savedAt"] = text(raw.get("savedAt", ""), "저장 시각", 50)
    return result


def parse_snapshot(content):
    if not isinstance(content, str) or len(content.encode("utf-8")) > MAX_BYTES:
        raise ValueError("백업 파일은 16MB 이내로 선택해 주세요.")
    def invalid_constant(value):
        raise ValueError("올바르지 않은 숫자 값이 있습니다.")
    return validate_snapshot(json.loads(content.lstrip("\ufeff"), parse_constant=invalid_constant))
