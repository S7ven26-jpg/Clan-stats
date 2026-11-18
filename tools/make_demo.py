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

    # incursiones de la capital (fines de semana de viernes a lunes)
    (out_dir / "capital").mkdir(parents=True)
    for d0 in [(10, 2), (10, 9), (10, 16), (10, 23), (10, 30), (11, 6), (11, 13)]:
        start = datetime(2026, d0[0], d0[1], 7, 0, tzinfo=timezone.utc)
        end = start + timedelta(days=3)
        mem = []
        for p in random.sample(PLAYERS, random.randint(22, 28)):
            lim, bonus = 5, random.choice([0, 0, 1])
            used = random.choice([lim + bonus, lim + bonus, lim, lim - 1, 3, 0]) if random.random() > 0.08 else 0
            mem.append({"tag": p["tag"], "name": p["name"], "attacks": used, "attack_limit": lim,
                        "bonus_attack_limit": bonus,
                        "looted": int(used * random.uniform(1400, 6200) * (1 + p["skill"]))})
        sid = "capital_" + start.strftime("%Y%m%d")
        rec = {"id": sid, "state": "ended", "start": start.strftime("%Y-%m-%dT%H:%M:%SZ"), "end": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
               "total_loot": sum(m["looted"] for m in mem), "raids_completed": random.randint(3, 6),
               "total_attacks": sum(m["attacks"] for m in mem), "districts_destroyed": random.randint(12, 28),
               "offensive_reward": random.randint(1100, 1700), "defensive_reward": random.randint(250, 700), "members": mem}
        (out_dir / "capital" / f"{sid}.json").write_text(json.dumps(rec), encoding="utf-8")
    (out_dir / "capital_contrib.json").write_text(json.dumps({
        "fetched": "2026-11-16T12:00:00Z", "clan_members": 30,
        "members": [{"tag": p["tag"], "name": p["name"], "contributed": random.randint(400_000, 5_000_000)} for p in PLAYERS]}), encoding="utf-8")

    # scouting CWL (8 clanes) y ficha del clan
    (out_dir / "scout").mkdir(parents=True)
    rivals = ["Los Titanes", "Dragones MX", "Elite Warriors", "Furia Roja", "Night Owls", "Pampa Clash", "Legión X"]
    clans = []
    for i, nm in enumerate([OUR_CLAN["name"]] + rivals):
        base = random.uniform(14.6, 16.8)
        mem = [{"tag": f"#S{i}{j:03d}", "name": f"Jugador{j}", "th": max(10, min(17, round(base + random.gauss(0, 1.1) - j * 0.03)))} for j in range(random.randint(15, 30))]
        w, l = random.randint(80, 400), random.randint(40, 200)
        clans.append({"tag": OUR_CLAN["tag"] if i == 0 else f"#R{i:04d}", "name": nm, "level": random.randint(12, 25), "badge": None,
                      "info": {"war_wins": w, "war_losses": l, "war_ties": random.randint(0, 8), "win_streak": random.randint(0, 9),
                               "war_log_public": random.random() > 0.15, "war_league": random.choice(["Cristal I", "Oro I", "Oro II", "Cristal II"]),
                               "points": random.randint(18000, 42000), "members_count": len(mem)}, "members": mem})
    (out_dir / "scout" / "2026-11.json").write_text(json.dumps({"season": "2026-11", "state": "inWar", "our_tag": OUR_CLAN["tag"],
        "fetched": "2026-11-02T08:00:00Z", "clans": clans}), encoding="utf-8")
    roles = ["leader", "coLeader", "coLeader", "admin", "admin", "admin"] + ["member"] * (len(PLAYERS) - 6)
    members = [{"tag": p["tag"], "name": p["name"], "role": roles[i], "th": p["th"], "exp": random.randint(120, 300),
                "trophies": random.randint(3800, 5600), "bb_trophies": random.randint(2800, 5600), "rank": i + 1,
                "donations": random.randint(0, 2200), "received": random.randint(0, 1800), "league": "Leyenda"} for i, p in enumerate(PLAYERS)]
    members.sort(key=lambda m: -m["trophies"])
    for i, mm in enumerate(members, 1):
        mm["rank"] = i
    (out_dir / "clan.json").write_text(json.dumps({
        "fetched": "2026-11-17T20:00:00Z", "tag": OUR_CLAN["tag"], "name": OUR_CLAN["name"], "type": "inviteOnly", "level": 18, "points": 31250, "bb_points": 28400,
        "capital_points": 21800, "description": "Clan para jugar en equipo, guerras y CWL todos los meses. ¡Se busca actividad y buen rollo! (texto de ejemplo)",
        "war_frequency": "always", "war_win_streak": 4, "war_wins": 231, "war_ties": 3, "war_losses": 88, "war_log_public": True, "location": "International",
        "chat_language": "Español", "required_trophies": 3500, "required_th": 14, "war_league": "Cristal I", "capital_league": "Oro II", "capital_hall": 9,
        "districts": [{"name": "Capital Peak", "hall": 9}, {"name": "Barbarian Camp", "hall": 7}, {"name": "Wizard Valley", "hall": 6}],
        "labels": ["Guerra de clanes", "CWL", "Amigable"], "badge": None, "members": members}), encoding="utf-8")



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
