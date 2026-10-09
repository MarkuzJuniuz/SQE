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

    # ------------------------------------------------ page 1: comms + the times YOU must hit
    p = _Page(f"SQE  {head}", sub)
    if ctx.get("fc3"):                      # FC3 radios have no channels: just the frequencies
        p.cols([(20, "FREQUENCIES")], 15, DIM, True, 3)
        for e in list(ctx["comm1"].values()) + list(ctx["comm2"].values()):
            p.cols([(20, e.label), (160, f"{e.mhz:7.3f}"), (290, (e.callsign + " " + e.note).strip()[:44])], 18, bold=True, gap=5)
    else:
        p.cols([(20, "COMM1 UHF")], 15, DIM, True, 3)
        for ch, e in ctx["comm1"].items():
            p.cols([(20, f"CH{ch}"), (84, e.label), (230, f"{e.mhz:7.3f}"), (340, (e.callsign + " " + e.note).strip()[:36])], 18, bold=True, gap=5)
        p.cols([(20, "COMM2 VHF")], 15, DIM, True, 3)
        for ch, e in ctx["comm2"].items():
            p.cols([(20, f"CH{ch}"), (84, e.label), (230, f"{e.mhz:7.3f}"), (340, e.callsign)], 18, bold=True, gap=5)
    p.rule(6)
    p.cols([(20, "WP"), (64, "NAME"), (160, "TIME"), (282, "ALT"), (342, "KTS"), (396, "HDG/NM"), (474, "REMARKS")], 14, DIM, True, 4)
    for r in ctx["waypoints"]:
        hot = r["name"] in ("MSHL", "PUSH", "TGT", "SEAD", "CAP1")
        y0 = p.y
        p.cols([(20, r["wp"]), (64, r["name"]), (160, r["time"]), (282, r["alt"]), (342, r["kts"]), (400, r["leg"])], 17, bold=hot, gap=7)
        last = " ".join(x for x in (r["win"], r["note"]) if x)[:40]
        if last:
            p.d.text((474, y0 + 3), last, font=_font(12, bool(r["win"])), fill=INK if r["win"] else DIM)
    p.y += 4
    p.text(f"Numbers are as your {ctx['jet']} cockpit shows them: {ctx['numbering']}", 12, color=DIM, gap=3)
    p.text("PUSH +/-30 s, TOT +/-1 min. Times are YOUR flight's.", 12, color=DIM, gap=3)
    p.text(ctx.get("zulu_note", "Times are local. Zulu = local - 4 h (your jet may show Zulu)."), 12, color=DIM)
    pages.append(p.save(outdir / "1_comms_times.png"))

    # ------------------------------------------------ page 2: fuel, codes, package, threats
    p = _Page(f"SQE  {head}", "FUEL / CODES / PACKAGE / THREATS")
    p.cols([(20, f"BINGO {ctx['bingo']} lb"), (260, f"JOKER {ctx['joker']} lb"), (500, f"WX: {ctx.get('weather_short') or ctx['weather']}")], 18, bold=True, gap=6)
    p.cols([(20, f"IFF M3 {ctx['mode3']}"), (260, f"LASER {ctx['laser']}")], 18, bold=True, gap=6)
    p.text("BULLSEYE  " + ctx["bullseye"], 14, color=DIM, gap=4)
    if ctx.get("target_data"):
        p.text(ctx["target_data"][:78], 14, bold=True, gap=4)
    p.rule()
    p.text("PACKAGE  (STN = Link 16 / SADL station number)", 14, color=DIM, bold=True, gap=3)
    p.cols([(20, "CALLSIGN"), (200, "TYPE"), (300, "TASK"), (430, "M3"), (500, "STN")], 13, DIM, True, 3)
    for r in ctx["whois"]:
        p.cols([(20, r["cs"]), (200, r["ac"]), (300, r["role"]), (430, r["m3"]), (500, r["stn"])], 14, bold=r["you"], gap=3)
    if ctx.get("others"):
        p.rule()
        p.text("ALSO IN THIS MISSION (AI packages, same area; each pushes and strikes on its own time)", 12, color=DIM, bold=True, gap=3)
        for o in ctx["others"][:3]:
            p.text(o["line"][:70], 13, bold=True, gap=1)
            p.text("   " + o["sub"][:88], 11, color=DIM, gap=3)
    p.rule()
    p.text("THREATS NEAR TARGET", 15, bold=True, gap=3)
    for t in (ctx["threats"][:8] or ["No known SAM or radar sites within 60 nm."]):
        p.text("- " + t, 13, gap=3)
    p.rule()
    p.text(f"Intelligence: about {ctx['n_def']} enemy fighters (CAP and alert aircraft) in the area." if ctx["n_def"]
           else "No organised fighter defence expected.", 14, gap=3)
    pages.append(p.save(outdir / "2_package_info.png"))
    return pages
