#!/usr/bin/env python3
"""Reduce first-view report clutter while preserving the underlying guidance."""
from pathlib import Path
import re
import sys

root=Path(sys.argv[1])
renderer=root/'report_template_v0.1'/'render_report.py'
template=root/'report_template_v0.1'/'report_template.html'

def replace_once(path, old, new, label):
    text=path.read_text(encoding='utf-8')
    count=text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected one match, got {count}')
    path.write_text(text.replace(old,new,1),encoding='utf-8')

# Show only the three most important actions on the first screen.
text=renderer.read_text(encoding='utf-8')
text,count=re.subn(r'def roadmap_rows\(tasks: list\[dict\], limit: int = 4\)', 'def roadmap_rows(tasks: list[dict], limit: int = 3)', text, count=1)
if count != 1:
    raise SystemExit('roadmap limit replacement failed')

# When the person cannot work yet, do not immediately show the Hello Work application script.
old="""    if answer.get('can_start_new_job') == 'difficult':
        return (
            '<h3>進む順番</h3><div class="flow">'
            '<span class="flow-step">まず体調を整える</span><span class="flow-arrow">→</span>'
            '<span class="flow-step">働ける状態になる</span><span class="flow-arrow">→</span>'
            '<span class="flow-step">住居所を管轄するハローワークへ行く</span></div><div class="notice compact"><strong>最初に何と言えばいい？</strong><p>窓口で「退職したので、失業手当の手続きをしたい」と伝えれば大丈夫です。離職票-1・2、マイナンバー確認書類、本人確認書類、本人名義の口座が分かるものなどを持参します。離職理由が実際と違う場合は、その場で「離職理由が実際と違います」と伝えてください。</p></div>'
        )"""
new="""    if answer.get('can_start_new_job') == 'difficult':
        return ''"""
if old not in text:
    raise SystemExit('difficult employment flow block not found')
text=text.replace(old,new,1)

# Keep concrete Hello Work wording for people who can work, but behind a closed detail.
old_normal_flow = """        '<details><summary>？「受給資格決定日」って何？</summary><div class="detail-body">ハローワークに離職票などを提出し、求職申込みをして、失業手当の受給資格を確認してもらった日のことです。</div></details>'
    )"""
new_normal_flow = """        '<details><summary>▶ 最初に何と言えばいい？</summary><div class="detail-body"><p>窓口で「退職したので、失業手当の手続きをしたい」と伝えれば大丈夫です。離職票-1・2、マイナンバー確認書類、本人確認書類、本人名義の口座が分かるものなどを持参します。離職理由が実際と違う場合は、その場で「離職理由が実際と違います」と伝えてください。</p></div></details>'
        '<details><summary>？「受給資格決定日」って何？</summary><div class="detail-body">ハローワークに離職票などを提出し、求職申込みをして、失業手当の受給資格を確認してもらった日のことです。</div></details>'
    )"""
if old_normal_flow not in text:
    raise SystemExit('normal employment flow detail anchor missing')
text=text.replace(old_normal_flow,new_normal_flow,1)

# Put generic terminology and reemployment information behind context-aware helpers.
anchor="def employment_reason_note(answer: dict, ei: dict) -> str:\n"
if anchor not in text:
    raise SystemExit('employment_reason_note anchor missing')
helpers=r'''def employment_name_note(answer: dict) -> str:
    return (
        '<details><summary>▶ 「退職給付金」という言い方について</summary>'
        '<div class="detail-body"><p>広告などで「退職給付金」と呼ばれることがありますが、'
        '「退職給付金」という名称の公的制度が別にあるわけではありません。'
        'このレポートでは、失業手当・再就職手当・傷病手当金など、実際の制度名で案内します。</p></div></details>'
    )


def reemployment_note(answer: dict) -> str:
    if answer.get('can_start_new_job') != 'now':
        return ''
    return (
        '<details><summary>▶ 早く再就職したときの手当</summary>'
        '<div class="detail-body"><p>早めに再就職した場合は、再就職手当の対象になることがあります。'
        '就職が決まったら、失業手当の手続きをしているハローワークへ'
        '「再就職手当の対象になるか確認したい」と伝えてください。</p></div></details>'
    )


'''
text=text.replace(anchor,helpers+anchor,1)

# Non-dispute separation-reason explanations are useful, but not first-view material.
old_reason="""    if code in {'EI_REASON_NEED_FACTS', 'EI_REASON_TOKUTEI_JUKYU_POSSIBLE', 'EI_REASON_TOKUTEI_RIYU_POSSIBLE'}:
        return '<div class="notice compact"><strong>離職理由は最終確定ではありません</strong><p>離職理由はここでは決めきれません。離職票-2の記載と実際の経緯が違う場合は、住居所を管轄するハローワークで「離職理由が実際と違います」と伝えてください。最終的な離職理由はハローワークが確認して決めます。</p></div>'"""
new_reason="""    if code in {'EI_REASON_NEED_FACTS', 'EI_REASON_TOKUTEI_JUKYU_POSSIBLE', 'EI_REASON_TOKUTEI_RIYU_POSSIBLE'}:
        return '<details><summary>▶ 離職理由が気になる場合</summary><div class="detail-body"><p>離職理由はここでは決めきれません。離職票-2の記載と実際の経緯が違う場合は、住居所を管轄するハローワークで「離職理由が実際と違います」と伝えてください。最終的な離職理由はハローワークが確認して決めます。</p></div></details>'"""
if old_reason not in text:
    raise SystemExit('employment reason compact block missing')
text=text.replace(old_reason,new_reason,1)

# Add the new placeholders.
old_values="""        'employment_benefit_summary': employment_summary(answer, result.get('employment_insurance', {})),
        'employment_flow': employment_flow(answer, result.get('employment_insurance', {})),
        'employment_reason_note': employment_reason_note(answer, result.get('employment_insurance', {})),
"""
new_values="""        'employment_benefit_summary': employment_summary(answer, result.get('employment_insurance', {})),
        'employment_name_note': employment_name_note(answer),
        'employment_flow': employment_flow(answer, result.get('employment_insurance', {})),
        'employment_reason_note': employment_reason_note(answer, result.get('employment_insurance', {})),
        'reemployment_note': reemployment_note(answer),
"""
if old_values not in text:
    raise SystemExit('renderer value block missing')
text=text.replace(old_values,new_values,1)
renderer.write_text(text,encoding='utf-8')

# First screen: tell the reader they only need the short action list.
replace_once(
    template,
    '<p class="lead">最初に全体の流れを見て、そのあと必要なところを詳しく確認できます。</p>',
    '<p class="lead">最初は「まずやること」だけ見れば大丈夫です。詳しい説明は、必要なところだけ開けます。</p>',
    'hero lead'
)
replace_once(template,'<h2 class="roadmap-heading">確認する順番</h2>','<h2 class="roadmap-heading">まずやること</h2>','roadmap heading')

# The duplicated full action list is now closed by default.
old_tasks='''  <section class="report-page">
    <div class="section-kicker">01</div>
    <h2>確認する順番を詳しく見る</h2>
    <p class="section-lead">確認先や目安も含めて、上の順番を詳しくまとめています。</p>
    <div class="task-detail-list">{{task_rows}}</div>
  </section>'''
new_tasks='''  <section class="report-page compact-section">
    <details class="section-details"><summary>▶ 手続き先・期限を詳しく見る</summary>
      <div class="detail-body"><div class="task-detail-list">{{task_rows}}</div></div>
    </details>
  </section>'''
replace_once(template,old_tasks,new_tasks,'task details collapse')

# Replace always-visible generic notices with optional details.
old_name='''    <div class="notice compact"><strong>「退職給付金」という名前について</strong><p>広告などで「退職給付金」と呼ばれることがありますが、「退職給付金」という名称の公的制度が別にあるわけではありません。このレポートでは、基本手当・再就職手当・傷病手当金など、実際の制度名ごとに案内します。給付の可否・金額・期間は、それぞれの制度の要件と行政機関等の審査で決まります。</p></div>
      {{employment_benefit_summary}}'''
new_name='''    {{employment_benefit_summary}}
    {{employment_name_note}}'''
replace_once(template,old_name,new_name,'employment terminology detail')

old_reemployment='''    <div class="notice compact"><strong>再就職手当</strong><p>早めに再就職した場合は、再就職手当の対象になることがあります。就職が決まったら、失業手当の手続きをしているハローワークへ「再就職手当の対象になるか確認したい」と伝えてください。</p></div>'''
replace_once(template,old_reemployment,'    {{reemployment_note}}','reemployment conditional')

# Insurance/pension options stay available, but do not occupy the first read-through.
old_insurance='''    <div class="compare-grid">
      <article><h3>家族の扶養</h3><p>家族の扶養に入れる場合は、自分で健康保険料を払わずに済むことがあります。家族の勤務先の人事・総務に「健康保険の扶養に入れる条件を確認したい」と伝えてください。収入見込みや、失業手当・傷病手当金を受ける場合の扱いも一緒に確認します。</p></article>
      <article><h3>任意継続</h3><p>退職前の健康保険を、退職後も続ける方法です。退職前の加入先が協会けんぽなら協会けんぽ、健康保険組合ならその組合へ「任意継続の期限と保険料を確認したい」と伝えてください。加入先が分からなければ、マイナポータルの健康保険の資格情報で確認できます。</p></article>
      <article><h3>国民健康保険</h3><p>市区町村で手続します。保険料は自治体や前年の所得などで変わるため、住んでいる市区町村で確認してください。</p></article>
    </div>
    <div class="notice compact"><strong>国民年金</strong><p>{{pension_note}}</p></div>
    <details><summary>▶ 支払いが難しい場合</summary><div class="detail-body">国民年金には、保険料の免除や納付猶予の制度があります。支払いが難しいときは、住んでいる市区町村の国民年金窓口か年金事務所で「退職して保険料の支払いが難しいので、免除や納付猶予を相談したい」と伝えてください。</div></details>'''
new_insurance='''    <p class="section-lead">期限は上の「まずやること」に出しています。ここでは選択肢だけ確認できます。</p>
    <details><summary>▶ 健康保険の3つの選択肢を見る</summary><div class="detail-body">
      <div class="compare-grid">
        <article><h3>家族の扶養</h3><p>家族の勤務先の人事・総務に「健康保険の扶養に入れる条件を確認したい」と伝えてください。収入見込みや、失業手当・傷病手当金を受ける場合の扱いも確認します。</p></article>
        <article><h3>任意継続</h3><p>退職前の加入先が協会けんぽなら協会けんぽ、健康保険組合ならその組合へ「任意継続の期限と保険料を確認したい」と伝えてください。</p></article>
        <article><h3>国民健康保険</h3><p>住んでいる市区町村で手続します。保険料は自治体や前年の所得などで変わります。</p></article>
      </div>
    </div></details>
    <details><summary>▶ 国民年金の手続きを見る</summary><div class="detail-body"><p>{{pension_note}}</p>
      <p>支払いが難しいときは、市区町村の国民年金窓口か年金事務所で「退職して保険料の支払いが難しいので、免除や納付猶予を相談したい」と伝えてください。</p>
    </div></details>'''
replace_once(template,old_insurance,new_insurance,'insurance pension collapse')

# Secondary paperwork becomes one optional block instead of another full section of prose.
old_other='''    <h2>そのほかに確認しておくこと</h2>
    <div class="compact-list">
      <p><strong>源泉徴収票</strong><br>会社から受け取ったら保管してください。年末調整や確定申告で必要になることがあります。</p>
      <p><strong>住民税</strong><br>退職時期や会社の処理によって、住民税の支払い方法が変わることがあります。会社の案内や、届いた納付書を確認してください。</p>
      <p><strong>企業型DC・iDeCo</strong><br>加入していた場合は、退職後に資産を移す手続が必要か確認してください。</p>
    </div>'''
new_other='''    <h2>そのほかの手続き</h2>
    <details><summary>▶ 源泉徴収票・住民税・企業型DCなど</summary><div class="detail-body compact-list">
      <p><strong>源泉徴収票</strong><br>会社から受け取ったら保管してください。年末調整や確定申告で必要になることがあります。</p>
      <p><strong>住民税</strong><br>退職時期や会社の処理によって支払い方法が変わることがあります。会社の案内や届いた納付書を確認してください。</p>
      <p><strong>企業型DC・iDeCo</strong><br>加入していた場合は、退職後に資産を移す手続きが必要か確認してください。</p>
    </div></details>'''
replace_once(template,old_other,new_other,'other procedures collapse')

print('report readability patch applied')
