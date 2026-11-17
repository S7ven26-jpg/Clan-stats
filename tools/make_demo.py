#!/usr/bin/env python3
"""Genera datos FALSOS de ejemplo y produce docs/data/demo.json.

Sirve para ver el dashboard sin API key:   python3 tools/make_demo.py
y luego abrir  docs/index.html?demo=1  (con un servidor local o GitHub Pages).
"""
import json
import random
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
random.seed(7)

NAMES = [
    "Shadow", "Draco", "Valkiria", "Nexus", "Zeta", "Kratos", "Luna", "Tigre", "Orion", "Fenix",
    "Rayo", "Bruja", "Titan", "Cobra", "Neo", "Atlas", "Hielo", "Volcan", "Samurai", "Dragona",
    "Lobo", "Pixel", "Mamba", "Blitz", "Eclipse", "Gaucho", "Ninja", "Trueno", "Alfa", "Rebelde",
]
RIVALS = ["Los Titanes", "Dragones MX", "Elite Warriors", "Furia Roja", "Night Owls", "Pampa Clash", "Legión X", "Reyes del Norte"]
OUR_CLAN = {"tag": "#DEMO123", "name": "Arepa con queso"}
PLAYERS = [
    {"tag": f"#P{i:04d}", "name": n, "th": random.choice([14, 15, 15, 16, 16, 17]), "skill": random.uniform(-0.2, 0.25)}
    for i, n in enumerate(NAMES)
]


def fmt(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def roll(ath, dth, skill):
    p3 = min(max(0.42 + 0.18 * (ath - dth) + skill, 0.05), 0.92)
    r = random.random()
    if r < p3:
        return 3, 100.0
    if r < p3 + 0.35:
        return (2, 99.0) if random.random() < 0.06 else (2, round(random.uniform(55, 95), 1))
    if r < p3 + 0.47:
        return 1, round(random.uniform(15, 50), 1)
    return 0, round(random.uniform(0, 30), 1)


def make_war(wid, kind, season, rnd, start, members, state, apm, used_prob=0.93, progress=1.0):
    n = len(members)
    opp = [
        {"tag": f"#O{wid[-6:]}{i}", "name": f"Rival{i + 1}", "th": random.choice([14, 15, 16, 17]), "pos": i + 1, "attacks": []}
        for i in range(n)
    ]
    ours = [
        {"tag": m["tag"], "name": m["name"], "th": m["th"], "pos": i + 1, "attacks": []}
        for i, m in enumerate(members)
    ]
    skill = {m["tag"]: m["skill"] for m in members}
    events = []
    for m in ours:
        k = apm if random.random() < used_prob else max(0, apm - random.choice([1, 1, 2]))
        if random.random() > progress:
            k = 0
        for _ in range(k):
            events.append(("us", m))
    for m in opp:
        k = apm if random.random() < 0.9 else apm - 1
        if random.random() > progress:
            k = 0
        for _ in range(k):
            events.append(("them", m))
    random.shuffle(events)

    best = {"us": {}, "them": {}}
    for order, (side, m) in enumerate(events, 1):
        defs = opp if side == "us" else ours
        d = random.choice(defs)
        sk = skill.get(m["tag"], random.uniform(-0.15, 0.15))
        stars, des = roll(m["th"], d["th"], sk)
        m["attacks"].append({
            "order": order, "defender": d["tag"], "stars": stars,
            "destruction": des, "duration": random.randint(60, 178),
        })
        b = best[side].get(d["tag"], (0, 0))
        best[side][d["tag"]] = max(b, (stars, des))

    def totals(side):
        v = best[side].values()
        return sum(s for s, _ in v), round(sum(d for _, d in v) / n, 2)

    cs, cd = totals("us")
    os_, od = totals("them")
    end = start + timedelta(hours=24)
    return {
        "id": wid, "type": kind, "season": season, "round": rnd, "war_tag": None, "state": state,
        "start": fmt(start), "end": fmt(end), "team_size": n, "attacks_per_member": apm,
        "clan": {**OUR_CLAN, "stars": cs, "destruction": cd, "members": ours},
        "opponent": {"tag": "#OPP999", "name": random.choice(RIVALS), "stars": os_, "destruction": od, "members": opp},
    }


def build(out_dir):
    (out_dir / "wars").mkdir(parents=True)
    (out_dir / "cwl").mkdir(parents=True)

    def save(w):
        (out_dir / "wars" / f"{w['id']}.json").write_text(json.dumps(w), encoding="utf-8")

    for season, y, m, war_days in [("2026-10", 2026, 10, [9, 12, 15, 19, 23, 27]), ("2026-11", 2026, 11, [10, 13])]:
        roster = random.sample(PLAYERS, 18)
        (out_dir / "cwl" / f"{season}.json").write_text(
            json.dumps({"season": season, "state": "ended", "tag_map": {},
                        "roster": [{"tag": p["tag"], "name": p["name"], "th": p["th"]} for p in roster]}),
            encoding="utf-8",
        )
        for r in range(1, 8):
            lineup = random.sample(roster, 15)
            start = datetime(y, m, 1 + r, 8, 0, tzinfo=timezone.utc)
            save(make_war(f"cwl_{season}_r{r}", "cwl", season, r, start, lineup, "warEnded", 1))
        for d in war_days:
            start = datetime(y, m, d, 18, 0, tzinfo=timezone.utc)
            save(make_war(f"war_{y}{m:02d}{d:02d}T180000", "war", season, None, start,
                          random.sample(PLAYERS, 30), "warEnded", 2))
    # una guerra en curso (parcial)
    start = datetime(2026, 11, 15, 18, 0, tzinfo=timezone.utc)
    save(make_war("war_20261115T180000", "war", "2026-11", None, start, random.sample(PLAYERS, 30), "inWar", 2, progress=0.5))


def main():
    out = ROOT / "docs" / "data" / "demo.json"
    with tempfile.TemporaryDirectory() as tmp:
        build(Path(tmp))
        subprocess.run(
            [sys.executable, str(ROOT / "collector" / "stats.py"), "--data-dir", tmp, "--out", str(out)],
            check=True,
        )
    print(f"Demo listo: {out}")


if __name__ == "__main__":
    main()
