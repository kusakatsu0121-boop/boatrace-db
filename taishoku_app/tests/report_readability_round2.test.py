from __future__ import annotations

import importlib.util
import json
import re
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
RUNTIME=ROOT/"runtime"
RENDERER=RUNTIME/"report_template_v0.1"/"render_report.py"

spec=importlib.util.spec_from_file_location("taishoku_round2", RENDERER)
mod=importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)

base={
    "display_name":"QA",
    "as_of_date":"2026-10-14",
    "age_at_exit":40,
    "employment_status":"retired",
    "employment_insurance_duration":"5_to_10y",
    "wage_regular_month_estimate":300000,
    "exit_reasons":["career_work"],
    "can_start_new_job":"now",
    "job_intent":"seeking_now",
    "separation_notice_status":"received",
    "separation_reason_dispute":"no_difference",
    "national_pension_done":True,
    "cause_work_related":"no",
}

def render(answer):
    with tempfile.TemporaryDirectory() as td:
        d=Path(td)
        ap=d/"a.json"; hp=d/"r.html"; pp=d/"r.pdf"; sp=d/"s.json"
        ap.write_text(json.dumps(answer,ensure_ascii=False),encoding="utf-8")
        mod.render(ap,hp,pp,sp)
        return hp.read_text(encoding="utf-8"), json.loads(sp.read_text(encoding="utf-8"))

# Completed post-exit health insurance means no voluntary-continuation task.
html,snap=render({**base,"post_exit_health_insurance_done":True})
ids=[x.get("task_id") for x in (snap.get("actions") or {}).get("timeline",[])]
assert "ACT-POST-VC" not in ids
assert "任意継続を選ぶ場合は申出期限を確認する" not in html

# If insurance is not done, the deadline remains available.
html2,snap2=render({**base,"post_exit_health_insurance_done":False})
ids2=[x.get("task_id") for x in (snap2.get("actions") or {}).get("timeline",[])]
assert "ACT-POST-VC" in ids2

# When sickness allowance is relevant, that section comes before unemployment.
health={
    **base,
    "post_exit_health_insurance_done":True,
    "exit_reasons":["health"],
    "can_start_new_job":"difficult",
    "job_intent":"undecided",
    "sickness_benefit_status":"receiving",
    "health_insurance_type":"kyokai_kenpo",
    "medical_consultation":"consulted",
    "waiting_combined_four_days":True,
    "payable_absence_after_waiting":"yes",
    "absence_pay_status":"none",
    "insured_period_before_exit":"one_year_or_more",
    "worked_on_exit_date":"not_worked_or_not_planned",
}
health_html,_=render(health)
assert health_html.index("<h2>傷病手当金</h2>") < health_html.index("<h2>失業手当（基本手当）</h2>")

# The hero wording is shorter and more direct.
assert "退職前後｜あなたが今やること" in health_html
assert "最初は「まずやること」だけ確認してください" in health_html
assert "最初は「まずやること」だけ見れば大丈夫です" not in health_html

# Sickness is section 02 after the reordered layout.
assert '<div class="section-kicker">02</div>\n      <h2>傷病手当金</h2>' in health_html

# If the person already answered that they will not work on the exit date,
# the retirement-day warning is unnecessary and must stay hidden.
assert "退職日に出勤する前に確認" not in health_html
assert "退職日の出勤予定を確認してください" not in health_html

# If exit-day attendance is planned, keep a short critical warning.
blocked={**health,"employment_status":"exit_date_fixed_employed","exit_date_status":"decided","worked_on_exit_date":"worked_or_planned"}
blocked_html,_=render(blocked)
m=re.search(r'<div class="notice critical">(.*?)</div>',blocked_html,re.S)
assert m
warning=re.sub(r'<[^>]+>','',m.group(1))
assert "退職日に出勤する前に確認" in warning
assert "退職日に出勤すると、退職後の傷病手当金にどう影響しますか" in warning
assert "マイナポータル" not in warning
assert len(warning) < 150, len(warning)

# If attendance is not answered yet, show only the short confirmation reminder.
unknown={**health,"employment_status":"exit_date_fixed_employed","exit_date_status":"decided"}
unknown.pop("worked_on_exit_date",None)
unknown_html,_=render(unknown)
assert "退職日の出勤予定を確認してください" in unknown_html
assert "マイナポータル" not in unknown_html

print("REPORT_READABILITY_ROUND3_OK")
