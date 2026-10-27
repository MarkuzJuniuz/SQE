from __future__ import annotations
import json
import time
from pathlib import Path
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QCheckBox, QSpinBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QFrame, QHBoxLayout,
                               QLabel, QLineEdit, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem,
                               QTextBrowser, QVBoxLayout, QHeaderView, QTabWidget, QWidget, QScrollArea)
from .. import settings as S
from ..aircraft import AIRCRAFT
from ..difficulty import LEVELS
from . import theme
from .widgets import card


def _browse(parent, line: QLineEdit, title: str):
    d = QFileDialog.getExistingDirectory(parent, title, line.text() or str(Path.home()))
    if d:
        line.setText(S.native(d))


class NewCampaignDialog(QDialog):
    def __init__(self, parent=None, weather_mode: str = "clear", skill_red: str = "level", skill_blue: str = "level"):
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
        self.month = QComboBox()
        for i, mname in enumerate(("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"), 1):
            self.month.addItem(mname, i)
        self.month.setCurrentIndex(5)
        self.day = QSpinBox(); self.day.setRange(1, 28); self.day.setValue(12)
        row = QHBoxLayout(); row.addWidget(self.month, 1); row.addWidget(self.day); row.addWidget(QLabel("2006"))
        form.addRow("Campaign starts", row)
        self.night = QCheckBox("Allow night sorties (otherwise missions are spread through daylight)")
        form.addRow("", self.night)
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
        self.blurb = QLabel(); self.blurb.setWordWrap(True); self.blurb.setObjectName("dim"); lay.addWidget(self.blurb)
        self.lvl.currentIndexChanged.connect(self._b); self._b()
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel); bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject); lay.addWidget(bb)

    def _b(self):
        self.blurb.setText(LEVELS[self.lvl.currentData()].blurb)

    def _squads(self):
        from ..scenario import squadron_options
        self.sqd.clear()
        for sid, label in squadron_options(self.ac.currentData(), self.th.currentData() or "caucasus"):
            self.sqd.addItem(label, sid)

    def values(self) -> dict:
        return {"name": self.name.text().strip() or "Campaign", "aircraft": self.ac.currentData(), "level": self.lvl.currentData(),
                "start_date": f"2006-{self.month.currentData():02d}-{self.day.value():02d}", "night_ops": self.night.isChecked(),
                "squadron": self.sqd.currentData(), "theatre": self.th.currentData() or "caucasus", "weather_mode": str(self.wx.currentData()),
                "ai_skill_red": str(self.skr.currentData() or "level"), "ai_skill_blue": str(self.skb.currentData() or "level")}


class SettingsDialog(QDialog):
    """Six tabs: General (flight timing), Campaign (what the world does), Mission build (merging, limits), DCS integration (paths, the
    scripting patch), Terrain scan (with a plain scanned / not scanned status) and Experimental (features still being tested). Every control keeps the name it always had."""
    def __init__(self, settings: S.AppSettings, parent=None):
        super().__init__(parent); self.s = settings; self.setWindowTitle("Settings"); self.setMinimumWidth(720); self.setMinimumHeight(560); self.resize(780, 700)
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
        self.tob = QSpinBox(); self.tob.setRange(-600, 900); self.tob.setSuffix(" s"); self.tob.setValue(int(settings.takeoff_buffer_s))
        row(v, "Takeoff buffer", self.tob)
        hint(v, "Time between mission start and the takeoff time on your kneeboard (you start on the runway or cat, engines running). "
                "Default 60 s. Negative means the plan expects you to be rolling before the clock starts, so you must make the time up in the air.")
        self.hold = QSpinBox(); self.hold.setRange(-10, 30); self.hold.setSuffix(" min"); self.hold.setValue(int(settings.hold_minutes))
        row(v, "Marshal slack", self.hold)
        hint(v, "Time between reaching the marshal point and the PUSH. Smaller = less waiting. Negative means you must beat the "
                "natural pace (afterburner time). AI flights adjust automatically.")
        self.fuel = QCheckBox("AI fuel management (unlimited until the push, real fuel in the fight, unlimited again from egress)")
        self.fuel.setChecked(bool(settings.ai_unlimited_fuel)); v.addWidget(self.fuel)
        self.hotramp = QCheckBox("Hot starts at the ramp (scramble pairs)")
        self.hotramp.setChecked(bool(getattr(settings, "hot_ramp_scrambles", False))); v.addWidget(self.hotramp)
        hint(v, "Land fields only. On: alert pairs at land fields wait hot on the ramp and taxi out when called. Off: they wait hidden and appear on the runway (the older, steadier way). "
                "The carrier always keeps the hidden deck start, and so does your own field.")
        self.f14n = QCheckBox("F-14B(U): name waypoints with special-point codes (IP, ST, HB...) so DEST can select them")
        self.f14n.setChecked(bool(settings.f14_special_names)); v.addWidget(self.f14n)
        v.addStretch(1)

        # ---- Experimental: features still being tested; each one can be switched off --------------------------------------
        v = page("Experimental")
        hint(v, "Features still being tried out. Each one can be switched off if it misbehaves; the defaults are the safe ones.")
        self.ecm = QCheckBox("ECM script (SQE's own jamming)")
        self.ecm.setChecked(bool(getattr(settings, "ecm_script", False))); v.addWidget(self.ecm)
        hint(v, "SQE's own jamming model; off by default. Off: jammers use DCS's own ECM. AI jets with a jammer (F-16, F/A-18, F-14, F-15C and the rest) keep it off on the way in and out "
                "and switch it on over the attack leg only when a radar locks them. On: SQE's hook decides jamming and burn-through itself.")
        self.hotrwy = QCheckBox("Hot starts on the runway (AI flights)")
        self.hotrwy.setChecked(bool(getattr(settings, "hot_runway_starts", False))); v.addWidget(self.hotrwy)
        hint(v, "Land fields other than yours. On: AI package flights wait hidden and appear on the runway in time to make their push, one runway release a minute apart. "
                "A flight that cannot be released in time (the package is already underway at the start) still appears airborne. The carrier keeps the airborne start. Off: all AI flights appear airborne.")
        self.hotrwy_own = QCheckBox("    ...also at my own field")
        self.hotrwy_own.setChecked(bool(getattr(settings, "hot_runway_own_field", False)) and self.hotrwy.isChecked()); v.addWidget(self.hotrwy_own)
        hint(v, "Needs the setting above. AI flights at your own field appear on the runway only after you have taken off, never in the last ten minutes before your planned landing, "
                "and wait while you are on your way in to land.")
        self.hotrwy_own.setEnabled(self.hotrwy.isChecked())
        def _own_gate(on):
            self.hotrwy_own.setEnabled(bool(on))
            if not on:
                self.hotrwy_own.setChecked(False)
        self.hotrwy.toggled.connect(_own_gate)
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
                "that cannot attack at all is scrubbed (the war simulation leaves its target alone). Clear is what SQE always did.")
        from ..difficulty import SKILL_CHOICES as _SK
        self.skr, self.skb = QComboBox(), QComboBox()
        for cb_, key_ in ((self.skr, "ai_skill_red"), (self.skb, "ai_skill_blue")):
            for k, val in _SK.items():
                cb_.addItem(val, k)
            cb_.setCurrentIndex(max(0, cb_.findData(getattr(settings, key_, "level"))))
        row(v, "AI Skill, Red", self.skr)
        row(v, "AI Skill, Blue", self.skb)
        hint(v, "How good the AI pilots are, one setting for each side (Red's ground units follow the Red setting; Blue's base defences follow the Blue setting once it is set). "
                "Level default is what SQE always did: Red follows the difficulty level (Average, Good, High) and Blue's AI flights fly at High. DCS's top skill "
                "levels can feel like cheating; lower one side if it does. It changes the AI's skill only, not how the campaign's numbers run. It applies from your next mission.")
        self.splash = QCheckBox("Splash damage: blast damage around bomb and missile impacts (on by default)")
        self.splash.setChecked(bool(getattr(settings, "splash_damage", True))); v.addWidget(self.splash)
        hint(v, "DCS often leaves a vehicle a few metres from a bomb untouched. On: ground units near an air-to-ground weapon's impact take a blast "
                "of their own, scaled to the warhead and weaker with distance. Kills it causes count for the shooter.")
        # v0.41.18: AI landings
        _lm = [("Always skip", "always"), ("Skip at your home deck / field", "home"), ("Land for real", "never")]
        self.land_cv, self.land_af = QComboBox(), QComboBox()
        for cb_, key_, dflt_ in ((self.land_cv, "ai_land_carrier", "always"), (self.land_af, "ai_land_field", "never")):
            for lab_, val_ in _lm:
                cb_.addItem(lab_, val_)
            cb_.setCurrentIndex(max(0, cb_.findData(str(getattr(settings, key_, dflt_)))))
        _row = QFormLayout(); _row.addRow("AI landings, carrier", self.land_cv); _row.addRow("AI landings, airfields", self.land_af); v.addLayout(_row)
        hint(v, "Skip: AI flights going home are recovered short of the base (10 nm from the boat, 8 nm from a field), count as landed and leave the mission, "
                "so DCS's landing queue never runs them dry or fills your pattern. Your own wingmen are recovered too once you are back. Land for real: DCS landings.")
        self.ruins = QCheckBox("Ruins: show what earlier packages already hit (smoke and fire); struck flights fly home")
        self.ruins.setChecked(bool(getattr(settings, "ruins", True))); v.addWidget(self.ruins)
        hint(v, "Earlier packages in the same area that struck before your start leave smoking ruins (at most three sites, a few plumes each). The result is "
                "decided when you build the mission and applied at the debrief.")
        self.carc = QCheckBox("Carcasses: wrecks at damaged and destroyed ground sites near your route")
        self.carc.setChecked(bool(getattr(settings, "carcasses", True))); v.addWidget(self.carc)
        self.cw = QSpinBox(); self.cw.setRange(5, 100); self.cw.setSuffix(" % of a unit"); self.cw.setValue(int(getattr(settings, "carcass_weight_pct", 25)))
        row(v, "Wreck weight", self.cw)
        hint(v, "Wrecks are dead static objects: no AI, no weapons. Each counts this share of a unit toward the unit limit. When a mission is over the limit the "
                "furthest wrecks from your route are dropped first, before any flight is touched. Wrecks stay where they are from day to day.")
        v.addStretch(1)

        # ---- Mission build: merging and limits -----------------------------------------------------------------------------------
        v = page("Mission Build")
        self.merge = QComboBox(); self.merge.addItem("Off (one package per mission)", "off"); self.merge.addItem("Same area (targets inside the radius)", "area")
        self.merge.setCurrentIndex(1 if settings.merge_mode == "area" else 0)
        self.mmax = QSpinBox(); self.mmax.setRange(60, 400); self.mmax.setSuffix(" units max"); self.mmax.setValue(int(settings.merge_max_units))
        row(v, "Package merging", self.merge, self.mmax)
        hint(v, "Packages inside the radius that start within the time windows below fly in the same mission (AI-flown, one shared ground "
                "world and support). The waiting window shows the unit count so you can compare performance. The unit limit counts the whole mission, merged packages included: over it, returning flights go first, then the package that starts latest (a Fighter Sweep last), then wrecks are trimmed.")
        self.mrad = QSpinBox(); self.mrad.setRange(10, 150); self.mrad.setSingleStep(5); self.mrad.setSuffix(" nm"); self.mrad.setValue(int(getattr(settings, "merge_radius_nm", 15)))
        row(v, "Merge radius", self.mrad)
        hint(v, "Packages whose target is inside this circle fly in the same mission (within the time windows below). The circle is centred on your target, "
                "slid inward so it never hangs over the edge of the target area; your own target stays inside it. If the unit limit is exceeded, the package "
                "that starts latest drops first.")
        self.mback = QSpinBox(); self.mback.setRange(0, 30); self.mback.setSingleStep(5); self.mback.setSuffix(" min before"); self.mback.setValue(int(getattr(settings, "merge_back_min", 15)))
        row(v, "Earlier packages", self.mback)
        hint(v, "Packages that started up to this long before yours also fly, already airborne and underway when the mission starts. "
                "A package that has already struck is not flown to its target (see Ruins on the Campaign tab). 0 = only later packages.")
        self.mfwd = QSpinBox(); self.mfwd.setRange(0, 60); self.mfwd.setSingleStep(5); self.mfwd.setSuffix(" min after"); self.mfwd.setValue(int(getattr(settings, "merge_fwd_min", 30)))
        row(v, "Later packages", self.mfwd)
        hint(v, "Packages that start up to this long after yours also fly in the same mission (late-activated, they push at their own time). "
                "Over the unit limit, the package that starts latest is dropped first.")
        self.mpct = QSpinBox(); self.mpct.setRange(0, 100); self.mpct.setSuffix(" %"); self.mpct.setValue(int(settings.merge_enemy_pct))
        row(v, "Enemy air sum", self.mpct)
        hint(v, "When packages are folded in: enemy fighters = the biggest package's need + this share of every other folded package's need (100 = full sum).")
        self.feng = QSpinBox(); self.feng.setRange(0, 300); self.feng.setSuffix(" nm"); self.feng.setValue(int(settings.fighter_engage_nm))
        self.fmin = QSpinBox(); self.fmin.setRange(0, 120); self.fmin.setSuffix(" min after TOT"); self.fmin.setValue(int(settings.fighter_engage_minutes))
        row(v, "TARCAP / escort / sweep engage range", self.feng, self.fmin)
        hint(v, "How far AI TARCAPs, escorts, sweeps and SEAD go after a fighter, and for how long: the engage task ends this many minutes after the strike's TOT and they fly on home (alert pairs get 5 minutes more). 0 = unlimited. Your own flight is never limited (unless SQE was started with --ai-test).")
        v.addStretch(1)

        # ---- DCS integration: paths and the scripting patch ---------------------------------------------------------------------
        v = page("DCS integration")
        self.inst, self.saves = QLineEdit(S.native(settings.dcs_install)), QLineEdit(S.native(settings.dcs_saves))
        for label, line, ttl, h_ in (
                ("DCS", self.inst, "Select the DCS World install folder", "Install folder (only needed for the MissionScripting.lua patch)"),
                ("DCS Saves", self.saves, "Select your DCS Saved Games folder", r"e.g. C:\Users\You\Saved Games\DCS  or  ...\DCS_Server")):
            r = QHBoxLayout(); lb = QLabel(label); lb.setMinimumWidth(80); b = QPushButton("Browse")
            b.clicked.connect(lambda _=0, l=line, t_=ttl: _browse(self, l, t_))
            r.addWidget(lb); r.addWidget(line, 1); r.addWidget(b); v.addLayout(r)
            hint(v, h_)
        self.ms = QLabel(); v.addWidget(self.ms)
        self.autopatch = QCheckBox("Enable DCS scripting access while SQE is open (patches MissionScripting.lua at start, restores it on exit)")
        self.autopatch.setChecked(bool(settings.auto_patch_scripting)); v.addWidget(self.autopatch)
        hint(v, "Results need io/lfs enabled in MissionScripting.lua. A backup is saved next to the file. "
                "If SQE is closed before the mission ends, DCS can no longer write the results file.")
        v.addStretch(1)
        self.inst.textChanged.connect(self._refresh); self._refresh()

        # ---- Terrain scan ---------------------------------------------------------------------------------------------------------------
        v = page("Terrain scan")
        self.tm_status = QLabel(); self.tm_status.setWordWrap(True); v.addWidget(self.tm_status)
        self.tm_relief = QLabel(); self.tm_relief.setWordWrap(True); v.addWidget(self.tm_relief)
        self.tm_roads = QLabel(); self.tm_roads.setWordWrap(True); v.addWidget(self.tm_roads)
        self.shore = QSpinBox(); self.shore.setRange(300, 5000); self.shore.setSingleStep(100); self.shore.setSuffix(" m"); self.shore.setValue(int(getattr(settings, "shore_margin_m", 1500)))
        self.river = QSpinBox(); self.river.setRange(0, 1000); self.river.setSingleStep(50); self.river.setSuffix(" m rivers"); self.river.setValue(int(getattr(settings, "river_margin_m", 100)))
        row(v, "Shore margin", self.shore, self.river)
        self.tm = QLabel(); self.tm.setObjectName("small"); self.tm.setWordWrap(True); v.addWidget(self.tm)
        self.probe_btn = QPushButton("Create terrain scan mission"); self.probe_btn.clicked.connect(self._make_probe)
        self.recheck_btn = QPushButton("Re-check"); self.recheck_btn.clicked.connect(self._tm_refresh)
        r = QHBoxLayout(); r.addWidget(self.probe_btn); r.addWidget(self.recheck_btn); r.addStretch(1); v.addLayout(r)
        hint(v, "To measure the real map once: create the scan mission, start it in DCS (Fly), wait for COMPLETE, then Re-check. "
                "Without a scan SQE uses a rough built-in coastline (it can be 1-3 km off and has no rivers).")
        v.addStretch(1)
        self._tm_refresh()

        self.tabs.tabBar().moveTab(1, self.tabs.count() - 1)                  # Experimental last
        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel); bb.accepted.connect(self._save)
        bb.rejected.connect(self.reject); lay.addWidget(bb)
        if not settings.dcs_saves or not Path(settings.dcs_saves).exists():
            self.tabs.setCurrentIndex(3)                                  # first run: the paths are what is missing

    def _tm_refresh(self):
        from .. import terrainmask as _tmk, relief as _rl, roads as _rd
        _tmk.configure(self.s.sqe_dir if self.s.dcs_saves else None)
        _rl.configure(self.s.sqe_dir if self.s.dcs_saves else None)
        _rd.configure(self.s.sqe_dir if self.s.dcs_saves else None)
        sc = _tmk.scanned(self.s.sqe_dir if self.s.dcs_saves else None)
        have = ", ".join(f"{t} (scanned {dte})" for t, dte in sc) if sc else "none yet"
        ok = bool(_tmk.available())
        self.tm_status.setText(("Scanned: " + _tmk.info()) if ok else "Not scanned: ground sites use the coarse built-in coastline (up to 1-3 km off, no rivers).")
        self.tm_status.setStyleSheet(f"color: {theme.GREEN if ok else theme.AMBER}; font-weight: 700; font-size: 15px;")
        rok = bool(_rl.available())
        self.tm_relief.setText(("Ground height: " + _rl.info()) if rok else "Ground height: not scanned. Low flights use a flat estimate and the kneeboard has no minimum safe altitude (run the scan mission again).")
        self.tm_relief.setStyleSheet(f"color: {theme.GREEN if rok else theme.AMBER}; font-weight: 700; font-size: 15px;")
        dok = bool(_rd.available())
        self.tm_roads.setText(("Roads: " + _rd.info()) if dok else "Roads: not scanned. Columns and supply sites are not placed on roads (run the scan mission again).")
        self.tm_roads.setStyleSheet(f"color: {theme.GREEN if dok else theme.AMBER}; font-weight: 700; font-size: 15px;")
        self.tm.setText("Ground sites stay this far from the sea and lakes, and the second value from rivers and shallow water (rivers need the scan). "
                        f"Terrain scans on disk: {have}.")

    def _make_probe(self):
        create_scan_mission(self, self.s, self.saves.text())

    def _refresh(self):
        self.ms.setText("MissionScripting.lua: " + S.mission_scripting_status(self.inst.text()))

    def _save(self):
        self.s.dcs_install, self.s.dcs_saves = S.native(self.inst.text()), S.native(self.saves.text())
        self.s.hold_minutes = int(self.hold.value())
        self.s.takeoff_buffer_s = int(self.tob.value())
        self.s.ai_unlimited_fuel = self.fuel.isChecked()
        self.s.hot_ramp_scrambles = self.hotramp.isChecked()
        self.s.hot_runway_starts = self.hotrwy.isChecked()
        self.s.hot_runway_own_field = self.hotrwy.isChecked() and self.hotrwy_own.isChecked()
        self.s.merge_mode = self.merge.currentData(); self.s.merge_max_units = int(self.mmax.value())
        self.s.merge_enemy_pct = int(self.mpct.value())
        self.s.merge_back_min = int(self.mback.value()); self.s.merge_fwd_min = int(self.mfwd.value())
        self.s.merge_radius_nm = int(self.mrad.value())
        self.s.ruins = bool(self.ruins.isChecked())
        self.s.ecm_script = bool(self.ecm.isChecked())
        self.s.splash_damage = bool(self.splash.isChecked())
        self.s.ai_land_carrier = str(self.land_cv.currentData() or "always")
        self.s.ai_land_field = str(self.land_af.currentData() or "never")
        self.s.carcasses = bool(self.carc.isChecked()); self.s.carcass_weight_pct = int(self.cw.value())
        self.s.weather_mode = str(self.wxm.currentData())
        self.s.ai_skill_red = str(self.skr.currentData() or "level"); self.s.ai_skill_blue = str(self.skb.currentData() or "level")
        self.s.shore_margin_m = int(self.shore.value())
        self.s.river_margin_m = int(self.river.value())
        self.s.fighter_engage_nm = int(self.feng.value()); self.s.fighter_engage_minutes = int(self.fmin.value())
        self.s.f14_special_names = self.f14n.isChecked()
        self.s.auto_patch_scripting = self.autopatch.isChecked(); self.s.patch_asked = True
        if self.s.dcs_install:                                   # take effect now, not at the next start
            ok, msg = (S.patch_mission_scripting if self.s.auto_patch_scripting else S.restore_mission_scripting)(self.s.dcs_install)
            if not ok:
                QMessageBox.warning(self, "MissionScripting.lua", msg)
        pr = self.s.problems()
        if pr:
            QMessageBox.warning(self, "Check your paths", "\n".join(pr)); return
        self.s.save(); self.accept()


class WaitingDialog(QDialog):
    """FLY opens this. It polls SQE_state.json and shows live casualties for both sides."""
    def __init__(self, session, parent=None):
        super().__init__(parent); self.sess = session; self.data = None; self.manual = None
        self.setWindowTitle("Sortie in progress"); self.setMinimumSize(760, 560)
        p = session.state.pending; tl = p["timeline"]
        lay = QVBoxLayout(self); lay.setSpacing(12)
        t = QLabel("Sortie in progress"); t.setObjectName("title"); lay.addWidget(t)
        info = card(); lay.addWidget(info)
        il = info.layout()
        il.addWidget(QLabel(f"<b>{p['objective']}</b>"))
        il.addWidget(QLabel(f"Mission file: <b>SQE_Sortie.miz</b> in your DCS Missions folder. Start DCS, open it from the Missions list, and fly."))
        pd = p.get("package_dict", {}); cn = p.get("counts") or {}
        il.addWidget(QLabel(f"Mission start <b>{pd.get('start', '')}</b> local   |   {cn.get('groups', '?')} groups, {cn.get('units', '?')} units"))
        il.addWidget(QLabel(f"Launch {tl['launch']}   |   Marshal {tl['marshal']}   |   <b>PUSH {tl['push']}</b>   |   <b>TOT {tl['tot']}</b>   |   Egress {tl['egress']}"))
        for wmsg in (p.get("warnings") or []):                  # v0.41.133: the notes come last (the "Built with notes" popup is gone)
            wl = QLabel("Note: " + wmsg); wl.setWordWrap(True); wl.setStyleSheet(f"color:{theme.AMBER};"); il.addWidget(wl)
        self.status = QLabel("Waiting for DCS results..."); self.status.setObjectName("h2"); lay.addWidget(self.status)
        self.tbl = QTableWidget(0, 3); self.tbl.setHorizontalHeaderLabels(["This sortie", "Friendly", "Enemy"])
        self.tbl.verticalHeader().setVisible(False); self.tbl.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tbl.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch); self.tbl.setMinimumHeight(190)
        lay.addWidget(self.tbl)
        self.last = QLabel(""); self.last.setObjectName("small"); lay.addWidget(self.last)
        row = QHBoxLayout()
        self.b_man = QPushButton("Manually Submit..."); self.b_abort = QPushButton("Abort mission"); self.b_abort.setObjectName("danger")
        self.b_ok = QPushButton("Accept results"); self.b_ok.setObjectName("good"); self.b_ok.setEnabled(False)
        row.addWidget(self.b_man); row.addWidget(self.b_abort); row.addStretch(1); row.addWidget(self.b_ok); lay.addLayout(row)
        self.b_man.clicked.connect(self._manual); self.b_abort.clicked.connect(self._abort); self.b_ok.clicked.connect(self.accept)
        self.timer = QTimer(self); self.timer.timeout.connect(self._poll); self.timer.start(1000); self._dots = 0
        self._poll()

    def _fill(self, t):
        rows = [("Aircraft lost / total", f"{t['blue_air_lost']} / {t['blue_air_total']}", f"{t['red_air_lost']} / {t['red_air_total']}"),
                ("Ground units lost / total", f"{t['blue_ground_lost']} / {t['blue_ground_total']}", f"{t['red_ground_lost']} / {t['red_ground_total']}"),
                ("Landed / recovered", str(t["landed"]), str(t.get("red_landed", 0)))]
        self.tbl.setRowCount(len(rows))
        for i, r in enumerate(rows):
            for j, v in enumerate(r):
                it = QTableWidgetItem(v); it.setTextAlignment(Qt.AlignCenter if j else Qt.AlignLeft | Qt.AlignVCenter)
                self.tbl.setItem(i, j, it)

    def _poll(self):
        status, data, t = self.sess.poll(self.manual)
        self._dots = (self._dots + 1) % 4
        if status == "ok":
            self.data = data; self._fill(t); self.b_ok.setEnabled(True)
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


def create_scan_mission(parent, settings, saves_text: str = "") -> bool:
    """Write SQE_TerrainScan.miz into the DCS Missions folder and tell the user how to run it. Returns True when it was created."""
    from .. import terrainprobe
    saves = saves_text or settings.dcs_saves
    if not saves:
        QMessageBox.warning(parent, "Terrain scan", "Set the DCS Saved Games folder first."); return False
    try:
        from .. import theatres as _th
        tid = _th.active()["id"]
        p = terrainprobe.make_probe(Path(S.native(saves)) / "Missions" / ("SQE_TerrainScan.miz" if tid == "caucasus" else f"SQE_TerrainScan_{tid}.miz"))
    except Exception as ex:
        QMessageBox.warning(parent, "Terrain scan", f"Could not create the mission: {ex}"); return False
    QMessageBox.information(parent, "Terrain scan",
                            f"Created {p.name} in your DCS Missions folder (you start in a free Su-25T).\n\n1. Keep SQE open (it enables DCS scripting while open).\n"
                            "2. In DCS: Mission > Fly > Missions > My Missions > SQE_TerrainScan, then Fly.\n"
                            "3. Wait for the message 'SQE terrain scan COMPLETE' (about a minute; DCS may stutter), then leave the mission.\n"
                            "SQE uses the result the next time you open or start a campaign.")
    return True
