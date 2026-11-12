"""Build data.js for the Mike's Way site from the game logs.

Usage:  python build_data.py ["C:/Users/billi/Videos/Softball Stats"]
Reads league.json + games/*.json (same rules as stats.ps1) and writes data.js next to this script.
Re-run it after every new game is logged.
"""
import glob, json, os, sys

_SIBLING = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Softball Stats")  # E:\MikesWay\Softball Stats
SRC = sys.argv[1] if len(sys.argv) > 1 else _SIBLING if os.path.isdir(_SIBLING) else os.path.join(os.environ.get("MW_VIDEOS") or os.path.join(os.path.expanduser("~"), "Videos"), "Softball Stats")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data.js")
US = "PUR"

# Seasons: (name, first date, last date). Add a line for each new season; the newest is shown by default.
SEASONS = [
    ("Fall 2026", "2026-08-01", "2026-12-31"),
    # ("Spring 2027", "2027-01-01", "2027-07-31"),   <- uncomment / add when the season starts
    # ("Fall 2027", "2027-08-01", "2027-12-31"),
]


def season_of(date):
    for name, a, b in SEASONS:
        if a <= date <= b:
            return name
    return date[:4]


# Batters the video couldn't identify. Map them to a roster id once you know who they are,
# e.g. "2026-11-10/mw_C": "feretic". Unmapped ones still count in team totals and box scores.
ALIASES = {}

# Courtesy / pinch runners: the run goes to the ORIGINAL runner (the player who got on base), not the
# player who ran for him. (game id, PA index where the runner came in, runner id, original player id).
# From that PA to the end of the half-inning, the runner's run is credited to the original player.
COURTESY = [
    ("2026-10-29-g1", 36, "2", "99"),             # Gio ran for Hegel, scored on Billings' sac fly
    ("2026-10-29-g2", 65, "2", "99"),             # Gio ran for Hegel (didn't score)
    ("2026-11-03-g2", 8, "15", "stamboulian"),  # #15 ran for the gray-hoodie batter
    ("2026-11-03-g2", 26, "15", "stamboulian"),
    ("2026-11-03-g2", 41, "15", "mw_unk"),        # possible; didn't score
]

HIT_TB = {"1B": 1, "2B": 2, "3B": 3, "HR": 4}
NO_AB = {"BB", "HBP", "SF", "SAC"}
KEYS = ["G", "PA", "AB", "R", "H", "2B", "3B", "HR", "RBI", "BB", "SO", "SF", "HBP", "TB"]


def load(p):
    with open(p, encoding="utf-8-sig") as f:
        return json.load(f)


league = load(os.path.join(SRC, "league.json"))
teams = league["teams"]
us = teams[US]
roster = us["roster"]


def new_line():
    return {k: 0 for k in KEYS} | {"pas": []}


games = []
for path in sorted(glob.glob(os.path.join(SRC, "games", "*.json"))):
    g = load(path)
    gid = g["id"]
    opp = g["home"] if g["away"] == US else g["away"]
    alias = lambda b: ALIASES.get(f"{gid}/{b}", b)

    lines, order = {}, []
    # active courtesy runners: runner id -> (original id, inning, half); a run by the runner goes to the original
    cr_start = {c[1]: (c[2], c[3]) for c in COURTESY if c[0] == gid}
    on_for = {}
    for i, pa in enumerate(g["pa"]):
        if pa["team"] != US:
            continue
        on_for = {r: v for r, v in on_for.items() if v[1:] == (pa["inning"], pa["half"]) and pa["batter"] != r}
        if i in cr_start:
            r0, o0 = cr_start[i]; on_for[r0] = (o0, pa["inning"], pa["half"])
        b = alias(pa["batter"])
        if b not in lines:
            lines[b] = new_line(); lines[b]["G"] = 1; order.append(b)
        l, r = lines[b], pa["result"]
        if r != "UNK":  # UNK = reached before filming: runs count, the PA doesn't
            l["PA"] += 1
            if r not in NO_AB:
                l["AB"] += 1
        if r in HIT_TB:
            l["H"] += 1; l["TB"] += HIT_TB[r]
            if r != "1B":
                l[r] += 1
        l["BB"] += r == "BB"; l["HBP"] += r == "HBP"; l["SF"] += r == "SF"; l["SO"] += r == "K"
        l["RBI"] += int(pa.get("rbi") or 0)
        l["pas"].append({"inn": pa["inning"], "res": r, "rbi": int(pa.get("rbi") or 0)})
        sc = pa.get("scored") or []
        sc = [sc] if isinstance(sc, (str, int)) else list(sc) if isinstance(sc, list) else []
        for s in sc:
            s = str(s)
            if s and not str(s).startswith("?"):
                if s in on_for:  # courtesy runner scored: the run belongs to the player he ran for
                    s = on_for.pop(s)[0]
                s = alias(s)
                lines.setdefault(s, new_line() | {"G": 1})
                if s not in order:
                    order.append(s)
                lines[s]["R"] += 1

    # line score: stored values win (they hold runs the camera missed)
    ls = g.get("linescore") or {}
    inns = max([int(i) for t in ls.values() for i in t] or [0])
    def runs(t):
        return [ls.get(t, {}).get(str(i)) for i in range(1, inns + 1)]
    ours, theirs = runs(US), runs(opp)
    hits = lambda t: sum(1 for p in g["pa"] if p["team"] == t and p["result"] in HIT_TB)
    errs = lambda t: sum(1 for p in g["pa"] for e in (p.get("errors") or []) if e and e.get("team") == t)
    R_us, R_them = sum(x or 0 for x in ours), sum(x or 0 for x in theirs)
    games.append({
        "id": gid, "date": g["date"], "season": season_of(g["date"]), "field": g.get("field", ""),
        "home": g["home"] == US, "opp": opp, "oppName": teams.get(opp, {}).get("name", opp), "oppShort": teams.get(opp, {}).get("short", opp),
        "oppColor": teams.get(opp, {}).get("color", "#888"),
        "final": g.get("final", ""),
        "ls": {"us": ours, "them": theirs},
        "R": [R_us, R_them], "H": [hits(US), hits(opp)], "E": [errs(US), errs(opp)],
        "result": "W" if R_us > R_them else "L" if R_us < R_them else "T",
        "order": order, "lines": lines,
        "oppHasPA": any(p["team"] == opp for p in g["pa"]),
        "moments": [m["text"] for m in g.get("moments", [])],
    })

# Fielding credits (defense.json, made from the play notes): only credits to a named player count.
# defense.json plus any defense_*.json (one file per batch of games), merged.
DEF_FILES = sorted(glob.glob(os.path.join(os.path.dirname(OUT), "defense*.json")))
if DEF_FILES:
    dj = {"positions": {}, "plays": []}
    for fp in DEF_FILES:
        part = load(fp)
        dj["positions"].update(part.get("positions", {}))
        dj["plays"] += part.get("plays", [])
    for g in games:
        plays = [p for p in dj.get("plays", []) if p.get("game") == g["id"]]
        if not plays:
            continue
        d = {}
        for p in plays:
            for c in p.get("credits", []):
                pid = ALIASES.get(f"{g['id']}/{c.get('player')}", c.get("player"))
                if not pid or pid == "?" or c.get("conf") == "low" or c.get("stat") not in ("PO", "A", "E", "DP"):
                    continue
                d.setdefault(pid, {"PO": 0, "A": 0, "E": 0, "DP": 0})[c["stat"]] += 1
        g["def"] = d
        g["pos"] = {k: v for k, v in dj.get("positions", {}).get(g["id"], {}).items() if k in g["lines"]}
        g["defUnassigned"] = sum(1 for p in plays for c in p.get("credits", []) if c.get("player") in (None, "", "?"))

players = []
for pid, p in roster.items():
    players.append({"id": pid, "num": p.get("number", ""), "name": p["name"],
                    "display": p.get("display", ""), "bats": p.get("bats", "?")})

data = {"team": {"name": us["name"], "short": us["short"], "color": us["color"]},
        "rules": league.get("rules", {}), "players": players, "games": games,
        "seasons": [n for n, a, b in sorted(SEASONS, key=lambda x: x[1])]
                   + sorted({g["season"] for g in games} - {n for n, *_ in SEASONS})}
with open(OUT, "w", encoding="utf-8") as f:
    f.write("// Generated by build_data.py from the Softball Stats game logs. Don't edit by hand.\n")
    f.write("const DATA = " + json.dumps(data, ensure_ascii=False, indent=1) + ";\n")
print(f"wrote {OUT}: {len(players)} players, {len(games)} games")
for g in games:
    unk = [b for b in g["order"] if b not in roster]
    print(f"  {g['date']} {g['result']} {g['R'][0]}-{g['R'][1]} vs {g['oppName']}" + (f"  unidentified: {unk}" if unk else ""))
