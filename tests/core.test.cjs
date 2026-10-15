const assert = require('node:assert/strict');
const C = require('../schedule-core.js');
assert.deepEqual(C.range('weekly','2026-01-01'), ['2025-12-29','2026-01-04']);
assert.equal(C.range('monthly','2024-02-02')[1], '2024-02-29');
assert.throws(() => C.dateObject('2026-02-30'));
assert.throws(() => C.dateObject('0001-01-01'));
assert.throws(() => C.quickInput('13/40 09:00 잘못된 날짜', '2026-10-02'));
assert.equal(C.escape('<img onerror="x">'), '&lt;img onerror=&quot;x&quot;&gt;');
const first = C.newEvent('2026-09-25');
first.title = '행사'; first.time = '09:00'; first.notes = '내부 메모'; first.checklist = [{id:'a',text:'준비',done:true}];
const snapshot = C.empty(); snapshot.events.push(first);
const result = C.copyWeek(snapshot, [first.id], '2026-10-02', true);
assert.equal(result.added.length, 1);
assert.equal(result.added[0].date, '2026-10-02');
assert.equal(result.added[0].status, 'tentative');
assert.equal(result.added[0].checklist[0].done, false);
snapshot.events.push(result.added[0]);
assert.equal(C.copyWeek(snapshot, [first.id], '2026-10-02', true).added.length, 0);
assert.equal(C.copyWeek(C.empty(), [], '2026-10-02', false).added.length, 0);
assert.equal(C.noteText(first).includes('내부 메모'), true);
const busy = {...first, endTime:'10:00'};
const point = {...first,id:'point',time:'09:30',endTime:''};
assert.equal(C.sameStartConflicts([busy],point).length,0); // Durations are outside this advisory.
const same = {...point,time:'09:00'};
assert.deepEqual(C.sameStartConflicts([busy],same),[busy]);
assert.equal(C.sameStartConflicts([busy],{...same,endTime:'09:15'}).length,1);
assert.equal(C.sameStartConflicts([busy],{...same,date:'2026-09-26'}).length,0);
assert.equal(C.sameStartConflicts([busy],busy).length,0); // Editing excludes itself.
for (const attendee of ['v_gunsu','general']) {
  assert.equal(C.sameStartConflicts([busy],{...same,attendee}).length,0);
  assert.equal(C.sameStartConflicts([{...busy,attendee}],same).length,0);
  assert.equal(C.sameStartConflicts([{...busy,attendee}],{...same,attendee}).length,0);
}
assert.equal(C.sameStartConflicts([busy],{...same,status:'cancelled'}).length,0);
assert.equal(C.sameStartConflicts([{...busy,status:'cancelled'}],same).length,0);
assert.equal(C.sameStartConflicts([{...busy,status:'tentative'}],{...same,status:'tentative'}).length,1);
assert.equal(C.sameStartConflicts([busy],{...same,time:''}).length,0);
assert.equal(C.sameStartConflicts([busy],{...same,time:'24:00'}).length,0);
for (const time of ['00:00','23:59']) assert.equal(C.sameStartConflicts([{...busy,time}],{...same,time}).length,1);
const conflictSnapshot = C.empty(); conflictSnapshot.deletedEvents.push(busy);
assert.equal(C.sameStartConflicts(conflictSnapshot.events,same).length,0);
const another = {...busy,id:'another',title:'다른 행사'};
const input = [busy,another];
assert.equal(C.sameStartConflicts(input,same).length,2);
assert.deepEqual(input,[busy,another]); // Display ordering never reorders saved data.
const quick = C.quickInput('9/25 09:00 빠른 입력', '2026-09-25');
assert.equal(C.sameStartConflicts([busy],quick).length,1);
console.log('JavaScript date, validation, escaping, copy and checklist checks passed.');
