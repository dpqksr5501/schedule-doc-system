# -*- coding: utf-8 -*-
"""
보은군 군수실 일정표 시스템 - HWPX & HWP 자동 생성 엔진 (완전 무결점 템플릿 복제 방식)
Template-Cloning Engine for Perfect Hancom OWPML Compatibility
"""

import os
import sys
import zipfile
import shutil
import tempfile
import copy
import xml.etree.ElementTree as ET
from datetime import datetime

NS_HP = 'http://www.hancom.co.kr/hwpml/2011/paragraph'
NS_HC = 'http://www.hancom.co.kr/hwpml/2011/core'
NS_HH = 'http://www.hancom.co.kr/hwpml/2011/head'

NS = {
    'hp': NS_HP,
    'hc': NS_HC,
    'hh': NS_HH
}

# 행 기본 높이 단위
ROW_HEIGHT_UNIT = 2329
HEADER_HEIGHTS = 6316 + 1280 + 2612 # 제목행 + 작성일자행 + 컬럼헤더행

def get_base_dir():
    if getattr(sys, 'frozen', False):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))

def get_template_path():
    bundled = os.path.join(get_base_dir(), 'assets', 'template.hwpx')
    if os.path.exists(bundled):
        return bundled
    fallback = r"C:\Users\I\Documents\카카오톡 받은 파일\0. 주간주요행사계획(26.07.06.~07.12.).hwpx"
    return fallback

def _set_p_text(p_elem, text, char_ref='0'):
    """문단(p) 내부의 텍스트와 charPrIDRef를 완벽하고 깨끗하게 교체"""
    runs = p_elem.findall(f'{{{NS_HP}}}run')
    if runs:
        for r in runs[1:]:
            p_elem.remove(r)
        target_run = runs[0]
    else:
        target_run = ET.SubElement(p_elem, f'{{{NS_HP}}}run')

    target_run.attrib['charPrIDRef'] = str(char_ref)
    
    t_nodes = target_run.findall(f'{{{NS_HP}}}t')
    if t_nodes:
        for t in t_nodes[1:]:
            target_run.remove(t)
        t_elem = t_nodes[0]
        t_elem.clear()
        t_elem.text = text
    else:
        for child in list(target_run):
            target_run.remove(child)
        t_elem = ET.SubElement(target_run, f'{{{NS_HP}}}t')
        t_elem.text = text

    lineseg = p_elem.find(f'{{{NS_HP}}}linesegarray')
    if lineseg is not None:
        p_elem.remove(lineseg)


def generate_weekly_hwpx(week_data, output_path):
    """
    원본 HWPX의 실제 셀(tc)을 완벽하게 딥카피(Deep-Copy)하여
    여백, 너비, 글꼴, 셀 주소(colAddr/rowAddr) 및 행 수를 정확히 유지한 HWPX 생성
    """
    template_file = get_template_path()
    if not os.path.exists(template_file):
        raise FileNotFoundError(f"원본 템플릿 파일을 찾을 수 없습니다: {template_file}")

    temp_dir = tempfile.mkdtemp()
    try:
        # 1. 템플릿 압축 해제
        with zipfile.ZipFile(template_file, 'r') as z:
            z.extractall(temp_dir)

        section0_path = os.path.join(temp_dir, 'Contents', 'section0.xml')
        
        with open(section0_path, 'r', encoding='utf-8') as f:
            xml_text = f.read()

        root = ET.fromstring(xml_text.encode('utf-8'))
        tbl = root.find(f'.//{{{NS_HP}}}tbl')
        if tbl is None:
            raise ValueError("테이블을 찾을 수 없습니다.")

        rows = tbl.findall(f'{{{NS_HP}}}tr')
        header_rows = rows[:3]
        
        # 템플릿 셀 원형(Archetype) 추출
        sample_row = rows[3]
        sample_tcs = sample_row.findall(f'{{{NS_HP}}}tc')
        proto_date = copy.deepcopy(sample_tcs[0])   # colAddr=0, colSpan=1, width=4149
        proto_time = copy.deepcopy(sample_tcs[1])   # colAddr=1, colSpan=2, width=3866
        proto_title = copy.deepcopy(sample_tcs[2])  # colAddr=3, colSpan=1, width=30244
        proto_place = copy.deepcopy(sample_tcs[3])  # colAddr=4, colSpan=1, width=9491
        proto_dept = copy.deepcopy(sample_tcs[4])   # colAddr=5, colSpan=2, width=7793

        # 2. 제목 기간 문자열 완벽 치환
        period_str = week_data.get('period_str', '')
        if period_str:
            p_elems = header_rows[0].findall(f'.//{{{NS_HP}}}p')
            for p in p_elems:
                p_text = ''.join([t.text for t in p.findall(f'.//{{{NS_HP}}}t') if t.text])
                if '2026.' in p_text or '~' in p_text:
                    _set_p_text(p, f"({period_str})", char_ref='16')
                    break

        # 3. 작성일자 치환
        created_str = week_data.get('created_date_str', '')
        if created_str:
            p_elems = header_rows[1].findall(f'.//{{{NS_HP}}}p')
            for p in p_elems:
                p_text = ''.join([t.text for t in p.findall(f'.//{{{NS_HP}}}t') if t.text])
                if '작성' in p_text:
                    _set_p_text(p, created_str, char_ref='0')
                    break

        # 4. 기존 데이터 행들 모두 제거
        for r in rows[3:]:
            tbl.remove(r)

        # 5. 새 데이터 행 생성 및 삽입
        COLOR_REFS = {
            'gunsu': '36',      # 초록색 (#008000)
            'v_gunsu': '33',    # 파란색 (#0000FF)
            'important': '36',  # 강조
            'general': '0'      # 검정색 (#000000)
        }

        # 총 데이터 행 개수 미리 계산
        total_data_events = 0
        days_list = week_data.get('days', [])
        for d in days_list:
            evs = d.get('events', [])
            total_data_events += len(evs) if evs else 1

        current_row_idx = 3

        def create_tc(proto, text, row_idx, col_addr, row_span, col_span, char_ref='0', is_last_row=False, height=ROW_HEIGHT_UNIT):
            tc = copy.deepcopy(proto)
            
            # cellAddr 설정
            c_addr = tc.find(f'{{{NS_HP}}}cellAddr')
            if c_addr is not None:
                c_addr.attrib['colAddr'] = str(col_addr)
                c_addr.attrib['rowAddr'] = str(row_idx)

            # cellSpan 설정
            c_span = tc.find(f'{{{NS_HP}}}cellSpan')
            if c_span is not None:
                c_span.attrib['colSpan'] = str(col_span)
                c_span.attrib['rowSpan'] = str(row_span)

            # cellSz 높이 동적 설정 (요일 일정 수에 맞게 정확히 비례)
            c_sz = tc.find(f'{{{NS_HP}}}cellSz')
            if c_sz is not None:
                c_sz.attrib['height'] = str(height)

            # 마지막 행인 경우 하단 테두리를 SOLID 실선(id=10)으로 닫아줌!
            if is_last_row:
                tc.attrib['borderFillIDRef'] = '10'

            # 텍스트 및 색상 설정
            p = tc.find(f'.//{{{NS_HP}}}p')
            if p is not None:
                _set_p_text(p, text, char_ref=char_ref)

            return tc

        global_event_idx = 0

        for day in days_list:
            events = day.get('events', [])
            day_label = day.get('dayLabel', '')

            if not events:
                global_event_idx += 1
                is_last = (global_event_idx == total_data_events)
                tr = ET.SubElement(tbl, f'{{{NS_HP}}}tr')
                tr.append(create_tc(proto_date, day_label, current_row_idx, col_addr=0, row_span=1, col_span=1, char_ref='0', is_last_row=is_last, height=ROW_HEIGHT_UNIT))
                tr.append(create_tc(proto_time, "", current_row_idx, col_addr=1, row_span=1, col_span=2, char_ref='0', is_last_row=is_last, height=ROW_HEIGHT_UNIT))
                tr.append(create_tc(proto_title, "", current_row_idx, col_addr=3, row_span=1, col_span=1, char_ref='0', is_last_row=is_last, height=ROW_HEIGHT_UNIT))
                tr.append(create_tc(proto_place, "", current_row_idx, col_addr=4, row_span=1, col_span=1, char_ref='0', is_last_row=is_last, height=ROW_HEIGHT_UNIT))
                tr.append(create_tc(proto_dept, "", current_row_idx, col_addr=5, row_span=1, col_span=2, char_ref='0', is_last_row=is_last, height=ROW_HEIGHT_UNIT))
                current_row_idx += 1
            else:
                day_event_cnt = len(events)
                date_cell_height = day_event_cnt * ROW_HEIGHT_UNIT # 그 요일 일정 개수만큼 정확한 높이

                for idx, ev in enumerate(events):
                    global_event_idx += 1
                    is_last = (global_event_idx == total_data_events)
                    tr = ET.SubElement(tbl, f'{{{NS_HP}}}tr')
                    c_ref = COLOR_REFS.get(ev.get('attendee', 'general'), '0')

                    if idx == 0:
                        # 해당 요일 첫 행: 날짜 셀 (높이를 요일 일정수에 맞춤, 마지막 행이면 테두리 닫음)
                        is_date_last = (day == days_list[-1])
                        tr.append(create_tc(proto_date, day_label, current_row_idx, col_addr=0, row_span=day_event_cnt, col_span=1, char_ref='0', is_last_row=is_date_last, height=date_cell_height))

                    # 시간, 행사명, 장소, 주관 (각 1행 높이 ROW_HEIGHT_UNIT)
                    tr.append(create_tc(proto_time, ev.get('time', ''), current_row_idx, col_addr=1, row_span=1, col_span=2, char_ref=c_ref, is_last_row=is_last, height=ROW_HEIGHT_UNIT))
                    tr.append(create_tc(proto_title, ev.get('title', ''), current_row_idx, col_addr=3, row_span=1, col_span=1, char_ref=c_ref, is_last_row=is_last, height=ROW_HEIGHT_UNIT))
                    tr.append(create_tc(proto_place, ev.get('place', ''), current_row_idx, col_addr=4, row_span=1, col_span=1, char_ref=c_ref, is_last_row=is_last, height=ROW_HEIGHT_UNIT))
                    tr.append(create_tc(proto_dept, ev.get('dept', ''), current_row_idx, col_addr=5, row_span=1, col_span=2, char_ref=c_ref, is_last_row=is_last, height=ROW_HEIGHT_UNIT))

                    current_row_idx += 1

        # 6. 테이블 총 행 수(rowCnt) 및 전체 높이(sz height) 갱신
        tbl.attrib['rowCnt'] = str(current_row_idx)
        sz_elem = tbl.find(f'{{{NS_HP}}}sz')
        if sz_elem is not None:
            calculated_tbl_height = HEADER_HEIGHTS + (total_data_events * ROW_HEIGHT_UNIT)
            sz_elem.attrib['height'] = str(calculated_tbl_height)

        # 7. XML 저장
        ET.register_namespace('hp', NS_HP)
        ET.register_namespace('hc', NS_HC)
        ET.register_namespace('hh', NS_HH)

        tree = ET.ElementTree(root)
        tree.write(section0_path, encoding='utf-8', xml_declaration=True)

        # 8. HWPX로 재압축
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as out_zip:
            for root_dir, dirs, files in os.walk(temp_dir):
                for file in files:
                    full_p = os.path.join(root_dir, file)
                    rel_p = os.path.relpath(full_p, temp_dir)
                    out_zip.write(full_p, rel_p)

        return output_path
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def convert_hwpx_to_hwp(hwpx_path, hwp_path):
    """pywin32를 이용해 HWPX를 완벽한 HWP 바이너리로 변환"""
    try:
        import win32com.client
        hwp = win32com.client.Dispatch("HWPFrame.HwpObject")
        hwp.RegisterModule("FilePathCheckDLL", "FilePathCheckerModule")
        hwp.Open(hwpx_path, "HWPX", "forceopen:true")
        hwp.SaveAs(hwp_path, "HWP")
        hwp.Quit()
        return True, hwp_path
    except Exception as e:
        return False, str(e)
