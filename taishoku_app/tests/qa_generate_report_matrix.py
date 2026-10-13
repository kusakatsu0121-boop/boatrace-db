from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime"
OUT = ROOT / "qa_output" / "report_matrix"
RENDERER = RUNTIME / "report_template_v0.1" / "render_report.py"

BASE = {
    "display_name": "QAテスト",
    "as_of_date": "2026-10-12",
    "age_at_exit": 40,
    "employment_insurance_duration": "5_to_10y",
    "wage_regular_month_estimate": 300000,
    "job_intent": "seeking_now",
    "can_start_new_job": "now",
    "exit_reasons": ["career"],
    "separation_notice_status": "received",
    "separation_reason_dispute": "no_difference",
    "post_exit_health_insurance_done": True,
    "national_pension_done": True,
    "cause_work_related": "no",
}

HEALTH = {
    "exit_reasons": ["health"],
    "can_start_new_job": "difficult",
    "health_insurance_type": "kyokai_kenpo",
    "medical_consultation": "consulted",
    "waiting_combined_four_days": True,
    "payable_absence_after_waiting": "yes",
    "absence_pay_status": "none",
    "cause_work_related": "no",
    "insured_period_before_exit": "one_year_or_more",
}

CASES = [
    ("01_retired_normal", {"employment_status": "retired"}),
    ("02_leave_not_applied", {"employment_status": "on_leave", **HEALTH, "sickness_benefit_status": "not_applied"}),
    ("03_leave_applying", {"employment_status": "on_leave", **HEALTH, "sickness_benefit_status": "applying"}),
    ("04_leave_receiving", {"employment_status": "on_leave", **HEALTH, "sickness_benefit_status": "receiving"}),
    ("05_exit_fixed_not_applied", {"employment_status": "exit_date_fixed_employed", "exit_date_status": "decided", **HEALTH, "sickness_benefit_status": "not_applied"}),
    ("06_exit_fixed_applying", {"employment_status": "exit_date_fixed_employed", "exit_date_status": "decided", **HEALTH, "sickness_benefit_status": "applying"}),
    ("07_exit_fixed_receiving", {"employment_status": "exit_date_fixed_employed", "exit_date_status": "decided", **HEALTH, "sickness_benefit_status": "receiving"}),
    ("08_retired_not_applied", {"employment_status": "retired", **HEALTH, "sickness_benefit_status": "not_applied"}),
    ("09_retired_applying", {"employment_status": "retired", **HEALTH, "sickness_benefit_status": "applying"}),
    ("10_retired_receiving", {"employment_status": "retired", **HEALTH, "sickness_benefit_status": "receiving"}),
    ("11_retired_reason_dispute", {
        "employment_status": "retired",
        "exit_reasons": ["long_hours"],
        "overtime_hours_last_6m": [85, 90, 95, 80, 88, 92],
        "overtime_evidence": True,
        "reason_causation": True,
        "separation_notice_status": "received",
        "separation_reason_dispute": "difference",
    }),
    ("12_retired_sparse_unknown", {
        "employment_status": "retired",
        "can_start_new_job": "unknown",
        "job_intent": "undecided",
        "exit_reasons": ["not_organized"],
        "employment_insurance_duration": "unknown",
        "wage_regular_month_estimate": None,
        "separation_notice_status": "unknown",
        "post_exit_health_insurance_done": False,
        "national_pension_done": False,
    }),
]

if OUT.exists():
    shutil.rmtree(OUT)
OUT.mkdir(parents=True, exist_ok=True)

summary = []
for name, extra in CASES:
    case = dict(BASE)
    case.update(extra)
    d = OUT / name
    d.mkdir(parents=True, exist_ok=True)
    answer = d / "answer.json"
    html = d / "report.html"
    pdf = d / "report.pdf"
    snap = d / "snapshot.json"
    answer.write_text(json.dumps(case, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    cp = subprocess.run(
        ["python3", str(RENDERER), str(answer), "--html", str(html), "--pdf", str(pdf), "--snapshot", str(snap)],
        text=True, capture_output=True
    )
    if cp.returncode != 0:
        raise SystemExit(f"{name} render failed\nSTDOUT:\n{cp.stdout}\nSTDERR:\n{cp.stderr}")
    h = html.read_text(encoding="utf-8")
    s = json.loads(snap.read_text(encoding="utf-8"))
    summary.append({
        "case": name,
        "review_required": bool((s.get("human_review") or {}).get("required")),
        "review_reasons": (s.get("human_review") or {}).get("reasons") or [],
        "html_chars": len(h),
        "has_input_none": "入力なし" in h,
        "has_unset_reference": "受付番号 未設定" in h,
        "has_vague_early": "すみやかに" in h,
        "has_current_insurer_wording": "現在、会社で本人として加入している健康保険" in h,
        "has_pre_exit_insurer_wording": "退職前に本人として加入していた健康保険" in h,
    })

(OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(summary, ensure_ascii=False, indent=2))
