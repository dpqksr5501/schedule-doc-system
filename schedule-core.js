/* Pure schedule logic shared by the UI and the Node regression tests. */
(function (root, factory) {
  const core = factory();
  if (typeof module === 'object' && module.exports) module.exports = core;
  else root.ScheduleCore = core;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  const weekdays = ['일', '월', '화', '수', '목', '금', '토'];
  const today = () => dateString(new Date());
  function dateString(date) { return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`; }
  function dateObject(value) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) throw new Error('날짜를 확인해 주세요.');
    const [y, m, d] = value.split('-').map(Number);
    if (y < 1900 || y > 2199) throw new Error('일정 날짜는 1900년부터 2199년 사이로 입력해 주세요.');
    const date = new Date(0); date.setHours(12, 0, 0, 0); date.setFullYear(y, m - 1, d);
    if (dateString(date) !== value) throw new Error('실제로 존재하는 날짜를 입력해 주세요.');
    return date;
  }
  function addDays(value, days) { const date = dateObject(value); date.setDate(date.getDate() + days); return dateString(date); }
  function monday(value) { const day = dateObject(value).getDay(); return addDays(value, day === 0 ? -6 : 1 - day); }
  function label(value) { const d = dateObject(value); return `${d.getMonth() + 1}.${d.getDate()}(${weekdays[d.getDay()]})`; }
  function range(view, selected) {
    if (view === 'weekly') { const start = monday(selected); return [start, addDays(start, 6)]; }
    if (view === 'monthly') { const d = dateObject(selected); return [dateString(new Date(d.getFullYear(), d.getMonth(), 1)), dateString(new Date(d.getFullYear(), d.getMonth() + 1, 0))]; }
    return [selected, selected];
  }
  function empty() { return {schemaVersion: 3, revision: 0, savedAt: '', events: [], deletedEvents: [], settings: {orgName: '보은군', leaderTitle: '군수님', subLeaderTitle: '부군수님', fontSize: 'normal'}}; }
  const id = () => crypto.randomUUID().replace(/-/g, '');
  function newEvent(selected = today()) { return {id: id(), date: selected, time: '09:00', endTime: '', title: '', place: '', dept: '', attendee: 'gunsu', priority: 'normal', status: 'confirmed', annotation: '', participants: '', preparation: '', contact: '', notes: '', checklist: [], updatedAt: ''}; }
  function validateEvent(event) {
    dateObject(event.date);
    if (!/^(?:[01]\d|2[0-3]):[0-5]\d$/.test(event.time) || event.endTime && !/^(?:[01]\d|2[0-3]):[0-5]\d$/.test(event.endTime)) throw new Error('시간은 00:00부터 23:59 사이로 입력해 주세요.');
    if (event.endTime && event.endTime <= event.time) throw new Error('종료 시간은 시작 시간보다 늦게 입력해 주세요.');
    if (!event.title.trim()) throw new Error('행사명을 입력해 주세요.');
    if (!['gunsu', 'v_gunsu', 'general'].includes(event.attendee) || !['normal', 'important'].includes(event.priority)) throw new Error('참석 구분과 중요도를 확인해 주세요.');
    return event;
  }
  function filterEvents(snapshot, view, selected, only = false) {
    const [start, end] = range(view, selected);
    return snapshot.events.filter(e => e.date >= start && e.date <= end && e.status !== 'cancelled' && (view !== 'daily' || !only || e.attendee === 'gunsu'))
      .sort((a, b) => a.date.localeCompare(b.date) || a.time.localeCompare(b.time) || a.id.localeCompare(b.id));
  }
  function quickInput(value, selected) {
    let remaining = value.trim();
    if (!remaining) throw new Error('행사 내용을 입력해 주세요.');
    const event = newEvent(selected);
    const dates = remaining.match(/(?:^|\s)(?:(\d{4})[-./])?(\d{1,2})[-./](\d{1,2})(?=\s|$)/);
    if (dates) { event.date = `${dates[1] || selected.slice(0, 4)}-${dates[2].padStart(2, '0')}-${dates[3].padStart(2, '0')}`; remaining = remaining.replace(dates[0], ' ').trim(); }
    const times = remaining.match(/(?:^|\s)(\d{1,2}):(\d{2})(?=\s|$)/);
    if (times) { event.time = `${times[1].padStart(2, '0')}:${times[2]}`; remaining = remaining.replace(times[0], ' ').trim(); }
    event.title = remaining;
    validateEvent(event);
    return event; // Open a prefilled form; never silently guess a department or save.
  }
  function fingerprint(event) { return [event.date, event.time, event.endTime || '', event.title, event.place || '', event.dept || '', event.attendee].join('\u001f'); }
  function copyWeek(snapshot, selectedIds, selected, details) {
    const previous = addDays(monday(selected), -7);
    const existing = new Set(snapshot.events.map(fingerprint));
    let skipped = 0;
    const added = snapshot.events.filter(e => selectedIds.includes(e.id) && e.date >= previous && e.date <= addDays(previous, 6) && e.status !== 'cancelled').map(event => {
      const clone = {...structuredClone(event), id: id(), date: addDays(event.date, 7), status: 'tentative', updatedAt: new Date().toISOString()};
      clone.checklist = details ? clone.checklist.map(c => ({...c, id: id(), done: false})) : [];
      if (!details) for (const key of ['annotation', 'participants', 'preparation', 'contact', 'notes']) clone[key] = '';
      if (existing.has(fingerprint(clone))) { skipped++; return null; }
      existing.add(fingerprint(clone)); return clone;
    }).filter(Boolean);
    return {added, skipped};
  }
  function conflicts(events, event) {
    const minutes = value => Number(value.slice(0, 2)) * 60 + Number(value.slice(3));
    const start = minutes(event.time), end = event.endTime ? minutes(event.endTime) : start + 1;
    return events.filter(e => e.id !== event.id && e.date === event.date && e.status !== 'cancelled' && e.attendee === event.attendee &&
      minutes(e.time) < end && start < (e.endTime ? minutes(e.endTime) : minutes(e.time) + 1));
  }
  function noteText(event) {
    const lines = [];
    for (const [label, key] of [['참석', 'participants'], ['담당', 'contact'], ['준비', 'preparation'], ['메모', 'notes']]) if (event[key]) lines.push(`${label}: ${event[key]}`);
    if (event.checklist.length) lines.push('확인: ' + event.checklist.map(c => `${c.done ? '완료' : '미완료'} ${c.text}`).join(' / '));
    return lines.join('\n');
  }
  function titleText(event, notes) { return `${event.priority === 'important' ? '[중요] ' : ''}${event.status === 'tentative' ? '[미확정] ' : ''}${event.title}${notes && noteText(event) ? '\n' + noteText(event) : ''}`; }
  function calendar(selected) {
    const [start, end] = range('monthly', selected); let cursor = monday(start); const final = addDays(monday(end), 6); const weeks = [];
    while (cursor <= final) { const week = []; for (let i = 0; i < 7; i++) { week.push(cursor); cursor = addDays(cursor, 1); } weeks.push(week); } return weeks;
  }
  function escape(value) { return String(value ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c])); }
  return {today, dateObject, dateString, addDays, monday, label, range, empty, id, newEvent, validateEvent, filterEvents, quickInput, copyWeek, conflicts, noteText, titleText, calendar, escape};
});
