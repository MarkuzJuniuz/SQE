from __future__ import annotations
import json
import time
from pathlib import Path
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QCheckBox, QSpinBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QFrame, QHBoxLayout,
                               QLabel, QLineEdit, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem,
                               QTextBrowser, QVBoxLayout, QHeaderView)
from .. import settings as S
from ..aircraft import AIRCRAFT
from ..difficulty import LEVELS
from . import theme
from .widgets import card


def _browse(parent, line: QLineEdit, title: str):
    d = QFileDialog.getExistingDirectory(parent, title, line.text() or str(Path.home()))
    if d:
        line.setText(d)


class NewCampaignDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent); self.setWindowTitle("New Campaign"); self.setMinimumWidth(520)
        lay = QVBoxLayout(self); lay.setSpacing(12)
        t = QLabel("New Campaign"); t.setObjectName("title"); lay.addWidget(t)
        form = QFormLayout(); form.setSpacing(10)
        self.name = QLineEdit("Iron Tide"); form.addRow("Campaign name", self.name)
        self.ac = QComboBox()
        for k, s in AIRCRAFT.items():
            if s.player_flyable:
                self.ac.addItem(f"{s.display}  ({s.service}, {'carrier' if s.service == 'Navy' else 'land-based'})", k)
        form.addRow("You fly", self.ac)
        self.sqd = QComboBox(); form.addRow("Your squadron", self.sqd)
        self.ac.currentIndexChanged.connect(self._squads); self._squads()
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
        row = QHBoxLayout(); row.addWidget(self.month, 1); row.addWidget(self.day); row.addWidget(QLabel("2004"))
        form.addRow("Campaign starts", row)
        self.night = QCheckBox("Allow night sorties (otherwise missions are spread through daylight)")
        form.addRow("", self.night)
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
        for sid, label in squadron_options(self.ac.currentData()):
            self.sqd.addItem(label, sid)

    def values(self) -> dict:
        return {"name": self.name.text().strip() or "Campaign", "aircraft": self.ac.currentData(), "level": self.lvl.currentData(),
                "start_date": f"2004-{self.month.currentData():02d}-{self.day.value():02d}", "night_ops": self.night.isChecked(),
                "squadron": self.sqd.currentData()}


class SettingsDialog(QDialog):
    def __init__(self, settings: S.AppSettings, parent=None):
        super().__init__(parent); self.s = settings; self.setWindowTitle("Settings"); self.setMinimumWidth(680)
        lay = QVBoxLayout(self); lay.setSpacing(12)
        t = QLabel("Settings"); t.setObjectName("title"); lay.addWidget(t)
        self.inst, self.saves = QLineEdit(settings.dcs_install), QLineEdit(settings.dcs_saves)
        for label, line, ttl, hint in (
                ("DCS", self.inst, "Select the DCS World install folder", "Install folder (only needed for the MissionScripting.lua patch)"),
                ("DCS Saves", self.saves, "Select your DCS Saved Games folder", r"e.g. C:\Users\You\Saved Games\DCS  or  ...\DCS_Server")):
            row = QHBoxLayout(); lb = QLabel(label); lb.setMinimumWidth(80); b = QPushButton("Browse")
            b.clicked.connect(lambda _=0, l=line, t=ttl: _browse(self, l, t))
            row.addWidget(lb); row.addWidget(line, 1); row.addWidget(b); lay.addLayout(row)
            h = QLabel(hint); h.setObjectName("small"); lay.addWidget(h)
        row = QHBoxLayout(); lb = QLabel("Takeoff buffer"); lb.setMinimumWidth(80)
        self.tob = QSpinBox(); self.tob.setRange(-600, 900); self.tob.setSuffix(" s"); self.tob.setValue(int(settings.takeoff_buffer_s))
        row.addWidget(lb); row.addWidget(self.tob); row.addStretch(1); lay.addLayout(row)
        h = QLabel("Time between mission start and the takeoff time on your kneeboard (you start on the runway or cat, engines running). "
                   "Default 60 s. Negative means the plan expects you to be rolling before the clock starts, so you must make the time up in the air."); h.setObjectName("small"); h.setWordWrap(True); lay.addWidget(h)
        row = QHBoxLayout(); lb = QLabel("Marshal slack"); lb.setMinimumWidth(80)
        self.hold = QSpinBox(); self.hold.setRange(-10, 30); self.hold.setSuffix(" min"); self.hold.setValue(int(settings.hold_minutes))
        row.addWidget(lb); row.addWidget(self.hold); row.addStretch(1); lay.addLayout(row)
        h = QLabel("Time between reaching the marshal point and the PUSH. Smaller = less waiting. Negative means you must beat the "
                   "natural pace (afterburner time). AI flights adjust automatically."); h.setObjectName("small"); h.setWordWrap(True); lay.addWidget(h)
        self.fuel = QCheckBox("AI flights use the Retribution fuel trick (unlimited until the push, real fuel in the fight, unlimited again from egress)")
        self.fuel.setChecked(bool(settings.ai_unlimited_fuel)); lay.addWidget(self.fuel)
        row = QHBoxLayout(); lb = QLabel("Package merging"); lb.setMinimumWidth(120)
        self.merge = QComboBox(); self.merge.addItem("Off (one package per mission)", "off"); self.merge.addItem("Same area (fold up to 3 packages)", "area")
        self.merge.setCurrentIndex(1 if settings.merge_mode == "area" else 0)
        self.mmax = QSpinBox(); self.mmax.setRange(60, 400); self.mmax.setSuffix(" units max"); self.mmax.setValue(int(settings.merge_max_units))
        row.addWidget(lb); row.addWidget(self.merge, 1); row.addWidget(self.mmax); lay.addLayout(row)
        h = QLabel("Packages in the same area that start within 30 minutes after yours fly in the same mission (AI-flown, one shared ground "
                   "world and support). The waiting window shows the unit count so you can compare performance. Trimmed to the unit limit."); h.setObjectName("small"); h.setWordWrap(True); lay.addWidget(h)
        self.ms = QLabel(); lay.addWidget(self.ms)
        self.autopatch = QCheckBox("Enable DCS scripting access while SQE is open (patches MissionScripting.lua at start, restores it on exit)")
        self.autopatch.setChecked(bool(settings.auto_patch_scripting)); lay.addWidget(self.autopatch)
        note = QLabel("Results need io/lfs enabled in MissionScripting.lua (same approach as Liberation/Retribution). A backup is saved next to the file. "
                      "If SQE is closed before the mission ends, DCS can no longer write the results file.")
        note.setWordWrap(True); note.setObjectName("small"); lay.addWidget(note)
        self.inst.textChanged.connect(self._refresh); self._refresh()
        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel); bb.accepted.connect(self._save)
        bb.rejected.connect(self.reject); lay.addWidget(bb)

    def _refresh(self):
        self.ms.setText("MissionScripting.lua: " + S.mission_scripting_status(self.inst.text()))

    def _save(self):
        self.s.dcs_install, self.s.dcs_saves = self.inst.text().strip(), self.saves.text().strip()
        self.s.hold_minutes = int(self.hold.value())
        self.s.takeoff_buffer_s = int(self.tob.value())
        self.s.ai_unlimited_fuel = self.fuel.isChecked()
        self.s.merge_mode = self.merge.currentData(); self.s.merge_max_units = int(self.mmax.value())
        self.s.auto_patch_scripting = self.autopatch.isChecked()
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
        il.addWidget(QLabel(f"Mission start <b>{pd.get('start', '')}</b> local   |   {cn.get('groups', '?')} groups, {cn.get('units', '?')} units   |   seed {p.get('seed', '')}"))
        for wmsg in (p.get("warnings") or []):
            wl = QLabel("Note: " + wmsg); wl.setWordWrap(True); wl.setStyleSheet(f"color:{theme.AMBER};"); il.addWidget(wl)
        il.addWidget(QLabel(f"Launch {tl['launch']}   |   Marshal {tl['marshal']}   |   <b>PUSH {tl['push']}</b>   |   <b>TOT {tl['tot']}</b>   |   Egress {tl['egress']}"))
        self.status = QLabel("Waiting for DCS results..."); self.status.setObjectName("h2"); lay.addWidget(self.status)
        self.tbl = QTableWidget(0, 3); self.tbl.setHorizontalHeaderLabels(["This sortie", "Coalition (blue)", "Enemy (red)"])
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
                ("Landed / recovered", str(t["landed"]), "-")]
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
        h = QLabel("Meanwhile, elsewhere in the theatre"); h.setObjectName("h2"); lay.addWidget(h)
        mw = QTextBrowser()
        mw.setHtml("<br>".join(("<b>" + ln + "</b>") if i == 0 else ln for r in out["meanwhile"] for i, ln in enumerate(r["lines"])) or "Nothing else was tasked.")
        lay.addWidget(mw, 1)
        d = QLabel(f"Day {state.day} begins. A new tasking order is ready."); d.setObjectName("dim"); lay.addWidget(d)
        bb = QDialogButtonBox(QDialogButtonBox.Close); bb.rejected.connect(self.reject); bb.accepted.connect(self.accept)
        btn = bb.button(QDialogButtonBox.Close); btn.setText("Continue"); btn.setObjectName("primary")
        btn.clicked.connect(self.accept); lay.addWidget(bb)
