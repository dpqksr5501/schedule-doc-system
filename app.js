/* Desktop UI: native persistence is authoritative; preview mode is explicitly temporary. */
(function () {
  'use strict';
  const C = window.ScheduleCore, h = C.escape, $ = id => document.getElementById(id);
  let state = C.empty(), view = 'daily', selected = C.today(), api, information;
  let started = false, starting = false, readOnly = false, working = false, writing = false, writeQueue = Promise.resolve();
  let history = [], draft, originalDraft, listPage = 1, toastTimer, lastFocus;
  const names = {daily: '일일 일정표', weekly: '주간 행사계획', monthly: '월간 일정표', list: '전체 일정 · 검색'};
  const attendeeNames = {gunsu: '군수님 참석', v_gunsu: '부군수님 참석', general: '일반 / 부서 행사'};
  const statusNames = {confirmed: '확정', tentative: '미확정', cancelled: '취소'};
  const preview = new URLSearchParams(location.search).get('preview') === '1';

  function toast(message) { $('toast').textContent = message; $('toast').hidden = false; clearTimeout(toastTimer); toastTimer = setTimeout(() => { $('toast').hidden = true; }, 5500); }
  function notice(message) { $('notice').textContent = message; $('notice').hidden = !message; }
  function check(result) { if (!result || !result.success) throw new Error(result?.message || '작업을 완료하지 못했습니다.'); return result; }
  function errorMessage(error) { toast(error.message || String(error)); $('saveStatus').textContent = '작업 실패 · 내용을 확인해 주세요'; $('saveStatus').style.color = '#a3322d'; }
  async function run(action) { try { await action(); } catch (error) { errorMessage(error); } }
  function setWorking(value) { working = value; updateControls(); }
  function updateControls() {
    const disabled = working || writing || readOnly || !started;
    for (const id of ['newBtn', 'guideNewBtn', 'hintNewBtn', 'quickBtn', 'saveEventBtn', 'deleteBtn', 'copyBtn']) $(id).disabled = disabled;
    $('undoBtn').disabled = disabled || !history.length;
    for (const id of ['hwpxBtn', 'hwpBtn', 'printBtn']) $(id).disabled = disabled || view === 'list';
    for (const id of ['selectedDate', 'gunsuOnly', 'includeNotes', 'includeAnnotation', 'weekendPair', 'prevBtn', 'nextBtn', 'todayBtn']) $(id).disabled = working || writing;
    document.querySelectorAll('#viewNav button').forEach(button => { button.disabled = working || writing; });
  }
  function savedStatus() {
    $('saveStatus').textContent = state.savedAt ? '저장 완료 · ' + new Date(state.savedAt).toLocaleTimeString('ko-KR', {hour: '2-digit', minute: '2-digit'}) : '이 PC에 자동 저장됩니다';
    $('saveStatus').style.color = '';
    document.body.classList.toggle('large-text', state.settings.fontSize === 'large');
  }
  function commit(change, track = true) {
    const operation = writeQueue.then(async () => {
      if (readOnly) throw new Error('백업을 복원한 뒤 일정을 입력해 주세요.');
      if (working) throw new Error('현재 작업이 완료된 뒤 다시 시도해 주세요.');
      writing = true; updateControls(); $('saveStatus').textContent = '저장 중…';
      const before = structuredClone(state), next = structuredClone(state);
      try {
        change(next);
        const result = check(await api.save_persistent_data(JSON.stringify(next), state.revision));
        state = result.snapshot;
        if (track) { history.push(before); history = history.slice(-30); }
        savedStatus(); render(); return result;
      } finally { writing = false; updateControls(); }
    });
    writeQueue = operation.catch(() => {});
    return operation;
  }
  async function undo() {
    if (!history.length) return;
    const previous = structuredClone(history[history.length - 1]);
    await commit(next => { next.events = previous.events; next.deletedEvents = previous.deletedEvents; next.settings = previous.settings; }, false);
    history.pop(); updateControls(); toast('최근 변경을 되돌렸습니다.');
  }
  async function confirmAction(title, message, button = '계속') {
    $('confirmTitle').textContent = title; $('confirmMessage').textContent = message; $('confirmYes').textContent = button;
    const dialog = $('confirmDialog'); dialog.showModal();
    return new Promise(resolve => {
      let done = false;
      const finish = value => { if (done) return; done = true; dialog.close(); $('confirmYes').onclick = null; $('confirmNo').onclick = null; dialog.removeEventListener('cancel', cancel); resolve(value); };
      const cancel = event => { event.preventDefault(); finish(false); };
      $('confirmYes').onclick = () => finish(true); $('confirmNo').onclick = () => finish(false); dialog.addEventListener('cancel', cancel);
    });
  }
  function utility(title, body) { $('utilityTitle').textContent = title; $('utilityBody').innerHTML = body; if (!$('utilityDialog').open) $('utilityDialog').showModal(); }
  function closeUtility() { $('utilityDialog').close(); }
  function periodText() { const [a, b] = C.range(view, selected); return a === b ? `${a.replace(/-/g, '. ')} (${C.label(a).slice(-2, -1)})` : `${a.replace(/-/g, '. ')} ~ ${b.replace(/-/g, '. ')}`; }
  function color(event) { return event.attendee; }
  function eventButton(event, content) { return `<button class="event-link ${color(event)}" data-edit="${h(event.id)}">${content}</button>`; }
  let previewSequence = 0;
  function documentRequest() {
    return {view, date: selected, gunsuOnly: $('gunsuOnly').checked,
      weekendPair: $('weekendPair').checked, includeAnnotation: $('includeAnnotation').checked,
      includeNotes: $('includeNotes').checked};
  }
  function unit(value) { return `${value * 25.4 / 7200}mm`; }
  function updateUsageGuide(plan) {
    const tip = $('guideTip');
    $('documentHint').hidden = true;
    if (readOnly) { tip.textContent = '일정 데이터를 읽지 못했습니다. 백업 · 복원 · 업데이트에서 복원 방법을 확인해 주세요.'; return; }
    if (!state.events.length) tip.textContent = '첫 일정부터 입력해 보세요. 일정 저장은 입력 내용 보관이고, 한글 저장은 배부할 문서를 만드는 기능입니다.';
    else if (view === 'list') tip.textContent = '행사명·장소·메모로 찾을 수 있습니다. 한글 문서를 만들려면 왼쪽에서 일일·주간·월간을 선택하세요.';
    else if (plan) {
      if (!plan.eventCount) {
        tip.textContent = state.events.length ? '선택한 기간에 출력할 일정이 없습니다. 날짜와 참석 구분을 확인해 주세요.' : '날짜를 고르고 첫 일정을 입력해 주세요.';
      } else if ($('includeNotes').checked) tip.textContent = '상세 업무자료가 별도 페이지에 붙습니다. 참석자·연락사항·내부 메모를 배부해도 되는지 확인한 뒤 저장하세요.';
      else if ($('includeAnnotation').checked) tip.textContent = '행사 아래에 짧은 출력 주석이 들어갑니다. 주석 내용을 확인한 뒤 한글 저장 (.hwp)을 누르세요.';
      else tip.textContent = '날짜·시간·장소를 확인한 뒤 한글 저장 (.hwp)을 누르세요. 주석과 내부 메모는 기본 문서에 포함되지 않습니다.';
    } else tip.textContent = '양식과 날짜를 선택해 미리보기를 확인해 주세요.';
    if (plan && !plan.eventCount) {
      $('documentHint').hidden = false;
      $('documentHintText').textContent = !state.events.length ? '아직 일정이 없습니다. 첫 일정을 입력하면 일간·주간·월간에 함께 반영됩니다.' : view === 'daily' && $('gunsuOnly').checked ? '이 날짜에 군수님 참석으로 등록된 일정이 없습니다. 날짜를 바꾸거나 군수님 참석만 체크를 해제해 보세요.' : '선택한 기간에 출력할 일정이 없습니다. 날짜를 바꾸거나 전체 일정에서 찾아보세요. 취소 일정은 일반 일정표에 표시되지 않습니다.';
      $('hintNewBtn').hidden = !!state.events.length;
      $('hintFindBtn').hidden = !state.events.length;
      $('hintFindBtn').disabled = working || writing;
    }
  }
  function fitPapers() {
    const stage = $('documentStage'), available = stage.clientWidth;
    stage.querySelectorAll('.paper-frame').forEach(frame => {
      const paper = frame.firstElementChild;
      const scale = $('fitPaper').checked ? Math.min(1, available / paper.offsetWidth) : 1;
      paper.style.transform = `scale(${scale})`;
      frame.style.width = `${paper.offsetWidth * scale}px`;
      frame.style.height = `${paper.offsetHeight * scale}px`;
    });
  }
  function planCell(cell, row) {
    const borders = {L: 'left', R: 'right', T: 'top', B: 'bottom'};
    let style = `width:${unit(cell.width)};font-size:${cell.font / 100}pt;color:${cell.color};font-weight:${cell.bold ? 700 : 400};text-align:${cell.align.toLowerCase()};`;
    style += `vertical-align:${row.kind.endsWith('header') || cell.rowSpan > 1 ? 'middle' : 'top'};`;
    for (const [side, name] of Object.entries(borders)) style += `border-${name}:${cell.borders.includes(side) ? '0.1mm solid #000' : '0'};`;
    if (cell.fill) style += `background:${cell.fill};`;
    let content = cell.segments ? cell.segments.map(segment => `<span class="plan-text-segment" style="font-size:${segment.font / 100}pt;color:${segment.color || cell.color};font-weight:${(segment.bold ?? cell.bold) ? 700 : 400}">${h(segment.text)}</span>`).join('') : h(cell.text);
    if (cell.picture) {
      const symbol = cell.picture === 'symbol';
      const width = Math.min(cell.width - 700, symbol ? 5600 : 14500);
      const height = Math.min(row.height - 600, Math.round(width * (symbol ? 749 / 777 : 1157 / 3392)));
      content = `<img src="assets/boeun-${symbol ? 'symbol' : 'slogan'}.png" alt="보은군" style="width:${unit(width)};height:${unit(height)}">`;
    } else if (cell.eventId) content = `<button class="plan-event" data-edit="${h(cell.eventId)}">${content}</button>`;
    return `<td colspan="${cell.span}" rowspan="${cell.rowSpan}" style="${style}">${content}</td>`;
  }
  async function renderDocument() {
    const sequence = ++previewSequence, request = documentRequest();
    const stage = $('documentStage'); stage.setAttribute('aria-busy', 'true');
    try {
      const result = check(await api.preview_document(request));
      if (sequence !== previewSequence || view === 'list') return;
      const plan = result.plan;
      stage.innerHTML = plan.pages.map((page, index) => `<div class="paper-frame"><section class="paper plan-paper ${page.landscape ? 'landscape' : ''}" aria-label="${h(plan.title)} ${index + 1}쪽">
        <table class="plan-table ${h(page.kind)}" style="width:${unit(page.width)}"><colgroup>${page.grid.map(width => `<col style="width:${width / page.width * 100}%">`).join('')}</colgroup><tbody>${page.rows.map(row => `<tr class="plan-${h(row.kind)}" style="height:${unit(row.height)}">${row.cells.map(cell => planCell(cell,row)).join('')}</tr>`).join('')}</tbody></table>
        <div class="paper-footer"><span>${page.kind === 'reference' ? '업무 참고자료 · 내부 공유용' : '일정 변경 내용 확인 후 사용'}</span><span>${index + 1} / ${plan.pages.length}쪽</span></div></section></div>`).join('');
      fitPapers();
      $('documentCount').textContent = `${plan.eventCount.toLocaleString()}건 · ${plan.pages.length}쪽${request.includeNotes ? ' (업무 참고자료 포함)' : ''}`;
      updateUsageGuide(plan);
      return true;
    } catch (error) {
      if (sequence === previewSequence && view !== 'list') stage.innerHTML = `<div class="notice" role="alert">미리보기를 만들지 못했습니다. ${h(error.message)}</div>`;
      return false;
    } finally { if (sequence === previewSequence) stage.setAttribute('aria-busy', 'false'); }
  }
  function renderList() {
    const query = $('searchInput').value.trim().toLocaleLowerCase(), status = $('listStatus').value;
    const events = state.events.filter(e => (status === 'all' || e.status === status) && (!query || [e.title, e.place, e.dept, e.annotation, e.participants, e.preparation, e.notes, e.contact].some(v => v.toLocaleLowerCase().includes(query))))
      .sort((a, b) => b.date.localeCompare(a.date) || a.time.localeCompare(b.time));
    const pages = Math.max(1, Math.ceil(events.length / 50)); listPage = Math.min(listPage, pages);
    $('documentCount').textContent = `검색 결과 ${events.length.toLocaleString()}건`;
    const body = events.slice((listPage - 1) * 50, listPage * 50).map(e => `<tr><td>${h(e.date)}<br><span class="subtle">${h(e.time)}${e.endTime ? ' ~ ' + h(e.endTime) : ''}</span></td><td>${eventButton(e, h((e.priority === 'important' ? '[중요] ' : '') + e.title))}${C.noteText(e) ? '<span class="memo-marker">업무 메모 있음</span>' : ''}</td><td>${h(e.place || '장소 미정')}<br><span class="subtle">${h(e.dept)}</span></td><td><span class="badge">${h(attendeeNames[e.attendee])}</span><br><span class="badge ${h(e.status)}">${h(statusNames[e.status])}</span></td><td><button class="button quiet" data-edit="${h(e.id)}">수정</button></td></tr>`).join('');
    $('documentStage').innerHTML = '<div class="list-card"><table class="list-table"><thead><tr><th>일자 / 시간</th><th>행사명</th><th>장소 / 부서</th><th>참석 / 상태</th><th>관리</th></tr></thead><tbody>' + (body || '<tr><td colspan="5" class="empty-row">조건에 맞는 일정이 없습니다.</td></tr>') + '</tbody></table></div>';
    $('listPagination').innerHTML = `<button class="button secondary" data-page="${listPage - 1}" ${listPage === 1 ? 'disabled' : ''}>이전</button><span>${listPage} / ${pages}쪽</span><button class="button secondary" data-page="${listPage + 1}" ${listPage === pages ? 'disabled' : ''}>다음</button>`;
  }
  function render() {
    updateUsageGuide();
    $('viewTitle').textContent = names[view]; $('selectedDate').value = selected; $('periodLabel').textContent = periodText();
    $('gunsuFilter').hidden = view !== 'daily'; $('weekendFilter').hidden = view !== 'daily' || ![0,6].includes(C.dateObject(selected).getDay()); $('copyBtn').hidden = view !== 'weekly'; $('listControls').hidden = view !== 'list'; $('listPagination').hidden = view !== 'list';
    $('trashCount').textContent = state.deletedEvents.length; $('orgLabel').textContent = state.settings.orgName + ' · 업무 도우미';
    $('viewNav').querySelectorAll('[data-view]').forEach(button => { button.classList.toggle('active', button.dataset.view === view); button.setAttribute('aria-current', button.dataset.view === view ? 'page' : 'false'); });
    if (view === 'list') { previewSequence++; $('documentStage').setAttribute('aria-busy', 'false'); renderList(); }
    else { renderDocument(); }
    $('noteHint').textContent = $('includeNotes').checked ? '상세 메모는 뒤쪽 업무 참고자료에 붙습니다.' : $('includeAnnotation').checked ? '행사 아래에 출력 주석만 표시합니다.' : '기본 문서에는 주석과 내부 메모가 빠집니다.';
    updateControls();
  }
  function renderChecks() { $('checklistEditor').innerHTML = draft.checklist.map(check => `<div class="check-row" data-check="${h(check.id)}"><input type="checkbox" aria-label="준비 완료" ${check.done ? 'checked' : ''}><input type="text" maxlength="500" aria-label="준비 확인 사항" value="${h(check.text)}" placeholder="예: 인사말 자료 준비"><button type="button" class="icon-button" data-remove-check="${h(check.id)}" aria-label="확인 사항 제거">×</button></div>`).join(''); }
  function openEvent(event = null) {
    if (working || writing || readOnly) return;
    draft = structuredClone(event || C.newEvent(selected)); originalDraft = structuredClone(draft);
    lastFocus = document.activeElement; $('eventForm').reset(); $('eventError').hidden = true;
    for (const key of ['date','time','endTime','title','place','dept','attendee','priority','status','annotation','participants','preparation','contact','notes']) $('eventForm').elements.namedItem(key).value = draft[key] || '';
    $('eventDialogTitle').textContent = state.events.some(e => e.id === draft.id) ? '일정 · 업무 메모 수정' : '새 일정 등록';
    $('deleteBtn').hidden = !state.events.some(e => e.id === draft.id); renderChecks(); $('eventDialog').showModal();
    if (api.set_editing) run(() => api.set_editing(true));
    $('eventForm').elements.namedItem('title').focus();
  }
  function readDraft() {
    const next = structuredClone(draft);
    for (const key of ['date','time','endTime','title','place','dept','attendee','priority','status','annotation','participants','preparation','contact','notes']) next[key] = $('eventForm').elements.namedItem(key).value.trim();
    next.checklist = [...$('checklistEditor').querySelectorAll('[data-check]')].map(row => ({id: row.dataset.check, text: row.querySelector('input[type=text]').value.trim(), done: row.querySelector('input[type=checkbox]').checked}));
    return next;
  }
  async function closeEvent() {
    if (writing) return;
    if (draft && JSON.stringify(readDraft()) !== JSON.stringify(originalDraft) && !await confirmAction('입력 내용을 닫을까요?', '아직 저장하지 않은 변경 내용이 있습니다. 닫으면 이번에 입력한 내용은 저장되지 않습니다.', '저장하지 않고 닫기')) return;
    $('eventDialog').close(); draft = null; lastFocus?.focus();
    if (api.set_editing) await api.set_editing(false);
  }
  async function saveEvent() {
    try {
      const event = C.validateEvent(readDraft());
      if (event.checklist.some(c => !c.text)) throw new Error('확인 목록의 내용을 입력하거나 빈 항목을 제거해 주세요.');
      const conflicts = C.conflicts(state.events, event);
      if (conflicts.length && !await confirmAction('시간이 겹치는 일정이 있습니다', conflicts.map(e => `${e.time} ${e.title}`).join('\n') + '\n\n확인 후 이 일정도 저장할까요?', '확인 후 저장')) return;
      event.updatedAt = new Date().toISOString();
      await commit(next => { const index = next.events.findIndex(e => e.id === event.id); if (index >= 0) next.events[index] = event; else next.events.push(event); });
      selected = event.date; $('eventDialog').close(); draft = null; render(); toast('일정을 저장했습니다. 한글 문서는 [한글 저장 (.hwp)]으로 새로 만드세요.');
      if (api.set_editing) await api.set_editing(false);
    } catch (error) { $('eventError').textContent = error.message; $('eventError').hidden = false; $('eventError').scrollIntoView({block: 'nearest'}); errorMessage(error); }
  }
  async function deleteEvent() {
    if (!await confirmAction('일정을 휴지통으로 옮길까요?', draft.title + '\n삭제 후에도 휴지통에서 복원할 수 있습니다.', '휴지통으로 이동')) return;
    const id = draft.id;
    await commit(next => { const index = next.events.findIndex(e => e.id === id); if (index >= 0) next.deletedEvents.unshift({...next.events.splice(index, 1)[0], deletedAt: new Date().toISOString()}); });
    $('eventDialog').close(); draft = null; toast('휴지통으로 이동했습니다. 되돌리기로도 복원할 수 있습니다.');
    if (api.set_editing) await api.set_editing(false);
  }
  function showTrash() {
    utility('삭제된 일정 휴지통', '<p class="subtle">삭제한 일정의 업무 메모와 확인 목록도 함께 복원됩니다.</p>' + (state.deletedEvents.length ? state.deletedEvents.map(e => `<div class="trash-row"><div><strong>${h(e.title)}</strong><small>${h(e.date)} ${h(e.time)} · ${h(e.place || '장소 미정')}</small></div><button class="button secondary" data-restore-event="${h(e.id)}">복원</button></div>`).join('') : '<p>휴지통이 비어 있습니다.</p>'));
  }
  async function restoreEvent(id) { await commit(next => { const index = next.deletedEvents.findIndex(e => e.id === id); if (index >= 0) { const event = next.deletedEvents.splice(index, 1)[0]; delete event.deletedAt; next.events.push(event); } }); showTrash(); toast('일정과 메모를 복원했습니다.'); }
  function showCopy() {
    const start = C.addDays(C.monday(selected), -7), end = C.addDays(start, 6);
    const events = state.events.filter(e => e.date >= start && e.date <= end && e.status !== 'cancelled').sort((a,b) => a.date.localeCompare(b.date) || a.time.localeCompare(b.time));
    utility('지난주 일정 가져오기', `<p class="subtle">${h(start)} ~ ${h(end)}에서 선택한 일정을 다음 주 같은 요일로 옮겨 복사합니다. 동일한 일정은 건너뛰고, 새 일정은 미확정으로 등록합니다.</p>` + (events.length ? events.map(e => `<div class="copy-row"><label><input type="checkbox" data-copy-id="${h(e.id)}" checked>${h(C.label(e.date))} ${h(e.time)} ${h(e.title)}</label></div>`).join('') + '<label class="checkbox-label"><input type="checkbox" id="copyDetails"> 참석 예정자와 업무 메모도 함께 복사 (확인 목록은 미완료로 변경)</label><button class="button primary" data-action="copy">선택한 일정 가져오기</button>' : '<p>지난주에 등록된 일정이 없습니다.</p>'));
  }
  async function copySelected() {
    const ids = [...$('utilityBody').querySelectorAll('[data-copy-id]:checked')].map(el => el.dataset.copyId), details = $('copyDetails').checked;
    let outcome;
    await commit(next => { outcome = C.copyWeek(next, ids, selected, details); next.events.push(...outcome.added); });
    closeUtility(); toast(`${outcome.added.length}건을 가져왔습니다. 중복 ${outcome.skipped}건은 건너뛰었습니다.`);
  }
  async function showTools() {
    const result = check(await api.list_backups());
    utility('백업 · 복원 · 프로그램 관리', `<section class="utility-section"><h3>내 일정 백업</h3><p>일정, 휴지통, 업무 메모를 하나의 백업 파일로 보관합니다.</p><div class="utility-actions"><button class="button primary" data-action="backup">지금 백업하기</button><button class="button secondary" data-action="restore-file">백업 파일 선택</button></div></section><section class="utility-section"><h3>자동 백업에서 복원</h3><p>최근 저장 이전의 상태를 60개까지 보관합니다. 선택하면 복원할 내용부터 확인합니다.</p>${result.items.length ? result.items.map(item => `<div class="backup-row"><div><strong>${h(item.savedAt ? new Date(item.savedAt).toLocaleString('ko-KR') : '이전 데이터')}</strong><small>일정 ${item.count}건 · 저장 순서 ${item.revision}</small></div><button class="button secondary" data-backup="${h(item.id)}">내용 확인</button></div>`).join('') : '<p>첫 일정 저장 후 자동 백업이 쌓입니다.</p>'}</section><section class="utility-section"><h3>화면 글자 크기</h3><div class="utility-actions"><button class="button secondary" data-font="normal">기본 크기</button><button class="button secondary" data-font="large">크게 보기</button></div></section><section class="utility-section"><h3>프로그램 업데이트</h3><p>현재 v${h(information.version)} · 확인 후 직접 선택할 때만 새 버전을 적용합니다.</p><button class="button secondary" data-action="update">새 버전 확인</button><div id="updateResult"></div></section>`);
  }
  function showHelp() {
    utility('사용 방법 · 파일 저장 위치', `<section class="utility-section"><h3>처음에는 세 가지만 기억하세요.</h3><p>① 새 일정을 입력하고 저장합니다.<br>② 일일·주간·월간 양식을 고릅니다.<br>③ 한글 저장 (.hwp) 또는 인쇄를 누릅니다.</p><p>화면의 일정을 누르면 참석 예정자, 준비사항, 업무 메모와 확인 목록을 함께 수정할 수 있습니다.</p></section><section class="utility-section"><h3>바탕화면 출력 폴더</h3><p>기본 한글 저장은 실제 HWP 파일을 만듭니다. 한글의 접근 승인창이 나타나면 경로를 확인하고 허용해 주세요. 한글 파일은 양식별 폴더에, 백업 파일은 데이터백업 폴더에 보관합니다.</p><div class="path-box">${h(information.outputPath)}</div><button class="button primary" data-action="folder">저장 폴더 열기</button></section><section class="utility-section"><h3>프로그램과 일정 데이터</h3><p>배포 실행 파일을 처음 열면 바탕화면 실행 바로가기가 준비됩니다. 프로그램 파일과 일정은 서로 다른 곳에 보관되므로 업데이트 후에도 일정을 유지합니다.</p><div class="path-box">프로그램: ${h(information.appPath)}<br>일정 데이터: ${h(information.dataPath)}</div></section><section class="utility-section"><h3>업무 메모와 출력</h3><p>메모는 기본 한글 문서와 인쇄물에서 빠집니다. 일정표에는 ‘출력 주석 포함’으로 짧은 안내만 넣을 수 있습니다. 자세한 참석자·준비사항·메모는 ‘상세 업무자료 첨부’를 선택하면 뒤쪽 참고자료에 붙습니다. 전체 데이터 백업에는 메모도 포함됩니다.</p><button class="button secondary" data-action="manual">자세한 사용설명서 열기</button></section>`);
  }
  async function previewRestore(content) {
    const summary = check(await api.preview_restore(content));
    const message = `일정 ${summary.count}건 / 휴지통 ${summary.trashCount}건\n기간: ${summary.firstDate || '없음'} ~ ${summary.lastDate || '없음'}\n백업 시각: ${summary.savedAt || '기록 없음'}\n\n현재 일정을 이 백업의 내용으로 교체합니다. 현재 데이터는 자동 백업으로 보관합니다.`;
    if (!await confirmAction('백업 내용을 확인해 주세요', message, '이 내용으로 복원')) return;
    await writeQueue; setWorking(true);
    try { const before = readOnly ? null : structuredClone(state); state = check(await api.restore_data(content, state.revision)).snapshot; readOnly = false; if (before) { history.push(before); history = history.slice(-30); } savedStatus(); notice('백업을 복원했습니다. 일정 날짜와 메모를 확인해 주세요.'); render(); closeUtility(); toast('백업 데이터 복원을 완료했습니다.'); }
    finally { setWorking(false); }
  }
  async function exportDocument(format) {
    await writeQueue;
    const request = documentRequest(); const rangeDate = view === 'daily' && request.weekendPair && C.dateObject(selected).getDay() === 0 ? C.addDays(selected, -1) : selected; let events = C.filterEvents(state, view, rangeDate, request.gunsuOnly); if (view === 'daily' && request.weekendPair && [0,6].includes(C.dateObject(selected).getDay())) events = events.concat(C.filterEvents(state, view, C.addDays(rangeDate, 1), request.gunsuOnly));
    const issues = [events.filter(e => !e.place).length ? `장소 미정 ${events.filter(e => !e.place).length}건` : '', events.filter(e => e.status === 'tentative').length ? `미확정 ${events.filter(e => e.status === 'tentative').length}건` : '', $('includeNotes').checked ? '뒤쪽 업무 참고자료에 내부 참석자·준비사항·연락사항 포함' : '', $('includeAnnotation').checked ? '행사 아래 출력 주석 포함' : ''].filter(Boolean);
    if (issues.length && !await confirmAction('출력 내용을 확인해 주세요', issues.join('\n') + '\n\n이 내용으로 문서를 저장할까요?', '문서 저장')) return;
    setWorking(true); $('saveStatus').textContent = format === 'hwp' ? 'HWP 저장 중 · 한글 접근 승인창을 확인하세요 (최대 90초)' : 'HWPX 문서를 저장하는 중…';
    try {
      const result = await api.export_document(request, format);
      if (result.path) {
        $('lastOutputText').textContent = result.message + '\n' + result.path;
        $('lastOutputBtn').textContent = result.fallback ? 'HWPX 중간 문서 보기' : '저장한 파일 보기';
        $('lastOutput').hidden = false;
      }
      check(result);
      toast(result.message);
    }
    finally { setWorking(false); savedStatus(); }
  }
  async function printDocument() {
    await writeQueue;
    if ($('includeNotes').checked && !await confirmAction('업무 메모 포함 인쇄', '참석 예정자와 내부 준비사항·메모도 인쇄합니다. 내부 공유용 자료가 맞는지 확인해 주세요.', '인쇄 준비')) return;
    setWorking(true);
    try {
      if (!await renderDocument()) throw new Error('미리보기를 확인한 뒤 다시 인쇄해 주세요.');
      let style = $('printPageRule'); if (!style) { style = document.createElement('style'); style.id = 'printPageRule'; document.head.append(style); }
      style.textContent = `@page { size: A4 ${view === 'monthly' ? 'landscape' : 'portrait'}; margin: 5mm; }`;
      await new Promise(resolve => requestAnimationFrame(resolve));
      window.print();
    } finally { setWorking(false); }
  }
  async function checkUpdate() {
    const target = $('updateResult'); target.textContent = '새 버전을 확인하는 중…';
    const result = await api.check_update();
    if (!result.success) { target.textContent = result.message; return; }
    if (!result.hasUpdate) { target.textContent = '현재 정식 버전을 사용하고 있습니다.'; return; }
    target.textContent = `새 버전 v${result.latestVersion}\n${result.releaseNotes || ''}${result.canApply ? '' : '\n' + result.message}`;
    if (result.canApply && await confirmAction('새 버전을 적용할까요?', `v${information.version} → v${result.latestVersion}\n일정은 그대로 유지하고 프로그램을 다시 시작합니다. 기존 버전도 복구용으로 보관합니다.`, '다운로드 후 재시작')) {
      await writeQueue; setWorking(true); target.textContent = '파일을 다운로드하고 확인하는 중입니다. 이 창을 잠시 유지해 주세요.';
      try { check(await api.apply_update()); toast('새 버전을 시작합니다.'); } catch (error) { setWorking(false); throw error; }
    }
  }
  function movePeriod(direction) { const d = C.dateObject(selected); if (view === 'monthly') { d.setDate(1); d.setMonth(d.getMonth() + direction); selected = C.dateString(d); } else selected = C.addDays(selected, direction * (view === 'weekly' ? 7 : 1)); render(); }
  function bind() {
    $('viewNav').addEventListener('click', event => { const button = event.target.closest('[data-view]'); if (button) { view = button.dataset.view; listPage = 1; render(); } });
    const click = (id, action) => $(id).addEventListener('click', () => run(action));
    click('newBtn', () => openEvent()); click('undoBtn', undo); click('todayBtn', () => { selected = C.today(); render(); }); click('prevBtn', () => movePeriod(-1)); click('nextBtn', () => movePeriod(1));
    click('guideNewBtn', () => openEvent()); click('hintNewBtn', () => openEvent()); click('guideHelpBtn', showHelp);
    click('hintFindBtn', () => { if (working || writing) return; view = 'list'; listPage = 1; $('searchInput').value = ''; $('listStatus').value = 'all'; render(); $('searchInput').focus(); });
    click('quickBtn', () => { const event = C.quickInput($('quickInput').value, selected); openEvent(event); });
    $('quickInput').addEventListener('keydown', event => { if (event.key === 'Enter' && !event.isComposing) { event.preventDefault(); $('quickBtn').click(); } });
    $('selectedDate').addEventListener('change', () => run(() => { C.dateObject($('selectedDate').value); selected = $('selectedDate').value; render(); }));
    for (const id of ['gunsuOnly','includeNotes','includeAnnotation','weekendPair']) $(id).addEventListener('change', render);
    $('fitPaper').addEventListener('change', fitPapers); window.addEventListener('resize', fitPapers);
    click('trashBtn', showTrash); click('toolsBtn', showTools); click('helpBtn', showHelp); click('copyBtn', showCopy); click('folderBtn', async () => check(await api.open_export_folder())); click('lastOutputBtn', async () => check(await api.open_last_output()));
    click('hwpxBtn', () => exportDocument('hwpx')); click('hwpBtn', () => exportDocument('hwp')); click('printBtn', printDocument); click('csvBtn', async () => { const result = check(await api.export_csv()); toast(result.message); });
    $('documentStage').addEventListener('click', event => { const button = event.target.closest('[data-edit]'); if (button) openEvent(state.events.find(e => e.id === button.dataset.edit)); });
    $('listPagination').addEventListener('click', event => { const button = event.target.closest('[data-page]'); if (button) { listPage = Number(button.dataset.page); renderList(); } });
    $('searchInput').addEventListener('input', () => { listPage = 1; renderList(); }); $('listStatus').addEventListener('change', () => { listPage = 1; renderList(); });
    $('eventForm').addEventListener('submit', event => { event.preventDefault(); run(saveEvent); }); click('deleteBtn', deleteEvent);
    click('addCheckBtn', () => { draft = readDraft(); if (draft.checklist.length >= 40) throw new Error('확인 목록은 40개까지 등록할 수 있습니다.'); draft.checklist.push({id: C.id(), text: '', done: false}); renderChecks(); $('checklistEditor').lastElementChild?.querySelector('input[type=text]').focus(); });
    $('checklistEditor').addEventListener('click', event => { const button = event.target.closest('[data-remove-check]'); if (button) { draft = readDraft(); draft.checklist = draft.checklist.filter(c => c.id !== button.dataset.removeCheck); renderChecks(); } });
    $('eventDialog').addEventListener('cancel', event => { event.preventDefault(); run(closeEvent); });
    document.querySelectorAll('[data-close]').forEach(button => button.addEventListener('click', () => { const dialog = button.closest('dialog'); if (dialog.id === 'eventDialog') run(closeEvent); else dialog.close(); }));
    $('utilityBody').addEventListener('click', event => run(async () => {
      const button = event.target.closest('button'); if (!button) return;
      if (button.dataset.restoreEvent) return restoreEvent(button.dataset.restoreEvent);
      if (button.dataset.backup) return previewRestore(check(await api.get_backup(button.dataset.backup)).content);
      if (button.dataset.font) { await commit(next => { next.settings.fontSize = button.dataset.font; }); toast('화면 글자 크기를 변경했습니다.'); return; }
      switch (button.dataset.action) {
        case 'copy': return copySelected(); case 'folder': return check(await api.open_export_folder()); case 'manual': return check(await api.open_manual());
        case 'backup': { const result = check(await api.backup_data()); toast(result.message); return; }
        case 'restore-file': $('restoreFile').click(); return; case 'update': return checkUpdate();
      }
    }));
    $('restoreFile').addEventListener('change', event => run(async () => { const file = event.target.files[0]; event.target.value = ''; if (!file) return; if (file.size > 16 * 1024 * 1024) throw new Error('백업 파일은 16MB 이내로 선택해 주세요.'); await previewRestore(await file.text()); }));
    document.addEventListener('keydown', event => { if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'z' && !event.target.closest('input,textarea,[contenteditable=true]') && !document.querySelector('dialog[open]')) { event.preventDefault(); run(undo); } });
    window.addEventListener('beforeunload', event => { if (writing) { event.preventDefault(); event.returnValue = ''; } });
  }
  function previewApi() {
    let snapshot = C.empty();
    const examples = [ ['09:00','주요 업무 보고','군청 소회의실','gunsu'], ['11:00','주민 소통 간담회','군청 대회의실','gunsu'], ['14:00','지역 현안 점검','현장 방문','v_gunsu'] ];
    if (new URLSearchParams(location.search).get('empty') !== '1') snapshot.events = examples.map(([time,title,place,attendee], i) => ({...C.newEvent(), time, title, place, attendee, dept: '행정운영과', status: i === 2 ? 'tentative' : 'confirmed', annotation: i === 1 ? '주민 대표 3명 참석 · 군수님 인사말 3분' : '', participants: i === 1 ? '주민 대표, 관련 부서장' : '', preparation: i === 1 ? '군수님 인사말 3분, 현안 자료 준비' : '', checklist: i === 1 ? [{id:C.id(), text:'자료 10부 준비', done:false}] : []}));
    const unavailable = async () => ({success:false,message:'화면 미리보기입니다. 파일 저장은 데스크톱 프로그램에서 이용해 주세요.'});
    return {bootstrap: async () => ({success:true,snapshot,version:'2.1.2',outputPath:'바탕화면 / 군수실_일정_출력문서',dataPath:'실제 데이터에 접근하지 않는 미리보기',appPath:'미리보기'}), ready:async()=>({success:true}),
      preview_document:async(request)=>{const response=await fetch('/preview-document',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({snapshot,request})});if(!response.ok) throw new Error('개발용 preview_server.py로 화면을 열어 주세요.');return response.json();}, save_persistent_data:async(content, expected)=>{if(expected!==snapshot.revision) return {success:false,message:'저장 순서 불일치'}; snapshot=JSON.parse(content);snapshot.revision++;snapshot.savedAt=new Date().toISOString();return {success:true,snapshot:structuredClone(snapshot)};}, list_backups:async()=>({success:true,items:[]}), export_document:unavailable, backup_data:unavailable, preview_restore:unavailable,restore_data:unavailable,open_export_folder:unavailable,open_last_output:unavailable,open_manual:unavailable,export_csv:unavailable,check_update:unavailable};
  }
  async function start() {
    if (started || starting) return;
    api = preview ? previewApi() : window.pywebview?.api;
    if (!api) return;
    starting = true;
    try { information = check(await api.bootstrap()); } finally { starting = false; }
    state = information.snapshot; readOnly = !!information.readOnly; started = true;
    $('usageGuide').open = !state.events.length;
    bind(); savedStatus(); $('versionLabel').textContent = 'v' + information.version; $('outputPath').textContent = information.outputPath;
    const messages = [];
    if (preview) messages.push('화면 미리보기입니다. 입력 내용은 이 화면에만 잠시 보관되며, 실제 일정이나 파일은 변경하지 않습니다.');
    if (readOnly) messages.push(information.recoveryError);
    if (information.recovery) messages.push(`자동 백업으로 복구했습니다. 복구 시각: ${information.recovery.savedAt || '이전 데이터'}. 최근 일정과 메모를 확인해 주세요.`);
    if (information.outputError) messages.push(information.outputError);
    if (information.updateWarning) messages.push(information.updateWarning);
    notice(messages.join('\n')); render();
    const ready = await api.ready(); if (!ready.success) notice((messages.join('\n') + '\n' + ready.message).trim());
    if (!preview && !readOnly && !state.events.length && !state.deletedEvents.length) {
      try {
        const legacyEvents = localStorage.getItem('gunsu_schedule_events');
        if (legacyEvents && JSON.parse(legacyEvents).length) {
          const legacy = JSON.stringify({events: JSON.parse(legacyEvents), deletedEvents: JSON.parse(localStorage.getItem('gunsu_schedule_trash') || '[]'), settings: JSON.parse(localStorage.getItem('gunsu_schedule_settings') || '{}')});
          await previewRestore(legacy);
        }
      } catch (error) { notice('이전 화면의 일정을 가져오지 못했습니다. 이전 프로그램에서 데이터 백업을 저장한 뒤 백업·복원 메뉴를 이용해 주세요. ' + error.message); }
    }
  }
  window.addEventListener('pywebviewready', () => run(start), {once:true});
  window.addEventListener('DOMContentLoaded', () => { if (preview || window.pywebview?.api) run(start); else setTimeout(() => { if (!started) notice('데스크톱 프로그램 연결을 기다리고 있습니다. 실행 파일(GunsuSchedule.exe)로 열어 주세요. 브라우저에서 HTML 파일만 열면 실제 일정이 저장되지 않습니다.'); }, 5000); });
})();
