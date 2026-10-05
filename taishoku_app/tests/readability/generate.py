"""Offline synthetic reports; never submits Tally or approves/publishes a job."""
import json, subprocess, sys
from pathlib import Path
app=Path(__file__).resolve().parents[2]
runtime=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else app/'runtime'
out=Path(sys.argv[2]).resolve() if len(sys.argv)>2 else app/'readability-output'
base=dict(display_name='動作確認用（架空）',reference_id='SYNTHETIC',as_of_date='2026-10-04',employment_status='retired',exit_date_status='already_retired',exit_date='2026-09-30',exit_reasons=['career_work'],can_start_new_job='now',age_at_exit=41,wage_6m_total=1800000,employment_insurance_duration='10_to_20y',insured_months_24m=24,insured_months_12m=12,separation_notice_status='received',separation_reason_dispute='matches',job_intent='seeking')
health=dict(exit_reasons=['health'],health_reason_selected=True,can_start_new_job='difficult',medical_consultation='consulting',health_insurance_type='kyokai_kenpo',cause_work_related='no',unable_to_do_usual_work='yes',waiting_three_days_completed='yes',payable_absence_after_waiting='yes',absence_pay_status='none',insured_period_before_exit='1y_plus',worked_on_exit_date='not_worked_or_not_planned',same_condition_continues_after_exit='yes',became_able_after_exit='no',known_daily_amount=6500)
cases={
 '01-voluntary':base,
 '02-on-leave':dict(base,**health,employment_status='on_leave',exit_date_status='not_decided',exit_date=None),
 '03-health-exit':dict(base,**health,employment_status='exit_date_fixed_employed',exit_date_status='decided',exit_date='2026-10-31'),
 '04-dispute':dict(base,exit_reasons=['dismissal_encouragement'],separation_reason_dispute='difference'),
 '05-missing':dict(display_name='動作確認用（情報不足）',as_of_date='2026-10-04',employment_status='unknown',can_start_new_job='unknown',employment_insurance_duration='unknown',exit_reasons=['unknown']),
 '06-health-retired':dict(base,**health),
 '07-insurer-unknown':{**base,**health,'health_insurance_type':'unknown'},
}
for name,answer in cases.items():
 d=out/name;d.mkdir(parents=True,exist_ok=True)
 (d/'answer.json').write_text(json.dumps(answer,ensure_ascii=False,indent=2))
 subprocess.run(['python3',str(runtime/'report_template_v0.1/render_report.py'),str(d/'answer.json'),'--html',str(d/'report.html'),'--snapshot',str(d/'evaluation.json')],check=True,stdout=subprocess.DEVNULL)
 print(name)
