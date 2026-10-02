"""Compatibility facade and isolated Hancom COM conversion."""
from pathlib import Path
import logging
import uuid
from document_engine import NS_HP, NS_HC, NS_HH, get_template_path, generate_document
from schedule_domain import event_record, text, today
from hwp_validation import validate_hwp


def generate_weekly_hwpx(week_data, output_path):
    days = []
    for day in week_data.get('days', []):
        events = [event_record(dict(raw, id=raw.get('id', uuid.uuid4().hex),
                                    date=raw.get('date', today()))) for raw in day.get('events', [])]
        days.append({'date': events[0]['date'] if events else day.get('date', today()),
                     'dayLabel': text(day.get('dayLabel', ''), '일자', 80), 'events': events})
    if not days:
        days = [{'date': today(), 'events': []}]
    generate_document({'view': 'weekly', 'title': '주간 주요행사계획', 'days': days,
                       'period_str': text(week_data.get('period_str', ''), '기간', 150),
                       'created_date_str': text(week_data.get('created_date_str', ''), '작성일', 150),
                       'includeNotes': False, 'includeAnnotation': False}, output_path)
    return str(output_path)


def convert_hwpx_to_hwp(hwpx_path, hwp_path):
    hwp, initialized = None, False
    try:
        import pythoncom
        import win32com.client
        pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)
        initialized = True
        hwp = win32com.client.DispatchEx('HWPFrame.HwpObject')
        # An absent optional module must not block normal Hancom access approval.
        # Never auto-click the approval dialog or change the PC's security policy.
        registered = False
        for name in ('FilePathCheckerModule', 'FilePathCheckerModuleExample'):
            try:
                registered = bool(hwp.RegisterModule('FilePathCheckDLL', name))
            except Exception:
                logging.warning('Hancom security module unavailable: %s', name)
            if registered:
                break
        if not registered:
            logging.info('Using the normal Hancom file-access approval dialog')
            hwp.XHwpWindows.Item(0).Visible = True
        if not hwp.Open(str(Path(hwpx_path).resolve()), 'HWPX', 'forceopen:true'):
            raise RuntimeError('한글에서 HWPX를 열지 못했습니다.')
        if not hwp.SaveAs(str(Path(hwp_path).resolve()), 'HWP'):
            raise RuntimeError('HWP 저장이 실패했습니다.')
        validate_hwp(hwp_path)
        return True, str(hwp_path)
    except Exception as error:
        logging.exception('Hancom conversion failed')
        if isinstance(error, (RuntimeError, ValueError)):
            return False, str(error)
        return False, '한글 프로그램에 연결하지 못했습니다. HWPX를 열 수 있는 Windows 한글의 설치 및 자동화 사용 가능 여부를 전산 담당자에게 확인해 주세요.'
    finally:
        if hwp is not None:
            try:
                hwp.Quit()
            except Exception:
                pass
        if initialized:
            pythoncom.CoUninitialize()
