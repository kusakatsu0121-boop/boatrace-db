// Public-safe, non-decisional guidance for a submission awaiting human review.
// Do not render free-form Tally answers, amounts, eligibility decisions, report
// previews, or unreviewed calculated results here. Every output is constant text.
export function interimGuidanceHtml(missingInputs = [], reviewReasons = []) {
  const missing = new Set(Array.isArray(missingInputs) ? missingInputs : []);
  const reasons = Array.isArray(reviewReasons) ? reviewReasons : [];
  const tasks = [];

  if (missing.has('wage_6m_total_or_regular_month')) {
    tasks.push('賃金額は未確認のため、給付の金額目安は算出していません。金額を調べたい場合は給与明細などを確認できます。今すぐ金額を入力し直す必要はありません。');
  }
  if (reasons.some(item => String(item).includes('離職理由'))) {
    tasks.push('離職理由：離職票の記載と実際の退職経緯を照らし合わせ、違いがあれば経緯をメモしてハローワークで確認してください。');
  }
  if (reasons.some(item => String(item).includes('待期3日')) || missing.has('waiting_three_days_completed') || missing.has('payable_absence_after_waiting')) {
    tasks.push('休業の日付：仕事に就けなかった日をカレンダーに記録し、最初の連続3日、その後の休業、各日の給与・手当を分けて整理してください。');
  }
  if (missing.has('cause_work_related')) {
    tasks.push('体調不良と仕事・通勤との関係：状況と日付を整理し、会社や関係する申請窓口に確認してください。');
  }
  if (missing.has('absence_pay_status')) {
    tasks.push('休業中の給与：欠勤日について会社から給与や手当が出たか、給与明細や会社への確認で整理してください。');
  }
  if (!tasks.length) {
    tasks.push('回答の一部に確認が必要です。追加で必要な情報を運営者が確認するまで、給付の可否や金額は確定扱いにしません。');
  }

  const items = tasks.map(item => `<li>${item}</li>`).join('');
  return `<section aria-label="確認待ちの暫定道案内" style="margin-top:1.5rem;border:1px solid #bbb;border-radius:12px;padding:1rem"><h2 style="font-size:1.2rem;margin-top:0">確認待ちの暫定道案内</h2><p>分かる範囲で、次に確認することだけを整理しました。給付の可否・金額・申請期限を判定した正式なレポートではありません。</p><ol>${items}</ol><p>この案内は、確認待ちの回答を自動承認したり、未承認レポートを公開したりするものではありません。同じ回答を再送信する必要はありません。</p></section>`;
}
