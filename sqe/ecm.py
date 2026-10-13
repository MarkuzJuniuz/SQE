"""Jamming (v0.35.0). DCS has no jamming of its own, so SQE emulates the effect: when a radar-guided missile is launched at an aircraft,
the mission hook (debrief.LUA_HOOK) rolls the odds that the target's jamming defeats it and destroys the missile partway through its flight.
The same table serves both sides, the player's jet included.

Tiers (what the aircraft brings):
  1  internal self-protection set: protects only that aircraft (the F-15C included since v0.40.9: it carries an internal jammer)
  2  an ECM pod on the loadout: stronger, and also covers aircraft flying close by

The numbers are SQE's own judgement, not sourced figures. Pure data, no pydcs.
"""
from __future__ import annotations

# internal self-protection by DCS type string (substring match, first hit wins)
INTERNAL = (("F-15C", 1), ("F-14", 1), ("FA-18C", 1), ("F-16C", 0), ("A-10C", 0), ("Su-24M", 1), ("Tu-22M3", 1), ("MiG-29", 0), ("Su-27", 0))

# loadout CLSIDs that are an ECM pod
PODS = ("=ALQ_184_Long", "=ALQ_184", "ALQ_184", "ALQ-184")

# kill chance per launch at full range, by tier of the best jammer covering the target
P_SELF = {1: 0.20, 2: 0.45}
P_COVER = 0.30                  # a pod-carrier close by covers an aircraft that has no pod of its own
COVER_NM = 2.0                  # how close counts as "close by"
BURN_KM = 12.0                  # inside this launch range the missile burns through: no effect
FULL_KM = 40.0                  # at this launch range and beyond the full chance applies


def internal_tier(dcs_type: str) -> int:
    t = str(dcs_type).replace("_", "-")
    for key, tier in INTERNAL:
        if key in t:
            return tier
    return 0


def has_pod(pylons: dict | None) -> bool:
    for v in (pylons or {}).values():
        c = (v.get("CLSID") if isinstance(v, dict) else v) or ""
        if any(p in str(c) for p in PODS):
            return True
    return False


def tier(dcs_type: str, pylons: dict | None) -> int:
    """0 = nothing, 1 = internal set, 2 = pod on the loadout (a pod carrier always has at least tier 2)."""
    return 2 if has_pod(pylons) else internal_tier(dcs_type)


def chance(tier_self: int, best_cover: int, launch_km: float) -> float:
    """Chance the missile is defeated: the better of the target's own tier and a pod-carrier close by, scaled by launch range (burn-through)."""
    p = max(P_SELF.get(tier_self, 0.0), P_COVER if best_cover >= 2 else 0.0)
    if launch_km <= BURN_KM:
        return 0.0
    return p * min(1.0, (launch_km - BURN_KM) / (FULL_KM - BURN_KM))


def jammer_on(unit_name: str) -> bool:
    """The one place that says whether a jammer is switched on. Always true for now; a future export script can feed the cockpit switch here."""
    return True


# ---- the abstract war (war.py): how much jamming a package brings ------------------------------------------------------------
SITE_CUT = 0.20                 # a package with full jamming cover cuts the site's strength in the SEAD odds by this much
LOSS_CUT = 0.15                 # ...and the package's loss chance by this much
_W = {0: 0.0, 1: 0.4, 2: 1.0}   # weight of a flight's tier in the package cover


def flight_tier(aircraft: str, role) -> int:
    """Tier of a flight from the default loadout table (a pod anywhere on the role's preset = 2)."""
    from .loadouts import _D, _ALIAS
    from .aircraft import AIRCRAFT
    name = _ALIAS.get(role, getattr(role, "value", str(role)))
    tab = _D.get(aircraft, {})
    row = tab.get(name) or tab.get("CAP") or next(iter(tab.values()), {})
    if any("ALQ_184" in str(v) for v in row.values()):
        return 2
    spec = AIRCRAFT.get(aircraft)
    return internal_tier(spec.dcs_class) if spec else 0


def package_cover(pkg) -> float:
    """0..1: the aircraft-weighted jamming cover of a package's own flights (support aircraft do not count)."""
    n = tot = 0
    for f in pkg.flights:
        if getattr(f, "tag", None):
            continue
        n += f.count
        tot += f.count * _W[flight_tier(f.aircraft, f.role)]
    return tot / n if n else 0.0
