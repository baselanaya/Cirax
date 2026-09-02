"""Cirax desktop app — a real GUI over the same local conversion core.

Drag files in, pick a target, watch the queue. Uses the exact registry,
router and sandboxed executor as the CLI; nothing leaves the machine.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt, QThreadPool, Signal, QObject
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QGroupBox, QHBoxLayout,
    QHeaderView, QLabel, QListWidget, QMainWindow, QPushButton, QProgressBar,
    QTabWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from cirax.detect import detect
from cirax.executor import ConversionError, execute
from cirax.probe import probe_all
from cirax.registry import load
from cirax.router import find_plan, reachable


class JobSignals(QObject):
    step = Signal(str, int, int)      # engine chain, step index, step count
    done = Signal(str, bool, str)     # output path, ok, message


class Job(QObject):
    def __init__(self, reg, src: Path, dst: Path, plan, sandbox: str,
                 preset: str | None = None):
        super().__init__()
        self.reg, self.src, self.dst, self.plan = reg, src, dst, plan
        self.sandbox, self.preset = sandbox, preset
        self.signals = JobSignals()

    def run(self):
        try:
            steps = self.plan.steps
            for i, s in enumerate(steps):
                self.signals.step.emit(" -> ".join(self.plan.engines), i, len(steps))
            execute(self.plan, self.reg, self.src, self.dst, quiet=True,
                    sandbox=self.sandbox, preset=self.preset)
            self.signals.done.emit(str(self.dst), True, "done")
        except (ConversionError, RuntimeError) as exc:
            self.signals.done.emit(str(self.dst), False, str(exc)[-300:])


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.reg = load()
        probe_all(self.reg)
        self.pool = QThreadPool.globalInstance()
        self.setWindowTitle("Cirax — universal local conversion hub")
        self.resize(960, 640)
        self._dark()
        self._ui()

    def _dark(self):
        app = QApplication.instance()
        app.setStyle("Fusion")
        p = QPalette()
        bg, base, text = QColor(16, 20, 24), QColor(26, 33, 41), QColor(219, 228, 236)
        p.setColor(QPalette.Window, bg)
        p.setColor(QPalette.WindowText, text)
        p.setColor(QPalette.Base, base)
        p.setColor(QPalette.Text, text)
        p.setColor(QPalette.Button, base)
        p.setColor(QPalette.ButtonText, text)
        p.setColor(QPalette.Highlight, QColor(22, 104, 168))
        p.setColor(QPalette.HighlightedText, Qt.white)
        app.setPalette(p)

    def _ui(self):
        tabs = QTabWidget()
        self.setCentralWidget(tabs)

        convert = QWidget()
        v = QVBoxLayout(convert)

        title = QLabel("<b style='font-size:18pt'>● Cirax</b> "
                       "<span style='color:#7d8b99'>every format → every "
                       "format · 100% local · sandboxed</span>")
        v.addWidget(title)

        drop = QGroupBox("Files")
        dv = QVBoxLayout(drop)
        self.pick = QPushButton("Add files…")
        self.pick.clicked.connect(self._add_files)
        self.files = QListWidget()
        dv.addWidget(self.pick)
        dv.addWidget(self.files)
        v.addWidget(drop, stretch=2)

        opts = QGroupBox("Target")
        ov = QVBoxLayout(opts)
        self.target = QComboBox()
        groups: dict[str, list] = {}
        for f in self.reg.formats.values():
            if f.mime == "application/x-tree":
                continue
            groups.setdefault(f.domain, []).append(f)
        for dom in sorted(groups):
            for f in sorted(groups[dom], key=lambda x: x.ext):
                self.target.addItem(f"[{dom}] .{f.ext} — {f.name or f.mime}",
                                    f.mime)
        self.preset = QComboBox()
        self.preset.addItem("default")
        for e in self.reg.engines:
            for name in e.presets:
                self.preset.addItem(f"{name} ({e.name})")
        row = QHBoxLayout()
        row.addWidget(QLabel("Convert to:"))
        row.addWidget(self.target, stretch=3)
        row.addWidget(QLabel("Preset:"))
        row.addWidget(self.preset, stretch=2)
        self.sandbox = QCheckBox("Sandbox jobs (bwrap)")
        self.sandbox.setChecked(True)
        row.addWidget(self.sandbox)
        ov.addLayout(row)

        go = QHBoxLayout()
        self.go = QPushButton("Convert")
        self.go.setFixedHeight(36)
        self.go.clicked.connect(self._convert)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        go.addWidget(self.go)
        go.addWidget(self.progress, stretch=1)
        ov.addLayout(go)
        self.status = QLabel("ready")
        self.status.setStyleSheet("color:#7d8b99")
        ov.addWidget(self.status)
        v.addWidget(opts)
        tabs.addTab(convert, "Convert")

        engines = QWidget()
        ev = QVBoxLayout(engines)
        from PySide6.QtWidgets import QTableWidget
        t = QTableWidget(len(self.reg.engines), 4)
        t.setHorizontalHeaderLabels(["Engine", "Status", "Version", "Domains"])
        t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        t.setEditTriggers(QTableWidget.NoEditTriggers)
        for i, e in enumerate(self.reg.engines):
            t.setItem(i, 0, QTableWidgetItem(e.name))
            t.setItem(i, 1, QTableWidgetItem("installed" if e.installed
                                             else "missing"))
            t.setItem(i, 2, QTableWidgetItem(e.version or ""))
            t.setItem(i, 3, QTableWidgetItem(", ".join(e.categories)))
        ev.addWidget(t)
        tabs.addTab(engines, "Engines")

    def _add_files(self):
        names, _ = QFileDialog.getOpenFileNames(self, "Add files")
        for n in names:
            self.files.addItem(n)

    def _convert(self):
        if self.files.count() == 0:
            self.status.setText("add at least one file")
            return
        dst_mime = self.target.currentData()
        preset = self.preset.currentText().split(" (")[0]
        sandbox = "auto" if self.sandbox.isChecked() else "off"
        planned = []
        for i in range(self.files.count()):
            src = Path(self.files.item(i).text())
            mime, _ = detect(src, self.reg.ext_to_mime)
            plan = find_plan(self.reg, mime, dst_mime)
            if plan is None:
                self.status.setText(f"no route for {src.name} ({mime})")
                return
            planned.append((src, plan))
        self.go.setEnabled(False)
        self.progress.setRange(0, len(planned))
        self.progress.setValue(0)
        # executor preset support: pass through via closure
        for src, plan in planned:
            dst = src.with_suffix("." + self.reg.ext_for(dst_mime))
            job = Job(self.reg, src, dst, plan, sandbox,
                      None if preset == "default" else preset)
            job.signals.done.connect(lambda p, ok, msg: self._job_done(p, ok, msg))
            self.pool.start(lambda j=job: j.run())
        # simple sequential pool queue
        self._expected = len(planned)

    def _job_done(self, path, ok, msg):
        self.progress.setValue(min(self.progress.value() + 1,
                                   self.progress.maximum()))
        if not ok:
            self.status.setText(f"error: {msg}")
        else:
            self.status.setText(f"done: {path}")
        if self.progress.value() >= self.progress.maximum():
            self.go.setEnabled(True)


def main():
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
