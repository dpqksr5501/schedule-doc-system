const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const C = require('../schedule-core.js');
const source = fs.readFileSync(require('node:path').join(__dirname, '../app.js'), 'utf8');
const save = source.slice(source.indexOf('  async function saveEvent()'), source.indexOf('  async function deleteEvent()'));
const event = (id, fields = {}) => ({...C.newEvent('2026-10-16'), id, title: '주민 간담회', ...fields});

function scenario({candidate = event('new'), existing = [event('old', {place: '대회의실', dept: '행정과', status: 'tentative'})], confirm = async () => true, failSave = false} = {}) {
  const elements = new Map(['eventDialog', 'eventError'].map(id => [id, {
    hidden: true, close() { this.closed = true; }, scrollIntoView() {}
  }]));
  const calls = {confirm: [], commits: 0, errors: [], editing: []};
  const context = {
    C, draft: structuredClone(candidate), savingEvent: false, working: false, writing: false, readOnly: false,
    state: {...C.empty(), events: structuredClone(existing)}, selected: candidate.date,
    $: id => elements.get(id), readDraft: () => structuredClone(candidate), updateControls() {},
    confirmAction: async (...args) => { calls.confirm.push(args); return confirm(...args); },
    commit: async change => { if (failSave) throw new Error('저장 공간 부족'); change(context.state); calls.commits++; },
    render() {}, toast() {}, errorMessage: error => calls.errors.push(error.message),
    api: {set_editing: async value => calls.editing.push(value)}
  };
  vm.createContext(context); vm.runInContext(save, context);
  return {context, calls, elements};
}

(async () => {
  const accepted = scenario();
  await accepted.context.saveEvent();
  assert.equal(accepted.calls.commits, 1);
  assert.equal(accepted.context.state.events.length, 2);
  assert.match(accepted.calls.confirm[0][0], /군수님/);
  assert.match(accepted.calls.confirm[0][1], /2026-10-16 09:00/);
  assert.match(accepted.calls.confirm[0][1], /주민 간담회 \[미확정\]/);
  assert.match(accepted.calls.confirm[0][1], /대회의실.*행정과/);
  assert.equal(accepted.calls.confirm[0][2], '이대로 저장');
  assert.equal(accepted.context.draft, null);
  assert.deepEqual(accepted.calls.editing, [false]);

  const cancelled = scenario({confirm: async () => false});
  const before = JSON.stringify(cancelled.context.state);
  await cancelled.context.saveEvent();
  assert.equal(cancelled.calls.commits, 0);
  assert.equal(JSON.stringify(cancelled.context.state), before);
  assert.equal(cancelled.context.draft.title, '주민 간담회');
  assert.equal(cancelled.elements.get('eventDialog').closed, undefined);
  assert.equal(cancelled.context.savingEvent, false);
  assert.equal(cancelled.calls.editing.length, 0);

  for (const candidate of [event('old'), event('new', {attendee: 'general'}), event('new', {status: 'cancelled'}), event('new', {time: '10:00'})]) {
    const unblocked = scenario({candidate}); await unblocked.context.saveEvent();
    assert.equal(unblocked.calls.confirm.length, 0);
    assert.equal(unblocked.calls.commits, 1);
  }
  const multiple = scenario({existing: [event('old-a', {title: '<img src=x onerror=alert(1)>'}), event('old-b')]});
  await multiple.context.saveEvent();
  assert.match(multiple.calls.confirm[0][1], /2건/);
  assert.match(multiple.calls.confirm[0][1], /장소: 미정 · 주관부서: 미정/);
  assert.match(multiple.calls.confirm[0][1], /<img src=x onerror=alert\(1\)>/); // Passed as text to confirmAction.

  let finish;
  const repeated = scenario({confirm: () => new Promise(resolve => { finish = resolve; })});
  const pending = repeated.context.saveEvent();
  await repeated.context.saveEvent();
  assert.equal(repeated.calls.confirm.length, 1);
  finish(true); await pending;
  assert.equal(repeated.calls.commits, 1);
  assert.equal(repeated.context.savingEvent, false);

  const failed = scenario({failSave: true}); await failed.context.saveEvent();
  assert.equal(failed.calls.commits, 0);
  assert.equal(failed.context.state.events.length, 1);
  assert.equal(failed.context.draft.title, '주민 간담회');
  assert.equal(failed.context.savingEvent, false);
  assert.deepEqual(failed.calls.errors, ['저장 공간 부족']);
  const invalid = scenario({candidate: event('new', {title: ' '})}); await invalid.context.saveEvent();
  assert.equal(invalid.calls.commits, 0);
  assert.equal(invalid.calls.confirm.length, 0);
  assert.equal(invalid.context.savingEvent, false);
  console.log('Same-start save advisory: confirm, cancel, edit, exclusions, multiple matches, repeated submit and failed persistence passed.');
})().catch(error => { console.error(error); process.exitCode = 1; });
