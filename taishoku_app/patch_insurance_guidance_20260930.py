#!/usr/bin/env python3
"""Make health-insurance guidance concrete and current for the 2026 MyNa-insurance flow."""
from pathlib import Path
import sys

root = Path(sys.argv[1])

def replace_once(path, old, new, label):
    text = path.read_text(encoding='utf-8')
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected one match, got {count}')
    path.write_text(text.replace(old, new, 1), encoding='utf-8')

partial = root / 'workflow_webhook_v0.1' / 'partial_guidance.mjs'
replace_once(
    partial,
    '体調不良が仕事や通勤に関係していそうな場合は、健康保険と労災で扱いが変わります。ここでは決めきれないので、健康保険や労災の窓口で確認してください。',
    '仕事や通勤が原因かもしれない場合は、会社の人事・給与担当に「労災になるか、傷病手当金はどこへ聞けばいいか」を確認してください。会社に聞きづらければ、労働基準監督署でも相談できます。',
    'partial work-related destination'
)

web = root / 'workflow_webhook_v0.1' / 'webhook_server.mjs'
replace_once(
    web,
    "if (missing.includes('cause_work_related')) hints.push('仕事や通勤との関係がありそうなら、健康保険や労災の窓口で確認してください。');",
    "if (missing.includes('cause_work_related')) hints.push('仕事や通勤が原因かもしれない場合は、会社の人事・給与担当に「労災になるか、傷病手当金はどこへ聞けばいいか」を確認してください。会社に聞きづらければ、労働基準監督署でも相談できます。');",
    'web work-related destination'
)

evaluate = root / 'workflow_rule_package_v0.1' / 'evaluate.mjs'
for old, new, label in [
    (
        '休んだ日に給与や手当が一部支払われている場合、傷病手当金は差額だけ支給されることがあります。加入している健康保険へ確認してください。',
        '休んだ日に給与や手当が一部出ている場合、傷病手当金は差額だけになることがあります。傷病手当金の申請先（協会けんぽ支部・健康保険組合など）へ確認してください。',
        'eval partial pay'
    ),
    (
        '休んだ日に給与などが通常どおり支払われている場合、傷病手当金が支給されない日があります。対象日ごとの扱いは、加入している健康保険へ確認してください。',
        '休んだ日に給与などが通常どおり出ている場合、傷病手当金が出ない日があります。対象日ごとの扱いは、傷病手当金の申請先（協会けんぽ支部・健康保険組合など）へ確認してください。',
        'eval full pay'
    ),
    (
        '退職後も傷病手当金を続けて受ける場合、退職日に出勤すると退職翌日以降は受け取れません。退職日や最終出勤日を決める前に、加入している健康保険へ確認してください。',
        '退職後も傷病手当金を続けて受けたい場合は、退職日や最終出勤日を決める前に、傷病手当金の申請先（協会けんぽ支部・健康保険組合など）へ「退職日に出勤すると継続給付にどう影響するか」を確認してください。',
        'eval post-exit attendance'
    ),
    (
        "'加入している健康保険・会社'",
        "'傷病手当金の申請先（協会けんぽ・健康保険組合など）／会社の人事'",
        'eval SHO destination'
    ),
    (
        "'家族側の健康保険・以前の健康保険・市区町村'",
        "'家族の勤務先の人事／退職前の加入先（協会けんぽ・健康保険組合）／住んでいる市区町村'",
        'eval post-exit choices destination'
    ),
    (
        "'以前の健康保険'",
        "'退職前の加入先（協会けんぽ・健康保険組合）'",
        'eval voluntary continuation destination'
    ),
    (
        "'加入している健康保険・ハローワーク'",
        "'傷病手当金の申請先（協会けんぽ・健康保険組合など）／ハローワーク'",
        'eval sickness and HW destination'
    ),
]:
    replace_once(evaluate, old, new, label)

template = root / 'report_template_v0.1' / 'report_template.html'
for old, new, label in [
    (
        '家族の健康保険の扶養に入れる場合は、自分で健康保険料を払わずに済むことがあります。続柄、同居・別居、今後の収入見込み、失業手当や傷病手当金の扱いを、家族が加入している健康保険へ確認してください。',
        '家族の扶養に入れる場合は、自分で健康保険料を払わずに済むことがあります。家族の勤務先の人事・総務に「健康保険の扶養に入れる条件を確認したい」と伝えてください。収入見込みや、失業手当・傷病手当金を受ける場合の扱いも一緒に確認します。',
        'template family dependent'
    ),
    (
        '退職前に加入していた健康保険を、退職後も続ける方法です。申出期限と保険料を、退職前の健康保険へ確認してください。',
        '退職前の健康保険を、退職後も続ける方法です。退職前の加入先が協会けんぽなら協会けんぽ、健康保険組合ならその組合へ「任意継続の期限と保険料を確認したい」と伝えてください。加入先が分からなければ、マイナポータルの健康保険の資格情報で確認できます。',
        'template voluntary continuation'
    ),
    (
        '給付を受けられるか、離職理由がどう扱われるかなどの最終判断は、健康保険やハローワークなどの窓口が行います。',
        '給付を受けられるか、離職理由がどう扱われるかなどの最終判断は、協会けんぽ・健康保険組合・ハローワークなどの窓口が行います。',
        'template final authority'
    ),
]:
    replace_once(template, old, new, label)

renderer = root / 'report_template_v0.1' / 'render_report.py'
for old, new, label in [
    (
        "('協会けんぽ｜傷病手当金', 'https://www.kyoukaikenpo.or.jp/benefit/injury_and_sickness_allowance/'),",
        "('厚生労働省｜マイナ保険証・資格確認書などの資格確認方法', 'https://www.mhlw.go.jp/stf/newpage_50657.html'),\n    ('協会けんぽ｜傷病手当金', 'https://www.kyoukaikenpo.or.jp/benefit/injury_and_sickness_allowance/'),",
        'renderer add MHLW qualification source'
    ),
    (
        '退職日や最終出勤日を決める前に、加入している健康保険へ確認してください。',
        '退職日や最終出勤日を決める前に、傷病手当金の申請先へ「退職日に出勤すると、退職後の継続給付にどう影響するか」を確認してください。申請先が分からなければ、マイナポータルの健康保険の資格情報で加入先を確認できます。',
        'renderer retirement-day warning'
    ),
    (
        "'SHO_NEED_INSURANCE_CONFIRMATION': 'まず、現在加入している健康保険を確認してください。',",
        "'SHO_NEED_INSURANCE_CONFIRMATION': 'まず、マイナポータルの健康保険の資格情報で加入先の名前を確認してください。協会けんぽなら協会けんぽ、○○健康保険組合ならその組合が傷病手当金の問い合わせ先です。マイナポータルが使えなければ、「資格情報のお知らせ」や「資格確認書」を見るか、会社の人事に「傷病手当金の問い合わせ先を教えてください」と聞けば大丈夫です。',",
        'renderer insurance destination'
    ),
    (
        '確認するポイントは主に5つです。①加入している健康保険、②普段の仕事ができない状態か、③最初の連続3日間の待期ができているか、④4日目以降に休んだ日があるか、⑤休んだ日に給与や手当が出ているか。',
        '確認するポイントは主に5つです。①傷病手当金の申請先、②普段の仕事ができない状態か、③最初の連続3日間の待期ができているか、④4日目以降に休んだ日があるか、⑤休んだ日に給与や手当が出ているか。',
        'renderer five points'
    ),
    (
        '必要な申請書をそろえて、加入している健康保険へ申請します。原則として、申請する休業期間が終わったあとに、その期間分を申請します。',
        '必要な申請書をそろえて、協会けんぽに加入しているなら協会けんぽ、健康保険組合ならその組合へ申請します。加入先が分からなければ、マイナポータルの健康保険の資格情報で確認できます。原則として、申請する休業期間が終わったあとに、その期間分を申請します。',
        'renderer application destination'
    ),
    (
        '該当する場合は、加入している健康保険へ確認してください。',
        '該当する場合は、傷病手当金の申請先（協会けんぽ・健康保険組合など）へ確認してください。',
        'renderer other benefits'
    ),
]:
    replace_once(renderer, old, new, label)

replace_once(
    renderer,
    '      <h2>傷病手当金</h2>',
    '''      <h2>傷病手当金</h2>
      <div class="notice compact"><strong>どこに聞けばいい？</strong><p>マイナポータルの健康保険の資格情報で「保険者名」を確認してください。協会けんぽなら協会けんぽ、○○健康保険組合ならその組合が問い合わせ先です。マイナポータルが使えないときは、「資格情報のお知らせ」や「資格確認書」を見るか、会社の人事に「傷病手当金の問い合わせ先を教えてください」と聞けば大丈夫です。</p></div>''',
    'renderer visible destination box'
)

finalizer = root / 'workflow_pipeline_v0.1' / 'instant_finalize.mjs'
replace_once(
    finalizer,
    '<li><strong>傷病手当金：</strong>加入している健康保険。協会けんぽの場合は<a href="https://www.kyoukaikenpo.or.jp/benefit/injury_and_sickness_allowance/" target="_blank" rel="noopener noreferrer">傷病手当金の公式案内</a></li>',
    '<li><strong>傷病手当金：</strong>マイナポータルの健康保険の資格情報で加入先を確認してください。協会けんぽなら協会けんぽ、健康保険組合ならその組合へ。分からなければ会社の人事に「傷病手当金の問い合わせ先を教えてください」と聞けば大丈夫です。<a href="https://www.mhlw.go.jp/stf/newpage_50657.html" target="_blank" rel="noopener noreferrer">加入先の確認方法</a>／<a href="https://www.kyoukaikenpo.or.jp/benefit/injury_and_sickness_allowance/" target="_blank" rel="noopener noreferrer">傷病手当金の公式案内</a></li>',
    'finalizer sickness destination'
)
replace_once(
    finalizer,
    '<li><strong>退職後の健康保険：</strong>任意継続は加入していた健康保険、国民健康保険はお住まいの市区町村。<a href="https://www.kyoukaikenpo.or.jp/faq/voluntary_continuation/001/" target="_blank" rel="noopener noreferrer">退職後の健康保険の公式案内</a></li>',
    '<li><strong>退職後の健康保険：</strong>任意継続は退職前の加入先（協会けんぽ・健康保険組合）、国民健康保険は住んでいる市区町村へ確認してください。退職前の加入先はマイナポータルの健康保険の資格情報で確認できます。<a href="https://www.kyoukaikenpo.or.jp/faq/voluntary_continuation/001/" target="_blank" rel="noopener noreferrer">任意継続の公式案内</a></li>',
    'finalizer post-exit insurance'
)

print('2026 insurance destination guidance applied')
