#!/usr/bin/env python3
"""Do not treat explicit false answers as missing employment-reason inputs."""
from pathlib import Path
import sys

root = Path(sys.argv[1])
target = root / 'workflow_rule_package_v0.1' / 'evaluate.mjs'
text = target.read_text(encoding='utf-8')

old = """    if (!overtime.known) {
      result.reason.status_code = 'EI_REASON_NEED_FACTS';
      result.missing_inputs.push('overtime_hours_last_6m', 'overtime_evidence', 'reason_causation');
    } else if (overtime.met && input.reason_causation === true) {
      result.reason.status_code = 'EI_REASON_TOKUTEI_JUKYU_POSSIBLE';
      if (input.overtime_evidence !== true) result.missing_inputs.push('overtime_evidence');
    }"""
new = """    if (!overtime.known) {
      result.reason.status_code = 'EI_REASON_NEED_FACTS';
      result.missing_inputs.push('overtime_hours_last_6m');
      if (input.overtime_evidence === undefined || input.overtime_evidence === null) result.missing_inputs.push('overtime_evidence');
      if (input.reason_causation === undefined || input.reason_causation === null) result.missing_inputs.push('reason_causation');
      if (input.overtime_evidence === false) result.alerts.push('時間外労働を確認できる資料は「ない」と回答されています。未入力ではありませんが、離職理由の確認では資料の有無が影響することがあります。');
    } else if (overtime.met && input.reason_causation === true) {
      result.reason.status_code = 'EI_REASON_TOKUTEI_JUKYU_POSSIBLE';
      if (input.overtime_evidence === undefined || input.overtime_evidence === null) {
        result.missing_inputs.push('overtime_evidence');
      } else if (input.overtime_evidence === false) {
        result.alerts.push('時間外労働を確認できる資料は「ない」と回答されています。未入力ではありません。ハローワークには、手元にある資料だけを持参してください。');
      }
    }"""
count=text.count(old)
if count != 1:
    raise SystemExit(f'long-hours missing block expected once, got {count}')
target.write_text(text.replace(old,new,1),encoding='utf-8')
print('explicit false evidence/causation answers no longer treated as missing')
