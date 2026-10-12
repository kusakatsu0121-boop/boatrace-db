import assert from 'node:assert/strict';
import { buildGuide, sources } from '../../docs/taishoku-guide/guide.mjs';

const cases = [
  ['ordinary', {employment:'retired',work:'ready',reason:'same',insurance:'unknown'}, ['job','insurance','pension']],
  ['on-leave', {employment:'leave',work:'ill',sickness:'not_applied'}, ['sickness','extension']],
  ['sick-before-retirement', {employment:'before',work:'ill',sickness:'applying'}, ['sickness','extension']],
  ['dispute', {employment:'retired',work:'ready',reason:'dispute'}, ['dispute','job']],
  ['unknown', {}, ['work-status','insurance','pension']],
];
for (const [name,input,expected] of cases) {
  const tasks = buildGuide(input);
  for (const id of expected) assert(tasks.some(t=>t.id===id),`${name}: missing ${id}`);
}
assert.match(buildGuide({employment:'retired',sickness:'receiving'})[0].where,/退職前/);
assert.match(buildGuide({employment:'before',sickness:'applying'})[0].say,/受付状況/);
assert.match(buildGuide({sickness:'receiving'})[0].say,/次回分/);
assert(!buildGuide({insurance:'done'}).some(t=>['insurance','pension'].includes(t.id)));
assert(!buildGuide({work:'ill'}).some(t=>t.id==='job'));
assert(!buildGuide({work:'later'}).some(t=>t.id==='job'));
assert.deepEqual(buildGuide({employment:'<script>',work:'bad',reason:'bad'}),buildGuide());
let count=0;
for(const employment of ['unknown','before','leave','retired'])
for(const work of ['unknown','ready','ill','later'])
for(const reason of ['unknown','same','dispute','no_notice'])
for(const sickness of ['unknown','not_applied','applying','receiving'])
for(const insurance of ['unknown','done']) {
  const tasks=buildGuide({employment,work,reason,sickness,insurance});
  assert(tasks.length>0);
  assert.equal(new Set(tasks.map(t=>t.id)).size,tasks.length);
  for(const task of tasks) {
    for(const key of ['title','where','action','say','bring','fallback']) assert(task[key]?.length>5,key);
    assert(sources[task.source][1].startsWith('https://'));
    assert(!/あなたは.+回答|入力内容から判断|この回答では|承認待ち|正式レポートを出す前/.test(JSON.stringify(task)));
  }
  count++;
}
console.log(`STATIC_GUIDE_OK: 5 representative cases + ${count} routing combinations`);
