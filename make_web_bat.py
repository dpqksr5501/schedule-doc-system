# -*- coding: utf-8 -*-
bat_content = """@echo off
cd /d "C:\\Users\\I\\.gemini\\antigravity\\scratch\\schedule_manager"
start "" "index.html"
exit
"""

desktop_path = r"C:\Users\I\Desktop\군수실_일정_웹브라우저_실행.bat"
with open(desktop_path, "wb") as f:
    f.write(bat_content.encode("cp949"))

print("SUCCESS: Web browser launcher bat file created!")
