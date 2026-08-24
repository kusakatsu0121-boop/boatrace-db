import csv
import sqlite3
from pathlib import Path
import sys

SRC = Path(sys.argv[1] if len(sys.argv) > 1 else "source/data/results/realtime")
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else "artifacts/boatrace.sqlite")
OUT.parent.mkdir(parents=True, exist_ok=True)

con = sqlite3.connect(OUT)
cur = con.cursor()
cur.executescript('''
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS races(
  race_code TEXT PRIMARY KEY,
  race_date TEXT,
  venue_code TEXT,
  race_no INTEGER,
  deadline_time TEXT,
  winning_method TEXT,
  weather TEXT,
  wind_direction TEXT,
  wind_speed REAL,
  wave_height REAL,
  air_temp REAL,
  water_temp REAL
);
CREATE TABLE IF NOT EXISTS entries(
  race_code TEXT NOT NULL,
  boat_no INTEGER NOT NULL,
  racer_name TEXT,
  actual_course INTEGER,
  actual_st REAL,
  finish_order INTEGER,
  f_start INTEGER DEFAULT 0,
  PRIMARY KEY(race_code, boat_no)
);
CREATE INDEX IF NOT EXISTS idx_entries_course ON entries(actual_course);
CREATE INDEX IF NOT EXISTS idx_entries_racer ON entries(racer_name);
CREATE INDEX IF NOT EXISTS idx_entries_finish ON entries(finish_order);
''')

def num(v, integer=False):
    if v in (None, ''): return None
    try:
        return int(float(v)) if integer else float(v)
    except Exception:
        return None

def norm(s):
    return (s or '').replace('　', ' ').strip()

files = sorted(SRC.rglob('*.csv'))
loaded = 0
skipped = 0
for fp in files:
    try:
        with fp.open(encoding='utf-8-sig', newline='') as f:
            for row in csv.DictReader(f):
                code = row.get('レースコード')
                if not code:
                    continue
                race_no = ''.join(ch for ch in (row.get('レース回') or '') if ch.isdigit())
                cur.execute('''INSERT OR REPLACE INTO races
                  (race_code,race_date,venue_code,race_no,deadline_time,winning_method,weather,wind_direction,wind_speed,wave_height,air_temp,water_temp)
                  VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''',(
                    code,row.get('レース日'),str(row.get('レース場') or code[8:10]).zfill(2),
                    int(race_no) if race_no else int(code[10:12]),row.get('締切時刻'),norm(row.get('決まり手')),
                    row.get('天候'),row.get('風向'),num(row.get('風速(m)')),num(row.get('波の高さ(cm)')),
                    num(row.get('気温(℃)')),num(row.get('水温(℃)'))))

                finish = {}
                names = {}
                for k in range(1,7):
                    b = num(row.get(f'{k}着_艇番'), True)
                    if b:
                        finish[b] = k
                        names[b] = norm(row.get(f'{k}着_選手名'))
                course = {}
                st = {}
                fs = {}
                for c in range(1,7):
                    b = num(row.get(f'{c}コース_艇番'), True)
                    if b:
                        course[b] = c
                        st[b] = num(row.get(f'{c}コース_スタートタイミング'))
                        fs[b] = 1 if (row.get(f'{c}コース_F') or '').strip() else 0
                for b, fin in finish.items():
                    cur.execute('''INSERT OR REPLACE INTO entries
                      (race_code,boat_no,racer_name,actual_course,actual_st,finish_order,f_start)
                      VALUES(?,?,?,?,?,?,?)''',
                      (code,b,names.get(b),course.get(b),st.get(b),fin,fs.get(b,0)))
                loaded += 1
        con.commit()
    except Exception as e:
        skipped += 1
        print('SKIP', fp, e)

cur.executescript('''
DROP TABLE IF EXISTS course_baseline;
CREATE TABLE course_baseline AS
SELECT actual_course AS course,
       COUNT(*) AS starts,
       AVG(CASE WHEN finish_order=1 THEN 1.0 ELSE 0 END) AS p1,
       AVG(CASE WHEN finish_order<=2 THEN 1.0 ELSE 0 END) AS top2,
       AVG(CASE WHEN finish_order<=3 THEN 1.0 ELSE 0 END) AS top3,
       AVG(actual_st) AS avg_st
FROM entries WHERE actual_course IS NOT NULL
GROUP BY actual_course;

DROP TABLE IF EXISTS racer_course_summary;
CREATE TABLE racer_course_summary AS
SELECT racer_name,actual_course AS course,COUNT(*) AS starts,
       AVG(CASE WHEN finish_order=1 THEN 1.0 ELSE 0 END) AS p1,
       AVG(CASE WHEN finish_order<=2 THEN 1.0 ELSE 0 END) AS top2,
       AVG(CASE WHEN finish_order<=3 THEN 1.0 ELSE 0 END) AS top3,
       AVG(actual_st) AS avg_st
FROM entries WHERE racer_name IS NOT NULL AND actual_course IS NOT NULL
GROUP BY racer_name,actual_course;

DROP TABLE IF EXISTS winning_method_summary;
CREATE TABLE winning_method_summary AS
SELECT e.racer_name,e.actual_course AS course,r.winning_method,COUNT(*) AS wins
FROM entries e JOIN races r USING(race_code)
WHERE e.finish_order=1
GROUP BY e.racer_name,e.actual_course,r.winning_method;

DROP TABLE IF EXISTS escape_follow_summary;
CREATE TABLE escape_follow_summary AS
SELECT e.actual_course AS second_course, COUNT(*) AS times
FROM entries e JOIN races r USING(race_code)
WHERE r.winning_method='逃げ' AND e.finish_order=2
GROUP BY e.actual_course;
''')
con.commit()

races = cur.execute('SELECT COUNT(*) FROM races').fetchone()[0]
entries = cur.execute('SELECT COUNT(*) FROM entries').fetchone()[0]
print(f'files={len(files)} loaded_rows={loaded} skipped_files={skipped} races={races} entries={entries}')
con.close()
