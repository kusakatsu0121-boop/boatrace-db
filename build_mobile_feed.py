#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from adjusted_winrate import NEUTRAL_WINRATE, normalize_grade, series_label
from racer_directory import cards_to_long, wave_band, wind_band


VENUES = {
    "01":"桐生","02":"戸田","03":"江戸川","04":"平和島","05":"多摩川","06":"浜名湖",
    "07":"蒲郡","08":"常滑","09":"津","10":"三国","11":"びわこ","12":"住之江",
    "13":"尼崎","14":"鳴門","15":"丸亀","16":"児島","17":"宮島","18":"徳山",
    "19":"下関","20":"若松","21":"芦屋","22":"福岡","23":"唐津","24":"大村"
}


def latest_file(root: Path) -> Path:
    files = sorted(root.glob("*/*/*.csv"))
    if not files:
        raise SystemExit(f"no csv files under {root}")
    return files[-1]


def read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, low_memory=False)


def maybe_read(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, low_memory=False) if path.exists() else pd.DataFrame()


def num(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return None
    try:
        x = float(v)
    except Exception:
        return None
    if not np.isfinite(x):
        return None
    return round(x, 4)


def intval(v):
    x = num(v)
    return int(x) if x is not None else None


def text(v):
    if v is None:
        return None
    s = str(v).strip()
    if not s or s.lower() == "nan":
        return None
    return s


def clean(d: dict) -> dict:
    return {k: v for k, v in d.items() if v is not None}


def event_runs(card_row: pd.Series | None, boat: int):
    if card_row is None:
        return []
    rows = []
    for day in range(1, 8):
        for run in (1, 2):
            p = f"艇{boat}_節D{day}走{run}_"
            race_no = intval(card_row.get(p + "R番号"))
            course = intval(card_row.get(p + "進入"))
            frame = intval(card_row.get(p + "枠"))
            stv = num(card_row.get(p + "ST"))
            finish = text(card_row.get(p + "着順"))
            if all(v is None for v in [race_no, course, frame, stv, finish]):
                continue
            rows.append(clean({
                "day": day, "run": run, "race_no": race_no, "course": course,
                "frame": frame, "st": stv, "finish": finish,
            }))
    return rows


def make_maps(globals_df: pd.DataFrame, conditions: pd.DataFrame):
    gm = {}
    motor_slope = 0.0
    if not globals_df.empty:
        for _, r in globals_df.iterrows():
            typ = text(r.get("adjustment_type")); val = text(r.get("condition_value")); course = intval(r.get("course"))
            accepted = intval(r.get("accepted")); adj = num(r.get("adjustment")) or 0.0
            if typ == "motor_slope" and accepted:
                motor_slope = adj
            if typ and val is not None and accepted:
                gm[(typ, val, course)] = adj
    cm = {}
    if not conditions.empty:
        for _, r in conditions.iterrows():
            if intval(r.get("accepted")) != 1:
                continue
            reg = intval(r.get("regno")); typ = text(r.get("condition_type")); val = text(r.get("condition_value"))
            if reg is None or typ is None or val is None:
                continue
            cm[(reg, typ, val)] = {
                "adjustment": num(r.get("adjustment")) or 0.0,
                "n": intval(r.get("n")) or 0,
                "reliability": num(r.get("reliability")) or 0.0,
            }
    return gm, cm, motor_slope


def gget(gm, typ, value, course=None):
    if value is None:
        return 0.0
    candidates = [str(value)]
    if str(value).isdigit():
        candidates.append(str(value).zfill(2))
    for v in candidates:
        key = (typ, v, course)
        if key in gm:
            return float(gm[key])
    return 0.0


def cget(cm, regno, typ, values):
    if regno is None:
        return None
    if not isinstance(values, (list, tuple)):
        values = [values]
    for v in values:
        if v is None:
            continue
        key = (int(regno), typ, str(v))
        if key in cm:
            return cm[key]
    return None


def center_values(entries, key):
    vals = [float(e.get(key, 0.0) or 0.0) for e in entries]
    mean = float(np.mean(vals)) if vals else 0.0
    for e, v in zip(entries, vals):
        e[key] = round(v - mean, 4)


def current_weather_map(src: Path, y: str, m: str, day: str):
    path = src / "previews" / "sui" / y / m / f"{day}.csv"
    if not path.exists():
        return {}
    df = read_csv(path)
    out = {}
    if "レースコード" not in df.columns:
        return out
    for _, r in df.iterrows():
        code = text(r.get("レースコード"))
        if not code:
            continue
        ws = num(r.get("風速(m)")); wave = num(r.get("波の高さ(cm)"))
        out[str(code)] = clean({
            "weather": text(r.get("天候")), "wind_direction": text(r.get("風向")), "wind_speed": ws,
            "wind_band": wind_band(ws) if ws is not None else None, "wave_height": wave,
            "wave_band": wave_band(wave) if wave is not None else None, "air_temp": num(r.get("気温(℃)")),
            "water_temp": num(r.get("水温(℃)")), "observed_at": text(r.get("気象観測時刻")),
        })
    return out


def add_today_adjustments(entries, venue_code, venue_name, grade, event_title, weather, gm, cm, motor_slope):
    if not entries:
        return
    grade_norm = normalize_grade(grade); series = series_label(event_title, None)

    strengths = []
    for e in entries:
        current = num(e.get("current_winrate"))
        strengths.append((current if current is not None else NEUTRAL_WINRATE) - NEUTRAL_WINRATE)
    for e, s in zip(entries, strengths):
        e["_current_strength"] = s

    motor_rates = [num(e.get("motor_2rate")) for e in entries]
    valid_m = [v for v in motor_rates if v is not None]
    motor_mean = float(np.mean(valid_m)) if valid_m else None

    for e in entries:
        course = int(e.get("boat_no") or 0); reg = intval(e.get("regno")); f = intval(e.get("f_count")) or 0
        f_bucket = "2+" if f >= 2 else ("1" if f >= 1 else "0")

        e["_course_adj"] = gget(gm, "course", str(course), course)
        e["_venue_course_adj"] = (
            gget(gm, "venue_course", venue_name, course)
            or gget(gm, "venue_course", venue_code, course)
            or gget(gm, "venue_course", str(int(venue_code)), course)
        )
        mr = num(e.get("motor_2rate"))
        e["_motor_adj"] = float(np.clip((mr - motor_mean) * motor_slope, -0.8, 0.8)) if mr is not None and motor_mean is not None else 0.0
        e["_f_adj"] = gget(gm, "f_count", f_bucket, None)

        env = 0.0
        if weather:
            env += gget(gm, "weather_course", weather.get("weather"), course)
            env += gget(gm, "wind_direction_course", weather.get("wind_direction"), course)
            env += gget(gm, "wind_band_course", weather.get("wind_band"), course)
            env += gget(gm, "wave_band_course", weather.get("wave_band"), course)
        e["_environment_adj"] = float(np.clip(env, -0.8, 0.8))

        used = []
        venue_hit = cget(cm, reg, "venue", [venue_name, venue_code, str(int(venue_code))])
        grade_hit = cget(cm, reg, "grade", grade_norm)
        series_hit = cget(cm, reg, "series", series) if series != "通常" else None
        place_adj = venue_hit["adjustment"] if venue_hit else 0.0
        series_adj = (grade_hit["adjustment"] if grade_hit else 0.0) + (series_hit["adjustment"] if series_hit else 0.0)
        weather_adj = 0.0; weather_hits = []
        if weather:
            for typ, val in [("weather", weather.get("weather")), ("wind_direction", weather.get("wind_direction")), ("wind_band", weather.get("wind_band")), ("wave_band", weather.get("wave_band"))]:
                hit = cget(cm, reg, typ, val)
                if hit:
                    weather_adj += hit["adjustment"]; weather_hits.append((typ, val, hit))
        weather_adj = float(np.clip(weather_adj, -0.5, 0.5))
        e["_personal_adj"] = float(np.clip(place_adj + series_adj + weather_adj, -0.8, 0.8))

        if venue_hit: used.append({"label": "当地適性", "value": round(place_adj, 3), "n": venue_hit["n"], "reliability": venue_hit["reliability"]})
        if grade_hit: used.append({"label": f"{grade_norm}適性", "value": round(grade_hit["adjustment"], 3), "n": grade_hit["n"], "reliability": grade_hit["reliability"]})
        if series_hit: used.append({"label": f"{series}適性", "value": round(series_hit["adjustment"], 3), "n": series_hit["n"], "reliability": series_hit["reliability"]})
        for typ, val, hit in weather_hits:
            label = {"weather":"天候","wind_direction":"風向","wind_band":"風速帯","wave_band":"波高帯"}[typ]
            used.append({"label": f"{label}:{val}", "value": round(hit["adjustment"], 3), "n": hit["n"], "reliability": hit["reliability"]})
        e["accepted_conditions"] = used

    for key in ["_course_adj", "_venue_course_adj", "_motor_adj", "_f_adj", "_environment_adj", "_personal_adj"]:
        center_values(entries, key)

    total_strength = [e["_current_strength"] for e in entries]
    for i, e in enumerate(entries):
        opp = [s for j, s in enumerate(total_strength) if j != i]
        field_adj = -float(np.mean(opp)) if opp else 0.0
        e["field_adjustment"] = round(field_adj, 4); e["course_adjustment"] = round(e["_course_adj"], 4)
        e["venue_course_adjustment"] = round(e["_venue_course_adj"], 4); e["motor_adjustment"] = round(e["_motor_adj"], 4)
        e["f_adjustment"] = round(e["_f_adj"], 4); e["environment_adjustment"] = round(e["_environment_adj"], 4)
        e["personal_condition_adjustment"] = round(e["_personal_adj"], 4)
        today = NEUTRAL_WINRATE + e["_current_strength"] + field_adj + e["_course_adj"] + e["_venue_course_adj"] + e["_motor_adj"] + e["_f_adj"] + e["_environment_adj"] + e["_personal_adj"]
        e["today_adjusted_winrate"] = round(float(np.clip(today, 1.0, 10.0)), 3)
        e["today_delta_vs_official"] = round(e["today_adjusted_winrate"] - float(e.get("national_win_rate") or NEUTRAL_WINRATE), 3)
        for k in [k for k in list(e.keys()) if k.startswith("_")]:
            e.pop(k, None)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--source", default="source/data"); ap.add_argument("--directory", default="artifacts/racer_directory"); ap.add_argument("--site", default="site"); args = ap.parse_args()
    src = Path(args.source); ddir = Path(args.directory); site = Path(args.site); data_dir = site / "data"; data_dir.mkdir(parents=True, exist_ok=True)

    card_file = latest_file(src / "programs" / "race_cards"); cards = read_csv(card_file); cl = cards_to_long(cards)
    if cl.empty: raise SystemExit("latest race card is empty")
    race_date = text(cl["レース日"].dropna().iloc[0]) if "レース日" in cl.columns else card_file.stem
    y, m, day = race_date.split("-"); title_path = src / "programs" / "title" / y / m / f"{day}.csv"
    title = read_csv(title_path) if title_path.exists() else pd.DataFrame(); weather_by_race = current_weather_map(src, y, m, day)

    basic = maybe_read(ddir / "racer_basic.csv"); course = maybe_read(ddir / "racer_course.csv"); trends = maybe_read(ddir / "racer_trends.csv"); traits = maybe_read(ddir / "racer_traits.csv")
    adjusted = maybe_read(ddir / "racer_adjusted.csv"); conditions = maybe_read(ddir / "racer_condition_adjustments.csv"); globals_df = maybe_read(ddir / "model_global_adjustments.csv"); validation = maybe_read(ddir / "model_validation.csv")
    for df in [basic, course, trends, traits, adjusted, conditions]:
        if not df.empty and "regno" in df.columns: df["regno"] = pd.to_numeric(df["regno"], errors="coerce").astype("Int64")
    gm, cm, motor_slope = make_maps(globals_df, conditions)

    x = cl.copy(); x["regno"] = pd.to_numeric(x["regno"], errors="coerce").astype("Int64"); x["expected_course"] = x["boat_no"].astype(int)
    if not basic.empty:
        cols = [c for c in ["regno","all_top3_rate","all_avg_st","all_st_top_rate","recent5_top3_rate","recent10_top3_rate","recent20_top3_rate","recent20_avg_st","recent20_course_adj_perf"] if c in basic.columns]
        x = x.merge(basic[cols], on="regno", how="left")
    if not course.empty:
        course["course"] = pd.to_numeric(course["course"], errors="coerce").astype("Int64")
        cols = [c for c in ["regno","course","n","win1_rate","top2_rate","top3_rate","avg_finish","avg_st","st_sd","st_top_rate","st_0x_rate","course_adj_perf"] if c in course.columns]
        c = course[cols].rename(columns={"n":"course_n","win1_rate":"course_win1_rate","top2_rate":"course_top2_rate","top3_rate":"course_top3_rate","avg_finish":"course_avg_finish","avg_st":"course_avg_st","st_sd":"course_st_sd","st_top_rate":"course_st_top_rate","st_0x_rate":"course_st_0x_rate","course_adj_perf":"course_adj_perf_history"})
        x = x.merge(c, left_on=["regno","expected_course"], right_on=["regno","course"], how="left")
    if not trends.empty:
        cols = [c for c in ["regno","trend_candidate","course_adj_perf_change","top3_rate_change_pt","avg_st_change_sec","avg_finish_change","recent_n","baseline_n"] if c in trends.columns]
        x = x.merge(trends[cols], on="regno", how="left")
    if not traits.empty:
        cols = [c for c in ["regno","strong_field_n","strong_field_top3_rate","strong_field_course_adj_perf","weak_field_n","weak_field_top3_rate","weak_field_course_adj_perf","good_motor_n","good_motor_top3_rate","bad_motor_n","bad_motor_top3_rate","motor_dependency_top3_delta_pt","second_run_n","second_run_top3_rate","first_run_top3_rate","after_good_n","after_good_top3_rate","after_bad_n","after_bad_top3_rate"] if c in traits.columns]
        x = x.merge(traits[cols], on="regno", how="left")
    if not adjusted.empty:
        cols = [c for c in ["regno","sample_n","raw_points","ability_adjustment","base_winrate","form_n","form_raw","form_adjustment","current_winrate","rating_quality"] if c in adjusted.columns]
        x = x.merge(adjusted[cols], on="regno", how="left")

    meta = {}
    if not title.empty and "レースコード" in title.columns:
        for _, r in title.iterrows():
            code = text(r.get("レースコード"))
            if code: meta[str(code)] = {"venue": text(r.get("レース場")), "day_label": text(r.get("日次")), "grade": text(r.get("グレード")), "race_name": text(r.get("レース名")), "event_title": text(r.get("タイトル")), "deadline": text(r.get("電話投票締切予定"))}

    raw_cards = {}
    if "レースコード" in cards.columns:
        for _, r in cards.iterrows():
            code = text(r.get("レースコード"))
            if code: raw_cards[str(code)] = r

    venues = {}
    for race_code, g in x.groupby("レースコード", sort=True):
        g = g.sort_values("boat_no"); code_s = str(race_code)
        venue_code = str(g["レース場コード"].iloc[0]).zfill(2) if "レース場コード" in g.columns else code_s[8:10]
        race_no_raw = text(g["レース回"].iloc[0]) if "レース回" in g.columns else code_s[10:12]
        race_no = intval("".join(ch for ch in str(race_no_raw) if ch.isdigit())) or int(code_s[10:12])
        rm = meta.get(code_s, {}); venue_name = rm.get("venue") or VENUES.get(venue_code, venue_code); card_row = raw_cards.get(code_s)

        entries = []
        for _, r in g.iterrows():
            boat = intval(r.get("boat_no")); eruns = event_runs(card_row, boat) if boat else []
            numeric_finishes = [intval(z.get("finish")) for z in eruns]; numeric_finishes = [z for z in numeric_finishes if z is not None]
            normal_st = [num(z.get("st")) for z in eruns]; normal_st = [z for z in normal_st if z is not None and z >= 0]
            entries.append(clean({
                "boat_no": boat, "regno": intval(r.get("regno")), "name": text(r.get("name")), "class_grade": text(r.get("class_grade")), "f_count": intval(r.get("f_count")), "l_count": intval(r.get("l_count")),
                "pub_avg_st": num(r.get("pub_avg_st")), "national_win_rate": num(r.get("national_win_rate")), "national_2rate": num(r.get("national_2rate")), "national_3rate": num(r.get("national_3rate")),
                "local_win_rate": num(r.get("local_win_rate")), "local_2rate": num(r.get("local_2rate")), "local_3rate": num(r.get("local_3rate")), "motor_no": intval(r.get("motor_no")), "motor_2rate": num(r.get("motor_2rate")), "motor_3rate": num(r.get("motor_3rate")),
                "boat_no_assigned": intval(r.get("boat_no_assigned")), "boat_2rate": num(r.get("boat_2rate")), "boat_3rate": num(r.get("boat_3rate")), "course_n": intval(r.get("course_n")), "course_win1_rate": num(r.get("course_win1_rate")), "course_top2_rate": num(r.get("course_top2_rate")), "course_top3_rate": num(r.get("course_top3_rate")), "course_avg_finish": num(r.get("course_avg_finish")), "course_avg_st": num(r.get("course_avg_st")), "course_st_sd": num(r.get("course_st_sd")), "course_st_top_rate": num(r.get("course_st_top_rate")), "course_st_0x_rate": num(r.get("course_st_0x_rate")),
                "all_top3_rate": num(r.get("all_top3_rate")), "all_avg_st": num(r.get("all_avg_st")), "recent5_top3_rate": num(r.get("recent5_top3_rate")), "recent10_top3_rate": num(r.get("recent10_top3_rate")), "recent20_top3_rate": num(r.get("recent20_top3_rate")), "recent20_avg_st": num(r.get("recent20_avg_st")),
                "trend": text(r.get("trend_candidate")), "trend_top3_delta": num(r.get("top3_rate_change_pt")), "trend_st_delta": num(r.get("avg_st_change_sec")), "trend_perf_delta": num(r.get("course_adj_perf_change")), "strong_field_n": intval(r.get("strong_field_n")), "strong_field_top3_rate": num(r.get("strong_field_top3_rate")), "strong_field_perf": num(r.get("strong_field_course_adj_perf")), "weak_field_n": intval(r.get("weak_field_n")), "weak_field_top3_rate": num(r.get("weak_field_top3_rate")), "motor_dependency_delta": num(r.get("motor_dependency_top3_delta_pt")), "bad_motor_n": intval(r.get("bad_motor_n")), "bad_motor_top3_rate": num(r.get("bad_motor_top3_rate")), "second_run_n": intval(r.get("second_run_n")), "second_run_top3_rate": num(r.get("second_run_top3_rate")), "first_run_top3_rate": num(r.get("first_run_top3_rate")),
                "rating_sample_n": intval(r.get("sample_n")), "raw_points": num(r.get("raw_points")), "base_winrate": num(r.get("base_winrate")), "form_n": intval(r.get("form_n")), "form_adjustment": num(r.get("form_adjustment")), "current_winrate": num(r.get("current_winrate")), "rating_quality": num(r.get("rating_quality")),
                "event_runs": eruns, "event_n": len(eruns), "event_avg_st": round(float(np.mean(normal_st)), 4) if normal_st else None, "event_avg_finish": round(float(np.mean(numeric_finishes)), 3) if numeric_finishes else None,
            }))

        weather = weather_by_race.get(code_s, {})
        add_today_adjustments(entries, venue_code, venue_name, rm.get("grade"), rm.get("event_title"), weather, gm, cm, motor_slope)
        race = {"race_code": code_s, "race_no": race_no, "race_name": rm.get("race_name"), "grade": rm.get("grade"), "grade_normalized": normalize_grade(rm.get("grade")), "series": series_label(rm.get("event_title"), rm.get("race_name")), "day_label": rm.get("day_label"), "event_title": rm.get("event_title"), "deadline": rm.get("deadline"), "weather": weather, "entries": entries}
        venues.setdefault(venue_code, {"venue_code": venue_code, "venue": venue_name, "races": []})["races"].append(race)

    payload = {"race_date": race_date, "source_card": str(card_file.relative_to(src)), "model": {"name": "opponent-adjusted-winrate-v1", "neutral_winrate": round(NEUTRAL_WINRATE, 4), "sample_rule": "少数標本・期間で再現しない個別条件は当日補正に不使用"}, "venues": sorted(venues.values(), key=lambda v: v["venue_code"])}
    if not validation.empty and {"metric", "value"}.issubset(validation.columns): payload["model"]["validation"] = {str(r["metric"]): num(r["value"]) for _, r in validation.iterrows() if text(r.get("metric"))}
    for v in payload["venues"]: v["races"] = sorted(v["races"], key=lambda r: r["race_no"])
    with (data_dir / "today.json").open("w", encoding="utf-8") as f: json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    print(f"mobile feed: date={race_date} venues={len(payload['venues'])} races={sum(len(v['races']) for v in payload['venues'])} model={payload['model']['name']}")


if __name__ == "__main__":
    main()
