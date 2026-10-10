#!/usr/bin/env python3
"""Improve retirement-report output clarity without changing benefit calculations."""
from pathlib import Path
import re
import sys

root = Path(sys.argv[1])

def replace_once(path, old, new, label):
    text = path.read_text(encoding='utf-8')
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected one match, got {count}')
    path.write_text(text.replace(old, new, 1), encoding='utf-8')

def replace_function(path, name, next_name, new_source):
    text = path.read_text(encoding='utf-8')
    pattern = rf"def {re.escape(name)}\b.*?(?=\ndef {re.escape(next_name)}\b)"
    new_text, count = re.subn(pattern, new_source.rstrip() + "\n\n", text, count=1, flags=re.S)
    if count != 1:
        raise SystemExit(f'{name}: function replacement count={count}')
    path.write_text(new_text, encoding='utf-8')

renderer = root / 'report_template_v0.1' / 'render_report.py'

replace_function(renderer, 'overview_summary', 'roadmap_rows', r'''
def overview_summary(answer: dict, result: dict) -> str:
    sho_active = bool(result.get('sickness_allowance', {}).get('active'))
    sho_state = answer.get('sickness_benefit_status')
    reason_code = (result.get('employment_insurance', {}).get('reason') or {}).get('status_code')
    retired = answer.get('employment_status') == 'retired'
    exit_planned = answer.get('exit_date_status') == 'decided' or answer.get('employment_status') in {'exit_date_fixed_employed', 'using_paid_leave'}

    if sho_active and sho_state == 'receiving':
        if retired:
            return (
                '傷病手当金を受給中です。退職後の継続給付については、現在の国民健康保険などではなく、'
                '退職前に本人として加入していた健康保険へ確認してください。'
            )
        if exit_planned:
            return (
                '傷病手当金を受給中です。退職日を決める前に、退職後も続けて受けられる条件と、'
                '退職日に出勤した場合の扱いを確認してください。'
            )
        return '傷病手当金を受給中です。次の申請期間と、会社・医師に証明してもらう範囲を確認してください。'

    if sho_active and sho_state == 'applying':
        return (
            '傷病手当金は申請中です。同じ期間を出し直すのではなく、申請先から不備や追加書類の連絡がないか確認してください。'
            + ('退職予定なら、退職後の継続給付の条件も先に確認してください。' if exit_planned else '')
        )

    if sho_active and sho_state == 'not_applied':
        return (
            '傷病手当金はまだ申請していません。まず対象になりそうかと申請先を確認し、'
            '休んだ期間の会社・医師の証明をそろえる流れを確認してください。'
        )

    if sho_active and answer.get('can_start_new_job') == 'difficult':
        return (
            '今すぐ働くのが難しい間は、失業手当より先に傷病手当金を確認してください。'
            '退職後も働けない状態が30日以上続く場合は、雇用保険の受給期間延長も確認します。'
        )

    if sho_active:
        return (
            '傷病手当金の対象になるか、必要な条件だけ確認してください。'
            '退職予定なら、退職日や最終出勤日が継続給付に影響しないかも確認します。'
        )

    if reason_code and reason_code != 'EI_REASON_GENERAL_PROVISIONAL':
        return (
            '失業手当の手続きとあわせて、離職理由を確認してください。'
            '離職票-2と実際の経緯が違う場合に備えて、勤怠や会社からの通知などを手元にまとめておきます。'
        )

    if retired:
        return '退職後に必要な手続きを、期限のあるものから順番に進めてください。'

    return '退職前に決めておくことと、退職後に期限がある手続きを先に確認してください。'
''')

replace_function(renderer, 'employment_summary', 'employment_flow', r'''
def employment_summary(answer: dict, ei: dict) -> str:
    if answer.get('age_at_exit') is not None and answer.get('age_at_exit') >= 65:
        return (
            '<div class="notice warning"><strong>65歳以上の場合は、失業手当の扱いが異なります</strong>'
            '<p>65歳以上では、一般的な基本手当ではなく、高年齢求職者給付金などの対象になる場合があります。'
            '住居所を管轄するハローワークで「65歳以上で退職したので、受けられる雇用保険の給付を確認したい」と伝えてください。</p></div>'
        )
    if answer.get('can_start_new_job') == 'difficult':
        return (
            '<div class="notice warning"><strong>今は失業手当より先に確認したいことがあります</strong>'
            '<p>失業手当は、働ける状態で仕事を探す人が対象です。今すぐ働くことが難しい場合は、まず傷病手当金を確認してください。'
            '退職後に働けない状態が30日以上続く場合は、住居所を管轄するハローワークへ'
            '「病気で今すぐ働けないので、受給期間延長の手続きを確認したい」と伝えてください。</p></div>'
        )

    scenarios = ei.get('scenarios') or []
    primary = next((x for x in scenarios if x.get('id') == 'general'), scenarios[0] if scenarios else None)
    if not primary:
        return (
            '<div class="notice compact"><strong>受給額はまだ計算できません</strong>'
            '<p>金額を出すには、年齢、退職前の賃金、雇用保険の加入期間などが必要です。'
            '離職理由が未確定でも、分かる範囲の金額は条件を明記して表示します。</p></div>'
        )

    reason_code = (ei.get('reason') or {}).get('status_code')
    uncertain_reason = reason_code in {
        'EI_REASON_NEED_FACTS',
        'EI_REASON_TOKUTEI_JUKYU_POSSIBLE',
        'EI_REASON_TOKUTEI_RIYU_POSSIBLE',
        'EI_REASON_NOTICE_DISPUTE',
    }

    total = primary.get('total_yen')
    daily = ei.get('benefit_daily_yen')
    duration = DURATION_LABELS.get(answer.get('employment_insurance_duration'), '分からない')
    days_label = f'{primary.get("days")}日' if primary.get('days') is not None else '算出できません'
    title = '失業手当の総額（一般の給付日数で仮計算）' if uncertain_reason else '失業手当の受給総額（目安）'
    premise = (
        '<p class="note"><strong>この金額の前提：</strong>'
        '離職理由はまだ確定していません。上の総額と日数は「通常の給付日数」を前提にした仮計算です。'
        'ハローワークの判断で給付日数・総額が変わる可能性があります。</p>'
        if uncertain_reason else
        '<p class="note">※実際は認定ごとに支給されます。一度にまとめて受け取る金額ではありません。</p>'
    )

    html_out = (
        '<div class="total-card">'
        f'<span class="label">{title}</span>'
        f'<span class="amount">{yen(total)}</span>'
        f'{premise}'
        '</div>'
        '<div class="metric-grid">'
        f'<div class="metric"><span>1日あたりの失業手当（目安）</span><strong>{yen(daily)}</strong></div>'
        f'<div class="metric"><span>{"仮の給付日数" if uncertain_reason else "受け取れる日数（目安）"}</span><strong>{e(days_label)}</strong></div>'
        f'<div class="metric"><span>雇用保険に入っていた期間</span><strong>{e(duration)}</strong></div>'
        '</div>'
    )

    alternatives = [x for x in scenarios if x is not primary]
    if alternatives:
        blocks = []
        for x in alternatives:
            blocks.append(
                f'<div class="scenario"><strong>{e(x.get("label"))}</strong>'
                f'<p>{e(x.get("days"))}日・{yen(x.get("total_yen"))}</p></div>'
            )
        html_out += (
            '<div class="notice warning"><strong>離職理由が認められた場合は、日数・総額が変わる可能性があります</strong>'
            '<div class="scenario-list">' + ''.join(blocks) + '</div>'
            '<p>どの区分になるかはここでは確定しません。離職票-2と実際の経緯をハローワークで確認してください。</p></div>'
        )
    elif uncertain_reason:
        html_out += (
            '<div class="notice warning"><strong>まだ確定していないこと</strong>'
            '<p>離職理由の区分が未確定です。表示した総額は一般の給付日数を使った仮計算で、確定額ではありません。</p></div>'
        )
    return html_out
''')

replace_function(renderer, 'sickness_section', 'review_content', r'''
def sickness_section(answer: dict, result: dict) -> str:
    sho = result.get('sickness_allowance', {})
    if not sho.get('active'):
        return ''

    state = answer.get('sickness_benefit_status') or 'unknown'
    state_copy = {
        'receiving': (
            '受給中',
            'すでに受給中です。初回申請の案内ではなく、次に申請する期間と、会社・医師の証明が必要な範囲を確認してください。'
        ),
        'applying': (
            '申請中',
            'すでに申請中です。同じ期間を重ねて申請せず、申請先から不備や追加書類の連絡がないか確認してください。'
        ),
        'received_before': (
            '過去に受給したことがあります',
            '以前の受給と今回の休業が同じ傷病・同じ支給期間として扱われるか、申請先へ確認してください。'
        ),
        'not_applied': (
            'まだ申請していません',
            '初めて申請する場合は、休んだ期間について本人・会社・医師が記入する申請書をそろえて申請します。'
        ),
        'unknown': (
            '申請状況を先に確認',
            '申請済みか、すでに支給を受けているか分からない場合は、申請書の控えや入金履歴を確認してください。'
        ),
    }
    state_label, state_detail = state_copy.get(state, state_copy['unknown'])

    amount = sho.get('amount') or {}
    metrics = []
    if amount.get('daily_yen') is not None:
        metrics.append(f'<div class="metric"><span>1日あたりの支給額目安</span><strong>{yen(amount.get("daily_yen"))}</strong></div>')
    if answer.get('known_total_amount') is not None:
        metrics.append(f'<div class="metric"><span>これまでに確認できた支給総額</span><strong>{yen(answer.get("known_total_amount"))}</strong></div>')
    if answer.get('known_paid_days') is not None:
        metrics.append(f'<div class="metric"><span>これまでに確認できた支給対象日数</span><strong>{int(answer.get("known_paid_days"))}日</strong></div>')
    if not metrics:
        metrics.append(
            '<div class="notice compact"><strong>金額はまだ表示していません</strong>'
            '<p>日額を出すには、支給決定通知書の日額、または標準報酬月額などの情報が必要です。</p></div>'
        )
    metric_html = '<div class="metric-grid">' + ''.join(metrics) + '</div>' if any('class="metric"' in x for x in metrics) else ''.join(metrics)

    retired = answer.get('employment_status') == 'retired'
    if retired:
        contact = (
            '<div class="notice compact"><strong>どこに聞けばいい？</strong>'
            '<p><strong>退職後の継続給付について聞く先は、現在の国民健康保険や家族の扶養先ではありません。</strong>'
            '退職前に本人として加入していた健康保険（協会けんぽ・○○健康保険組合など）へ確認してください。'
            '退職前の加入先が分からなければ、退職した会社の人事に「退職前の健康保険の問い合わせ先を教えてください」と聞けば大丈夫です。</p></div>'
        )
    else:
        contact = (
            '<div class="notice compact"><strong>どこに聞けばいい？</strong>'
            '<p>現在、会社で本人として加入している健康保険が問い合わせ先です。'
            'マイナポータルの健康保険の資格情報で「保険者名」を確認し、協会けんぽなら協会けんぽ、'
            '○○健康保険組合ならその組合へ確認してください。分からなければ会社の人事に'
            '「傷病手当金の問い合わせ先を教えてください」と聞けば大丈夫です。</p></div>'
        )

    post_exit = ''
    if sho.get('post_exit'):
        post_exit = (
            '<div class="notice warning"><strong>退職後も続けて受けたい場合</strong>'
            '<p>退職前の健康保険に本人として継続1年以上加入していたか、待期が完成しているか、'
            '退職日に出勤していないかなどを確認します。退職後に国保や扶養へ切り替えても、'
            '継続給付の確認先は退職前に本人として加入していた健康保険です。</p></div>'
        )

    cause_note = ''
    if answer.get('cause_work_related') == 'yes':
        cause_note = (
            '<div class="notice warning"><strong>仕事中・通勤中の事故やけがが関係する場合</strong>'
            '<p>傷病手当金より労災保険を先に確認する場合があります。会社の人事・労災担当、'
            'または労働基準監督署へ相談してください。</p></div>'
        )

    timing = ''
    if (sho.get('payment_timing') or {}).get('processing_business_days'):
        timing = (
            '<p>協会けんぽでは、申請書を受け付けて不備がない場合、支払いまで10営業日程度が目安です。'
            '健康保険組合は組合ごとに異なります。</p>'
        )

    if state == 'not_applied':
        application_detail = (
            '<p>申請する休業期間が終わったあと、その期間分の申請書をそろえて提出します。'
            '協会けんぽなら協会けんぽ、健康保険組合ならその組合へ提出します。'
            '傷病手当金は、支給対象となる各日について、原則としてその翌日から2年を過ぎると時効になります。</p>'
        )
    elif state == 'applying':
        application_detail = (
            '<p>申請済みなので、同じ期間を出し直す前に受付状況を確認してください。'
            '不備や追加書類の連絡が来た場合だけ、その内容に対応します。'
            '次の休業期間分を申請する場合は、対象期間が終わってから次回分を準備します。</p>'
        )
    elif state == 'receiving':
        application_detail = (
            '<p>受給中なので、初回申請ではなく次回分の対象期間と証明欄を確認してください。'
            '退職予定・退職済みの場合は、退職後の継続給付の条件も退職前の加入先へ確認します。</p>'
        )
    elif state == 'received_before':
        application_detail = (
            '<p>以前に受給したことがある場合は、今回が同じ傷病・同じ支給期間の続きかを申請先へ確認してください。'
            '新たに申請できる期間がある場合は、その期間の会社・医師の証明をそろえます。</p>'
        )
    else:
        application_detail = (
            '<p>まず、申請済みか・受給中かを確認してください。状態が分かれば、必要な次の手続きだけ案内できます。</p>'
        )

    return f'''
    <section class="report-page">
      <div class="section-kicker">03</div>
      <h2>傷病手当金</h2>
      <div class="notice compact"><strong>現在：{e(state_label)}</strong><p>{e(state_detail)}</p></div>
      {contact}
      <div class="notice compact"><strong>{e(sickness_status_text(sho.get('status_code')))}</strong></div>
      {post_exit}
      {cause_note}
      {metric_html}
      <div class="notice warning"><strong>傷病手当金と失業手当を、そのまま足し算しないでください</strong>
        <p>同じ期間に両方を満額受け取る前提の合計額ではありません。今すぐ働けない間は、傷病手当金と雇用保険の受給期間延長を先に確認します。</p>
      </div>
      <details><summary>▶ 条件を確認する</summary><div class="detail-body">
        <p>主に確認するのは、加入先、仕事ができない状態か、連続3日の待期、4日目以降の休業、休業日の給与の5点です。</p>
        <p>退職後も継続して受ける場合は、退職前の健康保険に本人として継続1年以上加入していたかなど、追加の条件があります。</p>
      </div></details>
      <details><summary>▶ 病院で伝えること</summary><div class="detail-body"><p>症状がいつからあるか、普段どんな仕事をしているか、今は何が難しいか、いつから休んでいるかを伝えてください。傷病手当金の申請を考えている場合は、そのことも医師に伝えてください。</p></div></details>
      <details><summary>▶ 申請状況に合わせた次の手続き</summary><div class="detail-body">{application_detail}{timing}</div></details>
      <details><summary>▶ ほかの給付との調整</summary><div class="detail-body"><p>老齢年金、障害年金、労災給付、出産手当金などを受けている場合は、傷病手当金の金額が調整されることがあります。該当する場合は、退職前または現在の申請先へ、どの給付を受けているか伝えて確認してください。</p></div></details>
    </section>
    '''
''')

replace_function(renderer, 'review_content', 'render', r'''
def _answer_present(answer: dict, key: str) -> bool:
    value = answer.get(key)
    return value is not None and value != '' and value != 'unknown'


def _really_missing(answer: dict, key: str) -> bool:
    if key == 'known_daily_amount_or_standard_monthly_remuneration':
        if _answer_present(answer, 'known_daily_amount'):
            return False
        values = answer.get('standard_monthly_remunerations')
        if isinstance(values, list) and len(values) > 0:
            return False
        if _answer_present(answer, 'pension_premium_regular_month') and answer.get('remuneration_changed_12m') == 'almost_same':
            return False
        return True
    if key == 'wage_6m_total_or_regular_month':
        return not (_answer_present(answer, 'wage_6m_total') or _answer_present(answer, 'wage_regular_month_estimate'))
    if key == 'overtime_hours_last_6m':
        values = answer.get('overtime_hours_last_6m')
        return not (isinstance(values, list) and len(values) > 0)
    if key in {'overtime_evidence', 'reason_causation'}:
        return answer.get(key) is None
    return not _answer_present(answer, key)


def review_section(answer: dict, result: dict) -> str:
    missing = []
    for module_name in ('sickness_allowance', 'employment_insurance'):
        for key in result.get(module_name, {}).get('missing_inputs', []) or []:
            if not _really_missing(answer, key):
                continue
            label = MISSING_LABELS.get(key, key)
            if label not in missing:
                missing.append(label)

    reasons = result.get('human_review', {}).get('reasons', []) or []
    friendly_reasons = []
    for item in reasons:
        label = REVIEW_REASON_LABELS.get(item, item)
        if label not in friendly_reasons:
            friendly_reasons.append(label)

    all_items = missing + [x for x in friendly_reasons if x not in missing]
    if not all_items:
        return ''

    return (
        '<h2>追加で確認したいこと</h2>'
        '<p class="section-lead">ここに出すのは、まだ確認できていないことだけです。</p>'
        '<ul>' + ''.join(f'<li>{e(x)}</li>' for x in all_items) + '</ul>'
    )


def meta_row(answer: dict) -> str:
    items = []
    display_name = answer.get('display_name')
    reference_id = answer.get('reference_id')
    if display_name:
        items.append(f'<span>{e(display_name)}</span>')
    if reference_id:
        items.append(f'<span>受付番号 {e(reference_id)}</span>')
    return f'<div class="meta-row">{"".join(items)}</div>' if items else ''
''')

# Make the render function use dynamic metadata and filtered review output.
text = renderer.read_text(encoding='utf-8')
text = text.replace(
    "    reasons = '・'.join(REASON_LABELS.get(x, x) for x in answer.get('exit_reasons', [])) or '未選択'\n"
    "    case_summary = f'{STATUS_LABELS.get(answer.get(\"employment_status\"), \"現在の状況：未選択\")} ／ 退職・休職を考えた主な理由：{reasons}'\n",
    "    status_label = STATUS_LABELS.get(answer.get('employment_status'), '現在の状況は未選択です')\n"
    "    reason_values = [REASON_LABELS.get(x, x) for x in answer.get('exit_reasons', [])]\n"
    "    case_parts = [status_label]\n"
    "    if reason_values:\n"
    "        case_parts.append('退職・休職を考えた主な理由：' + '・'.join(reason_values))\n"
    "    case_summary = ' ／ '.join(case_parts)\n",
    1
)
text = text.replace(
    "        'display_name': e(answer.get('display_name', 'あなた')),\n"
    "        'reference_id': e(answer.get('reference_id', '未設定')),\n",
    "        'display_name': e(answer.get('display_name') or 'あなた'),\n"
    "        'meta_row': meta_row(answer),\n",
    1
)
text = text.replace(
    "        'review_content': review_content(result),\n",
    "        'review_section': review_section(answer, result),\n",
    1
)
renderer.write_text(text, encoding='utf-8')

template = root / 'report_template_v0.1' / 'report_template.html'
replace_once(
    template,
    '<div class="meta-row"><span>{{display_name}}</span><span>受付番号 {{reference_id}}</span></div>',
    '{{meta_row}}',
    'dynamic metadata row'
)
replace_once(
    template,
    '<h2>追加で確認したいこと</h2>\n    {{review_content}}',
    '{{review_section}}',
    'filtered review section'
)

# Clarify current vs pre-retirement insurer in the fixed caution shown on successful reports.
finalizer = root / 'workflow_pipeline_v0.1' / 'instant_finalize.mjs'
ftext = finalizer.read_text(encoding='utf-8')
replacement = (
    '<li><strong>傷病手当金：</strong>在職中・休職中は、現在会社で本人として加入している健康保険へ。'
    '退職後の継続給付は、現在の国民健康保険や家族の扶養先ではなく、退職前に本人として加入していた健康保険へ確認してください。'
    '分からなければ会社の人事に「退職前の健康保険の問い合わせ先を教えてください」と聞けば大丈夫です。'
    '<a href="https://www.kyoukaikenpo.or.jp/benefit/injury_and_sickness_allowance/" target="_blank" rel="noopener noreferrer">傷病手当金の公式案内</a></li>'
)
ftext, count = re.subn(
    r'<li><strong>傷病手当金：</strong>.*?</li>',
    replacement,
    ftext,
    count=1,
    flags=re.S,
)
if count != 1:
    raise SystemExit(f'finalizer sickness contact replacement count={count}')
finalizer.write_text(ftext, encoding='utf-8')

# Replace vague timing with concrete statutory deadlines or clear trigger conditions.
evaluate = root / 'workflow_rule_package_v0.1' / 'evaluate.mjs'
for old, new, label in [
    (
        "'医療機関へ相談する', 'できるだけ早く', '医療機関'",
        "'医療機関へ相談する', '症状が続いているなら早め（法定の届出期限ではありません）', '医療機関'",
        'medical timing'
    ),
    (
        "'退職後の健康保険を選んで手続する', '退職後すみやかに'",
        "'退職後の健康保険を選んで手続する', '国保は原則14日以内／任意継続は加入先の期限を確認（協会けんぽは退職日の翌日から20日以内）'",
        'post-exit insurance timing'
    ),
    (
        "'国民年金への切替が必要か確認し、必要なら手続する', '退職後すみやかに'",
        "'国民年金への切替が必要か確認し、必要なら手続する', '第1号になる場合は退職日の翌日から14日以内'",
        'pension timing'
    ),
    (
        "'離職票の発行・送付状況を確認する', '届いていない場合は早め'",
        "'離職票の発行・送付状況を確認する', '離職票が必要なのに届いていないとき（まず会社へ）'",
        'separation notice timing'
    ),
    (
        "'ハローワークで求職申込みと失業手当の手続をする', '離職票などがそろったら'",
        "'ハローワークで求職申込みと失業手当の手続をする', '離職票などがそろい次第（受給期間は原則、退職日の翌日から1年）'",
        'unemployment timing'
    ),
    (
        "'傷病手当金と、必要なら雇用保険の受給期間延長を確認する', '早め'",
        "'傷病手当金と、必要なら雇用保険の受給期間延長を確認する', '働けない状態が30日以上続いたら、受給期間延長を確認'",
        'extension timing'
    ),
]:
    replace_once(evaluate, old, new, label)

# Add official sources for the newly shown deadlines.
rtext = renderer.read_text(encoding='utf-8')
anchor = "    ('協会けんぽ｜傷病手当金FAQ（退職後の継続給付）', 'https://www.kyoukaikenpo.or.jp/g6/cat620/r307'),\n"
extra = (
    anchor
    + "    ('協会けんぽ｜傷病手当金支給申請書', 'https://www.kyoukaikenpo.or.jp/g2/cat230/r124/'),\n"
    + "    ('日本年金機構｜会社を退職したときの国民年金の手続き', 'https://www.nenkin.go.jp/service/kokunen/kanyu/20140710-03.html'),\n"
)
if rtext.count(anchor) != 1:
    raise SystemExit('source anchor missing or duplicated')
renderer.write_text(rtext.replace(anchor, extra, 1), encoding='utf-8')

print('output clarity patch applied')
