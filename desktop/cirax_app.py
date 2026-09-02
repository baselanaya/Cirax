"""Cirax desktop app — a real GUI over the same local conversion core.

Drag files anywhere, pick a target, watch the queue. Uses the exact
registry, router and sandboxed executor as the CLI; nothing leaves the
machine. The target list is built from what the dropped files actually
are — you only ever see formats they can truly become. Workers are
QRunnables that can never take the app down; native crashes leave a
faulthandler trace in ~/.local/state/cirax/.
"""

from __future__ import annotations

import faulthandler
import sys
from pathlib import Path

from PySide6.QtCore import QUrl, Qt, QRunnable, QThreadPool, Slot, Signal, QObject
from PySide6.QtGui import (
    QColor, QDesktopServices, QDragEnterEvent, QDropEvent, QIcon, QPalette,
)
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox,
    QFileDialog, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMainWindow,
    QPushButton, QProgressBar, QTableWidget, QTableWidgetItem, QTabWidget,
    QVBoxLayout, QWidget,
)

from cirax.detect import detect
from cirax.executor import ConversionError, execute
from cirax.probe import probe_all
from cirax.registry import load
from cirax.router import find_plan, reachable

STATE_DIR = Path.home() / ".local" / "state" / "cirax"

STYLE = """
QMainWindow, QWidget { background: #101418; color: #dbe4ec; font-size: 13px; }
QLabel#header { font-size: 19px; font-weight: 700; color: #5ac8fa; }
QLabel#tagline { color: #7d8b99; }
QLabel#status { color: #9fb0bf; }
QGroupBox {
    border: 1px solid #202b34; border-radius: 10px; margin-top: 12px;
    padding: 12px 10px 10px 10px; background: #131a21;
}
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 4px;
                   color: #9fb0bf; }
QPushButton {
    background: #1a2129; color: #dbe4ec; border: 1px solid #2a3844;
    border-radius: 8px; padding: 8px 14px;
}
QPushButton:hover { border-color: #5ac8fa; }
QPushButton#primary { background: #1668a8; border: none; font-weight: 600; }
QPushButton#primary:disabled { background: #24313d; color: #6b7a88; }
QPushButton#open { color: #7fd18b; border: none; background: transparent; }
QComboBox, QLineEdit {
    background: #1a2129; border: 1px solid #2a3844; border-radius: 8px;
    padding: 6px 8px; color: #dbe4ec;
}
QTableWidget { background: #131a21; border: 1px solid #202b34;
               border-radius: 10px; gridline-color: #202b34; }
QHeaderView::section { background: #101418; color: #7d8b99;
                       border: none; padding: 6px; }
QProgressBar { background: #1a2129; border: none; border-radius: 6px;
               height: 12px; text-align: center; color: transparent; }
QProgressBar::chunk { background: #1668a8; border-radius: 6px; }
QTabWidget::pane { border: none; }
QTabBar::tab { background: transparent; color: #7d8b99; padding: 8px 16px; }
QTabBar::tab:selected { color: #5ac8fa; border-bottom: 2px solid #5ac8fa; }
QCheckBox::indicator { width: 15px; height: 15px; }
"""


class JobSignals(QObject):
    progress = Signal(str, int)          # src path, percent (0-100)
    done = Signal(str, bool, str)        # src path, ok, message


class ConversionJob(QRunnable):
    """Runs one plan in the thread pool; never lets an exception escape."""

    def __init__(self, reg, src: Path, dst: Path, plan, sandbox: str,
                 preset: str | None):
        super().__init__()
        self.reg, self.src, self.dst, self.plan = reg, src, dst, plan
        self.sandbox, self.preset = sandbox, preset
        self.signals = JobSignals()
        self.setAutoDelete(True)

    @Slot()
    def run(self):  # worker thread
        total = max(len(self.plan.steps), 1)
        try:
            for i in range(total):
                self.signals.progress.emit(str(self.src), int(i / total * 100))
            execute(self.plan, self.reg, self.src, self.dst, quiet=True,
                    sandbox=self.sandbox, preset=self.preset)
            self.signals.progress.emit(str(self.src), 100)
            self.signals.done.emit(str(self.src), True, str(self.dst))
        except Exception as exc:  # noqa: BLE001 - GUI must survive anything
            self.signals.done.emit(str(self.src), False, str(exc)[-300:])


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.reg = load()
        probe_all(self.reg)
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        self._crash_log = open(STATE_DIR / "crash.log", "w")
        faulthandler.enable(self._crash_log)
        self.pool = QThreadPool.globalInstance()
        self.pool.setMaxThreadCount(max(2, self.pool.maxThreadCount() // 2))
        self._pending: list[str] = []
        self._reach: dict[str, dict] = {}
        self._row_by_src: dict[str, int] = {}
        self.setWindowTitle("Cirax — universal local conversion hub")
        self.resize(1020, 680)
        self.setAcceptDrops(True)
        self._icon()
        self._dark()
        self._ui()

    # ---------- look ----------
    def _icon(self):
        cands = [Path("/usr/share/icons/hicolor/256x256/apps/cirax.png")]
        if hasattr(sys, "_MEIPASS"):
            cands.insert(0, Path(sys._MEIPASS) / "cirax.png")  # type: ignore
        cands.append(Path(__file__).resolve().parent.parent / "assets" / "cirax.png")
        for cand in cands:
            if cand.exists():
                self.setWindowIcon(QIcon(str(cand)))
                break

    def _dark(self):
        app = QApplication.instance()
        app.setStyle("Fusion")
        p = app.palette()
        for role, color in ((QPalette.Window, QColor(16, 20, 24)),
                            (QPalette.Base, QColor(19, 26, 33)),
                            (QPalette.WindowText, QColor(219, 228, 236)),
                            (QPalette.Text, QColor(219, 228, 236)),
                            (QPalette.ButtonText, QColor(219, 228, 236)),
                            (QPalette.Highlight, QColor(22, 104, 168))):
            p.setColor(role, color)
        app.setPalette(p)
        app.setStyleSheet(STYLE)

    # ---------- layout ----------
    def _ui(self):
        tabs = QTabWidget()
        self.setCentralWidget(tabs)
        tabs.addTab(self._convert_tab(), "Convert")
        tabs.addTab(self._engines_tab(), "Engines")

    def _convert_tab(self) -> QWidget:
        root = QWidget()
        v = QVBoxLayout(root)
        v.setContentsMargins(18, 14, 18, 14)
        v.setSpacing(10)

        header = QHBoxLayout()
        head = QLabel("● Cirax")
        head.setObjectName("header")
        tag = QLabel("every format → every format · 100% local · sandboxed")
        tag.setObjectName("tagline")
        header.addWidget(head)
        header.addWidget(tag)
        header.addStretch()
        v.addLayout(header)

        self.drop = QLabel(
            "drag & drop files anywhere — or click to browse\n"
            "webp · heic · raw · docx · epub · pdf · mp4 · flac · zip · glb …")
        self.drop.setAlignment(Qt.AlignCenter)
        self.drop.setFixedHeight(88)
        self.drop.setStyleSheet(
            "border: 2px dashed #33424f; border-radius: 10px; color: #9fb0bf;"
            "background: #131a21;")
        v.addWidget(self.drop)
        self.drop.mousePressEvent = lambda e: self._add_files()

        self.files_list = QLabel("<i style='color:#5c6b78'>no files yet</i>")
        self.files_list.setWordWrap(True)
        v.addWidget(self.files_list)

        self.detected_label = QLabel("")
        self.detected_label.setObjectName("tagline")
        self.detected_label.setWordWrap(True)
        v.addWidget(self.detected_label)

        row = QHBoxLayout()
        row.addWidget(QLabel("Convert to:"))
        self.target = QComboBox()
        self.target.setEnabled(False)
        self.target.addItem("add files to see possible targets", "")
        self.target.currentIndexChanged.connect(self._target_hint)
        self.target.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        row.addWidget(self.target, stretch=1)
        v.addLayout(row)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Preset:"))
        self.preset = QComboBox()
        self.preset.addItem("default")
        for e in self.reg.engines:
            for name in e.presets:
                self.preset.addItem(f"{name} ({e.name})")
        row2.addWidget(self.preset, stretch=2)
        self.sandbox_box = QCheckBox("Sandbox")
        self.sandbox_box.setChecked(True)
        self.sandbox_box.setToolTip("bubblewrap jail: no network, read-only fs")
        row2.addWidget(self.sandbox_box)
        row2.addStretch()
        v.addLayout(row2)

        self.jobs = QTableWidget(0, 5)
        self.jobs.setHorizontalHeaderLabels(
            ["File", "Route", "Progress", "Status", ""])
        self.jobs.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.jobs.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.jobs.verticalHeader().setVisible(False)
        self.jobs.setEditTriggers(QTableWidget.NoEditTriggers)
        self.jobs.setSelectionMode(QTableWidget.NoSelection)
        v.addWidget(self.jobs, stretch=1)

        go = QHBoxLayout()
        self.go = QPushButton("Convert")
        self.go.setObjectName("primary")
        self.go.setFixedHeight(38)
        self.go.setEnabled(False)
        self.go.clicked.connect(self._convert)
        self.status = QLabel("ready")
        self.status.setObjectName("status")
        go.addWidget(self.go)
        go.addWidget(self.status, stretch=1)
        v.addLayout(go)
        return root

    def _engines_tab(self) -> QWidget:
        root = QWidget()
        v = QVBoxLayout(root)
        v.setContentsMargins(18, 14, 18, 14)
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("filter engines…")
        self.filter.textChanged.connect(self._fill_engines)
        v.addWidget(self.filter)
        self.engines_table = QTableWidget(0, 4)
        self.engines_table.setHorizontalHeaderLabels(
            ["Engine", "Status", "Version", "Domains"])
        self.engines_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch)
        self.engines_table.setEditTriggers(QTableWidget.NoEditTriggers)
        v.addWidget(self.engines_table)
        self.counts = QLabel()
        self.counts.setObjectName("tagline")
        v.addWidget(self.counts)
        self._fill_engines()
        return root

    def _fill_engines(self):
        needle = self.filter.text().lower()
        rows = [e for e in self.reg.engines
                if needle in e.name.lower() or needle in e.binary.lower()]
        inst = sum(1 for e in rows if e.installed)
        self.engines_table.setRowCount(len(rows))
        for i, e in enumerate(rows):
            self.engines_table.setItem(i, 0, QTableWidgetItem(e.name))
            self.engines_table.setItem(i, 1, QTableWidgetItem(
                "installed" if e.installed else "missing"))
            self.engines_table.setItem(i, 2, QTableWidgetItem(e.version or ""))
            self.engines_table.setItem(i, 3, QTableWidgetItem(
                ", ".join(e.categories)))
        self.counts.setText(f"{inst}/{len(rows)} engines shown · "
                            f"{len(self.reg.formats)} formats in vocabulary")

    # ---------- detected formats -> smart target list ----------
    def _refresh_targets(self):
        self.target.clear()
        self._reach = {}
        if not self._pending:
            self.target.addItem("add files to see possible targets", "")
            self.target.setEnabled(False)
            self.go.setEnabled(False)
            self._target_hint()
            return
        self.target.setEnabled(True)

        src_mimes: dict[str, str] = {}
        for p in self._pending:
            mime, _ = detect(Path(p), self.reg.ext_to_mime)
            src_mimes[p] = mime
        src_set = set(src_mimes.values())
        for p in self._pending:
            mime = src_mimes[p]
            for t_mime, plan in reachable(self.reg, mime).items():
                if t_mime in src_set:
                    continue  # never offer converting a file to itself
                cur = self._reach.get(t_mime)
                if cur is None or plan.cost < cur["plan"].cost:
                    self._reach[t_mime] = {"plan": plan}

        by_domain: dict[str, list] = {}
        for mime, info in self._reach.items():
            plan = info["plan"]
            dom = mime.split("/")[0]
            ext = self.reg.ext_for(mime)
            loss = "lossless" if plan.lossless else "lossy"
            by_domain.setdefault(dom, []).append(
                (plan.cost, ext, mime, " → ".join(plan.engines), loss))
        n = 0
        for dom in sorted(by_domain):
            for cost, ext, mime, chain, loss in sorted(by_domain[dom]):
                self.target.addItem(f"[{dom}] .{ext}   ·   via {chain}   ·   "
                                    f"{loss}", mime)
                n += 1
        if n == 0:
            self.target.addItem("no conversion targets found", "")
            self.go.setEnabled(False)
        else:
            self.go.setEnabled(True)
        self._target_hint()

    def _target_hint(self):
        mime = self.target.currentData()
        info = self._reach.get(mime) if mime else None
        if info:
            plan = info["plan"]
            loss = "lossless" if plan.lossless else "lossy"
            self.status.setText(f"route: {' → '.join(plan.engines)} · {loss}")
        elif not self._pending:
            self.status.setText("ready")

    # ---------- drag & drop ----------
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        self._add_paths([u.toLocalFile() for u in event.mimeData().urls()
                         if u.isLocalFile()])

    def _add_files(self):
        names, _ = QFileDialog.getOpenFileNames(self, "Add files")
        self._add_paths(names)

    def _add_paths(self, names):
        self._pending = [p for p in self._pending if Path(p).exists()]
        for n in names:
            if n and n not in self._pending:
                self._pending.append(n)
        if self._pending:
            shown = ", ".join(Path(p).name for p in self._pending[:6])
            extra = f" … +{len(self._pending) - 6}" if len(self._pending) > 6 else ""
            self.files_list.setText(
                f"<b>{len(self._pending)}</b> file(s): {shown}{extra}")
        self._refresh_targets()
        self._refresh_detected()

    def _refresh_detected(self):
        parts = []
        for p in self._pending:
            mime, _ = detect(Path(p), self.reg.ext_to_mime)
            fmt = self.reg.formats.get(mime)
            parts.append(f"<b>{Path(p).name}</b> "
                         f"<span style='color:#7d8b99'>({fmt.name or mime})</span>")
        self.detected_label.setText(
            "detected: " + " · ".join(parts) if parts
            else "detected formats will appear here")

    # ---------- conversion ----------
    def _convert(self):
        paths = [Path(p) for p in self._pending]
        if not paths:
            self.status.setText("add at least one file")
            return
        dst_mime = self.target.currentData()
        if not dst_mime:
            self.status.setText("pick a target format first")
            return
        preset = self.preset.currentText().split(" (")[0]
        preset = None if preset == "default" else preset
        sandbox = "auto" if self.sandbox_box.isChecked() else "off"

        self.jobs.setRowCount(0)
        self._row_by_src = {}
        queued = 0
        for src in paths:
            mime, _ = detect(src, self.reg.ext_to_mime)
            plan = find_plan(self.reg, mime, dst_mime)
            if plan is None:
                self.status.setText(f"no route for {src.name} ({mime})")
                continue
            dst = src.with_suffix("." + self.reg.ext_for(dst_mime))
            if dst == src:
                self.status.setText(f"skip {src.name}: pick a different target")
                continue
            row = self.jobs.rowCount()
            self.jobs.insertRow(row)
            self.jobs.setItem(row, 0, QTableWidgetItem(src.name))
            self.jobs.setItem(row, 1, QTableWidgetItem(" → ".join(plan.engines)))
            bar = QProgressBar()
            bar.setRange(0, 100)
            self.jobs.setCellWidget(row, 2, bar)
            self.jobs.setItem(row, 3, QTableWidgetItem("queued"))
            self._row_by_src[str(src)] = row
            job = ConversionJob(self.reg, src, dst, plan, sandbox, preset)
            job.signals.progress.connect(self._job_progress)
            job.signals.done.connect(self._job_done)
            self.pool.start(job)
            queued += 1
        self.status.setText(f"converting {queued} file(s)…" if queued
                            else "nothing to convert")

    def _row_for(self, src_path: str) -> int | None:
        row = self._row_by_src.get(src_path)
        if row is not None and row < self.jobs.rowCount():
            return row
        return None

    def _job_progress(self, src_path: str, pct: int):
        row = self._row_for(src_path)
        if row is not None:
            bar = self.jobs.cellWidget(row, 2)
            if bar:
                bar.setValue(pct)

    def _job_done(self, src_path: str, ok: bool, msg: str):
        row = self._row_for(src_path)
        if row is None:
            return
        self.jobs.setItem(row, 3, QTableWidgetItem("done" if ok else "failed"))
        self.jobs.item(row, 3).setForeground(
            QColor("#7fd18b") if ok else QColor("#ff8484"))
        if ok:
            out = Path(msg)
            self.jobs.setItem(row, 4, QTableWidgetItem(out.name))
            btn = QPushButton("open")
            btn.setObjectName("open")
            btn.setToolTip(str(out))
            btn.clicked.connect(lambda _=False, p=out: self._open(p))
            self.jobs.setCellWidget(row, 4, btn)
            self.status.setText(f"done: {out.name}")
        else:
            self.jobs.setItem(row, 4, QTableWidgetItem(
                msg.splitlines()[-1][:90] if msg else "error"))
            self.status.setText("conversion failed — see the jobs table")

    def _open(self, path: Path):
        if not path.exists() or path.stat().st_size == 0:
            self.status.setText(f"result missing or empty: {path}")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


def main():
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
