#!/usr/bin/env python3
"""Add a fixed caution and official confirmation destinations before instant report approval."""
from pathlib import Path
import sys

root = Path(sys.argv[1])
target = root / 'workflow_pipeline_v0.1' / 'instant_finalize.mjs'
text = target.read_text(encoding='utf-8')

anchor = "export async function finalizeInstantReport({ outputRoot, referenceId, token, timeoutMs = 120000 }) {"
if text.count(anchor) != 1:
    raise SystemExit('finalize anchor missing or duplicated')

helper = r'''
const REPORT_CAUTION_MARKER = 'data-taishoku-report-caution="v1"';

function addReportCaution(jobDir) {
  const htmlPath = path.join(jobDir, 'report_preview.html');
  if (!fs.existsSync(htmlPath)) throw new Error('report_preview_missing_before_caution');
  let html = fs.readFileSync(htmlPath, 'utf8');
  if (html.includes(REPORT_CAUTION_MARKER)) return;

  const caution = `
<section ${REPORT_CAUTION_MARKER} style="max-width:900px;margin:16px auto;padding:16px 18px;border:1px solid #d9dee6;border-radius:14px;background:#f8fafc;color:#18202a;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;line-height:1.7">
  <h2 style="font-size:1.05rem;margin:0 0 8px">この結果を見る前に</h2>
  <p style="margin:0 0 10px">このレポートは、入力した内容をもとに整理した目安です。受給可否、最終的な支給額、離職理由、申請期限などを確定するものではありません。実際の手続きでは、手元の書類と各窓口の案内を確認してください。</p>
  <ul style="margin:0;padding-left:1.3rem">
    <li><strong>失業給付・離職理由：</strong>住所地を管轄するハローワーク。<a href="https://www.mhlw.go.jp/stf/seisakunitsuite/bunya/0000135026.html" target="_blank" rel="noopener noreferrer">厚生労働省「基本手当について」</a></li>
    <li><strong>傷病手当金：</strong>加入している健康保険。協会けんぽの場合は<a href="https://www.kyoukaikenpo.or.jp/benefit/injury_and_sickness_allowance/" target="_blank" rel="noopener noreferrer">傷病手当金の公式案内</a></li>
    <li><strong>退職後の健康保険：</strong>任意継続は加入していた健康保険、国民健康保険はお住まいの市区町村。<a href="https://www.kyoukaikenpo.or.jp/faq/voluntary_continuation/001/" target="_blank" rel="noopener noreferrer">退職後の健康保険の公式案内</a></li>
    <li><strong>退職後の年金：</strong>日本年金機構・年金事務所。<a href="https://www.nenkin.go.jp/service/mokutekibetsu/kojin/kanyu/index.html" target="_blank" rel="noopener noreferrer">年金加入の公式案内</a></li>
    <li><strong>会社が作る書類：</strong>離職票、退職証明書、健康保険の資格喪失関係などは勤務先の人事・給与担当にも確認してください。</li>
  </ul>
</section>`;

  const body = html.match(/<body\b[^>]*>/i);
  if (body) {
    const pos = body.index + body[0].length;
    html = html.slice(0, pos) + caution + html.slice(pos);
  } else {
    html = caution + html;
  }
  fs.writeFileSync(htmlPath, html, 'utf8');
}

'''
text = text.replace(anchor, helper + anchor, 1)

old = """  const result = await approve(
    jobDir,"""
new = """  addReportCaution(jobDir);

  const result = await approve(
    jobDir,"""
if text.count(old) != 1:
    raise SystemExit(f'approve insertion point expected once, got {text.count(old)}')
text = text.replace(old, new, 1)

target.write_text(text, encoding='utf-8')
print('instant report caution added before approval snapshot')
