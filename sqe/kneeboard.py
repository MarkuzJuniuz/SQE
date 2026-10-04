"""Two kneeboard pages (PNG 768x1024).
Page 1: comms ladder + waypoints (numbered the way YOUR jet's cockpit numbers them).
Page 2: timeline, fuel, codes, package who's-who (with Link 16 STNs), threats, bullseye."""
from __future__ import annotations
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from dcs import mapping

W, H = 768, 1024
BG, INK, DIM, RULE, HOT = (245, 242, 232), (20, 20, 20), (95, 95, 95), (170, 165, 150), (150, 30, 30)
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


class _Page:
    def __init__(self, title, sub):
        self.img = Image.new("RGB", (W, H), BG); self.d = ImageDraw.Draw(self.img); self.y = 18
        self.text(title, 28, bold=True, gap=4); self.text(sub, 15, color=DIM, gap=4); self.rule()

    def text(self, s, size=18, x=20, color=INK, bold=False, gap=6):
        self.d.text((x, self.y), s, font=_font(size, bold), fill=color); self.y += size + gap

    def rule(self, gap=8):
        self.d.line([(16, self.y), (W - 16, self.y)], fill=RULE, width=2); self.y += gap

    def cols(self, items, size=18, color=INK, bold=False, gap=8):
        for x, s in items:
            self.d.text((x, self.y), str(s), font=_font(size, bold), fill=color)
        self.y += size + gap

    def save(self, p):
        self.img.save(p); return p


def render_pages(outdir, ctx: dict) -> list:
    outdir = Path(outdir); outdir.mkdir(parents=True, exist_ok=True)
    head = f"{ctx['date']}  {ctx['callsign']}  {ctx['role']}"
    sub = ctx["objective"][:70]
    pages = []

    # ------------------------------------------------ page 1: comms + waypoints
    p = _Page(f"SQE  {head}", sub)
    p.text("COMMS", 16, color=DIM, bold=True, gap=3)
    p.cols([(20, "COMM1 UHF")], 16, DIM, True, 3)
    for ch, e in ctx["comm1"].items():
        p.cols([(20, f"CH{ch}"), (84, e.label), (230, f"{e.mhz:7.3f}"), (340, (e.callsign + " " + e.note).strip()[:36])], 18, bold=True, gap=5)
    p.cols([(20, "COMM2 VHF")], 16, DIM, True, 3)
    for ch, e in ctx["comm2"].items():
        p.cols([(20, f"CH{ch}"), (84, e.label), (230, f"{e.mhz:7.3f}"), (340, e.callsign)], 18, bold=True, gap=5)
    p.rule(6)
    p.cols([(20, "WP"), (62, "NAME"), (170, "TIME"), (262, "ALT"), (326, "KTS"), (386, "POSITION")], 14, DIM, True, 4)
    for r in ctx["waypoints"]:
        hot = r["name"] in ("PUSH", "TGT", "CAS", "ESC", "SEAD", "SWP", "CAP1")
        p.cols([(20, r["wp"]), (62, r["name"]), (170, r["time"]), (262, r["alt"]), (326, r["kts"]), (386, r["pos"])], 16, bold=hot, gap=6)
        if r.get("note"):
            p.d.text((62, p.y - 4), r["note"][:62], font=_font(12), fill=DIM); p.y += 11
    p.y += 6
    p.text(f"Cockpit numbering for {ctx['jet']}: {ctx['numbering']}", 12, color=DIM)
    pages.append(p.save(outdir / "1_comms_waypoints.png"))

    # ------------------------------------------------ page 2: everything else
    p = _Page(f"SQE  {head}", "TIMELINE / FUEL / CODES / PACKAGE / THREATS")
    tl = ctx["timeline"]
    for (k1, l1), (k2, l2) in ((("launch", "LAUNCH"), ("marshal", "MARSHAL")), (("push", "PUSH"), ("tot", "TOT")), (("egress", "EGRESS"), ("rtb", "RTB"))):
        p.cols([(20, l1), (190, tl[k1]), (400, l2), (560, tl[k2])], 20, bold=(k1 == "push"), gap=6)
    p.rule()
    p.cols([(20, f"BINGO {ctx['bingo']} lb"), (260, f"JOKER {ctx['joker']} lb"), (500, f"WX: {ctx['weather']}")], 18, bold=True, gap=6)
    p.cols([(20, f"IFF M3 {ctx['mode3']}"), (260, f"LASER {ctx['laser']}"), (500, f"BULLS {ctx['bulls_short']}")], 18, bold=True, gap=6)
    p.text("BULLSEYE  " + ctx["bullseye"], 14, color=DIM)
    p.rule()
    p.text("PACKAGE  (Link 16 / SADL STN shown where the jet is networked)", 14, color=DIM, bold=True, gap=3)
    p.cols([(20, "CALLSIGN"), (170, "TYPE"), (270, "TASK"), (400, "M3"), (470, "STN")], 13, DIM, True, 3)
    for r in ctx["whois"]:
        p.cols([(20, r["cs"]), (170, r["ac"]), (270, r["role"]), (400, r["m3"]), (470, r["stn"])], 14, bold=r["you"], gap=3)
    p.rule()
    p.text("THREATS NEAR TARGET", 15, bold=True, gap=3)
    for t in (ctx["threats"][:7] or ["No known SAM or radar sites within 60 nm."]):
        p.text("- " + t, 13, gap=3)
    p.rule()
    p.text(f"Expect about {ctx['n_def']} hostile fighters at the target." if ctx["n_def"] else "No organised fighter defence expected.", 14, gap=3)
    p.text("Hold at MSHL. Leave on PUSH. Stay on time.", 14, color=DIM)
    pages.append(p.save(outdir / "2_package_info.png"))
    return pages
