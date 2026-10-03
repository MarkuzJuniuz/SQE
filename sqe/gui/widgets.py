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


class MapView(QWidget):
    """Schematic theatre map: positions only (no terrain imagery). North is up."""
    def __init__(self):
        super().__init__(); self.state = None; self.setMinimumSize(420, 300)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_state(self, st):
        self.state = st; self.update()

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(theme.PANEL))
        st = self.state
        if not st:
            return
        pts = [(b.y, -b.x) for b in st.bases.values()] + [(a.y, -a.x) for a in st.assets.values()]
        xs, ys = [q[0] for q in pts], [q[1] for q in pts]
        minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
        m = 34
        sc = min((self.width() - 2 * m) / max(1, maxx - minx), (self.height() - 2 * m) / max(1, maxy - miny))
        ox = (self.width() - sc * (maxx - minx)) / 2; oy = (self.height() - sc * (maxy - miny)) / 2
        P = lambda x, y: QPointF(ox + ((y) - minx) * sc, oy + ((-x) - miny) * sc)
        p.setPen(QPen(QColor(theme.BORDER), 1))
        for i in range(1, 6):
            p.drawLine(int(self.width() * i / 6), 0, int(self.width() * i / 6), self.height())
            p.drawLine(0, int(self.height() * i / 6), self.width(), int(self.height() * i / 6))
        f = QFont(); f.setPointSize(8); p.setFont(f)
        for a in st.assets.values():
            q = P(a.x, a.y)
            dead = a.destroyed
            col = QColor("#4a5566") if dead else QColor(theme.RED).darker(int(100 + 70 * (1 - a.health)))
            p.setPen(Qt.NoPen); p.setBrush(QBrush(col))
            if a.kind == AssetKind.AIRFIELD:
                p.drawRect(QRectF(q.x() - 6, q.y() - 6, 12, 12))
            elif a.kind == AssetKind.SAM:
                p.drawPolygon(QPolygonF([QPointF(q.x(), q.y() - 6), QPointF(q.x() - 6, q.y() + 5), QPointF(q.x() + 6, q.y() + 5)]))
            elif a.kind == AssetKind.ARMOR:
                p.drawRect(QRectF(q.x() - 8, q.y() - 3, 16, 6))
            elif a.kind == AssetKind.EWR:
                p.drawEllipse(q, 3, 3)
            else:
                p.drawPolygon(QPolygonF([QPointF(q.x(), q.y() - 6), QPointF(q.x() + 6, q.y()), QPointF(q.x(), q.y() + 6), QPointF(q.x() - 6, q.y())]))
            if a.kind in (AssetKind.AIRFIELD, AssetKind.C2):
                p.setPen(QColor(theme.DIM)); p.drawText(QPointF(q.x() + 9, q.y() + 4), a.name.split(" (")[0][:18])
        for b in st.bases.values():
            q = P(b.x, b.y)
            p.setPen(Qt.NoPen); p.setBrush(QBrush(QColor(theme.BLUE)))
            if b.kind == BaseKind.CARRIER:
                p.drawPolygon(QPolygonF([QPointF(q.x() - 11, q.y() - 4), QPointF(q.x() + 11, q.y() - 4), QPointF(q.x() + 7, q.y() + 5), QPointF(q.x() - 11, q.y() + 5)]))
            else:
                p.drawEllipse(q, 6, 6)
            p.setPen(QColor(theme.TEXT)); p.drawText(QPointF(q.x() + 10, q.y() + 4), b.name.replace(" AB", "")[:20])
        p.setPen(QColor(theme.DIM))
        p.drawText(10, self.height() - 24, "North up. Blue = coalition, red = enemy (fades as destroyed).")
        p.drawText(10, self.height() - 10, "Square airfield, triangle SAM, bar armor, diamond HQ / depot.")
