from __future__ import annotations
import math
from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QColor, QPainter, QPen, QBrush, QPolygonF, QFont
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget, QSizePolicy
from ..models import AssetKind, BaseKind
from . import theme


def card(layout_cls=QVBoxLayout, margins=(16, 14, 16, 14), spacing=8) -> QFrame:
    f = QFrame(); f.setObjectName("card")
    lay = layout_cls(f); lay.setContentsMargins(*margins); lay.setSpacing(spacing)
    return f


class StatCard(QFrame):
    def __init__(self, label: str, color: str):
        super().__init__(); self.setObjectName("card"); self.color = color
        lay = QVBoxLayout(self); lay.setContentsMargins(16, 12, 16, 12); lay.setSpacing(2)
        self.l = QLabel(label.upper()); self.l.setObjectName("small")
        self.v = QLabel("-"); self.v.setObjectName("big"); self.v.setStyleSheet(f"color:{color};")
        self.s = QLabel(""); self.s.setObjectName("dim")
        for w in (self.l, self.v, self.s):
            lay.addWidget(w)

    def set(self, value: str, sub: str = ""):
        self.v.setText(value); self.s.setText(sub)


def _load_geo():
    from .. import theatres
    return theatres.active()["id"], theatres.geo()


_GEO = None
_GEO_ID = None
SEA, LAND, COAST, BORDER = "#0a141f", "#16212e", "#33485f", "#3d5169"


class MapView(QWidget):
    """Theatre map: coastline and borders (Natural Earth, public domain) with bases, targets and SAM threat rings. North is up."""
    def __init__(self):
        super().__init__(); self.state = None; self.rings = True; self.setMinimumSize(420, 300)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_state(self, st):
        self.state = st; self.update()

    def set_rings(self, on: bool):
        self.rings = on; self.update()

    def _draw_ground(self, p, P, st):
        """The ground war: strengths at the sector centres and the contact line across the axis."""
        from .. import ground
        if not ground.active(st):
            return
        import math
        g = st.ground; c = g["centers"]
        f = QFont(); f.setPointSize(8); f.setBold(True); p.setFont(f)
        for i, (cx, cy) in enumerate(c):                                      # a sector number and a small red | blue bar: the figures are in the list above the map
            q = P(cx, cy); r, b = g["red"][i], g["blue"][i]
            w = 24.0; tot = max(1.0, r + b); x0 = q.x() - w / 2; y0 = q.y() + 9
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(QColor(theme.RED if r >= ground.MIN_FORCE else theme.DIM))); p.drawRect(QRectF(x0, y0, w * r / tot, 4))
            p.setBrush(QBrush(QColor(theme.BLUE if b >= ground.MIN_FORCE else theme.DIM))); p.drawRect(QRectF(x0 + w * r / tot, y0, w * b / tot, 4))
            p.setPen(QColor(theme.TEXT)); p.drawText(QPointF(q.x() - 3, q.y() + 7), str(i + 1))
        lx, ly = ground.line_xy(g)
        dx, dy = c[-1][0] - c[0][0], c[-1][1] - c[0][1]; n = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / n, dx / n; half = 25000.0
        pen = QPen(QColor(theme.AMBER), 2); pen.setStyle(Qt.DashLine); p.setPen(pen)
        p.drawLine(P(lx + nx * half, ly + ny * half), P(lx - nx * half, ly - ny * half))
        p.setPen(QColor(theme.AMBER)); p.drawText(P(lx + nx * half, ly + ny * half) + QPointF(8, -6), "front line")

    def paintEvent(self, _):
        global _GEO, _GEO_ID
        from .. import theatres
        if _GEO is None or _GEO_ID != theatres.active()["id"]:
            _GEO_ID, _GEO = _load_geo()
        from ..briefing import RANGE_NM
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(SEA))
        st = self.state
        if not st:
            return
        pts = [(b.y, -b.x) for b in st.bases.values()] + [(a.y, -a.x) for a in st.assets.values()]
        xs, ys = [q[0] for q in pts], [q[1] for q in pts]
        pad = 0.14 * max(max(xs) - min(xs), max(ys) - min(ys), 1)
        minx, maxx, miny, maxy = min(xs) - pad, max(xs) + pad, min(ys) - pad, max(ys) + pad
        sc = min(self.width() / max(1, maxx - minx), self.height() / max(1, maxy - miny))
        ox = (self.width() - sc * (maxx - minx)) / 2; oy = (self.height() - sc * (maxy - miny)) / 2
        P = lambda x, y: QPointF(ox + (y - minx) * sc, oy + ((-x) - miny) * sc)
        # land, lakes, coast, borders
        p.setPen(QPen(QColor(COAST), 1.2)); p.setBrush(QBrush(QColor(LAND)))
        for ring in _GEO["land"]:
            p.drawPolygon(QPolygonF([P(x, y) for x, y in ring]))
        p.setPen(Qt.NoPen); p.setBrush(QBrush(QColor(SEA)))
        for ring in _GEO["lakes"]:
            p.drawPolygon(QPolygonF([P(x, y) for x, y in ring]))
        pen = QPen(QColor(BORDER), 1); pen.setStyle(Qt.DashLine); p.setPen(pen); p.setBrush(Qt.NoBrush)
        for line in _GEO["borders"]:
            p.drawPolyline(QPolygonF([P(x, y) for x, y in line]))
        # SAM threat rings
        if self.rings:
            for a in st.assets.values():
                if a.kind == AssetKind.SAM and not a.destroyed and a.variant in RANGE_NM and RANGE_NM[a.variant] >= 8:
                    c = P(a.x, a.y); r = RANGE_NM[a.variant] * 1852 * sc
                    p.setPen(QPen(QColor(255, 93, 108, 170), 1)); p.setBrush(QBrush(QColor(255, 93, 108, 26)))
                    p.drawEllipse(c, r, r)
        f = QFont(); f.setPointSize(8); p.setFont(f)
        for a in st.assets.values():
            q = P(a.x, a.y); dead = a.destroyed
            col = QColor("#4a5566") if dead else QColor(theme.RED).darker(int(100 + 70 * (1 - a.health)))
            p.setPen(Qt.NoPen); p.setBrush(QBrush(col))
            if a.kind == AssetKind.AIRFIELD:
                p.drawRect(QRectF(q.x() - 5, q.y() - 5, 10, 10))
            elif a.kind == AssetKind.SAM:
                p.drawPolygon(QPolygonF([QPointF(q.x(), q.y() - 5), QPointF(q.x() - 5, q.y() + 4), QPointF(q.x() + 5, q.y() + 4)]))
            elif a.kind == AssetKind.ARMOR:
                p.drawRect(QRectF(q.x() - 8, q.y() - 3, 16, 6))
            elif a.kind == AssetKind.EWR:
                p.drawEllipse(q, 3, 3)
            else:
                p.drawPolygon(QPolygonF([QPointF(q.x(), q.y() - 5), QPointF(q.x() + 5, q.y()), QPointF(q.x(), q.y() + 5), QPointF(q.x() - 5, q.y())]))
            if a.kind in (AssetKind.AIRFIELD, AssetKind.C2):
                p.setPen(QColor("#9fb0c4")); p.drawText(QPointF(q.x() + 8, q.y() + 4), a.name.split(" (")[0][:18])
        for b in st.bases.values():
            q = P(b.x, b.y)
            p.setPen(Qt.NoPen); p.setBrush(QBrush(QColor(theme.BLUE)))
            if b.kind == BaseKind.CARRIER:
                p.drawPolygon(QPolygonF([QPointF(q.x() - 11, q.y() - 4), QPointF(q.x() + 11, q.y() - 4), QPointF(q.x() + 7, q.y() + 5), QPointF(q.x() - 11, q.y() + 5)]))
            else:
                p.drawEllipse(q, 5, 5)
            p.setPen(QColor(theme.TEXT)); p.drawText(QPointF(q.x() + 9, q.y() + 4), b.name.replace(" AB", "")[:20])
        self._draw_ground(p, P, st)
        p.setPen(QColor(theme.DIM))
        p.drawText(10, self.height() - 22, "North up. Blue = coalition, red = enemy. Circles = SAM threat range.")
        p.drawText(10, self.height() - 8, "Square airfield, triangle SAM, bar armor, diamond HQ/depot.")
