# -*- coding: utf-8 -*-
with open(r'C:\Users\I\.gemini\antigravity\scratch\schedule_manager\app.js', 'r', encoding='utf-8') as f:
    code = f.read()

# saveData 확장
old_save_events = """  function saveEvents() {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(events));
  }"""

new_save_events = """  function saveEvents() {
    const jsonStr = JSON.stringify(events);
    localStorage.setItem(STORAGE_KEY, jsonStr);
    // 데스크톱 앱 영구 저장소(%APPDATA%) 2중 안전 백업
    if (window.pywebview && window.pywebview.api && window.pywebview.api.save_persistent_data) {
      window.pywebview.api.save_persistent_data(jsonStr);
    }
  }"""

if old_save_events in code:
    code = code.replace(old_save_events, new_save_events)

# 네이티브 기능 함수들 추가 (app.js 맨 끝 바로 전)
native_helpers = """
  // ===================================================
  // 데스크톱 네이티브 API 연동 (한글 저장 / 폴더열기 / 자가 업데이트)
  // ===================================================
  async function triggerNativeExport(format) {
    if (!window.pywebview || !window.pywebview.api) {
      alert('데스크톱 프로그램 환경에서만 한글(.hwpx/.hwp) 직접 저장이 지원됩니다.\\n(상단 [🖨️ A4 바로 인쇄]로 PDF 저장 가능)');
      return;
    }

    const mon = getMondayOfDate(selectedDate);
    const sun = addDays(mon, 6);
    const periodStr = `${mon.slice(2).replace(/-/g, '.')} ~ ${sun.slice(5).replace(/-/g, '.')}`;

    // 주간 데이터 취합
    const daysData = [];
    for (let i = 0; i < 7; i++) {
      const dStr = addDays(mon, i);
      const dNum = parseInt(dStr.slice(8), 10);
      const dayName = getDayOfWeek(dStr);
      const dayEvents = events.filter(e => e.date === dStr).sort((a, b) => a.time.localeCompare(b.time));
      daysData.push({
        dayLabel: `${dNum}(${dayName})`,
        events: dayEvents
      });
    }

    const payload = {
      period_str: `${mon.replace(/-/g, '. ')} ~ ${sun.slice(5).replace(/-/g, '. ')}`,
      created_date_str: `${getTodayString().replace(/-/g, '. ')}작성 (군수실)`,
      days: daysData
    };

    try {
      let res;
      if (format === 'hwp') {
        res = await window.pywebview.api.export_hwp(payload);
      } else {
        res = await window.pywebview.api.export_hwpx(payload);
      }
      if (res && res.success) {
        alert(res.message || '한글 파일이 바탕화면 [군수실_일정_출력문서] 폴더에 성공적으로 저장되었습니다!');
      } else {
        alert('저장 실패: ' + (res ? res.message : '알 수 없는 오류'));
      }
    } catch (e) {
      alert('한글 문서 생성 중 오류: ' + e.message);
    }
  }

  function triggerOpenFolder() {
    if (window.pywebview && window.pywebview.api) {
      window.pywebview.api.open_export_folder();
    } else {
      alert('바탕화면의 [군수실_일정_출력문서] 폴더를 확인해 주세요.');
    }
  }

  async function triggerCheckUpdate() {
    if (!window.pywebview || !window.pywebview.api) {
      alert('데스크톱 전용 프로그램 환경에서만 GitHub 자동 패치가 지원됩니다.');
      return;
    }

    try {
      const res = await window.pywebview.api.check_update();
      if (!res || !res.success) {
        alert(res ? res.message : '최신 버전 확인 실패');
        return;
      }

      if (res.hasUpdate) {
        const confirmMsg = `🎉 새로운 업데이트가 발견되었습니다!\\n\\n` +
                           `• 현재 버전: v${res.currentVersion}\\n` +
                           `• 최신 버전: v${res.latestVersion}\\n\\n` +
                           `[업데이트 내용]\\n${res.releaseNotes}\\n\\n` +
                           `지금 다운로드하여 자동으로 프로그램을 재실행하시겠습니까?`;
        
        if (confirm(confirmMsg)) {
          alert('새 버전을 다운로드하고 있습니다. 잠시 후 자동으로 프로그램이 재시작됩니다...');
          const applyRes = await window.pywebview.api.apply_update(res.downloadUrl);
          if (!applyRes.success) {
            alert('업데이트 적용 실패: ' + applyRes.message);
          }
        }
      } else {
        alert(`현재 최신 버전(v${res.currentVersion})을 사용하고 있습니다! ✨`);
      }
    } catch (err) {
      alert('업데이트 확인 중 오류 발생: ' + err.message);
    }
  }
"""

marker = "  function escapeHtml(str) {"
if marker in code:
    code = code.replace(marker, native_helpers + "\n" + marker)
    with open(r'C:\Users\I\.gemini\antigravity\scratch\schedule_manager\app.js', 'w', encoding='utf-8') as f:
        f.write(code)
    print("SUCCESS: app.js updated with native export and self-update triggers!")
else:
    print("Could not find marker in app.js")
