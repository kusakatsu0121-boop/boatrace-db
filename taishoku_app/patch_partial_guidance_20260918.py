#!/usr/bin/env python3
"""Add strictly allowlisted interim guidance; never release the unapproved report."""
from pathlib import Path
import sys

root = Path(sys.argv[1]); target = root / 'workflow_webhook_v0.1' / 'webhook_server.mjs'
module = root / 'workflow_webhook_v0.1' / 'partial_guidance.mjs'
if not module.is_file():
    raise SystemExit('partial guidance helper missing from source overlay')
text = target.read_text(encoding='utf-8')

def replace_once(old, new, label):
    global text
    actual = text.count(old)
    if actual != 1:
        raise SystemExit(f'{label}: expected exactly one match, got {actual}')
    text = text.replace(old, new, 1)

replace_once(
    "import { resolveReportAccess, resolvePendingReview } from '../workflow_report_access_v0.1/report_access.mjs';",
    "import { resolveReportAccess, resolvePendingReview } from '../workflow_report_access_v0.1/report_access.mjs';\nimport { interimGuidanceHtml } from './partial_guidance.mjs';",
    'import partial helper',
)
replace_once(
    "hints.push('賃金額を確認していないため、金額の目安は算出できません。給与明細などを確認してください。');",
    "hints.push('賃金を確認しない場合、金額目安は算出しません。金額が必要になったときは、給与明細などで確認できます。');",
    'remove mandatory wage demand',
)
replace_once(
    '  const details = review && hints.length',
    "  const interim = review ? interimGuidanceHtml(missing, reasons) : '';\n  const details = review && hints.length",
    'only render interim for review',
)
replace_once(
    '${details}<p>同じ回答を再送信せず、運営者にお問い合わせください。</p>',
    '${details}${interim}<p>同じ回答を再送信せず、運営者にお問い合わせください。</p>',
    'embed interim below review reasons',
)
target.write_text(text, encoding='utf-8')
print('allowlisted interim guidance patched; no eligibility, amount, approval, or delivery changes')
