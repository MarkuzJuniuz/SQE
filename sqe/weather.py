"""Weather: a believable day-to-day picture, and what it means for the weapons you can use.

Modes (Settings > Weather)
  clear        what SQE always did: no cloud, 80 km visibility
  fixed        one of clear / scattered / broken / overcast / rain / storm, every day
  procedural   the theatre's climate (monthly cloud and rain odds in the theatre pack) drives a slow day-to-day chain

How procedural works
  * Six ordered states: CLEAR, SCATTERED, BROKEN, OVERCAST, RAIN, STORM. Each month's odds of each state come from the pack's
    `climate` block (sunshine and rain-day normals) with a maximum-entropy fit, so the long-run average matches the climate.
  * Tomorrow's state is today's state or a NEIGHBOUR on that scale (a Metropolis walk), never a jump: clear to storm takes days.
  * Inside a day the weather drifts linearly from 06:00 of today's state to 06:00 of tomorrow's, so a sortie at 06:30 and one at
    18:00 see a gradual change, never a flip. Everything is seeded from the campaign id and the day, so the plan, the mission
    and the briefing always agree, and a saved campaign always shows the same weather.

Weapons
  Weapon classes are read from DCS's own weapon names. Laser and electro-optical weapons need a clear line of sight; the thresholds
  below start from the USAF's Desert Storm weather report (laser-guided bombs need a cloud-free line of sight from release to
  target; forecast threshold: ceilings at or above 10,000 ft) and are otherwise hand-tuned for play. GPS weapons, anti-radiation
  missiles and air-to-air weapons ignore the weather. `adapt()` swaps what the weather rules out for a GPS weapon on the same
  pylon; `assess()` says whether a package can fly at all.
"""
from __future__ import annotations
import math
import random
import re
from dataclasses import dataclass, asdict, field
from datetime import date, timedelta

STATES = ["CLEAR", "SCATTERED", "BROKEN", "OVERCAST", "RAIN", "STORM"]
LABEL = {"CLEAR": "Clear", "SCATTERED": "Scattered cloud", "BROKEN": "Broken cloud", "OVERCAST": "Overcast", "RAIN": "Rain",
         "STORM": "Heavy rain and storms"}
COVER = [0.05, 0.30, 0.70, 1.0, 1.0, 1.0]
MODES = {"clear": "Clear (always)", "procedural": "Procedural (from the theatre's climate)", "scattered": "Scattered cloud (always)",
         "broken": "Broken cloud (always)", "overcast": "Overcast (always)", "rain": "Rain (always)", "storm": "Heavy rain and storms (always)"}
FT, KT = 0.3048, 1.943844

# per state: (cover lo, hi), (cloud base ft AGL lo, hi), (visibility km lo, hi), ground wind factor, turbulence, QNH mmHg offset, temp offset C
_P = {
    "CLEAR":     ((0.00, 0.10), (25000, 25000), (35, 70), 0.8, 0, +3, +1.5),
    "SCATTERED": ((0.20, 0.40), (4500, 9000), (25, 50), 0.9, 2, +2, +0.5),
    "BROKEN":    ((0.60, 0.85), (2500, 7000), (15, 35), 1.0, 4, 0, 0.0),
    "OVERCAST":  ((1.00, 1.00), (1200, 4500), (8, 20), 1.2, 6, -2, -0.5),
    "RAIN":      ((1.00, 1.00), (1000, 3000), (4, 10), 1.5, 10, -6, -1.5),
    "STORM":     ((1.00, 1.00), (700, 2000), (2, 6), 2.4, 22, -12, -3.0),
}
# DCS cloud presets (dcs.cloud_presets.Clouds member names) that suit each state
_PRESETS = {
    "SCATTERED": ["LightScattered1", "LightScattered2", "HighScattered1", "HighScattered2", "HighScattered3", "Scattered1", "Scattered2"],
    "BROKEN": ["Scattered3", "Scattered4", "Scattered5", "Scattered6", "Scattered7", "Broken1", "Broken2", "Broken3", "Broken4"],
    "OVERCAST": ["Broken5", "Broken6", "Broken7", "Broken8", "Overcast1", "Overcast2", "Overcast3", "Overcast4", "Overcast5", "Overcast6", "Overcast7"],
    "RAIN": ["LightRain1", "LightRain2", "LightRain3", "OvercastAndRain1", "OvercastAndRain2", "OvercastAndRain3"],
    "STORM": ["OvercastAndRain1", "OvercastAndRain2", "OvercastAndRain3"],
}
DEFAULT_CLIMATE = {"sun_frac": [0.45] * 12, "rain_frac": [0.40] * 12, "wind_ms": [4.0] * 12, "fog": [0.03] * 12}


@dataclass
class Wx:
    state: str = "CLEAR"
    cover: float = 0.0
    base_ft: float = 25000.0          # lowest cloud base above ground (feet); 25000 = none
    vis_km: float = 80.0
    rain: int = 0                     # 0 none, 1 rain, 2 heavy rain
    fog_m: float = 0.0                # fog visibility in metres when there is fog (0 = none)
    wind_from: float = 270.0          # degrees, the direction the wind blows FROM
    wind_kt: float = 5.0
    turb: float = 0.0
    qnh_mmhg: float = 760.0
    temp_c: float = 20.0
    preset: str = ""                  # dcs.cloud_presets.Clouds member name ('' = no clouds)
    base_m: float = 0.0               # cloud base (metres) as given to DCS (clamped into the preset's range)
    mode: str = "clear"

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict | None) -> "Wx | None":
        if not d:
            return None
        ok = {k: v for k, v in d.items() if k in Wx.__dataclass_fields__}
        return Wx(**ok)

    @property
    def ceiling_ft(self) -> float:
        return self.base_ft if self.cover >= 0.5 else 25000.0


# ---------------------------------------------------------------------------------------------------------------------------
def _rng(*parts) -> random.Random:
    return random.Random(":".join(str(p) for p in parts))      # a str seed is hashed with SHA-512: stable across runs and machines


def _fit(target_mean: float) -> list:
    """Weights over the four dry states with the requested mean cover (maximum entropy: w ~ exp(lambda * cover))."""
    c = COVER[:4]
    lo, hi = -40.0, 40.0
    t = min(max(target_mean, 0.07), 0.93)
    for _ in range(80):
        lam = (lo + hi) / 2
        w = [math.exp(lam * x) for x in c]
        m = sum(wi * x for wi, x in zip(w, c)) / sum(w)
        lo, hi = (lam, hi) if m < t else (lo, lam)
    w = [math.exp(((lo + hi) / 2) * x) for x in c]
    s = sum(w)
    return [x / s for x in w]


def stationary(clim: dict, month: int) -> list:
    """Long-run odds of the six states in a month, from the climate block."""
    sun = clim["sun_frac"][month - 1]
    rainy = clim["rain_frac"][month - 1]
    rain, storm = 0.5 * rainy, 0.10 * rainy
    dry = max(0.05, 1.0 - rain - storm)
    need = ((1.0 - sun) - (rain + storm)) / dry
    pi = [x * dry for x in _fit(need)] + [rain, storm]
    s = sum(pi)
    return [x / s for x in pi]


_CHAIN: dict = {}


def _sig(clim: dict) -> int:
    return hash((tuple(clim["sun_frac"]), tuple(clim["rain_frac"])))


def _state_on(campaign_id: str, start: date, k: int, clim: dict) -> int:
    """State index on campaign day k (0-based): a neighbour-only Metropolis walk whose long-run odds are the month's climate."""
    seq = _CHAIN.setdefault((campaign_id, start.toordinal(), _sig(clim)), [])
    while len(seq) <= k:
        step = len(seq)
        pi = stationary(clim, (start + timedelta(days=step)).month)
        r = _rng(campaign_id, "wx", step)
        if not seq:
            x, acc, s = r.random(), 0.0, len(pi) - 1
            for j, p in enumerate(pi):
                acc += p
                if x < acc:
                    s = j
                    break
        else:
            s = seq[-1]
            if r.random() >= 0.35:                               # 35% of days simply repeat
                nb = s - 1 if r.random() < 0.5 else s + 1
                if 0 <= nb < len(pi) and r.random() < min(1.0, pi[nb] / max(pi[s], 1e-9)):
                    s = nb
        seq.append(s)
    return seq[k]


def _anchor(campaign_id: str, k: int, state: str, clim: dict, month: int) -> dict:
    """The 06:00 picture of a day in `state`, with seeded variation."""
    r = _rng(campaign_id, "wxp", k)
    (c0, c1), (b0, b1), (v0, v1), wf, turb, dq, dt = _P[state]
    u = lambda a, b: a + (b - a) * r.random()
    return {"cover": u(c0, c1), "base": u(b0, b1), "vis": u(v0, v1), "wind": clim["wind_ms"][month - 1] * wf * u(0.8, 1.25),
            "dir": u(0, 360), "turb": turb, "qnh": 761 + dq + u(-2, 2), "dt": dt + u(-2.0, 2.0),
            "fog": r.random() < clim["fog"][month - 1] and state in ("OVERCAST", "RAIN", "SCATTERED", "BROKEN")}


def _fixed(state: str, clim: dict, month: int) -> dict:
    (c0, c1), (b0, b1), (v0, v1), wf, turb, dq, dt = _P[state]
    return {"cover": (c0 + c1) / 2, "base": (b0 + b1) / 2, "vis": (v0 + v1) / 2, "wind": clim["wind_ms"][month - 1] * wf, "dir": 250.0,
            "turb": turb, "qnh": 761 + dq, "dt": dt, "fog": False}


def _finish(state: str, a: dict, b: dict | None, f: float, hour: float, temp_month: float, mode: str, rng) -> Wx:
    mix = lambda k: a[k] + ((b[k] - a[k]) * f if b else 0.0)
    cover, base, vis = mix("cover"), mix("base"), mix("vis")
    if state == "CLEAR":
        cover, base = min(cover, 0.1), 25000.0
    wind_dir = a["dir"] + ((((b["dir"] - a["dir"] + 540) % 360) - 180) * f if b else 0.0)
    fog_m = 0.0
    if (a["fog"] or (b and b["fog"] and f > 0.7)) and hour < 9.5:
        fog_m = 500.0 + 3500.0 * min(1.0, max(0.0, (hour - 5.0) / 4.5))     # thick at dawn, burns off towards mid-morning
        vis = min(vis, fog_m / 1000.0)
    rain = 2 if state == "STORM" else 1 if state == "RAIN" else 0
    preset, base_m = "", 0.0
    if state != "CLEAR":
        from dcs.cloud_presets import Clouds
        pool = _PRESETS.get(state) or _PRESETS["SCATTERED"]
        want = base * FT
        ok = [n for n in pool if Clouds[n].value.min_base <= want <= Clouds[n].value.max_base]
        preset = rng.choice(ok or pool)
        pv = Clouds[preset].value
        base_m = min(max(want, pv.min_base), pv.max_base)
        base = base_m / FT
    return Wx(state=state, cover=round(cover, 2), base_ft=round(base), vis_km=round(vis, 1), rain=rain, fog_m=round(fog_m),
              wind_from=round(wind_dir) % 360, wind_kt=round(mix("wind") * KT, 1), turb=round(mix("turb")), qnh_mmhg=round(mix("qnh"), 1),
              temp_c=round(temp_month + mix("dt"), 1), preset=preset, base_m=round(base_m), mode=mode)


def clear_day(temp_c: float = 20.0) -> Wx:
    return Wx(temp_c=temp_c)


def forecast(mode: str, campaign_id: str, start: date, day: int, hour: float, pack: dict) -> Wx:
    """The weather at local `hour` on campaign day `day` (1-based) for the active theatre pack."""
    k = max(0, int(day) - 1)
    d = start + timedelta(days=k)
    temp = float(pack["temp_c"][d.month - 1])
    if mode in (None, "", "clear"):
        return Wx(temp_c=temp, mode="clear", wind_kt=0.0)
    clim = pack.get("climate") or DEFAULT_CLIMATE
    rng = _rng(campaign_id, "wxc", k, int(hour * 4))
    if mode != "procedural":
        state = {"scattered": "SCATTERED", "broken": "BROKEN", "overcast": "OVERCAST", "rain": "RAIN", "storm": "STORM"}.get(mode, "CLEAR")
        return _finish(state, _fixed(state, clim, d.month), None, 0.0, hour, temp, mode, rng)
    s0 = _state_on(campaign_id, start, k, clim)
    s1 = _state_on(campaign_id, start, k + 1, clim)
    f = min(max((hour - 6.0) / 24.0, 0.0), 1.0)
    a = _anchor(campaign_id, k, STATES[s0], clim, d.month)
    b = _anchor(campaign_id, k + 1, STATES[s1], clim, (d + timedelta(days=1)).month)
    s = int(round(s0 + (s1 - s0) * f))
    return _finish(STATES[s], a, b, f, hour, temp, mode, rng)


def for_package(state, mode: str, pack: dict, hhmm: str) -> Wx:
    """Weather for a campaign state at a package start time ('HH:MM' local)."""
    hh, mm = int(hhmm[:2]), int(hhmm[3:5])
    return forecast(mode, state.campaign_id, _start(state), state.day, hh + mm / 60.0, pack)


def _start(state) -> date:
    return state.campaign_date() - timedelta(days=max(0, state.day - 1))


def metar(wx: Wx) -> str:
    """A compact kneeboard string, e.g. 'OVC020 7KM RA 240/12'."""
    if wx.mode == "clear":
        return "CLEAR"
    sky = "CLR" if wx.cover < 0.1 else "FEW" if wx.cover < 0.3 else "SCT" if wx.cover < 0.55 else "BKN" if wx.cover < 0.9 else "OVC"
    out = [f"{sky}{int(round(wx.base_ft / 100.0)):03d}" if sky != "CLR" else "CLR", f"{wx.vis_km:.0f}KM"]
    if wx.rain:
        out.append("+RA" if wx.rain == 2 else "RA")
    if wx.fog_m:
        out.append("FG")
    return " ".join(out)


def describe(wx: Wx, short: bool = False) -> str:
    if wx.mode == "clear":
        return "clear skies, unrestricted visibility"
    if wx.state == "CLEAR" and wx.vis_km >= 40:
        sky = "clear skies"
    else:
        sky = f"{LABEL[wx.state].lower()}, base {int(round(wx.base_ft, -2)):,} ft" if wx.cover >= 0.2 else "few clouds"
    bits = [sky, f"visibility {wx.vis_km:.0f} km" if wx.vis_km >= 10 else f"visibility {wx.vis_km:.1f} km"]
    if wx.rain:
        bits.append("heavy rain" if wx.rain == 2 else "rain")
    if wx.fog_m:
        bits.append("fog")
    if not short and wx.wind_kt >= 1:
        bits.append(f"wind {int(wx.wind_from):03d} at {int(round(wx.wind_kt))} kt")
    return ", ".join(bits)


# ---------------------------------------------------------------------------------------------------------------------------
# Weapon classes and what the weather does to them
# ---------------------------------------------------------------------------------------------------------------------------
LASER_BASE_FT, LASER_VIS_KM = 10000, 8.0           # USAF Desert Storm report: forecast threshold ceilings >= 10,000 ft; cloud-free line of sight
EO_BASE_FT, EO_VIS_KM = 3000, 6.0                  # imaging-IR Mavericks and pod-aimed weapons: hand-tuned
VISUAL_BASE_FT, VISUAL_VIS_KM = 1500, 5.0          # unguided weapons, rockets, gun: you have to see the target
OPEN_COVER = 0.45                                  # below this the sky has gaps: a clear line of sight exists


def classify(name: str) -> str:
    n = (name or "").lower()
    if "anti-radiation" in n or "harm" in n or "agm-88" in n or "agm-45" in n or "alarm" in n:
        return "ARM"
    if any(k in n for k in ("jdam", "gps", "jsow", "agm-154", "slam", "gbu-54", "gbu-38", "gbu-31", "gbu-32", "gbu-24e")):
        return "GPS"
    if "laser" in n or re.search(r"gbu-(10|12|16|24)\b", n) or "paveway" in n or "agm-65e" in n or "agm-65l" in n:
        return "LASER"
    if any(k in n for k in ("maverick", "iir", " tv ", "walleye", "agm-62", "agm-65", "optical")):
        return "EO"
    if re.search(r"\baim-|\baam\b|\br-(27|24|77|73|60|3s|33|40)|\bsidewinder|\bsparrow|\bamraam|\bphoenix", n):
        return "A2A"
    if any(k in n for k in ("mk-8", "mk 8", "cbu", "rocket", "hydra", "m117", "m-117", "fab-", "s-8", "s-5", "lau-68", "lau-61", "bomb")):
        return "UNGUIDED"
    return "OTHER"


def usable(cls: str, wx: Wx) -> bool:
    """Can a weapon of this class be employed in this weather?"""
    if cls in ("GPS", "ARM", "A2A", "OTHER"):
        return True
    open_sky = wx.cover < OPEN_COVER
    if cls == "LASER":
        return (open_sky or wx.base_ft >= LASER_BASE_FT) and wx.vis_km >= LASER_VIS_KM and wx.rain == 0
    if cls == "EO":
        return (open_sky or wx.base_ft >= EO_BASE_FT) and wx.vis_km >= EO_VIS_KM and wx.rain < 2
    if cls == "UNGUIDED":
        return (open_sky or wx.base_ft >= VISUAL_BASE_FT) and wx.vis_km >= VISUAL_VIS_KM
    return True


def _names() -> dict:
    from dcs.weapons_data import weapon_ids
    return weapon_ids


def weapon_name(clsid: str) -> str:
    w = _names().get(clsid)
    return (w or {}).get("name", "") if isinstance(w, dict) else ""


def _weight(clsid: str) -> float:
    w = _names().get(clsid)
    return float((w or {}).get("weight", 0) or 0) if isinstance(w, dict) else 0.0


def adapt(aircraft_dcs_type, load: dict, wx: Wx) -> tuple:
    """Swap every laser / imaging weapon the weather rules out for the closest-weight GPS weapon that fits the same pylon.
    Returns (new loadout, [notes], usable A/G classes left, A/G classes that stayed unusable)."""
    import copy
    out = copy.deepcopy(load)
    notes, keep, dead = [], set(), set()
    for pylon in sorted(out):
        clsid = out[pylon]["CLSID"]
        nm = weapon_name(clsid)
        cls = classify(nm)
        if cls in ("A2A", "OTHER"):
            continue
        if usable(cls, wx):
            keep.add(cls)
            continue
        P = getattr(aircraft_dcs_type, f"Pylon{pylon}", None)
        best, bw = None, None
        if P is not None:
            for attr, val in vars(P).items():
                if attr.startswith("_") or not isinstance(val, tuple) or len(val) < 2 or not isinstance(val[1], dict):
                    continue
                c2 = val[1].get("clsid", "")
                n2 = weapon_name(c2).lower()
                if classify(n2) != "GPS" or "agm" in n2 or "slam" in n2 or not re.search(r"jdam|gbu-", n2):
                    continue                          # a GPS BOMB for a bomb or Maverick pylon, never a cruise missile
                gap = abs(_weight(c2) - _weight(clsid))
                if bw is None or gap < bw:
                    best, bw = c2, gap
        if best:
            out[pylon] = {"CLSID": best}
            notes.append(f"{_short(nm)} -> {_short(weapon_name(best))}")
            keep.add("GPS")
        else:
            dead.add(cls)
    return out, notes, keep, dead


def _short(name: str) -> str:
    n = re.split(r"\s[-:]\s", name)[0]
    return re.sub(r"\s+", " ", n).strip()[:40] or name[:40]


# What each flight role must be able to do for its package to be worth flying (any one class suffices)
_NEED = {"STRIKE": {"GPS", "LASER", "UNGUIDED", "EO"}, "CAS": {"GPS", "LASER", "UNGUIDED", "EO"}, "SEAD": {"ARM"}}


def assess(wx: Wx, objective_type: str, flights: list, lib, aircraft_table) -> dict:
    """Can this package fly? flights = [Flight]. Returns {"scrub": reason or "", "notes": [str]}.
    Defensive air patrols are never scrubbed. Everything else is scrubbed in a storm, in fog, or when an attacking flight is left
    with nothing it can use."""
    if objective_type in ("BARCAP", "FLEET_DEFENSE"):
        return {"scrub": "", "notes": []}
    if wx.state == "STORM" or (wx.base_ft < 600 and wx.cover >= 0.5) or wx.vis_km < 1.5:
        why = "storms" if wx.state == "STORM" else "fog" if wx.fog_m else "ceiling and visibility below limits"
        return {"scrub": f"weather: {why} ({describe(wx, short=True)})", "notes": []}
    notes = []
    for f in flights:
        need = _NEED.get(f.role.value if hasattr(f.role, "value") else str(f.role))
        if not need or getattr(f, "tag", ""):
            continue
        spec = aircraft_table[f.aircraft]
        load = lib.for_role(f.aircraft, f.role)
        new, ch, keep, _dead = adapt(spec.dcs_type, load, wx)
        if ch:
            notes.append(f"{f.callsign}: {'; '.join(sorted(set(ch)))} ({LABEL[wx.state].lower()}, base {int(round(wx.base_ft, -2)):,} ft)")
        if not (keep & need):
            return {"scrub": f"weather: {f.callsign} ({spec.display}) has no weapon it can use ({describe(wx, short=True)})", "notes": notes}
    return {"scrub": "", "notes": notes}


def apply(m, wx: Wx) -> None:
    """Write the weather into a pydcs mission. 'clear' mode leaves exactly what SQE always wrote (no cloud, calm, 80 km)."""
    from dcs.weather import Wind
    w = m.weather
    w.atmosphere_type = 0
    w.type_weather = 0
    w.season_temperature = float(wx.temp_c)
    w.qnh = float(wx.qnh_mmhg)
    w.enable_dust = False
    w.visibility_distance = int(min(max(wx.vis_km, 0.5), 80.0) * 1000)
    if wx.preset:
        from dcs.cloud_presets import Clouds
        w.clouds_preset = Clouds[wx.preset].value
        w.clouds_base = int(wx.base_m)
        w.clouds_density = 0
        w.name = f"SQE {LABEL[wx.state]}"
    else:
        w.clouds_preset = None
        w.clouds_density = 0
    w.enable_fog = bool(wx.fog_m)
    if wx.fog_m:
        w.fog_visibility = int(wx.fog_m)
        w.fog_thickness = 200
    if wx.wind_kt > 0:
        ms = wx.wind_kt / KT
        to = lambda deg: int(round((deg + 180) % 360))                # DCS stores the direction the wind blows TO
        w.wind_at_ground = Wind(to(wx.wind_from), round(ms, 1))
        w.wind_at_2000 = Wind(to(wx.wind_from + 25), round(ms * 1.8, 1))
        w.wind_at_8000 = Wind(to(wx.wind_from + 55), round(ms * 3.2, 1))
        w.turbulence_at_ground = float(wx.turb)
