#!/usr/bin/env python3
"""Make Hello Work and pension guidance concrete: where to go, what to bring, what to say."""
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
    '離職票が届いたら「離職理由」と実際の退職経緯を見比べてください。違いがあれば、経緯をメモしてハローワークで伝えてください。',
    '離職票-2の「離職理由」と実際の退職経緯を見比べてください。違いがあれば、失業手当の手続きで住居所を管轄するハローワークへ行き、「離職理由が実際と違います」と伝えてください。勤怠、会社からの通知、メールなど経緯が分かるものがあれば一緒に持っていきます。',
    'partial separation'
)

web = root / 'workflow_webhook_v0.1' / 'webhook_server.mjs'
replace_once(
    web,
    "if (reasons.some(v => String(v).includes('離職理由'))) hints.push('離職票の離職理由と、実際の退職経緯を見比べてください。違いがあればハローワークで伝えてください。');",
    "if (reasons.some(v => String(v).includes('離職理由'))) hints.push('離職票-2の離職理由が実際と違うなら、住居所を管轄するハローワークで失業手当の手続きをするときに「離職理由が実際と違います」と伝えてください。経緯が分かる資料があれば持参します。');",
    'web separation'
)

evaluate = root / 'workflow_rule_package_v0.1' / 'evaluate.mjs'
for old,new,label in [
    (
        "'市区町村・年金事務所'",
        "'住んでいる市区町村の国民年金窓口／年金事務所'",
        'pension destination'
    ),
    (
        "'会社、必要に応じハローワーク'",
        "'まず会社の人事・給与担当／届かない場合は住居所を管轄するハローワーク'",
        'separation notice destination'
    ),
    (
        "'離職票の退職理由が実際と違う場合は、経緯を整理してハローワークに伝える'",
        "'離職票-2の離職理由が実際と違う場合は、住居所を管轄するハローワークで「離職理由が実際と違います」と伝える'",
        'separation dispute task'
    ),
    (
        "'ハローワーク'",
        "'住居所を管轄するハローワーク'",
        'separation dispute destination'
    ),
]:
    replace_once(evaluate,old,new,label)

template = root / 'report_template_v0.1' / 'report_template.html'
for old,new,label in [
    (
        '早めに再就職した場合は、再就職手当の対象になることがあります。対象になるかどうかや金額は、就職が決まった時点でハローワークへ確認してください。',
        '早めに再就職した場合は、再就職手当の対象になることがあります。就職が決まったら、失業手当の手続きをしているハローワークへ「再就職手当の対象になるか確認したい」と伝えてください。',
        'reemployment allowance'
    ),
    (
        '国民年金には、保険料の免除や納付猶予の制度があります。支払いが難しい場合は、市区町村または年金事務所へ相談してください。',
        '国民年金には、保険料の免除や納付猶予の制度があります。支払いが難しいときは、住んでいる市区町村の国民年金窓口か年金事務所で「退職して保険料の支払いが難しいので、免除や納付猶予を相談したい」と伝えてください。',
        'pension exemption'
    ),
]:
    replace_once(template,old,new,label)

renderer = root / 'report_template_v0.1' / 'render_report.py'
for old,new,label in [
    (
        "('ハローワークインターネットサービス｜雇用保険Q&A', 'https://www.hellowork.mhlw.go.jp/help/question05.html'),",
        "('厚生労働省｜基本手当Q&A（手続場所・必要書類・離職理由）', 'https://www.mhlw.go.jp/stf/seisakunitsuite/bunya/0000139508.html'),\n    ('ハローワークインターネットサービス｜雇用保険Q&A', 'https://www.hellowork.mhlw.go.jp/help/question05.html'),",
        'add hello work source'
    ),
    (
        '<p>65歳以上では、一般的な基本手当ではなく、高年齢求職者給付金などの対象になる場合があります。金額や手続はハローワークで確認してください。</p></div>',
        '<p>65歳以上では、一般的な基本手当ではなく、高年齢求職者給付金などの対象になる場合があります。住居所を管轄するハローワークで「65歳以上で退職したので、受けられる雇用保険の給付を確認したい」と伝えてください。</p></div>',
        'age 65'
    ),
    (
        '退職後に働けない状態が30日以上続く場合は、雇用保険の受給期間延長もハローワークへ確認してください。',
        '退職後に働けない状態が30日以上続く場合は、住居所を管轄するハローワークへ「病気で今すぐ働けないので、受給期間延長の手続きを確認したい」と伝えてください。',
        'extension'
    ),
    (
        '離職票に書かれた退職理由が実際の経緯と違う、または判断できない場合は、失業手当の手続時に実際の経緯をハローワークへ伝えてください。',
        '離職票-2の退職理由が実際の経緯と違う、または判断できない場合は、住居所を管轄するハローワークで失業手当の手続きをするときに「離職理由が実際と違います」と伝えてください。勤怠、退職通知、メールなど経緯が分かる資料があれば持参します。',
        'separation warning'
    ),
    (
        '離職理由はここでは決めきれません。離職票の記載や実際の経緯をもとに、最終的にはハローワークが判断します。',
        '離職理由はここでは決めきれません。離職票-2の記載と実際の経緯が違う場合は、住居所を管轄するハローワークで「離職理由が実際と違います」と伝えてください。最終的な離職理由はハローワークが確認して決めます。',
        'separation final'
    ),
    (
        '次の仕事が決まっている場合は、失業手当や再就職手当の扱いが通常と異なることがあります。必要な手続があるか、ハローワークへ確認してください。',
        '次の仕事が決まっている場合は、失業手当や再就職手当の扱いが通常と異なることがあります。失業手当の手続きをしているハローワークへ「就職が決まりました。必要な手続きと再就職手当の対象になるか確認したい」と伝えてください。',
        'job decided'
    ),
    (
        '退職後すぐに次の会社の厚生年金へ入らない場合は、国民年金への切替が必要か確認してください。配偶者の扶養に入る場合は、国民年金の保険料を自分で納めない「第3号被保険者」になれることがあります。健康保険の扶養とは別の手続なので、あわせて確認してください。',
        '退職後すぐに次の会社の厚生年金へ入らない場合は、住んでいる市区町村の国民年金窓口で「会社を退職したので、国民年金への切替が必要か確認したい」と伝えてください。配偶者の扶養に入る場合は、配偶者の勤務先へ「年金の第3号被保険者の手続きも必要ですか」と確認してください。',
        'pension normal'
    ),
    (
        '年齢や次の勤務先によって必要な手続が変わります。分からない場合は、市区町村または年金事務所へ確認してください。',
        '年齢や次の勤務先によって必要な手続きが変わります。分からなければ、住んでいる市区町村の国民年金窓口か年金事務所で「退職後に必要な年金の手続きを確認したい」と伝えてください。個人の年金相談は、原則どこの年金事務所でも受け付けています。',
        'pension fallback'
    ),
]:
    replace_once(renderer,old,new,label)

# Add one concrete, visible instruction near the unemployment flow.
replace_once(
    renderer,
    '<span class="flow-step">ハローワークで失業手当の手続きをする</span></div>',
    '<span class="flow-step">住居所を管轄するハローワークへ行く</span></div><div class="notice compact"><strong>最初に何と言えばいい？</strong><p>窓口で「退職したので、失業手当の手続きをしたい」と伝えれば大丈夫です。離職票-1・2、マイナンバー確認書類、本人確認書類、本人名義の口座が分かるものなどを持参します。離職理由が実際と違う場合は、その場で「離職理由が実際と違います」と伝えてください。</p></div>',
    'visible hello work instruction'
)

finalizer = root / 'workflow_pipeline_v0.1' / 'instant_finalize.mjs'
replace_once(
    finalizer,
    '<li><strong>失業給付・離職理由：</strong>住所地を管轄するハローワーク。<a href="https://www.mhlw.go.jp/stf/seisakunitsuite/bunya/0000135026.html" target="_blank" rel="noopener noreferrer">厚生労働省「基本手当について」</a></li>',
    '<li><strong>失業給付・離職理由：</strong>住居所を管轄するハローワークへ。「退職したので失業手当の手続きをしたい」と伝えてください。離職票-2の理由が実際と違えば「離職理由が実際と違います」と伝え、経緯が分かる資料があれば持参します。<a href="https://www.mhlw.go.jp/stf/seisakunitsuite/bunya/0000139508.html" target="_blank" rel="noopener noreferrer">手続場所・必要書類・離職理由の公式Q&A</a></li>',
    'finalizer hello work'
)
replace_once(
    finalizer,
    '<li><strong>退職後の年金：</strong>日本年金機構・年金事務所。<a href="https://www.nenkin.go.jp/service/mokutekibetsu/kojin/kanyu/index.html" target="_blank" rel="noopener noreferrer">年金加入の公式案内</a></li>',
    '<li><strong>退職後の年金：</strong>すぐ次の会社の厚生年金に入らない場合は、住んでいる市区町村の国民年金窓口で「退職したので国民年金への切替が必要か確認したい」と伝えてください。分からない場合は年金事務所でも個人相談できます。<a href="https://www.nenkin.go.jp/service/mokutekibetsu/kojin/kanyu/index.html" target="_blank" rel="noopener noreferrer">退職後の年金加入の公式案内</a>／<a href="https://www.nenkin.go.jp/section/soudan/index.html" target="_blank" rel="noopener noreferrer">年金の相談窓口を探す</a></li>',
    'finalizer pension'
)

print('concrete Hello Work and pension guidance applied')
