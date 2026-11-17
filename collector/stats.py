#!/usr/bin/env python3
"""Motor de estadisticas: lee data/wars/*.json y genera docs/data/stats.json.

Calcula por jugador (guerras, CWL y total), por guerra/ronda (MVP) y por
temporada (MVP y bonos de medallas CWL). Las reglas estan en config.json.
"""
import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SUM_KEYS = [
    "available", "used", "stars", "new_stars", "three", "destruction",
    "hit_up", "hit_eq", "hit_down", "duration", "duration_n",
    "def_n", "def_stars", "def_three", "def_destruction", "missed", "score",
]


def load_json(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def sdiv(a, b, d=2):
    return round(a / b, d) if b else None


# ---------------------------------------------------------------- por guerra
def score_line(L, W):
    s = (
        L["stars"] * W["star"]
        + L["new_stars"] * W["new_star"]
        + L["three"] * W["three_star"]
        + (L["destruction"] / 10) * W["destruction_per_10pct"]
        + L["hit_up"] * W["hit_up"]
        - L["missed"] * W["missed_attack_penalty"]
    )
    return round(s, 1)


def war_lines(war, W):
    ended = war["state"] == "warEnded"
    allowed = war.get("attacks_per_member") or 1
    ours, theirs = war["clan"], war["opponent"]
    opp_th = {m["tag"]: m.get("th") or 0 for m in theirs["members"]}
    opp_pos = {m["tag"]: m.get("pos") or 0 for m in theirs["members"]}
    our_th = {m["tag"]: m.get("th") or 0 for m in ours["members"]}

    lines = {}
    for m in ours["members"]:
        lines[m["tag"]] = {
            "tag": m["tag"], "name": m["name"], "th": m.get("th"), "pos": m.get("pos"),
            "available": allowed, "used": 0, "stars": 0, "new_stars": 0, "three": 0,
            "destruction": 0, "hit_up": 0, "hit_eq": 0, "hit_down": 0,
            "duration": 0, "duration_n": 0, "target_pos": 0,
            "def_n": 0, "def_stars": 0, "def_three": 0, "def_destruction": 0,
        }

    # ataques propios en orden cronologico -> estrellas "netas" (nuevas)
    best = {}
    atks = [(a, m["tag"]) for m in ours["members"] for a in m["attacks"]]
    atks.sort(key=lambda x: x[0].get("order") or 0)
    for a, tag in atks:
        L = lines[tag]
        d = a["defender"]
        new = max(0, a["stars"] - best.get(d, 0))
        best[d] = max(best.get(d, 0), a["stars"])
        L["used"] += 1
        L["stars"] += a["stars"]
        L["new_stars"] += new
        L["three"] += 1 if a["stars"] == 3 else 0
        L["destruction"] += a["destruction"]
        L["target_pos"] += opp_pos.get(d, 0)
        dth, ath = opp_th.get(d, 0), our_th.get(tag, 0)
        if dth > ath:
            L["hit_up"] += 1
        elif dth == ath:
            L["hit_eq"] += 1
        else:
            L["hit_down"] += 1
        if a.get("duration") is not None:
            L["duration"] += a["duration"]
            L["duration_n"] += 1

    # defensa: ataques del rival contra nuestros jugadores
    for m in theirs["members"]:
        for a in m["attacks"]:
            L = lines.get(a["defender"])
            if L:
                L["def_n"] += 1
                L["def_stars"] += a["stars"]
                L["def_three"] += 1 if a["stars"] == 3 else 0
                L["def_destruction"] += a["destruction"]

    out = []
    for L in lines.values():
        L["missed"] = max(0, L["available"] - L["used"]) if ended else 0
        L["score"] = score_line(L, W)
        L["avg_destruction"] = sdiv(L["destruction"], L["used"], 1)
        L["avg_target_pos"] = sdiv(L["target_pos"], L["used"], 1)
        L["destruction"] = round(L["destruction"], 1)
        out.append(L)
    out.sort(key=lambda L: (-L["score"], -L["destruction"], L["name"].lower()))
    return out


def mvp_key(L):
    """Desempate: puntos > destruccion > estrellas netas > ataques a TH superior
    > bases mas dificiles (posicion de mapa mas baja). Si todo empata, es empate real."""
    return (L["score"], round(L["destruction"], 1), L["new_stars"], L["hit_up"], -(L.get("avg_target_pos") or 99))


def summarize_war(war, W):
    lines = war_lines(war, W)
    ended = war["state"] == "warEnded"
    ranked = [L for L in lines if L["used"] > 0]
    ranked.sort(key=mvp_key, reverse=True)
    podium, mvps = [], []
    if ended and ranked:
        rank, prev = 0, None
        for L in ranked:
            k = mvp_key(L)
            if k != prev:
                rank, prev = rank + 1, k
            if rank > 3:
                break
            entry = {"tag": L["tag"], "name": L["name"], "score": L["score"], "rank": rank}
            podium.append(entry)
            if rank == 1:
                mvps.append(entry)

    c, o = war["clan"], war["opponent"]
    if not ended:
        result = "live"
    elif (c["stars"], c["destruction"]) > (o["stars"], o["destruction"]):
        result = "win"
    elif (c["stars"], c["destruction"]) < (o["stars"], o["destruction"]):
        result = "lose"
    else:
        result = "tie"
    return {
        "id": war["id"], "type": war["type"], "round": war.get("round"), "season": war["season"],
        "state": war["state"], "start": war.get("start"), "end": war.get("end"),
        "team_size": war.get("team_size"), "attacks_per_member": war.get("attacks_per_member"),
        "opponent": {"tag": o.get("tag"), "name": o.get("name")},
        "stars": c["stars"], "destruction": c["destruction"],
        "opp_stars": o["stars"], "opp_destruction": o["destruction"],
        "result": result, "mvp": mvps[0] if mvps else None, "mvps": mvps, "podium": podium,
        "lines": lines,
    }


# ------------------------------------------------------------- agregaciones
def new_agg(L):
    a = {k: 0 for k in SUM_KEYS}
    a.update(tag=L["tag"], name=L["name"], th=L.get("th"), wars=0, mvps=0)
    return a


def finish(a):
    u = a["used"]
    a["attack_rate"] = sdiv(a["used"] * 100, a["available"], 1)
    a["avg_stars"] = sdiv(a["stars"], u)
    a["three_rate"] = sdiv(a["three"] * 100, u, 1)
    a["avg_destruction"] = sdiv(a["destruction"], u, 1)
    a["new_per_attack"] = sdiv(a["new_stars"], u)
    a["hit_up_rate"] = sdiv(a["hit_up"] * 100, u, 1)
    a["avg_duration"] = sdiv(a["duration"], a["duration_n"], 0)
    a["def_avg_stars"] = sdiv(a["def_stars"], a["def_n"])
    a["avg_score"] = sdiv(a["score"], a["wars"], 1)
    a["score"] = round(a["score"], 1)
    a["destruction"] = round(a["destruction"], 1)
    return a


def aggregate(wars_out):
    """wars_out: guerras terminadas, en orden cronologico."""
    agg = {}
    for w in wars_out:
        mvp_tags = {m["tag"] for m in (w.get("mvps") or ([w["mvp"]] if w.get("mvp") else []))}
        for L in w["lines"]:
            a = agg.setdefault(L["tag"], new_agg(L))
            a["name"], a["th"] = L["name"], L.get("th") or a["th"]
            a["wars"] += 1
            for k in SUM_KEYS:
                a[k] += L[k]
            if L["tag"] in mvp_tags:
                a["mvps"] += 1
    res = [finish(a) for a in agg.values()]
    res.sort(key=lambda a: (-a["score"], a["name"].lower()))
    return res


def top_player(players):
    c = [p for p in players if p["used"] > 0]
    if not c:
        return None
    p = max(c, key=lambda p: (p["score"], p["destruction"], p["new_stars"], p["hit_up"]))
    return {"tag": p["tag"], "name": p["name"], "score": p["score"]}


def build_season(season, wars_out, roster, W, B, now_month):
    ended = sorted((w for w in wars_out if w["state"] == "warEnded"), key=lambda w: w["start"] or "")
    groups = {
        "all": ended,
        "war": [w for w in ended if w["type"] == "war"],
        "cwl": [w for w in ended if w["type"] == "cwl"],
    }
    players = {k: aggregate(v) for k, v in groups.items()}

    # jugadores del roster de CWL que aun no han jugado ninguna ronda
    have = {p["tag"] for p in players["cwl"]}
    for r in roster:
        if r["tag"] not in have:
            players["cwl"].append(finish(new_agg(r)))
    players["cwl"].sort(key=lambda a: (-a["score"], a["name"].lower()))

    cwl_rounds = len(groups["cwl"])
    mvp = {
        "war": top_player(players["war"]),
        "cwl": top_player(players["cwl"]),
        "overall": top_player(players["all"]),
        "war_final": season < now_month,
        "cwl_final": cwl_rounds >= 7,
    }

    rows = []
    for p in players["cwl"]:
        is_mvp = bool(mvp["cwl"] and mvp["cwl"]["tag"] == p["tag"])
        raw = (
            p["stars"] * B["per_star"]
            + p["three"] * B["per_three_star"]
            + p["mvps"] * B["per_round_mvp"]
            + (B["season_mvp"] if is_mvp else 0)
            - p["missed"] * B["per_missed_attack_penalty"]
        )
        eligible = p["wars"] >= B["min_rounds_played"]
        rows.append({
            "tag": p["tag"], "name": p["name"], "th": p["th"],
            "rounds_played": p["wars"], "rounds_total": cwl_rounds,
            "stars": p["stars"], "three": p["three"], "round_mvps": p["mvps"],
            "missed": p["missed"], "season_mvp": is_mvp,
            "eligible": eligible, "bonus": max(0, round(raw)) if eligible else 0,
        })
    rows.sort(key=lambda r: (-r["bonus"], r["name"].lower()))

    return {
        "players": players,
        "wars": sorted(wars_out, key=lambda w: w["start"] or "", reverse=True),
        "mvp": mvp,
        "cwl_rounds": cwl_rounds,
        "cwl_bonus": rows,
    }


# -------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=str(ROOT / "data"))
    ap.add_argument("--out", default=str(ROOT / "docs" / "data" / "stats.json"))
    ap.add_argument("--config", default=str(ROOT / "config.json"))
    args = ap.parse_args()

    cfg = load_json(args.config)
    W, B = cfg["mvp_weights"], cfg["cwl_bonus"]
    data_dir = Path(args.data_dir)

    wars_dir = data_dir / "wars"
    wars = [load_json(p) for p in sorted(wars_dir.glob("*.json"))] if wars_dir.exists() else []
    cwl_dir = data_dir / "cwl"
    rosters = {p.stem: load_json(p).get("roster", []) for p in cwl_dir.glob("*.json")} if cwl_dir.exists() else {}

    by_season = defaultdict(list)
    for w in wars:
        if w.get("season"):
            by_season[w["season"]].append(summarize_war(w, W))

    now = datetime.now(timezone.utc)
    now_month = now.strftime("%Y-%m")
    seasons = sorted(by_season, reverse=True)
    season_data = {s: build_season(s, by_season[s], rosters.get(s, []), W, B, now_month) for s in seasons}

    # historico: todas las temporadas juntas
    all_ended = sorted(
        (w for s in seasons for w in by_season[s] if w["state"] == "warEnded"),
        key=lambda w: w["start"] or "",
    )
    all_players = {
        "all": aggregate(all_ended),
        "war": aggregate([w for w in all_ended if w["type"] == "war"]),
        "cwl": aggregate([w for w in all_ended if w["type"] == "cwl"]),
    }
    cnt_war, cnt_cwl = defaultdict(int), defaultdict(int)
    for s in seasons:
        m = season_data[s]["mvp"]
        if m["war"] and m["war_final"]:
            cnt_war[m["war"]["tag"]] += 1
        if m["cwl"] and m["cwl_final"]:
            cnt_cwl[m["cwl"]["tag"]] += 1
    for plist in all_players.values():
        for p in plist:
            p["season_mvps_war"] = cnt_war.get(p["tag"], 0)
            p["season_mvps_cwl"] = cnt_cwl.get(p["tag"], 0)

    clan_name = cfg["clan_tag"]
    if wars:
        latest = max(wars, key=lambda w: w.get("start") or "")
        clan_name = latest["clan"].get("name") or clan_name

    body = {
        "clan": {"tag": cfg["clan_tag"], "name": clan_name},
        "weights": W,
        "bonus": B,
        "seasons": seasons,
        "data": season_data,
        "all_time": {"players": all_players},
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        prev = load_json(out)
        prev.pop("generated_at", None)
        if prev == body:
            print("Sin cambios en las estadisticas.")
            return
    body["generated_at"] = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    out.write_text(json.dumps(body, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Estadisticas escritas en {out} ({len(wars)} guerras/rondas, {len(seasons)} temporada(s)).")


if __name__ == "__main__":
    main()
