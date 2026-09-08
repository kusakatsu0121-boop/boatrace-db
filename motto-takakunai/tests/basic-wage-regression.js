function basicWageOf(s) {
  const text = s.replace(/,/g, '');
  const explicit = text.match(/(?:基本時給|通常時給)\s*[:：]?\s*(\d{3,4})/);
  if (explicit) return +explicit[1];

  const re = /時給\s*[:：]?\s*(\d{3,4})/g;
  let m;
  while ((m = re.exec(text))) {
    const before = text.slice(Math.max(0, m.index - 24), m.index);
    if (/深夜|夜間|割増|22時|翌\s*5時|25%/.test(before)) continue;
    return +m[1];
  }
  return null;
}

const cases = [
  ['時給1,750円／22時以降は深夜時給2,188円', 1750],
  ['深夜時給2,188円', null],
  ['22時～翌5時は時給2,188円', null],
  ['基本時給：1,750円 深夜時給2,188円', 1750],
  ['時給1,750円～2,187円', 1750],
];

let failed = 0;
for (const [input, expected] of cases) {
  const actual = basicWageOf(input);
  if (actual !== expected) {
    failed++;
    console.error({ input, expected, actual });
  }
}
if (failed) process.exit(1);
console.log(`basic wage regression: ${cases.length}/${cases.length} passed`);
