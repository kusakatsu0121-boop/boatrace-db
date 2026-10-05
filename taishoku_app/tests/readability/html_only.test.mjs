// Offline regression: real normalizer/evaluator/renderer, no Tally or database calls.
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import crypto from 'node:crypto';
import assert from 'node:assert/strict';
import {pathToFileURL} from 'node:url';
import {spawnSync} from 'node:child_process';
const [baselineArg,runtimeArg,fixturesArg]=process.argv.slice(2);
if(!fixturesArg)throw new Error('Usage: node html_only.test.mjs BASELINE_RUNTIME HTML_RUNTIME FIXTURES');
const baseline=path.resolve(baselineArg),runtime=path.resolve(runtimeArg),fixtures=path.resolve(fixturesArg);
const map=JSON.parse(fs.readFileSync(path.join(runtime,'workflow_rule_package_v0.1/tally_field_map.v1.json')));
const before=(await import(pathToFileURL(path.join(baseline,'workflow_pipeline_v0.1/process_tally_submission.mjs')))).processTallySubmission;
const after=(await import(pathToFileURL(path.join(runtime,'workflow_pipeline_v0.1/process_tally_submission.mjs')))).processTallySubmission;
const out=fs.mkdtempSync(path.join(os.tmpdir(),'html-only-test-'));
const hash=p=>crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');
for(const file of ['workflow_pipeline_v0.1/approve_job.mjs','workflow_pipeline_v0.1/instant_finalize.mjs','workflow_report_access_v0.1/report_access.mjs','workflow_rule_package_v0.1/evaluate.mjs','workflow_rule_package_v0.1/workflow_rules_v0.1.json','workflow_persistence_v0.1/persist_job.mjs','workflow_persistence_v0.1/restore_job.mjs'])assert.equal(hash(path.join(baseline,file)),hash(path.join(runtime,file)),file+' must remain unchanged');
let rendered=0,blocked=0;
const statuses=new Set();
for(const name of fs.readdirSync(fixtures)){
 const answer=JSON.parse(fs.readFileSync(path.join(fixtures,name,'answer.json')));
 answer.service_scope_consent=['confirmed'];
 if(answer.wage_6m_total!=null){answer.wage_input_method='six_month_total';answer.wage_value_raw=answer.wage_6m_total;}
 const fields=map.fields.filter(f=>answer[f.internal_key]!=null).map(f=>{
  const v=answer[f.internal_key];
  const choice=x=>Object.entries({...f.option_labels,...f.options}).find(([,value])=>value===x)?.[0]??x;
  return {key:f.field_id,label:f.question,value:f.kind==='multiple'?v.map(choice):f.kind==='single'?choice(v):v};
 });
 const payload={data:{responseId:'HTMLONLY-'+name,createdAt:'2026-10-04T00:00:00Z',fields}};
 const a=before(payload,{outputRoot:path.join(out,'before')});const b=after(payload,{outputRoot:path.join(out,'after')});
 for(const key of ['status','delivery_allowed','automatic_delivery','human_review'])assert.deepEqual(b[key],a[key],name+' '+key);
 statuses.add(b.status);
 assert.equal(b.automatic_delivery,false);
 assert(!fs.existsSync(path.join(b.job_dir,'report_preview.pdf')));
 assert(!('report_url' in b));
 if(b.status!=='blocked'){
  rendered++;
  assert.equal(fs.readFileSync(a.files.html_report,'utf8'),fs.readFileSync(b.files.html_report,'utf8'),name+' exact HTML');
  assert.equal(b.review_artifact,'html_preview');
  assert(!Object.keys(b.files).some(k=>k.includes('pdf')));
  assert(!('pdf_sha256' in b.artifacts));
  assert.equal(b.artifacts.html_sha256,a.artifacts.html_sha256);
  const strip=p=>{const x=JSON.parse(fs.readFileSync(p));delete x.evaluated_at;return x};
  assert.deepEqual(strip(a.files.evaluation),strip(b.files.evaluation));
  // -S disables site packages: HTML must not depend on PyMuPDF or any pip package.
  const run=spawnSync('python3',['-S',path.join(runtime,'report_template_v0.1/render_report.py'),b.files.normalized_answer,'--html',path.join(out,'stdlib.html')],{encoding:'utf8'});
  assert.equal(run.status,0,run.stderr);
 }else blocked++;
 console.log(name,b.status,'PASS');
}
assert(statuses.has('ready_for_manual_delivery'));
assert(statuses.has('review_required'));
assert(statuses.has('blocked'));
console.log(JSON.stringify({rendered,blocked,securityFilesUnchanged:true,pdfFilesCreated:0,stdlibOnly:true}));
