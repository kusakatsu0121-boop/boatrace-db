#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from racer_directory import cards_to_long


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="source/data")
    ap.add_argument("--directory", default="artifacts/racer_directory")
    ap.add_argument("--site", default="site")
    args = ap.parse_args()

    src = Path(args.source)
    ddir = Path(args.directory)
    site = Path(args.site)
    data_dir = site / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    card_file = latest_file(src / "programs" / "race_cards")
    cards = read_csv(card_file)
    cl = cards_to_long(cards)
    if cl.empty:
        raise SystemExit("latest race card is empty")

    race_date = text(cl["レース日"].dropna().iloc[0]) if "レース日" in cl.columns else card_file.stem
    y, m, day = race_date.split("-")
    title_path = src / "programs" / "title" / y / m / f"{day}.csv"
    title = read_csv(title_path) if title_path.exists() else pd.DataFrame()

    basic = maybe_read(ddir / "racer_basic.csv")
    course = maybe_read(ddir / "racer_course.csv")
    trends = maybe_read(ddir / "racer_trends.csv")
    traits = maybe_read(ddir / "racer_traits.csv")

    for df in [basic, course, trends, traits]:
        if not df.empty and "regno" in df.columns:
            df["regno"] = pd.to_numeric(df["regno"], errors="coerce").astype("Int64")

    x = cl.copy()
    x["regno"] = pd.to_numeric(x["regno"], errors="coerce").astype("Int64")
    x["expected_course"] = x["boat_no"].astype(int)

    if not basic.empty:
        cols = [c for c in [
            "regno","all_top3_rate","all_avg_st","all_st_top_rate",
            "recent5_top3_rate","recent10_top3_rate","recent20_top3_rate",
            "recent20_avg_st","recent20_course_adj_perf"
        ] if c in basic.columns]
        x = x.merge(basic[cols], on="regno", how="left")

    if not course.empty:
        course["course"] = pd.to_numeric(course["course"], errors="coerce").astype("Int64")
        cols = [c for c in [
            "regno","course","n","win1_rate","top3_rate","avg_st","st_sd","st_top_rate","course_adj_perf"
        ] if c in course.columns]
        c = course[cols].rename(columns={
            "n":"course_n","win1_rate":"course_win1_rate","top3_rate":"course_top3_rate",
            "avg_st":"course_avg_st","st_sd":"course_st_sd","st_top_rate":"course_st_top_rate",
            "course_adj_perf":"course_adj_perf_history"
        })
        x = x.merge(c, left_on=["regno","expected_course"], right_on=["regno","course"], how="left")

    if not trends.empty:
        cols = [c for c in [
            "regno","trend_candidate","course_adj_perf_change","top3_rate_change_pt",
            "avg_st_change_sec","avg_finish_change","recent_n","baseline_n"
        ] if c in trends.columns]
        x = x.merge(trends[cols], on="regno", how="left")

    if not traits.empty:
        cols = [c for c in [
            "regno","strong_field_n","strong_field_top3_rate","strong_field_course_adj_perf",
            "weak_field_n","weak_field_top3_rate","weak_field_course_adj_perf",
            "good_motor_n","good_motor_top3_rate","bad_motor_n","bad_motor_top3_rate",
            "motor_dependency_top3_delta_pt","second_run_n","second_run_top3_rate",
            "first_run_top3_rate","after_good_n","after_good_top3_rate","after_bad_n","after_bad_top3_rate"
        ] if c in traits.columns]
        x = x.merge(traits[cols], on="regno", how="left")

    meta = {}
    if not title.empty and "レースコード" in title.columns:
        for _, r in title.iterrows():
            code = text(r.get("レースコード"))
            if not code:
                continue
            meta[code] = {
                "venue": text(r.get("レース場")),
                "day_label": text(r.get("日次")),
                "grade": text(r.get("グレード")),
                "race_name": text(r.get("レース名")),
                "event_title": text(r.get("タイトル")),
                "deadline": text(r.get("電話投票締切予定")),
            }

    venues = {}
    for race_code, g in x.groupby("レースコード", sort=True):
        g = g.sort_values("boat_no")
        venue_code = str(g["レース場コード"].iloc[0]).zfill(2) if "レース場コード" in g.columns else str(race_code)[8:10]
        race_no_raw = text(g["レース回"].iloc[0]) if "レース回" in g.columns else str(race_code)[10:12]
        race_no = intval("".join(ch for ch in str(race_no_raw) if ch.isdigit())) or int(str(race_code)[10:12])
        rm = meta.get(str(race_code), {})
        venue_name = rm.get("venue") or VENUES.get(venue_code, venue_code)

        entries = []
        for _, r in g.iterrows():
            entries.append(clean({
                "boat_no": intval(r.get("boat_no")),
                "regno": intval(r.get("regno")),
                "name": text(r.get("name")),
                "class_grade": text(r.get("class_grade")),
                "f_count": intval(r.get("f_count")),
                "l_count": intval(r.get("l_count")),
                "pub_avg_st": num(r.get("pub_avg_st")),
                "national_win_rate": num(r.get("national_win_rate")),
                "national_3rate": num(r.get("national_3rate")),
                "local_win_rate": num(r.get("local_win_rate")),
                "local_3rate": num(r.get("local_3rate")),
                "motor_no": intval(r.get("motor_no")),
                "motor_2rate": num(r.get("motor_2rate")),
                "motor_3rate": num(r.get("motor_3rate")),
                "course_n": intval(r.get("course_n")),
                "course_win1_rate": num(r.get("course_win1_rate")),
                "course_top3_rate": num(r.get("course_top3_rate")),
                "course_avg_st": num(r.get("course_avg_st")),
                "course_st_sd": num(r.get("course_st_sd")),
                "course_st_top_rate": num(r.get("course_st_top_rate")),
                "all_top3_rate": num(r.get("all_top3_rate")),
                "all_avg_st": num(r.get("all_avg_st")),
                "recent5_top3_rate": num(r.get("recent5_top3_rate")),
                "recent10_top3_rate": num(r.get("recent10_top3_rate")),
                "recent20_top3_rate": num(r.get("recent20_top3_rate")),
                "recent20_avg_st": num(r.get("recent20_avg_st")),
                "trend": text(r.get("trend_candidate")),
                "trend_top3_delta": num(r.get("top3_rate_change_pt")),
                "trend_st_delta": num(r.get("avg_st_change_sec")),
                "trend_perf_delta": num(r.get("course_adj_perf_change")),
                "strong_field_n": intval(r.get("strong_field_n")),
                "strong_field_top3_rate": num(r.get("strong_field_top3_rate")),
                "strong_field_perf": num(r.get("strong_field_course_adj_perf")),
                "weak_field_n": intval(r.get("weak_field_n")),
                "weak_field_top3_rate": num(r.get("weak_field_top3_rate")),
                "motor_dependency_delta": num(r.get("motor_dependency_top3_delta_pt")),
                "bad_motor_n": intval(r.get("bad_motor_n")),
                "bad_motor_top3_rate": num(r.get("bad_motor_top3_rate")),
                "second_run_n": intval(r.get("second_run_n")),
                "second_run_top3_rate": num(r.get("second_run_top3_rate")),
                "first_run_top3_rate": num(r.get("first_run_top3_rate")),
            }))

        race = {
            "race_code": str(race_code),
            "race_no": race_no,
            "race_name": rm.get("race_name"),
            "grade": rm.get("grade"),
            "day_label": rm.get("day_label"),
            "event_title": rm.get("event_title"),
            "deadline": rm.get("deadline"),
            "entries": entries,
        }
        venues.setdefault(venue_code, {"venue_code": venue_code, "venue": venue_name, "races": []})["races"].append(race)

    payload = {
        "race_date": race_date,
        "source_card": str(card_file.relative_to(src)),
        "venues": sorted(venues.values(), key=lambda v: v["venue_code"]),
    }
    for v in payload["venues"]:
        v["races"] = sorted(v["races"], key=lambda r: r["race_no"])

    with (data_dir / "today.json").open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    print(f"mobile feed: date={race_date} venues={len(payload['venues'])} races={sum(len(v['races']) for v in payload['venues'])}")


if __name__ == "__main__":
    main()
