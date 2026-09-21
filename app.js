// ===================================================
// 군수님 일정표 원스톱 관리 시스템 - 고도화 버전 (v1.0.1)
// With Smart Quick-Input, Previous Week Copy, Trash/Restore,
// and Native Python HWPX/HWP Desktop Integration
// ===================================================

(function() {
  'use strict';

  // --- 상태 관리 ---
  let events = [];
  let deletedEvents = [];
  let settings = {
    title: '군수실 일정표',
    leaderTitle: '군수님',
    subLeaderTitle: '부군수님',
    orgName: '보은군',
    weeklyTitle: '주 간 주 요 행 사 계 획',
    monthlyTitle: '월간 일정표'
  };
  let logos = {
    symbol: '',
    slogan: ''
  };

  let currentTab = 'daily'; // 'daily' | 'weekly' | 'monthly' | 'admin'
  let selectedDate = '2026-07-06';
  let selectedYear = 2026;
  let selectedMonth = 7;
  let dailyFilterGunsuOnly = true;

  const DAY_NAMES = ['일', '월', '화', '수', '목', '금', '토'];

  // --- 초기화 ---
  window.addEventListener('DOMContentLoaded', initApp);

  function initApp() {
    loadData();
    setupUI();
    renderCurrentTab();
  }

  function loadData() {
    if (window.INITIAL_DATA) {
      if (window.INITIAL_DATA.logos) logos = window.INITIAL_DATA.logos;
      if (window.INITIAL_DATA.settings) settings = Object.assign(settings, window.INITIAL_DATA.settings);
    }

    const savedEvents = localStorage.getItem('gunsu_schedule_events');
    const savedTrash = localStorage.getItem('gunsu_schedule_trash');
    const savedSettings = localStorage.getItem('gunsu_schedule_settings');

    if (savedEvents) {
      try { events = JSON.parse(savedEvents); } catch(e) { events = []; }
    } else if (window.INITIAL_DATA && window.INITIAL_DATA.initialEvents) {
      events = JSON.parse(JSON.stringify(window.INITIAL_DATA.initialEvents));
      saveEvents();
    }

    if (savedTrash) {
      try { deletedEvents = JSON.parse(savedTrash); } catch(e) { deletedEvents = []; }
    }

    if (savedSettings) {
      try { settings = Object.assign(settings, JSON.parse(savedSettings)); } catch(e) {}
    }

    const todayStr = getTodayString();
    if (events.some(e => e.date === todayStr)) {
      selectedDate = todayStr;
      selectedYear = parseInt(todayStr.split('-')[0], 10);
      selectedMonth = parseInt(todayStr.split('-')[1], 10);
    }

    updateTrashBadge();
  }

  function saveEvents() {
    localStorage.setItem('gunsu_schedule_events', JSON.stringify(events));
  }

  function saveTrash() {
    localStorage.setItem('gunsu_schedule_trash', JSON.stringify(deletedEvents));
    updateTrashBadge();
  }

  function saveSettings() {
    localStorage.setItem('gunsu_schedule_settings', JSON.stringify(settings));
  }

  function updateTrashBadge() {
    const el = document.getElementById('trashCount');
    if (el) el.textContent = deletedEvents.length;
  }

  // --- 날짜 헬퍼 ---
  function getTodayString() {
    const d = new Date();
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${y}-${m}-${day}`;
  }

  function formatDateKorean(dateStr) {
    const parts = dateStr.split('-');
    const d = new Date(parseInt(parts[0], 10), parseInt(parts[1], 10) - 1, parseInt(parts[2], 10));
    const m = parts[1];
    const day = parts[2];
    const dayName = DAY_NAMES[d.getDay()];
    return `${m}월 ${day}일(${dayName})`;
  }

  function getMondayOfDate(dateStr) {
    const parts = dateStr.split('-');
    const d = new Date(parseInt(parts[0], 10), parseInt(parts[1], 10) - 1, parseInt(parts[2], 10));
    const dayOfWeek = d.getDay();
    const diff = (dayOfWeek === 0 ? -6 : 1 - dayOfWeek);
    d.setDate(d.getDate() + diff);
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${y}-${m}-${day}`;
  }

  function addDays(dateStr, days) {
    const parts = dateStr.split('-');
    const d = new Date(parseInt(parts[0], 10), parseInt(parts[1], 10) - 1, parseInt(parts[2], 10));
    d.setDate(d.getDate() + days);
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${y}-${m}-${day}`;
  }

  // --- UI 이벤트 바인딩 (Null-Safe) ---
  function setupUI() {
    const headerLogo = document.getElementById('headerSloganImg');
    if (headerLogo && logos.slogan) headerLogo.src = logos.slogan;

    // 탭 전환
    document.querySelectorAll('.tab-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        currentTab = btn.dataset.tab;
        renderControlBar();
        renderCurrentTab();
      });
    });

    // 안전한 이벤트 리스너 바인딩 헬퍼
    function bindClick(id, fn) {
      const el = document.getElementById(id);
      if (el) el.addEventListener('click', fn);
    }

    bindClick('btnNewEvent', () => openEventModal());
    bindClick('btnPrint', () => window.print());
    bindClick('btnExportExcel', exportToExcel);
    bindClick('btnBackupData', backupData);
    bindClick('btnRestoreData', () => {
      const fi = document.getElementById('fileRestoreInput');
      if (fi) fi.click();
    });
    
    const fileInp = document.getElementById('fileRestoreInput');
    if (fileInp) fileInp.addEventListener('change', handleFileRestore);

    bindClick('btnOpenManual', triggerOpenManual);
    bindClick('btnExportHwpx', () => triggerNativeExport('hwpx'));
    bindClick('btnExportHwp', () => triggerNativeExport('hwp'));
    bindClick('btnOpenFolder', triggerOpenFolder);
    bindClick('btnCheckUpdate', triggerCheckUpdate);

    // 스마트 빠른 입력 바인딩
    bindClick('btnQuickSubmit', handleQuickInput);
    const qInp = document.getElementById('quickInputText');
    if (qInp) {
      qInp.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') handleQuickInput();
      });
    }

    // 도구 드롭다운 토글
    const toolsBtn = document.getElementById('btnToolsMenu');
    const toolsDrop = document.getElementById('toolsDropdown');
    if (toolsBtn && toolsDrop) {
      toolsBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        toolsDrop.classList.toggle('show');
      });
      document.addEventListener('click', () => {
        toolsDrop.classList.remove('show');
      });
    }

    setupTrashModal();
    setupModal();
    renderControlBar();
  }

  // ===================================================
  // ⚡ 스마트 한 줄 빠른 입력 (Smart One-Liner Parser)
  // ===================================================
  function handleQuickInput() {
    const input = document.getElementById('quickInputText');
    const raw = input.value.trim();
    if (!raw) return;

    // 예: "7/15 14:00 보은읍 순방 군청소회의실 행정운영과"
    let dateStr = selectedDate;
    let timeStr = '10:00';
    let attendee = 'gunsu';
    let textRem = raw;

    // 1. 날짜 추출 (M/D 또는 YYYY-MM-DD)
    const dateMatch = textRem.match(/(\d{4}[-./])?(\d{1,2})[-./](\d{1,2})/);
    if (dateMatch) {
      const curYear = new Date().getFullYear();
      const y = dateMatch[1] ? dateMatch[1].replace(/[-./]/g, '') : curYear;
      const m = String(parseInt(dateMatch[2], 10)).padStart(2, '0');
      const d = String(parseInt(dateMatch[3], 10)).padStart(2, '0');
      dateStr = `${y}-${m}-${d}`;
      textRem = textRem.replace(dateMatch[0], '').trim();
    }

    // 2. 시간 추출 (HH:MM 또는 H시)
    const timeMatch = textRem.match(/(\d{1,2}):(\d{2})/);
    if (timeMatch) {
      const hh = String(parseInt(timeMatch[1], 10)).padStart(2, '0');
      const mm = timeMatch[2];
      timeStr = `${hh}:${mm}`;
      textRem = textRem.replace(timeMatch[0], '').trim();
    } else {
      const hourMatch = textRem.match(/(\d{1,2})시/);
      if (hourMatch) {
        timeStr = `${String(parseInt(hourMatch[1], 10)).padStart(2, '0')}:00`;
        textRem = textRem.replace(hourMatch[0], '').trim();
      }
    }

    // 3. 참석자 구분 파악
    if (textRem.includes('부군수') || textRem.includes('파랑')) {
      attendee = 'v_gunsu';
    } else if (textRem.includes('중요') || textRem.includes('빨강') || textRem.includes('긴급')) {
      attendee = 'important';
    } else if (textRem.includes('일반') || textRem.includes('자체') || textRem.includes('검정')) {
      attendee = 'general';
    }

    // 4. 나머지 텍스트를 공백으로 분리하여 행사명, 장소, 부서 추정
    const tokens = textRem.split(/\s+/).filter(t => t.length > 0);
    let title = '';
    let place = '';
    let dept = '';

    tokens.forEach(tok => {
      if (/과$|실$|소$|센터$/.test(tok) && !dept) {
        if (/회의실$|집무실$/.test(tok)) {
          place = tok;
        } else {
          dept = tok;
        }
      } else if (/회의실$|집무실$|컨벤션$|시장$|운동장$|회관$/.test(tok) && !place) {
        place = tok;
      } else {
        title += (title ? ' ' : '') + tok;
      }
    });

    if (!title) title = '주요 일정';

    const newEv = {
      id: 'evt_' + Date.now(),
      date: dateStr,
      time: timeStr,
      title: title,
      place: place,
      dept: dept,
      attendee: attendee
    };

    events.push(newEv);
    saveEvents();
    input.value = '';
    selectedDate = dateStr;
    renderCurrentTab();

    alert(`✅ 일정이 빠르게 등록되었습니다!\n[${dateStr} ${timeStr}] ${title} (${place || '장소미정'})`);
  }

  // ===================================================
  // 📋 지난주 일정 복사해서 이번 주로 가져오기
  // ===================================================
  function copyPreviousWeekEvents() {
    const curMon = getMondayOfDate(selectedDate);
    const prevMon = addDays(curMon, -7);
    const prevSun = addDays(prevMon, 6);

    // 지난주 일정들 검색
    const prevEvents = events.filter(e => e.date >= prevMon && e.date <= prevSun);
    if (prevEvents.length === 0) {
      alert(`지난주(${prevMon} ~ ${prevSun})에 등록된 일정이 없습니다.`);
      return;
    }

    const curSun = addDays(curMon, 6);
    const msg = `지난주(${prevMon} ~ ${prevSun})의 총 ${prevEvents.length}개 일정을\n이번 주(${curMon} ~ ${curSun})로 복사하시겠습니까?\n\n(※ 요일과 시간, 장소가 그대로 이번 주 날짜에 맞춰 생성됩니다.)`;
    if (!confirm(msg)) return;

    let copiedCount = 0;
    prevEvents.forEach(pe => {
      // 날짜에 정확히 7일 더하기
      const newDate = addDays(pe.date, 7);
      events.push({
        id: 'evt_' + Date.now() + '_' + Math.random().toString(36).substr(2, 4),
        date: newDate,
        time: pe.time,
        title: pe.title,
        place: pe.place,
        dept: pe.dept,
        attendee: pe.attendee
      });
      copiedCount++;
    });

    saveEvents();
    renderCurrentTab();
    alert(`🎉 지난주 일정 ${copiedCount}건이 이번 주로 성공적으로 복사되었습니다!`);
  }

  // ===================================================
  // 📄 Python 네이티브 HWPX / HWP 내보내기 연동
  // ===================================================
  function getWeeklyPayloadForNative() {
    const monday = getMondayOfDate(selectedDate);
    const sunday = addDays(monday, 6);
    const mParts = monday.split('-');
    const sParts = sunday.split('-');
    const periodText = `${mParts[0]}. ${parseInt(mParts[1], 10)}. ${parseInt(mParts[2], 10)}. ~ ${parseInt(sParts[1], 10)}. ${parseInt(sParts[2], 10)}.`;
    const createDateText = `${mParts[0]}. ${parseInt(mParts[1], 10)}. 1.작성`;

    let weekDays = [];
    for (let i = 0; i < 7; i++) {
      const curDate = addDays(monday, i);
      const cParts = curDate.split('-');
      const dObj = new Date(parseInt(cParts[0], 10), parseInt(cParts[1], 10) - 1, parseInt(cParts[2], 10));
      const dayNum = parseInt(cParts[2], 10);
      const dayLabel = `${dayNum}(${DAY_NAMES[dObj.getDay()]})`;

      const dEvents = events.filter(e => e.date === curDate);
      dEvents.sort((a, b) => a.time.localeCompare(b.time));

      weekDays.push({
        dayLabel: dayLabel,
        events: dEvents.map(e => ({
          time: e.time,
          title: e.title,
          place: e.place || '',
          dept: e.dept || '',
          attendee: e.attendee
        }))
      });
    }

    return {
      period_str: periodText,
      created_date_str: createDateText,
      days: weekDays
    };
  }

  function triggerNativeExport(format = 'hwpx') {
    const payload = getWeeklyPayloadForNative();

    // pywebview API가 연결되어 있는지 확인
    if (window.pywebview && window.pywebview.api) {
      const apiMethod = format === 'hwpx' ? window.pywebview.api.export_hwpx : window.pywebview.api.export_hwp;
      apiMethod(payload).then(res => {
        if (res.success) {
          alert(res.message);
        } else {
          alert('오류: ' + res.message);
        }
      }).catch(err => {
        alert('내보내기 통신 중 오류: ' + err);
      });
    } else {
      // 일반 웹 브라우저에서 실행된 경우 안내
      alert(`[알림]\n한글(${format.toUpperCase()}) 자동 생성 엔진은 데스크톱 전용 프로그램 실행 시 100% 무결점으로 동작합니다.\n\n현재 웹 브라우저 화면에서는 상단의 [🖨️ A4 인쇄 / PDF] 버튼으로 즉시 고품질 인쇄나 PDF 저장이 가능합니다!`);
    }
  }

  function triggerOpenFolder() {
    if (window.pywebview && window.pywebview.api) {
      window.pywebview.api.open_export_folder();
    } else {
      alert('바탕화면의 [군수님_일정표_출력문서] 폴더에 저장됩니다.');
    }
  }

  function triggerCheckUpdate() {
    if (window.pywebview && window.pywebview.api) {
      window.pywebview.api.check_update().then(res => {
        if (res.hasUpdate) {
          alert(`🔔 새로운 버전(${res.latestVersion})이 출시되었습니다!\n\n업데이트 내용:\n${res.releaseNotes}`);
        } else {
          alert(`현재 최신 버전(v${res.currentVersion || '1.0.1'})을 사용 중입니다.`);
        }
      });
    } else {
      alert('현재 최신 버전(v1.0.1)입니다.');
    }
  }

  // ===================================================
  // 🗑️ 휴지통 및 복원 관리 (Soft Delete)
  // ===================================================
  function setupTrashModal() {
    const modal = document.getElementById('trashModal');
    const btnOpen = document.getElementById('btnOpenTrash');
    const btnClose = document.getElementById('btnTrashClose');
    const btnDone = document.getElementById('btnTrashDone');
    const btnEmpty = document.getElementById('btnEmptyTrash');

    btnOpen.addEventListener('click', () => {
      renderTrashList();
      modal.classList.add('open');
    });

    btnClose.addEventListener('click', () => modal.classList.remove('open'));
    btnDone.addEventListener('click', () => modal.classList.remove('open'));
    btnEmpty.addEventListener('click', () => {
      if (deletedEvents.length === 0) return;
      if (confirm('휴지통의 모든 일정을 완전히 삭제하시겠습니까? (복구 불가)')) {
        deletedEvents = [];
        saveTrash();
        renderTrashList();
      }
    });
  }

  function renderTrashList() {
    const area = document.getElementById('trashListArea');
    if (deletedEvents.length === 0) {
      area.innerHTML = `<div style="text-align: center; padding: 40px; color: #94a3b8;">휴지통이 비어 있습니다.</div>`;
      return;
    }

    area.innerHTML = deletedEvents.map(ev => `
      <div class="trash-item">
        <div>
          <strong style="color: #334155;">[${ev.date} ${ev.time}]</strong> 
          <span style="font-weight: 600;">${escapeHtml(ev.title)}</span>
          <span style="color: #64748b; font-size: 13px;">(${escapeHtml(ev.place || '장소미정')})</span>
        </div>
        <button class="btn btn-outline btn-sm" onclick="window.restoreEvent('${ev.id}')" style="color: var(--primary);">
          ♻️ 복원
        </button>
      </div>
    `).join('');
  }

  window.restoreEvent = function(id) {
    const ev = deletedEvents.find(e => e.id === id);
    if (ev) {
      deletedEvents = deletedEvents.filter(e => e.id !== id);
      events.push(ev);
      saveEvents();
      saveTrash();
      renderTrashList();
      renderCurrentTab();
      alert(`[${ev.title}] 일정이 정상 복원되었습니다!`);
    }
  };

  // --- 상단 문서 조작 & 출력 툴바 렌더링 ---
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

  // --- 현재 탭 렌더링 분기 ---
  function renderCurrentTab() {
    const stage = document.getElementById('mainStageArea');
    if (!stage) return;

    if (currentTab === 'daily') {
      renderDaily();
    } else if (currentTab === 'weekly') {
      renderWeekly();
    } else if (currentTab === 'monthly') {
      renderMonthly();
    } else if (currentTab === 'admin') {
      renderAdmin();
    }
  }

  // ===================================================
  // 1. 일일 일정표 렌더러 (A4 세로)
  // ===================================================
  function renderDaily() {
    const stage = document.getElementById('mainStageArea');
    
    let dayEvents = events.filter(e => e.date === selectedDate);
    if (dailyFilterGunsuOnly) {
      dayEvents = dayEvents.filter(e => e.attendee === 'gunsu');
    }
    dayEvents.sort((a, b) => a.time.localeCompare(b.time));

    const dateTitleText = formatDateKorean(selectedDate);

    let itemsHtml = '';
    if (dayEvents.length === 0) {
      itemsHtml = `<div class="daily-empty">등록된 일정이 없습니다.</div>`;
    } else {
      itemsHtml = dayEvents.map(ev => `
        <div class="daily-item clickable-item" onclick="window.editEvent('${ev.id}')" title="마우스로 클릭하면 색상 및 내용을 바로 수정합니다">
          <span class="daily-item-bullet">▶</span>
          <span class="daily-item-time">${ev.time}</span>
          <span class="daily-item-title">${escapeHtml(ev.title)}</span>
          <span class="daily-item-place">&lt; ${escapeHtml(ev.place || '')} &gt;</span>
        </div>
      `).join('');
    }

    stage.innerHTML = `
      <div class="preview-stage">
        <div class="a4-paper a4-portrait">
          <div class="daily-document-box">
            <div class="daily-header">
              <div class="daily-header-left">
                ${logos.slogan ? `<img src="${logos.slogan}" class="daily-slogan-img" alt="슬로건">` : ''}
              </div>
              <div class="daily-header-center">
                <h2 class="daily-title-text">${settings.leaderTitle}  일정표</h2>
              </div>
              <div class="daily-header-right">
                [${dateTitleText}]
              </div>
            </div>
            <div class="daily-content-body">
              <div class="daily-items-list">
                ${itemsHtml}
              </div>
            </div>
          </div>
        </div>
      </div>
    `;
  }

  // ===================================================
  // 2. 주간 주요행사계획 렌더러 (A4 세로)
  // ===================================================
  function renderWeekly() {
    const stage = document.getElementById('mainStageArea');
    
    const monday = getMondayOfDate(selectedDate);
    const sunday = addDays(monday, 6);
    
    const mParts = monday.split('-');
    const sParts = sunday.split('-');
    const periodText = `(${mParts[0]}. ${parseInt(mParts[1], 10)}. ${parseInt(mParts[2], 10)}. ~ ${parseInt(sParts[1], 10)}. ${parseInt(sParts[2], 10)}.)`;
    const createDateText = `${mParts[0]}. ${parseInt(mParts[1], 10)}. 1.작성`;

    let weekDays = [];
    for (let i = 0; i < 7; i++) {
      const curDate = addDays(monday, i);
      const cParts = curDate.split('-');
      const dObj = new Date(parseInt(cParts[0], 10), parseInt(cParts[1], 10) - 1, parseInt(cParts[2], 10));
      const dayNum = parseInt(cParts[2], 10);
      const dayLabel = `${dayNum}(${DAY_NAMES[dObj.getDay()]})`;

      const dEvents = events.filter(e => e.date === curDate);
      dEvents.sort((a, b) => a.time.localeCompare(b.time));

      weekDays.push({
        date: curDate,
        dayLabel: dayLabel,
        events: dEvents
      });
    }

    let rowsHtml = '';
    weekDays.forEach(day => {
      if (day.events.length === 0) {
        rowsHtml += `
          <tr>
            <td class="col-date">${day.dayLabel}</td>
            <td class="col-time"></td>
            <td class="col-title"></td>
            <td class="col-place"></td>
            <td class="col-dept"></td>
          </tr>
        `;
      } else {
        const rowSpan = day.events.length;
        day.events.forEach((ev, idx) => {
          const colorClass = ev.attendee === 'gunsu' ? 'color-gunsu' : (ev.attendee === 'v_gunsu' ? 'color-vgunsu' : (ev.attendee === 'important' ? 'color-important' : 'color-general'));
          rowsHtml += `
            <tr class="clickable-item" onclick="window.editEvent('${ev.id}')" title="마우스로 클릭하면 색상 및 내용을 바로 수정합니다">
              ${idx === 0 ? `<td class="col-date" rowspan="${rowSpan}" onclick="event.stopPropagation()">${day.dayLabel}</td>` : ''}
              <td class="col-time ${colorClass}">${ev.time}</td>
              <td class="col-title ${colorClass}">${escapeHtml(ev.title)}</td>
              <td class="col-place ${colorClass}">${escapeHtml(ev.place || '')}</td>
              <td class="col-dept ${colorClass}">${escapeHtml(ev.dept || '')}</td>
            </tr>
          `;
        });
      }
    });

    stage.innerHTML = `
      <div class="preview-stage">
        <div class="a4-paper a4-portrait">
          <div class="weekly-document">
            <div class="weekly-header">
              <div class="weekly-logo-left">
                ${logos.symbol ? `<img src="${logos.symbol}" class="weekly-symbol-img" alt="심볼">` : ''}
              </div>
              <div class="weekly-title-center">
                <h2 class="weekly-main-title">${settings.weeklyTitle}</h2>
                <p class="weekly-sub-period">${periodText}</p>
              </div>
              <div class="weekly-logo-right">
                ${logos.slogan ? `<img src="${logos.slogan}" class="weekly-slogan-img" alt="슬로건">` : ''}
              </div>
            </div>
            <div class="weekly-date-row">
              ${createDateText}
            </div>
            <table class="weekly-table">
              <thead>
                <tr>
                  <th class="col-date">일자</th>
                  <th class="col-time">시간</th>
                  <th class="col-title">행  사  명</th>
                  <th class="col-place">장  소</th>
                  <th class="col-dept">주관/관련부서</th>
                </tr>
              </thead>
              <tbody>
                ${rowsHtml}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    `;
  }

  // ===================================================
  // 3. 월간 일정표 렌더러 (A4 가로)
  // ===================================================
  function renderMonthly() {
    const stage = document.getElementById('mainStageArea');

    const firstDay = new Date(selectedYear, selectedMonth - 1, 1);
    const firstDayOfWeek = firstDay.getDay();
    const diffToMon = (firstDayOfWeek === 0 ? -6 : 1 - firstDayOfWeek);
    const calStart = new Date(selectedYear, selectedMonth - 1, 1 + diffToMon);

    const lastDay = new Date(selectedYear, selectedMonth, 0);
    const lastDayOfWeek = lastDay.getDay();
    const diffToSun = (lastDayOfWeek === 0 ? 0 : 7 - lastDayOfWeek);
    const calEnd = new Date(selectedYear, selectedMonth - 1, lastDay.getDate() + diffToSun);

    const calStartStr = `${String(calStart.getFullYear()).slice(-2)}. ${calStart.getMonth() + 1}. ${calStart.getDate()}(${DAY_NAMES[calStart.getDay()]})`;
    const calEndStr = `${String(calEnd.getFullYear()).slice(-2)}. ${calEnd.getMonth() + 1}. ${calEnd.getDate()}(${DAY_NAMES[calEnd.getDay()]})`;
    const headerTitleText = `${settings.monthlyTitle}  ${calStartStr} ~ ${calEndStr}`;

    let weeks = [];
    let cur = new Date(calStart);
    while (cur <= calEnd) {
      let week = [];
      for (let i = 0; i < 7; i++) {
        const y = cur.getFullYear();
        const m = String(cur.getMonth() + 1).padStart(2, '0');
        const d = String(cur.getDate()).padStart(2, '0');
        const dateStr = `${y}-${m}-${d}`;
        const dayOfWeek = cur.getDay();

        const dEvents = events.filter(e => e.date === dateStr);
        dEvents.sort((a, b) => a.time.localeCompare(b.time));

        week.push({
          dateStr: dateStr,
          dayNum: cur.getDate(),
          monthNum: cur.getMonth() + 1,
          dayOfWeek: dayOfWeek,
          dayLabel: `${cur.getMonth() + 1}/ ${cur.getDate()}(${DAY_NAMES[dayOfWeek]})`,
          isWeekend: (dayOfWeek === 0 || dayOfWeek === 6),
          events: dEvents
        });
        cur.setDate(cur.getDate() + 1);
      }
      weeks.push(week);
    }

    let weeksHtml = weeks.map(week => `
      <tr class="week-row">
        ${week.map(cell => `
          <td>
            <div class="monthly-day-header ${cell.isWeekend ? 'weekend' : ''}">
              <span>${cell.dayLabel}</span>
            </div>
            <div class="monthly-cell-events">
              ${cell.events.map(ev => {
                const color = ev.attendee === 'gunsu' ? '#008000' : (ev.attendee === 'v_gunsu' ? '#0000ff' : (ev.attendee === 'important' ? '#cc0000' : '#000000'));
                const placePart = ev.place ? `(${escapeHtml(ev.place)})` : '';
                return `
                  <div class="monthly-event-item clickable-item" onclick="window.editEvent('${ev.id}')" style="color: ${color};" title="마우스로 클릭하면 색상 및 내용 바로 수정">
                    <span class="monthly-event-time">${ev.time}</span>
                    <span>${escapeHtml(ev.title)}${placePart}</span>
                  </div>
                `;
              }).join('')}
            </div>
          </td>
        `).join('')}
      </tr>
    `).join('');

    stage.innerHTML = `
      <div class="preview-stage">
        <div class="a4-paper a4-landscape">
          <div class="monthly-document">
            <h2 class="monthly-header-title">${headerTitleText}</h2>
            <table class="monthly-table">
              <thead>
                <tr>
                  <th>월</th>
                  <th>화</th>
                  <th>수</th>
                  <th>목</th>
                  <th>금</th>
                  <th class="col-weekend">토</th>
                  <th class="col-weekend">일</th>
                </tr>
              </thead>
              <tbody>
                ${weeksHtml}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    `;
  }

  // ===================================================
  // 4. 전체 일정 관리 테이블 뷰 (Admin Table)
  // ===================================================
  function renderAdmin() {
    const stage = document.getElementById('mainStageArea');
    const keyword = (document.getElementById('searchKeyword') ? document.getElementById('searchKeyword').value.trim() : '');
    const filterAtt = (document.getElementById('filterAttendee') ? document.getElementById('filterAttendee').value : 'all');

    let filtered = events.slice();
    if (keyword) {
      filtered = filtered.filter(e => 
        e.title.includes(keyword) || 
        (e.place && e.place.includes(keyword)) || 
        (e.dept && e.dept.includes(keyword))
      );
    }
    if (filterAtt !== 'all') {
      filtered = filtered.filter(e => e.attendee === filterAtt);
    }

    filtered.sort((a, b) => b.date.localeCompare(a.date) || a.time.localeCompare(b.time));

    const totalCountText = document.getElementById('totalCountText');
    if (totalCountText) totalCountText.textContent = filtered.length;

    let rowsHtml = filtered.map(ev => {
      let badgeHtml = '';
      if (ev.attendee === 'gunsu') badgeHtml = `<span class="attendee-badge badge-gunsu">🟢 ${settings.leaderTitle}</span>`;
      else if (ev.attendee === 'v_gunsu') badgeHtml = `<span class="attendee-badge badge-vgunsu">🔵 ${settings.subLeaderTitle}</span>`;
      else if (ev.attendee === 'important') badgeHtml = `<span class="attendee-badge badge-important">🔴 중요</span>`;
      else badgeHtml = `<span class="attendee-badge badge-general">⚫ 일반</span>`;

      return `
        <tr>
          <td style="font-weight: 700;">${ev.date}</td>
          <td>${ev.time}</td>
          <td style="font-weight: 600;">${escapeHtml(ev.title)}</td>
          <td>${escapeHtml(ev.place || '-')}</td>
          <td>${escapeHtml(ev.dept || '-')}</td>
          <td>${badgeHtml}</td>
          <td>
            <div class="action-btn-group">
              <button class="btn btn-outline btn-sm" onclick="window.editEvent('${ev.id}')">수정</button>
              <button class="btn btn-outline btn-sm" style="color: var(--danger);" onclick="window.deleteEvent('${ev.id}')">삭제</button>
            </div>
          </td>
        </tr>
      `;
    }).join('');

    if (filtered.length === 0) {
      rowsHtml = `<tr><td colspan="7" style="text-align: center; padding: 36px; color: #94a3b8;">일치하는 일정이 없습니다.</td></tr>`;
    }

    stage.innerHTML = `
      <div class="admin-view-panel">
        <div class="table-toolbar">
          <div style="font-size: 16px; font-weight: 800; color: #1e293b;">
            📋 등록된 일정 전체 목록
          </div>
          <button class="btn btn-primary" onclick="window.openEventModal()">➕ 새 일정 등록</button>
        </div>
        <table class="data-table">
          <thead>
            <tr>
              <th style="width: 14%;">날짜</th>
              <th style="width: 10%;">시간</th>
              <th style="width: 32%;">행사명</th>
              <th style="width: 16%;">장소</th>
              <th style="width: 12%;">주관부서</th>
              <th style="width: 10%;">참석 구분</th>
              <th style="width: 6%;">관리</th>
            </tr>
          </thead>
          <tbody>
            ${rowsHtml}
          </tbody>
        </table>
      </div>
    `;
  }

  // ===================================================
  // 일정 등록 및 수정 모달
  // ===================================================
  let editingEventId = null;

  function setupModal() {
    const modal = document.getElementById('eventModal');
    const btnClose = document.getElementById('btnModalClose');
    const btnCancel = document.getElementById('btnModalCancel');
    const form = document.getElementById('eventForm');

    btnClose.addEventListener('click', closeModal);
    btnCancel.addEventListener('click', closeModal);

    // 🎨 대형 컬러 칩 버튼 클릭 이벤트
    document.querySelectorAll('.color-chip-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.color-chip-btn').forEach(b => b.classList.remove('selected'));
        btn.classList.add('selected');
        const val = btn.dataset.val;
        document.getElementById('inputAttendeeVal').value = val;
      });
    });

    document.querySelectorAll('.chip').forEach(chip => {
      chip.addEventListener('click', () => {
        const targetId = chip.dataset.target;
        const targetInput = document.getElementById(targetId);
        if (targetInput) {
          targetInput.value = chip.dataset.val;
          targetInput.focus();
        }
      });
    });

    form.addEventListener('submit', (e) => {
      e.preventDefault();
      saveModalEvent();
    });
  }

  function openEventModal(eventId = null) {
    editingEventId = eventId;
    const modal = document.getElementById('eventModal');
    const titleEl = document.getElementById('modalTitle');

    if (eventId) {
      titleEl.textContent = '일정 수정';
      const ev = events.find(e => e.id === eventId);
      if (ev) {
        document.getElementById('inputEventDate').value = ev.date;
        document.getElementById('inputEventTime').value = ev.time;
        document.getElementById('inputEventTitle').value = ev.title;
        document.getElementById('inputEventPlace').value = ev.place || '';
        document.getElementById('inputEventDept').value = ev.dept || '';
        selectAttendeeOption(ev.attendee || 'gunsu');
      }
    } else {
      titleEl.textContent = '새 일정 등록';
      document.getElementById('inputEventDate').value = selectedDate || getTodayString();
      document.getElementById('inputEventTime').value = '10:00';
      document.getElementById('inputEventTitle').value = '';
      document.getElementById('inputEventPlace').value = '';
      document.getElementById('inputEventDept').value = '';
      selectAttendeeOption('gunsu');
    }

    modal.classList.add('open');
  }

  function selectAttendeeOption(val) {
    document.getElementById('inputAttendeeVal').value = val;
    document.querySelectorAll('.color-chip-btn').forEach(o => {
      if (o.dataset.val === val) o.classList.add('selected');
      else o.classList.remove('selected');
    });
  }

  function closeModal() {
    document.getElementById('eventModal').classList.remove('open');
    editingEventId = null;
  }

  function saveModalEvent() {
    const dateVal = document.getElementById('inputEventDate').value;
    const timeVal = document.getElementById('inputEventTime').value;
    const titleVal = document.getElementById('inputEventTitle').value.trim();
    const placeVal = document.getElementById('inputEventPlace').value.trim();
    const deptVal = document.getElementById('inputEventDept').value.trim();
    const attendeeVal = document.getElementById('inputAttendeeVal').value;

    if (!dateVal || !timeVal || !titleVal) {
      alert('날짜, 시간, 행사명을 모두 입력해주세요.');
      return;
    }

    if (editingEventId) {
      const ev = events.find(e => e.id === editingEventId);
      if (ev) {
        ev.date = dateVal;
        ev.time = timeVal;
        ev.title = titleVal;
        ev.place = placeVal;
        ev.dept = deptVal;
        ev.attendee = attendeeVal;
      }
    } else {
      const newEv = {
        id: 'evt_' + Date.now(),
        date: dateVal,
        time: timeVal,
        title: titleVal,
        place: placeVal,
        dept: deptVal,
        attendee: attendeeVal
      };
      events.push(newEv);
    }

    saveEvents();
    closeModal();
    selectedDate = dateVal;
    renderCurrentTab();
  }

  // 삭제 액션 -> 휴지통으로 이동 (Soft Delete)
  window.deleteEvent = function(id) {
    const target = events.find(e => e.id === id);
    if (!target) return;

    if (confirm(`[${target.title}] 일정을 삭제하시겠습니까?\n(※ 삭제된 일정은 상단 휴지통에서 언제든 복원할 수 있습니다.)`)) {
      events = events.filter(e => e.id !== id);
      deletedEvents.unshift(target);
      saveEvents();
      saveTrash();
      renderCurrentTab();
    }
  };

  window.editEvent = function(id) {
    openEventModal(id);
  };

  window.openEventModal = openEventModal;

  // ===================================================
  // 엑셀 내보내기 & 데이터 백업/복원
  // ===================================================
  function exportToExcel() {
    if (events.length === 0) {
      alert('내보낼 일정이 없습니다.');
      return;
    }

    const headers = ['날짜', '시간', '행사명', '장소', '주관/관련부서', '참석구분'];
    const rows = events.map(e => [
      e.date,
      e.time,
      `"${(e.title || '').replace(/"/g, '""')}"`,
      `"${(e.place || '').replace(/"/g, '""')}"`,
      `"${(e.dept || '').replace(/"/g, '""')}"`,
      e.attendee === 'gunsu' ? settings.leaderTitle : (e.attendee === 'v_gunsu' ? settings.subLeaderTitle : '일반')
    ]);

    const csvContent = '\uFEFF' + [headers.join(','), ...rows.map(r => r.join(','))].join('\r\n');
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `군수실_일정목록_${getTodayString()}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  function backupData() {
    const data = {
      events: events,
      deletedEvents: deletedEvents,
      settings: settings,
      exportTime: new Date().toISOString()
    };
    const jsonStr = JSON.stringify(data, null, 2);
    const blob = new Blob([jsonStr], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `군수실_일정데이터_백업_${getTodayString()}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  function handleFileRestore(e) {
    const file = e.target.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = function(evt) {
      try {
        const data = JSON.parse(evt.target.result);
        if (Array.isArray(data.events)) {
          events = data.events;
          if (Array.isArray(data.deletedEvents)) deletedEvents = data.deletedEvents;
          if (data.settings) settings = Object.assign(settings, data.settings);
          saveEvents();
          saveTrash();
          saveSettings();
          alert('데이터가 성공적으로 복원되었습니다!');
          renderCurrentTab();
        } else {
          alert('올바른 백업 파일 형식이 아닙니다.');
        }
      } catch(err) {
        alert('파일을 읽는 중 오류: ' + err.message);
      }
    };
    reader.readAsText(file);
    e.target.value = '';
  }


  // ===================================================
  // 데스크톱 네이티브 API 연동 (한글 저장 / 폴더열기 / 자가 업데이트)
  // ===================================================
  async function triggerNativeExport(format) {
    if (!window.pywebview || !window.pywebview.api) {
      alert('데스크톱 프로그램 환경에서만 한글(.hwpx/.hwp) 직접 저장이 지원됩니다.\n(상단 [🖨️ A4 바로 인쇄]로 PDF 저장 가능)');
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

  function triggerOpenManual() {
    if (window.pywebview && window.pywebview.api && window.pywebview.api.open_manual) {
      window.pywebview.api.open_manual();
    } else {
      alert('바탕화면 또는 [군수실_일정_출력문서] 폴더 안의 [★ 군수실_일정표_사용설명서.txt] 파일을 열어보세요!');
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
        const confirmMsg = `🎉 새로운 업데이트가 발견되었습니다!\n\n` +
                           `• 현재 버전: v${res.currentVersion}\n` +
                           `• 최신 버전: v${res.latestVersion}\n\n` +
                           `[업데이트 내용]\n${res.releaseNotes}\n\n` +
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

  function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/&/g, '&amp;')
              .replace(/</g, '&lt;')
              .replace(/>/g, '&gt;')
              .replace(/"/g, '&quot;')
              .replace(/'/g, '&#039;');
  }

})();
