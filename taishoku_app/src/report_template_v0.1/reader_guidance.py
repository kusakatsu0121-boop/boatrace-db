"""Presentation only: never mutates answers, evaluation, approval or access control."""
from html import escape

HW='https://www.hellowork.mhlw.go.jp/insurance/insurance_procedure.html'
SHO='https://www.kyoukaikenpo.or.jp/application_form/benefit/001/index.html'
PENSION='https://www.nenkin.go.jp/service/kokunen/kanyu/20140710-03.html'

def link(url,label):
    return f'<a href="{escape(url,quote=True)}" target="_blank" rel="noopener noreferrer">{escape(label)}</a>'

# Short title, words to say, documents/checks, fallback. Keys are existing task IDs.
GUIDES={
 'ACT-PRE-01':('書類を出す前に、期限と内容を聞く','書類を送ってきた担当者へ「提出期限と、署名すると何が決まるのか教えてください」と伝えてください。','届いた書類とメールを手元に置きます。','担当が不明なら、書類にある部署名・問い合わせ先へ聞いてください。'),
 'ACT-SHO-MEDICAL':('医師に、体調と仕事の状況を伝える','受診先で「体調が悪く、仕事を続けるのが難しいです」と伝えてください。','症状が始まった日、仕事内容、休んだ日をメモして持参します。','受診先が決まっていなければ、まずかかりつけ医に相談してください。'),
 'ACT-PRE-02':('退職の経緯が分かる資料をまとめる','会社からの通知、メール、勤怠、給与明細を手元にまとめてください。','いつ、誰から、何を言われたかも日付順にメモします。','資料がそろわなくても、ハローワークで事情を伝えて相談してください。'),
 'ACT-SHO-02':('退職前に、傷病手当金の継続条件を聞く','加入先の健康保険へ「退職後も傷病手当金を受けたいです。退職日と最終出勤日はどう影響しますか」と伝えてください。','退職予定日、最終出勤日、休んだ日、加入期間の分かるものを用意します。','加入先が不明なら、人事へ「傷病手当金の問い合わせ先を教えてください」と聞いてください。'),
 'ACT-PRE-DATE':('人事に、退職日・最終出勤日を聞く','会社の人事・総務へ「退職日、最終出勤日、有給休暇の残りと扱いを確認したい」と伝えてください。','退職に関するメールや書類を手元に置きます。','担当が不明なら、上司に人事・総務の窓口を聞いてください。'),
 'ACT-PRE-04':('退職後の書類がいつ届くか聞く','会社の人事・給与担当へ「離職票などの発送予定日と送付先を教えてください」と伝えてください。','送付先の住所を確認し、担当者名と予定日をメモします。','発送時期が未定なら、次にいつ連絡すればよいか聞いてください。'),
 'ACT-POST-01':('退職後の健康保険を選ぶ','下の「退職後の健康保険・年金」で3つの選択肢と相談先を見てください。','退職日と、次の会社の保険に入る予定日をメモします。','迷ったら、市区町村の国民健康保険窓口で「退職後の健康保険を相談したい」と伝えてください。'),
 'ACT-POST-02':('市区町村で、年金の切替を相談する','国民年金窓口で「退職したので、年金の切替が必要か確認したい」と伝えてください。','基礎年金番号かマイナンバーが分かるもの、本人確認書類、退職日の分かる書類を用意します。','不足する書類があれば、窓口で代わりに使える書類を聞いてください。'),
 'ACT-POST-VC':('任意継続を考えるなら、期限を聞く','退職前の健康保険へ「任意継続を検討しています。申込期限と保険料を教えてください」と伝えてください。','退職日、加入先の名前、資格情報を用意します。','加入先が不明なら、会社の人事へ問い合わせ先を聞いてください。'),
 'ACT-DOC-01':('届かない離職票の発送予定を聞く','会社の人事・給与担当へ「離職票が届いていません。発送予定を教えてください」と伝えてください。','退職日と、会社へ連絡した日をメモします。','会社に連絡しても届かない場合は、住所を担当するハローワークで「離職票が届かず困っています」と伝えてください。'),
 'ACT-EI-03':('離職理由の違いをハローワークに伝える','住所を担当するハローワークで「離職理由が実際と違います」と伝えてください。','離職票-2と、勤怠・退職通知・メールなど手元の資料を持参します。','何が違うか整理できなければ、実際の経緯を日付順に話してください。最終判断はハローワークが行います。'),
 'ACT-EI-01':('ハローワークで失業手当の手続きをする','住所を担当するハローワークで「退職したので、失業手当の手続きをしたい」と伝えてください。','持ち物は下の「失業手当」の一覧を見てください。','離職票が届かないときは、人事に発送予定を聞き、届かないままならハローワークへ相談してください。'),
 'ACT-EI-02':('働けない間の手続きを相談する','健康保険へ傷病手当金を相談してください。退職後に働けない状態が30日以上続く場合は、ハローワークへ「受給期間延長を相談したい」と伝えてください。','退職日、働けなくなった日、通院や休業の状況をメモします。','外出が難しければ、ハローワークへ郵送や代理人で相談できるか聞いてください。'),
}

def install(ns):
    ns['MISSING_LABELS'].update(age_at_exit='退職日時点の年齢。生年月日と退職日から確かめてください。', waiting_three_days_completed='病気やけがで連続して3日間休んだか。勤怠やカレンダーで日付を確認してください。', payable_absence_after_waiting='連続3日間休んだ後、4日目以降にも休んだ日があるか。勤怠を確認してください。', known_daily_amount_or_standard_monthly_remuneration='傷病手当金の支給通知にある日額。初めての申請なら、人事へ計算に使う標準報酬月額を聞いてください。')
    e=ns['e']; old_flow=ns['employment_flow']; old_sickness=ns['sickness_section']; old_review=ns['review_content']
    def overview(answer,result):
        tasks=result.get('actions',{}).get('timeline',[])
        if answer.get('employment_status')=='unknown':
            return 'まず、在職中か退職済みかと、退職日を整理してください。分からなければ会社の人事へ「現在の在籍状況と退職日を教えてください」と聞いてください。'
        if tasks and tasks[0]['task_id']=='ACT-POST-01':
            return '住んでいる市区町村の国民健康保険窓口で「退職後の健康保険を相談したい」と伝えてください。家族の扶養や任意継続も考えている場合は、下の3つの相談先で条件と保険料を比べてください。'
        if tasks:
            return GUIDES.get(tasks[0]['task_id'],('',tasks[0]['action']))[1]
        return '手元の退職書類と給与明細を集めてください。下にある窓口へ、分からない項目をそのまま伝えて相談できます。'
    def roadmap(tasks,limit=4):
        return ''.join(f'<p><a href="#task-{e(t["task_id"])}">{i}. {e(GUIDES.get(t["task_id"],(t["action"],))[0])}</a></p>' for i,t in enumerate(tasks,1))
    def task_rows(tasks):
        rows=[]
        for i,t in enumerate(tasks,1):
            guide=GUIDES.get(t['task_id'])
            title,say,materials,fallback=guide or (t['action'],t['action'],'手元にある関係書類を用意してください。','記載の窓口へ、必要な書類と次の手順を聞いてください。')
            source=link(HW,'公式：ハローワークの手続き') if t['task_id'].startswith(('ACT-EI','ACT-DOC')) else link(PENSION,'公式：退職後の年金') if t['task_id']=='ACT-POST-02' else link(SHO,'公式：協会けんぽの申請書') if t['task_id']=='ACT-SHO-02' else ''
            rows.append(f'<article class="task-detail" id="task-{e(t["task_id"])}"><div class="task-number">{i}</div><div><h3>{e(title)}</h3><p>{e(say)}</p><p><strong>用意するもの・見るもの</strong><br>{e(materials)}</p><details><summary>分からない・そろわないとき</summary><div class="detail-body">{e(fallback)}</div></details><p class="meta">時期：{e(t.get("timing"))}</p>{source}</div></article>')
        return ''.join(rows) or '<p>会社の人事に在籍状況と退職日を聞き、給与明細を手元に集めてください。</p>'
    def flow(answer,ei):
        if answer.get('can_start_new_job')=='difficult':
            return '<details><summary>働けるようになってからの流れ</summary><div class="detail-body"><p>仕事を探せる状態になったら、住所を担当するハローワークで失業手当の手続きを相談してください。</p>'+link(HW,'公式：手続きと持ち物')+'</div></details>'
        if answer.get('can_start_new_job') != 'now' or answer.get('job_intent') in {'not_seeking_now','next_job_decided','undecided','unknown'}:
            return '<p>すぐに働けるか、仕事を探す予定があるかを整理してください。判断できなければ、住所を担当するハローワークで「今の状況で必要な手続きを相談したい」と伝えてください。</p>'+link(HW,'公式：受給の条件と窓口')
        original=old_flow(answer,ei)
        materials='<details><summary>ハローワークへ持っていくもの</summary><div class="detail-body"><ul><li>離職票-1・2</li><li>マイナンバー確認書類と本人確認書類</li><li>本人名義の通帳またはキャッシュカード</li><li>写真2枚（縦3cm×横2.4cm）。以後の支給申請も含めて毎回マイナンバーカードを提示する場合は省略できます。</li></ul><p>離職票が届かない場合は、会社の人事へ発送予定を聞いてください。届かないままならハローワークへ相談できます。</p>'+link(HW,'公式：必要書類と窓口を探す')+'</div></details>'
        return '<p>住所を担当するハローワークで「退職したので、失業手当の手続きをしたい」と伝えてください。</p>'+materials+'<details><summary>受給までの流れ・用語を見る</summary><div class="detail-body">'+original+'<p>待期は、手続き後に失業している日を通算して7日間待つ期間です。失業認定は、仕事探しの状況などをハローワークが確認することです。</p></div></details>'
    def sickness(answer,result):
        rendered=old_sickness(answer,result)
        if not rendered:return rendered
        if result['sickness_allowance'].get('status_code')=='SHO_NEED_INSURANCE_CONFIRMATION':
            rendered=rendered.replace(e(ns['sickness_status_text']('SHO_NEED_INSURANCE_CONFIRMATION')), '加入先が分かってから、傷病手当金の対象になるか相談してください。')
        rendered=rendered.replace('<h2>傷病手当金</h2>','<h2>傷病手当金</h2><p>加入先へ「病気で休んでいます。傷病手当金を申請したいので、申請書と必要な書類を教えてください」と伝えてください。</p>')
        rendered=rendered.replace('<details><summary>▶ 申請方法・申請時期</summary>', '<p>'+link(SHO,'公式：協会けんぽの申請書・記入案内')+'</p><details><summary>▶ 申請方法・申請時期</summary>')
        return rendered
    def review(result):
        rendered=old_review(result)
        if '<ul>' not in rendered:return rendered
        return rendered+'<details><summary>不足している情報の調べ方</summary><div class="detail-body"><p>賃金：退職前6か月分の給与明細を集めてください。ない場合は、会社の給与担当へ再発行できるか聞いてください。</p><p>健康保険：マイナポータルの資格情報で保険者名を見てください。使えなければ、人事へ加入先を聞いてください。</p><p>休業日・給与：勤怠と給与明細を並べ、休んだ日と支払われた給与を確認してください。不明な箇所は人事へ聞いてください。</p><p>体調と仕事：医師へ仕事内容と難しい作業を伝え、働ける状態か相談してください。</p><p>離職理由・雇用保険の期間：離職票など手元の書類を持ち、ハローワークへ「この項目が分かりません」と伝えてください。</p></div></details>'
    ns.update(overview_summary=overview,roadmap_rows=roadmap,task_rows=task_rows,employment_flow=flow,sickness_section=sickness,review_content=review,TEMPLATE_VERSION='0.2.6')
