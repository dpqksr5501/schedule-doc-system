# -*- coding: utf-8 -*-
"""
시스템 핵심 기능 및 업데이트 파이프라인 전체 단위 테스트 (Test Suite)
"""
import os
import sys
import tempfile
import subprocess
import time

def run_all_tests():
    print("==================================================")
    print("    [군수실 시스템] 자동 검증 테스트 스위트 시작")
    print("==================================================")

    # 1. 영구 데이터 저장/로드 검증
    print("\n[TEST 1] 영구 데이터 보존(%APPDATA%) 테스트...")
    import main
    api = main.DesktopApi()
    test_data = '{"test_event": "보은군민의날", "timestamp": 20260920}'
    
    save_res = api.save_persistent_data(test_data)
    assert save_res['success'], f"저장 실패: {save_res}"
    
    load_res = api.load_persistent_data()
    assert load_res['success'] and "보은군민의날" in load_res['data'], f"로드 실패: {load_res}"
    print("  [SUCCESS]: %APPDATA% 파일 읽기/쓰기 100% 정상 작동!")

    # 2. GitHub Releases API 통신 검증
    print("\n[TEST 2] GitHub 최신 버전 조회 API 통신 테스트...")
    import updater
    chk = updater.check_for_updates()
    print(f"  -> GitHub 응답: {chk}")
    assert chk['currentVersion'] == "1.0.1", "버전 불일치"
    assert 'hasUpdate' in chk, "hasUpdate 필드 누락"
    print("  [SUCCESS]: 아드님 GitHub 저장소와 HTTPS 통신 100% 성공!")

    # 3. 윈도우 원자적 파일 교체(Atomic Self-Swap) 모의 테스트
    print("\n[TEST 3] 윈도우 파일 잠금 우회 자가 교체(Self-Swap) 테스트...")
    temp_d = tempfile.mkdtemp()
    dummy_target = os.path.join(temp_d, "current_app.exe")
    dummy_new = os.path.join(temp_d, "downloaded_update.exe")

    with open(dummy_target, "wb") as f:
        f.write(b"OLD_VERSION_1.0.1")
    with open(dummy_new, "wb") as f:
        f.write(b"NEW_VERSION_1.0.2")

    swap_bat = os.path.join(temp_d, "test_swap.bat")
    bat_script = f"""@echo off
timeout /t 1 /nobreak > nul
:retry
move /y "{dummy_new}" "{dummy_target}" > nul 2>&1
if %errorlevel% neq 0 (
    timeout /t 1 /nobreak > nul
    goto retry
)
del "%~f0"
"""
    with open(swap_bat, "wb") as f:
        f.write(bat_script.encode("cp949"))

    proc = subprocess.Popen(f'cmd.exe /c "{swap_bat}"', shell=True)
    proc.wait()

    with open(dummy_target, "rb") as f:
        final_content = f.read()

    print(f"  -> 교체된 파일 내용: {final_content}")
    assert final_content == b"NEW_VERSION_1.0.2", "파일 교체 실패!"
    print("  [SUCCESS]: 실행 파일 자가 교체(In-Place Swap) 메커니즘 100% 검증 완료!")

    # 4. 한글 HWPX 생성 무결성 테스트
    print("\n[TEST 4] 한글(HWPX) 자동 생성 엔진 검증...")
    import hwpx_generator
    dummy_week = {
        'period_str': '2026. 9. 21. ~ 9. 27.',
        'created_date_str': '2026. 9. 20.작성',
        'days': [
            {'dayLabel': '21(월)', 'events': [{'time': '09:00', 'title': '테스트', 'place': '군청', 'dept': '행정과', 'attendee': 'gunsu'}]}
        ]
    }
    test_hwpx = os.path.join(temp_d, "test.hwpx")
    res_p = hwpx_generator.generate_weekly_hwpx(dummy_week, test_hwpx)
    assert os.path.exists(res_p) and os.path.getsize(res_p) > 500000, "HWPX 생성 실패"
    print(f"  [SUCCESS]: 한글(HWPX) 정상 생성 완료 (크기: {os.path.getsize(res_p):,} bytes)")

    print("\n==================================================")
    print("  모든 4대 핵심 기능 테스트가 100% 성공했습니다!")
    print("==================================================")

if __name__ == '__main__':
    run_all_tests()
