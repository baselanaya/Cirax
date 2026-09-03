"""Cirax desktop app — the interchange.

Files are passengers, engines are transit lines, pivot formats are
interchanges. Drop a file and the app walks you through the journey:
detect → departures → destination. Same core as the CLI: registry,
router, sandboxed executor — nothing leaves the machine.
"""

from __future__ import annotations

import faulthandler
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path

from PySide6.QtCore import (
    QUrl, QPoint, Qt, QRunnable, QThreadPool, QTimer, Slot, Signal, QObject,
)
from PySide6.QtGui import (
    QColor, QDesktopServices, QDragEnterEvent, QDropEvent, QIcon, QPainter,
    QPalette,
)
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QCheckBox, QComboBox, QFrame,
    QFileDialog, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QMainWindow, QPushButton, QProgressBar, QScrollArea, QSpinBox,
    QStackedLayout, QStackedWidget, QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout,
    QWidget,
)

from cirax import __version__
from cirax.detect import detect
from cirax.executor import ConversionError, execute
from cirax.paths import state_dir
from cirax.probe import probe_all
from cirax.registry import load
from cirax.router import find_plan, reachable
from cirax import webui

STATE_DIR = state_dir()

# ── design tokens ────────────────────────────────────────────────────────
INK = "#0d1118"
SIGNAL = "#56c8f5"
BRASS = "#d9a441"
ROSE = "#f27e7e"
MIST = "#93a4b3"

DOMAIN_LINES = {
    "image": "#f27e9b",
    "video": "#b07ef2",
    "audio": "#f2b07e",
    "document": "#7ed4f2",
    "spreadsheet": "#7ef2b0",
    "presentation": "#f2d47e",
    "ebook": "#c97ef2",
    "archive": "#f27ee0",
    "data": "#7ef2d4",
    "font": "#d4f27e",
    "model3d": "#9bf27e",
    "subtitle": "#f29b7e",
    "gis": "#7ea0f2",
    "disk": "#8fa0b0",
    "compression": "#aab4be",
}

MONO = "'Cascadia Mono', 'JetBrains Mono', 'Fira Code', monospace"
UI_FONT = "'Segoe UI Variable', 'Segoe UI', 'Cantarell', 'Ubuntu', sans-serif"

STYLE = f"""
QWidget {{ background: transparent; color: #dbe4ec; font-size: 13px;
           font-family: {UI_FONT}; }}
QLabel#header {{ font-size: 20px; font-weight: 700; color: #ffffff;
                 letter-spacing: 1px; }}
QLabel#tagline {{ color: {MIST}; }}
QLabel#status {{ color: #9fb0bf; }}
QLabel#pagetitle {{ font-size: 16px; font-weight: 600; }}
QLabel#stepline {{ color: {MIST}; font-size: 11px; letter-spacing: 2px; }}
QLabel#destext {{ font-family: {MONO}; font-size: 17px; font-weight: 700; }}
QLabel#chain {{ font-family: {MONO}; font-size: 11px; color: {MIST}; }}
QLabel#board {{
    font-family: {MONO}; font-size: 13px; color: #dbe4ec;
    background: rgba(13, 17, 24, 200); border: 1px solid #233041;
    border-radius: 10px; padding: 10px 12px;
}}
QFrame#card {{
    background: rgba(23, 31, 40, 200); border: 1px solid #233041;
    border-radius: 12px;
}}
QFrame#destcard {{
    background: rgba(19, 26, 33, 215); border: 1px solid #26333f;
    border-radius: 10px;
}}
QFrame#destcard:hover {{
    border: 1px solid {SIGNAL}; background: rgba(28, 38, 48, 235);
}}
QFrame#sidebar {{ background: rgba(10, 13, 18, 230); border: none; }}
QPushButton {{
    background: rgba(26, 33, 41, 200); color: #dbe4ec;
    border: 1px solid #2a3844; border-radius: 9px; padding: 8px 14px;
}}
QPushButton:hover {{ border-color: {SIGNAL}; }}
QPushButton#primary {{ background: #1668a8; border: none; font-weight: 600; }}
QPushButton#primary:hover {{ background: #1b78c2; }}
QPushButton#primary:disabled {{ background: #24313d; color: #6b7a88; }}
QPushButton#nav {{
    background: transparent; border: none; border-radius: 10px;
    padding: 10px 14px; text-align: left; color: {MIST}; font-size: 14px;
}}
QPushButton#nav:hover {{ background: rgba(86, 200, 245, 25);
                        color: #dbe4ec; }}
QPushButton#nav:checked {{ background: rgba(22, 104, 168, 90);
                           color: #ffffff; font-weight: 600; }}
QPushButton#open {{ color: #7fd18b; border: none; background: transparent; }}
QPushButton#back {{ color: {MIST}; border: none; background: transparent;
                    font-weight: 600; }}
QComboBox, QLineEdit {{
    background: rgba(26, 33, 41, 210); border: 1px solid #2a3844;
    border-radius: 8px; padding: 6px 8px; color: #dbe4ec;
}}
QTableWidget {{ background: rgba(19, 26, 33, 190);
                border: 1px solid #233041; border-radius: 10px;
                gridline-color: #202b34; }}
QHeaderView::section {{ background: transparent; color: {MIST};
                        border: none; padding: 6px; }}
QProgressBar {{ background: rgba(26, 33, 41, 210); border: none;
                border-radius: 6px; height: 12px; color: transparent; }}
QProgressBar::chunk {{ background: {SIGNAL}; border-radius: 6px; }}
QCheckBox::indicator {{ width: 15px; height: 15px; }}
QScrollBar:vertical {{ background: transparent; width: 10px; }}
QScrollBar::handle:vertical {{ background: #2a3844; border-radius: 5px;
                               min-height: 30px; }}
"""


def line_color(domain: str) -> str:
    return DOMAIN_LINES.get(domain, "#8fa0b0")


class JobSignals(QObject):
    progress = Signal(str, int)
    done = Signal(str, bool, str)


class WatchSignals(QObject):
    log = Signal(str)


class WatchJob(QRunnable):
    """One watched-file conversion, off the UI thread."""

    def __init__(self, fn):
        super().__init__()
        self.fn = fn
        self.setAutoDelete(True)

    @Slot()
    def run(self):
        try:
            self.fn()
        except Exception as exc:  # noqa: BLE001
            print(f"watch job error: {exc}", file=sys.stderr)


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


def open_path(path: Path) -> None:
    path = Path(path)
    env = {k: v for k, v in os.environ.items()
           if k not in ("LD_LIBRARY_PATH", "PYTHONPATH", "PYTHONHOME")}
    if sys.platform == "win32":
        os.startfile(str(path))  # noqa: S606
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)], env=env)
    elif shutil.which("xdg-open"):
        subprocess.Popen(["xdg-open", str(path)], env=env,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
    else:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


def route_board_html(plan) -> str:
    """The signature element: the journey as a transit board."""
    chips = [f'<span style="color:{SIGNAL}">.{plan.src.split("/")[-1]}</span>']
    for step in plan.steps:
        chips.append('<span style="color:#3d4f60">&nbsp;──▸&nbsp;</span>')
        chips.append(f'<span style="background:rgba(26,33,41,220);'
                     f'border-radius:4px; padding:1px 6px;">'
                     f'{step.engine.name}</span>')
    chips.append('<span style="color:#3d4f60">&nbsp;──▸&nbsp;</span>')
    chips.append(f'<span style="color:{BRASS}">.{plan.dst.split("/")[-1]}</span>')
    return "".join(chips)


class Background(QWidget):
    """Painted gradient + soft blobs — the backdrop the glass cards sit on."""

    def paintEvent(self, event):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        from PySide6.QtGui import QLinearGradient
        g = QLinearGradient(0, 0, self.width(), self.height())
        g.setColorAt(0.0, QColor("#0b0f14"))
        g.setColorAt(1.0, QColor("#121c27"))
        p.fillRect(self.rect(), g)
        for cx, cy, r, color in (
                (self.width() * 0.85, -40, 380, QColor(22, 104, 168, 64)),
                (self.width() * 0.08, self.height() * 0.95, 420,
                 QColor(90, 200, 250, 44))):
            p.setBrush(color)
            p.setPen(Qt.NoPen)
            p.drawEllipse(QPoint(int(cx), int(cy)), r, r)
        p.end()


def make_card(parent=None) -> tuple[QWidget, QVBoxLayout]:
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


def _mono_font():
    from PySide6.QtGui import QFont
    f = QFont()
    f.setFamilies(["Cascadia Mono", "JetBrains Mono", "Fira Code",
                   "Consolas", "monospace"])
    return f


class DestinationCard(QFrame):
    """A departure on the board: one place the dropped files can go."""

    clicked = Signal(str)

    def __init__(self, ext: str, mime: str, domain: str, chain: str,
                 loss: str):
        super().__init__()
        self.setObjectName("destcard")
        self.mime = mime
        self.search_text = f".{ext} {domain} {chain} {loss}".lower()
        color = DOMAIN_LINES.get(domain, "#8fa0b0")
        self.setStyleSheet(
            f'QFrame#destcard {{ border-left: 3px solid {color}; }}')
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(220, 84)
        self.setToolTip(f"convert to {mime}")

        v = QVBoxLayout(self)
        v.setContentsMargins(12, 10, 10, 10)
        v.setSpacing(4)

        top = QHBoxLayout()
        top.setSpacing(6)
        dot = QLabel("●")
        dot.setStyleSheet(f"color: {color}; font-size: 10px;")
        ext_lbl = QLabel(f".{ext}")
        ext_lbl.setObjectName("destext")
        top.addWidget(dot)
        top.addWidget(ext_lbl)
        top.addStretch()
        loss_lbl = QLabel(loss)
        loss_lbl.setStyleSheet(
            f"color: {'#7fd18b' if loss == 'lossless' else '#e0b45a'};"
            f"font-size: 11px;")
        top.addWidget(loss_lbl)
        v.addLayout(top)

        chain_lbl = QLabel(chain)
        chain_lbl.setObjectName("chain")
        chain_lbl.setWordWrap(True)
        v.addWidget(chain_lbl)

    def mouseReleaseEvent(self, event):  # noqa: N802
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.mime)


class MainWindow(QMainWindow):
    wlog_sig = Signal(str)

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
        self._domain_pages: dict[str, QWidget] = {}
        self._dest_cards: list[DestinationCard] = []
        self._server = None
        self._watch_timer = None
        self._watch_state = {}
        self.setWindowTitle("Cirax — universal local conversion hub")
        self.resize(1080, 700)
        self.setAcceptDrops(True)
        self._icon()
        self._dark()
        self._ui()
        self.wlog_sig.connect(self._wlog)

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
        for role, color in ((QPalette.Window, QColor(13, 17, 24)),
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
        central = Background()
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
        for i, (name, builder) in enumerate([
                ("Convert", self._convert_page),
                ("Lines", self._lines_page),
                ("Watch", self._watch_page),
                ("Serve", self._serve_page),
                ("Engines", self._engines_page),
                ("About", self._about_page)]):
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
        """The three-step pipeline: drop → departures → journey."""
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(22, 18, 22, 18)

        steps = QLabel("DROP  ──  DEPARTURES  ──  JOURNEY")
        steps.setObjectName("stepline")
        v.addWidget(steps)

        self.flow = QStackedLayout()
        v.addLayout(self.flow, stretch=1)
        self.flow.addWidget(self._step_drop())
        self.flow.addWidget(self._step_departures())
        self.flow.addWidget(self._step_journey())
        return page

    def _step_drop(self) -> QWidget:
        card_w, cv = make_card()
        step = QLabel("STEP 1 · DROP")
        step.setObjectName("stepline")
        cv.addWidget(step)

        self.drop = QLabel(
            "drag & drop files anywhere — or click to browse\n"
            "webp · heic · raw · docx · epub · pdf · mp4 · flac · zip · glb …")
        self.drop.setAlignment(Qt.AlignCenter)
        self.drop.setFixedHeight(110)
        self.drop.setStyleSheet(
            "border: 2px dashed #33424f; border-radius: 10px; color: #9fb0bf;")
        cv.addWidget(self.drop)
        self.drop.mousePressEvent = lambda e: self._add_files()

        self.files_list = QLabel("<i style='color:#5c6b78'>no files yet</i>")
        self.files_list.setWordWrap(True)
        cv.addWidget(self.files_list)
        self.detected_label = QLabel("")
        self.detected_label.setObjectName("tagline")
        self.detected_label.setWordWrap(True)
        self.detected_label.hide()
        cv.addWidget(self.detected_label)
        return card_w

    def _step_departures(self) -> QWidget:
        card_w, cv = make_card()
        top = QHBoxLayout()
        back = QPushButton("← drop different files")
        back.setObjectName("back")
        back.clicked.connect(lambda: self.flow.setCurrentIndex(0))
        top.addWidget(back)
        top.addStretch()
        cv.addLayout(top)

        step = QLabel("STEP 2 · DEPARTURES")
        step.setObjectName("stepline")
        cv.addWidget(step)

        head = QLabel("Where should it go?")
        head.setObjectName("pagetitle")
        cv.addWidget(head)
        self.detected_label = QLabel("")
        self.detected_label.setObjectName("tagline")
        self.detected_label.setWordWrap(True)
        cv.addWidget(self.detected_label)

        self.dest_filter = QLineEdit()
        self.dest_filter.setPlaceholderText("filter destinations…")
        self.dest_filter.textChanged.connect(self._filter_dest_cards)
        cv.addWidget(self.dest_filter)

        grid_host = QWidget()
        self.dest_grid = QGridLayout(grid_host)
        self.dest_grid.setSpacing(10)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setWidget(grid_host)
        scroll.setMinimumHeight(250)
        cv.addWidget(scroll, stretch=1)

        row = QHBoxLayout()
        row.addWidget(QLabel("Preset:"))
        self.preset = QComboBox()
        self.preset.addItem("default")
        for e in self.reg.engines:
            for name in e.presets:
                self.preset.addItem(f"{name} ({e.name})")
        row.addWidget(self.preset, stretch=2)
        self.sandbox_box = QCheckBox("Sandbox")
        self.sandbox_box.setChecked(True)
        row.addWidget(self.sandbox_box)
        self.ai_box = QCheckBox("AI transforms")
        self.ai_box.setToolTip(
            "allow generative AI routes (GLM-OCR, piper) — off by default")
        self.ai_box.toggled.connect(lambda _c: self._refresh_targets())
        row.addWidget(self.ai_box)
        row.addStretch()
        cv.addLayout(row)
        return card_w

    def _step_journey(self) -> QWidget:
        card_w, cv = make_card()
        step = QLabel("STEP 3 · JOURNEY")
        step.setObjectName("stepline")
        cv.addWidget(step)

        self.board = QLabel("")
        self.board.setObjectName("board")
        self.board.setTextFormat(Qt.RichText)
        self.board.setWordWrap(True)
        cv.addWidget(self.board)

        self.jobs = QTableWidget(0, 5)
        self.jobs.setHorizontalHeaderLabels(
            ["File", "Route", "Progress", "Status", ""])
        self.jobs.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.jobs.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.jobs.verticalHeader().setVisible(False)
        self.jobs.setEditTriggers(QTableWidget.NoEditTriggers)
        self.jobs.setSelectionMode(QTableWidget.NoSelection)
        self.jobs.setMinimumHeight(200)
        cv.addWidget(self.jobs, stretch=1)

        go = QHBoxLayout()
        again = QPushButton("← new conversion")
        again.setObjectName("back")
        again.clicked.connect(lambda: self.flow.setCurrentIndex(0))
        self.status = QLabel("")
        self.status.setObjectName("status")
        go.addWidget(again)
        go.addWidget(self.status, stretch=1)
        cv.addLayout(go)
        return card_w

    def _lines_page(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(22, 18, 22, 18)
        outer.addWidget(page_title("Lines", "one page per file-type domain"))
        card_w, cv = make_card()
        outer.addWidget(card_w, stretch=1)
        grid = QGridLayout()
        grid.setSpacing(10)
        domains = sorted({f.domain for f in self.reg.formats.values()})
        for k, dom in enumerate(domains):
            fmts = sum(1 for f in self.reg.formats.values() if f.domain == dom)
            btn = QPushButton(f"● {dom}   ·   {fmts} formats")
            color = line_color(dom)
            btn.setStyleSheet(
                f"QPushButton {{ color: {color}; text-align: left;"
                f" padding: 10px 14px; }}")
            btn.clicked.connect(lambda _=False, d=dom: self._open_domain(d))
            grid.addWidget(btn, k // 2, k % 2)
        grid.setRowStretch(len(domains) // 2 + 1, 1)
        cv.addLayout(grid)
        cv.addWidget(QLabel(
            "each line page lists the formats on it and the engines that "
            "read and write them on this machine."))
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
        for f in sorted(self.reg.formats.values(),
                        key=lambda x: (x.domain, x.ext)):
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
        self.watch_log.setFont(_mono_font())
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
        pix = self.windowIcon().pixmap(96, 96)
        if not pix.isNull():
            icon_label.setPixmap(pix)
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

    def _domain_page(self, domain: str) -> QWidget:
        """One page per file-type domain: its line, formats and engines."""
        color = line_color(domain)
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(22, 18, 22, 18)

        top = QHBoxLayout()
        back = QPushButton("← all lines")
        back.setObjectName("back")
        back.clicked.connect(self._goto_lines)
        top.addWidget(back)
        top.addStretch()
        v.addLayout(top)

        spine = QFrame()
        spine.setFixedWidth(4)
        spine.setStyleSheet(f"background: {color}; border-radius: 2px;")
        card_w, cv = make_card()
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.addWidget(spine)
        body.addLayout(cv)
        card_w.setLayout(body)
        v.addWidget(card_w, stretch=1)

        head = QLabel(f"● {domain} line")
        head.setStyleSheet(f"font-size: 17px; font-weight: 700; color: {color};")
        cv.addWidget(head)
        fmts = sorted((f for f in self.reg.formats.values()
                       if f.domain == domain and f.mime != "application/x-tree"),
                      key=lambda f: f.ext)
        engines_on_line = sorted({
            e.name for e in self.reg.engines if e.installed
            for r in e.routes
            if any(t.split("/")[0] == domain for t in r.to_formats)
        })
        cv.addWidget(QLabel(
            f"{len(fmts)} formats · {len(engines_on_line)} engines on this line"))

        table = QTableWidget(len(fmts), 3)
        table.setHorizontalHeaderLabels(["Format", "Ext", "Reads / writes"])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        for i, f in enumerate(fmts):
            readers, writers = [], []
            for e in self.reg.engines:
                if not e.installed:
                    continue
                wild = any("*" in r.from_formats for r in e.routes)
                for r in e.routes:
                    if r.matches_input(f.mime) and e.name not in readers:
                        readers.append(e.name)
                    if f.mime in r.to_formats and not r.ops \
                            and e.name not in writers:
                        writers.append(e.name)
            table.setItem(i, 0, QTableWidgetItem(f.name or f.mime))
            table.setItem(i, 1, QTableWidgetItem("." + f.ext))
            table.setItem(i, 2, QTableWidgetItem(
                f"{', '.join(readers) or '—'} / {', '.join(writers) or '—'}"))
        cv.addWidget(table, stretch=1)
        cv.addWidget(QLabel(
            "drop " + domain + " files on the Convert page — targets are "
            "picked from this line and its interchanges automatically."))
        return page

    def _open_domain(self, domain: str):
        if domain not in self._domain_pages:
            self._domain_pages[domain] = self._domain_page(domain)
            self.stack.addWidget(self._domain_pages[domain])
        self.stack.setCurrentWidget(self._domain_pages[domain])

    def _goto_lines(self):
        self.nav_group.button(1).setChecked(True)
        self.stack.setCurrentIndex(1)

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

    def _build_destinations(self):
        """Populate the departures grid from the dropped files' reach."""
        while self.dest_grid.count():
            item = self.dest_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._dest_cards = []

        by_domain: dict[str, list] = {}
        for mime, info in sorted(self._reach.items(),
                                 key=lambda kv: kv[1]["plan"].cost):
            plan = info["plan"]
            dom = mime.split("/")[0]
            ext = self.reg.ext_for(mime)
            loss = "lossless" if plan.lossless else "lossy"
            by_domain.setdefault(dom, []).append(
                (ext, mime, " → ".join(plan.engines), loss))
        n = 0
        for dom in sorted(by_domain):
            for ext, mime, chain, loss in sorted(by_domain[dom]):
                card = DestinationCard(ext, mime, dom, chain, loss)
                card.clicked.connect(self._depart)
                self.dest_grid.addWidget(card, n // 3, n % 3)
                self._dest_cards.append(card)
                n += 1
        if n == 0:
            empty = QLabel("no conversion targets found for these files")
            empty.setObjectName("tagline")
            self.dest_grid.addWidget(empty, 0, 0)
        for i in range(self.dest_grid.count()):
            self.dest_grid.setColumnStretch(i % 3, 1)
            break

    # ---------- departures ----------
    def _refresh_targets(self):
        self._reach = {}
        allow_ai = self.ai_box.isChecked()
        if not self._pending:
            return
        src_mimes = {}
        for p in self._pending:
            mime, _ = detect(Path(p), self.reg.ext_to_mime)
            src_mimes[p] = mime
        src_set = set(src_mimes.values())
        for p in self._pending:
            mime = src_mimes[p]
            for t_mime, plan in reachable(self.reg, mime,
                                          allow_ai=allow_ai).items():
                if t_mime in src_set:
                    continue
                cur = self._reach.get(t_mime)
                if cur is None or plan.cost < cur["plan"].cost:
                    self._reach[t_mime] = {"plan": plan}

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
        self._build_destinations()
        self._refresh_detected()
        self.flow.setCurrentIndex(1)  # auto-advance to departures

    def _refresh_detected(self):
        parts = []
        for p in self._pending:
            mime, _ = detect(Path(p), self.reg.ext_to_mime)
            fmt = self.reg.formats.get(mime)
            dom = line_color(mime.split("/")[0])
            parts.append(f"<b>{Path(p).name}</b> "
                         f"<span style='color:{dom}'>●</span> "
                         f"<span style='color:#8fa0b0'>{fmt.name or mime}</span>")
        self.detected_label.setText(
            "detected: " + " · ".join(parts) if parts
            else "detected formats will appear here")

    def _filter_dest_cards(self):
        needle = self.dest_filter.text().lower()
        for card in self._dest_cards:
            card.setVisible(needle in card.search_text.lower())

    # ---------- journey ----------
    def _depart(self, dst_mime: str):
        """A departure was chosen: build jobs and move to the journey."""
        paths = [Path(p) for p in self._pending]
        preset = self.preset.currentText().split(" (")[0]
        preset = None if preset == "default" else preset
        sandbox = "auto" if self.sandbox_box.isChecked() else "off"

        self.jobs.setRowCount(0)
        self._row_by_src = {}
        self.status.setText("")
        boards = []
        for src in paths:
            mime, _ = detect(src, self.reg.ext_to_mime)
            plan = find_plan(self.reg, mime, dst_mime,
                             allow_ai=self.ai_box.isChecked())
            if plan is None:
                self.status.setText(f"no route for {src.name} ({mime})")
                continue
            dst = src.with_suffix("." + self.reg.ext_for(dst_mime))
            if dst == src:
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
            boards.append(plan)
        if boards:
            self.flow.setCurrentIndex(2)
            self.board.setText(route_board_html(boards[0]))
            self.board.show()
            self.status.setText(f"converting {len(boards)} file(s)…")
        else:
            self.flow.setCurrentIndex(1)
            self.status.setText("nothing to convert — pick a destination")

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
            wrap = QWidget()
            hl = QHBoxLayout(wrap)
            hl.setContentsMargins(0, 0, 0, 0)
            hl.setSpacing(6)
            b1 = QPushButton("open")
            b1.setObjectName("open")
            b1.setToolTip(str(out))
            b1.clicked.connect(lambda _=False, p=out: open_path(p))
            b2 = QPushButton("folder")
            b2.setObjectName("open")
            b2.clicked.connect(lambda _=False, p=out.parent: open_path(p))
            hl.addWidget(b1)
            hl.addWidget(b2)
            self.jobs.setCellWidget(row, 4, wrap)
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
        self._watch_state = {"dir": d, "out": out, "mime": mime, "done": {}}
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
            st["done"][f.name] = mtime

            def run_job(src=f, target=dst, p=plan, name=f.name):
                try:
                    execute(p, self.reg, src, target, quiet=True)
                    self.wlog_sig.emit(f"done: {target.name}")
                except ConversionError as exc:
                    self.wlog_sig.emit(f"error {name}: {str(exc)[-120:]}")

            self.pool.start(WatchJob(run_job))

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
    # CI smoke hook: construct the whole UI, report, exit — no event loop.
    if os.environ.get("CIRAX_SMOKE"):
        w = MainWindow()
        print(f"cirax-app smoke ok: {w.stack.count()} pages, "
              f"{w.flow.count()} pipeline steps")
        return 0
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
