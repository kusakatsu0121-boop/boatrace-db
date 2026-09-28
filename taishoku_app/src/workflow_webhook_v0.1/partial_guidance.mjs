// Public-safe, non-decisional guidance for a submission awaiting human review.
// Do not render free-form Tally answers, amounts, eligibility decisions, report
// previews, or unreviewed calculated results here. Every output is constant text.
export function interimGuidanceHtml(missingInputs = [], reviewReasons = []) {
  const missing = new Set(Array.isArray(missingInputs) ? missingInputs : []);
  const reasons = Array.isArray(reviewReasons) ? reviewReasons : [];
  const tasks = [];

  if (missing.has('wage_6m_total_or_regular_month')) {
    tasks.push('賃金額を入力していないため、今回は金額だけ出せません。金額も見たいときは、給与明細などで確認してからもう一度お試しください。');
  }
  if (reasons.some(item => String(item).includes('離職理由'))) {
    tasks.push('離職理由をまだ確定できません。離職票が届いている場合は「離職理由」を確認し、実際の退職経緯と違うところがあればメモしてハローワークで確認してください。');
  }
  if (reasons.some(item => String(item).includes('待期3日')) || missing.has('waiting_three_days_completed') || missing.has('payable_absence_after_waiting')) {
    tasks.push('傷病手当金は「最初の連続3日」と「4日目以降」を分けて確認します。休んだ日と、その日に給与や手当が出たかをカレンダーや給与明細で確認してください。');
  }
  if (missing.has('cause_work_related')) {
    tasks.push('体調不良が仕事・通勤によるものかは、この回答だけでは判断できません。健康保険と労災で扱いが変わるため、このツールでは決めず、関係する窓口で確認してください。');
  }
  if (missing.has('absence_pay_status')) {
    tasks.push('休んだ日に会社から給与や手当が出たか分かりません。給与明細を見るか、会社に確認してください。');
  }
  if (!tasks.length) {
    tasks.push('回答だけでは確定できない項目があります。今回は給付の可否や金額を断定しません。');
  }

  const items = tasks.map(item => `<li>${item}</li>`).join('');
  return `<section aria-label="確認待ちの案内" style="margin-top:1.5rem;border:1px solid #d9dee6;border-radius:14px;padding:1rem;background:#f8fafc"><h2 style="font-size:1.15rem;margin-top:0">次に確認すること</h2><p>今回は、確認できていない点だけを表示します。</p><ol>${items}</ol><p>同じ内容をそのまま送り直しても結果は変わりません。確認できる情報が増えたら、最初からもう一度お試しください。</p></section>`;
}
