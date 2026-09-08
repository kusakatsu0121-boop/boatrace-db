// Motto Takakunai - live search logic helpers
// Search-first design: do not rely on a growing fixed jobs database.

export function normalizeText(input = '') {
  return String(input)
    .replace(/[０-９]/g, c => String.fromCharCode(c.charCodeAt(0) - 65248))
    .replace(/[，]/g, ',')
    .replace(/[〜～]/g, '～')
    .replace(/\s+/g, ' ')
    .trim()
    .toLowerCase();
}

const TASK_ALIASES = {
  '検品': ['検品', 'チェック', '傷確認', 'キズ確認', '目視確認', '品質確認', '動作チェック'],
  '照合': ['照合', 'ラベル照合', 'リスト照合', '注文照合', '品番確認'],
  '入力': ['入力', 'データ入力', 'pc入力', 'システム入力', '登録'],
  '開梱': ['開梱', '開封', '箱を開ける'],
  '梱包': ['梱包', '箱詰め', '段ボールにつめる', '包装'],
  '発送': ['発送', '出荷', '発送準備', '送付準備'],
  '仕分け': ['仕分け', '分類', '振り分け'],
  '棚入れ': ['棚入れ', '棚に入れる', '格納'],
  '入荷': ['入荷', '入庫', '受入'],
  'ピッキング': ['ピッキング', '集品'],
  '撮影': ['撮影', '写真撮影'],
  'スキャン': ['スキャン', 'バーコード', '読み取り'],
  'ケース収納': ['ケース収納', 'ケースに入れる', 'ケースセット', 'ケースへのセット'],
  '封入': ['封入', '袋入れ'],
  '初期化': ['初期化', 'リセット'],
  '問合せ': ['問い合わせ', '問合せ', 'お問い合わせ対応'],
  '在庫管理': ['在庫管理', '在庫確認'],
  '資材発注': ['資材発注', '資材の発注']
};

export function canonicalizeTasks(tasks = [], rawText = '') {
  const text = normalizeText([rawText, ...tasks].join(' '));
  const found = [];
  for (const [canonical, aliases] of Object.entries(TASK_ALIASES)) {
    if (aliases.some(alias => text.includes(normalizeText(alias)))) found.push(canonical);
  }
  return [...new Set(found)].sort();
}

export function normalizeBaseHourly(input = '') {
  const s = normalizeText(input).replace(/,/g, '');
  const hourly = [...s.matchAll(/(?:基本時給|通常時給|時給)\s*[:：]?\s*(\d{3,4})(?:\s*(?:円)?\s*[～~-]\s*(\d{3,4}))?/g)]
    .map(m => ({ low: Number(m[1]), high: m[2] ? Number(m[2]) : null }));
  if (!hourly.length) return { baseHourly: null, displayedHigh: null, confidence: 0, reason: 'hourly_not_found' };

  const first = hourly[0];
  const shift = extractShift(input);
  const premiumLike = first.high && Math.abs(first.high / first.low - 1.25) < 0.025;
  if (first.high && shift === 'night' && premiumLike) {
    return { baseHourly: first.low, displayedHigh: first.high, confidence: 0.98, reason: 'night_premium_range_use_low' };
  }
  if (first.high && first.high !== first.low) {
    return { baseHourly: first.low, displayedHigh: first.high, confidence: 0.55, reason: 'variable_hourly_range_needs_detail' };
  }
  return { baseHourly: first.low, displayedHigh: first.high, confidence: 0.95, reason: 'single_hourly_amount' };
}

function parseStartHours(s) {
  const hours = [];
  for (const m of s.matchAll(/(?:^|[^\d])(\d{1,2}):\d{2}\s*(?:～|-|〜|~)/g)) hours.push(Number(m[1]));
  return hours.filter(h => h >= 0 && h <= 29);
}

export function extractShiftDetailed(input = '') {
  const s = normalizeText(input);
  const starts = parseStartHours(s);
  if (starts.length) {
    const nightStarts = starts.filter(h => h >= 18 || h <= 5).length;
    const dayStarts = starts.filter(h => h >= 6 && h < 18).length;
    if (nightStarts && !dayStarts) return { shift: 'night', confidence: 0.98, reason: 'explicit_start_time' };
    if (dayStarts && !nightStarts) return { shift: 'day', confidence: 0.98, reason: 'explicit_start_time' };
  }
  const hasNight = /夜勤|深夜|翌\d|翌朝/.test(s);
  const hasDay = /日勤|昼勤/.test(s);
  if (hasNight && !hasDay) return { shift: 'night', confidence: 0.9, reason: 'explicit_label' };
  if (hasDay && !hasNight) return { shift: 'day', confidence: 0.9, reason: 'explicit_label' };
  if (hasNight && hasDay) return { shift: 'unknown', confidence: 0.25, reason: 'conflicting_shift_labels' };
  return { shift: 'unknown', confidence: 0, reason: 'shift_not_found' };
}

export function extractShift(input = '') {
  return extractShiftDetailed(input).shift;
}

export function generateSearchQueries(job) {
  const station = job.station || '';
  const city = job.city || '';
  const product = job.product || '';
  const tasks = canonicalizeTasks(job.tasks || [], job.rawText || '');
  const company = job.company || '';
  const shiftWord = job.shift === 'night' ? '夜勤' : job.shift === 'day' ? '日勤' : '';
  const phrase = (job.distinctivePhrase || '').trim();
  const top2 = tasks.slice(0, 2).join(' ');
  const top3 = tasks.slice(0, 3).join(' ');

  const raw = [
    [station, product, top2, '派遣 時給'].join(' '),
    [station, product, shiftWord, '派遣'].join(' '),
    [city, station, top3, '求人'].join(' '),
    [station, top2, shiftWord, '求人'].join(' '),
    [city, product, top2, '派遣'].join(' '),
    phrase ? `"${phrase}"` : '',
    phrase ? [station, `"${phrase}"`].join(' ') : '',
    company ? [company, station, product, top2].join(' ') : '',
    [station, product, '派遣 求人'].join(' '),
    [station, tasks[0] || '', '派遣 時給'].join(' ')
  ];
  return [...new Set(raw.map(q => q.replace(/\s+/g, ' ').trim()).filter(q => q.length >= 4))];
}

export function candidateLocationGate(base, candidate) {
  const baseCity = normalizeText(base.city || '');
  const candCity = normalizeText(candidate.city || '');
  const baseStation = normalizeText(base.station || '');
  const candStation = normalizeText(candidate.station || '');

  const cityKnown = !!baseCity && !!candCity;
  const stationKnown = !!baseStation && !!candStation;
  const sameCity = cityKnown && baseCity === candCity;
  const sameStation = stationKnown && baseStation === candStation;

  if (cityKnown && !sameCity) return { pass: false, reason: 'different_city' };
  if (stationKnown && !sameStation) return { pass: false, reason: 'different_station' };
  if (!cityKnown && !stationKnown) return { pass: false, reason: 'location_unknown' };
  return { pass: true, reason: sameStation ? 'same_station' : 'same_city_station_unknown' };
}

export function filterComparisonCandidates(base, rows = []) {
  const accepted = [];
  const rejected = [];
  for (const row of rows) {
    const gate = candidateLocationGate(base, row);
    (gate.pass ? accepted : rejected).push({ ...row, locationGateReason: gate.reason });
  }
  return { accepted, rejected };
}

function taskSet(job) {
  return new Set(canonicalizeTasks(job.tasks || [], job.rawText || ''));
}

function taskSimilarity(a, b) {
  const A = taskSet(a);
  const B = taskSet(b);
  if (!A.size || !B.size) return 0;
  const inter = [...A].filter(x => B.has(x)).length;
  return (2 * inter) / (A.size + B.size);
}

export function periodClass(input = '') {
  const s = normalizeText(input);
  if (!s || /未取得|未確認|記載なし/.test(s)) return 'unknown';
  if (/長期|\d+\s*(?:か月|ヶ月|ヵ月|カ月|月)\s*以上/.test(s)) return 'long';
  if (/短期|\d+\s*(?:か月|ヶ月|ヵ月|カ月|月)\s*以内/.test(s)) return 'short';
  return 'unknown';
}

function compactPeriod(input = '') {
  return normalizeText(input)
    .replace(/\s+/g, '')
    .replace(/[（）()]/g, '')
    .replace(/開始日相談(?:ok|可)?/g, '')
    .replace(/即日/g, '')
    .trim();
}

export function comparePeriod(basePeriod = '', candidatePeriod = '') {
  const baseText = String(basePeriod || '').trim() || '期間未取得';
  const candidateText = String(candidatePeriod || '').trim() || '期間未取得';
  const baseClass = periodClass(baseText);
  const candidateClass = periodClass(candidateText);
  const wordingDifferent = compactPeriod(baseText) !== compactPeriod(candidateText);

  if (baseClass === 'unknown' || candidateClass === 'unknown') {
    return {
      relation: 'unknown',
      penalty: 0,
      baseClass,
      candidateClass,
      wordingDifferent,
      display: wordingDifferent ? `期間：${baseText} → ${candidateText}` : ''
    };
  }
  if (baseClass === candidateClass) {
    return {
      relation: wordingDifferent ? 'same_class_different_wording' : 'same',
      penalty: 0,
      baseClass,
      candidateClass,
      wordingDifferent,
      display: wordingDifferent ? `期間：${baseText} → ${candidateText}` : ''
    };
  }
  // Period wording is supporting evidence only. A short/long mismatch must never
  // override strong workplace, shift and task matches by itself.
  return {
    relation: 'different',
    penalty: 5,
    baseClass,
    candidateClass,
    wordingDifferent: true,
    display: `期間：${baseText} → ${candidateText}`
  };
}

export function crossMediaFingerprint(job) {
  return [
    normalizeText(job.company || ''),
    normalizeText(job.city || ''),
    normalizeText(job.station || ''),
    job.shift || 'unknown',
    Number(job.baseHourly || 0),
    canonicalizeTasks(job.tasks || [], job.rawText || '').join('|')
  ].join('::');
}

function likelyDuplicate(a, b) {
  if (normalizeText(a.company || '') !== normalizeText(b.company || '')) return false;
  if (normalizeText(a.city || '') !== normalizeText(b.city || '')) return false;
  if (normalizeText(a.station || '') !== normalizeText(b.station || '')) return false;
  if ((a.shift || 'unknown') !== (b.shift || 'unknown')) return false;
  if (Number(a.baseHourly || 0) !== Number(b.baseHourly || 0)) return false;
  if (a.product && b.product && normalizeText(a.product) !== normalizeText(b.product)) return false;
  return taskSimilarity(a, b) >= 0.62;
}

export function dedupeCrossMedia(rows = []) {
  const groups = [];
  for (const row of rows) {
    const group = groups.find(g => likelyDuplicate(g[0], row));
    if (group) group.push(row);
    else groups.push([row]);
  }
  return groups.map(group => {
    const ranked = [...group].sort((a, b) =>
      (Number(b.sourcePriority || 0) - Number(a.sourcePriority || 0)) ||
      (Number(b.detailCompleteness || 0) - Number(a.detailCompleteness || 0))
    );
    return {
      ...ranked[0],
      duplicateCount: group.length,
      sourceUrls: [...new Set(group.map(x => x.url).filter(Boolean))]
    };
  });
}

export function classifyPostingStatus(input = '', now = new Date()) {
  const s = normalizeText(input);
  if (/募集終了|掲載終了|この求人は終了|応募受付終了|求人情報は削除|ページが見つかりません/.test(s)) {
    return { status: 'ended', confidence: 0.99, reason: 'explicit_end_marker' };
  }
  const period = s.match(/掲載期間\s*[:：]?\s*(\d{4})\/(\d{1,2})\/(\d{1,2})\s*[～~-]\s*(\d{4})\/(\d{1,2})\/(\d{1,2})/);
  if (period) {
    const end = new Date(Number(period[4]), Number(period[5]) - 1, Number(period[6]), 23, 59, 59);
    if (end < now) return { status: 'ended', confidence: 0.96, reason: 'listing_period_expired' };
    return { status: 'active', confidence: 0.92, reason: 'listing_period_active' };
  }
  if (/応募する|webで応募|今すぐ応募|募集人数|掲載開始日/.test(s)) {
    return { status: 'active', confidence: 0.75, reason: 'active_page_signals' };
  }
  return { status: 'recheck', confidence: 0.35, reason: 'no_explicit_status' };
}

export function sameWorkRate(a, b) {
  const location = candidateLocationGate(a, b);
  if (!location.pass) return 0;

  const A = taskSet(a);
  const B = taskSet(b);
  const inter = [...A].filter(x => B.has(x)).length;
  const f1 = A.size && B.size ? (2 * inter) / (A.size + B.size) : 0;
  const sameStation = a.station && b.station && normalizeText(a.station) === normalizeText(b.station);
  const sameCity = a.city && b.city && normalizeText(a.city) === normalizeText(b.city);
  const shiftA = a.shift || 'unknown';
  const shiftB = b.shift || 'unknown';
  const sameShift = shiftA !== 'unknown' && shiftA === shiftB;
  const shiftConflict = shiftA !== 'unknown' && shiftB !== 'unknown' && shiftA !== shiftB;
  const sameProduct = a.product && b.product && normalizeText(a.product) === normalizeText(b.product);
  const roleConflict = a.role && b.role && a.role !== 'mixed' && b.role !== 'mixed' && a.role !== b.role;
  const period = comparePeriod(a.period || '', b.period || '');

  let score = (sameStation ? 30 : sameCity ? 14 : 0) + (sameShift ? 20 : 0) + (sameProduct ? 15 : 0) + f1 * 35;
  score -= period.penalty;
  if (shiftConflict) score = Math.min(score, 39);
  else if (!sameShift) score = Math.min(score, 59);
  if (!sameProduct) score = Math.min(score, 49);
  if (roleConflict) score = Math.min(score, 49);
  if (A.size < 2 || B.size < 2) score = Math.min(score, 69);

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
    // One company = one row, but first preserve the candidate that is most likely
    // to be the same actual work. Only then use pay as the tie-breaker.
    group.sort((a, b) =>
      (b.sameWorkRate || 0) - (a.sameWorkRate || 0) ||
      (b.baseHourly || 0) - (a.baseHourly || 0) ||
      (Number(b.sourcePriority || 0) - Number(a.sourcePriority || 0))
    );
    return { ...group[0], sameCompanyCandidateCount: group.length };
  });
}
