# -*- coding: utf-8 -*-
bat_content = """@echo off
cd /d "C:\\Users\\I\\.gemini\\antigravity\\scratch\\schedule_manager"
start "" "C:\\Users\\I\\AppData\\Local\\Programs\\Python\\Python314\\pythonw.exe" "main.py"
exit
"""

desktop_path = r"C:\Users\I\Desktop\군수실_일정_통합_관리_프로그램.bat"
with open(desktop_path, "wb") as f:
    f.write(bat_content.encode("cp949"))

print("SUCCESS: Desktop bat file rewritten in pure ASCII/CP949!")
