# -*- coding: utf-8 -*-
with open(r'C:\Users\I\.gemini\antigravity\scratch\schedule_manager\hwpx_generator.py', 'r', encoding='utf-8') as f:
    code = f.read()

old_tmpl = 'TEMPLATE_PATH = r"C:\\Users\\I\\Documents\\카카오톡 받은 파일\\0. 주간주요행사계획(26.07.06.~07.12.).hwpx"'
new_tmpl = '''def get_base_dir():
    import sys
    if getattr(sys, 'frozen', False):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))

def get_template_path():
    bundled = os.path.join(get_base_dir(), 'assets', 'template.hwpx')
    if os.path.exists(bundled):
        return bundled
    fallback = r"C:\\Users\\I\\Documents\\카카오톡 받은 파일\\0. 주간주요행사계획(26.07.06.~07.12.).hwpx"
    return fallback'''

if old_tmpl in code:
    code = code.replace(old_tmpl, new_tmpl)
    code = code.replace('if not os.path.exists(TEMPLATE_PATH):', 'template_file = get_template_path()\n    if not os.path.exists(template_file):')
    code = code.replace("with zipfile.ZipFile(TEMPLATE_PATH, 'r') as z_in:", "with zipfile.ZipFile(template_file, 'r') as z_in:")
    with open(r'C:\Users\I\.gemini\antigravity\scratch\schedule_manager\hwpx_generator.py', 'w', encoding='utf-8') as f:
        f.write(code)
    print("SUCCESS: hwpx_generator.py updated!")
else:
    print("Could not find old_tmpl")
