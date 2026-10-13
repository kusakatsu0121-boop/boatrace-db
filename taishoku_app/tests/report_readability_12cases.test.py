from __future__ import annotations
import importlib.util, json, re, tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
RUNTIME=ROOT/"runtime"
RENDERER=RUNTIME/"report_template_v0.1"/"render_report.py"
spec=importlib.util.spec_from_file_location("taishoku_matrix_after_readability", RENDERER)
mod=importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)

base={
    "display_name":"QA","as_of_date":"2026-10-12","age_at_exit":40,
    "employment_insurance_duration":"5_to_10y","wage_regular_month_estimate":300000,
    "health_insurance_type":"kyokai_kenpo","cause_work_related":"no",
    "separation_notice_status":"received","separation_reason_dispute":"no_difference",
    "post_exit_health_insurance_done":False,"national_pension_done":False,
}
cases=[
("01_clean",{**base,"employment_status":"retired","exit_reasons":[],"can_start_new_job":"now","job_intent":"seeking_now"}),
("02_leave_not_applied",{**base,"employment_status":"on_leave","exit_reasons":["health"],"sickness_benefit_status":"not_applied","can_start_new_job":"difficult","job_intent":"undecided","waiting_combined_four_days":True,"payable_absence_after_waiting":"yes"}),
("03_leave_applying",{**base,"employment_status":"on_leave","exit_reasons":["health"],"sickness_benefit_status":"applying","can_start_new_job":"difficult","job_intent":"undecided","waiting_combined_four_days":True,"payable_absence_after_waiting":"yes"}),
("04_leave_receiving",{**base,"employment_status":"on_leave","exit_reasons":["health"],"sickness_benefit_status":"receiving","can_start_new_job":"difficult","job_intent":"undecided","waiting_combined_four_days":True,"payable_absence_after_waiting":"yes","known_total_amount":350000,"known_paid_days":70}),
("05_exit_not_applied",{**base,"employment_status":"exit_date_fixed_employed","exit_date_status":"decided","exit_reasons":["health"],"sickness_benefit_status":"not_applied","can_start_new_job":"difficult","job_intent":"undecided","waiting_combined_four_days":True,"payable_absence_after_waiting":"yes","insured_period_before_exit":"one_year_or_more","worked_on_exit_date":"not_worked_or_not_planned"}),
("06_exit_applying",{**base,"employment_status":"exit_date_fixed_employed","exit_date_status":"decided","exit_reasons":["health"],"sickness_benefit_status":"applying","can_start_new_job":"difficult","job_intent":"undecided","waiting_combined_four_days":True,"payable_absence_after_waiting":"yes","insured_period_before_exit":"one_year_or_more","worked_on_exit_date":"not_worked_or_not_planned"}),
("07_exit_receiving",{**base,"employment_status":"exit_date_fixed_employed","exit_date_status":"decided","exit_reasons":["health"],"sickness_benefit_status":"receiving","can_start_new_job":"difficult","job_intent":"undecided","waiting_combined_four_days":True,"payable_absence_after_waiting":"yes","insured_period_before_exit":"one_year_or_more","worked_on_exit_date":"not_worked_or_not_planned","known_total_amount":450000,"known_paid_days":90}),
("08_retired_not_applied",{**base,"employment_status":"retired","exit_reasons":["health"],"sickness_benefit_status":"not_applied","can_start_new_job":"difficult","job_intent":"undecided","waiting_combined_four_days":True,"payable_absence_after_waiting":"yes","insured_period_before_exit":"one_year_or_more","worked_on_exit_date":"not_worked_or_not_planned"}),
("09_retired_applying",{**base,"employment_status":"retired","exit_reasons":["health"],"sickness_benefit_status":"applying","can_start_new_job":"difficult","job_intent":"undecided","waiting_combined_four_days":True,"payable_absence_after_waiting":"yes","insured_period_before_exit":"one_year_or_more","worked_on_exit_date":"not_worked_or_not_planned"}),
("10_retired_receiving",{**base,"employment_status":"retired","exit_reasons":["health"],"sickness_benefit_status":"receiving","can_start_new_job":"difficult","job_intent":"undecided","waiting_combined_four_days":True,"payable_absence_after_waiting":"yes","insured_period_before_exit":"one_year_or_more","worked_on_exit_date":"not_worked_or_not_planned","known_total_amount":600000,"known_paid_days":120}),
("11_received_before",{**base,"employment_status":"retired","exit_reasons":["health"],"sickness_benefit_status":"received_before","can_start_new_job":"difficult","job_intent":"undecided","waiting_combined_four_days":True,"payable_absence_after_waiting":"yes"}),
("12_disputed",{**base,"employment_status":"retired","exit_reasons":["long_hours"],"can_start_new_job":"now","job_intent":"seeking_now","separation_reason_dispute":"difference","overtime_evidence":False,"reason_causation":False}),
]

def initial_text(html:str)->str:
    html=re.sub(r"<details[^>]*>\s*<summary>(.*?)</summary>.*?</details>",r"\1",html,flags=re.S|re.I)
    html=re.sub(r"<style.*?</style>|<script.*?</script>"," ",html,flags=re.S|re.I)
    html=re.sub(r"<[^>]+>"," ",html)
    return re.sub(r"\s+"," ",html).strip()

banned=("回答しています","この回答では","入力内容から判断すると","回答者","受付番号 未設定","入力なし")
state_labels={"not_applied":"現在：まだ申請していません","applying":"現在：申請中","receiving":"現在：受給中","received_before":"現在：過去に受給したことがあります"}

with tempfile.TemporaryDirectory() as td:
    out=Path(td)
    for cid,answer in cases:
        ap=out/f"{cid}.json"; hp=out/f"{cid}.html"; pp=out/f"{cid}.pdf"; sp=out/f"{cid}.snapshot.json"
        ap.write_text(json.dumps(answer,ensure_ascii=False),encoding="utf-8")
        mod.render(ap,hp,pp,sp)
        html=hp.read_text(encoding="utf-8")
        text=initial_text(html)
        print(cid,"visible",len(text))
        assert len(text) < 1900, (cid,len(text))
        for phrase in banned:
            assert phrase not in html, (cid,phrase)
        if answer.get("can_start_new_job") == "difficult":
            assert "退職したので、失業手当の手続きをしたい" not in text, cid
            assert "再就職手当" not in text, cid
        else:
            assert "最初に何と言えばいい？" in html, cid
        state=answer.get("sickness_benefit_status")
        if state in state_labels:
            assert state_labels[state] in html, (cid,state)
        if answer.get("employment_status")=="retired" and state:
            assert "退職前に本人として加入していた健康保険" in html, cid
        if cid=="12_disputed":
            assert "一般の給付日数で仮計算" in html
            assert "離職理由はまだ確定していません" in html
            assert "180日" in html

print("REPORT_READABILITY_12_CASES_OK")
