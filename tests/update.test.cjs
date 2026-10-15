const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const source = fs.readFileSync(require('node:path').join(__dirname, '../app.js'), 'utf8');
const update = source.slice(source.indexOf('  async function checkUpdate('), source.indexOf('  function movePeriod('));

async function scenario(overrides = {}) {
  const elements = new Map(['updateStatus', 'updateBanner'].map(id => [id, {textContent: '', hidden: true}]));
  let calls = 0;
  const context = {
    checkingUpdate: false, working: false, writing: false, readOnly: false, draft: null,
    information: {version: '2.1.5'}, writeQueue: Promise.resolve(),
    $: id => elements.get(id) || null,
    document: {querySelector: () => null},
    setWorking: value => { context.working = value; },
    toast: () => {}, check: result => { if (!result.success) throw new Error(result.message); return result; },
    confirmAction: async () => true,
    api: {check_update: async () => ({success: true, hasUpdate: true, canApply: true, latestVersion: '2.1.6'}),
      apply_update: async () => { calls++; return {success: true}; }}
  };
  Object.assign(context, overrides);
  vm.createContext(context);
  vm.runInContext(update, context);
  await context.checkUpdate(true);
  return {context, elements, calls};
}

(async () => {
  const idle = await scenario();
  assert.equal(idle.calls, 1); // Startup succeeds without the management dialog existing.
  assert.equal(idle.context.working, true);
  const editing = await scenario({draft: {title: 'Unsaved edit'}});
  assert.equal(editing.calls, 0);
  assert.equal(editing.elements.get('updateBanner').hidden, false);
  const dialog = await scenario({document: {querySelector: () => ({open: true})}});
  assert.equal(dialog.calls, 0);
  const offline = await scenario({api: {check_update: async () => ({success: false, message: 'offline'})}});
  assert.equal(offline.context.working, false);
  assert.equal(offline.elements.get('updateBanner').hidden, true);
  const failed = await scenario({api: {
    check_update: async () => ({success: true, hasUpdate: true, canApply: true, latestVersion: '2.1.6'}),
    apply_update: async () => ({success: false, message: 'hash mismatch'})}});
  assert.equal(failed.context.working, false);
  assert.match(failed.elements.get('updateStatus').textContent, /hash mismatch/);
  const unverified = await scenario({api: {check_update: async () => ({success: true, hasUpdate: true, canApply: false})}});
  assert.equal(unverified.calls, 0);
  assert.equal(unverified.context.working, false);
  const readonly = await scenario({readOnly: true});
  assert.equal(readonly.calls, 0);
  console.log('Startup update: idle, editing, dialog, offline, failed download, unverified and read-only cases passed.');
})().catch(error => { console.error(error); process.exitCode = 1; });
