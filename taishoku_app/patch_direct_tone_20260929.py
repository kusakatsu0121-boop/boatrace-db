#!/usr/bin/env python3
"""Rewrite shared user-facing copy so it speaks directly to the reader."""
from pathlib import Path
import sys

root = Path(sys.argv[1])

def replace_once(path, old, new, label):
    text = path.read_text(encoding='utf-8')
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected one match, got {count}')
    path.write_text(text.replace(old, new, 1), encoding='utf-8')

def replace_exact(path, old, new, expected, label):
    text = path.read_text(encoding='utf-8')
    count = text.count(old)
    if count != expected:
        raise SystemExit(f'{label}: expected {expected} matches, got {count}')
    path.write_text(text.replace(old, new), encoding='utf-8')

partial = root / 'workflow_webhook_v0.1' / 'partial_guidance.mjs'
repls = [
('賃金額を入力していないため、今回は金額だけ出せません。金額も見たいときは、給与明細などで確認してからもう一度お試しください。',
 '金額まで知りたいときは、給与明細などで退職前6か月の賃金か、普段の1か月分の給与を確認してください。今のままでも、金額以外の手続きや確認先は見られます。','partial wage'),
('離職理由をまだ確定できません。離職票が届いている場合は「離職理由」を確認し、実際の退職経緯と違うところがあればメモしてハローワークで確認してください。',
 '離職票が届いたら「離職理由」と実際の退職経緯を見比べてください。違いがあれば、経緯をメモしてハローワークで伝えてください。','partial separation'),
('傷病手当金は「最初の連続3日」と「4日目以降」を分けて確認します。休んだ日と、その日に給与や手当が出たかをカレンダーや給与明細で確認してください。',
 '傷病手当金は「最初の連続3日」と「4日目以降」を分けて見ます。休んだ日と、その日に給与や手当が出たかを、カレンダーや給与明細で確認してください。','partial waiting'),
('体調不良が仕事・通勤によるものかは、この回答だけでは判断できません。健康保険と労災で扱いが変わるため、このツールでは決めず、関係する窓口で確認してください。',
 '体調不良が仕事や通勤に関係していそうな場合は、健康保険と労災で扱いが変わります。ここでは決めきれないので、健康保険や労災の窓口で確認してください。','partial work related'),
('休んだ日に会社から給与や手当が出たか分かりません。給与明細を見るか、会社に確認してください。',
 '休んだ日に給与や手当が出たか確認してください。分からなければ、給与明細を見るか会社へ確認してください。','partial pay'),
('回答だけでは確定できない項目があります。今回は給付の可否や金額を断定しません。',
 'まだ確認が必要な点があります。下の確認先を見ながら、必要なところだけ確認してください。','partial fallback'),
('今回は、確認できていない点だけを表示します。',
 'ここでは、次に確認すればいいことだけをまとめます。','partial intro'),
('同じ内容をそのまま送り直しても結果は変わりません。確認できる情報が増えたら、最初からもう一度お試しください。',
 '分かったことが増えたら、必要に応じてもう一度進めると、金額や案内を更新できます。','partial final'),
]
for old,new,label in repls:
    replace_once(partial,old,new,label)

web = root / 'workflow_webhook_v0.1' / 'webhook_server.mjs'
repls = [
("hints.push('賃金を確認しない場合、金額目安は算出しません。金額が必要になったときは、給与明細などで確認できます。');",
 "hints.push('金額まで知りたいときは、給与明細などで退職前6か月の賃金か普段の給与額を確認してください。');",'web wage hint'),
("hints.push('体調不良と仕事・通勤との関係が未確認です。加入する健康保険や相談窓口で確認してください。');",
 "hints.push('仕事や通勤との関係がありそうなら、健康保険や労災の窓口で確認してください。');",'web work hint'),
("hints.push('連続した待期3日と4日目以降の休業・給与を分けて確認してください。');",
 "hints.push('休んだ日を、最初の連続3日と4日目以降に分け、給与や手当が出た日も確認してください。');",'web waiting hint'),
("hints.push('離職理由の区分について、離職票や会社とのやり取りを確認してください。');",
 "hints.push('離職票の離職理由と、実際の退職経緯を見比べてください。違いがあればハローワークで伝えてください。');",'web separation hint'),
("const title = review ? '回答を受け付けました' : '処理を完了できませんでした';",
 "const title = review ? 'ここだけ確認してください' : 'うまく処理できませんでした';",'web title'),
("? '今回は、回答だけでは確定できない項目があるため、正式レポートはまだ出していません。下の「次に確認すること」だけご確認ください。'",
 "? '正式レポートを出す前に、まだ決めきれない点があります。下の「次に確認すること」だけ見れば大丈夫です。'",'web review explanation'),
(": '処理に失敗しました。回答内容が間違っているとは限りません。少し時間を置いて、最初からもう一度お試しください。';",
 ": 'うまく処理できませんでした。入力し直す前に、少し時間を置いてもう一度お試しください。';",'web failure explanation'),
('<h2 style="font-size:1.1rem">今回、確認できていないこと</h2>',
 '<h2 style="font-size:1.1rem">次に確認すること</h2>','web details heading'),
('同じ内容をそのまま送り直しても結果は変わりません。確認できる情報が増えたら、最初からもう一度お試しください。',
 '分かったことが増えたら、必要に応じてもう一度進めてください。','web final'),
('<title>回答を整理しています</title>','<title>必要な内容を整理しています</title>','processing title'),
('<body><main><div class="card"><div class="dot"></div><h1>回答を受け付けました</h1><p>いま、回答内容を整理しています。結果が出るまでこのままお待ちください。確認が必要な場合は、分からない点と次に確認することを表示します。</p></div></main></body>',
 '<body><main><div class="card"><div class="dot"></div><h1>送信できました</h1><p>いま、必要な手続きと確認先を整理しています。このままお待ちください。分からないところがあれば、次に確認することをそのまま表示します。</p></div></main></body>','processing body'),
]
for old,new,label in repls:
    replace_once(web,old,new,label)

finalizer = root / 'workflow_pipeline_v0.1' / 'instant_finalize.mjs'
replace_once(finalizer,
 'このレポートは、入力した内容をもとに整理した目安です。受給可否、最終的な支給額、離職理由、申請期限などを確定するものではありません。実際の手続きでは、手元の書類と各窓口の案内を確認してください。',
 'このレポートは、今の状況で次に何をすればいいかを整理した目安です。受給可否、最終的な支給額、離職理由、申請期限などを確定するものではありません。実際の手続きでは、手元の書類と各窓口の案内を確認してください。',
 'report caution')

evaluate = root / 'workflow_rule_package_v0.1' / 'evaluate.mjs'
replace_once(evaluate,
 '仕事中・通勤中の事故・けがが関係する回答のため、労災の確認を優先します。仕事のストレスやハラスメントによる体調不良は、この回答だけで労災扱いとはしません。',
 '仕事中・通勤中の事故やけがが関係している場合は、まず労災を確認してください。仕事のストレスやハラスメントによる体調不良は、ここだけでは労災扱いと決められません。',
 'evaluate accident')
replace_once(evaluate,
 "reasons.push('本人が回答した期限が7日以内または超過');",
 "reasons.push('期限が7日以内または超過');",
 'evaluate deadline reason')
replace_once(evaluate,
 "reasons.push('この先仕事を探す意向が未確認');",
 "reasons.push('今後仕事を探す予定がまだ決まっていない');",
 'evaluate job intent reason')


renderer = root / 'report_template_v0.1' / 'render_report.py'
renderer_repls = [
("'unknown': '現在の状況：回答なし',",
 "'unknown': '現在の状況：未選択',",
 'renderer unknown status'),
("'本人が回答した期限が7日以内または超過': '回答した期限が近い、またはすでに過ぎています。期限と必要な対応を確認してください',",
 "'期限が7日以内または超過': '期限が近い、またはすでに過ぎています。期限と必要な対応を確認してください',",
 'renderer deadline reason'),
("'この先仕事を探す意向が未確認': '今後、仕事を探す予定があるかを確認してください',",
 "'今後仕事を探す予定がまだ決まっていない': '今後、仕事を探す予定があるか確認してください',",
 'renderer job intent reason'),
("'今回のポイントは、体調面を優先しながら、傷病手当金と失業手当の順番を整理することです。'",
 "'まずは体調面を優先して、傷病手当金と失業手当の順番を確認してください。'",
 'renderer overview sick order'),
("'今回のポイントは、退職前後の手続とあわせて、傷病手当金の条件を確認しておくことです。'",
 "'まずは退職前後の手続とあわせて、傷病手当金の条件を確認してください。'",
 'renderer overview sick conditions'),
("'今回のポイントは、失業手当の手続とあわせて、離職理由を整理しておくことです。'",
 "'まずは失業手当の手続とあわせて、離職理由を整理してください。'",
 'renderer overview separation'),
("'今回のポイントは、退職後の手続を順番に整理することです。'",
 "'まずは退職後の手続きを、必要な順番で進めてください。'",
 'renderer overview retired'),
("'今回のポイントは、退職前に確認しておきたいことを先に整理することです。'",
 "'まずは退職前に確認しておきたいことから進めてください。'",
 'renderer overview default'),
("'今の回答だけで離職理由を決めることはできません。'",
 "'離職理由はここでは決めきれません。'",
 'renderer separation notice'),
("'SHO_CURRENTLY_UNLIKELY': '今の回答では、「普段の仕事ができない状態」とまでは判断できません。',",
 "'SHO_CURRENTLY_UNLIKELY': '今の時点では、「普段の仕事ができない状態」とまでは言い切れません。',",
 'renderer sickness unlikely'),
("'仕事中・通勤中の事故やけがが関係している場合は、労災保険の対象になる可能性があります。なお、仕事のストレスやハラスメントによる体調不良は、この回答だけで労災と決まるわけではありません。'",
 "'仕事中・通勤中の事故やけがが関係している場合は、労災保険の対象になる可能性があります。仕事のストレスやハラスメントによる体調不良は、ここだけで労災と決まるわけではありません。'",
 'renderer workers comp notice'),
("'「4日以上休んだ」という回答だけでは、最初の3日間（待期）と、4日目以降に休んだ日を分けられないことがあります。実際に休んだ日付を確認してください。'",
 "'「4日以上休んだ」だけでは、最初の3日間（待期）と、4日目以降に休んだ日を分けられないことがあります。実際に休んだ日付を確認してください。'",
 'renderer waiting explanation'),
("'今の回答では、追加で確認が必要な項目はありません。'",
 "'追加で確認が必要な項目はありません。'",
 'renderer no extra confirmation'),
("or '回答なし'",
 "or '未選択'",
 'renderer no reasons'),
('STATUS_LABELS.get(answer.get("employment_status"), "現在の状況：回答なし")',
 'STATUS_LABELS.get(answer.get("employment_status"), "現在の状況：未選択")',
 'renderer status fallback'),
]
for old,new,label in renderer_repls:
    replace_once(renderer,old,new,label)

replace_exact(
    renderer,
    '今の回答では順番を決めるための情報が足りません。下の「追加で確認したいこと」を見てください。',
    'まだ順番を決めるには情報が足りません。下の「追加で確認したいこと」を見てください。',
    2,
    'renderer insufficient sequence info'
)
replace_exact(
    renderer,
    'answer.get("display_name", "回答者")',
    'answer.get("display_name", "あなた")',
    2,
    'renderer display-name fallback'
)

template = root / 'report_template_v0.1' / 'report_template.html'
replace_once(
    template,
    '<p class="overview-label">今回の整理ポイント</p>',
    '<p class="overview-label">まず確認すること</p>',
    'template overview label'
)

print('direct reader-facing tone applied')
