// Duplicate reconciliation for live-search candidates.
// Goal: do not treat list/detail copies or stale mirrors with different wages as separate offers.

function n(v = '') {
  return String(v).toLowerCase().replace(/[０-９]/g, c => String.fromCharCode(c.charCodeAt(0) - 65248)).replace(/\s+/g, ' ').trim();
}

function taskSet(row) {
  return new Set((row.tasks || []).map(n).filter(Boolean));
}

function taskF1(a, b) {
  const A = taskSet(a), B = taskSet(b);
  if (!A.size || !B.size) return 0;
  const inter = [...A].filter(x => B.has(x)).length;
  return (2 * inter) / (A.size + B.size);
}

export function likelySamePostingFamily(a, b) {
  if (n(a.company) !== n(b.company)) return false;
  if (n(a.city) !== n(b.city)) return false;
  if (n(a.station) !== n(b.station)) return false;
  if ((a.shift || 'unknown') !== (b.shift || 'unknown')) return false;
  if (a.product && b.product && a.product !== 'unknown' && b.product !== 'unknown' && n(a.product) !== n(b.product)) return false;
  if (a.role && b.role && a.role !== 'mixed' && b.role !== 'mixed' && n(a.role) !== n(b.role)) return false;
  const walkA = Number(a.walkMinutes || 0), walkB = Number(b.walkMinutes || 0);
  if (walkA && walkB && Math.abs(walkA - walkB) > 3) return false;
  return taskF1(a, b) >= 0.75;
}

function sourceRank(row) {
  if (row.sourceType === 'detail') return 3;
  if (row.sourceType === 'listing') return 2;
  return 1;
}

export function reconcilePriceConflicts(rows = []) {
  const groups = [];
  for (const row of rows) {
    const group = groups.find(g => likelySamePostingFamily(g[0], row));
    if (group) group.push(row);
    else groups.push([row]);
  }

  return groups.map(group => {
    const wages = [...new Set(group.map(x => Number(x.baseHourly || 0)).filter(Boolean))].sort((a, b) => b - a);
    const ranked = [...group].sort((a, b) =>
      sourceRank(b) - sourceRank(a) ||
      Number(b.postingStatus === 'active') - Number(a.postingStatus === 'active') ||
      Number(b.baseHourly || 0) - Number(a.baseHourly || 0)
    );
    const selected = ranked[0];
    return {
      ...selected,
      duplicateFamilyCount: group.length,
      priceConflict: wages.length > 1,
      observedBaseHourlies: wages,
      alternateUrls: [...new Set(group.map(x => x.url).filter(Boolean))],
      reconciliationReason: wages.length > 1
        ? 'same posting family has conflicting wages; prefer direct detail page, keep all observed wages for recheck'
        : group.length > 1
          ? 'same posting family duplicated across sources'
          : 'single source'
    };
  });
}
