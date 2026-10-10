"""Kneeboard pages (PNG 768x1024), laid out like a printed form: shaded section bands, ruled rows, and exactly three type sizes.
Page 1: comms ladder + waypoints (numbered the way YOUR jet's cockpit numbers them), the tolerances, the time zone and the minimum safe altitude (with the ground-height scan).
Page 2: fuel, codes, weather, target lat/long, bullseye, package who's-who (with Link 16 STNs).
Page 3: the other packages in the mission (own push / TOT), threats near the target, intelligence.
Every clock time is hh:mm:ss. Text wraps only at logical breaks (after a comma or a sentence), never inside an item."""
from __future__ import annotations
import re
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from dcs import mapping

W, H = 768, 1024
BG, INK, DIM, RULE, BAND, ROWRULE = (245, 242, 232), (20, 20, 20), (95, 95, 95), (170, 165, 150), (226, 222, 208), (214, 209, 194)
TITLE, LABEL, VALUE = 24, 11, 16              # the only three sizes on the card
_F = ["DejaVuSansMono.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", "C:/Windows/Fonts/consola.ttf",
      "C:/Windows/Fonts/cour.ttf", "/System/Library/Fonts/Menlo.ttc"]
_FB = ["DejaVuSansMono-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
       "C:/Windows/Fonts/consolab.ttf", "C:/Windows/Fonts/courbd.ttf"]


def _font(size, bold=False):
    for c in (_FB if bold else []) + _F:
        try:
            return ImageFont.truetype(c, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


def _ddm(v, pos, neg, w):
    h = pos if v >= 0 else neg
    v = abs(v); d = int(v)
    return f"{h}{d:0{w}d}\u00b0{(v - d) * 60:06.3f}'"


def latlon(x, y, terrain):
    ll = mapping.Point(x, y, terrain).latlng()
    return f"{_ddm(ll.lat, 'N', 'S', 2)} {_ddm(ll.lng, 'E', 'W', 3)}"


def _tol(t) -> str:
    """'+/-30s' and '+/-1m' read as '+/-30 s' and '+/-1 min', matching the notes at the bottom of page 1."""
    return re.sub(r"\+/-1m\b", "+/-1 min", re.sub(r"\+/-(\d+)s\b", r"+/-\1 s", str(t)))


def hms(t) -> str:
    """Every clock time on the card as hh:mm:ss (a stray hh:mm gets :00)."""
    return re.sub(r"(?<![\d:])(\d\d:\d\d)(?![\d:])", r"\1:00", str(t))


class _Form:
    def __init__(self, title):
        self.img = Image.new("RGB", (W, H), BG); self.d = ImageDraw.Draw(self.img); self.y = 14
        self.cw = _font(VALUE).getlength("M")               # exact monospace advance
        self.d.text((20, self.y), title, font=_font(TITLE, True), fill=INK); self.y += TITLE + 10

    def band(self, label, cols=None):
        self.d.rectangle([14, self.y, W - 14, self.y + LABEL + 8], fill=BAND)
        for xc, t in (cols or [(0, label.upper())]):
            self.d.text((20 + int(xc * self.cw), self.y + 3), t, font=_font(LABEL, True), fill=DIM)
        self.y += LABEL + 14

    def row(self, cells, bold=False, color=INK, gap=6):
        """cells: [(x in characters, text)]. A thin rule closes the row, like a printed form."""
        for xc, t in cells:
            self.d.text((20 + int(xc * self.cw), self.y), str(t), font=_font(VALUE, bold), fill=color)
        self.y += VALUE + gap
        self.d.line([(16, self.y - 2), (W - 16, self.y - 2)], fill=ROWRULE, width=1)

    def line(self, t, bold=False, color=INK, indent=0, gap=6, hang=None):
        """Wrap at logical breaks only: after ', ' or a sentence end. A number is never parted from its unit ('+/-30 s', '2xF-16C').
        An item too long for one line falls back to word wrap."""
        width = int((W - 40) // self.cw) - indent
        hang = indent if hang is None else hang
        items = [x for x in re.split(r"(?<=[,.;:])\s+(?=\S)", str(t)) if x]
        cur, first = "", True

        def flush():
            nonlocal cur, first
            if cur:
                self.row([(indent if first else hang, cur)], bold, color, gap); first = False; cur = ""
        for it in items:
            room = width - (0 if first else (hang - indent))
            if len(it) > room:
                flush()
                c2 = ""
                for w in it.split():
                    if len(c2) + len(w) + 1 > room:
                        self.row([(indent if first else hang, c2)], bold, color, gap); first = False; c2 = w
                    else:
                        c2 = (c2 + " " + w).strip()
                cur = c2
                continue
            if cur and len(cur) + 1 + len(it) > room:
                flush()
            cur = (cur + " " + it).strip()
        flush()

    def save(self, p):
        self.img.save(p); return p


def _tgt_note(r, has_target):
    """Remark under the TGT row: where the coordinates are, then the jet's own note."""
    parts = []
    if has_target:
        parts.append("TGT LAT/LONG - PG 2.")
    for x in (r.get("win", ""), r.get("note", "")):
        if x:
            parts.append(x if x.endswith(".") else x + ".")
    return " ".join(parts)


def render_pages(outdir, ctx: dict) -> list:
    outdir = Path(outdir); outdir.mkdir(parents=True, exist_ok=True)
    head = f"{ctx['date']}  {ctx['callsign']}  {ctx['role']}"
    pages = []

    # ------------------------------------------------ page 1: comms + the times YOU must hit
    f = _Form(head)
    f.line(ctx["objective"][:60], color=DIM, gap=8)
    if ctx.get("fc3"):                      # FC3 radios have no channels: just the frequencies
        f.band("FREQUENCIES")
        for e in list(ctx["comm1"].values()) + list(ctx["comm2"].values()):
            f.row([(0, e.label), (12, f"{e.mhz:7.3f}"), (21, (e.callsign + " " + e.note).strip()[:40])], True)
    else:
        f.band("COMM 1 (UHF)")
        for ch, e in ctx["comm1"].items():
            f.row([(0, f"CH{ch}"), (4, e.label), (14, f"{e.mhz:7.3f}"), (23, ((e.callsign or e.note).replace("carrier control", "CVN")).strip()[:36])], True)
        f.band("COMM 2 (VHF)")
        for ch, e in ctx["comm2"].items():
            f.row([(0, f"CH{ch}"), (4, e.label), (14, f"{e.mhz:7.3f}"), (23, e.callsign[:36])], True)
    f.band("", [(0, "WP"), (3, "NAME"), (12, "TIME"), (22, "ALT"), (29, "KTS"), (34, "HDG/NM")])
    for r in ctx["waypoints"]:
        hot = r["name"] in ("MSHL", "PUSH", "TGT", "SEAD", "CAP1")
        f.row([(0, r["wp"]), (3, r["name"]), (12, hms(r["time"])), (22, r["alt"]), (29, r["kts"]), (34, r["leg"])], hot, gap=4)
        if r["name"] == "TGT":
            note = _tgt_note(r, bool(ctx.get("target_data")))
        else:
            note = " ".join(x for x in (r["win"], r["note"]) if x) if (hot or r["name"] in ("TKR", "RTB", "DIVERT", "TAKEOFF")) else ""
        if note:
            f.line(_tol(hms(note)), False, INK if hot else DIM, indent=3, gap=6)
    f.band("NOTES")
    num = str(ctx.get("numbering", "")).replace("...", "").rstrip(" .,")
    notes = [f"{ctx['jet']} waypoint numbers: {num}.", "PUSH +/-30 s, TOT +/-1 min.", ctx.get("zulu_note", "Times are local.")]
    if ctx.get("msa"):
        notes.append(f"MSA {int(ctx['msa']):,} ft along the route.")
    for note in notes:
        f.line(note, color=DIM, gap=4)
    pages.append(f.save(outdir / "1_comms_times.png"))

    # ------------------------------------------------ page 2: fuel, codes, weather, target, package
    f = _Form(head)
    f.band("FUEL")
    f.row([(0, f"BINGO {ctx['bingo']}"), (17, f"JOKER {ctx['joker']}")], True)
    f.band("CODES")
    f.row([(0, f"IFF M3 {ctx['mode3']}"), (17, f"LASER {ctx['laser']}")], True)
    f.band("WEATHER")
    f.row([(0, ctx.get("weather_short") or ctx["weather"])], True)
    if ctx.get("target_data"):
        f.band("TARGET LAT/LONG")
        coord = ctx["target_data"].split("  ", 1)[1].split("   (")[0].strip()
        f.row([(0, coord)], True, gap=2)
        f.line(ctx["objective"], color=DIM)
    f.band("BULLSEYE")
    f.row([(0, ctx["bullseye"])])
    f.band("", [(0, "PACKAGE (STN = LINK 16 / SADL)"), (19, "TYPE"), (26, "TASK"), (34, "M3"), (39, "STN")])
    for r in ctx["whois"]:
        f.row([(0, r["cs"].replace("..", "-")[:18]), (19, r["ac"]), (26, r["role"][:7]), (34, r["m3"]), (39, r["stn"][:5])], r["you"], gap=4)
    pages.append(f.save(outdir / "2_fuel_codes_package.png"))

    # ------------------------------------------------ page 3: other packages, threats, intelligence
    f = _Form(head)
    if ctx.get("others"):
        f.band("OTHER PACKAGES - OWN PUSH / TOT")
        for o in ctx["others"][:3]:
            f.line(o["line"], True, gap=2)
            f.row([(1, f"PUSH {hms(o['push'])}"), (17, f"TOT {hms(o['tot'])}"), (31, f"DONE {hms(o['rtb'])}")], gap=6)
            if o.get("status"):
                f.line(o["status"], False, DIM, indent=1, gap=4)
            f.line(o["flights"], False, DIM, indent=1, gap=8, hang=3)
    f.band("THREATS NEAR TARGET")
    for t in (ctx["threats"][:8] or ["No known SAM or radar sites within 60 nm."]):
        f.line("- " + t, gap=7)
    f.band("INTELLIGENCE")
    f.line(f"About {ctx['n_def']} enemy fighters (CAP and alert aircraft) in the area." if ctx["n_def"]
           else "No organised fighter defence expected.", gap=7)
    for l in ctx.get("intel", []):
        f.line(l, color=DIM, gap=7)
    pages.append(f.save(outdir / "3_other_threats_intel.png"))
    return pages
