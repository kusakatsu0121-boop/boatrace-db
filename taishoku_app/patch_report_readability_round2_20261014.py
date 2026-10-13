#!/usr/bin/env python3
"""Second readability pass: correct priority/order and remove completed-action noise."""
from pathlib import Path
import sys

root=Path(sys.argv[1])
renderer=root/'report_template_v0.1'/'render_report.py'
template=root/'report_template_v0.1'/'report_template.html'
evaluate=root/'workflow_rule_package_v0.1'/'evaluate.mjs'

def replace_once(path, old, new, label):
    text=path.read_text(encoding='utf-8')
    count=text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected one match, got {count}')
    path.write_text(text.replace(old,new,1),encoding='utf-8')

# Clearer, shorter first heading/instruction.
replace_once(
    template,
    '<h1>あなた専用｜退職前後ワークフロー</h1>',
    '<h1>退職前後｜あなたが今やること</h1>',
    'hero h1'
)
replace_once(
    template,
    '<p class="lead">最初は「まずやること」だけ見れば大丈夫です。詳しい説明は、必要なところだけ開けます。</p>',
    '<p class="lead">最初は「まずやること」だけ確認してください。詳しい説明は、必要なところだけ開けます。</p>',
    'hero lead'
)

# If sickness allowance is relevant it must appear before unemployment benefit.
old_order='''  <section class="report-page">
    <div class="section-kicker">02</div>
    <h2>失業手当（基本手当）</h2>
    {{employment_benefit_summary}}
    {{employment_name_note}}
    {{employment_flow}}
    {{employment_reason_note}}
    {{reemployment_note}}
  </section>

  {{sickness_section}}
'''
new_order='''  {{sickness_section}}

  <section class="report-page">
    <div class="section-kicker">{{employment_section_number}}</div>
    <h2>失業手当（基本手当）</h2>
    {{employment_benefit_summary}}
    {{employment_name_note}}
    {{employment_flow}}
    {{employment_reason_note}}
    {{reemployment_note}}
  </section>
'''
replace_once(template,old_order,new_order,'benefit section order')

# Renumber sections after moving sickness ahead of unemployment.
text=renderer.read_text(encoding='utf-8')
old_values="""        'sickness_section': sickness_section(answer, result),
        'insurance_section_number': '04' if has_sho else '03',
        'other_section_number': '05' if has_sho else '04',
"""
new_values="""        'sickness_section': sickness_section(answer, result),
        'employment_section_number': '03' if has_sho else '02',
        'insurance_section_number': '04' if has_sho else '03',
        'other_section_number': '05' if has_sho else '04',
"""
if text.count(old_values)!=1:
    raise SystemExit('section-number value block missing')
renderer.write_text(text.replace(old_values,new_values,1),encoding='utf-8')

# The retirement-day warning is important, but the current paragraph repeats itself and
# pushes the action list far down on mobile. Keep the action and the exact question only.
old_warning="""            '<div class="notice critical"><strong>！重要：退職日に出勤する予定がある場合</strong>'
            '<p>退職後も傷病手当金を続けて受ける予定なら、退職日に出勤するかどうかが重要です。退職日に出勤すると、退職翌日以降の傷病手当金は受け取れません。退職日や最終出勤日を決める前に、傷病手当金の申請先へ「退職日に出勤すると、退職後の継続給付にどう影響するか」を確認してください。申請先が分からなければ、マイナポータルの健康保険の資格情報で加入先を確認できます。</p></div>'"""
new_warning="""            '<div class="notice critical"><strong>！退職日に出勤する前に確認</strong>'
            '<p>退職後も傷病手当金を続けたい場合、退職日の出勤が影響します。退職日を決める前に、退職前の健康保険へ「退職日に出勤すると、退職後の傷病手当金にどう影響しますか？」と確認してください。</p></div>'"""
replace_once(renderer,old_warning,new_warning,'short retirement-day warning')

# Do not tell a person to check voluntary-continuation deadlines after they already
# answered that their post-exit health-insurance procedure is complete.
text=evaluate.read_text(encoding='utf-8')
old_task="""    tasks.push(task('ACT-POST-VC', '任意継続を選ぶ場合は申出期限を確認する', '資格喪失日から20日以内', '退職前の加入先（協会けんぽ・健康保険組合）', '任意継続には申出期限があるため', 'high', 'ACT-POST-01', { rank: 5, status: 'unknown' }));"""
new_task="""    if (input.post_exit_health_insurance_done !== true) {
      tasks.push(task('ACT-POST-VC', '任意継続を選ぶ場合は申出期限を確認する', '資格喪失日から20日以内', '退職前の加入先（協会けんぽ・健康保険組合）', '任意継続には申出期限があるため', 'high', 'ACT-POST-01', { rank: 5, status: 'unknown' }));
    }"""
if text.count(old_task)!=1:
    raise SystemExit('ACT-POST-VC task line missing')
evaluate.write_text(text.replace(old_task,new_task,1),encoding='utf-8')

print('second retirement readability pass applied')
