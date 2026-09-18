#!/usr/bin/env python3
"""Explain review-required instant reports without exposing an unapproved report."""
from pathlib import Path
import sys

root = Path(sys.argv[1]); target = root / 'workflow_webhook_v0.1' / 'webhook_server.mjs'
text = target.read_text(encoding='utf-8')

def replace_once(old, new, label):
    global text
    n = text.count(old)
    if n != 1:
        raise SystemExit(f'{label}: expected exactly one match, found {n}')
    text = text.replace(old, new, 1)

old_page = '''function reportUnavailablePage() {
  return '<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>レポートの確認が必要です</title></head><body style="font-family:sans-serif;max-width:36rem;margin:10vh auto;padding:1.5rem;line-height:1.8"><h1>レポートを表示できませんでした</h1><p>回答内容の確認、または処理の再確認が必要です。自動的に公開することはありません。重複送信はせず、運営者にお問い合わせください。</p></body></html>';
}'''
new_page = '''function reportUnavailablePage(outputRoot, token) {
  const state = readInstantStatus(outputRoot, token);
  const review = state?.status === 'review_required';
  const hints = [];
  const missing = Array.isArray(state?.missing_inputs) ? state.missing_inputs : [];
  const reasons = Array.isArray(state?.review_reasons) ? state.review_reasons : [];
  if (missing.includes('wage_6m_total_or_regular_month')) hints.push('賃金額を確認していないため、金額の目安は算出できません。給与明細などを確認してください。');
  if (missing.includes('cause_work_related')) hints.push('体調不良と仕事・通勤との関係が未確認です。加入する健康保険や相談窓口で確認してください。');
  if (reasons.some(v => String(v).includes('待期3日'))) hints.push('連続した待期3日と4日目以降の休業・給与を分けて確認してください。');
  if (reasons.some(v => String(v).includes('離職理由'))) hints.push('離職理由の区分について、離職票や会社とのやり取りを確認してください。');
  const title = review ? '確認が必要な項目があります' : 'レポートを表示できませんでした';
  const explanation = review
    ? '回答は受け付けましたが、給付の判断に確認が必要なため、レポートはまだ公開していません。'
    : 'レポートの処理が正常に完了しませんでした。回答内容に問題があると決まったわけではありません。';
  const details = review && hints.length
    ? `<h2 style="font-size:1.1rem">確認すること</h2><ul>${hints.map(v => `<li>${v}</li>`).join('')}</ul>`
    : '';
  return `<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${title}</title></head><body style="font-family:sans-serif;max-width:36rem;margin:8vh auto;padding:1.5rem;line-height:1.8"><h1>${title}</h1><p>${explanation}</p>${details}<p>同じ回答を再送信せず、運営者にお問い合わせください。</p></body></html>`;
}'''
replace_once(old_page, new_page, 'replace unavailable page')

old_failed = '''  return state?.status === 'failed' ||
    (state?.status === 'pending' && Number.isFinite(state.started_at) && Date.now() - state.started_at > 180000);'''
new_failed = '''  return state?.status === 'failed' || state?.status === 'review_required' ||
    (state?.status === 'pending' && Number.isFinite(state.started_at) && Date.now() - state.started_at > 180000);'''
replace_once(old_failed, new_failed, 'recognize review state')

old_exit = '''    console.error(JSON.stringify({ status: 'instant_finalize_exit', reference_id: ref, exit_code: code, automatic_delivery: false }));
    try {
      writeInstantStatus(outputRoot, token, { status: 'failed', finished_at: Date.now() });'''
new_exit = '''    console.error(JSON.stringify({ status: 'instant_finalize_exit', reference_id: ref, exit_code: code, automatic_delivery: false }));
    let manifest = null;
    try { manifest = JSON.parse(fs.readFileSync(path.join(outputRoot, ref, 'job_manifest.json'), 'utf8')); } catch {}
    const reviewRequired = manifest?.status === 'review_required';
    try {
      writeInstantStatus(outputRoot, token, {
        status: reviewRequired ? 'review_required' : 'failed',
        finished_at: Date.now(),
        ...(reviewRequired ? {
          missing_inputs: Array.isArray(manifest?.missing_inputs) ? manifest.missing_inputs : [],
          review_reasons: Array.isArray(manifest?.review_reasons) ? manifest.review_reasons : [],
        } : {}),
      });'''
replace_once(old_exit, new_exit, 'classify finalizer exit')

old_call = 'reportUnavailablePage()'
if text.count(old_call) != 2:
    raise SystemExit(f'failure-page calls: expected 2, found {text.count(old_call)}')
text = text.replace(old_call, 'reportUnavailablePage(outputRoot, token)')
target.write_text(text, encoding='utf-8')
print('patched review-specific guidance; no approval, token disclosure, or delivery changes')
