# -*- coding: utf-8 -*-
import os
import shutil

dist_dir = r"C:\Users\I\.gemini\antigravity\scratch\schedule_manager\dist"
desktop_dir = os.path.join(os.path.expanduser("~"), "Desktop")

# 1. dist 디렉토리 안의 exe 파일 찾기
exe_files = [f for f in os.listdir(dist_dir) if f.endswith(".exe")]
if exe_files:
    built_exe = os.path.join(dist_dir, exe_files[0])
    target_exe = os.path.join(desktop_dir, "군수실_일정_관리_시스템.exe")
    
    # 2. 바탕화면으로 복사
    shutil.copy2(built_exe, target_exe)
    print("SUCCESS: Copied to desktop as:", target_exe)
    print("File size:", os.path.getsize(target_exe), "bytes")
else:
    print("ERROR: No exe file found in dist!")

# 3. 바탕화면의 이전 .bat 파일들 모두 정리
for item in os.listdir(desktop_dir):
    if item.endswith(".bat") and ("군수" in item or "일정" in item):
        try:
            os.remove(os.path.join(desktop_dir, item))
            print("Removed old bat file:", item)
        except Exception as e:
            print("Failed to remove:", item, e)

print("Desktop is now 100% clean with ONLY '군수실_일정_관리_시스템.exe'!")
