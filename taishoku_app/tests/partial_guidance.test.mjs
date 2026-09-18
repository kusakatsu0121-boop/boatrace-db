import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import { interimGuidanceHtml } from '../runtime/workflow_webhook_v0.1/partial_guidance.mjs';

const W = fs.readFileSync(new URL('../runtime/workflow_webhook_v0.1/webhook_server.mjs', import.meta.url), 'utf8');
assert.match(W, /import \{ interimGuidanceHtml \} from '\.\/partial_guidance\.mjs'/);
assert.match(W, /const interim = review \? interimGuidanceHtml\(missing, reasons\) : '';/);
assert.match(W, /\$\{details\}\$\{interim\}/);
assert.match(W, /reportUnavailablePage\(outputRoot, token, durableReview\)/);

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
assert.match(salary, /賃金額は未確認/);
assert.match(salary, /金額目安は算出していません/);
assert.match(salary, /入力し直す必要はありません/);
assert.doesNotMatch(salary, /受給できます|支給確定/);
const injected = interimGuidanceHtml(['<script>alert(1)</script>'], ['<img src=x onerror=alert(1)>']);
assert.doesNotMatch(injected, /<script>|<img|onerror/);

const review = pageFor({status:'review_required',missing_inputs:[wageCode,'cause_work_related'],review_reasons:['離職理由区分に確認が必要']});
assert.match(review, /確認待ちの暫定道案内/);
assert.match(review, /金額目安は算出していません/);
assert.match(review, /離職票/);
assert.match(review, /まだ公開していません/);
assert.doesNotMatch(review, /<script>/);

const persistedReview = pageFor(null, {status:'review_required',missing_inputs:[wageCode],review_reasons:[]});
assert.match(persistedReview, /確認待ちの暫定道案内/);
assert.match(persistedReview, /算出していません/);
const failed = pageFor({status:'failed',missing_inputs:[wageCode]});
assert.doesNotMatch(failed, /確認待ちの暫定道案内/);
assert.match(failed, /回答内容に問題があると決まったわけではありません/);
console.log('PARTIAL_GUIDANCE_REVIEW_ONLY_OK');
