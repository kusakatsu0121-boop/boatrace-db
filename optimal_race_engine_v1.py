#!/usr/bin/env python3
"""
Optimal Race Engine v1

Condition-first hierarchical engine built from findings already validated in this
project. This module deliberately avoids inventing a global all-factor weight or
uncalibrated trifecta probabilities.

Input is a normalized race feature dict. Output is an explainable race reading:
entry pressure -> boat-1 status -> winner branches -> 2nd paths -> 3rd paths.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional


# ---- validated structural constants (project holdout findings) ----------------

C1_WIN_SECOND = {
    2: 0.34594,
    3: 0.28864,
    4: 0.18747,
    5: 0.12397,
    6: 0.05398,
}

# P(third course | first course=1, second course=*)
C1_CHAIN_THIRD = {
    (1, 2): {3: 0.3902, 4: 0.2826},
    (1, 3): {2: 0.3547, 4: 0.2950},
    (1, 4): {2: 0.3395},
    (1, 5): {2: 0.3325},
    (1, 6): {2: 0.3270},
}

VALIDATED_ATTACKS = {
    "B2_SASHI": {
        "combined_rate": 0.2712,
        "n": 236,
        "description": "boat1 beaten-sashi high × boat2 course2 sashi high",
    },
    "B3_MAKURI": {
        "combined_rate": 0.3062,
        "n": 209,
        "description": "boat1 beaten-makuri high × boat3 course3 makuri high",
    },
    "B3_MAKURISASHI": {
        "combined_rate": 0.1926,
        "n": 270,
        "description": "boat1 beaten-makuri-sashi high × boat3 course3 makuri-sashi high",
    },
}

FRONT_PUSH_EFFECTS = {
    # Descriptive/OOS matched effects conditional on actual movement. These are
    # evidence labels, NOT causal deductions to subtract blindly pre-race.
    "INYA30_ACTUAL_FRONT": {"n": 379, "b1_win": 0.3509, "matched": 0.5457, "diff_pt": -17.66},
    "INYA30_RETAIN_C1": {"n": 344, "b1_win": 0.3692, "matched": 0.5457, "diff_pt": -17.66},
    "INYA30_TO_C2_RETAIN_C1": {"n": 231, "b1_win": 0.3377, "matched": 0.5417, "diff_pt": -20.41},
}


@dataclass
class Evidence:
    code: str
    strength: str
    text: str
    n: Optional[int] = None
    rate: Optional[float] = None


@dataclass
class WinnerBranch:
    boat: int
    method: str
    priority: int
    evidence: List[Evidence]


@dataclass
class PathCandidate:
    course: int
    score: float
    evidence: List[Evidence]


def _bool(d: Dict[str, Any], key: str) -> bool:
    return bool(d.get(key, False))


def _num(d: Dict[str, Any], key: str, default: float = 0.0) -> float:
    try:
        v = d.get(key, default)
        return float(v) if v is not None else default
    except Exception:
        return default


def entry_pressure(race: Dict[str, Any]) -> Dict[str, Any]:
    """Summarize front-push risk using only pre-race historical profiles."""
    out = []
    max_risk = 0.0
    for c in race.get("front_push_candidates", []) or []:
        opps = int(c.get("opportunities", 0) or 0)
        rate = _num(c, "front_push_rate")
        if opps < 15:
            label = "LOW_SAMPLE"
        elif rate >= 0.50:
            label = "VERY_HIGH"
        elif rate >= 0.30:
            label = "HIGH"
        elif rate >= 0.15:
            label = "MEDIUM"
        else:
            label = "LOW"
        max_risk = max(max_risk, rate if opps >= 15 else 0.0)
        out.append({
            "boat": int(c.get("boat", 0) or 0),
            "racer": c.get("racer"),
            "opportunities": opps,
            "front_push_rate": rate,
            "expected_course": c.get("expected_course"),
            "risk": label,
        })
    return {
        "max_front_push_rate": max_risk,
        "high_risk_present": any(x["risk"] in ("HIGH", "VERY_HIGH") for x in out),
        "candidates": out,
    }


def classify_inside(race: Dict[str, Any], entry: Dict[str, Any]) -> Dict[str, Any]:
    b1 = race.get("boat1", {}) or {}
    b2 = race.get("boat2", {}) or {}
    b3 = race.get("boat3", {}) or {}

    flags: List[str] = []
    ev: List[Evidence] = []

    if entry["high_risk_present"]:
        flags.append("INSIDE_FRONT_PUSH_RISK")
        ev.append(Evidence(
            "FRONT_PUSH",
            "HIGH",
            "historically high front-push racer is present; actual movement has shown a large matched reduction in boat-1 win/escape",
            n=FRONT_PUSH_EFFECTS["INYA30_RETAIN_C1"]["n"],
            rate=FRONT_PUSH_EFFECTS["INYA30_RETAIN_C1"]["b1_win"],
        ))

    if _bool(b1, "beaten_sashi_high") and _bool(b2, "sashi_high"):
        flags.append("INSIDE_PRESSURED_2")
        x = VALIDATED_ATTACKS["B2_SASHI"]
        ev.append(Evidence("B2_SASHI", "HIGH", x["description"], x["n"], x["combined_rate"]))

    if _bool(b1, "beaten_makuri_high") and _bool(b3, "makuri_high"):
        flags.append("INSIDE_PRESSURED_3_MAKURI")
        x = VALIDATED_ATTACKS["B3_MAKURI"]
        ev.append(Evidence("B3_MAKURI", "VERY_HIGH", x["description"], x["n"], x["combined_rate"]))

    if _bool(b1, "beaten_makurisashi_high") and _bool(b3, "makurisashi_high"):
        flags.append("INSIDE_PRESSURED_3_MS")
        x = VALIDATED_ATTACKS["B3_MAKURISASHI"]
        ev.append(Evidence("B3_MS", "MEDIUM", x["description"], x["n"], x["combined_rate"]))

    if not flags:
        flags.append("INSIDE_STRONG_OR_ORDINARY")

    # This is only a descriptive risk index used for ordering scenarios; it is
    # intentionally not presented as a win probability.
    risk_index = 0.0
    risk_index += min(entry["max_front_push_rate"], 0.70) * 2.0
    risk_index += 1.25 if "INSIDE_PRESSURED_2" in flags else 0.0
    risk_index += 1.75 if "INSIDE_PRESSURED_3_MAKURI" in flags else 0.0
    risk_index += 0.75 if "INSIDE_PRESSURED_3_MS" in flags else 0.0
    # Strong own escape profile can reduce scenario priority, but does not erase
    # a validated attack condition.
    if _bool(b1, "escape_high"):
        risk_index -= 0.50

    return {
        "flags": flags,
        "risk_index": round(risk_index, 3),
        "evidence": [asdict(x) for x in ev],
    }


def winner_branches(race: Dict[str, Any], inside: Dict[str, Any]) -> List[WinnerBranch]:
    branches: List[WinnerBranch] = []
    flags = set(inside["flags"])

    # Inside branch always exists; its priority falls when multiple validated
    # pressure conditions are active.
    inside_priority = 1 if inside["risk_index"] < 1.5 else 2
    branches.append(WinnerBranch(
        boat=1,
        method="escape/inside",
        priority=inside_priority,
        evidence=[Evidence("B1_BASE", "BASE", "ordinary inside branch; strength comes from boat1 course-1 profile and race baseline")],
    ))

    if "INSIDE_PRESSURED_2" in flags:
        x = VALIDATED_ATTACKS["B2_SASHI"]
        branches.append(WinnerBranch(2, "sashi", 1, [Evidence("B2_SASHI", "HIGH", x["description"], x["n"], x["combined_rate"])]))

    if "INSIDE_PRESSURED_3_MAKURI" in flags:
        x = VALIDATED_ATTACKS["B3_MAKURI"]
        branches.append(WinnerBranch(3, "makuri", 1, [Evidence("B3_MAKURI", "VERY_HIGH", x["description"], x["n"], x["combined_rate"])]))

    if "INSIDE_PRESSURED_3_MS" in flags:
        x = VALIDATED_ATTACKS["B3_MAKURISASHI"]
        branches.append(WinnerBranch(3, "makuri-sashi", 2, [Evidence("B3_MS", "MEDIUM", x["description"], x["n"], x["combined_rate"])]))

    # stable ordering: lower priority number first, then higher validated rate
    def rate_of(b: WinnerBranch) -> float:
        vals = [e.rate for e in b.evidence if e.rate is not None]
        return max(vals) if vals else 0.0

    return sorted(branches, key=lambda b: (b.priority, -rate_of(b), b.boat))


def second_paths(race: Dict[str, Any], winner_boat: int) -> List[PathCandidate]:
    """Rank second-place courses conditional on winner branch."""
    out: List[PathCandidate] = []
    if winner_boat == 1:
        follow = race.get("winner_follow", {}) or {}
        for course, base in C1_WIN_SECOND.items():
            ev = [Evidence("C1_STRUCT_FOLLOW", "BASE", f"course {course} second after course-1 win", rate=base)]
            score = base

            # Optional racer-specific follow lift supplied by database.
            key = f"c{course}_second_lift"
            lift = _num(follow, key, 0.0)
            n = int(follow.get(f"c{course}_second_n", 0) or 0)
            if n >= 20 and lift != 0:
                score += lift
                ev.append(Evidence("RACER_FOLLOW2", "MEDIUM" if n < 50 else "HIGH", f"winner racer-specific course-{course} second lift", n=n, rate=None))

            # Validated special interaction: high c3 allow-escape helps 1-3.
            if course == 3 and _bool(race.get("boat3", {}) or {}, "allow_escape_high"):
                score += 0.0311  # 32.35 - 29.24 points in decimal form
                ev.append(Evidence("C3_ALLOW_ESCAPE", "MEDIUM", "high course-3 allow-escape profile lifts course-3 second among boat-1 wins"))

            out.append(PathCandidate(course, score, ev))
    else:
        # Until stronger OOS path tables exist for non-1 winners, use supplied
        # branch-specific path data if present; otherwise leave this layer DATA_ONLY.
        supplied = (race.get("branch_second_paths", {}) or {}).get(str(winner_boat), {}) or {}
        for k, v in supplied.items():
            try:
                c = int(k)
                score = float(v.get("rate", 0.0) if isinstance(v, dict) else v)
                n = int(v.get("n", 0) if isinstance(v, dict) else 0)
            except Exception:
                continue
            out.append(PathCandidate(c, score, [Evidence("SUPPLIED_BRANCH_PATH", "DATA", "branch-specific historical second path", n=n, rate=score)]))

    return sorted(out, key=lambda x: -x.score)


def third_paths(race: Dict[str, Any], first_course: int, second_course: int) -> List[PathCandidate]:
    out: List[PathCandidate] = []
    key = (first_course, second_course)
    chain = C1_CHAIN_THIRD.get(key, {})
    for course, rate in chain.items():
        out.append(PathCandidate(course, rate, [Evidence(
            "COURSE_CHAIN",
            "HIGH",
            f"structural third-course chain after {first_course}-{second_course}",
            rate=rate,
        )]))

    # Optional racer-specific third-follow lift from database.
    follow = race.get("winner_follow", {}) or {}
    if first_course == 1:
        for c in range(2, 7):
            lift = _num(follow, f"c{c}_third_lift", 0.0)
            n = int(follow.get(f"c{c}_third_n", 0) or 0)
            if n >= 20 and lift != 0:
                found = next((x for x in out if x.course == c), None)
                if found is None:
                    found = PathCandidate(c, 0.0, [])
                    out.append(found)
                found.score += lift
                found.evidence.append(Evidence("RACER_FOLLOW3", "MEDIUM" if n < 50 else "HIGH", f"winner racer-specific course-{c} third lift", n=n))

    return sorted(out, key=lambda x: -x.score)


def evaluate_race(race: Dict[str, Any]) -> Dict[str, Any]:
    entry = entry_pressure(race)
    inside = classify_inside(race, entry)
    branches = winner_branches(race, inside)

    branch_out = []
    for b in branches:
        seconds = second_paths(race, b.boat)
        sec_out = []
        for s in seconds[:5]:
            # For standard-entry reading, boat number approximates course for the
            # structural branch. If predicted actual courses are supplied, callers
            # should normalize first_course/second_course before calling this layer.
            first_course = int((race.get("predicted_course_by_boat", {}) or {}).get(str(b.boat), b.boat))
            second_course = s.course
            thirds = third_paths(race, first_course, second_course)
            sec_out.append({
                "second_course": s.course,
                "score": round(s.score, 5),
                "evidence": [asdict(e) for e in s.evidence],
                "third_candidates": [
                    {"course": t.course, "score": round(t.score, 5), "evidence": [asdict(e) for e in t.evidence]}
                    for t in thirds[:4]
                ],
            })
        branch_out.append({
            "winner_boat": b.boat,
            "method": b.method,
            "priority": b.priority,
            "evidence": [asdict(e) for e in b.evidence],
            "second_candidates": sec_out,
        })

    status = "DATA_ONLY"
    high_codes = {e["code"] for e in inside["evidence"] if e["strength"] in ("HIGH", "VERY_HIGH")}
    if high_codes:
        status = "VALIDATED_SIGNAL"
    elif len(inside["flags"]) > 1 or entry["high_risk_present"]:
        status = "WATCH"

    return {
        "race_code": race.get("race_code"),
        "entry": entry,
        "inside": inside,
        "branches": branch_out,
        "context": race.get("context", {}),
        "market": race.get("market", {}),
        "status": status,
        "bet_status": "DATA_ONLY",  # promoted only by separate OOS betting-rule gate
    }


if __name__ == "__main__":
    # Tiny smoke example; production caller should build this dict from DB tables.
    sample = {
        "race_code": "SAMPLE",
        "boat1": {"escape_high": False, "beaten_sashi_high": True, "beaten_makuri_high": True},
        "boat2": {"sashi_high": True},
        "boat3": {"makuri_high": True, "allow_escape_high": True},
        "front_push_candidates": [
            {"boat": 5, "racer": "sample", "opportunities": 20, "front_push_rate": 0.40, "expected_course": 2}
        ],
        "winner_follow": {},
        "predicted_course_by_boat": {"1": 1, "2": 2, "3": 3},
    }
    import json
    print(json.dumps(evaluate_race(sample), ensure_ascii=False, indent=2))
