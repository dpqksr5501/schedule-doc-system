# -*- coding: utf-8 -*-
with open(r'C:\Users\I\.gemini\antigravity\scratch\schedule_manager\app.js', 'r', encoding='utf-8') as f:
    code = f.read()

old_setup = """  // --- UI 이벤트 바인딩 ---
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

    // 퀵 액션 버튼들
    document.getElementById('btnNewEvent').addEventListener('click', () => openEventModal());
    document.getElementById('btnPrint').addEventListener('click', () => window.print());
    document.getElementById('btnExportExcel').addEventListener('click', exportToExcel);
    document.getElementById('btnBackupData').addEventListener('click', backupData);
    document.getElementById('btnRestoreData').addEventListener('click', () => document.getElementById('fileRestoreInput').click());
    document.getElementById('fileRestoreInput').addEventListener('change', handleFileRestore);

    // 네이티브 HWPX / HWP 내보내기 & 폴더 열기 & 업데이트 체크
    document.getElementById('btnExportHwpx').addEventListener('click', () => triggerNativeExport('hwpx'));
    document.getElementById('btnExportHwp').addEventListener('click', () => triggerNativeExport('hwp'));
    document.getElementById('btnOpenFolder').addEventListener('click', triggerOpenFolder);
    document.getElementById('btnCheckUpdate').addEventListener('click', triggerCheckUpdate);

    // 스마트 한 줄 빠른 입력
    document.getElementById('btnQuickSubmit').addEventListener('click', handleQuickInput);
    document.getElementById('quickInputText').addEventListener('keydown', (e) => {
      if (e.key === 'Enter') handleQuickInput();
    });

    // 휴지통 모달
    setupTrashModal();

    setupModal();
    renderControlBar();
  }"""

new_setup = """  // --- UI 이벤트 바인딩 (Null-Safe) ---
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
  }"""

if old_setup in code:
    code = code.replace(old_setup, new_setup)
    with open(r'C:\Users\I\.gemini\antigravity\scratch\schedule_manager\app.js', 'w', encoding='utf-8') as f:
        f.write(code)
    print("SUCCESS: setupUI updated with null-safe handlers!")
else:
    print("Could not find exact old_setup, trying fallback search...")
    # fallback
    import re
    code = re.sub(r'function setupUI\(\)\s*\{[\s\S]*?renderControlBar\(\);\s*\}', new_setup.strip(), code, count=1)
    with open(r'C:\Users\I\.gemini\antigravity\scratch\schedule_manager\app.js', 'w', encoding='utf-8') as f:
        f.write(code)
    print("Fallback replacement done!")
