from __future__ import annotations
import html
import json
import time
from pathlib import Path
from PySide6.QtCore import Qt, QSize, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QCheckBox, QRadioButton, QButtonGroup, QSpinBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QFrame, QHBoxLayout,
                               QGroupBox, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem,
                               QTextBrowser, QVBoxLayout, QHeaderView, QTabWidget, QWidget, QScrollArea, QAbstractItemView)
from .. import settings as S
from ..aircraft import AIRCRAFT, A10_VARIANTS, F14_VARIANTS
from ..difficulty import LEVELS
from ..timeofday import is_night
from . import theme
from .. import debrief as DB
from .widgets import StepSpin, card


def _browse(parent, line: QLineEdit, title: str):
    d = QFileDialog.getExistingDirectory(parent, title, line.text() or str(Path.home()))
    if d:
        line.setText(S.native(d))


EDGE_DECAY_TEXT = ("Your edge fades by 3% each night, back toward zero, when you do not keep flying that kind of job (nights with nothing for you to fly do not count). "
                   "Off: the edge you build is kept. Needs Tactical Edge on.")
TACTICAL_EDGE_TEXT = ("Your flying shapes the war. On: the higher-ups study your actual sorties, and what they learn is carried to every unit in the theatre: the "
                        "background strikes, SEAD and air cover of the same kind succeed more often (your Tactical Edge). Stay on the ground and red seizes the initiative: it "
                        "surges, the front can crack, and you can lose the war. Off: the war runs on its own, with no effect from your flying (no red surge, no Tactical Edge).")


class NewCampaignDialog(QDialog):
    def __init__(self, parent=None, weather_mode: str = "clear", skill_red: str = "level", skill_blue: str = "level", tactical_edge: bool = True, prefill: dict | None = None, edge_decay: bool = False):
        super().__init__(parent); self.setWindowTitle("New Campaign"); self.setMinimumWidth(520)
        lay = QVBoxLayout(self); lay.setSpacing(12)
        t = QLabel("New Campaign"); t.setObjectName("title"); lay.addWidget(t)
        form = QFormLayout(); form.setSpacing(10)
        self.name = QLineEdit("Iron Tide"); form.addRow("Campaign name", self.name)
        from .. import theatres as _th
        self.th = QComboBox()
        for tid, tname in _th.available().items():
            self.th.addItem(tname, tid)
        if self.th.count() > 1:                       # the picker only appears once there is more than one theatre pack
            form.addRow("Theatre", self.th)
        self.ac = QComboBox()
        for k, s in AIRCRAFT.items():
            if s.player_flyable:
                self.ac.addItem(f"{s.display}  ({s.service}, {'carrier' if s.service == 'Navy' else 'land-based'})", k)
        form.addRow("You fly", self.ac)
        self.sqd = QComboBox(); form.addRow("Your squadron", self.sqd)
        self.ac.currentIndexChanged.connect(self._squads); self.th.currentIndexChanged.connect(self._squads); self._squads()
        self.lvl = QComboBox()
        for n, d in LEVELS.items():
            self.lvl.addItem(d.name, n)
        self.lvl.setCurrentIndex(1)
        form.addRow("Difficulty", self.lvl)
        pf = prefill or {}                               # v0.41.162: from a save this build could not open: its name, aircraft and level
        if pf.get("name"):
            self.name.setText(str(pf["name"]))
        if pf.get("aircraft") and self.ac.findData(pf["aircraft"]) >= 0:
            self.ac.setCurrentIndex(self.ac.findData(pf["aircraft"]))
        if pf.get("level") and self.lvl.findData(int(pf["level"])) >= 0:
            self.lvl.setCurrentIndex(self.lvl.findData(int(pf["level"])))
        self.month = QComboBox()
        for i, mname in enumerate(("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"), 1):
            self.month.addItem(mname, i)
        self.month.setCurrentIndex(5)
        self.day = StepSpin(); self.day.setRange(1, 28); self.day.setValue(12)
        self.year_lbl = QLabel("2006")                   # S103a: the year is a fixed label from the theatre pack's `era` block (month and day stay free)
        row = QHBoxLayout(); row.addWidget(self.month, 1); row.addWidget(self.day); row.addWidget(self.year_lbl)
        form.addRow("Campaign starts", row)
        self.edge = QCheckBox("Tactical Edge: your sorties affect the war")
        self.edge.setChecked(bool(tactical_edge)); self.edge.setToolTip(TACTICAL_EDGE_TEXT)
        form.addRow("", self.edge)                      # the starting value for this campaign (S88 R3): Settings > Campaign changes it for the open campaign later
        self.edge_decay = QCheckBox("Enable Tactical Edge Decay")
        self.edge_decay.setChecked(bool(edge_decay)); self.edge_decay.setToolTip(EDGE_DECAY_TEXT); self.edge_decay.setEnabled(bool(tactical_edge))
        self.edge.toggled.connect(self.edge_decay.setEnabled); self.edge_decay.setStyleSheet("margin-left:22px;")      # a sub-option of Tactical Edge
        form.addRow("", self.edge_decay)
        from .. import weather as _wxn
        self.wx = QComboBox()
        for k, val in _wxn.MODES.items():
            self.wx.addItem(val, k)
        self.wx.setCurrentIndex(max(0, self.wx.findData(weather_mode)))
        form.addRow("Weather", self.wx)                # the same setting as Settings > Campaign > Weather: it can be changed there later
        from ..difficulty import SKILL_CHOICES as _SK
        self.skr, self.skb = QComboBox(), QComboBox()
        for cb_, cur_ in ((self.skr, skill_red), (self.skb, skill_blue)):
            for k, val in _SK.items():
                cb_.addItem(val, k)
            cb_.setCurrentIndex(max(0, cb_.findData(cur_)))
        form.addRow("AI Skill, Red", self.skr)          # the same two settings as Settings > Campaign > AI Skill: they can be changed there later
        form.addRow("AI Skill, Blue", self.skb)
        lay.addLayout(form)
        # S103a (XO 2026-11-18): Era Equipment, fixed when the campaign is created; the defaults are the theatre's `era` values (Caucasus 2006: A-10C, F-14B(U), Link 16 enabled).
        # The pickers list only the variants this build has (aircraft.A10_VARIANTS / F14_VARIANTS).
        eq = QGroupBox("Era Equipment"); ev = QVBoxLayout(eq); ev.setSpacing(8)
        ef = QFormLayout(); ef.setSpacing(8)
        self.a10 = QComboBox(); self.f14 = QComboBox(); self.l16 = QComboBox()
        for cb_, tbl_ in ((self.a10, A10_VARIANTS), (self.f14, F14_VARIANTS)):
            for k_, lab_ in tbl_.items():
                cb_.addItem(lab_, k_)
        self.l16.addItem("Enabled", True); self.l16.addItem("Disabled", False)
        ef.addRow("A-10", self.a10); ef.addRow("F-14", self.f14); ef.addRow("Link 16", self.l16)
        ev.addLayout(ef)
        eb = QHBoxLayout(); self.era_btn = QPushButton("Era Defaults"); self.era_btn.clicked.connect(self._era_defaults)
        eb.addWidget(self.era_btn); eb.addStretch(1); ev.addLayout(eb)
        eh = QLabel("Fixed when the campaign is created. Defaults follow the theatre's year."); eh.setObjectName("small"); eh.setWordWrap(True); ev.addWidget(eh)
        lay.addWidget(eq)
        self.th.currentIndexChanged.connect(self._era_defaults); self._era_defaults()
        self.blurb = QLabel(); self.blurb.setWordWrap(True); self.blurb.setObjectName("dim"); lay.addWidget(self.blurb)
        self.lvl.currentIndexChanged.connect(self._b); self._b()
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel); bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject); lay.addWidget(bb)

    def _b(self):
        self.blurb.setText(LEVELS[self.lvl.currentData()].blurb)

    def _era_defaults(self):
        """Set the year label and the three Era Equipment choices to the selected theatre's `era` values (a variant this build does not have leaves that picker on its first entry)."""
        from .. import theatres as _th
        try:
            e = _th.era(self.th.currentData() or "caucasus")
        except Exception:
            e = dict(_th.ERA_DEFAULT)
        self.year = int(e["year"]); self.year_lbl.setText(str(self.year))
        for cb_, key_ in ((self.a10, "a10_variant"), (self.f14, "f14_variant")):
            cb_.setCurrentIndex(max(0, cb_.findData(e[key_])))
        self.l16.setCurrentIndex(max(0, self.l16.findData(bool(e["link16"]))))

    def _squads(self):
        from ..scenario import squadron_options
        self.sqd.clear()
        for sid, label in squadron_options(self.ac.currentData(), self.th.currentData() or "caucasus"):
            self.sqd.addItem(label, sid)

    def values(self) -> dict:
        return {"name": self.name.text().strip() or "Campaign", "aircraft": self.ac.currentData(), "level": self.lvl.currentData(),
                "start_date": f"{self.year}-{self.month.currentData():02d}-{self.day.value():02d}", "tactical_edge": self.edge.isChecked(), "tactical_edge_decay": self.edge.isChecked() and self.edge_decay.isChecked(),
                "squadron": self.sqd.currentData(), "theatre": self.th.currentData() or "caucasus", "weather_mode": str(self.wx.currentData()),
                "ai_skill_red": str(self.skr.currentData() or "level"), "ai_skill_blue": str(self.skb.currentData() or "level"),
                "a10_variant": self.a10.currentData(), "f14_variant": self.f14.currentData(), "link16": bool(self.l16.currentData())}


class SettingsDialog(QDialog):
    """Four tabs: General (takeoff buffer, marshal slack, AI fuel, splash damage), Campaign (weather, Tactical Edge, AI skill),
    Mission Build (merging and limits, the hot-start, dormant-site, ILS, AWACS-radio and damage-call switches, then AI landings, ruins and carcasses) and DCS Integration (paths,
    the scripting patch, the ECM script). A new experimental feature gets its own "Experimental" tab (added last) while it is being tried out.
    Labels are in title case, hints stay sentences. Every setting keeps the key it always had; the two hot-runway keys are one radio group."""
    def __init__(self, settings: S.AppSettings, parent=None, state=None):
        super().__init__(parent); self.s = settings; self.state = state; self.setWindowTitle("Settings"); self.setMinimumWidth(720); self.setMinimumHeight(560); self.resize(780, 700)
        lay = QVBoxLayout(self); lay.setSpacing(10)
        t = QLabel("Settings"); t.setObjectName("title"); lay.addWidget(t)
        self.tabs = QTabWidget(); lay.addWidget(self.tabs, 1)

        def page(title):
            w = QWidget(); v = QVBoxLayout(w); v.setSpacing(10); v.setContentsMargins(14, 14, 14, 14)
            sa = QScrollArea(); sa.setWidgetResizable(True); sa.setFrameShape(QFrame.NoFrame); sa.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            w.setObjectName("tabpage"); sa.setObjectName("tabscroll")
            sa.setStyleSheet("QScrollArea#tabscroll, QScrollArea#tabscroll > QWidget > QWidget#tabpage { background: transparent; border: none; }")
            sa.viewport().setAutoFillBackground(False)
            sa.setWidget(w)                                                  # long hint texts keep their full height; the tab scrolls instead of squeezing them
            self.tabs.addTab(sa, title)
            return v

        def hint(v, text):
            h = QLabel(text); h.setObjectName("small"); h.setWordWrap(True); v.addWidget(h)

        def row(v, label, *widgets, width=130):
            r = QHBoxLayout(); lb = QLabel(label); lb.setMinimumWidth(width); r.addWidget(lb)
            for i, w_ in enumerate(widgets):
                r.addWidget(w_, 1 if (i == 0 and len(widgets) == 1 and isinstance(w_, (QLineEdit, QComboBox))) else 0)
            r.addStretch(1); v.addLayout(r)

        # ---- General: how a sortie runs for you ------------------------------------------------------------------------------
        v = page("General")
        self.tob = StepSpin(); self.tob.setRange(-600, 900); self.tob.setSuffix(" s"); self.tob.setValue(int(settings.takeoff_buffer_s))
        row(v, "Takeoff Buffer", self.tob)
        hint(v, "Time between mission start and the takeoff time on your kneeboard (you start on the runway or cat, engines running). "
                "Default 60 s. Negative means the plan expects you to be rolling before the clock starts, so you must make the time up in the air.")
        self.hold = StepSpin(); self.hold.setRange(-10, 30); self.hold.setSuffix(" min"); self.hold.setValue(int(settings.marshal_slack_min))
        row(v, "Marshal Slack", self.hold)
        hint(v, "Time between reaching the marshal point and the PUSH. Smaller = less waiting. Negative means you must beat the "
                "natural pace (afterburner time). AI flights adjust automatically.")
        self.fuel = QCheckBox("AI Fuel Management (Unlimited Until the Push, Real Fuel in the Fight, Unlimited Again From Egress)")
        self.fuel.setChecked(bool(settings.ai_unlimited_fuel)); v.addWidget(self.fuel)
        self.splash = QCheckBox("Splash Damage: Blast Damage Around Bomb and Missile Impacts (On by Default)")
        self.splash.setChecked(bool(getattr(settings, "splash_damage", True))); v.addWidget(self.splash)
        hint(v, "DCS often leaves a vehicle a few metres from a bomb untouched. On: ground units near an air-to-ground weapon's impact take a blast "
                "of their own, scaled to the warhead and weaker with distance. Kills it causes count for the shooter.")
        v.addStretch(1)

        # ---- Campaign: what the world does ----------------------------------------------------------------------------------------
        v = page("Campaign")
        from .. import weather as _wxm
        self.wxm = QComboBox()
        for k, val in _wxm.MODES.items():
            self.wxm.addItem(val, k)
        self.wxm.setCurrentIndex(max(0, self.wxm.findData(getattr(settings, "weather_mode", "clear"))))
        row(v, "Weather", self.wxm)
        hint(v, "Procedural follows the theatre's climate for the month and changes slowly from day to day (never clear to storm in an afternoon); each sortie "
                "sees the weather at its own start time. Laser and imaging weapons are swapped for GPS weapons when cloud or rain rules them out, and a package "
                "that cannot attack at all (or meets fog) is scrubbed (the war simulation leaves its target alone). Clear is what SQE always did.")
        # v0.41.165: Tactical Edge goes AFTER the whole Weather block (combo + its description), never between them
        # S88 R3 (XO 2026-11-18): the pair belongs to the OPEN campaign (`state.ground`), not to the app: greyed out when no campaign is open
        g_ = (getattr(state, "ground", None) or {}) if state is not None else {}
        self.edge_rows = bool(g_)
        self.edge = QCheckBox("Tactical Edge (Your Sorties Affect the War)"); self.edge.setChecked(bool(g_.get("tactical_edge", True)))
        row(v, "Tactical Edge", self.edge)
        hint(v, TACTICAL_EDGE_TEXT)
        self.edge_decay = QCheckBox("Enable Tactical Edge Decay"); self.edge_decay.setChecked(bool(g_.get("tactical_edge_decay", False)))
        row(v, "", self.edge_decay)
        hint(v, EDGE_DECAY_TEXT)
        self.edge.setEnabled(self.edge_rows); self.edge_decay.setEnabled(self.edge_rows and self.edge.isChecked())
        self.edge.toggled.connect(lambda on: self.edge_decay.setEnabled(self.edge_rows and on)); self.edge_decay.setStyleSheet("margin-left:22px;")
        if not self.edge_rows:
            hint(v, "Open a campaign to change this; it is saved with each campaign.")
        from ..difficulty import SKILL_CHOICES as _SK
        self.skr, self.skb = QComboBox(), QComboBox()
        for cb_, key_ in ((self.skr, "ai_skill_red"), (self.skb, "ai_skill_blue")):
            for k, val in _SK.items():
                cb_.addItem(val, k)
            cb_.setCurrentIndex(max(0, cb_.findData(getattr(settings, key_, "level"))))
        row(v, "AI Skill, Red", self.skr)
        row(v, "AI Skill, Blue", self.skb)
        hint(v, "How good the AI pilots are, one setting for each side (Red's ground units follow the Red setting; Blue's base defences are always Excellent, whatever this says). "
                "Level default is what SQE always did: Red follows the difficulty level (Average, Good, High) and Blue's AI flights fly at High. DCS's top skill "
                "levels can feel like cheating; lower one side if it does. It changes the AI's skill only, not how the campaign's numbers run. It applies from your next mission.")
        v.addStretch(1)

        # ---- Mission build: merging and limits -----------------------------------------------------------------------------------
        v = page("Mission Build")
        self.merge = QComboBox(); self.merge.addItem("Off (One Package per Mission)", "off"); self.merge.addItem("Same Area (Targets Inside the Radius)", "area")
        self.merge.setCurrentIndex(1 if settings.merge_mode == "area" else 0)
        self.mmax = StepSpin(); self.mmax.setRange(60, 400); self.mmax.setSuffix(" units max"); self.mmax.setValue(int(settings.max_units))
        row(v, "Package Merging", self.merge, self.mmax)
        hint(v, "Packages inside the radius that start within the time windows below fly in the same mission (AI-flown, one shared ground "
                "world and support). The waiting window shows the unit count so you can compare performance. The unit limit counts the whole mission, merged packages included: over it, returning flights go first, then the package that starts latest (a Fighter Sweep last), then wrecks are trimmed.")
        self.mrad = StepSpin(); self.mrad.setRange(10, 150); self.mrad.setSingleStep(5); self.mrad.setSuffix(" nm"); self.mrad.setValue(int(getattr(settings, "merge_radius_nm", 15)))
        row(v, "Merge Radius", self.mrad)
        hint(v, "Packages whose target is inside this circle fly in the same mission (within the time windows below). The circle is centred on your target, "
                "slid inward so it never hangs over the edge of the target area; your own target stays inside it. A raid also counts along its way in, "
                "from its airfield to its target. If the unit limit is exceeded, the package that starts latest drops first.")
        self.mraids = QCheckBox("Merge raids")
        self.mraids.setChecked(bool(getattr(settings, "merge_raids_all", True))); v.addWidget(self.mraids)
        hint(v, "Raid intercepts that start inside the time windows fly in one mission, wherever the raids are going. Off: a raid folds in only when its way in passes "
                "your target area. Missions that carry red's raids are marked in the list: red border = only red's raids, amber = your packages and red's raids together.")
        self.mback = StepSpin(); self.mback.setRange(0, 30); self.mback.setSingleStep(5); self.mback.setSuffix(" min before"); self.mback.setValue(int(getattr(settings, "merge_earlier_min", 15)))
        row(v, "Earlier Packages", self.mback)
        hint(v, "Packages that started up to this long before yours also fly, already airborne and underway when the mission starts. "
                "A package that has already struck is not flown to its target (see Ruins on this tab). 0 = only later packages.")
        self.mfwd = StepSpin(); self.mfwd.setRange(0, 60); self.mfwd.setSingleStep(5); self.mfwd.setSuffix(" min after"); self.mfwd.setValue(int(getattr(settings, "merge_later_min", 30)))
        row(v, "Later Packages", self.mfwd)
        hint(v, "Packages that start up to this long after yours also fly in the same mission (late-activated, they push at their own time). "
                "Over the unit limit, the package that starts latest is dropped first.")
        self.feng = StepSpin(); self.feng.setRange(0, 300); self.feng.setSuffix(" nm"); self.feng.setValue(int(settings.fighter_engage_nm))
        self.fmin = StepSpin(); self.fmin.setRange(0, 120); self.fmin.setSuffix(" min after TOT"); self.fmin.setValue(int(settings.fighter_engage_minutes))
        row(v, "TARCAP / Escort / Sweep Engage Range", self.feng, self.fmin)
        hint(v, "How far AI TARCAPs, escorts, sweeps and SEAD go after a fighter, and for how long: the engage task ends this many minutes after the strike's TOT and they fly on home (alert pairs get 5 minutes more). 0 = unlimited. Your own flight is never limited (unless SQE was started with --ai-test).")

        def tick(text, checked, hint_text, enabled=True):                 # one checkbox with its setting, its hint under it and its enabled state
            cb = QCheckBox(text); cb.setChecked(bool(checked)); cb.setEnabled(enabled); v.addWidget(cb); hint(v, hint_text)
            return cb
        self.hotramp = tick("Hot Starts at the Ramp (Scramble Pairs)", getattr(settings, "hot_ramp_scrambles", False),
            "Land fields only. On: alert pairs at land fields wait hot on the ramp and taxi out when called. Off: they wait hidden and appear on the runway (the older, steadier way). "
            "The carrier always keeps the hidden deck start, and so does your own field.")
        hs_ = getattr(settings, "hot_runway_starts", False); ho_ = hs_ and getattr(settings, "hot_runway_own_field", False)      # the own-field flag only counts with the runway starts on
        lb_ = QLabel("Hot Starts on the Runway"); v.addWidget(lb_)
        self.hot_none, self.hot_other, self.hot_own = QRadioButton("Disabled"), QRadioButton("AI Flights at a Different Field"), QRadioButton("AI Flights Including at My Own Field")
        self.hot_grp = QButtonGroup(self)
        for rb_ in (self.hot_none, self.hot_other, self.hot_own):
            self.hot_grp.addButton(rb_); v.addWidget(rb_)
        (self.hot_own if ho_ else self.hot_other if hs_ else self.hot_none).setChecked(True)
        hint(v, "Disabled: all AI flights appear airborne.\n"
                "AI Flights at a Different Field: at land fields other than yours, AI package flights wait hidden and appear on the runway in time to make their push, one runway release a minute apart. "
                "A flight that cannot be released in time (the package is already underway at the start) still appears airborne. The carrier keeps the airborne start.\n"
                "AI Flights Including at My Own Field: as above, and AI flights at your own field appear on the runway only after you have taken off, never in the last ten minutes before your planned landing, "
                "and wait while you are on your way in to land.")
        self.dorm = tick("Dormant Ground Sites (Wake When You Come Near)", getattr(settings, "dormant_sites", False),
            "On: red SAM sites on your route, red supply guards and the defences of blue airfields without flights start asleep. A detector (an early-warning radar, a red patrol or the longest-range SAM site) or an enemy aircraft coming near wakes them; "
            "30 seconds after no enemy is near they go back to sleep and wake again when one returns. On top of the usual mission, every other red radar (live) and SAM site (asleep) in the war is added, and they do not count toward the unit limits, so the mission can be much heavier. Off: as before, only the sites near your route and target are built, all live from the start, and blue fields without flights have no defences.")
        self.ilslv = tick("Keep ILS Runways Active in Low Visibility", getattr(settings, "ils_low_vis", True),
            "DCS lights the ILS only on the runway it counts as active, and the low-level wind picks that runway. When ceiling or visibility is low, the ground wind is turned to favour each field's "
            "ILS runway; the wind aloft keeps the season's real direction. In good weather the wind is left as it is.")
        self.awt = tick("AWACS Calls Need a Tuned Radio", getattr(settings, "awacs_tuned", True),           # v0.41.215 (XO)
            "On: you hear the AWACS only while one of your radios is on its frequency (it is in your comms plan); a call that comes due while you are not tuned is held up to a minute, "
            "then dropped, with one on-screen note. Read from the F-16C and A-10C first radio (UHF), and both radios of the F/A-18C and F-14B; the F-15C (FC3) is always counted tuned. "
            "Off: you hear every AWACS call whatever your radio is set to.")
        self.dmgc = tick("Show Damage Calls", getattr(settings, "damage_calls", True),                       # v0.41.215 (XO)
            "On: the other blue aircraft (your wingmen, other flights, the tanker and the AWACS) call when they are hit and when they eject or go down (\"Mayday, mayday, ejecting\"), "
            "each picked at random from a short list. Off: no such calls.")
        # v0.41.18: AI landings
        _lm = [("Always Skip", "always"), ("Skip at Your Home Deck / Field", "home"), ("Land for Real", "never")]
        self.land_cv, self.land_af = QComboBox(), QComboBox()
        for cb_, key_, dflt_ in ((self.land_cv, "ai_land_carrier", "always"), (self.land_af, "ai_land_field", "never")):
            for lab_, val_ in _lm:
                cb_.addItem(lab_, val_)
            cb_.setCurrentIndex(max(0, cb_.findData(str(getattr(settings, key_, dflt_)))))
        _row = QFormLayout(); _row.addRow("AI Landings, Carrier", self.land_cv); _row.addRow("AI Landings, Airfields", self.land_af); v.addLayout(_row)
        hint(v, "Skip: AI flights going home are recovered short of the base (10 nm from the boat, 8 nm from a field), count as landed and leave the mission, "
                "so DCS's landing queue never runs them dry or fills your pattern. Your own wingmen are recovered too once you are back. Land for real: DCS landings.")
        self.ruins = QCheckBox("Ruins: Show What Earlier Packages Already Hit (Smoke and Fire); Struck Flights Fly Home")
        self.ruins.setChecked(bool(getattr(settings, "ruins", True))); v.addWidget(self.ruins)
        hint(v, "Earlier packages in the same area that struck before your start leave smoking ruins (at most three sites, a few plumes each). The result is "
                "decided when you build the mission and applied at the debrief.")
        self.carc = QCheckBox("Carcasses: Wrecks at Damaged and Destroyed Ground Sites Near Your Route")
        self.carc.setChecked(bool(getattr(settings, "carcasses", True))); v.addWidget(self.carc)
        self.cw = StepSpin(); self.cw.setRange(5, 100); self.cw.setSuffix(" % of a unit"); self.cw.setValue(int(getattr(settings, "wreck_static_weight_pct", 25)))
        row(v, "Wreck and Static Weight", self.cw)
        hint(v, "Wrecks and supply buildings (fuel tanks, depots) are static objects: no AI, no weapons, they never move. Each counts this share of a unit toward "
                "the unit limit. When a mission is over the limit the furthest wrecks from your route are dropped first, before any flight is touched; buildings are "
                "placed before wrecks and are never dropped for them. Wrecks stay where they are from day to day.")
        v.addStretch(1)

        # ---- DCS integration: paths and the scripting patch ---------------------------------------------------------------------
        v = page("DCS Integration")
        self.inst, self.saves = QLineEdit(S.native(settings.dcs_install)), QLineEdit(S.native(settings.dcs_saves))
        for label, line, ttl, h_ in (
                ("DCS", self.inst, "Select the DCS World Install Folder", "Install folder (only needed for the MissionScripting.lua patch)"),
                ("DCS Saves", self.saves, "Select Your DCS Saved Games Folder", r"e.g. C:\Users\You\Saved Games\DCS  or  ...\DCS_Server")):
            r = QHBoxLayout(); lb = QLabel(label); lb.setMinimumWidth(80); b = QPushButton("Browse")
            b.clicked.connect(lambda _=0, l=line, t_=ttl: _browse(self, l, t_))
            r.addWidget(lb); r.addWidget(line, 1); r.addWidget(b); v.addLayout(r)
            hint(v, h_)
        self.ms = QLabel(); v.addWidget(self.ms)
        self.autopatch = QCheckBox("Enable DCS Scripting Access While SQE Is Open (Patches MissionScripting.lua at Start, Restores It on Exit)")
        self.autopatch.setChecked(bool(settings.auto_patch_scripting)); v.addWidget(self.autopatch)
        hint(v, "Results need io/lfs enabled in MissionScripting.lua. A backup is saved next to the file. "
                "If SQE is closed before the mission ends, DCS can no longer write the results file.")
        v.addSpacing(10)
        self.ecm = QCheckBox("ECM Script (SQE's Own Jamming)")
        self.ecm.setChecked(bool(getattr(settings, "ecm_script", False))); v.addWidget(self.ecm)
        hint(v, "SQE's own jamming model; off by default. Off: jammers use DCS's own ECM. AI jets with a jammer (F-16, F/A-18, F-14, F-15C and the rest) keep it off on the way in and out "
                "and switch it on over the attack leg only when a radar locks them. On: SQE's hook decides jamming and burn-through itself.")
        self.ecm_msg = QCheckBox("Show ECM Status")                      # v0.41.213 (XO): a sub-option of the ECM script
        self.ecm_msg.setChecked(bool(getattr(settings, "ecm_status", True))); self.ecm_msg.setEnabled(self.ecm.isChecked())
        self.ecm.toggled.connect(self.ecm_msg.setEnabled); self.ecm_msg.setStyleSheet("margin-left:22px;")
        self.ecm_msg.setToolTip("On-screen ECM messages: your F-16C's ECM lamp (\"ECM on\" / \"ECM off\") and \"Cockpit: ECM On\" / \"Cockpit: ECM Off\" for the F10 SQE ECM Switch / SQE ECM OFF calls of an FC3 jet. Off: no messages; the F10 commands still work.")
        v.addWidget(self.ecm_msg)
        v.addSpacing(10)
        self.ecm_state = QLabel(); v.addWidget(self.ecm_state)
        self.ecm_inst = QPushButton("Install ECM Script"); self.ecm_rem = QPushButton("Remove")
        self.ecm_inst.clicked.connect(lambda: self._ecm_do(S.install_ecm_script)); self.ecm_rem.clicked.connect(lambda: self._ecm_do(S.remove_ecm_script))
        r = QHBoxLayout(); r.addWidget(self.ecm_inst); r.addWidget(self.ecm_rem); r.addStretch(1); v.addLayout(r)
        hint(v, "Lets SQE read your F-16C's ECM lamp (about four times a second) so its jamming model knows when your jammer is on. It copies sqe_ecm_export.lua into "
                "Saved Games\\DCS\\Scripts and adds one line to the end of Export.lua there (a backup, Export.lua.sqe.bak, is saved first). Remove takes the line and the file out again. "
                "Without it SQE counts your jammer as on over the attack leg. Takes effect when DCS starts.")
        v.addStretch(1)
        self.inst.textChanged.connect(self._refresh); self.saves.textChanged.connect(self._refresh); self._refresh()

        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel); bb.accepted.connect(self._save)
        bb.rejected.connect(self.reject); lay.addWidget(bb)
        if not settings.dcs_saves or not Path(settings.dcs_saves).exists():
            self.tabs.setCurrentIndex(3)                                  # first run: the paths are what is missing

    def _refresh(self):
        self.ms.setText("MissionScripting.lua: " + S.mission_scripting_status(self.inst.text()))
        st = S.ecm_script_state(self.saves.text())
        self.ecm_state.setText("ECM script: " + S.ecm_script_status(self.saves.text()))
        self.ecm_inst.setEnabled(st not in ("nofolder", "ok")); self.ecm_rem.setEnabled(st not in ("nofolder", "none"))
        self.ecm_inst.setText("Update ECM Script" if st == "old" else "Install ECM Script")

    def _ecm_do(self, fn):
        ok, msg = fn(S.native(self.saves.text()))
        (QMessageBox.information if ok else QMessageBox.warning)(self, "ECM script", msg)
        self._refresh()

    def _save(self):
        self.s.dcs_install, self.s.dcs_saves = S.native(self.inst.text()), S.native(self.saves.text())
        self.s.marshal_slack_min = int(self.hold.value())
        self.s.takeoff_buffer_s = int(self.tob.value())
        self.s.ai_unlimited_fuel = self.fuel.isChecked()
        self.s.hot_ramp_scrambles = self.hotramp.isChecked()
        self.s.hot_runway_starts = not self.hot_none.isChecked()
        self.s.hot_runway_own_field = self.hot_own.isChecked()
        self.s.merge_mode = self.merge.currentData(); self.s.max_units = int(self.mmax.value())
        self.s.merge_earlier_min = int(self.mback.value()); self.s.merge_later_min = int(self.mfwd.value())
        self.s.merge_radius_nm = int(self.mrad.value()); self.s.merge_raids_all = bool(self.mraids.isChecked())
        self.s.ruins = bool(self.ruins.isChecked())
        self.s.ecm_script = bool(self.ecm.isChecked())
        self.s.ecm_status = bool(self.ecm_msg.isChecked())
        self.s.awacs_tuned = bool(self.awt.isChecked())
        self.s.damage_calls = bool(self.dmgc.isChecked())
        self.s.splash_damage = bool(self.splash.isChecked())
        self.s.ai_land_carrier = str(self.land_cv.currentData() or "always")
        self.s.ai_land_field = str(self.land_af.currentData() or "never")
        self.s.carcasses = bool(self.carc.isChecked()); self.s.wreck_static_weight_pct = int(self.cw.value())
        self.s.dormant_sites = bool(self.dorm.isChecked())
        self.s.weather_mode = str(self.wxm.currentData())
        self.s.ils_low_vis = bool(self.ilslv.isChecked())
        self.s.ai_skill_red = str(self.skr.currentData() or "level"); self.s.ai_skill_blue = str(self.skb.currentData() or "level")
        self.s.fighter_engage_nm = int(self.feng.value()); self.s.fighter_engage_minutes = int(self.fmin.value())
        self.s.auto_patch_scripting = self.autopatch.isChecked(); self.s.patch_asked = True
        if self.s.dcs_install:                                   # take effect now, not at the next start
            ok, msg = (S.patch_mission_scripting if self.s.auto_patch_scripting else S.restore_mission_scripting)(self.s.dcs_install)
            if not ok:
                QMessageBox.warning(self, "MissionScripting.lua", msg)
        pr = self.s.problems()
        if pr:
            QMessageBox.warning(self, "Check your paths", "\n".join(pr)); return
        if self.edge_rows:                                       # S88 R3: Tactical Edge is saved with the open campaign (the caller saves the session)
            self.state.ground["tactical_edge"] = bool(self.edge.isChecked()); self.state.ground["tactical_edge_decay"] = bool(self.edge.isChecked() and self.edge_decay.isChecked())
        self.s.save(); self.accept()


class WaitingDialog(QDialog):
    """FLY opens this. It polls SQE_state.json and shows live casualties for both sides."""
    def __init__(self, session, parent=None):
        super().__init__(parent); self.sess = session; self.data = None; self.manual = None
        self.setWindowTitle("Sortie In Progress"); self.setMinimumSize(760, 560); self.resize(780, 760)
        p = session.state.pending; tl = p["timeline"]
        lay = QVBoxLayout(self); lay.setSpacing(12)
        t = QLabel("Sortie In Progress"); t.setObjectName("title"); lay.addWidget(t)
        self.overall = QLabel(""); self.overall.setObjectName("h2"); self.overall.setVisible(False)         # S77: IN FLIGHT / ALL RECOVERED (set by _poll); S98b: sits above "Last update", hidden while empty
        info = card(); lay.addWidget(info)
        il = info.layout()
        il.addWidget(QLabel(f"Mission file: <b>SQE_Sortie.miz</b> in your DCS Missions folder. Start DCS, open it from the Missions list, and fly."))
        pd = p.get("package_dict", {}); cn = p.get("counts") or {}
        il.addWidget(QLabel(f"Mission start <b>{pd.get('start', '')}</b> local   |   {cn.get('groups', '?')} groups, {cn.get('units', '?')} units"))
        il.addWidget(QLabel(f"Launch {tl['launch']}   |   Marshal {tl['marshal']}   |   <b>PUSH {tl['push']}</b>   |   <b>TOT {tl['tot']}</b>   |   Egress {tl['egress']}"))
        self._notes = list(p.get("warnings") or [])             # XO 2026-11-15: the build notes sit behind a Notes button (a popup), not in the card
        if self._notes:
            self.b_notes = QPushButton(f"Notes ({len(self._notes)})"); self.b_notes.setStyleSheet(f"color:{theme.AMBER};")
            self.b_notes.clicked.connect(self._show_notes); il.addWidget(self.b_notes, 0, Qt.AlignLeft)
        self.status = QLabel("Waiting for DCS results..."); self.status.setObjectName("h2")        # S98b: placed above "Last update" below
        self.ptbl = QTableWidget(0, 2); self.ptbl.setHorizontalHeaderLabels(["Package", "Status"])         # S87: one row per package, its phase and result (set by _status_lines)
        self.ptbl.verticalHeader().setVisible(False); self.ptbl.setEditTriggers(QTableWidget.NoEditTriggers); self.ptbl.setSelectionMode(QTableWidget.NoSelection)
        self.ptbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch); self.ptbl.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.ptbl.setWordWrap(True); self.ptbl.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded); self.ptbl.setVerticalScrollMode(QTableWidget.ScrollPerPixel); self._fill_packages([]); lay.addWidget(self.ptbl, 100); lay.addStretch(1)       # S98b: blank until DCS answers; the package table sits right after the info card and takes its rows, a spacer takes the spare height so everything below stays anchored to the bottom (a short window squeezes the table to PKG_MIN_H and it scrolls)
        self.tbl = QTableWidget(0, 3); self.tbl.setHorizontalHeaderLabels(["This Sortie", "Friendly", "Enemy"])
        self.tbl.verticalHeader().setVisible(False); self.tbl.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tbl.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl.setFixedHeight(100)                                         # blank until the first state file; _fill sets the exact height
        self.tbl.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff); self.tbl.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        lay.addWidget(self.tbl)
        lay.addWidget(self.status); lay.addWidget(self.overall)          # S98b: mission status stacked just above "Last update"
        self.last = QLabel(""); self.last.setObjectName("small"); lay.addWidget(self.last)
        row = QHBoxLayout()
        self.b_man = QPushButton("Manually Submit..."); self.b_abort = QPushButton("Abort mission"); self.b_abort.setObjectName("danger")
        self.b_ok = QPushButton("Accept results"); self.b_ok.setObjectName("good"); self.b_ok.setEnabled(False)
        row.addWidget(self.b_man); row.addWidget(self.b_abort); row.addStretch(1); row.addWidget(self.b_ok); lay.addLayout(row)
        self.b_man.clicked.connect(self._manual); self.b_abort.clicked.connect(self._abort); self.b_ok.clicked.connect(self.accept)
        self.timer = QTimer(self); self.timer.timeout.connect(self._poll); self.timer.start(1000); self._dots = 0
        self._poll()

    def _fill(self, t):
        rows = [(DB._title("Aircraft lost / total"), f"{t['blue_air_lost']} / {t['blue_air_total']}", f"{t['red_air_lost']} / {t['red_air_total']}"),
                (DB._title("Ground units lost / total"), f"{t['blue_ground_lost']} / {t['blue_ground_total']}", f"{t['red_ground_lost']} / {t['red_ground_total']}")]
        self.tbl.setRowCount(len(rows))
        for i, r in enumerate(rows):
            for j, v in enumerate(r):
                it = QTableWidgetItem(v); it.setTextAlignment(Qt.AlignCenter if j else Qt.AlignLeft | Qt.AlignVCenter)
                self.tbl.setItem(i, j, it)
        self.tbl.resizeRowsToContents()
        self.tbl.setFixedHeight(self.tbl.horizontalHeader().height() + sum(self.tbl.rowHeight(i) for i in range(len(rows))) + 10)       # just its rows: the spare height goes to the package table

    PKG_MIN_H = 130                 # px: header and about two rows; the least the package table is squeezed to before it scrolls

    def _show_notes(self):
        """The build notes in a popup under the Notes button; a click outside closes it. No layout change."""
        pop = QFrame(self, Qt.Popup); pop.setObjectName("card"); pl = QVBoxLayout(pop)
        for n in self._notes:
            lb = QLabel(n); lb.setWordWrap(True); lb.setStyleSheet(f"color:{theme.AMBER};"); lb.setMaximumWidth(self.width() - 80); pl.addWidget(lb)
        pop.adjustSize(); pop.move(self.b_notes.mapToGlobal(self.b_notes.rect().bottomLeft())); pop.show()
        self._pop = pop

    def _fill_packages(self, rows):
        self.ptbl.setRowCount(len(rows))
        for i, r in enumerate(rows):
            for j, v in enumerate((r["name"], r["text"])):
                it = QTableWidgetItem(v); it.setTextAlignment(Qt.AlignLeft | Qt.AlignTop); self.ptbl.setItem(i, j, it)       # XO 2026-11-15: text at the top of its cell when a row wraps
        self.ptbl.resizeRowsToContents()
        need = self.ptbl.horizontalHeader().height() + sum(self.ptbl.rowHeight(i) for i in range(len(rows))) + 20
        self.ptbl.setMaximumHeight(need); self.ptbl.setMinimumHeight(min(need, self.PKG_MIN_H))           # as tall as its rows when the window has room; a short window squeezes it to PKG_MIN_H and it scrolls (bar only when needed)

    def _status_lines(self, data):
        """S77: the objective lines and the overall line, read-only from the hook's state file (nothing in the campaign changes; Accept stays the authority).
        The hook rewrites the file every 30 s and on every kill / loss / landing, so these change at most that often."""
        st = self.sess.state; man = self.sess.manifest(); pend = st.pending or {}
        start = (pend.get("package_dict") or {}).get("start", "00:00")
        self._fill_packages(DB.package_rows(st, man, data, pend))
        fs = DB.flight_status(st, man, data, pend)
        if fs["total"] and fs["airborne"] == 0:
            self.overall.setText("ALL RECOVERED, safe to exit"); self.overall.setStyleSheet(f"color:{theme.GREEN}; font-weight:bold;")
        elif fs["total"] and not data.get("mission_ended"):
            nxt = f", next event TOT {DB._clock_hm(start, fs['next_tot_s'])}" if fs["next_tot_s"] is not None else ""
            self.overall.setText(f"IN FLIGHT: {fs['airborne']} of {fs['total']} friendly aircraft airborne{nxt}"); self.overall.setStyleSheet("font-weight:bold;")
        else:
            self.overall.setText("")
        self.overall.setVisible(bool(self.overall.text()))

    def _poll(self):
        status, data, t = self.sess.poll(self.manual)
        self._dots = (self._dots + 1) % 4
        if status == "ok":
            self.data = data; self._fill(t); self.b_ok.setEnabled(True)
            try:
                self._status_lines(data)
            except Exception:                                   # a status line must never break the waiting window
                pass
            if data.get("mission_ended"):
                self.status.setText("Mission ended. Review the numbers, then Accept."); self.status.setStyleSheet(f"color:{theme.GREEN};")
            else:
                self.status.setText("Sortie underway" + "." * self._dots)
            self.last.setText(f"Last update from DCS: {time.strftime('%H:%M:%S')}  (mission time {int(data.get('time', 0)) // 60} min)")
        elif status == "mismatch":
            self.status.setText("Found a results file, but it belongs to a different sortie or campaign. Waiting...")
        else:
            self.status.setText("Waiting for DCS results" + "." * self._dots)

    def _manual(self):
        f, _ = QFileDialog.getOpenFileName(self, "Select SQE_state.json", str(self.sess.settings.sqe_dir), "State (*.json)")
        if not f:
            return
        status, data, t = self.sess.load_manual(f)
        if status == "mismatch" and QMessageBox.question(self, "Different sortie",
                "That file is for a different sortie or campaign. Use it anyway?") != QMessageBox.Yes:
            return
        if status in ("none", "busy"):
            QMessageBox.warning(self, "Cannot read file", "That file could not be read."); return
        if status == "mismatch":
            self.data = data
        else:
            self.manual = f
        self.timer.stop(); self.data = data; self.b_ok.setEnabled(True)
        self.status.setText("Using the file you selected. Press Accept.")
        if t:
            self._fill(t)

    def _abort(self):
        if QMessageBox.question(self, "Abort mission", "Discard this sortie? The campaign stays unchanged.") == QMessageBox.Yes:
            self.timer.stop(); self.done(2)

    def reject(self):          # closing the window keeps the sortie pending; Debrief via the Missions page
        self.timer.stop(); super().reject()


def _hm(s: str) -> int:
    h, m = str(s).split(":")[:2]
    return int(h) * 60 + int(m)


class DayResolvedDialog(QDialog):
    """v0.41.208 (XO): what Skip Turn did, fully described: one block per package (the war simulation's own result lines), scrollable.
    v0.41.337 (Phase 3): it is labelled by turn and takes several turns: `turns` is [{"label": "Day 1, 20:00", "results": [...]}, ...].
    S21 (XO 2026-11-11): the AFTER-ACTION REPORT of every skip, one dialog per run. `reason` (why an auto-skip stopped) is its header line.
    The report is a plain list of every simulated event, all shown at once in one QTextBrowser (it scrolls by itself, starts at the top; the animation was dropped)."""
    def __init__(self, turns: list, parent=None, reason: str = ""):
        super().__init__(parent); self.setWindowTitle("After-action report"); self.setMinimumSize(700, 480)
        lay = QVBoxLayout(self); lay.setSpacing(12)
        results = [r for t_ in turns for r in t_.get("results", [])]
        t = QLabel(f"{turns[0]['label']} resolved" if len(turns) == 1 else f"{turns[0]['label']} to {turns[-1]['label']}: {len(turns)} turns resolved"); t.setObjectName("title"); lay.addWidget(t)
        if reason:
            rl = QLabel(html.escape(reason)); rl.setObjectName("h2"); rl.setWordWrap(True); lay.addWidget(rl)
        ok = sum(1 for r in results if r.get("success")); scr = sum(1 for r in results if r.get("scrubbed")); held = sum(1 for r in results if r.get("held"))
        bits = [f"{ok} succeeded", f"{len(results) - ok - scr - held} failed"] + ([f"{held} turned back at the SAM gate"] if held else []) + ([f"{scr} scrubbed for weather"] if scr else [])
        sub = QLabel(f"The war simulation resolved {len(results)} package{'s' if len(results) != 1 else ''}: " + ", ".join(bits) + "."); sub.setWordWrap(True); sub.setObjectName("dim"); lay.addWidget(sub)
        self.body = QTextBrowser(); lay.addWidget(self.body, 1)
        h = []
        for t_ in turns:
            if len(turns) > 1:                                            # a run or a night: one header per turn, so the long log reads turn by turn
                h.append(f"<h3 style='margin-bottom:2px'>{html.escape(t_['label'])}</h3>")
            if not t_.get("results"):
                h.append(f"<p style='color:{theme.DIM}'>Nothing was tasked this turn.</p>")
            for r in t_.get("results", []):
                ln = r.get("lines") or [r.get("objective", "?")]
                col = theme.GREEN if r.get("success") else theme.AMBER if (r.get("scrubbed") or r.get("held")) else theme.RED
                detail = ("<br>" + "<br>".join("&nbsp;&nbsp;&nbsp;" + html.escape(x.strip()) for x in ln[1:])) if ln[1:] else ""     # no <br> when a result has no detail lines
                h.append(f"<p style='margin-bottom:2px'><b style='color:{col}'>{html.escape(ln[0])}</b>{detail}</p>")
        self.body.setHtml("".join(h) or "<p>Nothing was tasked.</p>")
        bb = QDialogButtonBox(QDialogButtonBox.Close); bb.rejected.connect(self.reject)
        btn = bb.button(QDialogButtonBox.Close); btn.setText("Continue"); btn.setObjectName("primary"); btn.clicked.connect(self.accept); lay.addWidget(bb)


class DebriefDialog(QDialog):
    def __init__(self, out: dict, state, parent=None):
        super().__init__(parent); self.setWindowTitle("Debrief"); self.setMinimumSize(820, 680)
        lay = QVBoxLayout(self); lay.setSpacing(12)
        t = QLabel("Debrief"); t.setObjectName("title"); lay.addWidget(t)
        if out["status"] != "ACTIVE":
            b = QLabel("CAMPAIGN VICTORY" if out["status"] == "VICTORY" else "CAMPAIGN LOST"); b.setObjectName("h2")
            b.setStyleSheet(f"color:{theme.GREEN if out['status'] == 'VICTORY' else theme.RED}; font-size:20px;"); lay.addWidget(b)
        c = card(); lay.addWidget(c)
        story = QLabel(out["story"].replace("\n", "<br>")); story.setWordWrap(True); story.setStyleSheet("font-size:14px;")
        c.layout().addWidget(story)
        pi = out.get("pilot") or {}
        if pi:
            pl = QLabel(f"Your log: {pi['flight_s'] // 60} min airborne, {pi['ka']} air / {pi['kg']} ground / {pi['ks']} ship kills credited to you.")
            pl.setObjectName("dim"); lay.addWidget(pl)
        h = QLabel("Results of your sortie"); h.setObjectName("h2"); lay.addWidget(h)
        tb = QTextBrowser(); tb.setMaximumHeight(130)
        tb.setHtml("<br>".join(out["lines"]) + (f"<br><span style='color:{theme.DIM}'>(Mission end event not seen: results are from the last checkpoint.)</span>" if not out["ended"] else ""))
        lay.addWidget(tb)
        if out.get("kill_log"):
            h = QLabel("Kill log"); h.setObjectName("h2"); lay.addWidget(h)
            kb = QTextBrowser(); kb.setMaximumHeight(130)
            kb.setHtml("<br>".join(k.replace("&", "&amp;").replace("<", "&lt;") for k in out["kill_log"])); lay.addWidget(kb)
        h = QLabel("Meanwhile, elsewhere in the theatre"); h.setObjectName("h2"); lay.addWidget(h)
        mw = QTextBrowser()
        mw.setHtml("<br>".join(("<b>" + ln + "</b>") if i == 0 else ln for r in out["meanwhile"] for i, ln in enumerate(r["lines"])) or "Nothing else was tasked.")
        lay.addWidget(mw, 1)
        d = QLabel(f"Day {state.day} begins. A new tasking order is ready."); d.setObjectName("dim"); lay.addWidget(d)
        bb = QDialogButtonBox(QDialogButtonBox.Close); bb.rejected.connect(self.reject); bb.accepted.connect(self.accept)
        btn = bb.button(QDialogButtonBox.Close); btn.setText("Continue"); btn.setObjectName("primary")
        btn.clicked.connect(self.accept); lay.addWidget(bb)
