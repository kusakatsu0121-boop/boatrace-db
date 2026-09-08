// Motto Takakunai - live search logic helpers
// Search-first design: do not rely on a growing fixed jobs database.

export function normalizeText(input = '') {
  return String(input)
    .replace(/[０-９]/g, c => String.fromCharCode(c.charCodeAt(0) - 65248))
    .replace(/[，]/g, ',')
    .replace(/\s+/g, ' ')
    .trim()
    .toLowerCase();
}

export function normalizeBaseHourly(input = '') {
  const s = normalizeText(input).replace(/,/g, '');
  const hourly = [...s.matchAll(/(?:基本時給|通常時給|時給)\s*[:：]?\s*(\d{3,4})(?:\s*(?:円)?\s*[～〜~-]\s*(\d{3,4}))?/g)]
    .map(m => ({ low: Number(m[1]), high: m[2] ? Number(m[2]) : null }));
  if (!hourly.length) return { baseHourly: null, displayedHigh: null, reason: 'hourly_not_found' };

  // Prefer the first explicit hourly amount. In Japanese night-shift listings, ranges such as
  // 1840-2300 and 1900-2375 commonly represent base + 25% late-night premium.
  const first = hourly[0];
  const isNight = /夜勤|翌|20:00|21:00|22:00|23:00|24:00|29:00/.test(s);
  const premiumLike = first.high && Math.abs(first.high / first.low - 1.25) < 0.025;
  return {
    baseHourly: first.low,
    displayedHigh: first.high,
    reason: isNight && premiumLike ? 'night_premium_range_use_low' : 'first_hourly_amount'
  };
}

export function extractShift(input = '') {
  const s = normalizeText(input);
  if (/夜勤|翌|20:00|21:00|22:00|23:00|24:00|29:00/.test(s)) return 'night';
  if (/日勤|8:00|9:00|10:00/.test(s)) return 'day';
  return 'unknown';
}

export function generateSearchQueries(job) {
  const station = job.station || '';
  const city = job.city || '';
  const product = job.product || '';
  const tasks = (job.tasks || []).filter(Boolean);
  const company = job.company || '';
  const shiftWord = job.shift === 'night' ? '夜勤' : job.shift === 'day' ? '日勤' : '';
  const phrase = (job.distinctivePhrase || '').trim();
  const topTasks = tasks.slice(0, 3).join(' ');

  // Multiple independent search routes are intentional. One-query search misses competitors.
  const raw = [
    [station, product, topTasks, '求人'].join(' '),
    [station, product, shiftWord, '派遣 時給'].join(' '),
    [city, station, topTasks, '派遣'].join(' '),
    phrase ? `"${phrase}" 求人` : '',
    company ? [company, station, product, topTasks].join(' ') : '',
    // Crucial competitor-discovery route: deliberately omit the pasted job's company.
    [station, product, tasks[0] || '', '派遣 求人'].join(' ')
  ];
  return [...new Set(raw.map(q => q.replace(/\s+/g, ' ').trim()).filter(q => q.length >= 4))];
}

function taskSignature(tasks = []) {
  return [...new Set(tasks.map(x => normalizeText(x)).filter(Boolean))].sort().join('|');
}

export function crossMediaFingerprint(job) {
  // URL/job ID are deliberately excluded: the same vacancy is often syndicated under different IDs.
  return [
    normalizeText(job.company || ''),
    normalizeText(job.city || ''),
    normalizeText(job.station || ''),
    job.shift || 'unknown',
    Number(job.baseHourly || 0),
    taskSignature(job.tasks || [])
  ].join('::');
}

export function dedupeCrossMedia(rows = []) {
  const groups = new Map();
  for (const row of rows) {
    const key = crossMediaFingerprint(row);
    const group = groups.get(key) || [];
    group.push(row);
    groups.set(key, group);
  }
  return [...groups.values()].map(group => ({
    ...group[0],
    duplicateCount: group.length,
    sourceUrls: [...new Set(group.map(x => x.url).filter(Boolean))]
  }));
}

export function sameWorkRate(a, b) {
  const A = new Set((a.tasks || []).map(normalizeText));
  const B = new Set((b.tasks || []).map(normalizeText));
  const inter = [...A].filter(x => B.has(x)).length;
  const f1 = A.size && B.size ? (2 * inter) / (A.size + B.size) : 0;
  const sameStation = a.station && b.station && normalizeText(a.station) === normalizeText(b.station);
  const sameCity = a.city && b.city && normalizeText(a.city) === normalizeText(b.city);
  const sameShift = a.shift !== 'unknown' && a.shift === b.shift;
  const sameProduct = a.product && b.product && normalizeText(a.product) === normalizeText(b.product);
  const roleConflict = a.role && b.role && a.role !== 'mixed' && b.role !== 'mixed' && a.role !== b.role;

  let score = (sameStation ? 30 : sameCity ? 14 : 0) + (sameShift ? 20 : 0) + (sameProduct ? 15 : 0) + f1 * 35;
  if (!sameCity) score = Math.min(score, 39);
  if (!sameShift) score = Math.min(score, 59);
  if (!sameProduct) score = Math.min(score, 49);
  if (roleConflict) score = Math.min(score, 49);
  if (A.size < 2 || B.size < 2) score = Math.min(score, 69);

  // Product requirement: never display 100%.
  return Math.max(0, Math.min(99, Math.round(score)));
}

export function chooseBestPerCompany(rows = []) {
  const groups = new Map();
  for (const row of rows) {
    const key = normalizeText(row.company || 'company_unknown');
    const group = groups.get(key) || [];
    group.push(row);
    groups.set(key, group);
  }
  return [...groups.values()].map(group => {
    group.sort((a, b) => (b.baseHourly || 0) - (a.baseHourly || 0) || (b.sameWorkRate || 0) - (a.sameWorkRate || 0));
    return { ...group[0], sameCompanyCandidateCount: group.length };
  });
}
