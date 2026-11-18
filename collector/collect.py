#!/usr/bin/env python3
"""Colector: consulta el API de Clash of Clans y guarda guerras y CWL en data/.

Solo usa la libreria estandar de Python (no hay que instalar nada).
Variables de entorno:
  COC_API_TOKEN  -> tu API key (obligatoria)
  COC_API_BASE   -> URL base del API (opcional, por defecto la de config.json)
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CFG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))

TOKEN = os.environ.get("COC_API_TOKEN", "").strip()
BASE = (os.environ.get("COC_API_BASE") or CFG.get("api_base") or "https://api.clashofclans.com/v1").rstrip("/")
CLAN = CFG["clan_tag"].strip().upper()
if not CLAN.startswith("#"):
    CLAN = "#" + CLAN


class ApiError(Exception):
    def __init__(self, msg, code=None):
        super().__init__(msg)
        self.code = code


def enc(tag):
    return urllib.parse.quote(tag, safe="")


def api_get(path, retries=3):
    """GET al API. Devuelve dict, o None si da 404 (no existe / no hay guerra)."""
    req = urllib.request.Request(
        f"{BASE}{path}",
        headers={"Authorization": f"Bearer {TOKEN}", "Accept": "application/json"},
    )
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            body = e.read().decode("utf-8", "replace")[:300]
            if e.code in (429, 500, 502, 503, 504) and attempt < retries - 1:
                time.sleep(2 * (attempt + 1))
                continue
            raise ApiError(f"HTTP {e.code} en {path}: {body}", e.code)
        except urllib.error.URLError as e:
            if attempt < retries - 1:
                time.sleep(2 * (attempt + 1))
                continue
            raise ApiError(f"Sin conexion en {path}: {e.reason}")


def iso(t):
    """'20261116T120000.000Z' -> '2026-11-16T12:00:00Z'."""
    if not t:
        return None
    try:
        return datetime.strptime(t, "%Y%m%dT%H%M%S.%fZ").strftime("%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return t


def norm_side(side):
    members = []
    for m in side.get("members", []):
        atks = [
            {
                "order": a.get("order"),
                "defender": a.get("defenderTag"),
                "stars": a.get("stars", 0),
                "destruction": a.get("destructionPercentage", 0),
                "duration": a.get("duration"),
            }
            for a in m.get("attacks", [])
        ]
        members.append(
            {
                "tag": m["tag"],
                "name": m.get("name", "?"),
                "th": m.get("townhallLevel") or m.get("townHallLevel"),
                "pos": m.get("mapPosition"),
                "attacks": atks,
            }
        )
    return {
        "tag": side.get("tag"),
        "name": side.get("name"),
        "stars": side.get("stars", 0),
        "destruction": round(side.get("destructionPercentage", 0) or 0, 2),
        "members": members,
    }


def normalize_war(raw, wid, kind, season, rnd=None, war_tag=None):
    """Devuelve la guerra con 'clan' = nuestro clan y 'opponent' = el rival."""
    a, b = raw.get("clan", {}), raw.get("opponent", {})
    if a.get("tag", "").upper() == CLAN:
        ours, theirs = a, b
    elif b.get("tag", "").upper() == CLAN:
        ours, theirs = b, a
    else:
        return None
    return {
        "id": wid,
        "type": kind,  # "war" o "cwl"
        "season": season,
        "round": rnd,
        "war_tag": war_tag,
        "state": raw.get("state"),
        "start": iso(raw.get("startTime")),
        "end": iso(raw.get("endTime")),
        "team_size": raw.get("teamSize"),
        "attacks_per_member": raw.get("attacksPerMember") or (1 if kind == "cwl" else 2),
        "clan": norm_side(ours),
        "opponent": norm_side(theirs),
    }


def save_json(path, obj):
    """Guarda solo si cambio. Devuelve True si escribio."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(obj, ensure_ascii=False, indent=1) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return False
    path.write_text(text, encoding="utf-8")
    return True


def is_final(path):
    if not path.exists():
        return False
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("state") == "warEnded"
    except ValueError:
        return False


def collect_regular():
    raw = api_get(f"/clans/{enc(CLAN)}/currentwar")
    if not raw:
        print("Guerra normal: no hay datos.")
        return
    state = raw.get("state")
    if state in (None, "notInWar", "preparation"):
        print(f"Guerra normal: estado '{state}', nada que guardar.")
        return
    if raw.get("warTag") or raw.get("attacksPerMember") == 1:
        print("Guerra normal: es una ronda de CWL, se ignora aqui.")
        return
    start = raw.get("startTime") or raw.get("preparationStartTime")
    if not start:
        return
    end = iso(raw.get("endTime")) or ""
    wid = f"war_{start[:15]}"
    path = DATA / "wars" / f"{wid}.json"
    if is_final(path):
        print(f"Guerra {wid}: ya estaba finalizada.")
        return
    war = normalize_war(raw, wid, "war", end[:7] or None)
    if war and save_json(path, war):
        print(f"Guerra {wid}: guardada ({state}).")
    else:
        print(f"Guerra {wid}: sin cambios.")


def collect_cwl():
    g = api_get(f"/clans/{enc(CLAN)}/currentwar/leaguegroup")
    if not g:
        print("CWL: el clan no esta en una liga de guerra ahora mismo.")
        return
    season = g.get("season")
    cwl_path = DATA / "cwl" / f"{season}.json"
    old = json.loads(cwl_path.read_text(encoding="utf-8")) if cwl_path.exists() else {}
    tag_map = old.get("tag_map", {})

    mine = next((c for c in g.get("clans", []) if c.get("tag", "").upper() == CLAN), None)
    roster = old.get("roster", [])
    if mine:
        roster = [
            {"tag": m["tag"], "name": m.get("name", "?"), "th": m.get("townHallLevel") or m.get("townhallLevel")}
            for m in mine.get("members", [])
        ]

    saved = 0
    for idx, rnd in enumerate(g.get("rounds", []), 1):
        for wt in rnd.get("warTags", []):
            if not wt or wt == "#0" or tag_map.get(wt) == "other":
                continue
            wid = f"cwl_{season}_r{idx}"
            path = DATA / "wars" / f"{wid}.json"
            if tag_map.get(wt) == "ours" and is_final(path):
                continue
            raw = api_get(f"/clanwarleagues/wars/{enc(wt)}")
            if not raw:
                continue
            tags = {raw.get("clan", {}).get("tag", "").upper(), raw.get("opponent", {}).get("tag", "").upper()}
            if CLAN not in tags:
                tag_map[wt] = "other"
                continue
            tag_map[wt] = "ours"
            if raw.get("state") == "preparation":
                continue
            war = normalize_war(raw, wid, "cwl", season, rnd=idx, war_tag=wt)
            if war and save_json(path, war):
                saved += 1
                print(f"CWL ronda {idx}: guardada ({raw.get('state')}).")
    save_json(cwl_path, {"season": season, "state": g.get("state"), "roster": roster, "tag_map": tag_map})
    print(f"CWL {season}: {saved} ronda(s) actualizada(s).")


def collect_capital():
    """Temporadas de incursion de la capital del clan: GET /clans/{tag}/capitalraidseasons.
    Guarda data/capital/capital_<AAAAMMDD>.json (una por fin de semana de incursion)."""
    d = api_get(f"/clans/{enc(CLAN)}/capitalraidseasons?limit=10")
    items = (d or {}).get("items", [])
    out = DATA / "capital"
    out.mkdir(parents=True, exist_ok=True)
    saved = 0
    for s in items:
        start = iso(s.get("startTime"))
        if not start:
            continue
        rec = {
            "id": "capital_" + start.replace("-", "")[:8],
            "state": s.get("state"),
            "start": start,
            "end": iso(s.get("endTime")),
            "total_loot": s.get("capitalTotalLoot") or 0,
            "raids_completed": s.get("raidsCompleted") or 0,
            "total_attacks": s.get("totalAttacks") or 0,
            "districts_destroyed": s.get("enemyDistrictsDestroyed") or 0,
            "offensive_reward": s.get("offensiveReward") or 0,
            "defensive_reward": s.get("defensiveReward") or 0,
            "members": [
                {
                    "tag": m.get("tag"), "name": m.get("name"),
                    "attacks": m.get("attacks") or 0,
                    "attack_limit": m.get("attackLimit") or 0,
                    "bonus_attack_limit": m.get("bonusAttackLimit") or 0,
                    "looted": m.get("capitalResourcesLooted") or 0,
                }
                for m in (s.get("members") or [])
            ],
        }
        path = out / f"{rec['id']}.json"
        if path.exists() and json.loads(path.read_text(encoding="utf-8")) == rec:
            continue
        path.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
        saved += 1
    print(f"Capital: {len(items)} temporada(s) de incursion, {saved} nueva(s) o actualizada(s).")


def collect_contrib():
    """Oro de capital APORTADO (acumulado de por vida) de los miembros actuales.
    Sale del logro 'Most Valuable Clanmate' de cada jugador (GET /players/{tag}).
    La API no da el oro aportado por fin de semana, solo este acumulado."""
    clan = api_get(f"/clans/{enc(CLAN)}") or {}
    members, failed = [], 0
    for m in clan.get("memberList", []):
        try:
            p = api_get(f"/players/{enc(m['tag'])}")
        except ApiError:
            failed += 1
            continue
        if not p:
            failed += 1
            continue
        val = next((a.get("value") for a in p.get("achievements", []) if a.get("name") == "Most Valuable Clanmate"), None)
        if val is not None:
            members.append({"tag": m["tag"], "name": m.get("name") or m["tag"], "contributed": val})
    if failed or not members:
        print(f"Aporte capital: {failed} jugador(es) sin leer; se conserva el archivo anterior.")
        return
    path = DATA / "capital_contrib.json"
    rec = {"clan_members": len(clan.get("memberList", [])), "members": sorted(members, key=lambda x: x["tag"])}
    if path.exists() and {k: v for k, v in json.loads(path.read_text(encoding="utf-8")).items() if k != "fetched"} == rec:
        return
    rec["fetched"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    path.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Aporte capital: {len(members)} jugador(es) guardados.")


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def collect_scout():
    """Scouting CWL: los 8 clanes del grupo de la liga (GET /clans/{tag}/currentwar/leaguegroup)
    + una consulta por clan rival (GET /clans/{tag}) solo la primera vez. Aparece al empezar la CWL."""
    g = api_get(f"/clans/{enc(CLAN)}/currentwar/leaguegroup")
    if not g or not g.get("clans"):
        print("Scouting: no hay grupo de CWL ahora mismo.")
        return
    season = g.get("season") or datetime.now(timezone.utc).strftime("%Y-%m")
    d = DATA / "scout"
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{season}.json"
    old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    old_info = {c["tag"]: c.get("info") for c in old.get("clans", [])}
    clans = []
    for c in g["clans"]:
        info = old_info.get(c["tag"])
        if not info:
            try:
                full = api_get(f"/clans/{enc(c['tag'])}") or {}
                info = {
                    "war_wins": full.get("warWins"), "war_losses": full.get("warLosses"), "war_ties": full.get("warTies"),
                    "win_streak": full.get("warWinStreak"), "war_log_public": full.get("isWarLogPublic"),
                    "war_league": (full.get("warLeague") or {}).get("name"), "points": full.get("clanPoints"),
                    "members_count": full.get("members"),
                } if full else None
            except ApiError:
                info = None
        clans.append({
            "tag": c["tag"], "name": c.get("name"), "level": c.get("clanLevel"),
            "badge": (c.get("badgeUrls") or {}).get("large"), "info": info,
            "members": [{"tag": m["tag"], "name": m.get("name"), "th": m.get("townHallLevel") or 0} for m in c.get("members", [])],
        })
    rec = {"season": season, "state": g.get("state"), "our_tag": CLAN, "clans": clans}
    if {k: v for k, v in old.items() if k != "fetched"} == rec:
        return
    rec["fetched"] = _now()
    path.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Scouting: {len(clans)} clanes guardados para {season}.")


def collect_clan():
    """Ficha de nuestro clan: GET /clans/{tag} (1 consulta). Se refresca cada 3 h o si cambia la plantilla."""
    path = DATA / "clan.json"
    old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    c = api_get(f"/clans/{enc(CLAN)}")
    if not c:
        return
    mem = [{
        "tag": m["tag"], "name": m.get("name"), "role": m.get("role"), "th": m.get("townHallLevel") or 0,
        "exp": m.get("expLevel"), "trophies": m.get("trophies") or 0, "bb_trophies": m.get("builderBaseTrophies") or 0,
        "rank": m.get("clanRank"), "donations": m.get("donations"), "received": m.get("donationsReceived"),   # None = el API no lo dio (no es lo mismo que 0)
        "league": (m.get("league") or {}).get("name"),
    } for m in c.get("memberList", [])]
    cap = c.get("clanCapital") or {}
    rec = {
        "tag": c.get("tag"), "name": c.get("name"), "description": c.get("description") or "", "type": c.get("type"),
        "level": c.get("clanLevel"), "points": c.get("clanPoints"), "bb_points": c.get("clanBuilderBasePoints"),
        "capital_points": c.get("clanCapitalPoints"), "war_frequency": c.get("warFrequency"),
        "war_win_streak": c.get("warWinStreak"), "war_wins": c.get("warWins"), "war_ties": c.get("warTies"),
        "war_losses": c.get("warLosses"), "war_log_public": c.get("isWarLogPublic"),
        "location": (c.get("location") or {}).get("name"), "chat_language": (c.get("chatLanguage") or {}).get("name"),
        "required_trophies": c.get("requiredTrophies"), "required_th": c.get("requiredTownhallLevel"),
        "war_league": (c.get("warLeague") or {}).get("name"), "capital_league": (c.get("capitalLeague") or {}).get("name"),
        "capital_hall": cap.get("capitalHallLevel"),
        "districts": [{"name": x.get("name"), "hall": x.get("districtHallLevel")} for x in cap.get("districts", [])],
        "labels": [x.get("name") for x in c.get("labels", [])],
        "badge": (c.get("badgeUrls") or {}).get("large"), "members": mem,
    }
    sig = lambda r: [(m["tag"], m["name"], m["role"], m["th"]) for m in r["members"]] + [r["name"], r["description"], r["level"]]
    if old:
        age = (datetime.now(timezone.utc) - datetime.strptime(old["fetched"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)).total_seconds()
        if age < 3 * 3600 and sig(old) == sig(rec):
            return
    rec["fetched"] = _now()
    path.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Clan: ficha guardada ({len(mem)} miembros).")


def week_key(d):
    """Clave semanal estable: ISO 8601 en UTC, p. ej. 2026-W47 (la semana empieza el lunes 00:00 UTC)."""
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def collect_history():
    """Captura SEMANAL del clan para Tendencias (data/history.json). Reusa la ficha del clan ya descargada: 0 consultas nuevas.
    Una sola captura por semana ISO (UTC): si se reintenta o el flujo corre de nuevo esa semana, no se duplica ni se sobrescribe."""
    cf = DATA / "clan.json"
    if not cf.exists():
        return
    c = json.loads(cf.read_text(encoding="utf-8"))
    now = datetime.now(timezone.utc)
    key = week_key(now)
    path = DATA / "history.json"
    hist = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    for h in hist:                      # migra capturas antiguas (diarias) a la clave semanal
        if "week" not in h:
            h["week"] = week_key(datetime.strptime(h["date"], "%Y-%m-%d"))
    if any(h["week"] == key for h in hist):
        return
    ms = c.get("members", [])
    known = [m["th"] for m in ms if (m.get("th") or 0) > 0]
    hist.append({
        "week": key, "taken": _now(), "points": c.get("points"), "members": len(ms),
        "th_avg": round(sum(known) / len(known), 2) if known else None, "th_known": len(known),
    })
    hist.sort(key=lambda h: h["week"])
    path.write_text(json.dumps(hist[-260:], ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Historial: captura de la semana {key} guardada ({len(hist)} en total).")


def main():
    if not TOKEN:
        sys.exit("Falta la variable COC_API_TOKEN (tu API key).")
    if CLAN in ("#TAGDETUCLAN", "#"):
        sys.exit("Edita config.json y pon el tag de tu clan en 'clan_tag'.")

    errors = []
    for fn in (collect_regular, collect_cwl):
        try:
            fn()
        except ApiError as e:
            errors.append(str(e))
            print(f"ERROR en {fn.__name__}: {e}", file=sys.stderr)
            if e.code == 403:
                print(
                    "  -> 403: revisa que la key permita la IP del proxy y que el "
                    "registro de guerra del clan sea PUBLICO.",
                    file=sys.stderr,
                )
    # extras: si fallan, solo avisan (no marcan el workflow en rojo)
    for fn in (collect_capital, collect_contrib, collect_scout, collect_clan, collect_history):
        try:
            fn()
        except ApiError as e:
            print(f"AVISO ({fn.__name__}): {e}", file=sys.stderr)
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
