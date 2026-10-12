"""Reader-facing safeguards for unreviewed guidance; no eligibility calculations."""
import re
from html import escape as e
from reader_guidance import GUIDES, link, HW, SHO, PENSION


def retired(a):
    return a.get('employment_status') == 'retired' or a.get('exit_date_status') == 'already_retired'


def undecided(a):
    return not retired(a) and a.get('exit_date_status') not in {'decided', 'already_retired'} and not a.get('exit_date')


def insurer(a):
    return '退職前に加入していた健康保険' if retired(a) else '勤務先で加入している健康保険'


def contact(a):
    return insurer(a)+'の保険者名を、資格情報のお知らせ・資格確認書などで確かめてください。マイナポータルを見る場合も、その勤務先で加入していた期間の情報か確認します。分からなければ、その会社の人事へ「傷病手当金の問い合わせ先を教えてください」と聞いてください。協会けんぽなら協会けんぽ、健康保険組合ならその組合へ相談します。'


def say(a):
    status=a.get('sickness_benefit_status')
    words={
      'receiving':'傷病手当金を受給中です。次の申請期間と必要書類を教えてください',
      'applying':'傷病手当金を申請中です。受付状況と、不足している書類があるか教えてください',
      'received_before':'以前、傷病手当金を受けました。今回の休業について必要な手続きを教えてください',
      'not_applied':'傷病手当金をまだ申請していません。対象条件と申請書類を教えてください',
    }.get(status,'傷病手当金について相談したいです。申請・支給の状況と、次に必要な手続きを教えてください')
    return insurer(a)+'へ「'+words+'」と伝えてください。'


def guide(t,a):
    item=GUIDES.get(t['task_id'],(t['action'],t['action'],'関係する書類を手元に用意してください。','記載の窓口へ必要書類を聞いてください。'))
    if t['task_id']=='ACT-PRE-DATE' and undecided(a):
        if a.get('employment_status')=='unknown':
            return ('在籍状況と必要な手続きを整理する','会社の人事へ「現在の在籍状況と、必要な手続きを教えてください」と伝えてください。','会社からの連絡や手元の書類を用意します。','退職日が未定なら、未定と伝えてください。')
        if a.get('employment_status')=='working' and 'health' not in a.get('exit_reasons',[]):
            return ('就業規則と必要書類を確認する','会社の就業規則で退職の申出方法を見てください。分からなければ人事へ「退職を検討する場合の手続きと必要書類を教えてください」と聞いてください。','就業規則と雇用契約書を手元に用意します。','退職日が未定なら、未定と伝えてください。')
        return ('休み方と休業中の手続きを相談する','会社の人事へ「休職制度、休める期間、休業中の給与と必要書類を教えてください」と伝えてください。','就業規則、休業の案内、給与明細を手元に用意します。','資料がなくても相談できます。退職日が未定なら、未定と伝えてください。')
    if t['task_id']=='ACT-EI-02':
        return (item[0],say(a)+'退職後に働けない状態が30日以上続く場合は、ハローワークへ「受給期間延長を相談したい」と伝えてください。',item[2],item[3])
    return item


def install(ns):
    ns['MISSING_LABELS'].update(health_insurance_type='傷病手当金を相談する保険者名。退職済みなら退職前の加入先を、資格情報の書類で調べてください。不明なら当時の会社の人事へ聞いてください。', wage_6m_total_or_regular_month='退職前6か月の賃金。給与明細を集め、なければ会社の給与担当へ再発行を聞いてください。', absence_pay_status='休業日の給与・手当。勤怠と給与明細を照らし合わせ、不明な支払いは給与担当へ聞いてください。', unable_to_do_usual_work='普段の仕事ができる状態か。医師へ仕事内容と難しい作業を伝えて相談してください。')
    old={k:ns[k] for k in ('overview_summary','employment_summary','sickness_section','critical_warning','review_content','employment_flow')}
    def overview(a,r):
        ts=r.get('actions',{}).get('timeline',[])
        if ts and ts[0]['task_id'] in {'ACT-PRE-DATE','ACT-EI-02'}:return guide(ts[0],a)[1]
        return old['overview_summary'](a,r)
    def roadmap(tasks,answer):
        return ''.join(f'<p><a href="#task-{e(t["task_id"])}">{i}. {e(guide(t,answer)[0])}</a></p>' for i,t in enumerate(tasks,1))
    def rows(tasks,answer):
        out=[]
        for i,t in enumerate(tasks,1):
            title,words,materials,fallback=guide(t,answer)
            timing=t.get('timing') or '窓口へ手続きの期限を聞いてください。'
            if t['task_id']=='ACT-PRE-DATE' and undecided(answer):timing='必要な手続きが分からないとき。相談のために退職日を決める必要はありません。'
            elif t['task_id']=='ACT-PRE-DATE':timing='退職日が決まっていても、最終出勤日・有給の扱いが不明なら人事へ確認'
            if timing in {'早め','退職後すみやかに'}:timing+='。窓口へ「私の手続きの期限はいつですか」と聞いてください。'
            if t['task_id']=='ACT-POST-VC':timing='退職日の翌日から20日以内。休日の扱い・書類の到着期限は退職前の保険者へ確認してください。'
            if t['task_id']=='ACT-POST-02':timing='国民年金の第1号への切替が必要な場合は、退職日の翌日から14日以内。過ぎていても市区町村の国民年金窓口へ相談してください。'
            if t.get('due_date'):timing+=' 期限：'+str(t['due_date'])
            source=link(HW,'公式：ハローワークの手続き') if t['task_id'].startswith(('ACT-EI','ACT-DOC')) else link('https://www.nenkin.go.jp/service/kokunen/kanyu/20140710-04.html','公式：国民年金の手続きと期限') if t['task_id']=='ACT-POST-02' else link(SHO,'公式：傷病手当金の申請書') if t['task_id']=='ACT-SHO-02' else link('https://www.kyoukaikenpo.or.jp/benefit/voluntary_continuation/index.html','公式：任意継続の期限') if t['task_id']=='ACT-POST-VC' else ''
            out.append(f'<article class="task-detail" id="task-{e(t["task_id"])}"><div class="task-number">{i}</div><div><h3>{e(title)}</h3><p>{e(words)}</p><p><strong>用意するもの・見るもの</strong><br>{e(materials)}</p><details><summary>分からない・そろわないとき</summary><div class="detail-body">{e(fallback)}</div></details><p class="meta">時期：{e(timing)}</p>{source}</div></article>')
        return ''.join(out)
    def summary(a,ei):
        rendered=old['employment_summary'](a,ei).replace('まず傷病手当金を続けて受けられるか確認してください。','傷病手当金の申請や、受給中の場合の継続について、下の問い合わせ先へ相談してください。')
        if 'total-card' not in rendered:return rendered
        if a.get('can_start_new_job') != 'now' or a.get('job_intent') != 'seeking':
            return '<p>働ける時期や求職の予定によって案内が変わるため、受給見込み額は表示していません。ハローワークへ、今の状況で必要な手続きを相談してください。</p>'
        scenarios=ei.get('scenarios') or []
        primary=next((s for s in scenarios if s.get('id')=='general'),scenarios[0])
        premise=primary.get('label') or '表示した給付日数を使った試算'
        note='試算の前提：'+premise+'。受給資格・離職理由・日数はハローワークが確認します。全日数分を受け取ると仮定した計算で、受給を保証する金額ではありません。'
        if a.get('separation_reason_dispute')=='difference':note='離職理由に争いがあるため、日数と総額は未確定です。'+note
        rendered=rendered.replace('<span class="label">失業手当の受給総額（参考）</span>', '<span class="label">条件を満たした場合の試算総額</span><p class="note">'+e(note)+'</p>')
        return rendered.replace('受け取れる日数（目安）','試算に使った日数')
    def sickness(a,r):
        s=old['sickness_section'](a,r)
        if not s:return s
        s=s.replace('加入先へ「病気で休んでいます。傷病手当金を申請したいので、申請書と必要な書類を教えてください」と伝えてください。',e(say(a)))
        s=re.sub(r'(<strong>どこに聞けばいい？</strong><p>).*?(</p>)',lambda m:m[1]+e(contact(a))+m[2],s,count=1)
        s=s.replace('加入先が分からなければ、マイナポータルの健康保険の資格情報で確認できます。',e(contact(a)))
        s=s.replace('傷病手当金を受けられる可能性があります。','傷病手当金の申請条件を、保険者へ相談してください。')
        s=s.replace('必要な条件を確認しています。','必要な条件を保険者へ相談してください。')
        sho=r.get('sickness_allowance',{}); amount=sho.get('amount') or {}
        eligible=sho.get('status_code') in {'SHO_CURRENT_POSSIBILITY','SHO_DIFFERENCE_POSSIBILITY'}
        post=sho.get('post_exit') or {}
        if post and post.get('status_code')!='SHO_POST_EXIT_POSSIBILITY':eligible=False
        metrics=[]
        if eligible and amount.get('daily_yen') is not None:
            label='支給通知の日額として記入した金額' if amount.get('method')=='notice_amount' else '条件を満たす場合の日額試算'
            metrics.append(f'<div class="metric"><span>{label}</span><strong>{e(ns["yen"](amount["daily_yen"]))}</strong></div>')
        for key,label in [('known_total_amount','過去の支給総額として記入した金額'),('known_paid_days','過去の支給日数として記入した日数')]:
            if a.get(key) is not None:metrics.append(f'<div class="metric"><span>{label}</span><strong>{e(str(a[key]))}{"円" if key=="known_total_amount" else "日"}</strong></div>')
        note='今後の支給額や支給継続を保証する表示ではありません。申請期間の給与やほかの給付との調整も、保険者へ相談してください。' if eligible else '支給条件の確認が必要なため、今後受け取れる金額は表示していません。上の案内に沿って保険者へ相談してください。'
        s,n=re.subn(r'<div class="metric-grid">.*?</div>\s*</div>',lambda m:'<div class="metric-grid">'+''.join(metrics)+'</div><p>'+e(note)+'</p>',s,count=1,flags=re.S)
        assert n==1
        return s
    def warning(a,r):
        s=old['critical_warning'](a,r)
        if retired(a):
            s=s.replace('退職日に出勤する予定がある場合','退職日の勤務状況を確かめてください').replace('退職日に出勤するかどうかが重要です。','退職日に出勤したかどうかが重要です。').replace('退職日や最終出勤日を決める前に、傷病手当金の申請先へ「退職日に出勤すると、退職後の継続給付にどう影響するか」を確認してください。','勤怠記録を手元に用意し、退職前の保険者へ「退職日の勤務状況を踏まえて、退職後の申請について相談したい」と伝えてください。')
            s=s.replace('申請先が分からなければ、マイナポータルの健康保険の資格情報で加入先を確認できます。',e(contact(a)))
        if any(t.get('task_id')=='ACT-POST-VC' for t in r.get('actions',{}).get('timeline',[])):
            s+='<div class="notice warning"><strong>任意継続を検討する場合は、先に期限を確認</strong><p>申出は退職日の翌日から20日以内です。ほかの相談が終わるのを待たず、退職前の保険者へ期限と必要書類を聞いてください。期限を過ぎたか分からない場合も、その保険者へ相談してください。</p>'+link('https://www.kyoukaikenpo.or.jp/benefit/voluntary_continuation/index.html','公式：任意継続の期限')+'</div>'
        return s
    def review(r):
        # Original list already uses the evaluator's actual missing fields/reasons.
        s=old['review_content'](r).split('<details><summary>不足している情報の調べ方')[0]
        return s.replace('追加で確認が必要な項目はありません。','申請時には、離職票・給与明細などの内容を窓口で確認してもらってください。傷病手当金は、申請期間の休業状況と給与について保険者へ相談してください。')
    def flow(a,ei):
        s=old['employment_flow'](a,ei)
        if not retired(a):s=s.replace('退職したので、失業手当の手続きをしたい','退職に備えて、失業手当の手続きと必要書類を知りたい')
        return s
    ns.update(overview_summary=overview,roadmap_rows=roadmap,task_rows=rows,employment_summary=summary,sickness_section=sickness,critical_warning=warning,review_content=review,employment_flow=flow,TEMPLATE_VERSION='0.2.7')
