from __future__ import annotations
import importlib.util, json, re, tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
RUNTIME=ROOT/"runtime"
RENDERER=RUNTIME/"report_template_v0.1"/"render_report.py"
TEMPLATE=RUNTIME/"report_template_v0.1"/"report_template.html"

spec=importlib.util.spec_from_file_location("taishoku_render_report_readability", RENDERER)
mod=importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)

# First view should show only three action steps.
tasks=[{"action":f"action-{i}","destination":"x","timing":"y"} for i in range(1,5)]
roadmap=mod.roadmap_rows(tasks)
assert "action-1" in roadmap and "action-2" in roadmap and "action-3" in roadmap
assert "action-4" not in roadmap
assert "続きの1項目" in roadmap

# A person who cannot work yet should not be given the immediate unemployment-application script.
assert mod.employment_flow({"can_start_new_job":"difficult"}, {}) == ""
assert mod.reemployment_note({"can_start_new_job":"difficult"}) == ""
assert "再就職手当" in mod.reemployment_note({"can_start_new_job":"now"})

template=TEMPLATE.read_text(encoding="utf-8")
assert "▶ 手続き先・期限を詳しく見る" in template
assert "▶ 健康保険の3つの選択肢を見る" in template
assert "▶ 国民年金の手続きを見る" in template
assert "▶ 源泉徴収票・住民税・企業型DCなど" in template
assert "最初は「まずやること」だけ見れば大丈夫です" in template

def visible_text(html: str) -> str:
    # Closed details expose only the summary in the initial browser view.
    html=re.sub(
        r"<details[^>]*>\s*<summary>(.*?)</summary>.*?</details>",
        r"\1",
        html,
        flags=re.S|re.I,
    )
    html=re.sub(r"<style.*?</style>|<script.*?</script>"," ",html,flags=re.S|re.I)
    html=re.sub(r"<[^>]+>"," ",html)
    return re.sub(r"\s+"," ",html).strip()

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
    ("clean", {**base,"employment_status":"retired","exit_reasons":[],"can_start_new_job":"now","job_intent":"seeking_now"}, 2300),
    ("leave_not_applied", {**base,"employment_status":"on_leave","exit_reasons":["health"],"sickness_benefit_status":"not_applied","can_start_new_job":"difficult","job_intent":"undecided","waiting_combined_four_days":True,"payable_absence_after_waiting":"yes"}, 2300),
    ("retired_receiving", {**base,"employment_status":"retired","exit_reasons":["health"],"sickness_benefit_status":"receiving","can_start_new_job":"difficult","job_intent":"undecided","waiting_combined_four_days":True,"payable_absence_after_waiting":"yes","insured_period_before_exit":"one_year_or_more","retirement_day_attendance":"no","known_total_amount":600000,"known_paid_days":120}, 2800),
]

with tempfile.TemporaryDirectory() as td:
    root=Path(td)
    for name,answer,limit in cases:
        ap=root/f"{name}.json"; hp=root/f"{name}.html"; pp=root/f"{name}.pdf"; sp=root/f"{name}.snapshot.json"
        ap.write_text(json.dumps(answer,ensure_ascii=False),encoding="utf-8")
        mod.render(ap,hp,pp,sp)
        text=visible_text(hp.read_text(encoding="utf-8"))
        print(name,"initial_visible_chars",len(text))
        assert len(text) < limit, (name,len(text),limit)
        if answer.get("can_start_new_job") == "difficult":
            assert "退職したので、失業手当の手続きをしたい" not in text
            assert "再就職手当" not in text

print("REPORT_READABILITY_OK")
