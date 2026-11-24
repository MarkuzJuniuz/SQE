"""Mission -> campaign feedback loop.

1. The builder embeds LUA_HOOK in the .miz.
2. During flight it rewrites  <Saved Games>\\SQE\\SQE_state.json  every 30 s and on every kill/loss/landing.
3. The waiting window polls that file; Accept applies it to the campaign.

REQUIRES io/lfs un-sanitized in <DCS>\\Scripts\\MissionScripting.lua (Settings has a one-click patch helper).
"""
from __future__ import annotations
import json
import os
import re
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from .models import AssetKind
from . import refit as _refit
from .state import CampaignState
from .runways import RUNWAY_HALF_LEN_M, RUNWAY_HALF_WIDTH_M
from .words import bda_text, strength_word

from .hook_lua import LUA_HOOK
SCRUB_LOSS_FRAC = 0.5          # v0.41.223: a side of a package (strikers, or the covering fighters) that has lost this share of its jets scrubs the package (judgment call: XO's run, a 2-ship that lost one went home; the Gudauta CAS escort was down to two of four)
SCRUB_STRIKE_GRACE_S = 180     # ...the strikers lost: scrub until this long after TOT (after that the strike is done or moot)
CAS_DONE_FRAC = 0.2            # S93: an AI CAS flight goes home once its target group is down to this share of its units (5 or more units: at least 1 may be left; fewer: all dead). Judgment call (run 19-23-07: 5 of 6 dead, the sixth never died)
CAS_LEASH_M = 18000            # S93: ...or once it strays this far from the target point after having been within it (twice CAS_ZONE_M: it was hunting air defence 30 km away)
SCRUB_COVER_LEAD_S = 90        # ...the cover lost: scrub only until this long before TOT (strikers that have committed finish the job)
RUNWAY_CREDIT = 0.6          # S75 (XO 2026-11-13): a runway job that closed the field reads as a win in the debrief (target_damage raised to this; same value as SUPPRESSED_CREDIT, narrative's 'great' threshold; judgment call). A runway has no health, so its damage was always 0%
SUPPRESSED_CREDIT = 0.6       # v0.41.414 (S61, XO): a primary SAM left suppressed (radars gone) reads as a win in the debrief: target_damage is raised to this (judgment call: narrative's 'great' threshold). Asset health and the war sim are untouched
BINGO_PCT = 20            # v0.41.92: the hook's bingo for pairs (BINGO_FUEL in the Lua below); the debrief fuel lines use it
BINGO_REPORT_PCT = 35      # ...and report a flight that ended the mission at or under this much fuel


def _jamcfg() -> str:
    from . import ecm
    return (f"local JC = {{ p1={ecm.P_SELF[1]}, p2={ecm.P_SELF[2]}, cover={ecm.P_COVER}, coverM={ecm.COVER_NM * 1852:.0f}, "
            f"burn={ecm.BURN_KM * 1000:.0f}, full={ecm.FULL_KM * 1000:.0f} }}")


def _lua_str(s: str) -> str:
    return str(s).replace("\\", "/").replace('"', "'")


def _lq(s) -> str:
    return '"' + _lua_str(s).replace("\n", " ") + '"'


def _gate_test_lua() -> str:
    """v0.41.363 (attack fix plan, Stage B1): DEV ONLY. Env var SQE_GATE_TEST_HOLD_S (seconds, read when the mission is built): the hook holds every AI
    gated flight that many seconds once, at its gate decision, then releases it through the normal resume(). Nothing is emitted when the variable is unset or 0."""
    try:
        n = int(float(os.environ.get("SQE_GATE_TEST_HOLD_S", "0") or 0))
    except ValueError:
        n = 0
    if n <= 0:
        return ""
    lines = [
        "  if not gs.tested then",
        "    local anyAi = false",
        "    for _, gt in ipairs(gs.gates) do if gt.ai and gt.dead then anyAi = true end end",
        "    if anyAi then",
        "      gs.tested = true",
        "      if not gs.tp then gs.tp = sitePoint(s) end",
        "      holdGroups(gs)",
        '      timer.scheduleFunction(function() if gs.holding then resume(gs, "test-hold") end; return nil end, nil, timer.getTime() + %d)' % n,
        "      return",
        "    end",
        "  end",
    ]
    return "\n".join(lines) + "\n"


def _umbrella_lua(x: dict) -> str:
    """The gate's umbrella fields for the hook (the SA-10 covering its target), or nothing."""
    if x.get("ux") is None:
        return ""
    return ", ux=%.1f, uz=%.1f, um=%d" % (float(x["ux"]), float(x["uz"]), int(x["um"]))


BOMB_FAR_KM = 20     # S149 (XO 2026-11-22: a jumped AI striker dumps its bombs and the hook called "Bombs away"): a bomb that leaves farther than this from its flight's target point is a jettison. SQE's strikers release inside 5 nm (JDAM, `routes.JDAM_RELEASE_NM`) to the point itself; 20 km is a judgment call with margin for a CAS target that moves


# S184: the SA number a MAGNUM call names, by a part of the DCS type name of the radar or launcher the missile goes for (first match wins).
# Source: the NATO reporting numbers of these systems (SA-2 S-75, SA-3 S-125, SA-5 S-200, SA-6 Kub, SA-8 Osa, SA-9 Strela-1, SA-10 S-300PS, SA-11 Buk,
# SA-13 Strela-10, SA-15 Tor, SA-19 Tunguska: public, firmness high); the type names are pydcs `vehicles.AirDefence` ids.
SAM_NUMBER_WORDS = (("Kub", "six"), ("S-300", "ten"), ("Buk", "eleven"), ("Osa", "eight"), ("Tor 9A", "fifteen"), ("SNR_75", "two"), ("s-125", "three"),
                    ("RPC_5N62", "five"), ("RLS_19J6", "five"), ("Tunguska", "nineteen"), ("Strela-10", "thirteen"), ("Strela-1 ", "nine"))


def lua_hook(campaign_id: str, sortie: int, package_id: str, despawn_names: list, player_name: str = "", group: str = "",
             calls: list | None = None, wps: list | None = None, sound: str = "", sound_you: str = "", flights: dict | None = None,
             enemy_air: list | None = None, sites: list | None = None, ruins: list | None = None, gates: list | None = None, ai_test: bool = False, gate_km: float = 40, jams: dict | None = None, jamw: dict | None = None,
             watch: list | None = None, done_after: float = 0, awacs: str = "AWACS", splash: bool = False,
             rwyq: list | None = None, prwy: str = "", alerts: list | None = None, cfg: dict | None = None, cover: list | None = None, ecm_player: str = "", ecm_msg: bool = True,
             tune_flags: list | None = None, tune_mhz: float = 0.0, awacs_unit: str = "", dmg: dict | None = None, dmg_on: bool = False, scrub: list | None = None, casdone: list | None = None, bomb_tgt: dict | None = None) -> str:
    tbl = ", ".join(f'["{n}"]=true' for n in despawn_names)
    cl = ", ".join(f'{{t={float(c[0]):.0f}, text="{_lua_str(c[1])}", you={"true" if (len(c) > 2 and c[2]) else "false"}}}' for c in (calls or []))
    uf = ", ".join(f"[{_lq(k)}]={_lq(v)}" for k, v in (flights or {}).items())
    btg = ", ".join(f"[{_lq(k)}]={{x={float(v[0]):.1f}, z={float(v[1]):.1f}}}" for k, v in (bomb_tgt or {}).items())
    ea = ", ".join(f"[{_lq(n)}]=true" for n in (enemy_air or []))
    lst = lambda xs: "{" + ", ".join(_lq(x) for x in xs) + "}"
    sc = ", ".join(f'{{pkg={_lq(x["pkg"])}, g={_lq(x["grp"])}, k={_lq(x["k"])}, units={lst(x["units"])}, to={int(x["to"])}, ai={"true" if x["ai"] else "false"}, '
                    f'you={"true" if x["you"] else "false"}, tot={float(x["tot"]):.0f}}}' for x in (scrub or []))
    st = ", ".join(f'{{id={_lq(x["id"])}, label={_lq(x["label"])}, who={_lq(x["who"])}, prim={"true" if x["prim"] else "false"}, '
                   f'units={lst(x["units"])}, trk={lst(x["trk"])}, srch={lst(x["srch"])}}}' for x in (sites or []))
    ru = ", ".join(f'{{x={r["x"]:.1f}, z={r["z"]:.1f}, n={int(r["n"])}, r={float(r["r"]):.0f}, p={int(r["p"])}, dn={float(r["dn"]):.2f}, pw={int(r["pw"])}, s={float(r["s"]):.2f}}}'
                   for r in (ruins or []))
    gt = ", ".join(f'{{t={float(x["t"]):.0f}, site={_lq(x["site"])}, grp={_lq(x["grp"])}, from={int(x["from"])}, to={int(x["to"])}, ai={"true" if x["ai"] else "false"}, dead={"true" if x.get("dead") else "false"}, you={"true" if x.get("you") else "false"}, seads={{{", ".join(_lq(n) for n in x.get("seads", []))}}}, also={{{", ".join(_lq(n) for n in x.get("also", []))}}}, more={{{", ".join(_lq(n) for n in x.get("more", []))}}}, gm={int(x.get("gm") or 0)}, acap={int(x.get("acap") or 0)}{_umbrella_lua(x)}{(", tx=%.1f, tz=%.1f" % (float(x["tx"]), float(x["tz"]))) if x.get("tx") is not None else ""}}}'
                   for x in (gates or []))
    cd_ = ", ".join(f'{{g={_lq(x["grp"])}, units={lst(x["units"])}, to={int(x["to"])}, tx={float(x["tx"]):.1f}, tz={float(x["tz"]):.1f}}}' for x in (casdone or []))
    cr = ", ".join("{x=%.1f, z=%.1f, pw=%.0f}" % (c[0], c[1], c[2]) for c in (cfg or {}).get("craters", []))
    return (LUA_HOOK.replace("__CRATERS__", cr).replace("__RWYS__", ", ".join("{id=%s, x=%.1f, z=%.1f, h={%s}}" % (_lq(r["id"]), r["x"], r["z"], ", ".join(str(int(h_)) for h_ in r["h"])) for r in (cfg or {}).get("rwys", []))).replace("__RWYLEN__", f"{RUNWAY_HALF_LEN_M:.0f}").replace("__RWYWID__", f"{RUNWAY_HALF_WIDTH_M:.0f}").replace("__SCRUB__", sc).replace("__SCRUBFRAC__", repr(float(SCRUB_LOSS_FRAC))).replace("__SCRUBGRACE__", f"{float(SCRUB_STRIKE_GRACE_S):.0f}").replace("__SCRUBLEAD__", f"{float(SCRUB_COVER_LEAD_S):.0f}").replace("__CASDONE__", cd_).replace("__CASDONEFRAC__", repr(float(CAS_DONE_FRAC))).replace("__CASLEASH__", f"{float(CAS_LEASH_M):.0f}")
            .replace("__GATEKM__", str(int(gate_km))).replace("__AITEST__", "true" if ai_test else "false").replace("__GATETEST__", _gate_test_lua()).replace("__GATES__", gt).replace("__RUINS__", ru).replace("__CAMPAIGN__", campaign_id).replace("__SORTIE__", str(sortie))
            .replace("__PKG__", package_id).replace("__DESPAWN__", tbl).replace("__PLAYER__", player_name)
            .replace("__PGROUP__", _lua_str(group)).replace("__SOUND__", sound).replace("__SOUND_YOU__", sound_you).replace("__CALLS__", cl).replace("__UFLT__", uf).replace("__BTGT__", btg).replace("__BOMBFAR__", str(int(BOMB_FAR_KM)))
            .replace("__ENEMYAIR__", ea).replace("__SITES__", st).replace("__JAMCFG__", _jamcfg()).replace("__ECMP__", ecm_player if ecm_player in ("live", "f10") else "").replace("__ECMMSG__", "1" if ecm_msg else "0")
            .replace("__TUNEF__", ", ".join(str(int(f)) for f in (tune_flags or []))).replace("__TUNEMHZ__", f"{float(tune_mhz):.3f}").replace("__AWUNIT__", _lua_str(awacs_unit))
            .replace("__DMGL__", ", ".join(f"[{_lq(k)}]={_lq(v)}" for k, v in (dmg or {}).items())).replace("__DMGON__", "true" if dmg_on else "false").replace("__JAMS__", ", ".join(f"[{_lq(k)}]={int(v)}" for k, v in (jams or {}).items()))
            .replace("__JAMW__", ", ".join(f"[{_lq(k)}]={{{float(a):.0f}, {float(b):.0f}}}" for k, (a, b) in (jamw or {}).items()))
            .replace("__WATCH__", ", ".join(_lq(n) for n in (watch or []))).replace("__DONEAFTER__", f"{float(done_after):.0f}").replace("__AWACS__", _lua_str(awacs)).replace("__SPLASH__", "true" if splash else "false")
            .replace("__RWYQ__", ", ".join(f'{{g={_lq(q["g"])}, f={int(q["f"])}, b={_lq(q["b"])}' + (f', t={int(q["t"])}' if q.get("t") is not None else '') + '}' for q in (rwyq or []))).replace("__PRWY__", _lua_str(prwy))
            .replace("__COVER__", ", ".join(f'{{g={_lq(c["g"])}, n={int(c["n"])}, bf={int(c["bf"])}, rf={int(c["rf"])}, u={float(c["u"]):.0f}}}' for c in (cover or [])))
            .replace("__ALERTS__", ", ".join(f'{{g={_lq(a["g"])}, f={int(a["f"])}, b={_lq(a["b"])}, ty={_lq(a["ty"])}, sq={_lq(a.get("sq", ""))}}}' for a in (alerts or [])))
            .replace("__PHOME__", ("{ x = %.1f, z = %.1f }" % tuple((cfg or {})["phome"])) if (cfg or {}).get("phome") else "nil")
            .replace("__SAMNUM__", ", ".join("{%s, %s}" % (_lq(part), _lq(word)) for part, word in SAM_NUMBER_WORDS))
            .replace("__MAGVAR__", "%.1f" % float((cfg or {}).get("magvar", 0.0)))
            .replace("__BLUEPLACES__", ", ".join(f"[{_lq(n_)}]=true" for n_ in (cfg or {}).get("blue_places", [])))
            .replace("__CVREC__", _cvrec_lua((cfg or {}).get("cvrec")))
            .replace("__RECOV__", _recov_lua((cfg or {}).get("recov")))
            .replace("__CFG__", json.dumps({k: v for k, v in (cfg or {}).items() if k not in ("cvrec", "recov", "rwys", "craters", "blue_places", "magvar")}).replace("'", "")))


def _recov_lua(rs) -> str:
    """v0.41.25: the recovery net's entries as a Lua list: group, carrier unit ("" for a field), x / z, radius (m), earliest time (s)."""
    return ", ".join(f'{{ g={_lq(r["g"])}, cv={_lq(r.get("cv") or "")}, x={float(r["x"]):.1f}, z={float(r["z"]):.1f}, r={float(r["r"]):.0f}, '
                     f't={float(r["t"]):.0f}, t2={float(r.get("t2", r["t"] + 1e6)):.0f}, dwell={float(r.get("dwell", 0)):.0f} }}' for r in (rs or []))


def _cvrec_lua(cv) -> str:
    """v0.41.17: the carrier recovery watch for your wingmen: the carrier unit, the radius (m) and the earliest time (s)."""
    if not cv:
        return ""
    if cv.get("cv"):
        return f'cv={_lq(cv["cv"])}, r={float(cv.get("r", 18520)):.0f}, t={float(cv.get("t", 0)):.0f}'
    return f'x={float(cv["x"]):.1f}, z={float(cv["z"]):.1f}, r={float(cv.get("r", 18520)):.0f}, t={float(cv.get("t", 0)):.0f}'


def install_hook(mission, campaign_id: str, sortie: int, package_id: str, despawn_names: list, player_name: str = "",
                 group: str = "", calls: list | None = None, wps: list | None = None, sound: str = "", sound_you: str = "", flights: dict | None = None,
                 enemy_air: list | None = None, sites: list | None = None, ruins: list | None = None, gates: list | None = None, ai_test: bool = False, gate_km: float = 40, jams: dict | None = None, jamw: dict | None = None,
                 watch: list | None = None, done_after: float = 0, awacs: str = "AWACS", splash: bool = False,
                 rwyq: list | None = None, prwy: str = "", alerts: list | None = None, cfg: dict | None = None, cover: list | None = None, ecm_player: str = "", ecm_msg: bool = True,
                 tune_flags: list | None = None, tune_mhz: float = 0.0, awacs_unit: str = "", dmg: dict | None = None, dmg_on: bool = False, scrub: list | None = None, casdone: list | None = None, bomb_tgt: dict | None = None) -> None:
    """Embed the results hook. NOTE: DoScript needs String(<the script itself>), NOT mission.string(...): the latter stores a
    translation KEY and DCS then tries to run the key's name as code ('DictKey_Translation_5: = expected')."""
    from dcs.triggers import TriggerStart
    from dcs.action import DoScript
    from dcs.translation import String
    t = TriggerStart(comment="SQE debrief hook")
    t.add_action(DoScript(String(lua_hook(campaign_id, sortie, package_id, despawn_names, player_name, group, calls, wps, sound, sound_you, flights, enemy_air, sites, ruins, gates, ai_test, gate_km, jams, jamw, watch, done_after, awacs, splash, rwyq, prwy, alerts, cfg, cover, ecm_player, ecm_msg, tune_flags, tune_mhz, awacs_unit, dmg, dmg_on, scrub, casdone, bomb_tgt))))
    mission.triggerrules.triggers.append(t)


@dataclass
class Manifest:
    campaign_id: str
    sortie: int
    package_id: str
    day: int
    player_unit: str = ""
    built_at: float = field(default_factory=time.time)
    groups: list = field(default_factory=list)
    cur_pkg: str = ""                      # package whose groups are being added right now (merged missions hold several)
    merged: list = field(default_factory=list)   # extra packages folded into this mission: id, number, objective, tot_s...
    ruins: list = field(default_factory=list)    # earlier packages whose strike is shown as ruins: id, number

    def add(self, kind: str, ref: str, units: list, **extra) -> None:
        if self.cur_pkg:
            extra.setdefault("pkg", self.cur_pkg)
        self.groups.append({"kind": kind, "ref": ref, "units": units, **extra})

    def mark_primary(self, ref: str, pkg_id: str) -> None:
        """A target that is already live (spawned for another package of this mission) is also this package's primary target."""
        for g in self.groups:
            if g["kind"] == "asset" and g["ref"] == ref:
                g.setdefault("primary_pkgs", [])
                if pkg_id not in g["primary_pkgs"]:
                    g["primary_pkgs"].append(pkg_id)

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, d):
        return cls(**d)


def read_state_file(path: Path, manifest: Manifest, min_mtime: float | None = None) -> tuple:
    """-> (status, data). status: 'none' | 'stale' | 'mismatch' | 'busy' | 'ok'."""
    path = Path(path)
    if not path.exists():
        return "none", None
    if min_mtime is not None and path.stat().st_mtime < min_mtime:
        return "stale", None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "busy", None                   # DCS is mid-write; try again next poll
    if data.get("campaign") != manifest.campaign_id or data.get("sortie") != manifest.sortie:
        return "mismatch", data
    return "ok", data


def tally(state: CampaignState, manifest: Manifest, data: dict) -> dict:
    """Live casualty counts for the waiting window."""
    lost = set(data.get("dead", [])) | set(data.get("ejected", []))
    t = {"blue_air_total": 0, "blue_air_lost": 0, "blue_ground_total": 0, "blue_ground_lost": 0, "red_air_total": 0, "red_air_lost": 0,
         "red_ground_total": 0, "red_ground_lost": 0, "landed": 0, "red_landed": 0}
    down = set(data.get("landed", []))
    for g in manifest.groups:
        n_dead = sum(1 for u in g["units"] if u in lost)
        if g["kind"] == "friendly":
            t["landed"] += sum(1 for u in g["units"] if u in down)      # this side only: the raw list also holds red aircraft that landed
            t["blue_air_total"] += len(g["units"]); t["blue_air_lost"] += n_dead
        elif g["kind"] == "friendly_ground":
            t["blue_ground_total"] += len(g["units"]); t["blue_ground_lost"] += n_dead
        elif g["kind"] == "enemy_air":
            t["red_landed"] += sum(1 for u in g["units"] if u in down)
            t["red_air_total"] += len(g["units"]); t["red_air_lost"] += n_dead
        elif g["kind"] == "asset":
            t["red_ground_total"] += len(g["units"]); t["red_ground_lost"] += n_dead
    return t


def _plan_entry(state, pkg_id: str, pending: dict | None = None) -> dict:
    """The package dict for an id. The flown package's own `package_dict` first (it holds the support flights attached at build time, the plan's copy does not), else the campaign plan."""
    pd = (pending or {}).get("package_dict") or {}
    if pd.get("id") == pkg_id:
        return pd
    return next((p for p in (state.plan or []) if p.get("id") == pkg_id), {})


def _clock_hm(start: str, add_s: float) -> str:
    """'HH:MM' of the mission start ('HH:MM...') plus add_s seconds (the builder's own `clock`, minus the seconds)."""
    s = str(start or "00:00")
    t = (int(s[:2]) * 3600 + int(s[3:5]) * 60 + int(add_s)) % 86400
    return f"{t // 3600:02d}:{t % 3600 // 60:02d}"


def _wording_runway(hits: int, need: int) -> str:
    """The waiting-screen runway status (XO 2026-11-14): no hit counts, nothing until the field is closed."""
    return "RUNWAY CUT, field closed" if hits >= need else ""


def _status_of(obj: dict, manifest: Manifest, data: dict) -> tuple:
    """READ-ONLY (never touches the state): the live status of one job -> (text, has_result). text '' = no status for this kind.
    Reads the same hook fields apply_debrief reads: `dead` / `ejected` against the manifest groups, `rwy`, `gates`, `aborted`."""
    lost = set(data.get("dead", [])) | set(data.get("ejected", []))
    typ, aim, tid = obj.get("type", ""), obj.get("aim", ""), obj.get("target_id", "")
    site = next((g for g in manifest.groups if g["kind"] == "asset" and g["ref"] == tid), None)
    gates = [e for e in (data.get("gates") or []) if e.get("site") == tid]
    if typ == "STRIKE" and aim == "RUNWAY":
        from . import runways as _rw
        n = int((data.get("rwy") or {}).get(tid, 0) or 0)
        return _wording_runway(n, _rw.HITS_TO_CLOSE), n > 0
    if typ == "DEAD" and site is not None:
        units = site["units"]; rad = list(site.get("trk") or []) + list(site.get("srch") or [])
        n_dead = sum(1 for u in units if u in lost); r_dead = sum(1 for u in rad if u in lost)
        if units and n_dead == len(units):
            txt = "site destroyed"
        elif rad and r_dead == len(rad):
            txt = "radars out, SUPPRESSED" + (f", {n_dead} of {len(units)} units lost" if n_dead > r_dead else " (launchers intact)")
        elif rad:
            txt = f"radars {r_dead} of {len(rad)} out" + (f", {n_dead} of {len(units)} units lost" if n_dead else "")
        else:
            txt = f"{n_dead} of {len(units)} units lost"
        if tid in (data.get("aborted") or []) or (gates and gates[-1].get("abort")):
            txt += "; strikers turned back at the radar gate"
        elif gates and gates[-1].get("radars", 1) == 0 and r_dead:
            txt += "; radar gate clear"
        return txt, n_dead > 0 or r_dead > 0
    if typ in ("STRIKE", "CAS") and site is not None:
        n_dead = sum(1 for u in site["units"] if u in lost)
        what = "vehicles" if typ == "CAS" else "target units"
        return f"{n_dead} of {len(site['units'])} {what} destroyed", n_dead > 0
    if typ in ("BARCAP", "FLEET_DEFENSE", "COUNTER_AIR"):
        red = [u for g in manifest.groups if g["kind"] == "enemy_air" for u in g["units"]]
        n_dead = sum(1 for u in red if u in lost)
        return (f"{n_dead} of {len(red)} enemy aircraft downed" if red else ""), n_dead > 0
    return "", False


def combat_flight_groups(state, manifest: Manifest, pending: dict | None = None) -> list:
    """Friendly manifest groups that belong to a combat package (the flown one and the merged ones): the plan's flight with NO tag.
    Tagged flights (BASE_BARCAP, CARRIER_BARCAP, HAVCAP, TKR_HAVCAP) are supports; reliefs are copies of them (same id), and alert / standby pairs are
    not plan flights at all, so neither counts. Tankers / AWACS are `support` groups, not `friendly`."""
    ids = [manifest.package_id] + [m["id"] for m in manifest.merged]
    tag = {}
    for pid in ids:
        for f in (_plan_entry(state, pid, pending).get("flights") or []):
            tag[f.get("id")] = f.get("tag", "") or ""
    return [g for g in manifest.groups if g["kind"] == "friendly" and g["ref"] in tag and not tag[g["ref"]]]


def objective_status(state, manifest: Manifest, data: dict, pending: dict | None = None) -> list:
    """S77: the live status of the flown job and of every merged package, for the waiting window. READ-ONLY: nothing in `state` changes
    (apply_debrief at Accept stays the authority). -> [{objective, kind, text, tot_s, has_result}], the flown package first (tot_s None)."""
    out = []
    pk = _plan_entry(state, manifest.package_id, pending)
    o = (pk.get("objective") or {}) if pk else {}
    txt, res = _status_of(o, manifest, data)
    out.append({"objective": (pending or {}).get("objective") or o.get("description", ""), "kind": o.get("type", ""), "text": txt, "tot_s": None, "has_result": res})
    for m in manifest.merged:
        if m.get("unseen"):
            continue
        mo = (_plan_entry(state, m["id"], pending).get("objective") or {})
        mo = {**mo, "type": mo.get("type") or m.get("type", "")}
        txt, res = _status_of(mo, manifest, data)
        out.append({"objective": m.get("objective", ""), "kind": mo.get("type", ""), "text": txt, "tot_s": float(m.get("tot_s", 0)), "has_result": res})
    return out


ON_TARGET_S = 300     # S87: a package reads "On target" this long after its TOT (no result yet), then "Returning". Judgment call: the attack run and the pull-off take a few minutes


from .textcase import title_case as _title      # S127: the helper moved to textcase.py (assets use it too); _title stays as the alias


_NAME_NOISE = re.compile(r"\s*\((?:\d+% left|\d+ aircraft|enemy [^)]*)\)")                                     # health, aircraft count, force counts: no numbers in the package name
_NAME_VERBS = ("destroy ", "suppress ", "dislodge the enemy forward position, ", "dislodge the ", "clear the air over ")
_NAME_TAILS = (", once its radars are down", " ahead of the strikes")
_NAME_OPENINGS = (("finish off ", "Finish Off"), ("strike ", "Strike"), ("close air support against ", "Close Air Support"),
                  ("intercept a bomber raid on ", "Intercept Raid"), ("intercept a raid on ", "Intercept Raid"), ("combat air patrol over ", "Combat Air Patrol"))


def short_objective(desc: str) -> str:
    """XO 2026-11-15: the waiting window's package name, 'Mission Type: Target Name' in Title Case, from the objective's description. Display only: no package number,
    no percentages or counts, the verb ('destroy', 'suppress') and the trailing clause dropped. A description in no known shape is shown as written, in Title Case."""
    d = _NAME_NOISE.sub("", desc or "").strip()
    typ, tgt = "", d
    if ":" in d:
        typ, tgt = (x.strip() for x in d.split(":", 1))
    else:
        for op, label in _NAME_OPENINGS:
            if d.lower().startswith(op):
                typ, tgt = label, d[len(op):].strip()
                if tgt.lower().startswith("the "):
                    tgt = tgt[4:]
                break
    low = tgt.lower()
    for v in _NAME_VERBS:
        if low.startswith(v):
            tgt = tgt[len(v):]
            if v.startswith("dislodge the enemy"):
                tgt = "enemy forward position, " + tgt
            break
    for t in _NAME_TAILS:
        if tgt.lower().endswith(t):
            tgt = tgt[:-len(t)]
    if typ.lower() == "oca" and tgt.lower().startswith("runway strike, "):
        typ, tgt = "OCA Runway Strike", tgt[len("runway strike, "):]
    typ = "Close Air Support" if typ.lower() == "close air support" else typ
    return _title(f"{typ}: {tgt}" if typ else tgt, keep_caps=True)


def package_rows(state, manifest: Manifest, data: dict, pending: dict | None = None) -> list:
    """S87 (XO 2026-11-14): one row per package for the waiting window's top table, the status never blank: the package's phase (En route, TOT hh:mm / On target / Returning / Complete /
    Scrubbed / Aborted), with the job's result in front once there is one ('Runway cut, returning'). READ-ONLY. -> [{name, text}] sorted by TOT (name = its objective as 'Mission Type: Target Name',
    merged ones the same, no number). Phase from the mission clock against the TOT and from the package's own combat flights (landed / dead / ejected = no longer airborne)."""
    start = ((pending or {}).get("package_dict") or {}).get("start", "00:00")
    now = float(data.get("time", 0) or 0)
    gone = set(data.get("dead", [])) | set(data.get("ejected", [])) | set(data.get("landed", []))
    scrubbed = {e.get("pkg") for e in (data.get("scrub") or [])}
    groups = combat_flight_groups(state, manifest, pending)
    tl = (pending or {}).get("timeline") or {}
    rows = []
    for i, r in enumerate(objective_status(state, manifest, data, pending)):
        if i == 0:
            pid, name, tot = manifest.package_id, short_objective(r["objective"]), (float(tl["tot_s"]) if tl.get("tot_s") is not None else None)
        else:
            m = [x for x in manifest.merged if not x.get("unseen")][i - 1]
            pid, name, tot = m["id"], short_objective(r["objective"]), float(m.get("tot_s", 0))
        mine = [g for g in groups if g.get("pkg") == pid]
        air = sum(1 for g in mine for u in g["units"] if u not in gone)
        res = r["text"] if (r["has_result"] and r["text"]) else ""
        if pid in scrubbed:
            phase = "Scrubbed"
            res = ""
        elif "turned back" in r["text"]:
            phase = "Aborted, turned back at the radar gate"
            res = ""
        elif mine and air == 0:
            phase = "Complete"
        elif tot is None or now < tot:
            phase = "En route" + (f", TOT {_clock_hm(start, tot)}" if tot is not None else "")
        elif now < tot + ON_TARGET_S and not res:
            phase = "On target"
        else:
            phase = "Returning"
        rows.append((tot is None, tot or 0.0, {"name": name, "text": _title(f"{res}, {phase}" if res else phase)}))
    rows.sort(key=lambda r: r[:2])              # XO 2026-11-15: by TOT, earliest first, no TOT last; the flown package is not special (a stable sort keeps the order among equal TOTs)
    return [r[2] for r in rows]


def flight_status(state, manifest: Manifest, data: dict, pending: dict | None = None) -> dict:
    """S77: the overall line's numbers. Combat flights only (see combat_flight_groups); aircraft of a scrubbed package are left out (they never launched or
    are on their way home). -> {total, airborne, next_tot_s (None when no TOT is left)}. airborne counts aircraft neither landed, dead nor ejected."""
    gone = set(data.get("dead", [])) | set(data.get("ejected", [])) | set(data.get("landed", []))
    scrubbed = {e.get("pkg") for e in (data.get("scrub") or [])}
    total = air = 0
    for g in combat_flight_groups(state, manifest, pending):
        if g.get("pkg") in scrubbed:
            continue
        total += len(g["units"]); air += sum(1 for u in g["units"] if u not in gone)
    now = float(data.get("time", 0) or 0)
    tots = [float(m["tot_s"]) for m in manifest.merged if not m.get("unseen")]
    tl = (pending or {}).get("timeline") or {}
    if tl.get("tot_s") is not None:
        tots.append(float(tl["tot_s"]))
    nxt = min((t for t in tots if t > now), default=None)
    return {"total": total, "airborne": air, "next_tot_s": nxt}


def kill_log(manifest: Manifest, data: dict) -> list[str]:
    """'12:34 MiG-29S (Bandit 2-1) killed by F-16C (Viper 1-1) with AIM-120C' for every kill the hook saw."""
    label = {}
    for g in manifest.groups:
        lab = g.get("callsign") or ""
        for i, u in enumerate(g["units"]):
            label[u] = f"{lab}-{i + 1}" if lab and g.get("kind") in ("friendly",) else (lab or "")
    def who(unit, typ):
        l = label.get(unit, "")
        return f"{typ} ({l})" if l else typ
    out = []
    for k in data.get("kills", []) or []:
        t = int(k.get("t", 0))
        w = k.get("w", "?")
        by = who(k.get("k", "?"), k.get("kt", "?")) if k.get("k", "?") != "?" else "unknown"
        out.append(f"{t // 60:02d}:{t % 60:02d}  {who(k.get('v', '?'), k.get('vt', '?'))} killed by {by}" + (f" [{w}]" if w not in ("?", "") else ""))
    return out


def stranded_jets(manifest: Manifest, data: dict) -> dict:
    """S130b (XO 2026-11-22): a blue jet that landed at a field that is not blue's is lost: captured at a red field, interned at a neutral one. -> {unit name: (place, "captured" or "interned")}.
    The hook writes the place's coalition under `landings[unit]["c"]` (0 neutral, 1 red, 2 blue, -1 it could not tell). A save, state file or landing without that number counts as blue (no change)."""
    out = {}
    landings = data.get("landings") or {}
    for g in manifest.groups:
        if g["kind"] != "friendly":
            continue
        for unit_name in g["units"]:
            landing = landings.get(unit_name)
            if not landing:
                continue
            coalition = int(landing.get("c", 2))
            if coalition == 1:
                out[unit_name] = (landing.get("p") or "a red field", "captured")
            elif coalition == 0:
                out[unit_name] = (landing.get("p") or "a neutral field", "interned")
    return out


def apply_debrief(state: CampaignState, manifest: Manifest, data: dict) -> dict:
    """Player-flown package: results are applied 1:1 (no dice). Returns a structured outcome for the debrief screen."""
    stranded = stranded_jets(manifest, data)                 # S130b: landed at a red or neutral field: counts as lost (never twice: a jet that is also dead / ejected is in the set once)
    lost = set(data.get("dead", [])) | set(data.get("ejected", [])) | set(stranded)
    lost_all = lost
    landed = set(data.get("landed", []))
    out = {"blue_losses": [], "red_assets": [], "red_air_lost": 0, "blue_air_lost": 0, "target_damage": 0.0,
           "lines": [], "ended": bool(data.get("mission_ended")), "objective": "", "objective_type": "",
           "player": "airborne", "package_id": manifest.package_id,
           "flights": {}}                                  # v0.41.337: friendly flight id -> {squadron, flew, lost, limped}: what Session._flown_sorties hands to refit.commit_turn
    limped_ = set((data.get("limped") or {}).keys())         # the hook's `limped` object: units that landed or were recovered below LIMP_LIFE (unit name -> hit points left, percent)
    site_cap = {}                                           # v0.41.241: blue supply sites / garrisons: the health the destroyed buildings or vehicles leave (applied after the raid's own hit, so one raid is never counted twice)
    for g in manifest.groups:
        dead = [u for u in g["units"] if u in lost]
        if g["kind"] == "blue_site" and dead and g["units"] and g.get("health_before") is not None:
            site_cap[g["ref"]] = min(site_cap.get(g["ref"], 1.0), float(g["health_before"]) * (len(g["units"]) - len(dead)) / len(g["units"]))
        if g["kind"] == "friendly":
            sq = state.squadrons[g["squadron"]]
            sq.available = max(0, sq.available - len(dead))
            out["flights"][g["ref"]] = {"squadron": g["squadron"], "flew": len(g["units"]), "lost": len(dead),
                                        "limped": sum(1 for u in g["units"] if u in limped_ and u not in lost)}      # v0.41.337: a limping jet that also died is just lost
            out["blue_air_lost"] += len(dead)
            if dead:
                out["blue_losses"].append({"callsign": g.get("callsign", g["ref"]), "lost": len(dead), "total": len(g["units"])})
                out["lines"].append(f"{g.get('callsign', g['ref'])}: lost {len(dead)}/{len(g['units'])} ({sq.name}: {sq.available}/{sq.authorized} left)")
            for unit_name in g["units"]:
                if unit_name in stranded:
                    place, fate = stranded[unit_name]
                    out["lines"].append(f"{g.get('callsign', g['ref'])} landed at {place} and is lost ({fate})")
        elif g["kind"] == "friendly_ground" and str(g.get("ref", "")).startswith("sector:"):
            if g["units"]:                                         # S81/S83: a front battle staged under a flight that is not its CAS: its losses cost the sector's Blue strength like red's column's cost its Red
                from . import ground as _gr3
                st_ = {"blue": "we were pushing", "red": "the enemy was pushing", "hold": "both sides held"}.get(g.get("stance"), "")
                out["lines"].append(f"Front, {g.get('label') or g['ref']}{' (' + st_ + ')' if st_ else ''}: our company lost {len(dead)} of {len(g['units'])} vehicles")
                gl3 = _gr3.front_loss(state, g.get("sector"), len(dead), int(g.get("base_count") or len(g["units"])))
                if gl3:
                    out["lines"].append(gl3)
        elif g["kind"] == "friendly_ground":
            out["ground_total"] = out.get("ground_total", 0) + len(g["units"]); out["ground_lost"] = out.get("ground_lost", 0) + len(dead)
            if g["units"]:
                out["lines"].append(f"Friendly troops: lost {len(dead)} of {len(g['units'])} vehicles")
                out["lines"].append("Front: the line was OVERRUN, the air support did not break the attack in time" if len(dead) * 10 >= len(g["units"]) * 3
                                    else "Front: the line HELD")                # S80: the battle's verdict, in the player's terms (a scripted overrun costs 30 to 80 percent of the company)
                from . import ground as _gr
                gl = _gr.blue_losses(state, g.get("ref", ""), len(dead), len(g["units"]), g.get("base_count")) if dead else None
                if gl:                                                  # the ground war takes the loss from that sector's Blue strength
                    out["lines"].append(gl)
                elif len(dead) * 2 >= len(g["units"]) and g.get("ref") in state.assets and not _gr.active(state):      # the position is overrun
                    a0 = state.assets[g["ref"]]
                    fields = [b for b in state.bases.values() if b.kind.value == "AIRFIELD"]
                    if fields:
                        nb = min(fields, key=lambda b: (b.x - a0.x) ** 2 + (b.y - a0.y) ** 2)
                        from . import sams as _sams
                        _sams.hit_field(state, nb, 0.10)
                        out["lines"].append(f"The position was overrun; the column presses on toward {nb.name}")
        elif g["kind"] == "asset":
            a = state.assets[g["ref"]]
            frac = (len(g["units"]) - len(dead)) / max(1, g["base_count"])
            before = a.health
            from . import ground as _gr2
            a.health = _gr2.column_health(state, a, before, frac)
            from . import works as _wk
            if _wk.is_works(a):                                         # S111: a works takes only a share of what the same bombs take off a depot
                a.health = before - (before - a.health) * _wk.damage_factor(state, a)
            if not g.get("primary") and _gr2.zone_of(state, a.id) is not None:      # S83: a red column hit only in passing loses no more than FRONT_CAP points (as blue's company), a CAS target is not capped
                a.health = max(a.health, before - _gr2.FRONT_CAP / _gr2.MAX_FORCE)
            dmg = before - a.health
            ra_ = {"name": a.name, "before": before, "after": a.health, "kind": a.kind.value, "primary": bool(g.get("primary")),
                   "destroyed": bool(a.destroyed or a.health <= _gr2.DOWN_HEALTH)}          # v0.41.171: tempo credits (tempo.credits)
            out["red_assets"].append(ra_)
            if g.get("primary"):
                out["target_damage"] = 1 - (a.health / before) if before > 0 else 0.0
            if dmg > 0:
                out["lines"].append(f"{a.name}: {strength_word(before)} -> {strength_word(a.health)}")
            rad = list(g.get("trk") or []) + list(g.get("srch") or [])
            if a.kind.value == "SAM" and rad and all(u in lost for u in rad) and not a.destroyed:
                a.suppressed = True; ra_["suppressed"] = True               # SEAD worked: the radars are gone, but the launchers are still there
                out["lines"].append(f"{a.name}: radars destroyed, launchers intact. SUPPRESSED, not dead: it needs a DEAD strike to finish it.")
                if g.get("primary"):
                    out["target_damage"] = max(out["target_damage"], SUPPRESSED_CREDIT)
        elif g["kind"] == "support":                              # v0.41.87: a tanker / AWACS shot down comes off its asset
            if dead:
                from . import support_assets as _sa
                ln = _sa.lose(state, g.get("label", ""), len(dead))
                if ln:
                    out["lines"].append(ln)
        elif g["kind"] == "enemy_air":
            w = state.enemy_air_at(g["ref"])
            if w and dead:
                w.lose(g.get("ac"), len(dead))                    # v0.41.53: the loss comes off the squadron that flew that type
                out["red_air_lost"] += len(dead)
                out["lines"].append(f"{len(dead)} enemy aircraft from {state.assets[g['ref']].name} destroyed")
    # a raid you were sent to stop: bombers still alive when they reached their base got through
    t_now = float(data.get("time", 0) or 0)
    from . import fleet as _fleet
    cv_sunk_ = _fleet.sunk_in(state, data)                      # v0.41.257: the carrier went down in this mission: the ship's loss replaces the old deck-hit model
    cv_ = _fleet.carrier_base(state)
    for g in manifest.groups:
        if g["kind"] == "enemy_air" and g.get("raid_base") and g["raid_base"] in state.bases:
            alive = [u for u in g["units"] if u not in lost]
            where = g.get("raid_label") or state.bases[g["raid_base"]].name
            wing = state.enemy_air_at(g["ref"])
            if len(alive) < len(g["units"]):
                out["lines"].append(f"Raid: {len(g['units']) - len(alive)} of {len(g['units'])} attack aircraft shot down")
            if cv_sunk_ and cv_ is not None and g["raid_base"] == cv_.id:
                continue
            rg_ = (data.get("rgate") or {}).get(g.get("raid_group", ""), {}) if g.get("raid_gate_s") is not None else {}
            arrive_ = g.get("raid_arrive_s", 0.0)
            if rg_.get("open") is not None:                       # v0.41.126: held at the gate until the radars went down: it can arrive no sooner than that plus the leg in
                arrive_ = max(arrive_, float(rg_["open"]) + float(g["raid_gate_s"]))
            if alive and g.get("raid_gate_s") is not None and rg_.get("abort") is not None and rg_.get("open") is None:
                out["lines"].append(f"Raid on {where}: the radars were still up, so the attack aircraft turned back at the gate; no bombs fell")
            elif alive and g.get("raid_gate_s") is not None and rg_.get("open") is None:
                out["lines"].append(f"Raid on {where}: the attack aircraft were still held outside the defences; no bombs fell")
            elif alive and t_now >= arrive_:
                from . import raids as _rd
                import random as _rnd
                out["lines"].append(f"Raid on {where}: {len(alive)} attack aircraft got through")
                out["lines"] += [x.strip() for x in _rd.hit(state, g["raid_base"], wing, _rnd.Random(f"{state.campaign_id}:{state.day}:through"), len(alive), g.get("raid_aim", ""), g.get("ac"))]
            elif alive:
                from . import raids as _rd
                import random as _rnd
                rr = _rnd.Random(f"{state.campaign_id}:{state.day}:early")
                if rr.random() < 0.5:
                    out["lines"].append(f"Raid: you left before the raiders arrived; {len(alive)} got through to {where}")
                    out["lines"] += [x.strip() for x in _rd.hit(state, g["raid_base"], wing, rr, len(alive), g.get("raid_aim", ""), g.get("ac"))]
                else:
                    out["lines"].append("Raid: you left before the raiders arrived; the defences stopped them")
            else:
                out["lines"].append(f"Raid on {where}: stopped, no bombs fell")
    for aid_, cap_ in site_cap.items():                     # ...the buildings that really burned count: the site is at most that healthy
        a_ = (getattr(state, "blue_assets", None) or {}).get(aid_)
        if a_ is not None and cap_ < a_.health - 1e-6:
            out["lines"].append(f"{a_.name}: {strength_word(a_.health)} -> {strength_word(cap_)} (buildings destroyed)")
            a_.health = max(0.0, cap_)
    follow_ = any((p_.get("objective") or {}).get("after") for p_ in (state.plan or []) if p_.get("id") == data.get("package"))      # v0.41.158: a strike / CAS behind a SEAD
    for ref in data.get("aborted", []) or []:
        a = state.assets.get(ref)
        if a is not None:
            out["lines"].append((f"Attack called off behind {a.name}" if follow_ else f"DEAD called off on {a.name}") +
                                ": its radars were still up when the strike flight reached the gate, so it turned back without attacking.")
    from . import runways as _rw                           # v0.41.254: bomb impacts on a runway (the hook counts them); 3 or more close the field
    for fid_, n_ in sorted((data.get("rwy") or {}).items()):
        if fid_ in state.assets or fid_ in state.bases:
            ln_ = _rw.add_hits(state, fid_, int(n_))
            if ln_:
                out["lines"].append(ln_)
    obj_rw = next(((p_.get("objective") or {}) for p_ in (state.plan or []) if p_.get("id") == data.get("package")), {})
    if obj_rw.get("aim") == "RUNWAY" and obj_rw.get("type") == "STRIKE":        # S75: a runway has no health, so the job is graded by the crater, not by `target_damage` (it read "0% destroyed" next to "CRATERED")
        tid_rw = obj_rw.get("target_id", "")
        n_rw = int((data.get("rwy") or {}).get(tid_rw, 0) or 0)
        closed_rw = _rw.is_closed(state, tid_rw) and n_rw > 0
        out["runway"] = {"hits": n_rw, "closed": closed_rw, "hours": _rw.hours_left(state, tid_rw) if closed_rw else 0}
        if closed_rw:
            out["target_damage"] = max(out["target_damage"], RUNWAY_CREDIT)
    # alert / scramble groups (v0.40.8): called, airborne, or stuck on the ground; and the build's settings, so test runs can be told apart
    ms_ = lambda t_: f"{int(t_) // 60:d}:{int(t_) % 60:02d}"                  # v0.41.208 (XO): scrambles are numbered in the order the build lists them (the briefing's QRA list uses the same numbers)
    owner_ = {q.id: q for w_ in state.enemy_air for q in w_.sqns}
    pkg_ = next((p_ for p_ in (state.plan or []) if p_.get("id") == data.get("package")), None)
    st_min_ = None                                                          # v0.41.343 (Phase 6a): the mission's start, absolute minute (the package's start time on today's clock)
    if pkg_ and pkg_.get("start"):
        from . import clock as _clk
        st_min_ = _clk.day_start_minute(state.day) + int(str(pkg_["start"])[:2]) * 60 + int(str(pkg_["start"])[3:5])
    flown_ = []
    for n_, al in enumerate(data.get("alerts", []) or [], 1):
        if al.get("called") is None:
            continue
        if al.get("air") is not None and al.get("sq") in owner_:             # a scramble that got airborne is a flown sortie of the squadron it came from; called but stuck, or never called, costs nothing
            gr_ = next((g_ for g_ in manifest.groups if g_.get("grp") == al.get("g") and g_["kind"] == "enemy_air"), None)
            n_fl_ = len(gr_["units"]) if gr_ else 2
            flown_.append({"unit": owner_[al["sq"]], "side": "red", "launch_min": (st_min_ if st_min_ is not None else _refit.now_min(state)) + int(al["called"]) // 60, "flew": n_fl_,
                           "lost": sum(1 for u_ in (gr_["units"] if gr_ else []) if u_ in lost), "limped": None})       # the group's dead were taken off `available` above: not counted twice
        who_ = f"Scramble {n_} ({al.get('ty', '?')}, {al.get('b', '?')})"
        if al.get("air") is not None:
            out["lines"].append(f"{who_}: ordered {ms_(al['called'])}, airborne +{ms_(al['air'] - al['called'])}")
        else:
            out["lines"].append(f"{who_}: ordered {ms_(al['called'])}, " + ("NEVER GOT AIRBORNE (stuck on the ground)" if al.get("stuck") else "not airborne yet when the mission ended"))
    # v0.41.92: fuel. The lead's fuel is tracked every 30 s (`tracks`: [t, x, z, alt_m, fuel_%, kts]); a flight that ended the mission low explains the
    # pairs that went home early (bingo). Reported for every AI group that was airborne and ended at BINGO_REPORT_PCT or less.
    ty_ = {a_["g"]: a_.get("ty", "") for a_ in (data.get("alerts") or [])}
    for gn_, tr_ in sorted((data.get("tracks") or {}).items()):
        fl_ = [p_ for p_ in tr_ if len(p_) >= 6 and p_[3] > 300 and p_[5] > 120 and 0 <= p_[4] <= 100]
        if len(fl_) < 4:
            continue
        last_ = fl_[-1]
        if last_[4] > BINGO_REPORT_PCT:
            continue
        cross_ = next((p_ for p_ in fl_ if p_[4] <= BINGO_PCT), None)
        out["lines"].append(f"Fuel: {gn_}{' (' + ty_[gn_] + ')' if ty_.get(gn_) else ''} airborne {int(fl_[0][0]) // 60}-{int(last_[0]) // 60} min, fuel {fl_[0][4]}% to {last_[4]}%"
                            + (f", at bingo ({BINGO_PCT}%) from {int(cross_[0]) // 60} min" if cross_ else ""))
    if flown_:
        import random as _rnd2
        ra_ = state.red_air or {}
        for unit_, n_srv_, _lp, _sh in _refit.commit_turn(state, flown_, _rnd2.Random(f"{state.campaign_id}:{state.day}:{state.turn}:scr")):
            if ra_.get("turn") == state.turn and isinstance(ra_.get("avail0"), dict) and unit_.id in ra_["avail0"]:
                ra_["avail0"][unit_.id] = max(0, int(ra_["avail0"][unit_.id]) - n_srv_)        # Session._red_sorties reads losses as avail0 less available: these jets went to refit, they were not lost
    cf_ = data.get("cfg") or {}
    if cf_:
        sp_ = data.get("splash") or {}
        out["lines"].append(f"Settings: splash damage {'ON' if cf_.get('splash_damage') else 'off'}" +
                            (f" ({sp_.get('blasts', 0)} blasts, {sp_.get('kills', 0)} kills)" if cf_.get("splash_damage") else "") +
                            f", ECM script {'ON' if cf_.get('ecm_script') else 'off'}, build v{cf_.get('version', '?')}")
    # merged missions: one line per folded-in package, from what really happened (reported only if its strike time was reached)
    t_end = float(data.get("time", 0) or 0)
    out["packages"] = []
    for m in manifest.merged:
        dmg = None
        for g in manifest.groups:
            if g["kind"] == "asset" and m["id"] in (g.get("primary_pkgs") or []):
                a = state.assets[g["ref"]]
                dmg = 1 - (a.health / g["health_before"]) if g.get("health_before") else 0.0
        fl = [g for g in manifest.groups if g["kind"] == "friendly" and g.get("pkg") == m["id"]]
        n_lost = sum(1 for g in fl for u in g["units"] if u in lost_all)
        tot = sum(len(g["units"]) for g in fl)
        done = t_end >= m["tot_s"] + 90 or m.get("type") == "FLEET_DEFENSE"      # v0.41.351: a merged raid is settled by the mission whatever the clock said (the group loop above applied it)
        if m.get("unseen"):
            continue                                         # a raid blue did not detect gets no package line (the raid's own events above stay)
        if str(m.get("objective", "")).startswith("Fighter Sweep"):
            dmg = None                                       # a sweep fights the air over the target area; the target itself is the strikers' job
        out["packages"].append({"number": m["number"], "objective": m["objective"], "damage": dmg, "lost": n_lost, "total": tot, "resolved": done})
        out["lines"].append(f"Package #{m['number']} ({m['objective']}): " + (f"{bda_text(dmg)}, lost {n_lost}/{tot} aircraft" if done and dmg is not None else
                            (f"flown to the end: lost {n_lost}/{tot} aircraft" if done else "you were out of the mission before its strike; it is resolved by the war simulation")))
    # SEAD first: a SEAD package that was really flown settles whether the site is blind (the DEAD stage and the failed-days count read it)
    from .war import note_sead as _note_sead
    t_end2 = float(data.get("time", 0) or 0)
    flown_ids = [data.get("package")] + [m["id"] for m in manifest.merged if t_end2 >= m["tot_s"] + 90]
    for pk in state.plan:
        o_ = pk.get("objective", {})
        if pk.get("id") in flown_ids and o_.get("type") == "DEAD" and o_.get("aim") in ("SEAD", "STANDOFF") and o_.get("target_id") in state.assets:
            a_ = state.assets[o_["target_id"]]
            _note_sead(state, a_.id, bool(a_.suppressed or a_.destroyed))
            out["lines"].append(f"SEAD on {a_.name}: " + (("its radars are out" + ("" if o_.get("aim") == "STANDOFF" else "; the Close DEAD package can go in")) if (a_.suppressed or a_.destroyed) else ("its radars are still up" + ("" if o_.get("aim") == "STANDOFF" else "; the Close DEAD package will not commit"))))
    pdat = data.get("player") or {}
    t0, t1 = pdat.get("takeoff"), pdat.get("landed")
    flight_s = (t1 - t0) if (t0 is not None and t1 is not None) else ((data.get("time", 0) - t0) if t0 is not None else 0)
    out["pilot"] = {"flight_s": max(0, int(flight_s)), "ka": int(pdat.get("ka", 0)), "kg": int(pdat.get("kg", 0)),
                    "ks": int(pdat.get("ks", 0)), "landed": t1 is not None}
    pu = manifest.player_unit
    if pu in data.get("ejected", []):
        out["player"] = "ejected"
    elif pu in data.get("dead", []):
        out["player"] = "lost"
    elif pu in stranded:
        out["player"] = stranded[pu][1]                 # S130b: "captured" or "interned": you walked away from it, the jet is gone
    elif pu in landed:
        out["player"] = "recovered"
    out["lines"] += _fleet.apply_debrief(state, manifest, data)             # v0.41.257: ships sunk in the mission (the carrier, its escorts)
    out["kill_log"] = kill_log(manifest, data)
    for ln in out["lines"]:
        state.note(ln)
    if not out["lines"]:
        out["lines"].append("No changes to the campaign.")
    return out
