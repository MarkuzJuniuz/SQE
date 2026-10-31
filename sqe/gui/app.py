from __future__ import annotations
import html
import sys
import traceback
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QSize, QUrl
from PySide6.QtGui import QAction, QColor, QDesktopServices, QFont
from PySide6.QtWidgets import (QApplication, QButtonGroup, QComboBox, QDialog, QFileDialog, QFrame, QGridLayout, QHBoxLayout,
                               QHeaderView, QLabel, QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QProgressBar,
                               QPushButton, QCheckBox, QScrollArea, QStackedWidget, QTableWidget, QTableWidgetItem, QTabWidget, QTextBrowser,
                               QSizePolicy, QVBoxLayout, QWidget)

from .. import APP_NAME, CAMPAIGN_EXT, __version__, narrative, overview_detail, posture, story
from ..aircraft import AIRCRAFT
from ..briefing import threat_lines
from ..timeofday import is_night
from ..difficulty import LEVELS
from ..engine import Session
from ..packages import PackageBuilder, folded_n_def
from ..settings import AppSettings
from . import theme
from .dialogs import DayResolvedDialog, DebriefDialog, NewCampaignDialog, SettingsDialog, WaitingDialog
from .widgets import MapView, SideCard, StatCard, card
from . import overview_view as V

RELEASES_URL = "https://github.com/MarkuzJuniuz/SQE/releases/latest"


def _game_note(text: str) -> str:
    """v0.41.133 (XO 2026-10-24): game-mechanics text in an in-universe popup: a small grey "SQE NOTE" label, then the text in grey italics, in parentheses."""
    return f'<span style="color:#8b97a8;"><small>SQE NOTE</small><br><i>({text})</i></span>'


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
        c = card(); left.addWidget(c, 1)
        hr = QHBoxLayout(); c.layout().addLayout(hr)
        h = QLabel("SITUATION"); h.setObjectName("head"); hr.addWidget(h); hr.addStretch(1)
        self.sit_btn = QPushButton("Hide"); self.sit_btn.setFlat(True); self.sit_btn.setCursor(Qt.PointingHandCursor); hr.addWidget(self.sit_btn)
        self.sit_btn.clicked.connect(self._toggle_situation)
        self.op = QLabel(narrative.TITLE); self.op.setObjectName("title"); c.layout().addWidget(self.op)
        self.phase = QLabel(); self.phase.setObjectName("h2"); self.phase.setStyleSheet(f"color:{theme.AMBER};"); self.phase.setWordWrap(True)
        c.layout().addWidget(self.phase)
        self.txt = QTextBrowser(); self.txt.setFrameShape(QFrame.NoFrame); self.txt.setStyleSheet("background:transparent;border:none;")   # v0.41.149: Background and Intent, scrollable, collapsible
        c.layout().addWidget(self.txt, 1)
        self.now = QLabel(); self.now.setWordWrap(True); self.now.setStyleSheet("font-size:14px;"); c.layout().addWidget(self.now)              # the Now line stays pinned at the bottom, open or closed
        self._sit_open = True; self._st = None; self.get_settings = lambda: None; self.get_session = lambda: None; self._left = left; self._sit_card = c
        gc = card(); left.addWidget(gc, 1)                                 # v0.41.149: the detail tabs (they replaced the one long sector list)
        self.dtabs = QTabWidget(); gc.layout().addWidget(self.dtabs)
        self.dviews = {}
        for key, title in (("ground", "Ground"), ("supply", "Supply"), ("ad", "Air defence"), ("air", "Air Operations"), ("edge", "Tactical Edge")):
            v = QTextBrowser(); v.setFrameShape(QFrame.NoFrame); v.setStyleSheet("background:transparent;border:none;"); self.dviews[key] = v
            if key == "ground":                                              # v0.41.207: the base notes sit in an expandable section above the sector table
                w = QWidget(); wl = QVBoxLayout(w); wl.setContentsMargins(0, 0, 0, 0); wl.setSpacing(4)
                self.notes_btn = QPushButton("Notes  \u25b8"); self.notes_btn.setFlat(True); self.notes_btn.setCursor(Qt.PointingHandCursor)
                self.notes_btn.setStyleSheet("text-align:left;padding:4px 6px;")
                self.notes_view = QTextBrowser(); self.notes_view.setFrameShape(QFrame.NoFrame); self.notes_view.setStyleSheet("background:transparent;border:none;")
                self.notes_view.setMaximumHeight(230); self.notes_view.setVisible(False)
                self.notes_btn.clicked.connect(self._toggle_notes)
                wl.addWidget(self.notes_btn); wl.addWidget(self.notes_view); wl.addWidget(v, 1)
                self.dtabs.addTab(w, title)
            else:
                self.dtabs.addTab(v, title)
        right = QVBoxLayout(); root.addLayout(right, 6)
        g = QGridLayout(); g.setSpacing(12); right.addLayout(g)
        self.cards = {"fr": StatCard("The front", theme.AMBER), "od": StatCard("Ground odds", theme.BLUE)}
        self.side = {"blue": SideCard("Coalition"), "red": SideCard("Russia")}
        g.addWidget(self.cards["fr"], 0, 0); g.addWidget(self.cards["od"], 0, 1); g.addWidget(self.side["blue"], 1, 0); g.addWidget(self.side["red"], 1, 1)
        self.today = StatCard("Today's tasking", theme.AMBER); right.addWidget(self.today)               # v0.41.152: what the day holds for you
        self.warn_card = card(); right.addWidget(self.warn_card)                # v0.41.148: warnings (a base about to fall, the counter-force), hidden when there are none
        wh = QLabel("WARNINGS"); wh.setObjectName("head"); self.warn_card.layout().addWidget(wh)
        self.warn = QLabel(); self.warn.setWordWrap(True); self.warn.setStyleSheet(f"color:{theme.AMBER};"); self.warn_card.layout().addWidget(self.warn)
        mc = card(); right.addWidget(mc, 1)
        top = QHBoxLayout(); mc.layout().addLayout(top)
        t = QLabel("THEATRE"); t.setObjectName("head"); top.addWidget(t); top.addStretch(1)
        self.rings = QCheckBox("SAM rings (red / blue)"); self.rings.setChecked(True); top.addWidget(self.rings)
        self.map = MapView(); mc.layout().addWidget(self.map, 1)
        self.rings.toggled.connect(self.map.set_rings)

    def _set_situation(self, on: bool):
        self._sit_open = on
        self.txt.setVisible(on); self.sit_btn.setText("Hide" if on else "Show")
        self._sit_card.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred if on else QSizePolicy.Maximum)
        self._left.setStretch(0, 3 if on else 0); self._left.setStretch(1, 2 if on else 1)          # a closed Situation panel gives the room to the detail tabs

    def _toggle_situation(self):
        self._set_situation(not self._sit_open)
        stg = self.get_settings()
        if stg is not None:
            stg.situation_open = self._sit_open
            try:
                stg.save()
            except OSError:
                pass

    @staticmethod
    def _table(headers, rows, note: str = "") -> str:
        th = "".join(f"<th align='left' style='color:#8fa3b8;padding-right:14px'>{html.escape(h)}</th>" for h in headers)
        tr = "".join("<tr>" + "".join(f"<td style='padding-right:14px'>{html.escape(str(c))}</td>" for c in r) + "</tr>" for r in rows)
        return (f"<p style='color:#b9c6d6'>{html.escape(note)}</p>" if note else "") + f"<table cellspacing='2'><tr>{th}</tr>{tr}</table>"

    def _toggle_notes(self):
        on = not self.notes_view.isVisible()
        if on:
            d = self.notes_view.document(); d.setTextWidth(max(300, self.notes_view.width() - 20))
            self.notes_view.setFixedHeight(min(230, int(d.size().height()) + 14))
        self.notes_view.setVisible(on); self.notes_btn.setText("Notes  \u25be" if on else "Notes  \u25b8")

    def _fill_details(self, st):
        import re
        from .. import ground, tempo, blue_barcap as _bb, bombers as _bomb
        od, en, e = overview_detail, story.enemy(st), V.e
        fe, fb = posture.supply_pct(st, "red"), posture.supply_pct(st, "blue")
        ae, ab = round(100 * posture.iads_pct(st, "red")), round(100 * posture.iads_pct(st, "blue"))
        # ---- Ground: the base notes (expandable), then the sector table with strength bars
        notes, rows, hist = od.ground_notes(st), od.ground_rows(st), od.history(st)
        base_rows, plain = [], []
        for n in notes:
            m = re.match(r"^(.+?): (next objective|held by the enemy|taken|LOST)$", n)
            (base_rows.append((m.group(1), V.title(m.group(2)))) if m else plain.append(n))
        self.notes_view.setHtml(("<p>" + "<br>".join(e(x) for x in plain) + "</p>" if plain else "") + (V.table(("Base", "Status"), base_rows) if base_rows else "<p>No ground war.</p>"))
        im = V.Images()
        raw = [(ground.red_strength(st, i) / posture.POINTS_PER_BATTALION, ground.blue_strength(st, i) / posture.POINTS_PER_BATTALION) for i in range(len(rows))] if rows else []
        trs = []
        for (name, r, b, tag), (rf, bf) in zip(rows, raw):
            trs.append([name, im.bar(r, rf / 10.0, V.pct_band(rf * 10)), im.bar(b, bf / 10.0, V.pct_band(bf * 10)), V.title(tag)])
        body = V.table(("Sector", en, "Coalition", "Status"), trs) if trs else ""
        body += V.section("Front History", "<br>".join(e(x) for x in hist)) if hist else "<p style='margin-top:14px;color:#8fa3b8'>The front has not moved yet.</p>"
        im.apply(self.dviews["ground"], body)
        # ---- Supply
        top = V.table(("Side", "Supply"), [("Coalition", ("bg", f"{fb}%", V.supply_band(fb))), (en, ("bg", f"{fe}%", V.supply_band(fe)))])
        sites = V.table(("Side", "Site", "Health", "State"), [(a, b, ("bg", f"{c}%", V.pct_band(c)), V.first_cap(d)) for a, b, c, d in od.supply_rows(st)])
        self.dviews["supply"].setHtml(top + V.section("Sites", sites)
                                      + "<p style='margin-top:14px;color:#8fa3b8'>A site mends in about 6 days at full supply (longer when supply is low), and not on a night after it was struck.</p>")
        # ---- Air defence: the transit section only when a battery is on its way
        orders = od.asks_rows(st)
        top = V.table(("Side", "Air Defense"), [("Coalition", ("bg", f"{ab}%", V.pct_band(ab))), (en, ("bg", f"{ae}%", V.pct_band(ae)))])
        transit = V.section("SAM Batteries in Transit", V.table(("Side", "Battery"), [(a, V.first_cap(b)) for a, b in orders])) if orders else ""
        sites = V.table(("Side", "Site", "Type", "Health", "State"), [(a, b, c, ("bg", f"{d}%", V.pct_band(d)), V.first_cap(x)) for a, b, c, d, x in od.air_defence_rows(st)])
        self.dviews["ad"].setHtml(top + transit + V.section("Sites", sites))
        # ---- Air Operations: BARCAP cover and the tanker / AWACS guards, under their own headings
        lines = _bb.status_lines(st)
        cover = [tuple((ln.strip().split(": ", 1) + [""])[:2]) for ln in lines if ln.startswith("   ")]
        head = next((ln for ln in lines if ln.startswith("BARCAP")), "")
        guard = next((ln.split(": ", 1)[1] for ln in lines if ln.startswith("Tanker / AWACS")), "")
        guard = guard.replace(" sorties planned", " guard sorties planned")
        extra = _bomb.status_lines(st)
        air = V.section("BARCAP Cover", "<p style='color:#8fa3b8'>Share of today's 24 hours with a pair up.</p>" + (V.table(("Area", "Cover"), cover) if cover else "")) if head else ""
        air += V.section("Tanker/AWACS", f"<p>{e(V.first_cap(guard))}</p>") if guard else ""
        air += V.section("Red Air", "<p>" + "<br>".join(e(x) for x in extra) + "</p>") if extra else ""
        self.dviews["air"].setHtml(air or "<p style='color:#8fa3b8'>Nothing is planned yet.</p>")
        # ---- Tactical Edge: a bar per job kind, full at the +40% cap
        im2 = V.Images()
        names = {"CAS": "Close Air Support", "STRIKE": "Strike", "DEAD": "SEAD/DEAD", "AIR": "Air Cover and Counter-Air"}
        trs = []
        for k in tempo.KINDS:
            v = tempo.get(st, k) * 100
            trs.append([names[k], im2.bar(f"{v:+.0f}%", v / (tempo.TEMPO_CAP * 100), "edge"), "At the cap" if abs(v) >= tempo.TEMPO_CAP * 100 - 0.5 else ""])
        im2.apply(self.dviews["edge"], "<p style='color:#b9c6d6'>What your flown sorties do to the odds of the same kind of job done in the background: 0 to +40 points, fading 3% a night. "
                  "A full bar is the +40% cap.</p><p style='margin:0'>&nbsp;</p>" + V.table(("Job", "Edge", ""), trs))

    def refresh(self, st):
        from .. import posture
        n, name, text = narrative.phase(st)
        self.phase.setText(f"{name.upper()}")                                   # v0.41.148: the posture label (it replaced the three phases)
        self._st = st
        sit = overview_detail.situation(st)
        self.now.setText(f"<b>Now:</b> {html.escape(sit['now'])}")
        self.txt.setHtml("".join(f"<p style='color:#b9c6d6;line-height:150%'>{html.escape(p)}</p>" for p in sit["background"]) +
                         (f"<hr><p style='line-height:150%'><b>Intent.</b> {html.escape(sit['intent'])}</p>" if sit["intent"] else ""))
        stg = self.get_settings()
        self._set_situation(True if stg is None else bool(getattr(stg, "situation_open", True)))
        if posture._active(st):
            k, tot = posture.stage(st)
            nxt = posture.objective(st)
            o = posture.front_odds(st)
            fe, fb = posture.supply_pct(st, "red"), posture.supply_pct(st, "blue")
            self.cards["fr"].set(f"Stage {k} of {tot}" if nxt is not None else "All taken", ("Next: " + nxt["name"] + "\n" if nxt is not None else "") +
                                 ", ".join(f"{nm} ({'taken' if s_ == 'ours' else 'next' if s_ == 'next' else 'enemy'})" for nm, s_ in posture.bases_status(st)))
            if st.status != "ACTIVE":
                self.cards["od"].set(posture.posture(st)[0], "The war is over", theme.DIM)
            else:
                self.cards["od"].set(o["word"].capitalize() if o else "No contact", posture.odds_line(st), V.odds_color(o["word"]) if o else theme.DIM)
            fb_, fe_ = fb, fe
            ab, ae = round(100 * posture.iads_pct(st, "blue")), round(100 * posture.iads_pct(st, "red"))
            en = story.enemy(st)
            self.side["red"].h.setText(en.upper())
            tb, te = posture.transit_text(st, "blue"), posture.transit_text(st, "red")
            self.side["blue"].set(f"{fb_}%", V.COLORS[V.supply_band(fb_)], f"{ab}%", V.COLORS[V.pct_band(ab)], ("Coalition: " + tb) if tb else "")
            self.side["red"].set(f"{fe_}%", V.COLORS[V.supply_band(fe_)], f"{ae}%", V.COLORS[V.pct_band(ae)], (en + ": " + te) if te else "")
        else:
            for kk in ("fr", "od"):
                self.cards[kk].set("-", "")
            for sd in self.side.values():
                sd.set("-", theme.DIM, "-", theme.DIM)
        sess = self.get_session()
        if sess is not None and sess.state is st:
            self.today.set(*overview_detail.tasking(sess))
        ws = posture.fall_warnings(st)
        self.warn.setText("\n".join(ws)); self.warn_card.setVisible(bool(ws))
        self._fill_details(st)
        self.map.set_state(st)


class MissionsPage(QWidget):
    def __init__(self, win):
        super().__init__(); self.win = win; self.pkgs = []; self.members = {}
        root = QHBoxLayout(self); root.setSpacing(16)
        left = QVBoxLayout(); root.addLayout(left, 4)
        self.day = QLabel(); self.day.setObjectName("h2"); left.addWidget(self.day)
        frow = QHBoxLayout(); fl = QLabel("Show"); fl.setObjectName("small"); frow.addWidget(fl)
        self.flt = QComboBox(); self.flt.addItem("My squadron", "squadron"); self.flt.addItem("All packages", "all")
        self.flt.setToolTip("My squadron: only packages with a flight from your squadron.  All: every package of the day, for looking only: you can fly only your own squadron's flights.")
        frow.addWidget(self.flt, 1); left.addLayout(frow)
        self.flt.currentIndexChanged.connect(self._filter_changed)
        self.lst = QListWidget(); left.addWidget(self.lst, 1); self.lst.currentRowChanged.connect(self._show)
        right = QVBoxLayout(); root.addLayout(right, 6)
        self.c = card(); right.addWidget(self.c, 1)
        L = self.c.layout()
        # everything that depends on the selected package lives in a scroll area, so a merged group of packages can be as tall as it needs
        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(True); self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet("QScrollArea { background: transparent; } QScrollArea > QWidget > QWidget { background: transparent; }")
        self.body = QWidget(); self.bl = QVBoxLayout(self.body); self.bl.setContentsMargins(0, 0, 6, 0); self.bl.setSpacing(8)
        self.scroll.setWidget(self.body); L.addWidget(self.scroll, 1)
        self.note = QLabel("Press FLY on your flight. Push time, TOT and the briefing are built when you do."); self.note.setObjectName("small"); L.addWidget(self.note)
        self.resume = QPushButton("Resume sortie in progress"); self.resume.setObjectName("fly"); self.resume.hide(); L.addWidget(self.resume)
        self.resume.clicked.connect(win.wait_for_results)
        self.skip = QPushButton("Skip Turn"); self.skip.setToolTip("Stand down for today: the whole tasking order is resolved by the war simulation and the date advances.")
        self.skip.clicked.connect(win.skip_turn); L.addWidget(self.skip, 0, Qt.AlignRight)

    def _filter_changed(self):
        if getattr(self, "sess", None) is None or getattr(self, "_loading", False):
            return
        self.sess.settings.list_filter = self.flt.currentData()
        try:
            self.sess.settings.save()
        except OSError:
            pass
        self.refresh(self.sess)

    def refresh(self, sess: Session):
        st = sess.state; self.sess = sess
        if st.status != "ACTIVE":                           # v0.41.150: the war is over: no tasking order, the ending instead
            self.lst.blockSignals(True); self.lst.clear(); self.lst.blockSignals(False)
            self.pkgs = []; self.members = {}
            self.day.setText(f"{st.campaign_date().strftime('%d %b %Y').upper()}  -  Day {st.day}  -  the war is over")
            self.resume.setVisible(False); self.skip.setEnabled(False); self.note.hide()
            self._clear_body()
            lab, text = posture.posture(st)
            self.bl.addWidget(self._label(lab, "title"))
            self.bl.addWidget(self._label(text, "dim"))
            self.bl.addWidget(self._label("There is nothing left to fly. Start a new campaign from the File menu.", "small"))
            self.bl.addStretch(1)
            return
        self.note.show()
        self._loading = True
        self.flt.setCurrentIndex(0 if sess.settings.list_filter != "all" else 1)
        self._loading = False
        mine_only = sess.settings.list_filter != "all"
        visible = [p for p in sess.packages() if (bool(sess.flyable(p)) or not mine_only)]
        groups = sess.collapse(visible)                     # a package that another one folds in is shown inside it, not as its own row
        self.pkgs = [h for h, _ in groups]; self.members = {h.number: m for h, m in groups}
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
        if self.pkgs and any(sess.flyable(p) for p in self.pkgs):
            self.lst.setCurrentRow(0)
        else:
            self._clear_body()
            self._idle_note(sess)

    def _idle_note(self, sess: Session):
        """Nothing to fly today: say so on the same pane, with the reasons, and a quiet pointer to Skip Turn."""
        if not sess.state or sess.state.status != "ACTIVE":
            return
        self.bl.addWidget(self._label(f"No flights for {sess.state.squadrons[sess.state.player.squadron_id].name} today.", "title"))
        for r in sess.idle_reasons():
            self.bl.addWidget(self._label(r, "dim"))
        self.bl.addWidget(self._label("Stand-down day for you. Skip Turn takes the day.", "small"))
        self.bl.addStretch(1)

    # ---- the right-hand panel ------------------------------------------------------------------------------------------------
    def _clear_body(self):
        while self.bl.count():
            it = self.bl.takeAt(0)
            w = it.widget()
            if w is not None:
                w.setParent(None); w.deleteLater()

    def _label(self, text, obj=None, color=None, wrap=True):
        l = QLabel(text)
        if obj:
            l.setObjectName(obj)
        l.setWordWrap(wrap)
        if color:
            l.setStyleSheet(f"color:{color};")
        return l

    def _fly_note(self, p) -> str:
        """What pressing FLY on this package's flight gives you: the start time and the other packages that fly with it."""
        ex = self.sess.merge_candidates(p)
        if not ex:
            return f"FLY here: the mission starts {p.start}, this package alone."
        parts = [f"#{x.number} ({'already airborne, started ' if x.start < p.start else 'starts '}{x.start})" for x in ex]
        return f"FLY here: the mission starts {p.start} and also flies " + ", ".join(parts) + "."

    def _flight_table(self, p):
        st = self.sess.state
        t = _tbl(["Flight", "Aircraft", "Qty", "Task", "Based at", ""])
        t.setSelectionMode(QTableWidget.NoSelection); t.setFocusPolicy(Qt.NoFocus)
        t.setStyleSheet("QTableWidget::item:selected, QTableWidget::item:hover, QTableWidget::item:focus { background: transparent; border: none; }")
        t.verticalHeader().setDefaultSectionSize(42)
        t.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff); t.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        hh = t.horizontalHeader()
        for c, m in enumerate((QHeaderView.ResizeToContents, QHeaderView.Stretch, QHeaderView.ResizeToContents, QHeaderView.Stretch,
                               QHeaderView.Stretch, QHeaderView.Fixed)):
            hh.setSectionResizeMode(c, m)
        hh.resizeSection(5, 100)
        t.setRowCount(len(p.flights)); t.setFixedHeight(64 + 42 * len(p.flights))
        opts = {f.id for f in self.sess.flyable(p)}
        sp = bool(p.extra.get("setpiece"))                  # v0.41.107: the carrier raid: every flight listed, those you cannot fly greyed out
        active = st.status == "ACTIVE"
        for i, f in enumerate(p.flights):
            spec = AIRCRAFT[f.aircraft]; yours = f.id in opts
            vals = (f.callsign, spec.display, f.count, f.task, st.bases[f.base_id].name.replace(" AB", ""))
            for j, v in enumerate(vals):
                t.setItem(i, j, _item(v, theme.GREEN if (yours and j == 0) else (theme.DIM if (f.tag or (sp and not yours)) else None), center=(j == 2)))
            if yours:
                b = QPushButton("FLY"); b.setObjectName("fly"); b.setEnabled(active); b.setFixedSize(84, 30)
                b.setToolTip(self._fly_note(p))
                b.clicked.connect(lambda _=0, n=p.number, fid=f.id: self.win.do_fly(n, fid))
                cont = QWidget(); cl = QHBoxLayout(cont); cl.setContentsMargins(4, 4, 4, 4); cl.addWidget(b, 0, Qt.AlignCenter)
                t.setCellWidget(i, 5, cont)
            else:
                t.setItem(i, 5, _item("AI Support" if f.tag else ("On alert (AI)" if sp else f"AI {spec.service}"), theme.DIM))
        return t, bool(opts)

    def _show(self, row):
        if row < 0 or row >= len(self.pkgs):
            return
        p = self.pkgs[row]; st = self.sess.state; mem = self.members.get(p.number, [])
        self._clear_body()
        night = is_night(st.campaign_date(), p.start)
        self.bl.addWidget(self._label(p.objective.description, "title"))
        from .. import weather as _wx
        _w = self.sess.wx_of(p)
        self.bl.addWidget(self._label(f"Mission start {p.start} local ({'night' if night else 'day'})   -   " + (_wx.describe(_w) if _w else "clear weather"), "h2", theme.AMBER))
        if p.extra.get("scrub"):
            self.bl.addWidget(self._label("SCRUBBED: " + p.extra["scrub"] + ". Nobody flies this package and the war simulation leaves its target alone.", None, theme.RED))
        for _n in p.extra.get("wx_notes", []):
            self.bl.addWidget(self._label("Weather loadout: " + _n, "small", theme.AMBER))
        sp = bool(p.extra.get("setpiece"))
        tbl, yours = self._flight_table(p)
        if sp:
            for i_, para in enumerate(narrative.setpiece_text(st, p, yours, AIRCRAFT[st.player.aircraft].display)):
                self.bl.addWidget(self._label(para, "dim" if i_ else None))
        else:
            self.bl.addWidget(self._label(narrative.intent_for(st, p), "dim"))
        if yours:
            self.bl.addWidget(self._label(self._fly_note(p), "small"))
        self.bl.addWidget(tbl)
        for x in mem:                                       # the packages that fly with this one: each with its own flights and FLY button
            line = QFrame(); line.setFrameShape(QFrame.HLine); line.setStyleSheet(f"color:{theme.DIM};"); self.bl.addWidget(line)
            xnight = is_night(st.campaign_date(), x.start)
            self.bl.addWidget(self._label(f"Also in this mission: #{x.number}  {x.objective.type.value.replace('_', ' ')}   {x.start}{' (night)' if xnight else ''}", "h2", theme.AMBER))
            self.bl.addWidget(self._label(x.objective.description, "title"))
            xt, xyours = self._flight_table(x)
            if xyours:
                self.bl.addWidget(self._label(self._fly_note(x), "small"))
            self.bl.addWidget(xt)
        sup = ("Support: " + ", ".join(f"{s.label} ({s.slot.title()})" for s in p.support) +
               ("  |  JTAC on the ground" if p.jtac else "") + ("  |  Joint Navy / Air Force package" if p.joint else ""))
        ex = self.sess.merge_candidates(p)
        if ex and yours:
            sup += "  |  Merged mission: also flies " + ", ".join(f"#{x.number}" for x in ex)
        self.bl.addWidget(self._label(sup, "dim"))
        if sp:
            self.bl.addStretch(1)
            return
        tx, ty = PackageBuilder(st).target_xy(p.objective)
        th = threat_lines(st, tx, ty)[:4]
        nd = folded_n_def(p, ex, self.sess.settings.merge_enemy_pct)
        self.bl.addWidget(self._label((f"Expect about {nd} hostile fighters at the target" + (f" (includes {', '.join('#%d' % x.number for x in ex)})" if ex else "") + ".  " if nd else "") +
                                      "Threats near target: " + ("; ".join(th) if th else "none known"), None, theme.AMBER))
        self.bl.addStretch(1)


class ForcesPage(QWidget):
    def __init__(self):
        super().__init__(); lay = QVBoxLayout(self)
        self.air_line = QLabel(); self.air_line.setObjectName("small"); self.air_line.setWordWrap(True); lay.addWidget(self.air_line)         # v0.41.152: aircraft counts, a detail line (jets no longer decide the war)
        self.tabs = QTabWidget(); lay.addWidget(self.tabs)
        self.sq = _tbl(["Squadron", "Aircraft", "Service", "Based at", "Serviceable", "Readiness"])
        self.ea = _tbl(["Aircraft", "Based at", "Serviceable", "Strength"])
        self.as_ = _tbl(["Enemy asset", "Type", "Depth", "Condition"])
        self.bs = _tbl(["Coalition base", "Type", "Patriot", "HAWK", "AAA"])
        self.gw = _tbl(["Sector", "Enemy force", "Friendly force", "Enemy forward garrison", "Friendly forward garrison"])
        self.sup = _tbl(["Support aircraft", "Type", "Based at", "Serviceable", "Cycle", "Cover today", "Strength"])
        for t, n in ((self.sq, "Coalition squadrons"), (self.sup, "Tankers and AWACS"), (self.bs, "Coalition bases"), (self.gw, "Ground war"), (self.ea, "Enemy air wings"), (self.as_, "Enemy assets")):
            self.tabs.addTab(t, n)

    @staticmethod
    def _bar(frac, color):
        b = QProgressBar(); b.setRange(0, 100); b.setValue(int(round(frac * 100))); b.setFormat("%p%")
        b.setStyleSheet(f"QProgressBar::chunk {{ background: {color}; border-radius:5px; }}"); return b

    def refresh(self, st):
        from .. import war as _war
        t = _war.totals(st); en = story.enemy(st)
        self.air_line.setText(f"Aircraft serviceable: Coalition {t['fa']} of {t['fz']}, {en} {t['ea']} of {t['ez']}.")
        self.tabs.setTabText(4, f"{en} air wings"); self.tabs.setTabText(5, f"{en} assets")
        self.gw.setHorizontalHeaderLabels(["Sector", f"{en} force", "Coalition force", f"{en} forward garrison", "Coalition forward garrison"])
        self.ea.setHorizontalHeaderLabels(["Aircraft", "Based at", "Serviceable", "Strength"]); self.as_.setHorizontalHeaderLabels([f"{en} asset", "Type", "Depth", "Condition"])
        sqs = list(st.squadrons.values()); self.sq.setRowCount(len(sqs))
        for i, s in enumerate(sqs):
            sp = AIRCRAFT[s.aircraft]
            for j, v in enumerate((s.name, sp.display, sp.service, st.bases[s.base_id].name, f"{s.available} / {s.authorized}")):
                self.sq.setItem(i, j, _item(v))
            self.sq.setCellWidget(i, 5, self._bar(s.readiness, theme.BLUE))
        rows_ = [(w, q) for w in st.enemy_air for q in w.sqns]                     # v0.41.208 (XO): laid out like the Coalition squadrons (no squadron names): one row per airframe, its base, serviceable and strength
        self.ea.setRowCount(len(rows_))
        for i, (w, q) in enumerate(rows_):
            for j, v in enumerate((q.aircraft.replace("_", "-"), st.assets[w.base_asset_id].name,
                                   f"{q.available} / {q.authorized}" + (f" (resting, {q.reserve})" if q.reserve else ""))):
                self.ea.setItem(i, j, _item(v))
            self.ea.setCellWidget(i, 3, self._bar(q.available / max(1, q.authorized), theme.RED))
        from .. import sams as _sams, support_assets as _sa
        bl = list(st.bases.values()); self.bs.setRowCount(len(bl))
        col = lambda h: theme.GREEN if h > 0.6 else theme.AMBER if h > 0.25 else theme.RED
        for i, b in enumerate(bl):
            self.bs.setItem(i, 0, _item(b.name)); self.bs.setItem(i, 1, _item("Carrier (escorted)" if b.kind.value == "CARRIER" else "Airfield"))
            if b.kind.value == "AIRFIELD":
                sites = _sams.blue_sites(st, b)                       # v0.41.100: one bar per site (an older save without sites shows its single defence figure on the Patriot)
                for j, k in enumerate(("pat", "hawk", "aaa")):
                    h = sites[k].health if sites else (b.defense if k == "pat" else None)
                    if h is None:
                        self.bs.setItem(i, 2 + j, _item("-", theme.DIM))
                    else:
                        self.bs.setCellWidget(i, 2 + j, self._bar(h, col(h)))
            else:
                self.bs.setItem(i, 2, _item("Cruiser + 2 escorts", theme.DIM))
                for j in (3, 4):
                    self.bs.setItem(i, j, _item("", theme.DIM))
        # tankers and AWACS (v0.41.100): the support assets, with the hours an aircraft of the type is on orbit today
        nice = {"bl_e3": "E-3A AWACS", "bl_e2": "E-2C AWACS (carrier)", "bl_kc135": "KC-135 tanker (boom)", "bl_kc135mprs": "KC-135 MPRS tanker (probe)",
                "bl_s3": "S-3B tanker (carrier)", "rd_a50": "A-50 AWACS (enemy, not flying yet)"}
        sa = _sa.ensure(st)
        fl = (getattr(st, "barcap", None) or {}).get("support_flights") or {}
        self.sup.setRowCount(len(sa))
        for i, (k, a) in enumerate(sorted(sa.items(), key=lambda kv: (kv[1]["side"] != "blue", kv[0]))):
            red = a["side"] != "blue"
            base = st.bases.get(a["base_id"]) or st.assets.get(a["base_id"])
            mins = 0; hi = 0
            for s0, e0 in sorted(fl.get(k, [])):                       # union of today's windows
                s0 = max(s0, hi); mins += max(0, e0 - s0); hi = max(hi, e0)
            cover = "-" if red else f"{mins / 60:.1f} h of 24"
            cyc = f"{a['sortie_min'] / 60:g} h on orbit, {a['turnaround_min'] / 60:g} h turnaround"
            dim = theme.DIM if red else None
            for j, v in enumerate((f"{a['label']}" + ("  (red)" if red else ""), nice.get(k, a["dcs_class"]), getattr(base, "name", a["base_id"]),
                                   f"{a['available']} / {a['authorized']}", cyc, cover)):
                self.sup.setItem(i, j, _item(v, dim))
            fr = a["available"] / max(1, a["authorized"])
            self.sup.setCellWidget(i, 6, self._bar(fr, theme.DIM if red else col(fr)))
        # the ground war (v0.41.102): each sector's two forces and the dug-in forward garrison each side holds there
        from .. import ground as _gr
        if _gr.active(st):
            n_ = _gr.n_zones(st.ground); self.gw.setRowCount(n_)
            for i in range(n_):
                zi = _gr.info(st, i)
                self.gw.setItem(i, 0, _item(zi["name"] + ("  (contested)" if zi["contested"] else "")))
                for j, (v, c) in enumerate(((zi["red"], theme.RED), (zi["blue"], theme.BLUE))):
                    self.gw.setCellWidget(i, 1 + j, self._bar(min(1.0, v / _gr.MAX_FORCE), c))
                for j, side in enumerate(("red", "blue")):
                    h = _gr.fwd_health(st, side, i)
                    held = (zi["red"] if side == "red" else zi["blue"]) >= _gr.MIN_FORCE
                    if (st.assets if side == "red" else st.blue_assets).get(_gr.fwd_id(side, i)) is None or not held:
                        self.gw.setItem(i, 3 + j, _item("-", theme.DIM))
                    else:
                        self.gw.setCellWidget(i, 3 + j, self._bar(h, col(h)))
        else:
            self.gw.setRowCount(0)
        al = sorted(st.assets.values(), key=lambda a: (a.kind.value, a.name)); self.as_.setRowCount(len(al))
        for i, a in enumerate(al):
            kind = "Garrison" if a.variant == "GARRISON" else (f"SAM {a.variant}" if a.kind.value == "SAM" else a.kind.value.title())
            if a.suppressed:
                kind += "  (radars suppressed)"
            from .. import theatres as _th; _tl = _th.active()["tier_labels"]; tier = _tl[min(len(_tl) - 1, max(1, a.tier))]
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


WIN_MAX = (1700, 960)         # v0.41.151 (XO 2026-10-27): the window opens at 90% of the usable screen, at most this big, centered (1080p: about 1700 x 936)
WIN_MIN = (1100, 700)
WIN_FRACTION = 0.90


def default_window_rect(ax: int, ay: int, aw: int, ah: int) -> tuple:
    """(x, y, w, h) for a usable screen area of aw x ah at (ax, ay): 90% of it, capped at WIN_MAX, never under WIN_MIN, centered."""
    w = max(WIN_MIN[0], min(WIN_MAX[0], int(aw * WIN_FRACTION)))
    h = max(WIN_MIN[1], min(WIN_MAX[1], int(ah * WIN_FRACTION)))
    return ax + (aw - w) // 2, ay + (ah - h) // 2, w, h


class MainWindow(QMainWindow):
    def __init__(self, session: Session):
        super().__init__(); self.session = session
        self.setWindowTitle(f"{APP_NAME}"); self.setMinimumSize(*WIN_MIN); self._place_window()
        root = QWidget(); root.setObjectName("root"); self.setCentralWidget(root)
        lay = QHBoxLayout(root); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(0)
        side = QFrame(); side.setObjectName("sidebar"); side.setFixedWidth(210); lay.addWidget(side)
        sl = QVBoxLayout(side); sl.setContentsMargins(14, 18, 14, 14); sl.setSpacing(4)
        lg = QLabel("SQE"); lg.setStyleSheet(f"font-size:30px;font-weight:800;color:{theme.BLUE};"); sl.addWidget(lg)
        sub = QLabel("Squadron Campaign Engine"); sub.setObjectName("small"); sl.addWidget(sub); sl.addSpacing(18)
        self.stack = QStackedWidget()
        self.p_over, self.p_miss, self.p_forces, self.p_pilot, self.p_log = OverviewPage(), MissionsPage(self), ForcesPage(), PilotPage(), LogPage()
        self.p_over.get_settings = lambda: self.session.settings
        self.p_over.get_session = lambda: self.session
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
        QApplication.instance().installEventFilter(self)                                    # v0.41.151: developer secret Ctrl+Space (see eventFilter)

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
        f.addSeparator(); act("S&ettings...", self.settings, "Ctrl+,"); act("Reset &window size and position", self.reset_window); f.addSeparator(); act("E&xit", self.close, "Alt+F4")
        h = mb.addMenu("&Help")
        a = QAction("&About SQE...", self); a.triggered.connect(self.about); h.addAction(a)
        a = QAction("&Latest release (GitHub)", self); a.triggered.connect(lambda: QDesktopServices.openUrl(QUrl(RELEASES_URL))); h.addAction(a)

    def about(self):
        from .. import EULA_LINE
        QMessageBox.about(self, f"About {APP_NAME}", (
            f"<h3>{APP_NAME} (SQE) v{__version__}</h3>"
            "<p>A dynamic campaign and sortie generator for DCS World. It builds light missions with few units.</p>"
            f"<p>{html.escape(EULA_LINE)}</p>"
            "<p><b>Credits</b><br>"
            "pydcs (the Retribution fork) builds the mission files.<br>"
            "PySide6 / Qt for the interface; Pillow for the kneeboard images.<br>"
            "Ground height data: SRTM (NASA / USGS Shuttle Radar Topography Mission) via the AWS open terrain tiles, public domain.</p>"))


    def _recent(self):
        self.recent.clear()
        for p in self.session.list_campaigns()[:8]:
            a = QAction(p.stem, self); a.triggered.connect(lambda _=0, q=p: self._open(q)); self.recent.addAction(a)
        if self.recent.isEmpty():
            self.recent.addAction(QAction("(none found)", self)).setEnabled(False)

    # ---- campaign ops -------------------------------------------------------------------------------------
    def new_campaign(self, prefill: dict | None = None):
        if self.session.settings.problems():
            self.settings()
            if self.session.settings.problems():
                return
        dlg = NewCampaignDialog(self, getattr(self.session.settings, "weather_mode", "clear"), getattr(self.session.settings, "ai_skill_red", "level"), getattr(self.session.settings, "ai_skill_blue", "level"), bool(getattr(self.session.settings, "pilot_influence", True)), prefill=prefill, edge_decay=bool(getattr(self.session.settings, "tempo_decay", False)))
        if dlg.exec() == QDialog.Accepted:
            try:
                v = dlg.values()
                self.session.settings.weather_mode = v.get("weather_mode", self.session.settings.weather_mode)
                self.session.settings.pilot_influence = bool(v.get("pilot_influence", True)); self.session.settings.tempo_decay = bool(v.get("tempo_decay", False))
                self.session.settings.ai_skill_red = v.get("ai_skill_red", self.session.settings.ai_skill_red); self.session.settings.ai_skill_blue = v.get("ai_skill_blue", self.session.settings.ai_skill_blue)
                try:
                    self.session.settings.save()
                except OSError:
                    pass
                self.session.new(v['name'], v['aircraft'], v['level'], start_date=v['start_date'], night_ops=v['night_ops'], squadron=v.get('squadron'), theatre=v.get('theatre', 'caucasus')); self.refresh_all()
            except Exception:
                QMessageBox.critical(self, "Could not create campaign", traceback.format_exc())

    def open_campaign(self):
        f, _ = QFileDialog.getOpenFileName(self, "Open campaign", str(self.session.campaigns_dir()), f"SQE campaign (*{CAMPAIGN_EXT})")
        if f:
            self._open(f)

    def _open(self, path):
        from ..state import SaveIncompatible
        try:
            self.session.open(path); self.refresh_all()
        except SaveIncompatible as e:
            self._incompatible(path, e)
        except Exception:
            QMessageBox.critical(self, "Could not open campaign", traceback.format_exc())

    def _incompatible(self, path, e):
        """v0.41.162: a save this build cannot open: say why, say which version could, and offer a backup + a new campaign (never a traceback)."""
        from .. import __version__
        i = e.info(); nm = i["name"] or Path(path).stem
        who = f"SQE v{i['saved_by']}" if i.get("saved_by") else "an earlier SQE"
        day = f" (day {i['day']})" if i.get("day") else ""
        box = QMessageBox(self); box.setWindowTitle("Can't open this campaign"); box.setIcon(QMessageBox.Information)
        if e.kind == "newer":
            box.setText(f"{nm} was saved by {i['saved_by'] and 'SQE v' + i['saved_by'] or 'a newer SQE'}, which is newer than this version (v{__version__}). Update SQE to open it. "
                        "This file has not been changed.")
            box.addButton("OK", QMessageBox.AcceptRole); box.exec(); return
        if e.kind == "damaged":
            box.setText(f"{nm} couldn't be opened (the file may be damaged or from a different version).")
        else:
            box.setText(f"{nm}{day} was saved by {who}. This version, v{__version__}, can't open it because the campaign format has changed.\n\n"
                        f"To keep playing that campaign, run {who}. This file has not been changed.")
        go = box.addButton("Back up and start a new campaign", QMessageBox.AcceptRole)
        box.addButton("Leave it alone", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is not go:
            return
        try:
            dst = self.session.backup_incompatible(path)
        except OSError as ex:
            QMessageBox.warning(self, "Backup failed", f"The backup could not be made ({ex}). Nothing was changed."); return
        QMessageBox.information(self, "Backed up", f"A copy was saved as {dst}.")
        self.new_campaign(prefill={"name": i["name"], "aircraft": i.get("aircraft"), "level": i.get("level")})

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

    def _place_window(self, reset: bool = False):
        """Open where it was last closed (Qt keeps it on a screen that still exists), or at the default size, centered."""
        from PySide6.QtCore import QByteArray
        stg = self.session.settings
        if not reset and getattr(stg, "window_geometry", ""):
            try:
                if self.restoreGeometry(QByteArray.fromBase64(stg.window_geometry.encode())):
                    return
            except Exception:
                pass
        scr = QApplication.screenAt(self.pos()) or QApplication.primaryScreen()
        a = scr.availableGeometry()
        x, y, w, h = default_window_rect(a.x(), a.y(), a.width(), a.height())
        self.setGeometry(x, y, w, h)

    def reset_window(self):
        self.session.settings.window_geometry = ""
        if self.isMaximized() or self.isFullScreen():
            self.showNormal()
        self._place_window(reset=True)
        try:
            self.session.settings.save()
        except OSError:
            pass

    def closeEvent(self, ev):
        st = self.session.state
        if st is not None and st.pending and self.session.settings.auto_patch_scripting and \
                QMessageBox.question(self, "Sortie pending",
                    "A sortie is still pending. Closing SQE restores DCS's MissionScripting.lua, so DCS can no longer write the results "
                    "for this mission.\n\nClose anyway?") != QMessageBox.Yes:
            ev.ignore(); return
        try:
            self.session.settings.window_geometry = bytes(self.saveGeometry().toBase64()).decode()
            self.session.settings.save()
        except Exception:
            pass
        ev.accept()

    def settings(self):
        if SettingsDialog(self.session.settings, self).exec() == QDialog.Accepted:
            if getattr(self.session, "state", None) is not None:
                self.session.refresh_weather(); self.session.save()      # the weather setting changes which packages fly
            self.refresh_all()

    # ---- flying --------------------------------------------------------------------------------------------------------
    def do_fly(self, number, flight_id):
        sess = self.session
        if sess.state.pending and QMessageBox.question(self, "Sortie pending",
                "A sortie is already built and waiting for results. Discard it and build a new one?") != QMessageBox.Yes:
            return
        if sess.state.pending:
            sess.abort()                                    # v0.41.149: discarding gives back what the sortie used, a scramble included (so it is offered again)
        if sess.settings.problems():
            QMessageBox.warning(self, "Settings", "\n".join(sess.settings.problems())); self.settings(); return
        scramble = False
        try:
            ev = sess.emergency_for(number, flight_id)
        except Exception:
            ev = None
        if ev:
            scramble = self._emergency_popup(ev, number)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            res = sess.fly(number, flight_id, scramble=scramble)
        except Exception:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "Could not build the mission", traceback.format_exc()); return
        QApplication.restoreOverrideCursor()
        self.refresh_all(); self.wait_for_results()

    def _emergency_popup(self, ev, number) -> bool:
        """An emergency came up as you clicked Fly. Returns True when you take it."""
        epkg = ev["package"]
        box = QMessageBox(self); box.setIcon(QMessageBox.Warning); box.setWindowTitle(ev["title"])
        if ev["eligible"]:
            box.setText(f"<b>{ev['title']}</b><br>{ev['text']}")
            box.setTextFormat(Qt.RichText); box.setInformativeText(f"Your squadron can answer it: {epkg.objective.description}.<br><br>" + _game_note(
                                   f"If you scramble, the package you were tasked with (#{number}) is left to the other squadrons and is settled by the war "
                                   f"simulation (or postponed a day if there are not enough aircraft for both). If you stay with your tasking, the emergency "
                                   f"is settled without you" + (" or flown by AI inside your mission." if epkg.objective.type.value in ("CAS", "FLEET_DEFENSE") else ".")))
            go = box.addButton("Scramble", QMessageBox.AcceptRole); box.addButton("Stay with my tasking", QMessageBox.RejectRole)
            box.exec()
            return box.clickedButton() is go
        box.setText(f"<b>{ev['title']}</b><br>{ev['text']}")
        box.setTextFormat(Qt.RichText); box.setInformativeText(f"{self.session.dispatch_line(epkg)}<br><br>" + _game_note(
                               ("If it lies inside your mission area it is joined to your mission as AI; otherwise the war simulation settles it."
                                if epkg.objective.type.value in ("CAS", "FLEET_DEFENSE") else "The war simulation settles it.")
                               + " Your own tasking goes ahead as planned."))
        box.addButton("Understood", QMessageBox.AcceptRole); box.exec()
        return False

    def eventFilter(self, obj, ev):
        """Developer secret (XO 2026-10-27): Ctrl+Space skips the day, in AI-Test only (v0.41.154). Done here and not as a QShortcut because a list or text box that has the focus (the Missions
        list) uses Ctrl+Space itself and swallowed the shortcut; the filter sees the key first."""
        from PySide6.QtCore import QEvent
        if ev.type() in (QEvent.ShortcutOverride, QEvent.KeyPress) and ev.key() == Qt.Key_Space and ev.modifiers() == Qt.ControlModifier and self.isActiveWindow() and getattr(self.session, "ai_test", False):
            if ev.type() == QEvent.KeyPress:
                self._dev_skip_day()
            ev.accept()
            return True
        return super().eventFilter(obj, ev)

    def _dev_skip_day(self):
        """Developer secret (XO 2026-10-27): Ctrl+Space skips the day at once, no questions and no result box, to watch the Overview and its map move.
        Not while a sortie is built (it would be thrown away) and not once the war is over."""
        st = self.session.state
        if st is None or st.status != "ACTIVE" or st.pending:
            return
        self.session.skip_day(); self.refresh_all()
        self._ending_popup("ACTIVE")

    def _ending_popup(self, before: str):
        """v0.41.164 (XO 2026-10-27): once, the moment the war ends (the status went from ACTIVE to won / lost), a box with the ending's story line - the same
        text as the Overview. Not when a finished campaign is merely loaded."""
        st = self.session.state
        if st is None or before != "ACTIVE" or st.status == "ACTIVE":
            return
        lab, text = posture.posture(st)
        QMessageBox.information(self, ("VICTORY: " if st.status == "VICTORY" else "DEFEAT: ") + lab, text)

    def skip_turn(self):
        sess = self.session
        stand_down = not sess.state.pending and not any(sess.flyable(p) for p in sess.packages())
        if not stand_down:                                       # v0.41.93: a stand-down day has nothing to choose, so no "are you sure"
            msg = "Skip today? Every package on the tasking order (including the ones you could fly) is resolved by the war simulation and the date advances."
            if sess.state.pending:
                msg += "\n\nThe sortie you built and have not finished will be discarded."
            if QMessageBox.question(self, "Skip Turn", msg) != QMessageBox.Yes:
                return
        before, day0 = sess.state.status, sess.state.day
        out = sess.skip_day(); self.refresh_all()
        DayResolvedDialog(out["results"], day0, self).exec()
        self._ending_popup(before)                                # (the war's ending, if this day ended it, has its own box with the story)

    def wait_for_results(self):
        dlg = WaitingDialog(self.session, self); r = dlg.exec()
        if r == QDialog.Accepted and dlg.data is not None:
            before = self.session.state.status
            out = self.session.apply(dlg.data); self.refresh_all(); DebriefDialog(out, self.session.state, self).exec(); self.refresh_all()
            self._ending_popup(before)
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
        for pill, txt in zip(self.pills, (st.campaign_date().strftime("%d %b %Y").upper(), f"Day {st.day}", LEVELS[st.level].name, name, st.player.aircraft)):
            pill.setText(txt)
        self.banner.setText({"ACTIVE": "Sortie pending" if st.pending else "", "VICTORY": "VICTORY", "DEFEAT": "DEFEAT"}[st.status])
        self.banner.setVisible(bool(self.banner.text()))
        self.setWindowTitle(f"{APP_NAME} - {st.name}" + ("  [AI TEST: your flight is flown by the AI]" if getattr(self.session, "ai_test", False) else "") + ("  [FULL MAP: no restrictions]" if getattr(self.session, "full_map", False) else "")
                            + (f"  [LATE SEAD: +{self.session.late_sead_min} min, from the next planned day]" if getattr(self.session, "late_sead_min", 0) else ""))


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
    sess.ai_test = "--ai-test" in sys.argv[1:]                  # all-AI test: your flight is built as an AI flight, no player slot
    sess.full_map = "--full-map" in sys.argv[1:]                # stress test: nothing is left out of the mission (every site, garrison, column and planned patrol)
    if "--late-sead" in sys.argv[1:]:                           # hold test: SEAD-stage packages go in late, so the DEAD stage reaches its gate with the radars up
        from ..engine import LATE_SEAD_MIN
        sess.late_sead_min = LATE_SEAD_MIN
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
