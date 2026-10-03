from __future__ import annotations
import sys
import traceback
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtGui import QAction, QColor, QFont
from PySide6.QtWidgets import (QApplication, QButtonGroup, QComboBox, QDialog, QFileDialog, QFrame, QGridLayout, QHBoxLayout,
                               QHeaderView, QLabel, QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QProgressBar,
                               QPushButton, QStackedWidget, QTableWidget, QTableWidgetItem, QTabWidget, QTextBrowser,
                               QVBoxLayout, QWidget)

from .. import APP_NAME, CAMPAIGN_EXT, __version__, narrative
from ..aircraft import AIRCRAFT
from ..briefing import threat_lines
from ..difficulty import LEVELS
from ..engine import Session
from ..packages import PackageBuilder
from ..settings import AppSettings
from ..war import totals
from . import theme
from .dialogs import DebriefDialog, NewCampaignDialog, SettingsDialog, WaitingDialog
from .widgets import MapView, StatCard, card


def _tbl(headers, stretch_last=True) -> QTableWidget:
    t = QTableWidget(0, len(headers)); t.setHorizontalHeaderLabels(headers); t.verticalHeader().setVisible(False)
    t.setEditTriggers(QTableWidget.NoEditTriggers); t.setSelectionBehavior(QTableWidget.SelectRows)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch); t.setAlternatingRowColors(False)
    return t


def _item(text, color=None, center=False):
    i = QTableWidgetItem(str(text))
    if color:
        i.setForeground(QColor(color))
    if center:
        i.setTextAlignment(Qt.AlignCenter)
    return i


class OverviewPage(QWidget):
    def __init__(self):
        super().__init__()
        root = QHBoxLayout(self); root.setSpacing(16)
        left = QVBoxLayout(); root.addLayout(left, 5)
        c = card(); left.addWidget(c)
        h = QLabel("THE CONFLICT"); h.setObjectName("small"); c.layout().addWidget(h)
        self.op = QLabel(narrative.TITLE); self.op.setObjectName("title"); c.layout().addWidget(self.op)
        self.phase = QLabel(); self.phase.setObjectName("h2"); self.phase.setStyleSheet(f"color:{theme.AMBER};"); self.phase.setWordWrap(True)
        c.layout().addWidget(self.phase)
        self.txt = QTextBrowser(); self.txt.setFrameShape(QFrame.NoFrame); self.txt.setStyleSheet("background:transparent;border:none;")
        c.layout().addWidget(self.txt, 1)
        right = QVBoxLayout(); root.addLayout(right, 6)
        g = QGridLayout(); g.setSpacing(12); right.addLayout(g)
        self.cards = {"fa": StatCard("Coalition air", theme.BLUE), "ea": StatCard("Enemy air", theme.RED),
                      "ad": StatCard("Air defences", theme.AMBER), "ar": StatCard("Armored advance", theme.GREEN)}
        for i, k in enumerate(("fa", "ea", "ad", "ar")):
            g.addWidget(self.cards[k], i // 2, i % 2)
        mc = card(); right.addWidget(mc, 1)
        self.map = MapView(); mc.layout().addWidget(self.map)

    def refresh(self, st):
        n, name, text = narrative.phase(st)
        self.phase.setText(name)
        self.txt.setHtml(f"<p style='font-size:14px;line-height:150%'>{text}</p><hr>" +
                         "".join(f"<p style='color:#b9c6d6;line-height:150%'>{p}</p>" for p in narrative.BACKGROUND.split("\n\n")))
        t = totals(st)
        self.cards["fa"].set(f"{t['friendly_air']:.0%}", f"{t['fa']} of {t['fz']} aircraft")
        self.cards["ea"].set(f"{t['enemy_air']:.0%}", f"{t['ea']} of {t['ez']} aircraft")
        self.cards["ad"].set(f"{t['iads']:.0%}", "SAM / radar sites operational")
        self.cards["ar"].set(f"{t['armor']:.0%}", "column strength")
        self.map.set_state(st)


class MissionsPage(QWidget):
    def __init__(self, win):
        super().__init__(); self.win = win; self.pkgs = []
        root = QHBoxLayout(self); root.setSpacing(16)
        left = QVBoxLayout(); root.addLayout(left, 4)
        self.day = QLabel(); self.day.setObjectName("h2"); left.addWidget(self.day)
        self.lst = QListWidget(); left.addWidget(self.lst, 1); self.lst.currentRowChanged.connect(self._show)
        right = QVBoxLayout(); root.addLayout(right, 6)
        self.c = card(); right.addWidget(self.c, 1)
        L = self.c.layout()
        self.title = QLabel(); self.title.setObjectName("title"); self.title.setWordWrap(True); L.addWidget(self.title)
        self.intent = QLabel(); self.intent.setObjectName("dim"); self.intent.setWordWrap(True); L.addWidget(self.intent)
        self.ft = _tbl(["Flight", "Aircraft", "Qty", "Role", "Based at", ""]); self.ft.setMaximumHeight(210); L.addWidget(self.ft)
        hh = self.ft.horizontalHeader()
        for c, m in enumerate((QHeaderView.ResizeToContents, QHeaderView.Stretch, QHeaderView.ResizeToContents, QHeaderView.ResizeToContents, QHeaderView.Stretch, QHeaderView.ResizeToContents)):
            hh.setSectionResizeMode(c, m)
        self.sup = QLabel(); self.sup.setObjectName("dim"); self.sup.setWordWrap(True); L.addWidget(self.sup)
        self.thr = QLabel(); self.thr.setWordWrap(True); self.thr.setStyleSheet(f"color:{theme.AMBER};"); L.addWidget(self.thr)
        L.addStretch(1)
        row = QHBoxLayout(); L.addLayout(row)
        row.addWidget(QLabel("Your flight")); self.pick = QComboBox(); row.addWidget(self.pick, 1)
        self.fly = QPushButton("FLY"); self.fly.setObjectName("primary"); row.addWidget(self.fly)
        self.note = QLabel("Push time, TOT and the briefing are set when you press FLY."); self.note.setObjectName("small"); L.addWidget(self.note)
        self.resume = QPushButton("Resume pending sortie..."); self.resume.setObjectName("danger"); self.resume.hide(); L.addWidget(self.resume)
        self.fly.clicked.connect(self._fly); self.resume.clicked.connect(win.wait_for_results)

    def refresh(self, sess: Session):
        st = sess.state; self.sess = sess
        self.pkgs = sess.packages()
        self.day.setText(f"Day {st.day} tasking order")
        self.lst.blockSignals(True); self.lst.clear()
        for p in self.pkgs:
            ok = bool(sess.flyable(p))
            it = QListWidgetItem(f"#{p.number}  {p.objective.type.value.replace('_', ' ')}"
                                 f"{'   [JOINT]' if p.joint else ''}\n{p.objective.description}" + ("" if ok else "\n(no flight for your aircraft)"))
            it.setData(Qt.UserRole, p.number); it.setSizeHint(QSize(0, 66))
            if not ok:
                it.setForeground(QColor(theme.DIM))
            self.lst.addItem(it)
        self.lst.blockSignals(False)
        self.resume.setVisible(bool(st.pending))
        if self.pkgs:
            self.lst.setCurrentRow(0); self._show(0)

    def _show(self, row):
        if row < 0 or row >= len(self.pkgs):
            return
        p = self.pkgs[row]; st = self.sess.state
        self.title.setText(p.objective.description)
        import random
        self.intent.setText(narrative.commander_intent(p.objective.type, random.Random(p.number * 7 + st.day)))
        self.ft.setRowCount(len(p.flights))
        opts = {f.id for f in self.sess.flyable(p)}
        for i, f in enumerate(p.flights):
            spec = AIRCRAFT[f.aircraft]
            yours = f.id in opts
            col = theme.GREEN if yours else None
            for j, v in enumerate((f.callsign, spec.display, f.count, f.role.value, st.bases[f.base_id].name.replace(" AB", ""),
                                   "you can fly" if yours else spec.service)):
                self.ft.setItem(i, j, _item(v, col if (yours and j in (0, 5)) else (theme.DIM if j == 5 else None), center=(j == 2)))
        self.sup.setText("Support: " + ", ".join(f"{s.label} ({s.slot.title()})" for s in p.support) +
                         ("  |  JTAC on the ground" if p.jtac else "") + ("  |  Joint Navy / Air Force package" if p.joint else ""))
        tx, ty = PackageBuilder(st).target_xy(p.objective)
        th = threat_lines(st, p, tx, ty)[:4]
        self.thr.setText("Threats near target: " + ("; ".join(th) if th else "none known"))
        self.pick.clear()
        for f in self.sess.flyable(p):
            self.pick.addItem(f"{f.callsign}  -  {f.count}x {AIRCRAFT[f.aircraft].display}, {f.role.value}", f.id)
        self.fly.setEnabled(self.pick.count() > 0 and st.status == "ACTIVE")
        self.pick.setEnabled(self.pick.count() > 0)

    def _fly(self):
        row = self.lst.currentRow()
        if row >= 0 and self.pick.currentData():
            self.win.do_fly(self.pkgs[row].number, self.pick.currentData())


class ForcesPage(QWidget):
    def __init__(self):
        super().__init__(); lay = QVBoxLayout(self)
        self.tabs = QTabWidget(); lay.addWidget(self.tabs)
        self.sq = _tbl(["Squadron", "Aircraft", "Service", "Based at", "Serviceable", "Readiness"])
        self.ea = _tbl(["Enemy air wing", "Types", "Serviceable", "Strength"])
        self.as_ = _tbl(["Enemy asset", "Type", "Condition"])
        for t, n in ((self.sq, "Coalition squadrons"), (self.ea, "Enemy air wings"), (self.as_, "Enemy assets")):
            self.tabs.addTab(t, n)

    @staticmethod
    def _bar(frac, color):
        b = QProgressBar(); b.setRange(0, 100); b.setValue(int(round(frac * 100))); b.setFormat("%p%")
        b.setStyleSheet(f"QProgressBar::chunk {{ background: {color}; border-radius:5px; }}"); return b

    def refresh(self, st):
        sqs = list(st.squadrons.values()); self.sq.setRowCount(len(sqs))
        for i, s in enumerate(sqs):
            sp = AIRCRAFT[s.aircraft]
            for j, v in enumerate((s.name, sp.display, sp.service, st.bases[s.base_id].name, f"{s.available} / {s.authorized}")):
                self.sq.setItem(i, j, _item(v))
            self.sq.setCellWidget(i, 5, self._bar(s.readiness, theme.BLUE))
        self.ea.setRowCount(len(st.enemy_air))
        for i, w in enumerate(st.enemy_air):
            for j, v in enumerate((st.assets[w.base_asset_id].name, ", ".join(w.types), f"{w.available} / {w.authorized}")):
                self.ea.setItem(i, j, _item(v))
            self.ea.setCellWidget(i, 3, self._bar(w.available / max(1, w.authorized), theme.RED))
        al = sorted(st.assets.values(), key=lambda a: (a.kind.value, a.name)); self.as_.setRowCount(len(al))
        for i, a in enumerate(al):
            self.as_.setItem(i, 0, _item(a.name, theme.DIM if a.destroyed else None)); self.as_.setItem(i, 1, _item(a.kind.value.title()))
            self.as_.setCellWidget(i, 2, self._bar(a.health, theme.GREEN if a.health > 0.6 else theme.AMBER if a.health > 0.25 else theme.RED))


class LogPage(QWidget):
    def __init__(self):
        super().__init__(); lay = QHBoxLayout(self); lay.setSpacing(16)
        self.hist = _tbl(["Day", "Sortie", "Objective", "You", "Lost", "Kills"]); lay.addWidget(self.hist, 5)
        self.log = QTextBrowser(); lay.addWidget(self.log, 4)

    def refresh(self, st):
        h = list(reversed(st.history)); self.hist.setRowCount(len(h))
        for i, e in enumerate(h):
            for j, v in enumerate((e["day"], e["sortie"], e["objective"], e["player"], e["blue_air_lost"], e["red_air_lost"])):
                self.hist.setItem(i, j, _item(v, center=(j != 2)))
        self.log.setHtml("<br>".join(reversed(st.log[-200:])))


class MainWindow(QMainWindow):
    def __init__(self, session: Session):
        super().__init__(); self.session = session
        self.setWindowTitle(f"{APP_NAME}"); self.resize(1280, 820); self.setMinimumSize(1100, 700)
        root = QWidget(); root.setObjectName("root"); self.setCentralWidget(root)
        lay = QHBoxLayout(root); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(0)
        side = QFrame(); side.setObjectName("sidebar"); side.setFixedWidth(210); lay.addWidget(side)
        sl = QVBoxLayout(side); sl.setContentsMargins(14, 18, 14, 14); sl.setSpacing(4)
        lg = QLabel("SQE"); lg.setStyleSheet(f"font-size:30px;font-weight:800;color:{theme.BLUE};"); sl.addWidget(lg)
        sub = QLabel("Squadron Campaign Engine"); sub.setObjectName("small"); sl.addWidget(sub); sl.addSpacing(18)
        self.stack = QStackedWidget()
        self.p_over, self.p_miss, self.p_forces, self.p_log = OverviewPage(), MissionsPage(self), ForcesPage(), LogPage()
        grp = QButtonGroup(self); grp.setExclusive(True)
        for i, (name, page) in enumerate((("Overview", self.p_over), ("Missions", self.p_miss), ("Forces", self.p_forces), ("Log", self.p_log))):
            b = QPushButton(name); b.setObjectName("nav"); b.setCheckable(True); grp.addButton(b, i); sl.addWidget(b)
            self.stack.addWidget(page); b.clicked.connect(lambda _=0, k=i: self.stack.setCurrentIndex(k))
            if i == 1:
                self.nav_missions = b
        grp.button(0).setChecked(True); sl.addStretch(1)
        self.camp = QLabel(""); self.camp.setObjectName("dim"); self.camp.setWordWrap(True); sl.addWidget(self.camp)
        st_btn = QPushButton("Settings"); st_btn.clicked.connect(self.settings); sl.addWidget(st_btn)
        vl = QLabel(f"v{__version__}"); vl.setObjectName("small"); sl.addWidget(vl)
        main = QVBoxLayout(); main.setContentsMargins(22, 18, 22, 18); main.setSpacing(14); lay.addLayout(main, 1)
        hdr = QHBoxLayout(); main.addLayout(hdr)
        self.h_title = QLabel(); self.h_title.setObjectName("title"); hdr.addWidget(self.h_title)
        self.pills = [QLabel() for _ in range(4)]
        for p in self.pills:
            p.setObjectName("pill"); hdr.addWidget(p)
        hdr.addStretch(1)
        self.banner = QLabel(); self.banner.setObjectName("pill"); hdr.addWidget(self.banner)
        main.addWidget(self.stack, 1)
        self._menus()

    # ---- menus ---------------------------------------------------------------------------------------
    def _menus(self):
        mb = self.menuBar(); f = mb.addMenu("&File")
        def act(text, fn, key=None):
            a = QAction(text, self); a.triggered.connect(fn)
            if key: a.setShortcut(key)
            f.addAction(a); return a
        act("&New Campaign...", self.new_campaign, "Ctrl+N"); act("&Open Campaign...", self.open_campaign, "Ctrl+O")
        self.recent = f.addMenu("Open &Recent"); self.recent.aboutToShow.connect(self._recent)
        f.addSeparator(); act("&Save", self.save, "Ctrl+S"); act("Save &As...", self.save_as, "Ctrl+Shift+S")
        f.addSeparator(); act("S&ettings...", self.settings, "Ctrl+,"); f.addSeparator(); act("E&xit", self.close, "Alt+F4")

    def _recent(self):
        self.recent.clear()
        for p in self.session.list_campaigns()[:8]:
            a = QAction(p.stem, self); a.triggered.connect(lambda _=0, q=p: self._open(q)); self.recent.addAction(a)
        if self.recent.isEmpty():
            self.recent.addAction(QAction("(none found)", self)).setEnabled(False)

    # ---- campaign ops -------------------------------------------------------------------------------------
    def new_campaign(self):
        if self.session.settings.problems():
            self.settings()
            if self.session.settings.problems():
                return
        dlg = NewCampaignDialog(self)
        if dlg.exec() == QDialog.Accepted:
            try:
                self.session.new(*dlg.values()); self.refresh_all()
            except Exception:
                QMessageBox.critical(self, "Could not create campaign", traceback.format_exc())

    def open_campaign(self):
        f, _ = QFileDialog.getOpenFileName(self, "Open campaign", str(self.session.campaigns_dir()), f"SQE campaign (*{CAMPAIGN_EXT})")
        if f:
            self._open(f)

    def _open(self, path):
        try:
            self.session.open(path); self.refresh_all()
        except Exception:
            QMessageBox.critical(self, "Could not open campaign", traceback.format_exc())

    def save(self):
        if self.session.state:
            self.session.save()

    def save_as(self):
        if not self.session.state:
            return
        f, _ = QFileDialog.getSaveFileName(self, "Save campaign as", str(self.session.campaigns_dir() / f"{self.session.state.name}{CAMPAIGN_EXT}"),
                                           f"SQE campaign (*{CAMPAIGN_EXT})")
        if f:
            self.session.save(f if f.endswith(CAMPAIGN_EXT) else f + CAMPAIGN_EXT); self.refresh_all()

    def settings(self):
        if SettingsDialog(self.session.settings, self).exec() == QDialog.Accepted:
            self.refresh_all()

    # ---- flying --------------------------------------------------------------------------------------------------------
    def do_fly(self, number, flight_id):
        sess = self.session
        if sess.state.pending and QMessageBox.question(self, "Sortie pending",
                "A sortie is already built and waiting for results. Discard it and build a new one?") != QMessageBox.Yes:
            return
        if sess.settings.problems():
            QMessageBox.warning(self, "Settings", "\n".join(sess.settings.problems())); self.settings(); return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            res = sess.fly(number, flight_id)
        except Exception:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "Could not build the mission", traceback.format_exc()); return
        QApplication.restoreOverrideCursor()
        if res.warnings:
            QMessageBox.information(self, "Built with notes", "\n".join(res.warnings))
        self.refresh_all(); self.wait_for_results()

    def wait_for_results(self):
        dlg = WaitingDialog(self.session, self); r = dlg.exec()
        if r == QDialog.Accepted and dlg.data is not None:
            out = self.session.apply(dlg.data); self.refresh_all(); DebriefDialog(out, self.session.state, self).exec(); self.refresh_all()
            self.stack.setCurrentIndex(0)
        elif r == 2:
            self.session.abort(); self.refresh_all()
        else:
            self.refresh_all()

    # ---- refresh ----------------------------------------------------------------------------------------------------------
    def refresh_all(self):
        st = self.session.state
        if not st:
            self.h_title.setText("No campaign loaded"); return
        for p in (self.p_over, self.p_forces, self.p_log):
            p.refresh(st)
        self.p_miss.refresh(self.session)
        n, name, _ = narrative.phase(st)
        self.h_title.setText(st.name)
        for pill, txt in zip(self.pills, (f"Day {st.day}", LEVELS[st.level].name, f"Phase {n}", st.player.aircraft)):
            pill.setText(txt)
        self.banner.setText({"ACTIVE": "Sortie pending" if st.pending else "", "VICTORY": "VICTORY", "DEFEAT": "DEFEAT"}[st.status])
        self.banner.setVisible(bool(self.banner.text()))
        self.camp.setText(f"{st.name}\n{self.session.path.name if self.session.path else ''}")
        self.setWindowTitle(f"{APP_NAME} - {st.name}")


def run():
    app = QApplication(sys.argv)
    app.setStyleSheet(theme.QSS); app.setApplicationName(APP_NAME)
    f = app.font(); f.setPointSize(10); app.setFont(f)
    settings = AppSettings.load(); sess = Session(settings)
    w = MainWindow(sess); w.show()
    def start():
        if settings.problems():
            QMessageBox.information(w, "Welcome", "First, tell SQE where DCS keeps your saves (Settings).")
            w.settings()
        last = Path(settings.last_campaign) if settings.last_campaign else None
        if last and last.exists():
            w._open(last)
        elif not settings.problems():
            w.new_campaign()
    QTimer.singleShot(0, start)
    sys.exit(app.exec())
