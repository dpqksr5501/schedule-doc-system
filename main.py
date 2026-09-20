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

class DesktopApi:
    """JavaScript 프론트엔드와 통신하는 Python 네이티브 브릿지 API"""
    
    def __init__(self):
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        os.makedirs(APPDATA_DIR, exist_ok=True)

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

    def export_hwpx(self, week_data):
        """주간 일정 데이터를 받아 실제 한글(.hwpx) 파일로 즉시 생성"""
        try:
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
            os.makedirs(OUTPUT_DIR, exist_ok=True)
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
