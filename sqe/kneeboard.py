"""Kneeboard pages (PNG 768x1024): 1 comms ladder, 2 waypoints with times, 3 timeline + threats."""
from __future__ import annotations
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from dcs import mapping

W, H = 768, 1024
BG, INK, DIM, RULE = (245, 242, 232), (20, 20, 20), (95, 95, 95), (170, 165, 150)
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
    return f"{h} {d:0{w}d}\u00b0{(v - d) * 60:06.3f}'"


def latlon(x, y, terrain):
    ll = mapping.Point(x, y, terrain).latlng()
    return f"{_ddm(ll.lat, 'N', 'S', 2)} {_ddm(ll.lng, 'E', 'W', 3)}"


class _Page:
    def __init__(self, title, sub):
        self.img = Image.new("RGB", (W, H), BG); self.d = ImageDraw.Draw(self.img); self.y = 24
        self.text(title, 34, bold=True); self.text(sub, 17, color=DIM); self.rule()

    def text(self, s, size=20, x=24, color=INK, bold=False, gap=8):
        self.d.text((x, self.y), s, font=_font(size, bold), fill=color); self.y += size + gap

    def rule(self):
        self.d.line([(20, self.y), (W - 20, self.y)], fill=RULE, width=2); self.y += 12

    def row(self, cols, xs, size=22, color=INK, bold=False):
        for c, x in zip(cols, xs):
            self.d.text((x, self.y), str(c), font=_font(size, bold), fill=color)
        self.y += size + 10

    def save(self, p):
        self.img.save(p); return p


def render_pages(outdir, package, plan, waypoints, terrain, state, tl, clock, threats, start_name) -> list:
    outdir = Path(outdir); outdir.mkdir(parents=True, exist_ok=True)
    pf = package.player_flight
    sub = f"Day {state.day} | {pf.callsign} | {package.objective.description}"[:62]
    pages = []

    p = _Page("COMMS", sub)
    p.text("COMM 1  (UHF)", 24, bold=True)
    for ch, e in plan.comm1.items():
        p.row([f"CH{ch}", e.label, f"{e.mhz:7.3f}"], [24, 120, 300], size=24, bold=True)
        extra = (e.callsign + "  " if e.callsign else "") + e.note
        if extra.strip():
            p.text(extra, 16, x=120, color=DIM, gap=4)
    p.y += 8; p.rule()
    p.text("COMM 2  (VHF)", 24, bold=True)
    for ch, e in plan.comm2.items():
        p.row([f"CH{ch}", e.label, f"{e.mhz:7.3f}"], [24, 120, 300], size=24, bold=True)
        p.text(e.callsign, 16, x=120, color=DIM, gap=4)
    p.y += 8; p.rule()
    p.text("PACKAGE", 22, bold=True)
    for f in package.flights:
        p.text(f"{f.callsign:<12} {f.count}x{f.aircraft:<7} {f.role.value}" + ("  <- YOU" if f.is_player else ""), 18)
    if plan.package_flights:
        p.y += 4; p.text("Other flights (info only):", 16, color=DIM)
        for e in plan.package_flights:
            p.text(f"{e.callsign:<12} {e.mhz:7.3f}  {e.note}", 16, color=DIM, gap=4)
    pages.append(p.save(outdir / "1_comms.png"))

    p = _Page("WAYPOINTS", sub)
    xs = [24, 70, 470, 560, 650]
    p.row(["#", "WAYPOINT / POSITION", "TIME", "ALT", "KTS"], xs, size=17, color=DIM, bold=True)
    p.d.text((xs[0], p.y), "1", font=_font(20), fill=INK)
    p.d.text((xs[1], p.y), "TAKEOFF", font=_font(20, True), fill=INK)
    p.d.text((xs[2], p.y), tl["launch"][:5], font=_font(20), fill=INK)
    p.y += 30; p.text(start_name, 16, x=70, color=DIM, gap=6)
    for i, w in enumerate(waypoints, 2):
        alt = f"{w.alt_ft // 1000}K" if w.alt_ft else "-"
        t = clock(w.eta_s)[:5] if w.eta_s else ""
        if w.name == "PUSH":
            t = tl["push"][:5]
        for x, s, b in ((xs[0], str(i), False), (xs[1], w.name, True), (xs[2], t, w.name in ("PUSH", "TGT", "CAS", "ESC", "SEAD", "SWP")),
                        (xs[3], alt, False), (xs[4], str(w.speed_kts), False)):
            p.d.text((x, p.y), s, font=_font(20, b), fill=INK)
        p.y += 30
        p.text(latlon(w.x, w.y, terrain), 15, x=70, color=DIM, gap=2)
        if w.note:
            p.text(w.note, 15, x=70, color=DIM, gap=5)
    pages.append(p.save(outdir / "2_waypoints.png"))

    p = _Page("TIMELINE & THREATS", sub)
    for k, label in (("launch", "LAUNCH"), ("marshal", "MARSHAL"), ("push", "PUSH"), ("tot", "TIME ON TARGET"), ("egress", "EGRESS")):
        p.row([label, tl[k]], [24, 330], size=26, bold=(k in ("push", "tot")))
    p.y += 6; p.rule()
    p.text("THREATS NEAR TARGET", 22, bold=True)
    for t in (threats or ["No known SAM or radar sites within 60 nm."]):
        p.text("- " + t, 16, gap=5)
    p.y += 6; p.rule()
    p.text("Hold at MSHL. Leave on PUSH. Stay on time.", 16, color=DIM)
    pages.append(p.save(outdir / "3_timeline.png"))
    return pages
