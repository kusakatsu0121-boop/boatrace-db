import fs from 'node:fs';

const cases = JSON.parse(fs.readFileSync(new URL('./cases.json', import.meta.url), 'utf8'));
const services = ['motto_takakunai', 'chatgpt', 'gemini', 'perplexity'];
const scoredCases = cases.filter(c => c?.scored === true);

function scoreResult(r = {}) {
  let score = 0;
  if (r.found_higher_same_job && r.active_verified) score += 1;
  score -= Number(r.false_same_job_count || 0);
  score -= Number(r.ended_job_count || 0) * 2;
  if (r.base_wage_correct === false) score -= 1;
  return score;
}

function pct(n, d) {
  return d ? Math.round((n / d) * 1000) / 10 : null;
}

function avg(values) {
  return values.length ? Math.round((values.reduce((a, b) => a + b, 0) / values.length) * 10) / 10 : null;
}

function metricPass(value, op, threshold) {
  if (value == null) return false;
  return op === '>=' ? value >= threshold : value <= threshold;
}

function gateForMotto(stats) {
  const n = stats.tested_cases;

  // 掲載終了の提示は、正式CASEで1件でも発生した時点で即レビュー対象。
  // CASE-10/20/30の総合点や他KPIで相殺しない。
  if (stats.ended_job_count > 0) {
    return {
      stage: n >= 30 ? 'CASE-30' : n >= 20 ? 'CASE-20' : n >= 10 ? 'CASE-10' : 'EARLY',
      verdict: 'STATUS_LOGIC_REVIEW',
      reason: `ended jobs presented: ${stats.ended_job_count}; final pass requires zero`
    };
  }

  if (n < 10) return { stage: 'COLLECTING', verdict: 'CONTINUE', reason: `${10 - n} scored cases until first gate` };

  if (n >= 30) {
    const pass = metricPass(stats.higher_same_job_recall_pct, '>=', 65)
      && metricPass(stats.false_same_job_rate_pct, '<=', 10)
      && metricPass(stats.base_wage_accuracy_pct, '>=', 95);
    return { stage: 'CASE-30', verdict: pass ? 'PASS' : 'FAIL_OR_PIVOT', reason: pass ? 'all final thresholds met' : 'one or more final thresholds missed' };
  }

  if (n >= 20) {
    const pass = metricPass(stats.higher_same_job_recall_pct, '>=', 60)
      && metricPass(stats.false_same_job_rate_pct, '<=', 12)
      && metricPass(stats.base_wage_accuracy_pct, '>=', 90);
    return { stage: 'CASE-20', verdict: pass ? 'GO' : 'REVIEW_OR_PIVOT', reason: pass ? 'all CASE-20 thresholds met' : 'one or more CASE-20 thresholds missed' };
  }

  const pass = metricPass(stats.higher_same_job_recall_pct, '>=', 50)
    && metricPass(stats.false_same_job_rate_pct, '<=', 20)
    && metricPass(stats.base_wage_accuracy_pct, '>=', 85);
  return { stage: 'CASE-10', verdict: pass ? 'GO' : 'LOGIC_REVIEW', reason: pass ? 'all CASE-10 thresholds met' : 'one or more CASE-10 thresholds missed' };
}

const out = {};
for (const service of services) {
  let score = 0;
  let gtHigher = 0;
  let foundHigher = 0;
  let candidateCount = 0;
  let falseSame = 0;
  let highCandidateCount = 0;
  let ended = 0;
  let wageChecks = 0;
  let wageCorrect = 0;
  const t1 = [];
  const t2 = [];
  const t3 = [];

  for (const c of scoredCases) {
    const r = c?.results?.[service];
    if (!r || !Object.keys(r).length) continue;
    score += scoreResult(r);

    if (c?.ground_truth?.status === 'exists') {
      gtHigher++;
      if (r.found_higher_same_job === true && r.active_verified === true) foundHigher++;
    }

    candidateCount += Number(r.presented_candidate_count || 0);
    falseSame += Number(r.false_same_job_count || 0);
    highCandidateCount += Number(r.presented_higher_candidate_count || (r.found_higher_same_job ? 1 : 0));
    ended += Number(r.ended_job_count || 0);

    if (r.base_wage_correct === true || r.base_wage_correct === false) {
      wageChecks++;
      if (r.base_wage_correct === true) wageCorrect++;
    }
    if (Number.isFinite(r.t1_result_seconds)) t1.push(r.t1_result_seconds);
    if (Number.isFinite(r.t2_open_clicks)) t2.push(r.t2_open_clicks);
    if (Number.isFinite(r.t3_total_seconds)) t3.push(r.t3_total_seconds);
  }

  out[service] = {
    score,
    tested_cases: scoredCases.filter(c => c?.results?.[service] && Object.keys(c.results[service]).length).length,
    ground_truth_positive_cases: gtHigher,
    higher_same_job_recall_pct: pct(foundHigher, gtHigher),
    false_same_job_rate_pct: pct(falseSame, candidateCount),
    ended_job_rate_pct: pct(ended, highCandidateCount),
    ended_job_count: ended,
    base_wage_accuracy_pct: pct(wageCorrect, wageChecks),
    avg_t1_result_seconds: avg(t1),
    avg_t2_open_clicks: avg(t2),
    avg_t3_total_seconds: avg(t3)
  };
}

const mottoGate = gateForMotto(out.motto_takakunai);

console.table(out);
console.log('\nMotto Takakunai gate:');
console.log(mottoGate);

if (mottoGate.verdict === 'STATUS_LOGIC_REVIEW' || mottoGate.verdict === 'FAIL_OR_PIVOT') {
  process.exitCode = 2;
}
