#!/usr/bin/env python3
from __future__ import annotations

from typing import Dict, Tuple

import numpy as np
import pandas as pd

POINTS = {1: 10.0, 2: 8.0, 3: 6.0, 4: 4.0, 5: 2.0, 6: 1.0}
NEUTRAL_WINRATE = sum(POINTS.values()) / 6.0  # 5.1667
BASE_HALF_LIFE_DAYS = 365.0
FORM_HALF_LIFE_DAYS = 28.0
FORM_LOOKBACK_DAYS = 120
RATING_PRIOR_RACES = 28.0
FORM_PRIOR_RACES = 18.0
MAX_FORM_ADJ = 0.60
MAX_CONDITION_ADJ = 0.75

# 少数標本は「参考」ではなく当日補正から外す。
CONDITION_RULES = {
    "venue": {"min_n": 30, "prior_n": 50, "min_effect": 0.10},
    "grade": {"min_n": 30, "prior_n": 50, "min_effect": 0.10},
    "series": {"min_n": 30, "prior_n": 50, "min_effect": 0.10},
    "weather": {"min_n": 50, "prior_n": 80, "min_effect": 0.10},
    "wind_direction": {"min_n": 50, "prior_n": 80, "min_effect": 0.10},
    "wind_band": {"min_n": 50, "prior_n": 80, "min_effect": 0.10},
    "wave_band": {"min_n": 50, "prior_n": 80, "min_effect": 0.10},
}

GLOBAL_INTERACTION_RULES = {
    "venue_course": {"min_n": 180, "prior_n": 300},
    "weather_course": {"min_n": 250, "prior_n": 400},
    "wind_direction_course": {"min_n": 250, "prior_n": 400},
    "wind_band_course": {"min_n": 250, "prior_n": 400},
    "wave_band_course": {"min_n": 250, "prior_n": 400},
}


def _num(s):
    return pd.to_numeric(s, errors="coerce")


def normalize_grade(v) -> str:
    s = str(v or "").upper().replace(" ", "")
    if "PG1" in s:
        return "PG1"
    if "SG" in s:
        return "SG"
    if "G1" in s:
        return "G1"
    if "G2" in s:
        return "G2"
    if "G3" in s:
        return "G3"
    return "一般"


def series_label(title=None, race_name=None) -> str:
    s = f"{title or ''} {race_name or ''}".replace(" ", "")
    if "ヴィーナス" in s:
        return "ヴィーナス"
    if "オールレディース" in s or "レディース" in s or "女子" in s:
        return "レディース"
    if "ルーキー" in s:
        return "ルーキー"
    if "マスターズ" in s:
        return "マスターズ"
    return "通常"


def _weighted_group_mean(df: pd.DataFrame, keys, value: str, weight: str) -> pd.DataFrame:
    keys = [keys] if isinstance(keys, str) else list(keys)
    z = df[keys + [value, weight]].dropna(subset=[value, weight]).copy()
    if z.empty:
        return pd.DataFrame(columns=keys + ["mean", "weight_sum", "n"])
    z["_wx"] = z[value] * z[weight]
    out = z.groupby(keys, dropna=False).agg(
        wx_sum=("_wx", "sum"), weight_sum=(weight, "sum"), n=(value, "size")
    ).reset_index()
    out["mean"] = out["wx_sum"] / out["weight_sum"].replace(0, np.nan)
    return out[keys + ["mean", "weight_sum", "n"]]


def _center_mapping(values: Dict, exposure: pd.Series) -> Dict:
    if not values:
        return values
    mapped = exposure.map(values)
    center = float(mapped.mean()) if mapped.notna().any() else 0.0
    return {k: float(v - center) for k, v in values.items()}


def _race_center(s: pd.Series, race_code: pd.Series) -> pd.Series:
    return s - s.groupby(race_code).transform("mean")


def _fit_global_components(p: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    x = p.copy()
    ref = x["race_date"].max()
    age = (ref - x["race_date"]).dt.days.clip(lower=0)
    x["_w"] = np.power(0.5, age / BASE_HALF_LIFE_DAYS)
    x["points"] = _num(x["finish"]).map(POINTS)
    x = x.dropna(subset=["points", "regno", "レースコード", "actual_course"]).copy()
    x["race_mean_points"] = x.groupby("レースコード")["points"].transform("mean")
    x["target_centered"] = x["points"] - x["race_mean_points"]

    global_rows = []

    # コース全体差。
    cg = _weighted_group_mean(x, "actual_course", "target_centered", "_w")
    course_map = {int(r["actual_course"]): float(r["mean"]) for _, r in cg.iterrows()}
    course_map = _center_mapping(course_map, x["actual_course"])
    x["_course_raw"] = x["actual_course"].map(course_map).fillna(0.0)
    x["course_component"] = _race_center(x["_course_raw"], x["レースコード"])
    for _, r in cg.iterrows():
        c = int(r["actual_course"])
        global_rows.append({
            "adjustment_type": "course", "condition_value": str(c), "course": c,
            "n": int(r["n"]), "effective_n": float(r["weight_sum"]),
            "raw_delta": float(r["mean"]), "adjustment": float(course_map.get(c, 0.0)), "accepted": 1,
        })

    # 場ごとのコース差。これは「当地巧者」と分離する。
    venue_col = "レース場" if "レース場" in x.columns else None
    x["venue_course_component"] = 0.0
    if venue_col:
        tmp = x.copy()
        tmp["_resid"] = tmp["target_centered"] - tmp["course_component"]
        vg = _weighted_group_mean(tmp, [venue_col, "actual_course"], "_resid", "_w")
        rule = GLOBAL_INTERACTION_RULES["venue_course"]
        vc_map = {}
        for _, r in vg.iterrows():
            key = (str(r[venue_col]), int(r["actual_course"]))
            shrink = float(r["n"]) / (float(r["n"]) + rule["prior_n"])
            adj = float(r["mean"]) * shrink if int(r["n"]) >= rule["min_n"] else 0.0
            vc_map[key] = adj
            global_rows.append({
                "adjustment_type": "venue_course", "condition_value": str(r[venue_col]), "course": int(r["actual_course"]),
                "n": int(r["n"]), "effective_n": float(r["weight_sum"]), "raw_delta": float(r["mean"]),
                "adjustment": float(adj), "accepted": int(int(r["n"]) >= rule["min_n"]),
            })
        if vc_map:
            by_venue = {}
            for (v, c), val in vc_map.items():
                by_venue.setdefault(v, []).append((c, val))
            for v, items in by_venue.items():
                center = float(np.mean([z[1] for z in items])) if items else 0.0
                for c, val in items:
                    vc_map[(v, c)] = val - center
            x["_venue_course_raw"] = [
                vc_map.get((str(v), int(c)), 0.0) for v, c in zip(x[venue_col], x["actual_course"])
            ]
            x["venue_course_component"] = _race_center(x["_venue_course_raw"], x["レースコード"])

    # モーターは同一レース内の2連率差だけを使う。
    x["motor_component"] = 0.0
    motor_slope = 0.0
    if "motor_2rate" in x.columns:
        m = _num(x["motor_2rate"])
        m_center = m - m.groupby(x["レースコード"]).transform("mean")
        resid = x["target_centered"] - x["course_component"] - x["venue_course_component"]
        ok = m_center.notna() & resid.notna()
        if ok.sum() >= 1000:
            ww = x.loc[ok, "_w"].to_numpy(float)
            xx = m_center.loc[ok].to_numpy(float)
            yy = resid.loc[ok].to_numpy(float)
            denom = float(np.sum(ww * xx * xx))
            if denom > 0:
                motor_slope = float(np.sum(ww * xx * yy) / denom)
                motor_slope = float(np.clip(motor_slope, -0.08, 0.08))
        raw_motor = (m_center.fillna(0.0) * motor_slope).clip(-0.8, 0.8)
        x["motor_component"] = _race_center(raw_motor, x["レースコード"])
        global_rows.append({
            "adjustment_type": "motor_slope", "condition_value": "motor_2rate_centered_1pt", "course": np.nan,
            "n": int(ok.sum()), "effective_n": float(x.loc[ok, "_w"].sum()), "raw_delta": motor_slope,
            "adjustment": motor_slope, "accepted": int(ok.sum() >= 1000),
        })

    # F状態。
    x["f_component"] = 0.0
    if "f_count" in x.columns:
        f = _num(x["f_count"]).fillna(0)
        x["_f_bucket"] = np.where(f >= 2, "2+", np.where(f >= 1, "1", "0"))
        resid = x["target_centered"] - x["course_component"] - x["venue_course_component"] - x["motor_component"]
        tmp = x.copy(); tmp["_resid"] = resid
        fg = _weighted_group_mean(tmp, "_f_bucket", "_resid", "_w")
        fmap = {}
        for _, r in fg.iterrows():
            shrink = float(r["n"]) / (float(r["n"]) + 500.0)
            fmap[str(r["_f_bucket"])] = float(r["mean"]) * shrink
        fmap = _center_mapping(fmap, x["_f_bucket"])
        raw_f = x["_f_bucket"].map(fmap).fillna(0.0)
        x["f_component"] = _race_center(raw_f, x["レースコード"])
        for _, r in fg.iterrows():
            k = str(r["_f_bucket"])
            global_rows.append({
                "adjustment_type": "f_count", "condition_value": k, "course": np.nan,
                "n": int(r["n"]), "effective_n": float(r["weight_sum"]), "raw_delta": float(r["mean"]),
                "adjustment": float(fmap.get(k, 0.0)), "accepted": 1,
            })
    else:
        x["_f_bucket"] = "0"

    # 天候・風・波はコースとの相互作用として、十分な件数があるものだけ採用。
    env_specs = [
        ("weather_course", "天候"),
        ("wind_direction_course", "風向"),
        ("wind_band_course", "wind_band"),
        ("wave_band_course", "wave_band"),
    ]
    x["environment_component"] = 0.0
    running = x["target_centered"] - x["course_component"] - x["venue_course_component"] - x["motor_component"] - x["f_component"]
    for adj_type, col in env_specs:
        if col not in x.columns:
            continue
        tmp = x.copy(); tmp["_resid"] = running
        gg = _weighted_group_mean(tmp, [col, "actual_course"], "_resid", "_w")
        rule = GLOBAL_INTERACTION_RULES[adj_type]
        mp = {}
        for _, r in gg.iterrows():
            val = str(r[col]); c = int(r["actual_course"])
            shrink = float(r["n"]) / (float(r["n"]) + rule["prior_n"])
            accepted = int(int(r["n"]) >= rule["min_n"])
            adj = float(r["mean"]) * shrink if accepted else 0.0
            mp[(val, c)] = adj
            global_rows.append({
                "adjustment_type": adj_type, "condition_value": val, "course": c,
                "n": int(r["n"]), "effective_n": float(r["weight_sum"]), "raw_delta": float(r["mean"]),
                "adjustment": adj, "accepted": accepted,
            })
        if mp:
            raw = pd.Series([mp.get((str(v), int(c)), 0.0) for v, c in zip(x[col], x["actual_course"])], index=x.index, dtype=float)
            comp = _race_center(raw, x["レースコード"])
            x["environment_component"] += comp
            running = running - comp

    x["known_component"] = x["course_component"] + x["venue_course_component"] + x["motor_component"] + x["f_component"] + x["environment_component"]
    x["base_resid"] = x["target_centered"] - x["known_component"]
    return x, pd.DataFrame(global_rows)


def _fit_opponent_ratings(x: pd.DataFrame) -> pd.Series:
    regs = pd.Index(sorted(x["regno"].dropna().astype(int).unique()))
    rating = pd.Series(0.0, index=regs, dtype=float)
    for _ in range(60):
        own = x["regno"].astype(int).map(rating).fillna(0.0)
        race_sum = own.groupby(x["レースコード"]).transform("sum")
        race_n = own.groupby(x["レースコード"]).transform("count")
        opp = (race_sum - own) / (race_n - 1).replace(0, np.nan)
        candidate = x["base_resid"] + opp.fillna(0.0)
        tmp = pd.DataFrame({"regno": x["regno"].astype(int), "w": x["_w"], "cand": candidate})
        tmp["wc"] = tmp["w"] * tmp["cand"]
        g = tmp.groupby("regno").agg(wc=("wc", "sum"), w=("w", "sum"))
        new = (g["wc"] / (g["w"] + RATING_PRIOR_RACES)).reindex(regs).fillna(0.0)
        exposure = x["regno"].astype(int).map(new).fillna(0.0)
        center = float(np.average(exposure, weights=x["_w"]))
        new = new - center
        diff = float((new - rating).abs().max())
        rating = new
        if diff < 1e-5:
            break
    return rating


def _fit_form(x: pd.DataFrame, rating: pd.Series):
    own = x["regno"].astype(int).map(rating).fillna(0.0)
    race_sum = own.groupby(x["レースコード"]).transform("sum")
    race_n = own.groupby(x["レースコード"]).transform("count")
    opp = (race_sum - own) / (race_n - 1).replace(0, np.nan)
    x = x.copy()
    x["opponent_rating"] = opp.fillna(0.0)
    x["model_center_without_form"] = own - x["opponent_rating"] + x["known_component"]
    x["model_residual"] = x["target_centered"] - x["model_center_without_form"]

    ref = x["race_date"].max()
    age = (ref - x["race_date"]).dt.days.clip(lower=0)
    xf = x.loc[age <= FORM_LOOKBACK_DAYS].copy()
    agef = (ref - xf["race_date"]).dt.days.clip(lower=0)
    xf["_fw"] = np.power(0.5, agef / FORM_HALF_LIFE_DAYS)
    xf["_fwr"] = xf["_fw"] * xf["model_residual"]
    g = xf.groupby("regno").agg(
        form_wr=("_fwr", "sum"), form_w=("_fw", "sum"), form_n=("model_residual", "size"), recent_last_date=("race_date", "max")
    )
    g["form_raw"] = g["form_wr"] / g["form_w"].replace(0, np.nan)
    g["form_adjustment"] = (g["form_raw"] * (g["form_w"] / (g["form_w"] + FORM_PRIOR_RACES))).clip(-MAX_FORM_ADJ, MAX_FORM_ADJ)
    return x, g.reset_index()


def _condition_effect_rows(x: pd.DataFrame) -> pd.DataFrame:
    specs = [
        ("venue", "レース場"), ("grade", "_grade_norm"), ("series", "_series"),
        ("weather", "天候"), ("wind_direction", "風向"), ("wind_band", "wind_band"), ("wave_band", "wave_band"),
    ]
    rows = []
    for kind, col in specs:
        if col not in x.columns:
            continue
        rule = CONDITION_RULES[kind]
        z = x.dropna(subset=["regno", col, "model_residual", "race_date"]).copy()
        if kind == "series":
            z = z[z[col].astype(str) != "通常"]
        for (reg, val), g in z.groupby(["regno", col], sort=False):
            n = int(len(g))
            raw = float(np.average(g["model_residual"], weights=g["_w"])) if n else np.nan
            g = g.sort_values("race_date"); mid = n // 2
            h1 = float(g.iloc[:mid]["model_residual"].mean()) if mid else np.nan
            h2 = float(g.iloc[mid:]["model_residual"].mean()) if n - mid else np.nan

            accepted = True; reason = "採用"
            if n < rule["min_n"]:
                accepted = False; reason = "標本不足"
            elif not np.isfinite(raw) or abs(raw) < rule["min_effect"]:
                accepted = False; reason = "差が小さい"
            elif not np.isfinite(h1) or not np.isfinite(h2) or h1 * h2 <= 0:
                accepted = False; reason = "期間で再現せず"
            elif min(abs(h1), abs(h2)) < rule["min_effect"] * 0.45:
                accepted = False; reason = "期間で弱い"

            shrink = n / (n + rule["prior_n"])
            adjustment = float(np.clip(raw * shrink, -MAX_CONDITION_ADJ, MAX_CONDITION_ADJ)) if accepted else 0.0
            agreement = 0.0
            if np.isfinite(h1) and np.isfinite(h2):
                agreement = max(0.0, 1.0 - abs(h1 - h2) / (4.0 * (abs(raw) + 0.10)))
            reliability = float(np.clip(shrink * agreement, 0.0, 1.0))
            rows.append({
                "regno": int(reg), "condition_type": kind, "condition_value": str(val), "n": n,
                "effective_n": float(g["_w"].sum()), "raw_delta": raw, "first_half_delta": h1, "second_half_delta": h2,
                "adjustment": adjustment, "accepted": int(accepted), "reliability": reliability, "reason": reason,
            })
    return pd.DataFrame(rows)


def build_adjusted_tables(panel: pd.DataFrame, profile: pd.DataFrame | None = None) -> Dict[str, pd.DataFrame]:
    """Build opponent/condition-adjusted win-rate-equivalent tables.

    The output is an estimate on BOAT RACE's familiar points-per-start scale,
    not an official win rate and not a guaranteed probability model.
    """
    if panel.empty:
        return {
            "racer_adjusted": pd.DataFrame(), "racer_condition_adjustments": pd.DataFrame(),
            "model_global_adjustments": pd.DataFrame(), "model_validation": pd.DataFrame(),
        }

    p = panel.copy()
    p["race_date"] = pd.to_datetime(p["race_date"], errors="coerce")
    p = p.dropna(subset=["race_date", "regno", "finish", "actual_course"]).copy()
    p["regno"] = _num(p["regno"]).astype("Int64")
    p = p.dropna(subset=["regno"]).copy(); p["regno"] = p["regno"].astype(int)
    p["_grade_norm"] = p.get("グレード", pd.Series("", index=p.index)).map(normalize_grade)
    titles = p.get("タイトル", pd.Series("", index=p.index)); rnames = p.get("レース名", pd.Series("", index=p.index))
    p["_series"] = [series_label(a, b) for a, b in zip(titles, rnames)]

    x, globals_df = _fit_global_components(p)
    rating = _fit_opponent_ratings(x)
    x, form = _fit_form(x, rating)
    conditions = _condition_effect_rows(x)

    agg = x.groupby("regno").agg(sample_n=("finish", "size"), raw_points=("points", "mean"), last_date=("race_date", "max")).reset_index()
    agg["ability_adjustment"] = agg["regno"].map(rating).fillna(0.0)
    agg["base_winrate"] = (NEUTRAL_WINRATE + agg["ability_adjustment"]).clip(1.0, 10.0)
    agg = agg.merge(form[["regno", "form_n", "form_raw", "form_adjustment"]], on="regno", how="left")
    agg["form_n"] = agg["form_n"].fillna(0).astype(int); agg["form_adjustment"] = agg["form_adjustment"].fillna(0.0)
    agg["current_winrate"] = (agg["base_winrate"] + agg["form_adjustment"]).clip(1.0, 10.0)
    agg["rating_quality"] = np.clip(agg["sample_n"] / (agg["sample_n"] + 40.0), 0.0, 1.0)

    if profile is not None and not profile.empty and "regno" in profile.columns:
        pcols = [c for c in ["regno", "name", "class_grade", "national_win_rate"] if c in profile.columns]
        prof = profile[pcols].copy(); prof["regno"] = _num(prof["regno"]).astype("Int64"); prof = prof.dropna(subset=["regno"])
        prof["regno"] = prof["regno"].astype(int)
        agg = agg.merge(prof.drop_duplicates("regno"), on="regno", how="left")

    mae_global = float(np.average(np.abs(x["target_centered"] - x["known_component"]), weights=x["_w"]))
    mae_adjusted = float(np.average(np.abs(x["model_residual"]), weights=x["_w"]))
    validation = pd.DataFrame([
        {"metric": "weighted_mae_global_only", "value": mae_global},
        {"metric": "weighted_mae_with_opponent_rating", "value": mae_adjusted},
        {"metric": "mae_improvement_pct", "value": (mae_global - mae_adjusted) / mae_global * 100 if mae_global else np.nan},
        {"metric": "neutral_winrate_scale", "value": NEUTRAL_WINRATE},
        {"metric": "races", "value": float(x["レースコード"].nunique())},
        {"metric": "entries", "value": float(len(x))},
        {"metric": "racers", "value": float(x["regno"].nunique())},
    ])

    return {
        "racer_adjusted": agg.sort_values("base_winrate", ascending=False).reset_index(drop=True),
        "racer_condition_adjustments": conditions.sort_values(["regno", "condition_type", "condition_value"]).reset_index(drop=True) if not conditions.empty else conditions,
        "model_global_adjustments": globals_df.reset_index(drop=True),
        "model_validation": validation,
    }
