"""Compare synthetic decisions and inspect rendered HTML using stdlib only."""
import json,sys
from pathlib import Path
from html.parser import HTMLParser
before,after=map(Path,sys.argv[1:3])
class Page(HTMLParser):
 def __init__(self):super().__init__();self.hrefs=[];self.ids=[];self.text=[]
 def handle_starttag(self,tag,attrs):
  a=dict(attrs)
  if 'id' in a:self.ids.append(a['id'])
  if tag=='a':self.hrefs.append(a.get('href',''))
 def handle_data(self,data):self.text.append(data)
for d in sorted(after.iterdir()):
 a=json.loads((d/'evaluation.json').read_text());b=json.loads((before/d.name/'evaluation.json').read_text())
 a.pop('evaluated_at');b.pop('evaluated_at');assert a==b,d.name
 s=(d/'report_preview.html').read_text();page=Page();page.feed(s)
 assert '{{' not in s
 assert 'age_at_exit' not in s
 assert len(page.ids)==len(set(page.ids))
 assert all(h[1:] in page.ids for h in page.hrefs if h.startswith('#'))
 assert all(h.startswith(('https://','#')) for h in page.hrefs)
 assert '今やること' in s and '公式の確認先を一覧で見る' in s
 assert not any(x in ''.join(page.text) for x in ['あなたは','入力内容から判断すると','この回答では'])
 assert s.count('data-taishoku-report-caution="v1"')==1
 if d.name=='01-voluntary':assert '写真2枚' in s and '離職票-1・2' in s
 if d.name=='03-health-exit':assert '退職日に出勤すると、退職翌日以降の傷病手当金は受け取れません' in s
 if d.name=='05-missing':assert '不足している情報の調べ方' in s and '今の状況で必要な手続きを相談したい' in s
 if d.name=='07-insurer-unknown':assert s.count('マイナポータルの健康保険の資格情報で「保険者名」')==1
 print(d.name, 'PASS: unchanged decisions; HTML links, notice, action guidance')
