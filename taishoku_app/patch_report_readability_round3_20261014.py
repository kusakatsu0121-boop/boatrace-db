#!/usr/bin/env python3
"""Third readability pass: show retirement-day warning only when needed and fix section numbering."""
from pathlib import Path
import re
import sys

root=Path(sys.argv[1])
renderer=root/'report_template_v0.1'/'render_report.py'

text=renderer.read_text(encoding='utf-8')

# Sickness allowance now appears before unemployment whenever active, so it is section 02.
old='''      <div class="section-kicker">03</div>
      <h2>傷病手当金</h2>'''
new='''      <div class="section-kicker">02</div>
      <h2>傷病手当金</h2>'''
if text.count(old)!=1:
    raise SystemExit(f'sickness section-number block expected once, got {text.count(old)}')
text=text.replace(old,new,1)

# Replace the blanket post-exit attendance warning with status-aware guidance.
old_func='''    sho = result.get('sickness_allowance', {})
    if sho.get('post_exit'):
        parts.append(
            '<div class="notice critical"><strong>！退職日に出勤する前に確認</strong>'
            '<p>退職後も傷病手当金を続けたい場合、退職日の出勤が影響します。退職日を決める前に、退職前の健康保険へ「退職日に出勤すると、退職後の傷病手当金にどう影響しますか？」と確認してください。</p></div>'
        )
'''
new_func='''    sho = result.get('sickness_allowance', {})
    post_exit_code = (sho.get('post_exit') or {}).get('status_code')
    worked_on_exit_date = answer.get('worked_on_exit_date')
    if post_exit_code == 'SHO_POST_EXIT_ATTENDANCE_BLOCK':
        if answer.get('employment_status') == 'retired':
            parts.append(
                '<div class="notice critical"><strong>！退職日の勤務を確認してください</strong>'
                '<p>退職日に出勤している場合は、退職後の傷病手当金に影響します。退職前に加入していた健康保険へ、退職日の勤務実績を伝えて確認してください。</p></div>'
            )
        else:
            parts.append(
                '<div class="notice critical"><strong>！退職日に出勤する前に確認</strong>'
                '<p>退職日に出勤する予定なら、出勤前に退職前の健康保険へ「退職日に出勤すると、退職後の傷病手当金にどう影響しますか？」と確認してください。</p></div>'
            )
    elif post_exit_code == 'SHO_POST_EXIT_NEED_CONFIRMATION' and worked_on_exit_date not in {'worked_or_planned', 'not_worked_or_not_planned'}:
        parts.append(
            '<div class="notice warning"><strong>退職日の出勤予定を確認してください</strong>'
            '<p>退職後も傷病手当金を続けたい場合は、退職日に出勤するかどうかを先に確認してください。</p></div>'
        )
'''
if text.count(old_func)!=1:
    raise SystemExit(f'critical-warning block expected once, got {text.count(old_func)}')
text=text.replace(old_func,new_func,1)
renderer.write_text(text,encoding='utf-8')
print('third retirement readability pass applied')
