# -*- coding: utf-8 -*-
with open(r'C:\Users\I\.gemini\antigravity\scratch\schedule_manager\main.py', 'r', encoding='utf-8') as f:
    code = f.read()

old_base = "BASE_DIR = os.path.dirname(os.path.abspath(__file__))"
new_base = """if getattr(sys, 'frozen', False):
    BASE_DIR = sys._MEIPASS
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))"""

if old_base in code:
    code = code.replace(old_base, new_base)
    with open(r'C:\Users\I\.gemini\antigravity\scratch\schedule_manager\main.py', 'w', encoding='utf-8') as f:
        f.write(code)
    print("SUCCESS: main.py BASE_DIR updated!")
else:
    print("Could not find old_base in main.py")
