# -*- coding: utf-8 -*-
with open(r'C:\Users\I\.gemini\antigravity\scratch\schedule_manager\initial_data.js', 'r', encoding='utf-8') as f:
    code = f.read()

code = code.replace("'title': '군수님 일정표'", "'title': '군수실 일정표'")
with open(r'C:\Users\I\.gemini\antigravity\scratch\schedule_manager\initial_data.js', 'w', encoding='utf-8') as f:
    f.write(code)

with open(r'C:\Users\I\.gemini\antigravity\scratch\schedule_manager\app.js', 'r', encoding='utf-8') as f:
    app_code = f.read()

app_code = app_code.replace("title: '군수님 일정표'", "title: '군수실 일정표'")
app_code = app_code.replace("a.download = `${settings.leaderTitle}_일정목록_${getTodayString()}.csv`;", "a.download = `군수실_일정목록_${getTodayString()}.csv`;")
app_code = app_code.replace("a.download = `군수님일정_백업_${getTodayString()}.json`;", "a.download = `군수실_일정데이터_백업_${getTodayString()}.json`;")

with open(r'C:\Users\I\.gemini\antigravity\scratch\schedule_manager\app.js', 'w', encoding='utf-8') as f:
    f.write(app_code)

print('Done updating initial_data.js and app.js!')
