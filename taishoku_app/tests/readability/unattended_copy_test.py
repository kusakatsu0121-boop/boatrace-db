"""Offline cross-product tests. Does not approve, persist, publish or submit."""
import json, subprocess, sys, tempfile, re
from pathlib import Path
runtime=Path(sys.argv[1]).resolve()
fixtures=Path(sys.argv[2]).resolve()
baseline=Path(sys.argv[3]).resolve()
renderer=runtime/'report_template_v0.1/render_report.py'
count=0
with tempfile.TemporaryDirectory() as d:
 d=Path(d)
 def run(a):
  global count
  (d/'a.json').write_text(json.dumps(a))
  subprocess.run(['python3','-S',str(renderer),str(d/'a.json'),'--html',str(d/'r.html'),'--snapshot',str(d/'e.json')],check=True,stdout=subprocess.DEVNULL)
  count+=1
  s=(d/'r.html').read_text()
  assert '入力なし' not in s and '受付番号 未設定' not in s
  assert '追加で確認が必要な項目はありません' not in s
  assert 'この順番で進める' not in s and 'まず1つ目から' not in s
  assert '不足している情報の調べ方' not in s
  assert not re.search(r'{{\w+}}',s)
  ids=set(re.findall(r'id="([^"]+)"',s))
  assert all(x in ids for x in re.findall(r'href="#([^"]+)"',s))
  return s,json.loads((d/'e.json').read_text())
 for p in sorted(fixtures.glob('*/answer.json')):
  s,r=run(json.loads(p.read_text()))
  old=json.loads((baseline/p.parent.name/'evaluation.json').read_text())
  r.pop('evaluated_at',None);old.pop('evaluated_at',None)
  assert r==old,p.parent.name+' evaluation changed'
 base=json.loads((fixtures/'03-health-exit/answer.json').read_text())
 for employment,date_status in [('on_leave','not_decided'),('exit_date_fixed_employed','decided'),('retired','already_retired')]:
  for benefit in ['not_applied','applying','receiving','received_before','unknown',None]:
   for insurance in ['kyokai_kenpo','unknown']:
    a={**base,'employment_status':employment,'exit_date_status':date_status,'sickness_benefit_status':benefit,'health_insurance_type':insurance}
    if date_status=='not_decided':a['exit_date']=None
    s,r=run(a)
    if insurance=='unknown':assert '約6,500円' not in s
    if benefit=='applying':assert '受付状況' in s
    if benefit=='receiving':assert '次の申請期間' in s
    if employment=='retired':
     assert '退職日に出勤する予定がある場合' not in s
     assert '退職前に加入していた健康保険' in s
    if date_status=='not_decided':
     assert '人事に、退職日・最終出勤日を聞く' not in s
     assert '休み方と休業中の手続き' in s
 a=json.loads((fixtures/'04-dispute/answer.json').read_text());s,_=run(a)
 assert '日数と総額は未確定' in s and '試算の前提：' in s
 a={**base,'display_name':'<script>alert(1)</script>','reference_id':'<img src=x onerror=alert(1)>'};s,_=run(a)
 assert '<script>alert(1)</script>' not in s and '<img src=x onerror' not in s
print(f'{count} rendered reports PASS; 7 evaluation snapshots unchanged; no external services')
