#!/usr/bin/env python3
from __future__ import annotations

import argparse
import glob
import itertools
import re
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd


def load_many(pattern: str) -> pd.DataFrame:
    files = sorted(glob.glob(pattern))
    if not files:
        return pd.DataFrame()
    frames = []
    for f in files:
        try:
            frames.append(pd.read_csv(f, dtype=str, low_memory=False))
        except Exception as e:
            print(f"SKIP {f}: {e}")
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def to_num(s):
    return pd.to_numeric(s, errors="coerce")


def parse_dayno(v):
    s = str(v or "")
    trans = str.maketrans("１２３４５６７", "1234567")
    s = s.translate(trans)
    m = re.search(r"([1-7])", s)
    return float(m.group(1)) if m else np.nan


def wind_band(v):
    try:
        x = float(v)
    except Exception:
        return "不明"
    if x < 2:
        return "0-1m"
    if x < 4:
        return "2-3m"
    if x < 6:
        return "4-5m"
    return "6m+"


def wave_band(v):
    try:
        x = float(v)
    except Exception:
        return "不明"
    if x <= 2:
        return "0-2cm"
    if x <= 5:
        return "3-5cm"
    if x <= 10:
        return "6-10cm"
    return "11cm+"


def cards_to_long(cards: pd.DataFrame) -> pd.DataFrame:
    out = []
    meta = [c for c in ["レースコード", "レース日", "レース場コード", "レース回"] if c in cards.columns]
    fields = {
        "登録番号": "regno", "選手名": "name", "期別": "term", "支部": "branch", "出身地": "birthplace",
        "年齢": "age", "級別": "class_grade", "賞除": "prize_exclusion", "F本数": "f_count", "L本数": "l_count",
        "全国平均ST": "pub_avg_st", "全国勝率": "national_win_rate", "全国2連対率": "national_2rate",
        "全国3連対率": "national_3rate", "当地勝率": "local_win_rate", "当地2連対率": "local_2rate",
        "当地3連対率": "local_3rate", "モーター番号": "motor_no", "モーター2連対率": "motor_2rate",
        "モーター3連対率": "motor_3rate", "ボート番号": "boat_no_assigned", "ボート2連対率": "boat_2rate",
        "ボート3連対率": "boat_3rate", "早見": "hayami",
    }
    for boat in range(1, 7):
        cols = list(meta)
        ren = {}
        for jp, en in fields.items():
            col = f"艇{boat}_{jp}"
            if col in cards.columns:
                cols.append(col)
                ren[col] = en
        p = cards[cols].copy().rename(columns=ren)
        p["boat_no"] = boat
        out.append(p)
    x = pd.concat(out, ignore_index=True)
    x["regno"] = to_num(x.get("regno"))
    x = x.dropna(subset=["regno"])
    x["regno"] = x["regno"].astype(int)
    for c in ["age", "f_count", "l_count", "pub_avg_st", "national_win_rate", "national_2rate", "national_3rate",
              "local_win_rate", "local_2rate", "local_3rate", "motor_no", "motor_2rate", "motor_3rate",
              "boat_no_assigned", "boat_2rate", "boat_3rate"]:
        if c in x.columns:
            x[c] = to_num(x[c])
    return x


def results_to_long(res: pd.DataFrame) -> pd.DataFrame:
    if res.empty:
        return res
    race_meta_cols = [c for c in ["レースコード", "レース日", "レース場", "レース回", "決まり手", "天候", "風向",
                                         "風速(m)", "波の高さ(cm)", "気温(℃)", "水温(℃)", "締切時刻"] if c in res.columns]
    race_meta = res[race_meta_cols].drop_duplicates("レースコード")
    finish_parts = []
    for rank in range(1, 7):
        bcol = f"{rank}着_艇番"; ncol = f"{rank}着_選手名"
        if bcol not in res.columns:
            continue
        cols = ["レースコード", bcol] + ([ncol] if ncol in res.columns else [])
        p = res[cols].copy().rename(columns={bcol: "boat_no", ncol: "result_name"})
        p["finish"] = rank
        finish_parts.append(p)
    finish = pd.concat(finish_parts, ignore_index=True)
    finish["boat_no"] = to_num(finish["boat_no"])
    finish = finish.dropna(subset=["boat_no"]); finish["boat_no"] = finish["boat_no"].astype(int)
    course_parts = []
    for course in range(1, 7):
        bcol = f"{course}コース_艇番"; scol = f"{course}コース_スタートタイミング"; fcol = f"{course}コース_F"
        if bcol not in res.columns:
            continue
        cols = ["レースコード", bcol] + ([scol] if scol in res.columns else []) + ([fcol] if fcol in res.columns else [])
        p = res[cols].copy().rename(columns={bcol: "boat_no", scol: "actual_st", fcol: "f_marker"})
        p["actual_course"] = course
        course_parts.append(p)
    course = pd.concat(course_parts, ignore_index=True)
    course["boat_no"] = to_num(course["boat_no"])
    course = course.dropna(subset=["boat_no"]); course["boat_no"] = course["boat_no"].astype(int)
    course["actual_st"] = to_num(course.get("actual_st"))
    course["f_start"] = course.get("f_marker", pd.Series("", index=course.index)).fillna("").astype(str).str.contains("F|Ｆ", regex=True).astype(int)
    x = finish.merge(course[["レースコード", "boat_no", "actual_course", "actual_st", "f_start"]], on=["レースコード", "boat_no"], how="left")
    x = x.merge(race_meta, on="レースコード", how="left")
    for c in ["風速(m)", "波の高さ(cm)", "気温(℃)", "水温(℃)"]:
        if c in x.columns:
            x[c] = to_num(x[c])
    return x


def build_panel(cards_long: pd.DataFrame, res_long: pd.DataFrame, title: pd.DataFrame) -> pd.DataFrame:
    c = cards_long.drop_duplicates(["レースコード", "boat_no"], keep="last")
    p = res_long.merge(c, on=["レースコード", "boat_no"], how="left", suffixes=("", "_card"))
    p = p.dropna(subset=["regno"]).copy(); p["regno"] = p["regno"].astype(int)
    p["race_date"] = pd.to_datetime(p.get("レース日"), errors="coerce")
    p["race_no_num"] = to_num(p.get("レース回").astype(str).str.extract(r"(\d+)")[0]) if "レース回" in p else np.nan
    if not title.empty and "レースコード" in title.columns:
        tcols = [c for c in ["レースコード", "日次", "グレード", "レース名", "タイトル", "ナイター"] if c in title.columns]
        p = p.merge(title[tcols].drop_duplicates("レースコード"), on="レースコード", how="left")
        if "日次" in p.columns: p["day_no"] = p["日次"].map(parse_dayno)
    if "風速(m)" in p.columns: p["wind_band"] = p["風速(m)"].map(wind_band)
    if "波の高さ(cm)" in p.columns: p["wave_band"] = p["波の高さ(cm)"].map(wave_band)
    if "national_win_rate" in p.columns:
        p["national_win_rate"] = to_num(p["national_win_rate"])
        total = p.groupby("レースコード")["national_win_rate"].transform("sum")
        count = p.groupby("レースコード")["national_win_rate"].transform("count")
        p["opponent_strength"] = (total - p["national_win_rate"]) / (count - 1).replace(0, np.nan)
    cb = p.groupby("actual_course")["finish"].mean()
    p["course_expected_finish"] = p["actual_course"].map(cb)
    p["course_adjusted_perf"] = p["course_expected_finish"] - p["finish"]
    normal_st = p["actual_st"].where(p["f_start"].fillna(0).eq(0))
    p["st_rank"] = normal_st.groupby(p["レースコード"]).rank(method="min", ascending=True)
    p["st_top"] = (p["st_rank"] == 1).astype(float)
    return p


def latest_profile(cards_long: pd.DataFrame) -> pd.DataFrame:
    x = cards_long.copy(); x["profile_date"] = pd.to_datetime(x.get("レース日"), errors="coerce")
    x = x.sort_values(["regno", "profile_date"]).groupby("regno", as_index=False).tail(1)
    keep = ["regno", "name", "term", "branch", "birthplace", "age", "class_grade", "prize_exclusion", "f_count", "l_count",
            "pub_avg_st", "national_win_rate", "national_2rate", "national_3rate", "local_win_rate", "local_2rate", "local_3rate", "profile_date"]
    return x[[c for c in keep if c in x.columns]].reset_index(drop=True)


def agg_perf(g: pd.DataFrame) -> dict:
    normal = g[g["f_start"].fillna(0).eq(0)]
    return {"n": int(len(g)), "win1_rate": (g["finish"] == 1).mean() * 100, "top2_rate": (g["finish"] <= 2).mean() * 100,
            "top3_rate": (g["finish"] <= 3).mean() * 100, "avg_finish": g["finish"].mean(), "avg_st": normal["actual_st"].mean(),
            "st_sd": normal["actual_st"].std(ddof=0), "st_top_rate": normal["st_top"].mean() * 100,
            "course_adj_perf": g["course_adjusted_perf"].mean()}


def basic_table(profile, p):
    rows = []; p = p.sort_values(["regno", "race_date", "race_no_num", "レースコード"])
    for reg, g in p.groupby("regno"):
        row = {"regno": reg}; row.update({f"all_{k}": v for k, v in agg_perf(g).items()})
        for n in [5, 10, 20, 40, 80]: row.update({f"recent{n}_{k}": v for k, v in agg_perf(g.tail(n)).items()})
        rows.append(row)
    return profile.merge(pd.DataFrame(rows), on="regno", how="left")


def course_table(p):
    rows = []
    for (reg, course), g in p.dropna(subset=["actual_course"]).groupby(["regno", "actual_course"]):
        row = {"regno": reg, "course": int(course)}; row.update(agg_perf(g))
        normal = g[g["f_start"].fillna(0).eq(0)]
        row["st_0x_rate"] = ((normal["actual_st"] >= 0) & (normal["actual_st"] < 0.10)).mean() * 100 if len(normal) else np.nan
        rows.append(row)
    return pd.DataFrame(rows)


def condition_table(p):
    rows = []; specs = [("F本数", "f_count"), ("場", "レース場"), ("節日次", "day_no"), ("レース区分", "レース名"),
                        ("グレード", "グレード"), ("天候", "天候"), ("風向", "風向"), ("風速帯", "wind_band"), ("波高帯", "wave_band")]
    for reg, g in p.groupby("regno"):
        for label, col in specs:
            if col not in g.columns: continue
            for val, h in g.dropna(subset=[col]).groupby(col):
                row = {"regno": reg, "condition_type": label, "condition_value": str(val)}; row.update(agg_perf(h)); rows.append(row)
    return pd.DataFrame(rows)


def kimarite_table(p):
    if "決まり手" not in p.columns: return pd.DataFrame()
    rows = []
    for (reg, course, method), g in p[(p["finish"] == 1) & p["決まり手"].notna()].groupby(["regno", "actual_course", "決まり手"]):
        rows.append({"regno": reg, "course": int(course), "winning_method": str(method), "wins": len(g)})
    return pd.DataFrame(rows)


def trend_table(p):
    rows = []; p = p.sort_values(["regno", "race_date", "race_no_num", "レースコード"])
    for reg, g in p.groupby("regno"):
        if len(g) < 12: continue
        recent = g.tail(20); base = g.iloc[max(0, len(g)-60):max(0, len(g)-20)]
        if len(base) < 8: base = g.iloc[:-20]
        if len(base) == 0: continue
        r, b = agg_perf(recent), agg_perf(base); cad = r["course_adj_perf"] - b["course_adj_perf"]; t3 = r["top3_rate"] - b["top3_rate"]
        rows.append({"regno": reg, "recent_n": len(recent), "baseline_n": len(base), "course_adj_perf_change": cad,
                     "top3_rate_change_pt": t3, "avg_st_change_sec": r["avg_st"] - b["avg_st"], "avg_finish_change": r["avg_finish"] - b["avg_finish"],
                     "trend_candidate": "上向き" if cad > 0.20 and t3 > 3 else ("下向き" if cad < -0.20 and t3 < -3 else "横ばい/不明")})
    return pd.DataFrame(rows)


def traits_table(p):
    rows = []; oq75 = p["opponent_strength"].quantile(.75); oq25 = p["opponent_strength"].quantile(.25)
    mq75 = p["motor_2rate"].quantile(.75); mq25 = p["motor_2rate"].quantile(.25)
    p = p.sort_values(["regno", "race_date", "race_no_num", "レースコード"]).copy()
    p["prev_finish"] = p.groupby("regno")["finish"].shift(1); p["day_run_no"] = p.groupby(["regno", "race_date"]).cumcount() + 1
    for reg, g in p.groupby("regno"):
        row = {"regno": reg, "n": len(g)}; hard = g[g["opponent_strength"] >= oq75]; easy = g[g["opponent_strength"] <= oq25]
        row.update({"strong_field_n": len(hard), "strong_field_top3_rate": (hard["finish"] <= 3).mean()*100 if len(hard) else np.nan,
                    "strong_field_course_adj_perf": hard["course_adjusted_perf"].mean(), "weak_field_n": len(easy),
                    "weak_field_top3_rate": (easy["finish"] <= 3).mean()*100 if len(easy) else np.nan, "weak_field_course_adj_perf": easy["course_adjusted_perf"].mean()})
        goodm = g[g["motor_2rate"] >= mq75]; badm = g[g["motor_2rate"] <= mq25]
        row.update({"good_motor_n": len(goodm), "good_motor_top3_rate": (goodm["finish"] <= 3).mean()*100 if len(goodm) else np.nan,
                    "bad_motor_n": len(badm), "bad_motor_top3_rate": (badm["finish"] <= 3).mean()*100 if len(badm) else np.nan})
        if len(goodm) and len(badm): row["motor_dependency_top3_delta_pt"] = row["good_motor_top3_rate"] - row["bad_motor_top3_rate"]
        second = g[g["day_run_no"] == 2]; first = g[g["day_run_no"] == 1]
        row.update({"second_run_n": len(second), "second_run_top3_rate": (second["finish"] <= 3).mean()*100 if len(second) else np.nan,
                    "first_run_top3_rate": (first["finish"] <= 3).mean()*100 if len(first) else np.nan})
        after_good = g[g["prev_finish"] <= 3]; after_bad = g[g["prev_finish"] > 3]
        row.update({"after_good_n": len(after_good), "after_good_top3_rate": (after_good["finish"] <= 3).mean()*100 if len(after_good) else np.nan,
                    "after_bad_n": len(after_bad), "after_bad_top3_rate": (after_bad["finish"] <= 3).mean()*100 if len(after_bad) else np.nan})
        rows.append(row)
    return pd.DataFrame(rows)


def pair_table(p, min_races=10):
    acc = {}
    for _, g in p[["レースコード", "regno", "finish"]].groupby("レースコード"):
        for a, b in itertools.combinations(g.to_dict("records"), 2):
            ra, rb = sorted([int(a["regno"]), int(b["regno"])]); key = (ra, rb)
            x, y = (a, b) if int(a["regno"]) == ra else (b, a)
            z = acc.setdefault(key, [0, 0, 0, 0.0, 0.0]); z[0] += 1; z[1] += int(x["finish"] <= 3); z[2] += int(y["finish"] <= 3); z[3] += x["finish"]; z[4] += y["finish"]
    return pd.DataFrame([{"regno_a": a, "regno_b": b, "races": z[0], "a_top3_rate": z[1]/z[0]*100, "b_top3_rate": z[2]/z[0]*100,
                          "a_avg_finish": z[3]/z[0], "b_avg_finish": z[4]/z[0]} for (a,b),z in acc.items() if z[0] >= min_races])


def market_table(p, payouts):
    if payouts.empty or "3連単_人気" not in payouts.columns: return pd.DataFrame()
    pay = payouts[["レースコード", "3連単_人気", "3連単_払戻金"]].copy(); pay["pop"] = to_num(pay["3連単_人気"]); pay["pay"] = to_num(pay["3連単_払戻金"])
    q = p.merge(pay[["レースコード", "pop", "pay"]], on="レースコード")[lambda d: d.finish <= 3]
    rows = []
    for reg, g in q.groupby("regno"):
        rows.append({"regno": reg, "top3_involvement_n": len(g), "avg_result_popularity_when_top3": g["pop"].mean(),
                     "popularity_61plus_rate": (g["pop"] >= 61).mean()*100, "popularity_101plus_rate": (g["pop"] >= 101).mean()*100,
                     "avg_trifecta_payout_when_top3": g["pay"].mean()})
    return pd.DataFrame(rows)


def write_all(out, tables, sqlite_path):
    out.mkdir(parents=True, exist_ok=True)
    for name, df in tables.items(): df.to_csv(out / f"{name}.csv", index=False); print(name, len(df))
    con = sqlite3.connect(sqlite_path)
    try:
        for name, df in tables.items():
            if not df.empty: df.to_sql(name, con, if_exists="replace", index=False)
    finally: con.close()


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--source", default="source/data"); ap.add_argument("--out", default="artifacts/racer_directory"); ap.add_argument("--sqlite", default="artifacts/boatrace.sqlite"); ap.add_argument("--pair-min-races", type=int, default=10); args = ap.parse_args()
    src = Path(args.source); cards = load_many(str(src/"programs/race_cards/*/*/*.csv")); results = load_many(str(src/"results/realtime/*/*/*.csv")); title = load_many(str(src/"programs/title/*/*/*.csv")); payouts = load_many(str(src/"results/payouts/*/*/*.csv"))
    if cards.empty or results.empty: raise SystemExit("required race_cards/results not found")
    cl = cards_to_long(cards); p = build_panel(cl, results_to_long(results), title)
    tables = {"racer_basic": basic_table(latest_profile(cl), p), "racer_course": course_table(p), "racer_condition": condition_table(p),
              "racer_kimarite": kimarite_table(p), "racer_trends": trend_table(p), "racer_traits": traits_table(p),
              "racer_pair_interactions": pair_table(p, args.pair_min_races), "racer_market_involvement": market_table(p, payouts)}
    write_all(Path(args.out), tables, Path(args.sqlite)); print(f"panel={len(p)} racers={p.regno.nunique()} races={p['レースコード'].nunique()}")


if __name__ == "__main__": main()
