from __future__ import annotations
import base64, importlib.util, json, re, tarfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
RUNTIME=ROOT/"runtime"
RENDERER=RUNTIME/"report_template_v0.1"/"render_report.py"
OUT=ROOT/"qa_report_matrix"
OUT.mkdir(parents=True, exist_ok=True)

spec=importlib.util.spec_from_file_location("taishoku_render_report", RENDERER)
mod=importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)

base={
    "display_name":"QA",
    "as_of_date":"2026-10-12",
    "age_at_exit":40,
    "employment_insurance_duration":"5_to_10y",
    "wage_regular_month_estimate":300000,
    "health_insurance_type":"kyokai_kenpo",
    "cause_work_related":"no",
    "separation_notice_status":"received",
    "separation_reason_dispute":"no_difference",
    "post_exit_health_insurance_done":False,
    "national_pension_done":False,
}

cases=[
    ("01_retired_unemployment_clean","退職済み・働ける・通常ケース",{
        **base,"employment_status":"retired","exit_reasons":[],
        "can_start_new_job":"now","job_intent":"seeking_now",
    }),
    ("02_on_leave_not_applied","休職中・傷病手当金未申請",{
        **base,"employment_status":"on_leave","exit_reasons":["health"],
        "sickness_benefit_status":"not_applied","can_start_new_job":"difficult","job_intent":"undecided",
        "waiting_combined_four_days":True,"payable_absence_after_waiting":"yes",
    }),
    ("03_on_leave_applying","休職中・傷病手当金申請中",{
        **base,"employment_status":"on_leave","exit_reasons":["health"],
        "sickness_benefit_status":"applying","can_start_new_job":"difficult","job_intent":"undecided",
        "waiting_combined_four_days":True,"payable_absence_after_waiting":"yes",
    }),
    ("04_on_leave_receiving","休職中・傷病手当金受給中",{
        **base,"employment_status":"on_leave","exit_reasons":["health"],
        "sickness_benefit_status":"receiving","can_start_new_job":"difficult","job_intent":"undecided",
        "waiting_combined_four_days":True,"payable_absence_after_waiting":"yes",
        "known_total_amount":350000,"known_paid_days":70,
    }),
    ("05_exit_fixed_not_applied","退職予定・傷病手当金未申請",{
        **base,"employment_status":"exit_date_fixed_employed","exit_date_status":"decided",
        "exit_reasons":["health"],"sickness_benefit_status":"not_applied",
        "can_start_new_job":"difficult","job_intent":"undecided",
        "waiting_combined_four_days":True,"payable_absence_after_waiting":"yes",
        "insured_period_before_exit":"one_year_or_more","retirement_day_attendance":"no",
    }),
    ("06_exit_fixed_applying","退職予定・傷病手当金申請中",{
        **base,"employment_status":"exit_date_fixed_employed","exit_date_status":"decided",
        "exit_reasons":["health"],"sickness_benefit_status":"applying",
        "can_start_new_job":"difficult","job_intent":"undecided",
        "waiting_combined_four_days":True,"payable_absence_after_waiting":"yes",
        "insured_period_before_exit":"one_year_or_more","retirement_day_attendance":"no",
    }),
    ("07_exit_fixed_receiving","退職予定・傷病手当金受給中",{
        **base,"employment_status":"exit_date_fixed_employed","exit_date_status":"decided",
        "exit_reasons":["health"],"sickness_benefit_status":"receiving",
        "can_start_new_job":"difficult","job_intent":"undecided",
        "waiting_combined_four_days":True,"payable_absence_after_waiting":"yes",
        "insured_period_before_exit":"one_year_or_more","retirement_day_attendance":"no",
        "known_total_amount":450000,"known_paid_days":90,
    }),
    ("08_retired_not_applied","退職済み・傷病手当金未申請",{
        **base,"employment_status":"retired","exit_reasons":["health"],
        "sickness_benefit_status":"not_applied","can_start_new_job":"difficult","job_intent":"undecided",
        "waiting_combined_four_days":True,"payable_absence_after_waiting":"yes",
        "insured_period_before_exit":"one_year_or_more","retirement_day_attendance":"no",
    }),
    ("09_retired_applying","退職済み・傷病手当金申請中",{
        **base,"employment_status":"retired","exit_reasons":["health"],
        "sickness_benefit_status":"applying","can_start_new_job":"difficult","job_intent":"undecided",
        "waiting_combined_four_days":True,"payable_absence_after_waiting":"yes",
        "insured_period_before_exit":"one_year_or_more","retirement_day_attendance":"no",
    }),
    ("10_retired_receiving","退職済み・傷病手当金受給中",{
        **base,"employment_status":"retired","exit_reasons":["health"],
        "sickness_benefit_status":"receiving","can_start_new_job":"difficult","job_intent":"undecided",
        "waiting_combined_four_days":True,"payable_absence_after_waiting":"yes",
        "insured_period_before_exit":"one_year_or_more","retirement_day_attendance":"no",
        "known_total_amount":600000,"known_paid_days":120,
    }),
    ("11_retired_received_before","退職済み・過去に傷病手当金を受給",{
        **base,"employment_status":"retired","exit_reasons":["health"],
        "sickness_benefit_status":"received_before","can_start_new_job":"difficult","job_intent":"undecided",
        "waiting_combined_four_days":True,"payable_absence_after_waiting":"yes",
    }),
    ("12_disputed_reason_info_poor","退職済み・離職理由に争い・情報不足",{
        **base,"employment_status":"retired","exit_reasons":["long_hours"],
        "can_start_new_job":"now","job_intent":"seeking_now",
        "separation_reason_dispute":"difference",
        "overtime_evidence":False,"reason_causation":False,
    }),
]

banned=["回答しています","この回答では","入力内容から判断すると","回答者","受付番号 未設定","入力なし"]
vague=["健康保険へ確認","ハローワークへ確認","年金事務所へ確認","早め","すみやかに"]
summaries=[]
for cid,label,answer in cases:
    ap=OUT/f"{cid}.json"; hp=OUT/f"{cid}.html"; pp=OUT/f"{cid}.pdf"; sp=OUT/f"{cid}.snapshot.json"
    ap.write_text(json.dumps(answer,ensure_ascii=False,indent=2),encoding="utf-8")
    mod.render(ap,hp,pp,sp)
    html=hp.read_text(encoding="utf-8")
    text=re.sub(r"<script.*?</script>|<style.*?</style>"," ",html,flags=re.S|re.I)
    text=re.sub(r"<[^>]+>"," ",text)
    text=re.sub(r"\s+"," ",text).strip()
    snap=json.loads(sp.read_text(encoding="utf-8"))
    summaries.append({
        "id":cid,"label":label,
        "chars":len(text),"headings":len(re.findall(r"<h[1-4]\b",html,re.I)),
        "details":html.count("<details>"),"notices":html.count('class="notice'),
        "human_review":snap.get("human_review",{}),
        "sho_status":snap.get("sickness_allowance",{}).get("status_code"),
        "ei_reason":snap.get("employment_insurance",{}).get("reason",{}).get("status_code"),
        "banned_hits":[x for x in banned if x in text],
        "vague_hits":[x for x in vague if x in text],
        "preview":text[:1800],
    })

(OUT/"summary.json").write_text(json.dumps(summaries,ensure_ascii=False,indent=2),encoding="utf-8")
print("===QA_SUMMARY===")
print(json.dumps(summaries,ensure_ascii=False,indent=2))
with tarfile.open(OUT/"qa-html.tar.gz","w:gz") as tf:
    for p in sorted(OUT.glob("*.html")):
        tf.add(p,arcname=p.name)
data=(OUT/"qa-html.tar.gz").read_bytes()
b64=base64.b64encode(data).decode("ascii")
print("===QA_TAR_B64_LEN===",len(b64))
print("===QA_TAR_B64===")
print(b64)
print("===QA_TAR_B64_END===")
