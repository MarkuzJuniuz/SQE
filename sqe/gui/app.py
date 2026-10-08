from __future__ import annotations
import sys
import traceback
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtGui import QAction, QColor, QFont
from PySide6.QtWidgets import (QApplication, QButtonGroup, QComboBox, QDialog, QFileDialog, QFrame, QGridLayout, QHBoxLayout,
                               QHeaderView, QLabel, QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QProgressBar,
                               QPushButton, QCheckBox, QStackedWidget, QTableWidget, QTableWidgetItem, QTabWidget, QTextBrowser,
                               QVBoxLayout, QWidget)

from .. import APP_NAME, CAMPAIGN_EXT, __version__, narrative
from ..aircraft import AIRCRAFT
from ..briefing import threat_lines
from ..timeofday import is_night
from ..difficulty import LEVELS
from ..engine import Session
from ..packages import PackageBuilder, folded_n_def
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
        top = QHBoxLayout(); mc.layout().addLayout(top)
        t = QLabel("THEATRE"); t.setObjectName("small"); top.addWidget(t); top.addStretch(1)
        self.rings = QCheckBox("SAM threat rings"); self.rings.setChecked(True); top.addWidget(self.rings)
        self.map = MapView(); mc.layout().addWidget(self.map, 1)
        self.rings.toggled.connect(self.map.set_rings)

    def refresh(self, st):
        n, name, text = narrative.phase(st)
        self.phase.setText(f"{name}   |   front: stage {min(3, st.front + 1)} of 3")
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
        frow = QHBoxLayout(); fl = QLabel("Show"); fl.setObjectName("small"); frow.addWidget(fl)
        self.flt = QComboBox(); self.flt.addItem("My squadron", "squadron"); self.flt.addItem("All packages", "all")
        self.flt.setToolTip("My squadron: only packages with a flight from your squadron.  All: every package of the day.")
        frow.addWidget(self.flt, 1); left.addLayout(frow)
        self.flt.currentIndexChanged.connect(self._filter_changed)
        self.lst = QListWidget(); left.addWidget(self.lst, 1); self.lst.currentRowChanged.connect(self._show)
        right = QVBoxLayout(); root.addLayout(right, 6)
        self.c = card(); right.addWidget(self.c, 1)
        L = self.c.layout()
        self.title = QLabel(); self.title.setObjectName("title"); self.title.setWordWrap(True); L.addWidget(self.title)
        self.when = QLabel(); self.when.setObjectName("h2"); self.when.setStyleSheet(f"color:{theme.AMBER};"); L.addWidget(self.when)
        self.intent = QLabel(); self.intent.setObjectName("dim"); self.intent.setWordWrap(True); L.addWidget(self.intent)
        self.ft = _tbl(["Flight", "Aircraft", "Qty", "Task", "Based at", ""])
        self.ft.setSelectionMode(QTableWidget.NoSelection); self.ft.setFocusPolicy(Qt.NoFocus)
        self.ft.setStyleSheet("QTableWidget::item:selected, QTableWidget::item:hover, QTableWidget::item:focus { background: transparent; border: none; }")
        self.ft.verticalHeader().setDefaultSectionSize(42)
        self.ft.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        hh = self.ft.horizontalHeader()
        for c, m in enumerate((QHeaderView.ResizeToContents, QHeaderView.Stretch, QHeaderView.ResizeToContents, QHeaderView.Stretch,
                               QHeaderView.Stretch, QHeaderView.Fixed)):
            hh.setSectionResizeMode(c, m)
        hh.resizeSection(5, 100)
        L.addWidget(self.ft)
        self.sup = QLabel(); self.sup.setObjectName("dim"); self.sup.setWordWrap(True); L.addWidget(self.sup)
        self.thr = QLabel(); self.thr.setWordWrap(True); self.thr.setStyleSheet(f"color:{theme.AMBER};"); L.addWidget(self.thr)
        L.addStretch(1)
        self.note = QLabel("Press FLY on your flight. Push time, TOT and the briefing are built when you do."); self.note.setObjectName("small"); L.addWidget(self.note)
        self.resume = QPushButton("Resume pending sortie..."); self.resume.setObjectName("danger"); self.resume.hide(); L.addWidget(self.resume)
        self.resume.clicked.connect(win.wait_for_results)
        self.skip = QPushButton("Skip Turn"); self.skip.setToolTip("Stand down for today: the whole tasking order is resolved by the war simulation and the date advances.")
        self.skip.clicked.connect(win.skip_turn); L.addWidget(self.skip, 0, Qt.AlignRight)

    def _filter_changed(self):
        if getattr(self, "sess", None) is None or getattr(self, "_loading", False):
            return
        self.sess.settings.flight_filter = self.flt.currentData()
        try:
            self.sess.settings.save()
        except OSError:
            pass
        self.refresh(self.sess)

    def refresh(self, sess: Session):
        st = sess.state; self.sess = sess
        self._loading = True
        self.flt.setCurrentIndex(0 if sess.settings.flight_filter != "all" else 1)
        self._loading = False
        mine_only = sess.settings.flight_filter != "all"
        self.pkgs = [p for p in sess.packages() if (bool(sess.flyable(p)) or not mine_only)]
        self.day.setText(f"{st.campaign_date().strftime('%d %b %Y').upper()}  -  Day {st.day} tasking order  ({len(self.pkgs)} shown)")
        self.lst.blockSignals(True); self.lst.clear()
        for p in self.pkgs:
            ok = bool(sess.flyable(p))
            night = is_night(st.campaign_date(), p.start)
            extra = sess.merge_candidates(p) if ok else []
            it = QListWidgetItem(f"#{p.number}  {p.objective.type.value.replace('_', ' ')}   {p.start}{' (night)' if night else ''}"
                                 f"{'   [JOINT]' if p.joint else ''}{f'   +{len(extra)} package' + ('s' if len(extra) > 1 else '') if extra else ''}"
                                 f"\n{p.objective.description}" + ("" if ok else "\n(no flight for your aircraft)"))
            it.setData(Qt.UserRole, p.number); it.setSizeHint(QSize(0, 66))
            if not ok:
                it.setForeground(QColor(theme.DIM))
            self.lst.addItem(it)
        self.lst.blockSignals(False)
        self.resume.setVisible(bool(st.pending))
        self.skip.setEnabled(st.status == "ACTIVE")
        if self.pkgs:
            self.lst.setCurrentRow(0)

    def _show(self, row):
        if row < 0 or row >= len(self.pkgs):
            return
        p = self.pkgs[row]; st = self.sess.state
        self.title.setText(p.objective.description)
        night = is_night(st.campaign_date(), p.start)
        self.when.setText(f"Mission start {p.start} local ({'night' if night else 'day'})   -   clear weather")
        import random
        self.intent.setText(narrative.commander_intent(p.objective.type, random.Random(p.number * 7 + st.day)))
        for r in range(self.ft.rowCount()):                     # drop old buttons completely (no ghost widgets)
            old = self.ft.cellWidget(r, 5)
            if old is not None:
                self.ft.removeCellWidget(r, 5); old.setParent(None); old.deleteLater()
        self.ft.clearContents()
        self.ft.setRowCount(len(p.flights)); self.ft.setMinimumHeight(40 + 42 * len(p.flights)); self.ft.setMaximumHeight(60 + 42 * len(p.flights))
        opts = {f.id for f in self.sess.flyable(p)}
        active = st.status == "ACTIVE"
        for i, f in enumerate(p.flights):
            spec = AIRCRAFT[f.aircraft]; yours = f.id in opts
            vals = (f.callsign, spec.display, f.count, f.task, st.bases[f.base_id].name.replace(" AB", ""))
            for j, v in enumerate(vals):
                self.ft.setItem(i, j, _item(v, theme.GREEN if (yours and j == 0) else (theme.DIM if f.tag else None), center=(j == 2)))
            if yours:
                b = QPushButton("FLY"); b.setObjectName("fly"); b.setEnabled(active); b.setFixedSize(84, 30)
                b.clicked.connect(lambda _=0, n=p.number, fid=f.id: self.win.do_fly(n, fid))
                cont = QWidget(); cl = QHBoxLayout(cont); cl.setContentsMargins(4, 4, 4, 4); cl.addWidget(b, 0, Qt.AlignCenter)
                self.ft.setCellWidget(i, 5, cont)
            else:
                self.ft.removeCellWidget(i, 5)
                self.ft.setItem(i, 5, _item("AI support" if f.tag else f"AI {spec.service}", theme.DIM))
        self.sup.setText("Support: " + ", ".join(f"{s.label} ({s.slot.title()})" for s in p.support) +
                         ("  |  JTAC on the ground" if p.jtac else "") + ("  |  Joint Navy / Air Force package" if p.joint else "") +
                         (("  |  Merged mission: also flies " + ", ".join(f"#{x.number}" for x in self.sess.merge_candidates(p)))
                          if opts and self.sess.merge_candidates(p) else ""))
        tx, ty = PackageBuilder(st).target_xy(p.objective)
        th = threat_lines(st, tx, ty)[:4]
        ex = self.sess.merge_candidates(p)
        nd = folded_n_def(p, ex, self.sess.settings.merge_enemy_pct)
        self.thr.setText((f"Expect about {nd} hostile fighters at the target" + (f" (includes {', '.join('#%d' % x.number for x in ex)})" if ex else "") + ".  " if nd else "") +
                         "Threats near target: " + ("; ".join(th) if th else "none known"))


class ForcesPage(QWidget):
    def __init__(self):
        super().__init__(); lay = QVBoxLayout(self)
        self.tabs = QTabWidget(); lay.addWidget(self.tabs)
        self.sq = _tbl(["Squadron", "Aircraft", "Service", "Based at", "Serviceable", "Readiness"])
        self.ea = _tbl(["Enemy air wing", "Types", "Serviceable", "Strength"])
        self.as_ = _tbl(["Enemy asset", "Type", "Depth", "Condition"])
        self.bs = _tbl(["Coalition base", "Type", "Air defences (Patriot + AAA)"])
        for t, n in ((self.sq, "Coalition squadrons"), (self.bs, "Coalition bases"), (self.ea, "Enemy air wings"), (self.as_, "Enemy assets")):
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
            for j, v in enumerate((st.assets[w.base_asset_id].name + (f"  ({w.squadrons} squadrons)" if w.squadrons > 1 else ""), ", ".join(w.types), f"{w.available} / {w.authorized}")):
                self.ea.setItem(i, j, _item(v))
            self.ea.setCellWidget(i, 3, self._bar(w.available / max(1, w.authorized), theme.RED))
        bl = list(st.bases.values()); self.bs.setRowCount(len(bl))
        for i, b in enumerate(bl):
            self.bs.setItem(i, 0, _item(b.name)); self.bs.setItem(i, 1, _item("Carrier (escorted)" if b.kind.value == "CARRIER" else "Airfield"))
            if b.kind.value == "AIRFIELD":
                self.bs.setCellWidget(i, 2, self._bar(b.defense, theme.GREEN if b.defense > 0.6 else theme.AMBER if b.defense > 0.25 else theme.RED))
            else:
                self.bs.setItem(i, 2, _item("Cruiser + 2 escorts", theme.DIM))
        al = sorted(st.assets.values(), key=lambda a: (a.kind.value, a.name)); self.as_.setRowCount(len(al))
        for i, a in enumerate(al):
            kind = "Garrison" if a.variant == "GARRISON" else (f"SAM {a.variant}" if a.kind.value == "SAM" else a.kind.value.title())
            if a.suppressed:
                kind += "  (radars blinded)"
            tier = ["", "T1 front", "T2 Abkhazia", "T3 coast / north", "T4 deep"][min(4, max(1, a.tier))]
            self.as_.setItem(i, 0, _item(a.name, theme.DIM if a.destroyed else None)); self.as_.setItem(i, 1, _item(kind))
            self.as_.setItem(i, 2, _item(tier + ("" if a.tier <= st.front + 2 else "  (locked)"), theme.DIM if a.tier > st.front + 2 else None))
            self.as_.setCellWidget(i, 3, self._bar(a.health, theme.GREEN if a.health > 0.6 else theme.AMBER if a.health > 0.25 else theme.RED))


class PilotPage(QWidget):
    def __init__(self):
        super().__init__(); lay = QVBoxLayout(self); lay.setSpacing(14)
        self.name = QLabel(); self.name.setObjectName("title"); lay.addWidget(self.name)
        g = QGridLayout(); g.setSpacing(12); lay.addLayout(g)
        self.cards = {k: StatCard(lbl, col) for k, lbl, col in (("sorties", "Sorties", theme.BLUE), ("hours", "Flight time", theme.BLUE),
                      ("air", "Air kills", theme.RED), ("ground", "Ground kills", theme.AMBER), ("landings", "Safe landings", theme.GREEN),
                      ("rescues", "Bail-outs (rescued)", theme.DIM))}
        for i, k in enumerate(self.cards):
            g.addWidget(self.cards[k], i // 3, i % 3)
        h = QLabel("Sortie history"); h.setObjectName("h2"); lay.addWidget(h)
        self.hist = _tbl(["Date", "Sortie", "Objective", "Result", "Kills", "Minutes", "Package losses"]); lay.addWidget(self.hist, 1)

    def refresh(self, st):
        pl = st.pilot or {}
        self.name.setText(f"{st.player.callsign} pilot log")
        h = pl.get("flight_s", 0) / 3600.0
        vals = {"sorties": (str(pl.get("sorties", 0)), ""), "hours": (f"{h:.1f} h", ""), "air": (str(pl.get("kills_air", 0)), ""),
                "ground": (str(pl.get("kills_ground", 0) + pl.get("kills_ship", 0)), "ground and ship"), "landings": (str(pl.get("landings", 0)), ""),
                "rescues": (str(pl.get("rescues", 0)), "you cannot die in this war")}
        for k, (v, s) in vals.items():
            self.cards[k].set(v, s)
        hist = list(reversed(st.history)); self.hist.setRowCount(len(hist))
        nice = {"recovered": "Recovered", "ejected": "Bailed out, rescued", "airborne": "Airborne at end"}
        for i, e in enumerate(hist):
            for j, v in enumerate((e.get("date", f"day {e['day']}"), e["sortie"], e["objective"], nice.get(e["player"], e["player"]),
                                   e.get("kills", 0), e.get("flight_min", 0), e["blue_air_lost"])):
                self.hist.setItem(i, j, _item(v, center=(j != 2)))


class LogPage(QWidget):
    def __init__(self):
        super().__init__(); lay = QVBoxLayout(self)
        h = QLabel("War log"); h.setObjectName("h2"); lay.addWidget(h)
        self.log = QTextBrowser(); lay.addWidget(self.log, 1)

    def refresh(self, st):
        self.log.setHtml("<br>".join(reversed(st.log[-300:])))


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
        self.p_over, self.p_miss, self.p_forces, self.p_pilot, self.p_log = OverviewPage(), MissionsPage(self), ForcesPage(), PilotPage(), LogPage()
        grp = QButtonGroup(self); grp.setExclusive(True)
        for i, (name, page) in enumerate((("Overview", self.p_over), ("Missions", self.p_miss), ("Forces", self.p_forces), ("Pilot", self.p_pilot), ("War log", self.p_log))):
            b = QPushButton(name); b.setObjectName("nav"); b.setCheckable(True); grp.addButton(b, i); sl.addWidget(b)
            self.stack.addWidget(page); b.clicked.connect(lambda _=0, k=i: self.stack.setCurrentIndex(k))
            if i == 1:
                self.nav_missions = b
        grp.button(0).setChecked(True); sl.addStretch(1)
        st_btn = QPushButton("Settings"); st_btn.clicked.connect(self.settings); sl.addWidget(st_btn)
        vl = QLabel(f"v{__version__}"); vl.setObjectName("small"); sl.addWidget(vl)
        main = QVBoxLayout(); main.setContentsMargins(22, 18, 22, 18); main.setSpacing(14); lay.addLayout(main, 1)
        hdr = QHBoxLayout(); main.addLayout(hdr)
        self.h_title = QLabel(); self.h_title.setObjectName("title"); hdr.addWidget(self.h_title)
        self.pills = [QLabel() for _ in range(5)]
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
                v = dlg.values(); self.session.new(v['name'], v['aircraft'], v['level'], start_date=v['start_date'], night_ops=v['night_ops'], squadron=v.get('squadron')); self.refresh_all()
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

    def closeEvent(self, ev):
        st = self.session.state
        if st is not None and st.pending and self.session.settings.auto_patch_scripting and \
                QMessageBox.question(self, "Sortie pending",
                    "A sortie is still pending. Closing SQE restores DCS's MissionScripting.lua, so DCS can no longer write the results "
                    "for this mission.\n\nClose anyway?") != QMessageBox.Yes:
            ev.ignore(); return
        ev.accept()

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

    def skip_turn(self):
        sess = self.session
        msg = "Skip today? Every package on the tasking order (including the ones you could fly) is resolved by the war simulation and the date advances."
        if sess.state.pending:
            msg += "\n\nThe sortie you built and have not finished will be discarded."
        if QMessageBox.question(self, "Skip Turn", msg) != QMessageBox.Yes:
            return
        out = sess.skip_day(); self.refresh_all()
        lines = [f"{'+' if r['success'] else '-'} {r['objective']}" for r in out["results"]]
        end = {"VICTORY": "\n\nVICTORY. The enemy has been broken.", "DEFEAT": "\n\nDEFEAT. The coalition position has collapsed."}.get(out["status"], "")
        QMessageBox.information(self, "Day resolved", "\n".join(lines) + end)

    def wait_for_results(self):
        dlg = WaitingDialog(self.session, self); r = dlg.exec()
        if r == QDialog.Accepted and dlg.data is not None:
            out = self.session.apply(dlg.data); self.refresh_all(); DebriefDialog(out, self.session.state, self).exec(); self.refresh_all()
            self.stack.setCurrentIndex(1); self.nav_missions.setChecked(True)
        elif r == 2:
            self.session.abort(); self.refresh_all()
        else:
            self.refresh_all()

    # ---- refresh ----------------------------------------------------------------------------------------------------------
    def refresh_all(self):
        st = self.session.state
        if not st:
            self.h_title.setText("No campaign loaded"); return
        for p in (self.p_over, self.p_forces, self.p_pilot, self.p_log):
            p.refresh(st)
        self.p_miss.refresh(self.session)
        n, name, _ = narrative.phase(st)
        self.h_title.setText(st.name)
        for pill, txt in zip(self.pills, (st.campaign_date().strftime("%d %b %Y").upper(), f"Day {st.day}", LEVELS[st.level].name, f"Phase {n}", st.player.aircraft)):
            pill.setText(txt)
        self.banner.setText({"ACTIVE": "Sortie pending" if st.pending else "", "VICTORY": "VICTORY", "DEFEAT": "DEFEAT"}[st.status])
        self.banner.setVisible(bool(self.banner.text()))
        self.setWindowTitle(f"{APP_NAME} - {st.name}")


def run():
    app = QApplication(sys.argv)
    app.setStyleSheet(theme.QSS); app.setApplicationName(APP_NAME)
    try:                                                       # own taskbar identity + icon (otherwise Windows groups SQE under python.exe)
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("MarkuzJuniuz.SQE")
    except Exception:
        pass
    try:
        from PySide6.QtGui import QIcon
        app.setWindowIcon(QIcon(str(Path(__file__).resolve().parent.parent / "data" / "sqe.png")))
    except Exception:
        pass
    f = app.font(); f.setPointSize(10); app.setFont(f)
    settings = AppSettings.load(); sess = Session(settings)
    w = MainWindow(sess); w.show()
    from .. import settings as S
    def scripting_on():
        if settings.auto_patch_scripting and settings.dcs_install:
            ok, msg = S.patch_mission_scripting(settings.dcs_install)
            if not ok:
                QMessageBox.warning(w, "MissionScripting.lua", msg + "\n\nWithout it DCS cannot write the sortie results for debriefing.")
        elif settings.auto_patch_scripting and not settings.dcs_install:
            QMessageBox.information(w, "MissionScripting.lua", "No DCS install folder is set (Settings), so MissionScripting.lua can't be patched automatically. "
                                    "Debriefing needs it.")
    app.aboutToQuit.connect(lambda: S.restore_mission_scripting(settings.dcs_install) if settings.dcs_install and settings.auto_patch_scripting else None)
    def start():
        if not settings.patch_asked:
            r = QMessageBox.question(w, "Debrief results", "To read mission results, SQE can temporarily edit DCS's MissionScripting.lua "
                                     "(enable io/lfs) while SQE is open. A backup is made and the file is restored when SQE closes.\n\n"
                                     "Allow this? You can change it later in Settings.", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            settings.auto_patch_scripting = (r == QMessageBox.Yes); settings.patch_asked = True; settings.save()
        scripting_on()
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
