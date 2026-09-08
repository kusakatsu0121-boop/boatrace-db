import fs from 'node:fs';

const cases = JSON.parse(fs.readFileSync(new URL('./cases.json', import.meta.url), 'utf8'));
const services = ['motto_takakunai', 'chatgpt', 'gemini', 'perplexity'];

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
  const clicks = [];
  const times = [];

  for (const c of cases) {
    const r = c?.results?.[service];
    if (!r || !Object.keys(r).length) continue;
    score += scoreResult(r);

    if (c?.ground_truth?.has_higher_same_job === true) {
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
    if (Number.isFinite(r.clicks)) clicks.push(r.clicks);
    if (Number.isFinite(r.elapsed_seconds)) times.push(r.elapsed_seconds);
  }

  out[service] = {
    score,
    tested_cases: cases.filter(c => c?.results?.[service] && Object.keys(c.results[service]).length).length,
    higher_same_job_recall_pct: pct(foundHigher, gtHigher),
    false_same_job_rate_pct: pct(falseSame, candidateCount),
    ended_job_rate_pct: pct(ended, highCandidateCount),
    base_wage_accuracy_pct: pct(wageCorrect, wageChecks),
    avg_clicks: clicks.length ? Math.round((clicks.reduce((a,b)=>a+b,0)/clicks.length)*10)/10 : null,
    avg_elapsed_seconds: times.length ? Math.round((times.reduce((a,b)=>a+b,0)/times.length)*10)/10 : null
  };
}

console.table(out);
