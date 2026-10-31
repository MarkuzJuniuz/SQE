"""v0.41.207 (XO's UI_Remarks.docx, 2026-10-29): how the Overview draws its figures. HTML and small images only; the numbers come from
overview_detail.py / posture.py (the data layer keeps its plain lowercase strings, the smoke test reads them). Colour rules (XO 2026-10-29):
supply bad at 65% or less, alright 66 to 90, good above 90; every other 0 to 100 figure (air defence, health, strength) red below 40, amber 40 to 70,
green above 70 (judgment call for the cut-offs). The middle band is amber (#E0A800), not pure yellow."""
from __future__ import annotations
import html
from PySide6.QtCore import QUrl
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QTextDocument
from . import theme

GOOD, MID, BAD = "#3ddc97", "#E0A800", "#ff5d6c"
DARK = "#04101c"
EVEN = MID                                    # "equal" ground odds: amber
COLORS = {"good": GOOD, "mid": MID, "bad": BAD, "edge": theme.BLUE}


def pct_band(p: float) -> str:
    return "good" if p > 70 else ("mid" if p >= 40 else "bad")


def supply_band(p: float) -> str:
    return "good" if p > 90 else ("mid" if p > 65 else "bad")


def odds_color(word: str) -> str:
    """Ground odds by sign: holding (we are ahead) green, even amber, losing red."""
    return {"holding": GOOD, "even": EVEN, "losing": BAD}.get(word, theme.BLUE)


def title(s: str) -> str:
    """Title case for a short label ('enemy holds' -> 'Enemy Holds'); acronyms (SEAD, CAS, SAM) stay as they are."""
    small = {"of", "and", "the", "to", "on", "in", "by"}
    return " ".join(w if (w.isupper() or (i and w in small)) else w[:1].upper() + w[1:] for i, w in enumerate(s.split(" ")))


def first_cap(s: str) -> str:
    return s[:1].upper() + s[1:]


def e(s) -> str:
    return html.escape(str(s))


HEAD = "color:#8fa3b8;padding:0 14px 4px 0"


def table(headers, rows, aligns=None) -> str:
    """rows: lists of cells; a cell is a string (escaped) or ('html', raw) or ('bg', text, band) for a coloured background."""
    th = "".join(f"<th align='left' style='{HEAD}'>{e(h)}</th>" for h in headers)
    out = [f"<table cellspacing='0' cellpadding='3'><tr>{th}</tr>"]
    for r in rows:
        tds = []
        for c in r:
            if isinstance(c, tuple) and c[0] == "html":
                tds.append(f"<td style='padding:3px 14px 3px 0'>{c[1]}</td>")
            elif isinstance(c, tuple) and c[0] == "bg":
                tds.append(f"<td align='center' bgcolor='{COLORS[c[2]]}' style='padding:3px 10px'><font color='{DARK}'><b>{e(c[1])}</b></font></td>")
            else:
                tds.append(f"<td style='padding:3px 14px 3px 0'>{e(c)}</td>")
        out.append("<tr>" + "".join(tds) + "</tr>")
    return "".join(out) + "</table>"


def section(heading: str, body: str) -> str:
    return f"<p style='margin-top:14px;margin-bottom:4px'><b>{e(heading)}</b></p>{body}"


def bar_image(text: str, frac: float, color: str, w: int = 120, h: int = 20) -> QImage:
    """A bar that fills `frac` of its width in `color`, the number at its left edge, white with a dark outline."""
    img = QImage(w, h, QImage.Format_ARGB32); img.fill(QColor(theme.PANEL))
    p = QPainter(img); p.setRenderHint(QPainter.Antialiasing)
    frac = max(0.0, min(1.0, frac))
    p.setPen(QColor(theme.BORDER)); p.setBrush(QColor("#202b38")); p.drawRoundedRect(0, 0, w - 1, h - 1, 4, 4)
    if frac > 0:
        p.setPen(QColor(0, 0, 0, 0)); p.setBrush(QColor(color)); p.drawRoundedRect(1, 1, max(4, int((w - 2) * frac)), h - 2, 3, 3)
    f = QFont(); f.setPointSize(9); f.setBold(True); p.setFont(f)
    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):                                              # v0.41.211 (XO): white number at the left edge with a thin dark outline, readable on the fill and on the empty track
        p.setPen(QColor(0, 0, 0, 200)); p.drawText(7 + dx, dy, w - 7, h, 0x81, text)               # AlignLeft | AlignVCenter
    p.setPen(QColor("#ffffff")); p.drawText(7, 0, w - 7, h, 0x81, text)
    p.end()
    return img


class Images:
    """Collects the bar images of one page and hands them to the QTextBrowser's document as named resources."""
    def __init__(self):
        self.items = {}

    def bar(self, text: str, frac: float, band: str) -> tuple:
        name = f"bar{len(self.items)}"
        self.items[name] = bar_image(text, frac, COLORS[band])
        return ("html", f"<img src='{name}'>")

    def apply(self, browser, doc_html: str) -> None:
        doc = browser.document()
        for n, img in self.items.items():
            doc.addResource(QTextDocument.ImageResource, QUrl(n), img)
        browser.setHtml(doc_html)
