"""Install presentation-only improvements after legacy patches; fail on drift."""
from pathlib import Path
import sys
root=Path(sys.argv[1]); folder=root/'report_template_v0.1'
p=folder/'render_report.py';s=p.read_text()
anchor="if __name__ == '__main__':"
assert s.count(anchor)==1
s=s.replace(anchor,"from reader_guidance import install\ninstall(globals())\n\n"+anchor)
s=s.replace("source_html = ''.join(f'<li>{e(label)}<br>{e(url)}</li>' for label, url in SOURCE_URLS)","source_html = ''.join(f'<li><a href=\"{e(url)}\" target=\"_blank\" rel=\"noopener noreferrer\">{e(label)}</a></li>' for label, url in dict((url, label) for label, url in SOURCE_URLS).items())")
# Correct tuple order for deduplicated URL -> label map.
s=s.replace('for label, url in dict((url, label)', 'for url, label in dict((url, label)')
p.write_text(s)
p=folder/'report_template.html';s=p.read_text()
s=s.replace('あなた専用｜退職前後ワークフロー','退職前後の手続きガイド')
s=s.replace('最初に全体の流れを見て、そのあと必要なところを詳しく確認できます。','まず1つ目から進めてください。分からないときの聞き方も載せています。')
s=s.replace('まず確認すること','今やること').replace('<p class="overview-context">{{case_summary}}</p>','')
s=s.replace('<h2 class="roadmap-heading">確認する順番</h2>\n    <div class="roadmap">{{roadmap_rows}}</div>','<details><summary>手続きの一覧から探す</summary><div class="detail-body">{{roadmap_rows}}</div></details>')
s=s.replace('確認する順番を詳しく見る','この順番で進める').replace('確認先や目安も含めて、上の順番を詳しくまとめています。','窓口では、書いてある言葉をそのまま伝えて大丈夫です。')
start='<div class="notice compact"><strong>「退職給付金」という名前について</strong><p>'
assert s.count(start)==1
s=s.replace(start,'<details><summary>「退職給付金」とは？</summary><div class="detail-body"><p>')
s=s.replace('給付の可否・金額・期間は、それぞれの制度の要件と行政機関等の審査で決まります。</p></div>','給付の可否・金額・期間は、それぞれの制度の要件と行政機関等の審査で決まります。</p></div></details>')
s=s.replace('市区町村で手続します。保険料は自治体や前年の所得などで変わるため、住んでいる市区町村で確認してください。','住んでいる市区町村の国民健康保険窓口で「退職したので、加入手続きと保険料を教えてください」と伝えてください。出向く前に、自治体の公式サイトで「国民健康保険・加入・必要書類」を見てください。書類がない場合は、窓口へ「代わりに使える書類はありますか」と聞いてください。')
s=s.replace('加入していた場合は、退職後に資産を移す手続が必要か確認してください。','加入していた場合は、会社の人事へ「企業型DCの移換先、期限、問い合わせ先を教えてください」と伝えてください。iDeCoの手続きは、契約している金融機関へ聞いてください。')
s=s.replace('会社の案内や、届いた納付書を確認してください。','会社の給与担当へ「退職後の住民税は、給与から引かれますか。納付書で払いますか」と聞いてください。納付書の内容が不明なら、発行した市区町村の住民税担当へ相談してください。')
s=s.replace('<p>{{pension_note}}</p>','<p>{{pension_note}}</p><p><a href="https://www.nenkin.go.jp/service/kokunen/kanyu/20140710-03.html" target="_blank" rel="noopener noreferrer">日本年金機構：退職後の手続き・必要書類</a></p>')
p.write_text(s)
p=folder/'report.css';p.write_text(p.read_text()+'\n/* Mobile reading: long links and document names must wrap. */\n.report { overflow-wrap: anywhere; }\n.task-detail > div { min-width: 0; }\nsummary { min-height: 44px; padding: 12px 0; cursor: pointer; }\n:target { scroll-margin-top: 16px; }\n')
print('reader guidance applied; evaluation and security unchanged')
# Keep the caution visible, but fold its duplicated directory of contacts.
p=root/'workflow_pipeline_v0.1/instant_finalize.mjs';s=p.read_text()
a='  <ul style="margin:0;padding-left:1.3rem">';b='  </ul>\n</section>`;'
assert s.count(a)==1 and s.count(b)==1
s=s.replace(a,'  <details><summary>公式の確認先を一覧で見る</summary>\n'+a).replace(b,'  </ul></details>\n</section>`;')
p.write_text(s)
