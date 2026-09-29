import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import crypto from 'node:crypto';
import vm from 'node:vm';
import { interimGuidanceHtml } from '../runtime/workflow_webhook_v0.1/partial_guidance.mjs';
import { finalizeInstantReport } from '../runtime/workflow_pipeline_v0.1/instant_finalize.mjs';

const W = fs.readFileSync(new URL('../runtime/workflow_webhook_v0.1/webhook_server.mjs', import.meta.url), 'utf8');
assert.match(W, /import \{ interimGuidanceHtml \} from '\.\/partial_guidance\.mjs'/);
assert.match(W, /const interim = review \? interimGuidanceHtml\(missing, reasons\) : '';/);
assert.match(W, /\$\{details\}\$\{interim\}/);
assert.match(W, /reportUnavailablePage\(outputRoot, token, durableReview\)/);
assert.match(W, /必要な内容を整理しています/);
assert.doesNotMatch(W, /通常は数十秒で表示されます/);

const start = W.indexOf('function reportUnavailablePage(');
const end = W.indexOf('\n}\n', start);
assert.ok(start >= 0 && end > start, 'review page present');
const pageFnSource = W.slice(start, end + 2);
function pageFor(state, durable = null) {
  const page = vm.runInNewContext(`${pageFnSource}\nreportUnavailablePage`, {
    readInstantStatus: () => state,
    interimGuidanceHtml,
  });
  return page('/no-real-job', 'not-a-real-token', durable);
}

const wageCode = 'wage_6m_total_or_regular_month';
const salary = interimGuidanceHtml([wageCode], []);
assert.match(salary, /金額まで知りたいときは/);
assert.match(salary, /給与明細/);
assert.doesNotMatch(salary, /受給できます|支給確定|回答しています|入力した内容をもとに/);
const injected = interimGuidanceHtml(['<script>alert(1)</script>'], ['<img src=x onerror=alert(1)>']);
assert.doesNotMatch(injected, /<script>|<img|onerror/);

const review = pageFor({status:'review_required',missing_inputs:[wageCode,'cause_work_related'],review_reasons:['離職理由区分に確認が必要']});
assert.match(review, /ここだけ確認してください/);
assert.match(review, /次に確認すること/);
assert.match(review, /金額まで知りたいときは/);
assert.match(review, /離職票/);
assert.match(review, /正式レポートを出す前に/);
assert.doesNotMatch(review, /<script>/);

const persistedReview = pageFor(null, {status:'review_required',missing_inputs:[wageCode],review_reasons:[]});
assert.match(persistedReview, /次に確認すること/);
assert.match(persistedReview, /金額まで知りたいときは/);
const failed = pageFor({status:'failed',missing_inputs:[wageCode]});
assert.doesNotMatch(failed, /次に確認すること/);
assert.match(failed, /うまく処理できませんでした/);
console.log('PARTIAL_GUIDANCE_REVIEW_ONLY_OK');

// Isolated readiness check: prove a ready report reaches the existing
// persistence boundary, but do not contact production Neon or submit Tally.
const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'taishoku-ready-smoke-'));
const referenceId = 'WF-synthetic-ready';
const job = path.join(temp, referenceId);
const token = crypto.randomBytes(32).toString('base64url');
fs.mkdirSync(job);
fs.writeFileSync(path.join(job, 'job_manifest.json'), JSON.stringify({reference_id:referenceId,status:'ready_for_manual_delivery',delivery_allowed:true,automatic_delivery:false}));
fs.writeFileSync(path.join(job, 'report_preview.html'), '<!doctype html><title>synthetic only</title>');
const oldDb = process.env.DATABASE_URL;
delete process.env.DATABASE_URL;
try {
  await assert.rejects(
    finalizeInstantReport({outputRoot:temp,referenceId,token,timeoutMs:300}),
    /DATABASE_URL is not configured/,
    'ready case must reach persistence, not timeout or auto-publish'
  );
  assert.equal(fs.existsSync(path.join(job,'approval.json')),false);
} finally {
  if (oldDb === undefined) delete process.env.DATABASE_URL;
  else process.env.DATABASE_URL = oldDb;
  fs.rmSync(temp, {recursive:true,force:true});
}
console.log('READY_PATH_REACHES_PERSISTENCE_BOUNDARY_OK (not a Tally/Neon E2E)');
