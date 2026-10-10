from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime"
RENDERER = RUNTIME / "report_template_v0.1" / "render_report.py"

spec = importlib.util.spec_from_file_location("taishoku_render_report", RENDERER)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)

# 1) A disputed separation reason must show the calculation premise next to the headline amount.
answer_dispute = {
    "age_at_exit": 40,
    "employment_insurance_duration": "5_to_10y",
}
ei_dispute = {
    "benefit_daily_yen": 6200,
    "reason": {"status_code": "EI_REASON_NOTICE_DISPUTE"},
    "scenarios": [
        {"id": "general", "label": "通常の給付日数で計算した場合", "days": 90, "total_yen": 558000},
    ],
}
html = mod.employment_summary(answer_dispute, ei_dispute)
assert "一般の給付日数で仮計算" in html
assert "離職理由はまだ確定していません" in html
assert "仮の給付日数" in html
assert "確定額ではありません" in html

# 2) If another scenario exists, it must be visible rather than hidden only in details.
ei_two = {
    **ei_dispute,
    "reason": {"status_code": "EI_REASON_TOKUTEI_JUKYU_POSSIBLE"},
    "scenarios": [
        {"id": "general", "label": "通常の給付日数で計算した場合", "days": 90, "total_yen": 558000},
        {"id": "special_if_recognized", "label": "長時間労働などが離職理由として認められた場合", "days": 180, "total_yen": 1116000},
    ],
}
html = mod.employment_summary(answer_dispute, ei_two)
assert "離職理由が認められた場合は、日数・総額が変わる" in html
assert "180日" in html and "1,116,000円" in html

# 3) Sickness-allowance state must change the guidance across employment states.
sho_result = {
    "sickness_allowance": {
        "active": True,
        "status_code": "SHO_CURRENT_POSSIBILITY",
        "amount": {"daily_yen": 5000},
        "payment_timing": {"processing_business_days": 10},
        "post_exit": {"status_code": "SHO_POST_EXIT_POSSIBILITY"},
    }
}
state_expected = {
    "not_applied": "まだ申請していません",
    "applying": "申請中",
    "receiving": "受給中",
}
for employment_status in ("on_leave", "exit_date_fixed_employed", "retired"):
    for benefit_state, expected in state_expected.items():
        answer = {
            "employment_status": employment_status,
            "sickness_benefit_status": benefit_state,
            "cause_work_related": "no",
        }
        output = mod.sickness_section(answer, sho_result)
        assert expected in output, (employment_status, benefit_state)
        assert "入力なし" not in output
        if employment_status == "retired":
            assert "退職前に本人として加入していた健康保険" in output
            assert "現在の国民健康保険や家族の扶養先ではありません" in output
        else:
            assert "現在、会社で本人として加入している健康保険" in output
        if benefit_state == "applying":
            assert "同じ期間を出し直す前に" in output
        if benefit_state == "receiving":
            assert "初回申請ではなく次回分" in output

# Extra captured states must also be explicitly handled.
for benefit_state, expected in {
    "received_before": "過去に受給したことがあります",
    "unknown": "申請状況を先に確認",
}.items():
    output = mod.sickness_section(
        {"employment_status": "retired", "sickness_benefit_status": benefit_state, "cause_work_related": "no"},
        sho_result,
    )
    assert expected in output

# 4) Already supplied values must not be repeated as missing.
answer_complete_for_items = {
    "health_insurance_type": "kyokai_kenpo",
    "wage_regular_month_estimate": 300000,
    "reason_causation": False,
    "overtime_evidence": False,
}
result_false_missing = {
    "sickness_allowance": {
        "missing_inputs": ["health_insurance_type"],
    },
    "employment_insurance": {
        "missing_inputs": [
            "wage_6m_total_or_regular_month",
            "reason_causation",
            "overtime_evidence",
        ],
    },
    "human_review": {"reasons": []},
}
assert mod.review_section(answer_complete_for_items, result_false_missing) == ""

result_real_missing = {
    "sickness_allowance": {"missing_inputs": ["absence_pay_status"]},
    "employment_insurance": {"missing_inputs": []},
    "human_review": {"reasons": []},
}
review = mod.review_section({}, result_real_missing)
assert "休業日に給与・手当が支払われたか" in review
assert "まだ確認できていないことだけ" in review

# 5) Optional metadata must not emit a fake reception number.
assert "受付番号" not in mod.meta_row({"display_name": "テスト"})
assert "受付番号 WF-TEST" in mod.meta_row({"display_name": "テスト", "reference_id": "WF-TEST"})

# 6) Vague timing must be replaced with a real deadline or a concrete trigger.
eval_source = (RUNTIME / "workflow_rule_package_v0.1" / "evaluate.mjs").read_text(encoding="utf-8")
for phrase in (
    "国保は原則14日以内",
    "退職日の翌日から20日以内",
    "第1号になる場合は退職日の翌日から14日以内",
    "働けない状態が30日以上続いたら",
    "受給期間は原則、退職日の翌日から1年",
):
    assert phrase in eval_source, phrase

renderer_source = RENDERER.read_text(encoding="utf-8")
template_source = (RUNTIME / "report_template_v0.1" / "report_template.html").read_text(encoding="utf-8")
assert "known_total = yen(answer.get('known_total_amount')) if answer.get('known_total_amount') is not None else '入力なし'" not in renderer_source
assert "受付番号 {{reference_id}}" not in template_source
assert "reference_id', '未設定'" not in renderer_source

print("REPORT_OUTPUT_CLARITY_MATRIX_OK: 9 core status/state combinations + edge cases")
