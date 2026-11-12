"""Build film.js: every play in each full-game video, with the second it starts at.

Usage:  python build_film.py                  (all games)
        python build_film.py 2026-10-29-g2    (only these games; the rest are kept from the current film.js)
Reads each game's concat list (title card + clips + final card) and the clip specs the video
builder wrote, measures every clip with ffprobe, and writes film.js next to this script.
Add a new game to FILMS below after its YouTube video is rendered.
"""
import glob, json, os, re, subprocess, sys

ONLY = sys.argv[1:]
V = os.environ.get("MW_VIDEOS") or os.path.join(os.path.expanduser("~"), "Videos").replace("\\", "/")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "film.js")

# game id (from the stats game logs) -> where its full-game video and build files live
FILMS = [
    # rendered by Softball Stats/video/yt-render.ps1 (same format as the Nov 10 video)
    {"game": "2026-10-29-g1", "video": "Baseball 2026-10-29/YouTube/Bad News Beers @ Mike's Way - Full Game 1 (2026-10-29).mp4",
     "work": "Baseball 2026-10-29/analysis/yt_2026-10-29-g1", "title": "title.mp4", "list": "list.txt", "index": None},
    {"game": "2026-11-03-g1", "video": "Baseball 2026-11-03/YouTube/Mike's Way @ Opponent - Full Game 1 (2026-11-03).mp4",
     "work": "Baseball 2026-11-03/analysis/yt_g1", "title": "title.mp4", "list": "list.txt", "index": None},
    {"game": "2026-11-03-g2", "video": "Baseball 2026-11-03/YouTube/Opponent @ Mike's Way - Full Game 2 (2026-11-03).mp4",
     "work": "Baseball 2026-11-03/analysis/yt_g2", "title": "title.mp4", "list": "list.txt", "index": None},
    {"game": "2026-10-29-g2", "video": "Baseball 2026-10-29/YouTube/Mike's Way @ Balls Deep - Full Game 2 (2026-10-29).mp4",
     "work": "Baseball 2026-10-29/analysis/yt_2026-10-29-g2", "title": "title.mp4", "list": "list.txt", "index": None},
    {"game": "2026-11-10", "video": "Softball 2026-11-10/YouTube/Money Store @ Mike's Way - Full Game (2026-11-10).mp4",
     "work": "Softball 2026-11-10/analysis/yt3", "title": "title.mp4", "list": "list.txt", "index": "index.json"},
]


def dur(p):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", p],
                                capture_output=True, text=True).stdout.strip() or 0)


def load(p):
    with open(p, encoding="utf-8-sig") as f:
        return json.load(f)


roster = load(os.path.join(V, "Softball Stats", "league.json"))["teams"]["PUR"]["roster"]
by_num = {r["number"]: k for k, r in roster.items() if r.get("number")}
by_disp = {r["display"].upper(): k for k, r in roster.items() if r.get("display")}

# ids the Nov 10 video build used before those batters were named
RENAMED = {"mw_A": "7", "mw_B": "feretic", "mw_C": "dileo", "mw_D": "giordano", "mw_F": "stamboulian"}

films = []
for f in FILMS:
    if ONLY and f["game"] not in ONLY:
        continue
    work = os.path.join(V, f["work"])
    t = dur(os.path.join(work, f["title"]))
    index = {e["name"]: e for e in load(os.path.join(work, f["index"]))} if f["index"] else {}
    clips = [re.search(r"'(.+)'", l).group(1) for l in open(os.path.join(work, f["list"]), encoding="ascii") if "file" in l]
    plays = []
    for c in clips:
        name = os.path.splitext(os.path.basename(c))[0]
        d = dur(c)
        sp = load(os.path.join(work, "specs", name + ".json"))
        b = sp.get("batter")
        if b:  # a plate appearance (clips without a batter are between-play moments)
            st = sp["states"][0]
            ours = sp["away"]["abbr"] == "MIKE'S WAY" if st["half"] == "top" else sp["home"]["abbr"] == "MIKE'S WAY"
            pid = (index.get(name) or {}).get("batter") if index else None
            pid = RENAMED.get(pid, pid)
            if not pid and ours:
                pid = by_num.get(b.get("number")) or by_disp.get((b.get("name") or "").upper())
            plays.append({"t": round(t, 2), "len": round(d, 2), "inn": st["inning"], "half": st["half"], "ours": ours,
                          "id": pid or "", "num": b.get("number") or "", "name": b.get("name") or "",
                          "result": (sp.get("result") or {}).get("text", ""),
                          "score": [st["away"], st["home"]]})
        t += d
    # link each clip to its plate appearance in the game log (clips follow the log's filmed PAs in video order)
    log = load(os.path.join(V, "Softball Stats", "games", f["game"] + ".json"))["pa"]
    def tkey(p):
        for k in ("t_contact", "t_last"):
            try:
                return float(p.get(k))
            except (TypeError, ValueError):
                pass
        return 0.0
    filmed = sorted([i for i, p in enumerate(log) if p.get("video")], key=lambda i: (log[i]["video"], tkey(log[i])))
    bad = 0
    for k, pl in enumerate(plays):
        if k >= len(filmed):
            break
        i = filmed[k]; p = log[i]
        pl.update({"pa": i, "code": p["result"], "rbi": int(p.get("rbi") or 0), "runs": int(p.get("runs") or 0)})
        if pl["ours"] and pl["id"] and pl["id"] != p["batter"]:
            bad += 1
    if len(filmed) != len(plays) or bad:
        print(f"  WARNING {f['game']}: {len(plays)} clips vs {len(filmed)} filmed PAs, {bad} batter mismatches")
    # fielding credits on each play (from defense.json; low-confidence ones left out)
    dfiles = glob.glob(os.path.join(os.path.dirname(OUT), "defense*.json"))
    if dfiles:
        dc = {p["pa"]: p.get("credits", []) for fp in dfiles for p in load(fp).get("plays", []) if p.get("game") == f["game"]}
        for pl in plays:
            cr = [{"player": c["player"], "stat": c["stat"], "pos": c.get("pos", "")} for c in dc.get(pl.get("pa"), [])
                  if c.get("stat") in ("PO", "A", "E", "DP") and c.get("conf") != "low"]
            if cr:
                pl["def"] = cr
    total = dur(os.path.join(V, f["video"]))
    films.append({"game": f["game"], "src": f["video"], "length": round(total, 1), "plays": plays})
    print(f"{f['game']}: {len(plays)} plays, clips end at {t:.1f}s, video is {total:.1f}s")

# Games with no finished video: play the raw phone clips, using the game log's timestamps.
# (Each play carries its own "src"; windows match how the YouTube builder cuts a play.)
RAW = []  # every game has a finished video now (10/29 G1 used raw clips until 2026-11-12)
WORDS = {"1B": "SINGLE", "2B": "DOUBLE", "3B": "TRIPLE", "HR": "HOME RUN", "BB": "WALK", "K": "STRIKEOUT", "GO": "GROUND OUT",
         "FO": "FLY OUT", "PO": "POP OUT", "LO": "LINE OUT", "SF": "SAC FLY", "E": "SAFE ON ERROR", "FC": "FIELDER'S CHOICE",
         "DP": "DOUBLE PLAY", "OUT": "OUT"}


def result_text(p):
    r, n = p["result"], int(p.get("rbi") or 0)
    if r == "HR":
        return "GRAND SLAM" if n >= 4 else f"{n}-RUN HOME RUN" if n >= 2 else "SOLO HOME RUN"
    if r == "SF":
        return "SAC FLY, RBI"
    base = WORDS.get(r, r)
    return f"RBI {base}" if n == 1 else f"{n}-RUN {base}" if n >= 2 else base


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


roster_all = load(os.path.join(V, "Softball Stats", "league.json"))["teams"]["PUR"]["roster"]
for rw in RAW:
    g = load(os.path.join(V, "Softball Stats", "games", rw["game"] + ".json"))
    ls = g.get("linescore") or {}
    away, home = g["away"], g["home"]
    score = {away: 0, home: 0}
    plays, lens = [], {}
    for i, p in enumerate(g["pa"]):
        before = [score[away], score[home]]
        # the other team's runs come from the line score: they bat in the half before ours
        if p["team"] == home and away in ls:
            before[0] = sum(v for k, v in ls[away].items() if int(k) <= p["inning"])
        elif p["team"] == away and home in ls:
            before[1] = sum(v for k, v in ls[home].items() if int(k) < p["inning"])
        score[p["team"]] += int(p.get("runs") or 0)
        if not p.get("video"):
            continue
        tc = num(p.get("t_contact")); has_contact = tc is not None
        tc = tc if has_contact else num(p.get("t_last"))
        if tc is None:
            continue
        s0 = max(0.0, tc - 2.5)
        te = num(p.get("t_end")) or tc
        s1 = min(te + 2.5, tc + 27) if has_contact else tc + 3
        s1 = max(s1, tc + 3)
        src = f"{rw['raw']}/{p['video']}.MOV"
        if src not in lens:
            lens[src] = dur(os.path.join(V, src))
        s1 = min(s1, lens[src])
        r = roster_all.get(p["batter"], {})
        plays.append({"t": round(s0, 2), "len": round(s1 - s0, 2), "src": src, "inn": p["inning"], "half": p["half"],
                      "ours": p["team"] == "PUR", "id": p["batter"] if p["team"] == "PUR" else "", "num": r.get("number", ""),
                      "name": r.get("display", ""), "result": result_text(p), "score": before,
                      "pa": i, "code": p["result"], "rbi": int(p.get("rbi") or 0), "runs": int(p.get("runs") or 0)})
    films.append({"game": rw["game"], "src": plays[0]["src"] if plays else "", "raw": True,
                  "length": round(sum(lens.values()), 1), "plays": plays})
    print(f"{rw['game']}: {len(plays)} plays from {len(lens)} raw clips (no finished video)")

if ONLY and os.path.exists(OUT):  # keep the other games exactly as they are in the current film.js
    old = open(OUT, encoding="utf-8").read()
    old = json.loads(old[old.index("const FILMS = ") + len("const FILMS = "):].rstrip().rstrip(";"))
    films += [g for g in old if g["game"] not in ONLY]
films.sort(key=lambda f: f["game"])
with open(OUT, "w", encoding="utf-8") as fh:
    fh.write("// Generated by build_film.py. Video paths are relative to C:/Users/billi/Videos.\n")
    fh.write("const FILMS = " + json.dumps(films, ensure_ascii=False, indent=1) + ";\n")
print("wrote", OUT)
