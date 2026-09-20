# -*- coding: utf-8 -*-
with open(r'C:\Users\I\.gemini\antigravity\scratch\schedule_manager\app.js', 'r', encoding='utf-8') as f:
    code = f.read()

old_start = '  // --- 상단 컨트롤바 렌더링 ---'
old_end = '  // --- 현재 탭 렌더링 분기 ---'

new_render_bar = '''  // --- 상단 문서 조작 & 출력 툴바 렌더링 ---
  function renderControlBar() {
    const bar = document.getElementById('controlBarArea');
    if (!bar) return;

    let filterHtml = '';
    let outputHtml = '';

    if (currentTab === 'daily') {
      filterHtml = `
        <div class="doc-filter-area">
          <label style="font-weight: 700; color: #334155;">📅 날짜:</label>
          <input type="date" id="dailyDatePicker" class="control-input" value="${selectedDate}">
          <button class="btn btn-outline btn-sm" id="btnDailyPrevDate">◀ 이전일</button>
          <button class="btn btn-outline btn-sm" id="btnDailyToday">오늘</button>
          <button class="btn btn-outline btn-sm" id="btnDailyNextDate">다음일 ▶</button>
          <label style="display: inline-flex; align-items: center; gap: 6px; font-weight: 700; margin-left: 10px; cursor: pointer;">
            <input type="checkbox" id="chkGunsuOnly" ${dailyFilterGunsuOnly ? 'checked' : ''}>
            🟢 ${settings.leaderTitle} 일정만
          </label>
        </div>
      `;
      outputHtml = `
        <div class="doc-output-area">
          <button class="btn btn-print" id="btnPrintAction">🖨️ A4 바로 인쇄</button>
          <button class="btn btn-success" id="btnExportHwpxAction">📄 한글(HWPX) 저장</button>
          <button class="btn btn-outline" id="btnExportHwpAction">📄 HWP 저장</button>
          <button class="btn btn-outline" id="btnOpenFolderAction">📁 저장폴더</button>
        </div>
      `;
    } else if (currentTab === 'weekly') {
      const mon = getMondayOfDate(selectedDate);
      const sun = addDays(mon, 6);
      filterHtml = `
        <div class="doc-filter-area">
          <label style="font-weight: 700; color: #334155;">🗓️ 주차:</label>
          <input type="date" id="weeklyDatePicker" class="control-input" value="${selectedDate}">
          <button class="btn btn-outline btn-sm" id="btnWeeklyPrev">◀ 이전 주</button>
          <span style="font-weight: 800; color: #1e293b; padding: 0 6px;">
            ${mon.slice(5).replace('-', '/')} ~ ${sun.slice(5).replace('-', '/')}
          </span>
          <button class="btn btn-outline btn-sm" id="btnWeeklyNext">다음 주 ▶</button>
          <button class="btn btn-outline btn-sm" id="btnCopyPrevWeek" style="color: #1e40af; border-color: #bfdbfe; background: #eff6ff; font-weight: 700;">
            📋 지난주 복사
          </button>
        </div>
      `;
      outputHtml = `
        <div class="doc-output-area">
          <button class="btn btn-print" id="btnPrintAction">🖨️ A4 바로 인쇄</button>
          <button class="btn btn-success" id="btnExportHwpxAction">📄 한글(HWPX) 저장</button>
          <button class="btn btn-outline" id="btnExportHwpAction">📄 HWP 저장</button>
          <button class="btn btn-outline" id="btnOpenFolderAction">📁 저장폴더</button>
        </div>
      `;
    } else if (currentTab === 'monthly') {
      filterHtml = `
        <div class="doc-filter-area">
          <label style="font-weight: 700; color: #334155;">🗓️ 년/월:</label>
          <select id="selYear" class="control-input">
            <option value="2025" ${selectedYear === 2025 ? 'selected' : ''}>2025년</option>
            <option value="2026" ${selectedYear === 2026 ? 'selected' : ''}>2026년</option>
            <option value="2027" ${selectedYear === 2027 ? 'selected' : ''}>2027년</option>
          </select>
          <select id="selMonth" class="control-input">
            ${Array.from({length: 12}, (_, i) => i + 1).map(m => 
              `<option value="${m}" ${selectedMonth === m ? 'selected' : ''}>${m}월</option>`
            ).join('')}
          </select>
          <button class="btn btn-outline btn-sm" id="btnMonthPrev">◀ 이전달</button>
          <button class="btn btn-outline btn-sm" id="btnMonthNext">다음달 ▶</button>
        </div>
      `;
      outputHtml = `
        <div class="doc-output-area">
          <button class="btn btn-print" id="btnPrintAction">🖨️ A4 바로 인쇄 (가로)</button>
        </div>
      `;
    } else if (currentTab === 'admin') {
      filterHtml = `
        <div class="doc-filter-area">
          <input type="text" id="searchKeyword" class="control-input" style="width: 240px;" placeholder="🔍 행사명, 장소, 부서 검색...">
          <select id="filterAttendee" class="control-input">
            <option value="all">전체 참석 구분</option>
            <option value="gunsu">🟢 ${settings.leaderTitle} 참석</option>
            <option value="v_gunsu">🔵 ${settings.subLeaderTitle} 참석</option>
            <option value="general">⚫ 일반/부서 행사</option>
          </select>
        </div>
      `;
      outputHtml = `
        <div class="doc-output-area">
          <span style="font-weight: 700; color: #475569;">총 <strong id="totalCountText" style="color: var(--primary);">0</strong>건</span>
        </div>
      `;
    }

    bar.innerHTML = filterHtml + outputHtml;

    // 공통 출력 액션 바인딩
    const printBtn = document.getElementById('btnPrintAction');
    if (printBtn) printBtn.addEventListener('click', () => window.print());

    const hwpxBtn = document.getElementById('btnExportHwpxAction');
    if (hwpxBtn) hwpxBtn.addEventListener('click', () => triggerNativeExport('hwpx'));

    const hwpBtn = document.getElementById('btnExportHwpAction');
    if (hwpBtn) hwpBtn.addEventListener('click', () => triggerNativeExport('hwp'));

    const folderBtn = document.getElementById('btnOpenFolderAction');
    if (folderBtn) folderBtn.addEventListener('click', triggerOpenFolder);

    // 각 탭별 필터 이벤트 바인딩
    if (currentTab === 'daily') {
      document.getElementById('dailyDatePicker').addEventListener('change', (e) => {
        selectedDate = e.target.value;
        renderDaily();
      });
      document.getElementById('btnDailyPrevDate').addEventListener('click', () => {
        selectedDate = addDays(selectedDate, -1);
        renderControlBar();
        renderDaily();
      });
      document.getElementById('btnDailyToday').addEventListener('click', () => {
        selectedDate = getTodayString();
        renderControlBar();
        renderDaily();
      });
      document.getElementById('btnDailyNextDate').addEventListener('click', () => {
        selectedDate = addDays(selectedDate, 1);
        renderControlBar();
        renderDaily();
      });
      document.getElementById('chkGunsuOnly').addEventListener('change', (e) => {
        dailyFilterGunsuOnly = e.target.checked;
        renderDaily();
      });
    } else if (currentTab === 'weekly') {
      document.getElementById('weeklyDatePicker').addEventListener('change', (e) => {
        selectedDate = e.target.value;
        renderControlBar();
        renderWeekly();
      });
      document.getElementById('btnWeeklyPrev').addEventListener('click', () => {
        selectedDate = addDays(selectedDate, -7);
        renderControlBar();
        renderWeekly();
      });
      document.getElementById('btnWeeklyNext').addEventListener('click', () => {
        selectedDate = addDays(selectedDate, 7);
        renderControlBar();
        renderWeekly();
      });
      document.getElementById('btnCopyPrevWeek').addEventListener('click', copyPreviousWeekEvents);
    } else if (currentTab === 'monthly') {
      document.getElementById('selYear').addEventListener('change', (e) => {
        selectedYear = parseInt(e.target.value, 10);
        renderMonthly();
      });
      document.getElementById('selMonth').addEventListener('change', (e) => {
        selectedMonth = parseInt(e.target.value, 10);
        renderMonthly();
      });
      document.getElementById('btnMonthPrev').addEventListener('click', () => {
        selectedMonth--;
        if (selectedMonth < 1) { selectedMonth = 12; selectedYear--; }
        renderControlBar();
        renderMonthly();
      });
      document.getElementById('btnMonthNext').addEventListener('click', () => {
        selectedMonth++;
        if (selectedMonth > 12) { selectedMonth = 1; selectedYear++; }
        renderControlBar();
        renderMonthly();
      });
    } else if (currentTab === 'admin') {
      document.getElementById('searchKeyword').addEventListener('input', renderAdmin);
      document.getElementById('filterAttendee').addEventListener('change', renderAdmin);
    }
  }
'''

start_idx = code.find(old_start)
end_idx = code.find(old_end)
if start_idx != -1 and end_idx != -1:
    new_code = code[:start_idx] + new_render_bar + '\n' + code[end_idx:]
    with open(r'C:\Users\I\.gemini\antigravity\scratch\schedule_manager\app.js', 'w', encoding='utf-8') as f:
        f.write(new_code)
    print('SUCCESS: app.js updated!')
else:
    print('FAILED to find markers')
