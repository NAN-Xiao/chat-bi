import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'

const deferred = () => { let resolve, reject; const promise = new Promise((a,b) => { resolve=a; reject=b }); return {promise,resolve,reject} }
function setup(enabled = true) {
  const exports = {}
  vm.runInNewContext(ts.transpileModule(readFileSync('src/utils/accountTheme.ts','utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS },
  }).outputText, { exports, require: () => ({ DEFAULT_THEME:'light', COLOR_THEME_SWITCHING_ENABLED:enabled, THEME_STORAGE_KEY:'theme' }) })
  const loads=[], saves=[], applied=[], broadcasts=[], states=[]
  const api=exports.createAccountTheme({
    load: () => {const d=deferred();loads.push(d);return d.promise},
    save: theme => {const d=deferred();saves.push({theme,...d});return d.promise},
    apply: t=>applied.push(t), publish: key=>broadcasts.push({key}),
    status: s=>states.push({...s}),
  })
  return {api, loads,saves,applied,broadcasts,states}
}
test('server preference restores per account and workspace rebinding does not reset it', async()=>{
  const t=setup();const first=t.api.bind('A');t.loads[0].resolve({theme:'dark'});await first
  assert.equal(t.applied.at(-1),'dark');await t.api.bind('A');assert.equal(t.loads.length,1)
  const second=t.api.bind('B');assert.equal(t.applied.at(-1),'light');t.loads[1].resolve({theme:'light'});await second
  assert.equal(t.applied.at(-1),'light')
})
test('choice applies immediately, saves once and publishes only after confirmation', async()=>{
  const t=setup();const ready=t.api.bind('A');t.loads[0].resolve({theme:'light'});await ready
  const pending=t.api.choose('dark');assert.equal(t.applied.at(-1),'dark');assert.equal(t.states.at(-1).saving,true)
  assert.equal(t.broadcasts.length,0);await t.api.choose('light');assert.equal(t.saves.length,1)
  t.saves[0].resolve({theme:'dark'});await pending
  assert.deepEqual(t.broadcasts,[{key:'theme:A'}]);assert.equal(t.states.at(-1).saving,false)
})
test('failed save restores confirmed preference and reports the failure', async()=>{
  const t=setup();const ready=t.api.bind('A');t.loads[0].resolve({theme:'light'});await ready
  const pending=t.api.choose('dark');t.saves[0].reject(Error('offline'));await assert.rejects(pending,/offline/)
  assert.equal(t.applied.at(-1),'light');assert.equal(t.broadcasts.length,0)
})
test('logout and account switch ignore late loads and saves from the old session', async()=>{
  const t=setup();const old=t.api.bind('A');t.api.reset();const next=t.api.bind('B')
  t.loads[1].resolve({theme:'light'});await next;t.loads[0].resolve({theme:'dark'});await old
  assert.equal(t.applied.at(-1),'light')
  const pending=t.api.choose('dark');t.api.reset();t.saves[0].resolve({theme:'dark'});await pending
  assert.equal(t.applied.at(-1),'light');assert.equal(t.broadcasts.length,0)
})
test('storage updates apply only to the same signed-in account without saving back', async()=>{
  const t=setup();const ready=t.api.bind('A');t.loads[0].resolve({theme:'light'});await ready
  t.api.acceptStorage('theme:B','dark');assert.equal(t.applied.at(-1),'light')
  const refresh=t.api.acceptStorage('theme:A','changed');t.loads[1].resolve({theme:'dark'});await refresh
  assert.equal(t.applied.at(-1),'dark');assert.equal(t.saves.length,0)
  t.api.reset();t.api.acceptStorage('theme:A','dark');assert.equal(t.applied.at(-1),'light')
})
test('forced light neither loads nor saves preferences; invalid server values fail explicitly', async()=>{
  const off=setup(false);await off.api.bind('A');await off.api.choose('dark');assert.equal(off.loads.length,0);assert.equal(off.saves.length,0)
  assert.equal(off.applied.at(-1),'light')
  const t=setup();const load=t.api.bind('A');t.loads[0].resolve({theme:'invalid'});await assert.rejects(load,/配色/)
  assert.equal(t.states.at(-1).ready,false)
})
test('embedded identity never loads or writes the owner account preference', async()=>{
  const t=setup();await t.api.bind('owner', false);await t.api.choose('dark')
  assert.equal(t.loads.length,0);assert.equal(t.saves.length,0);assert.equal(t.applied.at(-1),'light')
})
test('failed local save reconciles a confirmed change arriving from another tab', async()=>{
  const t=setup();const ready=t.api.bind('A');t.loads[0].resolve({theme:'light'});await ready
  const pending=t.api.choose('dark');const rejected=assert.rejects(pending,/offline/)
  t.api.acceptStorage('theme:A','dark');t.saves[0].reject(Error('offline'))
  await new Promise(resolve => setImmediate(resolve))
  assert.equal(t.loads.length,2)
  t.loads[1].resolve({theme:'dark'});await rejected
  assert.equal(t.applied.at(-1),'dark');assert.equal(t.states.at(-1).saving,false)
})
test('logout during reconciliation suppresses obsolete errors and visual changes', async()=>{
  const t=setup();const ready=t.api.bind('A');t.loads[0].resolve({theme:'light'});await ready
  const pending=t.api.choose('dark');t.api.acceptStorage('theme:A','dark');t.saves[0].reject(Error('old account failure'))
  await new Promise(resolve=>setImmediate(resolve));assert.equal(t.loads.length,2)
  t.api.reset();t.loads[1].resolve({theme:'dark'});await pending
  assert.equal(t.applied.at(-1),'light')
})
for (const serverTheme of ['light','dark']) {
  test(`conflicting save responses invalidate other tabs and reconcile server ${serverTheme}`, async()=>{
    const t=setup();const ready=t.api.bind('A');t.loads[0].resolve({theme:'light'});await ready
    const pending=t.api.choose('dark');t.api.acceptStorage('theme:A','another-commit');t.saves[0].resolve({theme:'dark'})
    await new Promise(resolve=>setImmediate(resolve))
    assert.deepEqual(t.broadcasts,[{key:'theme:A'}]) // no stale theme in the notification
    t.loads[1].resolve({theme:serverTheme});await pending
    assert.equal(t.applied.at(-1),serverTheme)
  })
}
test('stale storage payload cannot override the authoritative server preference',async()=>{
  const t=setup();const ready=t.api.bind('A');t.loads[0].resolve({theme:'light'});await ready
  const update=t.api.acceptStorage('theme:A','dark');t.loads[1].resolve({theme:'light'});await update
  assert.equal(t.applied.at(-1),'light')
})
