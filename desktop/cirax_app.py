"""Cirax desktop app — multi-page glass UI over the same local core.

Pages: Convert · Watch · Serve · Engines · About. Every conversion runs
through the exact sandboxed pipeline as the CLI. Nothing leaves the machine.
"""

from __future__ import annotations

import faulthandler
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

from PySide6.QtCore import (
    QUrl, QPoint, Qt, QRunnable, QThreadPool, QTimer, Slot, Signal, QObject,
)
from PySide6.QtGui import (
    QColor, QDesktopServices, QDragEnterEvent, QDropEvent, QIcon, QPainter,
    QPalette, QPixmap,
)
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QCheckBox, QComboBox, QFileDialog,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMainWindow, QPushButton,
    QProgressBar, QSpinBox, QStackedWidget, QTableWidget, QTableWidgetItem,
    QTabWidget, QTextEdit, QVBoxLayout, QWidget,
)

from cirax import __version__
from cirax.detect import detect
from cirax.executor import ConversionError, execute
from cirax.probe import probe_all
from cirax.registry import load
from cirax.router import find_plan, reachable
from cirax import webui

STATE_DIR = Path.home() / ".local" / "state" / "cirax"

STYLE = """
QWidget { background: transparent; color: #dbe4ec; font-size: 13px; }
QLabel#header { font-size: 20px; font-weight: 700; color: #ffffff; }
QLabel#tagline { color: #8fa0b0; }
QLabel#status { color: #9fb0bf; }
QLabel#pagetitle { font-size: 16px; font-weight: 600; color: #dbe4ec; }
QFrame#card {
    background: rgba(23, 31, 40, 205);
    border: 1px solid rgba(90, 200, 250, 38);
    border-radius: 14px;
}
QFrame#sidebar { background: rgba(13, 17, 22, 215); border: none; }
QPushButton {
    background: rgba(26, 33, 41, 200); color: #dbe4ec;
    border: 1px solid #2a3844; border-radius: 9px; padding: 8px 14px;
}
QPushButton:hover { border-color: #5ac8fa; }
QPushButton#primary { background: #1668a8; border: none; font-weight: 600; }
QPushButton#primary:hover { background: #1b78c2; }
QPushButton#primary:disabled { background: #24313d; color: #6b7a88; }
QPushButton#nav {
    background: transparent; border: none; border-radius: 10px;
    padding: 10px 14px; text-align: left; color: #9fb0bf; font-size: 14px;
}
QPushButton#nav:hover { background: rgba(90, 200, 250, 25); color: #dbe4ec; }
QPushButton#nav:checked {
    background: rgba(22, 104, 168, 90); color: #ffffff; font-weight: 600;
}
QPushButton#open { color: #7fd18b; border: none; background: transparent; }
QComboBox, QLineEdit, QSpinBox {
    background: rgba(26, 33, 41, 210); border: 1px solid #2a3844;
    border-radius: 8px; padding: 6px 8px; color: #dbe4ec;
}
QTableWidget, QTextEdit { background: rgba(19, 26, 33, 190);
    border: 1px solid rgba(90, 200, 250, 30); border-radius: 10px;
    gridline-color: #202b34; }
QHeaderView::section { background: transparent; color: #8fa0b0;
                       border: none; padding: 6px; }
QProgressBar { background: rgba(26, 33, 41, 210); border: none;
               border-radius: 6px; height: 12px; color: transparent; }
QProgressBar::chunk { background: #1668a8; border-radius: 6px; }
QTabWidget::pane { border: none; }
QTabBar::tab { background: transparent; color: #7d8b99; padding: 8px 16px; }
QTabBar::tab:selected { color: #5ac8fa; border-bottom: 2px solid #5ac8fa; }
QCheckBox::indicator { width: 15px; height: 15px; }
QScrollBar:vertical { background: transparent; width: 10px; }
QScrollBar::handle:vertical { background: #2a3844; border-radius: 5px;
                              min-height: 30px; }
"""


def child_env() -> dict[str, str]:
    env = dict(os.environ)
    for key in ("LD_LIBRARY_PATH", "PYTHONPATH", "PYTHONHOME"):
        env.pop(key, None)
    return env


def open_path(path: Path) -> None:
    """Open with the system handler, but with a clean environment —
    inside an AppImage, QDesktopServices children inherit bundle libs and
    the viewer fails to read perfectly good files."""
    path = Path(path)
    if shutil.which("xdg-open"):
        subprocess.Popen(
            ["xdg-open", str(path)], env=child_env(),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True)
    else:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


class JobSignals(QObject):
    progress = Signal(str, int)
    done = Signal(str, bool, str)


class ConversionJob(QRunnable):
    def __init__(self, reg, src: Path, dst: Path, plan, sandbox: str,
                 preset: str | None):
        super().__init__()
        self.reg, self.src, self.dst, self.plan = reg, src, dst, plan
        self.sandbox, self.preset = sandbox, preset
        self.signals = JobSignals()
        self.setAutoDelete(True)

    @Slot()
    def run(self):
        total = max(len(self.plan.steps), 1)
        try:
            for i in range(total):
                self.signals.progress.emit(str(self.src), int(i / total * 100))
            execute(self.plan, self.reg, self.src, self.dst, quiet=True,
                    sandbox=self.sandbox, preset=self.preset)
            self.signals.progress.emit(str(self.src), 100)
            self.signals.done.emit(str(self.src), True, str(self.dst))
        except Exception as exc:  # noqa: BLE001
            self.signals.done.emit(str(self.src), False, str(exc)[-300:])


class Background(QWidget):
    """Gradient + soft color blobs — the backdrop the glass cards sit on."""

    def paintEvent(self, event):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        from PySide6.QtGui import QLinearGradient
        g = QLinearGradient(0, 0, self.width(), self.height())
        g.setColorAt(0.0, QColor("#0b0f14"))
        g.setColorAt(1.0, QColor("#121c27"))
        p.fillRect(self.rect(), g)
        for cx, cy, r, color in (
                (self.width() * 0.85, -40, 380, QColor(22, 104, 168, 46)),
                (self.width() * 0.08, self.height() * 0.95, 420,
                 QColor(90, 200, 250, 30))):
            p.setBrush(color)
            p.setPen(Qt.NoPen)
            p.drawEllipse(QPoint(int(cx), int(cy)), r, r)
        p.end()


def make_card(parent=None) -> tuple[QWidget, QVBoxLayout]:
    from PySide6.QtWidgets import QFrame
    frame = QFrame(parent)
    frame.setObjectName("card")
    v = QVBoxLayout(frame)
    v.setContentsMargins(16, 14, 16, 14)
    v.setSpacing(10)
    return frame, v


def page_title(text: str, sub: str = "") -> QWidget:
    w = QWidget()
    h = QHBoxLayout(w)
    h.setContentsMargins(0, 0, 0, 0)
    t = QLabel(text)
    t.setObjectName("pagetitle")
    h.addWidget(t)
    h.addStretch()
    if sub:
        s = QLabel(sub)
        s.setObjectName("tagline")
        h.addWidget(s)
    return w


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
        self._watch_timer: QTimer | None = None
        self._watch_state: dict = {}
        self._server = None
        self._server_thread = None
        self.setWindowTitle("Cirax — universal local conversion hub")
        self.resize(1080, 700)
        self.setAcceptDrops(True)
        self._icon()
        self._dark()
        self._ui()

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
        for role, color in ((QPalette.Window, QColor(11, 15, 20)),
                            (QPalette.Base, QColor(19, 26, 33)),
                            (QPalette.WindowText, QColor(219, 228, 236)),
                            (QPalette.Text, QColor(219, 228, 236)),
                            (QPalette.ButtonText, QColor(219, 228, 236)),
                            (QPalette.Highlight, QColor(22, 104, 168))):
            p.setColor(role, color)
        app.setPalette(p)
        app.setStyleSheet(STYLE)

    # ---------- shell ----------
    def _ui(self):
        central = QWidget()
        h = QHBoxLayout(central)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)

        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(200)
        sv = QVBoxLayout(sidebar)
        sv.setContentsMargins(14, 18, 14, 14)
        logo = QLabel("● Cirax")
        logo.setObjectName("header")
        sv.addWidget(logo)
        ver = QLabel(f"v{__version__}")
        ver.setObjectName("tagline")
        sv.addWidget(ver)
        sv.addSpacing(18)
        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.stack = QStackedWidget()
        pages = [("Convert", self._convert_page),
                 ("Watch", self._watch_page),
                 ("Serve", self._serve_page),
                 ("Engines", self._engines_page),
                 ("About", self._about_page)]
        for i, (name, builder) in enumerate(pages):
            btn = QPushButton(name)
            btn.setObjectName("nav")
            btn.setCheckable(True)
            btn.setChecked(i == 0)
            self.nav_group.addButton(btn, i)
            sv.addWidget(btn)
            self.stack.addWidget(builder())
        self.nav_group.idClicked.connect(self.stack.setCurrentIndex)
        sv.addStretch()
        quit_btn = QPushButton("Quit")
        quit_btn.clicked.connect(self.close)
        sv.addWidget(quit_btn)

        h.addWidget(sidebar)
        h.addWidget(self.stack, stretch=1)
        self.setCentralWidget(central)

    # ---------- pages ----------
    def _convert_page(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(22, 18, 22, 18)
        outer.addWidget(page_title("Convert", "sandboxed · offline"))
        card_w, v = make_card()
        outer.addWidget(card_w, stretch=1)

        self.drop = QLabel(
            "drag & drop files anywhere — or click to browse\n"
            "webp · heic · raw · docx · epub · pdf · mp4 · flac · zip · glb …")
        self.drop.setAlignment(Qt.AlignCenter)
        self.drop.setFixedHeight(84)
        self.drop.setStyleSheet(
            "border: 2px dashed #33424f; border-radius: 10px; color: #9fb0bf;")
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
        self.jobs.setMinimumHeight(180)
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
        return page

    def _watch_page(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(22, 18, 22, 18)
        outer.addWidget(page_title("Watch", "convert new files as they land"))
        card_w, v = make_card()
        outer.addWidget(card_w, stretch=1)

        row = QHBoxLayout()
        self.watch_dir = QLineEdit()
        self.watch_dir.setPlaceholderText("folder to watch…")
        btn = QPushButton("Browse…")
        btn.clicked.connect(self._pick_watch_dir)
        row.addWidget(self.watch_dir, stretch=1)
        row.addWidget(btn)
        v.addLayout(row)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Convert to:"))
        self.watch_target = QComboBox()
        for f in sorted(self.reg.formats.values(), key=lambda x: (x.domain, x.ext)):
            self.watch_target.addItem(f"[{f.domain}] .{f.ext}", f.mime)
        self.watch_target.setCurrentIndex(-1)
        row2.addWidget(self.watch_target, stretch=2)
        row2.addWidget(QLabel("Out:"))
        self.watch_out = QLineEdit()
        self.watch_out.setPlaceholderText("same folder")
        row2.addWidget(self.watch_out, stretch=1)
        self.watch_btn = QPushButton("Start watching")
        self.watch_btn.setObjectName("primary")
        self.watch_btn.clicked.connect(self._toggle_watch)
        row2.addWidget(self.watch_btn)
        v.addLayout(row2)

        self.watch_log = QTextEdit()
        self.watch_log.setReadOnly(True)
        v.addWidget(self.watch_log, stretch=1)
        self.watch_timer = QTimer(self)
        self.watch_timer.setInterval(2000)
        self.watch_timer.timeout.connect(self._watch_tick)
        return page

    def _serve_page(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(22, 18, 22, 18)
        outer.addWidget(page_title("Serve", "local web UI"))
        card_w, v = make_card()
        outer.addWidget(card_w)

        info = QLabel(
            "Run a small local web server (Python stdlib) with the same UI as "
            "this app in your browser — useful for headless boxes. Uploads "
            "convert through the sandboxed pipeline. Default: loopback only.")
        info.setWordWrap(True)
        v.addWidget(info)

        row = QHBoxLayout()
        row.addWidget(QLabel("Port:"))
        self.serve_port = QSpinBox()
        self.serve_port.setRange(1024, 65535)
        self.serve_port.setValue(8400)
        row.addWidget(self.serve_port)
        self.serve_btn = QPushButton("Start server")
        self.serve_btn.setObjectName("primary")
        self.serve_btn.setCheckable(True)
        self.serve_btn.clicked.connect(self._toggle_serve)
        row.addWidget(self.serve_btn)
        row.addStretch()
        v.addLayout(row)
        self.serve_status = QLabel("stopped")
        self.serve_status.setObjectName("tagline")
        v.addWidget(self.serve_status)
        v.addStretch()
        return page

    def _engines_page(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(22, 18, 22, 18)
        outer.addWidget(page_title("Engines", "what this machine can do"))
        card_w, v = make_card()
        outer.addWidget(card_w, stretch=1)
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
        v.addWidget(self.engines_table, stretch=1)
        self.counts = QLabel()
        self.counts.setObjectName("tagline")
        v.addWidget(self.counts)
        self._fill_engines()
        return page

    def _about_page(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(22, 18, 22, 18)
        outer.addWidget(page_title("About"))
        card_w, v = make_card()
        outer.addWidget(card_w, stretch=1)
        icon_label = QLabel()
        icon_pixmap = self.windowIcon().pixmap(96, 96)
        if not icon_pixmap.isNull():
            icon_label.setPixmap(icon_pixmap)
        icon_label.setAlignment(Qt.AlignCenter)
        v.addWidget(icon_label)
        head = QLabel("Cirax")
        head.setObjectName("header")
        head.setAlignment(Qt.AlignCenter)
        v.addWidget(head)
        body = QLabel(
            f"version {__version__} · MIT license\n\n"
            "every format → every format · 100% local · sandboxed\n\n"
            "Cirax routes between the best local engines (FFmpeg, libvips, "
            "ImageMagick, LibreOffice, Pandoc, Calibre, 7-Zip, qpdf, GDAL, "
            "Ollama…) so any file can become any other — without ever "
            "leaving your disk.\n\n"
            "github.com/baselanaya/Cirax · pypi.org/project/cirax")
        body.setWordWrap(True)
        body.setAlignment(Qt.AlignCenter)
        v.addWidget(body)
        v.addStretch()
        return page

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

    # ---------- convert ----------
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

        src_mimes = {}
        for p in self._pending:
            mime, _ = detect(Path(p), self.reg.ext_to_mime)
            src_mimes[p] = mime
        src_set = set(src_mimes.values())
        for p in self._pending:
            mime = src_mimes[p]
            for t_mime, plan in reachable(self.reg, mime).items():
                if t_mime in src_set:
                    continue
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
                         f"<span style='color:#8fa0b0'>({fmt.name or mime})</span>")
        self.detected_label.setText(
            "detected: " + " · ".join(parts) if parts
            else "detected formats will appear here")

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
            btn.clicked.connect(lambda _=False, p=out: open_path(p))
            self.jobs.setCellWidget(row, 4, btn)
            self.status.setText(f"done: {out.name}")
        else:
            self.jobs.setItem(row, 4, QTableWidgetItem(
                msg.splitlines()[-1][:90] if msg else "error"))
            self.status.setText("conversion failed — see the jobs table")

    # ---------- watch ----------
    def _pick_watch_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Folder to watch")
        if d:
            self.watch_dir.setText(d)

    def _toggle_watch(self):
        if self.watch_timer.isActive():
            self.watch_timer.stop()
            self.watch_btn.setText("Start watching")
            self._wlog("stopped")
            return
        d = Path(self.watch_dir.text() or "~").expanduser()
        if not d.is_dir():
            self._wlog("error: not a folder")
            return
        mime = self.watch_target.currentData()
        if not mime:
            self._wlog("error: pick a target format")
            return
        out = Path(self.watch_out.text() or d).expanduser()
        out.mkdir(parents=True, exist_ok=True)
        self._watch_state = {"dir": d, "out": out, "mime": mime,
                             "done": {}}
        self.watch_timer.start()
        self.watch_btn.setText("Stop")
        self._wlog(f"watching {d} → .{self.reg.ext_for(mime)}")

    def _wlog(self, msg: str):
        self.watch_log.append(msg)

    def _watch_tick(self):
        st = self._watch_state
        d: Path = st["dir"]
        for f in sorted(d.iterdir()):
            if not f.is_file() or f.name.startswith("."):
                continue
            if f.suffix.lower().lstrip(".") == \
                    self.reg.ext_for(st["mime"]).lower():
                continue
            mtime = f.stat().st_mtime
            if st["done"].get(f.name) == mtime or f.name in st["done"]:
                continue
            mime, _ = detect(f, self.reg.ext_to_mime)
            plan = find_plan(self.reg, mime, st["mime"])
            if plan is None:
                st["done"][f.name] = mtime
                self._wlog(f"skip {f.name} (no route)")
                continue
            dst = st["out"] / (f.stem + "." + self.reg.ext_for(st["mime"]))
            try:
                execute(plan, self.reg, f, dst, quiet=True)
                st["done"][f.name] = mtime
                self._wlog(f"done: {dst.name}")
            except ConversionError as exc:
                st["done"][f.name] = mtime
                self._wlog(f"error {f.name}: {str(exc)[-120:]}")

    # ---------- serve ----------
    def _toggle_serve(self):
        if self._server is not None:
            self._server.shutdown()
            self._server = None
            self.serve_btn.setText("Start server")
            self.serve_status.setText("stopped")
            return
        from http.server import ThreadingHTTPServer

        reg = self.reg
        handler = webui.make_handler(reg, type("A", (), {
            "quiet": True, "sandbox": "auto" if
            self.sandbox_box.isChecked() else "off"})())
        port = self.serve_port.value()

        class Server(ThreadingHTTPServer):
            daemon_threads = True

        self._server = Server(("127.0.0.1", port), handler)
        t = threading.Thread(target=self._server.serve_forever, daemon=True)
        t.start()
        self.serve_status.setText(
            f"serving http://127.0.0.1:{port} — open it in your browser")

    def closeEvent(self, event):
        if self._server is not None:
            self._server.shutdown()
        if self._watch_timer is not None and self.watch_timer.isActive():
            self.watch_timer.stop()
        self._crash_log.close()
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
