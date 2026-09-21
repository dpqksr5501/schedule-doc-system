# -*- coding: utf-8 -*-
"""
군수실 일정 통합 관리 시스템 - 메인 데스크톱 실행 파일
보은군 군수실 전용 (Powered by Python & WebView2)
GitHub Repository: https://github.com/dpqksr5501/schedule-doc-system
"""

import os
import sys
import json
import subprocess
import webview
from datetime import datetime
import hwpx_generator
import updater

# 애플리케이션 기본 경로
if getattr(sys, 'frozen', False):
    BASE_DIR = sys._MEIPASS
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

INDEX_HTML = os.path.join(BASE_DIR, "index.html")
ICON_PATH = os.path.join(BASE_DIR, "assets", "app_icon.ico")
DESKTOP_DIR = os.path.join(os.path.expanduser("~"), "Desktop")
OUTPUT_DIR = os.path.join(DESKTOP_DIR, "군수실_일정_출력문서")

# 영구 데이터 저장소 (%APPDATA%\GunsuSchedule)
APPDATA_DIR = os.path.join(os.getenv('APPDATA', os.path.expanduser("~")), "GunsuSchedule")
DATA_FILE_PATH = os.path.join(APPDATA_DIR, "schedule_data.json")
MANUAL_FILE_PATH = os.path.join(OUTPUT_DIR, "★ 군수실_일정표_사용설명서.txt")

MANUAL_CONTENT = """========================================================================
    [보은군 군수실] 일정 통합 관리 시스템 간편 사용설명서
========================================================================

아버지, 업무 보실 때 한글 표 작업하느라 고생 많으셨죠?
단 한 번만 입력하시면 일일·주간·월간 일정표가 자동으로 만들어지고,
실제 한컴오피스 한글 문서로 1초 만에 저장되는 프로그램입니다!

------------------------------------------------------------------------
 1. 출력 파일 형식 안내 (★ MS 워드가 아닙니다!)
------------------------------------------------------------------------
* 100% 공공기관 표준인 [한컴오피스 한글 문서]로 출력됩니다.
  - 최신 한글 표준 규격: .hwpx 파일 지원
  - 기존 구버전 규격: .hwp 파일 지원
* 화면 상단에서 [한글(HWPX) 저장] 또는 [HWP 저장] 버튼을 누르시면,
  바탕화면의 [군수실_일정_출력문서] 폴더에 실제 한글 파일이 즉시 생성됩니다.
  (생성 후 파일이 든 폴더가 자동으로 화면에 열립니다)

* 컴퓨터에 프린터가 연결되어 있다면 [A4 바로 인쇄]를 눌러
  종이로 즉시 깨끗하게 출력하실 수도 있습니다.


------------------------------------------------------------------------
 2. 초간단 3단계 사용 순서
------------------------------------------------------------------------
 [ 1단계 ] 우측 상단 [ ➕ 새 일정 등록 ] 누르고 내용 입력하기
           (날짜, 시간, 행사명, 장소, 부서, 글씨 색상)
           ※ 상단 연초록색 한 줄 입력창에 대충 적고 엔터 치셔도 됩니다!

 [ 2단계 ] 상단 탭에서 원하는 양식 고르기
           - [📄 1. 일일 일정표] : 군수님 당일 일정표 A4 1장
           - [📑 2. 주간 행사계획] : 보은군청 공식 주간행사계획 표
           - [🗓️ 3. 월간 일정표] : 한 달 치 달력형 일정표

 [ 3단계 ] [ 🖨️ A4 바로 인쇄 ] 또는 [ 📄 한글(HWPX) 저장 ] 누르면 끝!


------------------------------------------------------------------------
 3. 알아두시면 10배 편해지는 핵심 꿀팁
------------------------------------------------------------------------
★ 꿀팁 1 : 표 위의 일정을 마우스로 "콕" 클릭해 보세요!
   - 한글 문서 화면에 적힌 일정을 마우스로 클릭하면, 그 자리에서 바로
     수정창이 열립니다. 오타 수정이나 글자 색상 변경이 1초 만에 끝납니다.

★ 꿀팁 2 : 글씨 색상 원클릭 선택
   - 등록창 아래에 큼직한 컬러 버튼이 있습니다.
     🟢 초록색 : 군수님 참석 (일일일정표에도 자동 반영)
     🔵 파란색 : 부군수님 참석
     ⚫ 검정색 : 일반 / 부서 행사
     🔴 빨간색 : 중요 / 특별 행사

★ 꿀팁 3 : [지난주 일정 복사] 버튼 활용
   - 주간 탭에서 [📋 지난주 복사]를 누르면, 지난주 일정이 이번 주로
     날짜만 싹 바뀌어 복제됩니다. 매주 반복되는 회의를 다시 칠 필요가 없습니다!

★ 꿀팁 4 : 실수로 지웠을 때 [휴지통] 복구
   - 일정을 잘못 삭제하셨더라도 상단 [⚙️ 도구] -> [🗑️ 삭제 휴지통]에서
     언제든 클릭 한 번으로 되살릴 수 있습니다.


------------------------------------------------------------------------
 4. 파일 저장 위치
------------------------------------------------------------------------
* 모든 한글 출력 파일은 바탕화면의 [군수실_일정_출력문서] 폴더에
  날짜별로 차곡차곡 안전하게 보관됩니다.


------------------------------------------------------------------------
 5. 프로그램 자동 업데이트 안내
------------------------------------------------------------------------
* 제가 새로운 기능이나 서식을 추가해서 업데이트를 올리면,
  프로그램 상단 [⚙️ 도구] -> [🔄 프로그램 패치 확인]을 누르거나
  프로그램을 켤 때 알아서 새 버전을 감지하고 최신으로 바뀝니다!
========================================================================
              - 항상 건강하시고 힘내세요, 아들 올림 -
========================================================================
"""

def ensure_manual_file():
    """출력 폴더에 항상 설명서가 존재하도록 보장"""
    try:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        if not os.path.exists(MANUAL_FILE_PATH):
            with open(MANUAL_FILE_PATH, 'w', encoding='utf-8-sig') as f:
                f.write(MANUAL_CONTENT)
    except Exception:
        pass


class DesktopApi:
    """JavaScript 프론트엔드와 통신하는 Python 네이티브 브릿지 API"""
    
    def __init__(self):
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        os.makedirs(APPDATA_DIR, exist_ok=True)
        ensure_manual_file()

    def get_version(self):
        """현재 앱 버전 반환"""
        return updater.get_current_version()

    def check_update(self):
        """GitHub Releases 최신 업데이트 확인"""
        return updater.check_for_updates()

    def apply_update(self, download_url):
        """GitHub Releases 최신 버전 다운로드 및 자동 재실행 자가 교체"""
        return updater.apply_update(download_url)

    def save_persistent_data(self, data_str):
        """아버님의 소중한 일정 데이터를 %APPDATA%에 영구 보존"""
        try:
            with open(DATA_FILE_PATH, 'w', encoding='utf-8') as f:
                f.write(data_str)
            return {'success': True}
        except Exception as e:
            return {'success': False, 'message': str(e)}

    def load_persistent_data(self):
        """%APPDATA%에 영구 보존된 데이터 로드"""
        try:
            if os.path.exists(DATA_FILE_PATH):
                with open(DATA_FILE_PATH, 'r', encoding='utf-8') as f:
                    return {'success': True, 'data': f.read()}
            return {'success': False, 'message': 'No file'}
        except Exception as e:
            return {'success': False, 'message': str(e)}

    def open_manual(self):
        """설명서 파일을 윈도우 기본 텍스트 뷰어(메모장)로 띄움"""
        try:
            ensure_manual_file()
            if os.name == 'nt':
                os.startfile(MANUAL_FILE_PATH)
            return {'success': True}
        except Exception as e:
            return {'success': False, 'message': str(e)}

    def export_hwpx(self, week_data):
        """주간 일정 데이터를 받아 실제 한글(.hwpx) 파일로 즉시 생성"""
        try:
            ensure_manual_file()
            period_clean = week_data.get('period_str', '주간일정').replace(' ', '').replace('~', '_').replace('.', '')
            today_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"주간주요행사계획_{period_clean}_{today_str}.hwpx"
            out_path = os.path.join(OUTPUT_DIR, filename)

            hwpx_generator.generate_weekly_hwpx(week_data, out_path)

            return {
                'success': True,
                'path': out_path,
                'filename': filename,
                'message': f"한글(HWPX) 파일이 성공적으로 생성되었습니다!\n저장위치: {out_path}"
            }
        except Exception as e:
            return {
                'success': False,
                'message': f"HWPX 생성 중 오류가 발생했습니다: {str(e)}"
            }

    def export_hwp(self, week_data):
        """HWPX 생성 후 OLE Automation을 통해 완벽한 구버전 HWP 파일로 변환 저장"""
        try:
            ensure_manual_file()
            hwpx_res = self.export_hwpx(week_data)
            if not hwpx_res['success']:
                return hwpx_res

            hwpx_path = hwpx_res['path']
            hwp_path = hwpx_path[:-5] + ".hwp"

            ok, err_or_path = hwpx_generator.convert_hwpx_to_hwp(hwpx_path, hwp_path)
            if ok:
                return {
                    'success': True,
                    'path': hwp_path,
                    'filename': os.path.basename(hwp_path),
                    'message': f"한글(HWP) 파일이 성공적으로 생성되었습니다!\n저장위치: {hwp_path}"
                }
            else:
                return {
                    'success': True,
                    'path': hwpx_path,
                    'isHwpxFallback': True,
                    'message': f"한글(HWPX) 파일로 생성되었습니다.\n(참고: 한글 프로그램 연동 불가로 HWPX로 저장됨)\n저장위치: {hwpx_path}"
                }
        except Exception as e:
            return {
                'success': False,
                'message': f"HWP 변환 중 오류: {str(e)}"
            }

    def open_export_folder(self):
        """저장된 출력 문서 폴더를 윈도우 파일 탐색기로 띄움"""
        try:
            ensure_manual_file()
            subprocess.Popen(f'explorer "{OUTPUT_DIR}"')
            return {'success': True}
        except Exception as e:
            return {'success': False, 'message': str(e)}


def main():
    api = DesktopApi()
    
    # 윈도우 창 설정 (군수실 전용 브랜딩)
    window = webview.create_window(
        title=f"군수실 일정 통합 관리 시스템 (v{updater.get_current_version()})",
        url=INDEX_HTML,
        js_api=api,
        width=1380,
        height=880,
        min_size=(1050, 720),
        text_select=True,
        zoomable=True
    )

    webview.start(debug=False)

if __name__ == '__main__':
    main()
