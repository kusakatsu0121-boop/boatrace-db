from __future__ import annotations
import json, shutil, subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
RUNTIME=ROOT/"runtime"
OUT=ROOT/"qa_output"/"round2_visual"
R=RUNTIME/"report_template_v0.1"/"render_report.py"
BASE={
"display_name":"QAテスト","as_of_date":"2026-10-14","age_at_exit":40,
"employment_insurance_duration":"5_to_10y","wage_regular_month_estimate":300000,
"separation_notice_status":"received","separation_reason_dispute":"no_difference",
"cause_work_related":"no","national_pension_done":True
}
HEALTH={
"exit_reasons":["health"],"can_start_new_job":"difficult","job_intent":"undecided",
"health_insurance_type":"kyokai_kenpo","medical_consultation":"consulted",
"waiting_combined_four_days":True,"payable_absence_after_waiting":"yes",
"absence_pay_status":"none","insured_period_before_exit":"one_year_or_more",
"retirement_day_attendance":"no"
}
CASES=[
("clean_done", {**BASE,"employment_status":"retired","exit_reasons":["career_work"],"can_start_new_job":"now","job_intent":"seeking_now","post_exit_health_insurance_done":True}),
("exit_not_applied",{**BASE,**HEALTH,"employment_status":"exit_date_fixed_employed","exit_date_status":"decided","sickness_benefit_status":"not_applied","post_exit_health_insurance_done":False}),
("retired_receiving",{**BASE,**HEALTH,"employment_status":"retired","sickness_benefit_status":"receiving","post_exit_health_insurance_done":True,"known_total_amount":600000,"known_paid_days":120}),
]
if OUT.exists(): shutil.rmtree(OUT)
OUT.mkdir(parents=True)
rows=[]
for name,a in CASES:
 d=OUT/name; d.mkdir()
 ap=d/"a.json"; hp=d/"report.html"; pp=d/"report.pdf"; sp=d/"snapshot.json"
 ap.write_text(json.dumps(a,ensure_ascii=False,indent=2),encoding="utf-8")
 cp=subprocess.run(["python3",str(R),str(ap),"--html",str(hp),"--pdf",str(pp),"--snapshot",str(sp)],capture_output=True,text=True)
 if cp.returncode: raise SystemExit(cp.stderr)
 h=hp.read_text(encoding="utf-8")
 snap=json.loads(sp.read_text(encoding="utf-8"))
 ids=[x.get("task_id") for x in (snap.get("actions") or {}).get("timeline",[])]
 rows.append({"case":name,"task_ids":ids,"sickness_before_unemployment":("<h2>傷病手当金</h2>" not in h) or h.index("<h2>傷病手当金</h2>")<h.index("<h2>失業手当（基本手当）</h2>"),"warning_has_mynaportal":"マイナポータル" in (h[h.find('notice critical'):h.find('notice critical')+1200] if 'notice critical' in h else ''),"has_old_h1":"あなた専用｜退職前後ワークフロー" in h})
(OUT/"summary.json").write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps(rows,ensure_ascii=False,indent=2))
