# ui/main_window.py
"""主窗口：地图、连接、日志、数据库检索、高度报警、截图。"""

import logging
import threading
import time
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, pyqtSlot, pyqtSignal, QObject
from PyQt6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QSplitter,
    QGroupBox,
    QLabel,
    QSizePolicy,
    QFrame,
    QLineEdit,
    QPushButton,
    QPlainTextEdit,
    QTableWidget,
    QTableWidgetItem,
    QComboBox,
    QMessageBox,
    QFileDialog,
    QDialog,
    QListWidget,
    QFormLayout,
    QDoubleSpinBox,
    QSpinBox,
    QApplication,
    QTabWidget,
    QStackedWidget,
    QRadioButton,
    QButtonGroup,
    QDialogButtonBox,
    QScrollArea,
    QCheckBox,
)
from PyQt6.QtCore import QSize
from PyQt6.QtGui import QGuiApplication, QPalette, QColor

from core.parser import parse_drone_message
from core.udp_client import run_udp_client

try:
    from core.mavlink_parser import MavLinkParser, decode_mavlink_to_annotated
    _MAVLINK_AVAILABLE = True
except ImportError:
    MavLinkParser = None
    _MAVLINK_AVAILABLE = False
from core.serial_client import run_serial_client, list_serial_ports, SERIAL_AVAILABLE, DEFAULT_SERIAL_FORMAT_CMD
from core import database
from map.map_widget import MapWidget, TILE_LAYERS
from ui.trajectory_3d_widget import Trajectory3DWidget
from ui.attitude_indicator import AttitudeIndicatorWidget, AttitudeIndicatorPfdWidget
from core import i18n

logger = logging.getLogger(__name__)


def _load_config():
    import yaml
    cfg_path = Path(__file__).parent.parent / "config.yaml"
    cfg = {}
    if cfg_path.exists():
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
    return cfg


class ConnectDialog(QDialog):
    """连接方式选择：UDP 或 串口，配置后连接。"""
    def __init__(self, parent, config: dict, serial_available: bool):
        super().__init__(parent)
        self.setWindowTitle(i18n.t("connect_data_source"))
        self._config = config
        self._serial_available = serial_available
        self._choice = None  # ("udp", {host, port}) or ("serial", {port, baud})
        layout = QVBoxLayout(self)
        self.mode_udp = QRadioButton(i18n.t("udp_esp32_bridge"))
        self.mode_serial = QRadioButton(i18n.t("serial_port"))
        self.mode_udp.setChecked(True)
        if not serial_available:
            self.mode_serial.setEnabled(False)
        layout.addWidget(self.mode_udp)
        layout.addWidget(self.mode_serial)
        # UDP 区
        udp_w = QWidget()
        udp_layout = QFormLayout(udp_w)
        self.host_edit = QLineEdit()
        self.host_edit.setPlaceholderText(i18n.t("host_placeholder"))
        self.host_edit.setText(config.get("udp_host", "127.0.0.1"))
        self.port_edit = QLineEdit()
        self.port_edit.setText(str(config.get("udp_port", 8888)))
        udp_layout.addRow(i18n.t("host") + ":", self.host_edit)
        udp_layout.addRow(i18n.t("port") + ":", self.port_edit)
        layout.addWidget(udp_w)
        # 串口区
        serial_w = QWidget()
        serial_layout = QFormLayout(serial_w)
        self.port_combo = QComboBox()
        self.port_combo.setMinimumWidth(180)
        self._refresh_ports()
        self.refresh_ports_btn = QPushButton(i18n.t("refresh_ports"))
        self.refresh_ports_btn.clicked.connect(self._refresh_ports)
        self.baud_combo = QComboBox()
        self.baud_combo.addItems(["9600", "19200", "38400", "57600", "115200", "230400", "460800"])
        self.baud_combo.setCurrentText(str(config.get("serial_baud", "115200")))
        serial_layout.addRow(i18n.t("serial_port") + ":", self.port_combo)
        serial_layout.addRow("", self.refresh_ports_btn)
        serial_layout.addRow(i18n.t("baud_rate") + ":", self.baud_combo)
        layout.addWidget(serial_w)
        def on_mode():
            udp = self.mode_udp.isChecked()
            udp_w.setVisible(udp)
            serial_w.setVisible(not udp)
        self.mode_udp.toggled.connect(lambda: on_mode())
        self.mode_serial.toggled.connect(lambda: on_mode())
        serial_w.setVisible(False)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self._on_connect)
        bb.rejected.connect(self.reject)
        layout.addWidget(bb)

    def _refresh_ports(self):
        if not SERIAL_AVAILABLE:
            return
        self.port_combo.clear()
        for port, desc in list_serial_ports():
            self.port_combo.addItem(f"{port} ({desc})", port)
        if self.port_combo.count() == 0:
            self.port_combo.addItem(i18n.t("no_serial_ports"), None)

    def _on_connect(self):
        if self.mode_udp.isChecked():
            host = self.host_edit.text().strip() or "127.0.0.1"
            try:
                port = int(self.port_edit.text().strip() or "8888")
            except ValueError:
                port = 8888
            self._choice = ("udp", {"host": host, "port": port})
        else:
            port = self.port_combo.currentData()
            if port is None and self.port_combo.count() > 0:
                txt = self.port_combo.currentText()
                if not txt.startswith("(") and " " in txt:
                    port = txt.split()[0]
            if not port or not isinstance(port, str):
                QMessageBox.warning(self, i18n.t("connect"), i18n.t("select_valid_serial"))
                return
            try:
                baud = int(self.baud_combo.currentText())
            except ValueError:
                baud = 115200
            self._choice = ("serial", {"port": port, "baud": baud})
        self.accept()

    def get_choice(self):
        return self._choice


class RecordsAndTrajectoryDialog(QDialog):
    """轨迹记录：由主界面「记录检索」按钮打开，仅含轨迹列表、回放、删除。"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(i18n.t("trajectory_records"))
        self.setMinimumSize(480, 360)
        layout = QVBoxLayout(self)
        self.trajectory_list = QListWidget()
        self.trajectory_list.setMinimumHeight(160)
        traj_btn_row = QHBoxLayout()
        self.traj_play_btn = QPushButton(i18n.t("trajectory_playback"))
        self.traj_play_btn.clicked.connect(self._do_playback)
        self.traj_delete_btn = QPushButton(i18n.t("trajectory_delete"))
        self.traj_delete_btn.clicked.connect(self._do_delete_trajectory)
        traj_btn_row.addWidget(self.traj_play_btn)
        traj_btn_row.addWidget(self.traj_delete_btn)
        traj_btn_row.addStretch()
        layout.addWidget(self.trajectory_list)
        layout.addLayout(traj_btn_row)
        close_btn = QPushButton(i18n.t("close"))
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)
        self._runs_list = []

    def _load_trajectory_list(self):
        self.trajectory_list.clear()
        parent = self.parent()
        if not parent or not getattr(parent, "conn", None):
            self._runs_list = []
            return
        with parent._db_lock:
            self._runs_list = database.trajectory_list_runs(parent.conn)
        for r in self._runs_list:
            created = (r.get("created_at") or "")[:19].replace("T", " ")
            name = r.get("name") or f"运行 {created}"
            self.trajectory_list.addItem(f"{r['id']}: {name}")

    def _do_playback(self):
        parent = self.parent()
        if not parent or not getattr(parent, "conn", None):
            QMessageBox.information(self, "", "数据库未就绪")
            return
        row = self.trajectory_list.currentRow()
        if row < 0 or row >= len(self._runs_list):
            QMessageBox.information(self, "", "请先选中一条轨迹记录")
            return
        run = self._runs_list[row]
        with parent._db_lock:
            points = database.trajectory_get_points(parent.conn, run["id"])
        if not points:
            QMessageBox.information(self, "", "该记录无轨迹点")
            return
        did = f"playback_{run['id']}"
        latlngs = [(p["lat"], p["lon"]) for p in points]
        parent.map_widget.update_drone_trajectory(did, latlngs)
        if latlngs and points:
            last = points[-1]
            heading = (last.get("yaw", 0) % 360 + 360) % 360
            parent.map_widget.update_drone(did, last["lat"], last["lon"], last.get("alt", 0), type="回放", detail_html=f"轨迹 {run.get('name','')} 共 {len(points)} 点", heading=heading)
        if hasattr(parent, "_append_log_line"):
            parent._append_log_line(f"已回放轨迹: {run.get('name','')} ({len(points)} 点)")

    def _do_delete_trajectory(self):
        parent = self.parent()
        if not parent or not getattr(parent, "conn", None):
            return
        row = self.trajectory_list.currentRow()
        if row < 0 or row >= len(self._runs_list):
            QMessageBox.information(self, "", "请先选中一条再删除")
            return
        run = self._runs_list[row]
        if QMessageBox.question(
            self, "", f"确定删除「{run.get('name','')}」？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        with parent._db_lock:
            database.trajectory_delete_run(parent.conn, run["id"])
        self._load_trajectory_list()
        if hasattr(parent, "_append_log_line"):
            parent._append_log_line("已删除轨迹记录")

    def showEvent(self, event):
        super().showEvent(event)
        self._load_trajectory_list()


class LogViewerWindow(QWidget):
    """应用日志子窗口，可独立关闭。"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("应用日志")
        self.setMinimumSize(500, 400)
        self.setWindowFlags(Qt.WindowType.Window)
        layout = QVBoxLayout(self)
        self.log_edit = QPlainTextEdit()
        self.log_edit.setReadOnly(True)
        layout.addWidget(self.log_edit)
        close_btn = QPushButton(i18n.t("close"))
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)

    def closeEvent(self, event):
        self.hide()
        event.accept()

    def append(self, text: str):
        self.log_edit.appendPlainText(text)

    def set_content(self, text: str):
        self.log_edit.setPlainText(text)


class LinkStats:
    """线程安全的链接统计：收发包字节数、包数、速率、最大包间隔等。"""
    def __init__(self):
        import threading
        self._lock = threading.Lock()
        self.reset()

    def reset(self):
        with self._lock:
            self.rx_bytes = 0
            self.rx_packets = 0
            self.tx_bytes = 0
            self.tx_packets = 0
            self.start_time = time.time()
            self.last_rx_time = None
            self.max_interval_ms = 0
            self.dropped = 0

    def add_rx(self, n_bytes: int, n_packets: int = 1):
        with self._lock:
            self.rx_bytes += n_bytes
            self.rx_packets += n_packets
            now = time.time()
            if self.last_rx_time is not None:
                interval_ms = (now - self.last_rx_time) * 1000
                if interval_ms > self.max_interval_ms:
                    self.max_interval_ms = interval_ms
            self.last_rx_time = now

    def add_tx(self, n_bytes: int, n_packets: int = 1):
        with self._lock:
            self.tx_bytes += n_bytes
            self.tx_packets += n_packets

    def snapshot(self):
        with self._lock:
            elapsed = time.time() - self.start_time
            rx_b = self.rx_bytes
            rx_p = self.rx_packets
            tx_b = self.tx_bytes
            tx_p = self.tx_packets
            max_ms = self.max_interval_ms
            dropped = self.dropped
        if elapsed < 0.001:
            elapsed = 0.001
        return {
            "rx_bytes": rx_b,
            "rx_packets": rx_p,
            "tx_bytes": tx_b,
            "tx_packets": tx_p,
            "rx_bytes_per_sec": rx_b / elapsed,
            "rx_packets_per_sec": rx_p / elapsed,
            "tx_bytes_per_sec": tx_b / elapsed,
            "max_interval_ms": max_ms,
            "dropped": dropped,
            "quality_pct": 100.0 if (rx_p + dropped) == 0 else 100.0 * rx_p / (rx_p + dropped),
            "elapsed": elapsed,
        }


class LinkStatisticsDialog(QDialog):
    """链接统计对话框：下载/上传字节与包数、速率、丢包、质量、最大包间隔。"""
    def __init__(self, parent=None, link_stats: LinkStats | None = None):
        super().__init__(parent)
        self.setWindowTitle(i18n.t("link_stats"))
        self.setMinimumSize(420, 320)
        self.setWindowFlags(Qt.WindowType.Window)
        self._link_stats = link_stats or LinkStats()
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self._labels = {}
        keys_and_labels = [
            ("bytes", i18n.t("bytes") + ":"),
            ("bytes_per_sec", i18n.t("bytes_per_sec") + ":"),
            ("packets", i18n.t("packets") + ":"),
            ("packets_per_sec", i18n.t("packets_per_sec") + ":"),
            ("dropped", i18n.t("dropped") + ":"),
            ("quality", i18n.t("quality") + ":"),
            ("max_interval_ms", i18n.t("max_interval_ms") + ":"),
            ("tx_bytes", i18n.t("bytes_total") + ":"),
            ("tx_bytes_per_sec", i18n.t("bytes_per_sec") + ":"),
        ]
        for k, title in keys_and_labels:
            lbl = QLabel("—")
            lbl.setMinimumWidth(100)
            self._labels[k] = lbl
            form.addRow(title, lbl)
        layout.addLayout(form)
        row2 = QHBoxLayout()
        self.reset_btn = QPushButton(i18n.t("reset"))
        self.reset_btn.clicked.connect(self._on_reset)
        row2.addStretch()
        row2.addWidget(self.reset_btn)
        layout.addLayout(row2)
        close_btn = QPushButton(i18n.t("close"))
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)
        self._timer.start(500)

    def _refresh(self):
        s = self._link_stats.snapshot()
        def fmt_b(b):
            if b >= 1024 * 1024:
                return f"{b / (1024*1024):.2f}Mb"
            if b >= 1024:
                return f"{b / 1024:.2f}Kb"
            return f"{b:.0f}b"
        def fmt_rate(r):
            if r >= 1024:
                return f"{r/1024:.2f}Kb"
            return f"{r:.0f}b"
        self._labels["bytes"].setText(fmt_b(s["rx_bytes"]))
        self._labels["bytes_per_sec"].setText(fmt_rate(s["rx_bytes_per_sec"]))
        self._labels["packets"].setText(str(s["rx_packets"]))
        self._labels["packets_per_sec"].setText(f"{s['rx_packets_per_sec']:.0f}")
        self._labels["dropped"].setText(str(s["dropped"]))
        self._labels["quality"].setText(f"{s['quality_pct']:.0f}%")
        self._labels["max_interval_ms"].setText(f"{s['max_interval_ms']:.0f}")
        self._labels["tx_bytes"].setText(fmt_b(s["tx_bytes"]))
        self._labels["tx_bytes_per_sec"].setText(fmt_rate(s["tx_bytes_per_sec"]))

    def _on_reset(self):
        self._link_stats.reset()
        self._refresh()

    def showEvent(self, event):
        super().showEvent(event)
        self._refresh()


class SettingsDialog(QDialog):
    """设置对话框：语言、姿态显示类型等。"""
    def __init__(self, parent=None, config: dict | None = None):
        super().__init__(parent)
        self.setWindowTitle(i18n.t("settings"))
        self.setMinimumWidth(360)
        self._config = dict(config or {})
        layout = QFormLayout(self)
        self.language_combo = QComboBox()
        self.language_combo.addItems(["zh", "en"])
        self.language_combo.setCurrentText(self._config.get("language", "zh"))
        layout.addRow(i18n.t("language") + ":", self.language_combo)
        self.attitude_combo = QComboBox()
        self.attitude_combo.addItem(i18n.t("attitude_classic"), "classic")
        self.attitude_combo.addItem(i18n.t("attitude_pfd"), "pfd")
        current_att = self._config.get("attitude_display_type", "classic")
        idx = self.attitude_combo.findData(current_att)
        if idx >= 0:
            self.attitude_combo.setCurrentIndex(idx)
        layout.addRow(i18n.t("attitude_display_type") + ":", self.attitude_combo)
        self.theme_combo = QComboBox()
        self.theme_combo.addItem(i18n.t("theme_dark"), "dark")
        self.theme_combo.addItem(i18n.t("theme_light"), "light")
        current_theme = self._config.get("gui_theme", "dark")
        idx = self.theme_combo.findData(current_theme)
        if idx >= 0:
            self.theme_combo.setCurrentIndex(idx)
        layout.addRow(i18n.t("gui_theme") + ":", self.theme_combo)
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        ok_btn = QPushButton(i18n.t("ok"))
        ok_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton(i18n.t("cancel"))
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addRow(btn_layout)

    def get_language(self) -> str:
        return self.language_combo.currentText()

    def get_attitude_display_type(self) -> str:
        return self.attitude_combo.currentData()

    def get_gui_theme(self) -> str:
        return self.theme_combo.currentData()


class RawMessageWindow(QWidget):
    """原始报文子窗口：两个标签页——原始十六进制 / MAVLink 解析注释。"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("原始报文")
        self.setMinimumSize(640, 420)
        self.setWindowFlags(Qt.WindowType.Window)
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        self.msg_edit = QPlainTextEdit()
        self.msg_edit.setReadOnly(True)
        self.msg_edit.setPlaceholderText("连接后收到的原始报文（十六进制）将显示在此")
        self.tabs.addTab(self.msg_edit, "原始十六进制")
        self.parsed_edit = QPlainTextEdit()
        self.parsed_edit.setReadOnly(True)
        self.parsed_edit.setPlaceholderText("MAVLink 解析后的消息（类型与字段注释）将显示在此")
        self.tabs.addTab(self.parsed_edit, "解析注释")
        layout.addWidget(self.tabs)
        close_btn = QPushButton(i18n.t("close"))
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)

    def closeEvent(self, event):
        self.hide()
        event.accept()

    def append(self, text: str):
        self.msg_edit.appendPlainText(text)

    def append_parsed(self, text: str):
        self.parsed_edit.appendPlainText(text)

    def set_content(self, text: str):
        self.msg_edit.setPlainText(text)

    def set_parsed_content(self, text: str):
        self.parsed_edit.setPlainText(text)


class MainWindow(QMainWindow):
    # 实时报文信号：主线程中更新 UI、写日志、解析并入库/地图/报警
    message_received = pyqtSignal(str, str)  # (raw_text, source)
    mavlink_records_received = pyqtSignal(list, str)  # (records, source)，主线程处理 MAVLink
    raw_packet_received = pyqtSignal(bytes, str)  # (raw_bytes, source)，用于原始报文窗口显示 MAVLink 十六进制
    log_line_ready = pyqtSignal(str)  # 日志行（供非主线程安全写入应用日志区）

    def __init__(self):
        super().__init__()
        self.setWindowTitle(i18n.t("app_title"))
        self.resize(1200, 800)
        cfg = _load_config()
        self.config = cfg
        i18n.set_language(cfg.get("language", "zh"))
        i18n.set_language_changed_callback(self._on_language_changed)
        self._apply_gui_theme(cfg.get("gui_theme", "dark"))
        self.udp_stop = None
        self.serial_stop = None
        self._udp_send = None
        self._serial_send = None
        self._target_system = 1
        self._target_component = 1
        self.conn = None
        self._receive_callbacks: list = []  # (raw_text, source) 实时报文回调
        self._realtime_max_lines = 500  # 实时报文区域最大行数
        self._alarm_height_m = int(cfg.get("alarm_height_m", 0))  # 高度报警阈值(米)，0=关闭
        # 单机模式：轨迹不裁剪，每点存 (ts, lat, lon, alt, roll, pitch, yaw)
        self._drone_trajectories: dict[str, list[tuple]] = {}  # drone_id -> [(ts, lat, lon, alt, roll, pitch, yaw), ...]
        self._drone_current: dict[str, dict] = {}  # 单机：仅保留一架
        self._current_run_start_ts: float | None = None  # 本次连接开始时间，用于保存轨迹记录
        self._operator_by_drone: dict[str, dict] = {}  # drone_id -> {lat, lon, alt}，每机一个操作者
        self._connection_status = "未连接"
        self._log_buffer: list[str] = []
        self._log_buffer_max = 2000
        self._log_window: LogViewerWindow | None = None
        self._raw_message_window: RawMessageWindow | None = None
        self._trajectory_3d_window: Trajectory3DWidget | None = None
        self._realtime_buffer: list[str] = []
        self._realtime_buffer_max = 500
        self._parsed_buffer: list[str] = []
        self._parsed_buffer_max = 500
        self._mavlink_parser = None
        if _MAVLINK_AVAILABLE:
            try:
                self._mavlink_parser = MavLinkParser()
            except Exception as e:
                logger.debug("MAVLink parser init skipped: %s", e)
        self._link_stats = LinkStats()
        self._link_stats_window: LinkStatisticsDialog | None = None
        self._serial_heartbeat_timer: QTimer | None = None

        data_dir = Path(cfg.get("data_dir", "data"))
        logs_dir = Path(cfg.get("logs_dir", "logs"))
        screenshots_dir = Path(cfg.get("screenshots_dir", "logs/screenshots"))
        logs_dir.mkdir(parents=True, exist_ok=True)
        screenshots_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir = logs_dir
        self.screenshots_dir = Path(screenshots_dir)
        self.raw_log_file = None
        self._open_raw_log()

        import sqlite3
        db_path = database.get_db_path(data_dir)
        self.conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._db_lock = threading.Lock()
        database.init_db(self.conn)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # 顶部一行：连接、底图、工具
        top = QHBoxLayout()
        self.connect_btn = QPushButton(i18n.t("connect"))
        self.connect_btn.clicked.connect(self._open_connect_dialog)
        self.disconnect_btn = QPushButton(i18n.t("disconnect"))
        self.disconnect_btn.clicked.connect(self._do_disconnect)
        self.disconnect_btn.setEnabled(False)
        top.addWidget(self.connect_btn)
        top.addWidget(self.disconnect_btn)
        self._map_label = QLabel(i18n.t("map") + ":")
        top.addWidget(self._map_label)
        self.provider_combo = QComboBox()
        self.provider_combo.addItems(["osm", "bing", "gaode", "baidu", "google", "google_cn"])
        self.layer_combo = QComboBox()
        self.layer_combo.addItems(["road", "satellite"])
        self.layer_combo.currentTextChanged.connect(self._on_layer_change)
        self.provider_combo.currentTextChanged.connect(self._on_layer_change)
        top.addWidget(self.provider_combo)
        top.addWidget(self.layer_combo)
        self.follow_map_cb = QCheckBox(i18n.t("follow_map"))
        self.follow_map_cb.setChecked(True)
        top.addWidget(self.follow_map_cb)
        self.screenshot_btn = QPushButton(i18n.t("screenshot"))
        self.screenshot_btn.clicked.connect(self._screenshot)
        self.log_window_btn = QPushButton(i18n.t("app_log"))
        self.log_window_btn.clicked.connect(self._open_log_window)
        self.raw_message_btn = QPushButton(i18n.t("raw_message"))
        self.raw_message_btn.clicked.connect(self._open_raw_message_window)
        self.link_stats_btn = QPushButton(i18n.t("link_stats"))
        self.link_stats_btn.clicked.connect(self._open_link_stats)
        self.trajectory_3d_btn = QPushButton(i18n.t("trajectory_3d"))
        self.trajectory_3d_btn.clicked.connect(self._open_trajectory_3d)
        self.records_btn = QPushButton(i18n.t("record_search"))
        self.records_btn.clicked.connect(self._open_records_and_trajectory)
        top.addWidget(self.screenshot_btn)
        top.addWidget(self.log_window_btn)
        top.addWidget(self.raw_message_btn)
        top.addWidget(self.link_stats_btn)
        top.addWidget(self.trajectory_3d_btn)
        top.addWidget(self.records_btn)
        self.settings_btn = QPushButton(i18n.t("settings"))
        self.settings_btn.clicked.connect(self._on_settings_click)
        top.addWidget(self.settings_btn)
        top.addStretch()
        layout.addLayout(top)

        # 主体：地图 + 右侧面板（可拖动分隔条调整宽度），包入 widget 以填满垂直空间
        content_widget = QWidget()
        content_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        content = QVBoxLayout(content_widget)
        content.setContentsMargins(0, 0, 0, 0)
        default_lat = float(cfg.get("default_lat", 31.2304))
        default_lon = float(cfg.get("default_lon", 121.4737))
        default_zoom = int(cfg.get("default_zoom", 14))
        self.map_widget = MapWidget(default_lat=default_lat, default_lon=default_lon, default_zoom=default_zoom)
        self.map_widget.setMinimumWidth(400)
        self.map_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        right = QFrame()
        right.setFrameShape(QFrame.Shape.StyledPanel)
        right.setMinimumWidth(280)
        right.setMaximumWidth(800)
        right.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(4, 4, 4, 4)
        self.state_group = QGroupBox(i18n.t("drone_state"))
        state_layout = QFormLayout(self.state_group)
        self.state_flight_mode = QLabel("—")
        self.state_arm = QLabel("—")
        self.state_battery = QLabel("—")
        self.state_attitude = QLabel("Roll — Pitch — Yaw —")
        self.state_heading_nose = QLabel("—")
        self.state_heading_course = QLabel("—")
        self.state_airspeed = QLabel("—")
        self.state_groundspeed = QLabel("—")
        self.state_alt = QLabel("—")
        self.state_lat = QLabel("—")
        self.state_lon = QLabel("—")
        self.state_gnss = QLabel("—")
        self._state_label_fm = QLabel(i18n.t("flight_mode") + ":")
        self._state_label_arm = QLabel(i18n.t("armed") + ":")
        self._state_label_bat = QLabel(i18n.t("battery") + ":")
        self._state_label_att = QLabel(i18n.t("attitude") + ":")
        self._state_label_heading_nose = QLabel(i18n.t("heading_nose") + ":")
        self._state_label_heading_course = QLabel(i18n.t("heading_course") + ":")
        self._state_label_air = QLabel(i18n.t("airspeed") + ":")
        self._state_label_gnd = QLabel(i18n.t("groundspeed") + ":")
        self._state_label_alt = QLabel(i18n.t("altitude") + ":")
        self._state_label_lat = QLabel(i18n.t("latitude") + ":")
        self._state_label_lon = QLabel(i18n.t("longitude") + ":")
        self._state_label_gnss = QLabel(i18n.t("gnss_satellites") + ":")
        state_layout.addRow(self._state_label_fm, self.state_flight_mode)
        state_layout.addRow(self._state_label_arm, self.state_arm)
        state_layout.addRow(self._state_label_bat, self.state_battery)
        state_layout.addRow(self._state_label_att, self.state_attitude)
        state_layout.addRow(self._state_label_heading_nose, self.state_heading_nose)
        state_layout.addRow(self._state_label_heading_course, self.state_heading_course)
        state_layout.addRow(self._state_label_air, self.state_airspeed)
        state_layout.addRow(self._state_label_gnd, self.state_groundspeed)
        state_layout.addRow(self._state_label_alt, self.state_alt)
        state_layout.addRow(self._state_label_lat, self.state_lat)
        state_layout.addRow(self._state_label_lon, self.state_lon)
        state_layout.addRow(self._state_label_gnss, self.state_gnss)
        right_layout.addWidget(self.state_group)
        # 姿态仪表单独成组，经典圆盘 / PFD 可切换
        self.attitude_group = QGroupBox(i18n.t("attitude_indicator"))
        attitude_layout = QVBoxLayout(self.attitude_group)
        self.attitude_stacked = QStackedWidget(self)
        self._attitude_classic = AttitudeIndicatorWidget(self)
        self._attitude_classic.setMinimumSize(220, 220)
        self._attitude_classic.setMaximumSize(380, 380)
        self._attitude_pfd = AttitudeIndicatorPfdWidget(self)
        self._attitude_pfd.setMinimumSize(320, 280)
        self._attitude_pfd.setMaximumSize(500, 440)
        self.attitude_stacked.addWidget(self._attitude_classic)
        self.attitude_stacked.addWidget(self._attitude_pfd)
        attitude_type = cfg.get("attitude_display_type", "classic")
        self.attitude_stacked.setCurrentIndex(1 if attitude_type == "pfd" else 0)
        attitude_layout.addWidget(self.attitude_stacked, 0, Qt.AlignmentFlag.AlignCenter)
        right_layout.addWidget(self.attitude_group)
        # 控制：解锁、起飞、降落（单机），紧凑布局
        self.control_group = QGroupBox(i18n.t("control"))
        self.control_group.setMaximumHeight(72)
        control_layout = QHBoxLayout(self.control_group)
        control_layout.setContentsMargins(6, 4, 6, 4)
        control_layout.setSpacing(6)
        self.arm_btn = QPushButton(i18n.t("arm"))
        self.arm_btn.clicked.connect(self._on_arm_click)
        self.takeoff_btn = QPushButton(i18n.t("takeoff"))
        self.takeoff_btn.clicked.connect(self._on_takeoff_click)
        self.land_btn = QPushButton(i18n.t("land"))
        self.land_btn.clicked.connect(self._on_land_click)
        self.rtl_btn = QPushButton(i18n.t("rtl"))
        self.rtl_btn.clicked.connect(self._on_rtl_click)
        from PyQt6.QtGui import QFont
        ctrl_font = QFont(self.arm_btn.font())
        ctrl_font.setPointSize(max(8, ctrl_font.pointSize() - 2))
        for btn in (self.arm_btn, self.takeoff_btn, self.land_btn, self.rtl_btn):
            btn.setFont(ctrl_font)
        control_layout.addWidget(self.arm_btn)
        control_layout.addWidget(self.takeoff_btn)
        control_layout.addWidget(self.land_btn)
        control_layout.addWidget(self.rtl_btn)
        control_layout.addStretch()
        right_layout.addWidget(self.control_group)
        # 轨迹记录：管理列表、回放、删除
        # 地图与右侧面板用 QSplitter，可拖动分隔条调整右侧宽度，解决列表数据显示不全
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_splitter.addWidget(self.map_widget)
        main_splitter.addWidget(right)
        main_splitter.setStretchFactor(0, 1)
        main_splitter.setStretchFactor(1, 0)
        main_splitter.setSizes([800, 360])
        content.addWidget(main_splitter)
        layout.addWidget(content_widget, 1)

        # 状态栏
        self.statusBar().showMessage("未连接")
        self.message_received.connect(self._on_message_received)
        self.mavlink_records_received.connect(self._on_mavlink_records_received)
        self.raw_packet_received.connect(self._on_raw_packet_received)
        self.map_widget.map_ready.connect(self._on_map_ready)
        # 日志：写入缓冲并供子窗口使用，主界面不再显示
        self._log_handler = None
        self._setup_log_handler()

    def register_receive_callback(self, callback):
        """注册实时报文回调：callback(raw_text: str, source: str) 在每次收到报文时于主线程调用。"""
        self._receive_callbacks.append(callback)

    def _update_connection_status(self):
        self.statusBar().showMessage(self._connection_status)
        self.disconnect_btn.setEnabled(self.udp_stop is not None or self.serial_stop is not None)

    def _apply_gui_theme(self, theme: str):
        """根据 gui_theme 设置界面背景与前景色（黑/白背景），仅改配色不改布局，与白背景一致。"""
        app = QApplication.instance()
        # 统一用 Fusion 样式，避免原生样式在深色下按钮颜色异常（如发红）
        try:
            app.setStyle("Fusion")
        except Exception:
            pass
        app.setStyleSheet("")
        self.setStyleSheet("")
        if theme == "light":
            app.setPalette(QPalette())
        else:
            p = QPalette()
            bg = QColor(0x25, 0x25, 0x26)
            fg = QColor(0xe0, 0xe0, 0xe0)
            base = QColor(0x3c, 0x3c, 0x3c)
            for group in (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive, QPalette.ColorGroup.Disabled):
                p.setColor(group, QPalette.ColorRole.Window, bg)
                p.setColor(group, QPalette.ColorRole.WindowText, fg)
                p.setColor(group, QPalette.ColorRole.Base, base)
                p.setColor(group, QPalette.ColorRole.Text, fg)
                p.setColor(group, QPalette.ColorRole.Button, base)
                p.setColor(group, QPalette.ColorRole.ButtonText, fg)
                p.setColor(group, QPalette.ColorRole.Highlight, QColor(0x0e, 0x63, 0x9e))
                p.setColor(group, QPalette.ColorRole.HighlightedText, fg)
                p.setColor(group, QPalette.ColorRole.PlaceholderText, QColor(0x80, 0x80, 0x80))
            app.setPalette(p)

    def _save_config(self):
        """将 self.config 写回 config.yaml。"""
        try:
            import yaml
            cfg_path = Path(__file__).parent.parent / "config.yaml"
            with open(cfg_path, "w", encoding="utf-8") as f:
                yaml.dump(self.config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
        except Exception as e:
            logger.warning("Save config: %s", e)

    def _on_settings_click(self):
        dlg = SettingsDialog(self, self.config)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        lang = dlg.get_language()
        if lang in ("zh", "en"):
            i18n.set_language(lang)
            self.config["language"] = lang
        att = dlg.get_attitude_display_type()
        if att in ("classic", "pfd"):
            self.config["attitude_display_type"] = att
            self.attitude_stacked.setCurrentIndex(1 if att == "pfd" else 0)
        theme = dlg.get_gui_theme()
        if theme in ("dark", "light"):
            self.config["gui_theme"] = theme
            self._apply_gui_theme(theme)
        self._save_config()
        self._refresh_ui_language()
        # 使 PFD 立即按新配色重绘（传入当前 theme）
        cur = self.attitude_stacked.currentWidget()
        if hasattr(cur, "set_flight_data"):
            cur.set_flight_data({"gui_theme": self.config.get("gui_theme", "dark")})

    def _on_language_changed(self, lang: str):
        self._refresh_ui_language()

    def _refresh_ui_language(self):
        """根据当前语言刷新界面文案。"""
        self.setWindowTitle(i18n.t("app_title"))
        self.connect_btn.setText(i18n.t("connect"))
        self.disconnect_btn.setText(i18n.t("disconnect"))
        self.screenshot_btn.setText(i18n.t("screenshot"))
        if hasattr(self, "_map_label"):
            self._map_label.setText(i18n.t("map") + ":")
        if hasattr(self, "follow_map_cb"):
            self.follow_map_cb.setText(i18n.t("follow_map"))
        self.log_window_btn.setText(i18n.t("app_log"))
        self.raw_message_btn.setText(i18n.t("raw_message"))
        self.link_stats_btn.setText(i18n.t("link_stats"))
        self.trajectory_3d_btn.setText(i18n.t("trajectory_3d"))
        self.records_btn.setText(i18n.t("record_search"))
        if hasattr(self, "state_group"):
            self.state_group.setTitle(i18n.t("drone_state"))
        if hasattr(self, "_state_label_fm"):
            self._state_label_fm.setText(i18n.t("flight_mode") + ":")
            self._state_label_arm.setText(i18n.t("armed") + ":")
            self._state_label_bat.setText(i18n.t("battery") + ":")
            self._state_label_att.setText(i18n.t("attitude") + ":")
            self._state_label_heading_nose.setText(i18n.t("heading_nose") + ":")
            self._state_label_heading_course.setText(i18n.t("heading_course") + ":")
            self._state_label_air.setText(i18n.t("airspeed") + ":")
            self._state_label_gnd.setText(i18n.t("groundspeed") + ":")
            self._state_label_alt.setText(i18n.t("altitude") + ":")
            self._state_label_lat.setText(i18n.t("latitude") + ":")
            self._state_label_lon.setText(i18n.t("longitude") + ":")
            self._state_label_gnss.setText(i18n.t("gnss_satellites") + ":")
        if hasattr(self, "attitude_group"):
            self.attitude_group.setTitle(i18n.t("attitude_indicator"))
        if hasattr(self, "control_group"):
            self.control_group.setTitle(i18n.t("control"))
            self.arm_btn.setText(i18n.t("arm"))
            self.takeoff_btn.setText(i18n.t("takeoff"))
            self.land_btn.setText(i18n.t("land"))
            self.rtl_btn.setText(i18n.t("rtl"))
        if hasattr(self, "settings_btn"):
            self.settings_btn.setText(i18n.t("settings"))
        self._update_state_panel()

    def _open_connect_dialog(self):
        if self.udp_stop or self.serial_stop:
            QMessageBox.information(self, i18n.t("connect"), i18n.t("already_connected_msg", status=self._connection_status))
            return
        dlg = ConnectDialog(self, self.config, SERIAL_AVAILABLE)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        choice = dlg.get_choice()
        if choice:
            self._do_connect(choice[0], choice[1])

    def _do_connect(self, mode: str, params: dict):
        if mode == "udp":
            self._disconnect_serial()
            host = params.get("host", "127.0.0.1")
            port = int(params.get("port", 8888))
            listen_port = int(self.config.get("udp_listen_port", 0))
            self.udp_stop, self._udp_send = run_udp_client(host, port, self._on_udp_data, listen_port=listen_port)
            self._serial_send = None
            self._connection_status = f"UDP: {host}:{port}"
            self._drone_trajectories.clear()
            self._current_run_start_ts = time.time()
            self._append_log_line(f"已连接 UDP {host}:{port}，等待数据…")
        else:
            self._disconnect()
            port = params.get("port")
            baud = int(params.get("baud", 115200))
            if not port:
                QMessageBox.warning(self, i18n.t("connect"), i18n.t("select_valid_serial"))
                return
            format_cmd_raw = (self.config.get("serial_format_cmd") or "").strip() or DEFAULT_SERIAL_FORMAT_CMD
            format_cmd = format_cmd_raw.encode("utf-8", errors="replace") if format_cmd_raw else None
            request_stream = self.config.get("serial_request_stream", True)
            use_binary = request_stream and _MAVLINK_AVAILABLE

            if use_binary:
                def on_serial_data(data: bytes, source: str):
                    self._on_udp_data(data, source)
            else:
                def on_serial_data(data: bytes, source: str):
                    try:
                        text = data.decode("utf-8", errors="replace")
                    except Exception:
                        return
                    self.message_received.emit(text, source)

            try:
                self.serial_stop, self._serial_send = run_serial_client(
                    port, baud, on_serial_data, format_cmd=format_cmd, use_binary=use_binary
                )
            except Exception as e:
                QMessageBox.warning(self, i18n.t("connect"), i18n.t("serial_open_failed", error=str(e)))
                return
            self._udp_send = None
            self._connection_status = f"串口: {port} @ {baud}"
            self._drone_trajectories.clear()
            self._current_run_start_ts = time.time()
            self._append_log_line(f"已连接串口 {port} @ {baud}，等待数据…")
            if format_cmd_raw:
                self._append_log_line("已向设备发送格式指令。")
            else:
                self._append_log_line("未发送格式指令。")
            if request_stream and _MAVLINK_AVAILABLE and self._serial_send:
                # 真实飞控：先发 GCS HEARTBEAT 让飞控识别地面站，再延迟发送数据流请求
                self._send_serial_gcs_heartbeat()
                QTimer.singleShot(1500, self._send_serial_mavlink_stream_requests)
        self._update_connection_status()

    def _do_disconnect(self):
        self._save_current_trajectory_run()
        if self._serial_heartbeat_timer is not None:
            try:
                self._serial_heartbeat_timer.stop()
            except Exception:
                pass
            self._serial_heartbeat_timer = None
        self._disconnect()
        self._disconnect_serial()
        self._udp_send = None
        self._serial_send = None
        self._connection_status = "未连接"
        self._update_connection_status()
        self._append_log_line("已断开连接")

    def _open_log_window(self):
        if self._log_window is None:
            self._log_window = LogViewerWindow(self)
            self._log_window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self._log_window.set_content("\n".join(self._log_buffer))
        self._log_window.showNormal()
        self._log_window.raise_()
        self._log_window.activateWindow()

    def _open_raw_message_window(self):
        """打开原始报文窗口，显示已收到的报文；打开后新报文会实时追加。"""
        if self._raw_message_window is None:
            self._raw_message_window = RawMessageWindow(self)
            self._raw_message_window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self._raw_message_window.set_content("\n".join(self._realtime_buffer))
        self._raw_message_window.set_parsed_content("\n".join(self._parsed_buffer))
        self._raw_message_window.showNormal()
        self._raw_message_window.raise_()
        self._raw_message_window.activateWindow()

    def _open_link_stats(self):
        """打开链接统计对话框。"""
        if self._link_stats_window is None:
            self._link_stats_window = LinkStatisticsDialog(self, self._link_stats)
            self._link_stats_window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
            self._link_stats_window.destroyed.connect(lambda: setattr(self, "_link_stats_window", None))
        self._link_stats_window.showNormal()
        self._link_stats_window.raise_()
        self._link_stats_window.activateWindow()
        self._link_stats_window._refresh()

    def _open_trajectory_3d(self):
        """打开 3D 轨迹窗口，显示当前轨迹数据。点格式 (ts, lat, lon, alt, roll, pitch, yaw)。"""
        if self._trajectory_3d_window is None:
            self._trajectory_3d_window = Trajectory3DWidget(self)
            self._trajectory_3d_window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
            self._trajectory_3d_window.destroyed.connect(lambda: setattr(self, "_trajectory_3d_window", None))
        traj_for_3d = {did: [(p[1], p[2], p[3]) for p in points] for did, points in self._drone_trajectories.items()}
        self._trajectory_3d_window.set_trajectories(traj_for_3d)
        self._trajectory_3d_window.showNormal()
        self._trajectory_3d_window.raise_()
        self._trajectory_3d_window.activateWindow()

    def get_search_rows(self):
        """供「记录与轨迹」对话框调用：从数据库检索记录并返回列表。"""
        if not self.conn:
            return []
        with self._db_lock:
            return database.search(self.conn, limit=200)

    def _open_records_and_trajectory(self):
        """打开记录检索与轨迹管理对话框（从主界面进入）。"""
        if getattr(self, "_records_dialog", None) is None:
            self._records_dialog = RecordsAndTrajectoryDialog(self)
            self._records_dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self._records_dialog.showNormal()
        self._records_dialog.raise_()
        self._records_dialog.activateWindow()


    def _update_state_panel(self):
        """用当前单机状态更新「无人机状态」面板。"""
        info = None
        if self._drone_current:
            info = next(iter(self._drone_current.values()))
        if info is None:
            self.state_flight_mode.setText("—")
            self.state_arm.setText("—")
            self.state_battery.setText("—")
            self.state_attitude.setText("Roll — Pitch — Yaw —")
            self.state_heading_nose.setText("—")
            self.state_heading_course.setText("—")
            self.state_airspeed.setText("—")
            self.state_groundspeed.setText("—")
            self.state_alt.setText("—")
            self.state_lat.setText("—")
            self.state_lon.setText("—")
            self.state_gnss.setText("—")
            cur = self.attitude_stacked.currentWidget()
            cur.set_attitude(0, 0)
            if hasattr(cur, "set_flight_data"):
                cur.set_flight_data({"gui_theme": self.config.get("gui_theme", "dark")})
            return
        self.state_flight_mode.setText(str(info.get("flight_mode") or "—"))
        self.state_arm.setText(i18n.t("yes") if info.get("arm_state") else i18n.t("no"))
        bat = info.get("battery_remaining", -1)
        bat_v = info.get("battery_voltage")
        if bat_v is not None:
            self.state_battery.setText(f"{bat_v} V" + (f" ({bat}%)" if bat >= 0 else ""))
        elif bat >= 0:
            self.state_battery.setText(f"{bat}%")
        else:
            self.state_battery.setText("—")
        r, p, y = info.get("roll", 0), info.get("pitch", 0), info.get("yaw", 0)
        self.state_attitude.setText(f"Roll {r:.1f}° Pitch {p:.1f}° Yaw {y:.1f}°")
        yaw_deg = info.get("yaw")
        heading_deg = info.get("heading")
        self.state_heading_nose.setText(f"{yaw_deg:.1f}°" if yaw_deg is not None else "—")
        self.state_heading_course.setText(f"{heading_deg:.1f}°" if heading_deg is not None else "—")
        air = info.get("airspeed")
        gnd = info.get("groundspeed")
        self.state_airspeed.setText(f"{air:.1f} m/s" if air is not None else "—")
        self.state_groundspeed.setText(f"{gnd:.1f} m/s" if gnd is not None else "—")
        alt = info.get("alt")
        self.state_alt.setText(f"{alt:.0f} m" if alt is not None else "—")
        lat = info.get("lat")
        lon = info.get("lon")
        self.state_lat.setText(f"{lat:.6f}°" if lat is not None else "—")
        self.state_lon.setText(f"{lon:.6f}°" if lon is not None else "—")
        sat = info.get("satellites_visible")
        fix_type = info.get("gps_fix_type")
        if sat is not None:
            self.state_gnss.setText(i18n.t("gnss_count_fmt", n=sat) + (f" (fix={fix_type})" if fix_type is not None else ""))
        else:
            self.state_gnss.setText("—")
        cur = self.attitude_stacked.currentWidget()
        cur.set_attitude(r, p)
        if hasattr(cur, "set_flight_data"):
            data = dict(info)
            data.setdefault("gui_theme", self.config.get("gui_theme", "dark"))
            cur.set_flight_data(data)

    def _format_drone_popup_html(self, info: dict) -> str:
        """根据探测信息生成地图弹窗 HTML（点击图标时展示全部信息，含操作者关联）。"""
        def esc(s):
            return str(s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        did = esc(info.get("drone_id", ""))
        ua_type = esc(info.get("type") or "—")
        lat = info.get("lat")
        lon = info.get("lon")
        alt = info.get("alt")
        speed = info.get("speed")
        heading = info.get("heading")
        ts = esc(info.get("timestamp") or "—")
        lat_str = f"{lat:.6f}" if lat is not None else "—"
        lon_str = f"{lon:.6f}" if lon is not None else "—"
        alt_str = f"{alt:.1f} m" if alt is not None else "—"
        speed_str = f"{speed:.1f} m/s" if speed is not None else "—"
        heading_str = f"{heading:.1f}°" if heading is not None else "—"
        lines = [
            "<b>—— 无人机 ——</b>",
            f"<b>识别号</b>: {did}",
            f"<b>机型</b>: {ua_type}",
            f"<b>纬度</b>: {lat_str}",
            f"<b>经度</b>: {lon_str}",
            f"<b>高度</b>: {alt_str}",
            f"<b>速度</b>: {speed_str}",
            f"<b>航向</b>: {heading_str}",
            f"<b>时间戳</b>: {ts}",
        ]
        if "roll" in info or "pitch" in info or "yaw" in info:
            lines.append("<b>—— 姿态 ——</b>")
            lines.append(f"<b>Roll</b>: {info.get('roll', 0):.1f}° <b>Pitch</b>: {info.get('pitch', 0):.1f}° <b>Yaw</b>: {info.get('yaw', 0):.1f}°")
        if "arm_state" in info or "flight_mode" in info or info.get("battery_remaining", -1) >= 0 or info.get("battery_voltage") is not None:
            lines.append("<b>—— 状态 ——</b>")
            if "arm_state" in info:
                lines.append(f"<b>{i18n.t('armed')}</b>: {i18n.t('yes') if info['arm_state'] else i18n.t('no')}")
            if info.get("flight_mode") not in (None, ""):
                lines.append(f"<b>飞行模式</b>: {esc(str(info['flight_mode']))}")
            bat_v = info.get("battery_voltage")
            bat = info.get("battery_remaining", -1)
            if bat_v is not None:
                lines.append(f"<b>电量</b>: {bat_v} V" + (f" ({bat}%)" if bat >= 0 else ""))
            elif bat >= 0:
                lines.append(f"<b>电量</b>: {bat}%")
            if "climb_rate" in info:
                lines.append(f"<b>爬升率</b>: {info['climb_rate']:.1f} m/s")
        op_lat = info.get("operator_lat")
        op_lon = info.get("operator_lon")
        op_alt = info.get("operator_alt", 0)
        if op_lat is not None and op_lon is not None:
            lines.append("<b>—— 关联操作者 ——</b>")
            lines.append(f"<b>操作者纬度</b>: {op_lat:.6f}")
            lines.append(f"<b>操作者经度</b>: {op_lon:.6f}")
            lines.append(f"<b>操作者高度</b>: {op_alt:.1f} m")
            lines.append("<small>点击本机或地图上「操」图标可联动高亮</small>")
        else:
            lines.append("<b>—— 关联操作者 ——</b>")
            lines.append("无")
        return "<br/>".join(lines)

    def _append_realtime_to_buffer(self, text: str, source: str):
        from datetime import datetime
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        for line in (text or "").strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            self._realtime_buffer.append(f"[{ts}] [{source}] {line}")
            if self._raw_message_window and self._raw_message_window.isVisible():
                self._raw_message_window.append(self._realtime_buffer[-1])
        while len(self._realtime_buffer) > self._realtime_buffer_max:
            self._realtime_buffer.pop(0)

    def _process_records(self, records: list[dict], source: str):
        """处理一批记录：单机模式只取第一条，入库、地图、轨迹（不裁剪），刷新状态。"""
        import time as tmod
        if not records:
            return
        record = records[0]
        record.setdefault("ts", tmod.time())
        if self.conn and record.get("lat") is not None and record.get("lon") is not None:
            with self._db_lock:
                database.insert_record(self.conn, record)
        self._target_system = record.get("system_id", 1)
        self._target_component = record.get("component_id", 1)
        did = record["drone_id"]
        ua_type = record.get("type", "")
        info = {
            "drone_id": did,
            "lat": record["lat"],
            "lon": record["lon"],
            "alt": record.get("alt", 0),
            "type": ua_type,
            "speed": record.get("speed", 0),
            "heading": record.get("heading", 0),
            "timestamp": record.get("timestamp", ""),
        }
        for key in ("roll", "pitch", "yaw", "heading", "arm_state", "flight_mode", "battery_remaining", "battery_voltage", "climb_rate", "airspeed", "groundspeed", "satellites_visible", "gps_fix_type"):
            if key in record:
                info[key] = record[key]
        if "operator_lat" in record and "operator_lon" in record:
            info["operator_lat"] = record["operator_lat"]
            info["operator_lon"] = record["operator_lon"]
            info["operator_alt"] = record.get("operator_alt", 0)
            self._operator_by_drone[did] = {
                "lat": record["operator_lat"],
                "lon": record["operator_lon"],
                "alt": record.get("operator_alt", 0),
            }
        info["height_alarm"] = False
        info["no_global_position"] = record.get("no_global_position", False)
        self._drone_current = {did: info}
        has_position = record.get("lat") is not None and record.get("lon") is not None
        if has_position:
            if self.follow_map_cb.isChecked():
                self.map_widget.set_center(record["lat"], record["lon"])
            popup_html = self._format_drone_popup_html(info)
            self.map_widget.update_drone(
                did,
                record["lat"],
                record["lon"],
                record.get("alt", 0),
                type=ua_type,
                detail_html=popup_html,
                operator_lat=info.get("operator_lat"),
                operator_lon=info.get("operator_lon"),
                alarm_area=False,
                height_alarm=False,
                heading=info.get("yaw", info.get("heading", 0)),
            )
            if "operator_lat" in record and "operator_lon" in record:
                self.map_widget.update_operator(
                    did,
                    record["operator_lat"],
                    record["operator_lon"],
                    record.get("operator_alt", 0),
                )
            if did not in self._drone_trajectories:
                self._drone_trajectories[did] = []
            pt = (
                record["ts"],
                record["lat"],
                record["lon"],
                record.get("alt", 0),
                record.get("roll", 0),
                record.get("pitch", 0),
                record.get("yaw", 0),
            )
            self._drone_trajectories[did].append(pt)
            self.map_widget.update_drone_trajectory(did, [(p[1], p[2]) for p in self._drone_trajectories[did]])
        self._update_state_panel()

    def _on_message_received(self, raw_text: str, source: str):
        """主线程：写原始日志、更新实时报文区、回调、解析并入库/地图/报警。"""
        try:
            if not raw_text or not raw_text.strip():
                return
            if self.raw_log_file:
                self.raw_log_file.write(raw_text)
                if not raw_text.endswith("\n"):
                    self.raw_log_file.write("\n")
                self.raw_log_file.flush()
            self._append_realtime_to_buffer(raw_text, source)
            for cb in self._receive_callbacks:
                try:
                    cb(raw_text, source)
                except Exception as e:
                    logger.exception("receive_callback: %s", e)
            import time as t
            records = []
            for line in raw_text.strip().split("\n"):
                line = line.strip()
                if not line:
                    continue
                record = parse_drone_message(line)
                if record is not None:
                    record["ts"] = t.time()
                    records.append(record)
            if records:
                self._process_records(records, source)
        except Exception as e:
            logger.exception("_on_message_received: %s", e)

    def _open_raw_log(self):
        if self.raw_log_file:
            try:
                self.raw_log_file.close()
            except Exception:
                pass
        path = self.logs_dir / f"raw_{time.strftime('%Y%m%d')}.log"
        self.raw_log_file = open(path, "a", encoding="utf-8")

    def _setup_log_handler(self):
        class TextEditHandler(logging.Handler):
            def __init__(self, signal):
                super().__init__()
                self._signal = signal

            def emit(self, record):
                try:
                    msg = self.format(record)
                    self._signal.emit(msg)
                except Exception:
                    pass
        self._log_handler = TextEditHandler(self.log_line_ready)
        self._log_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logging.getLogger().addHandler(self._log_handler)
        self.log_line_ready.connect(self._append_log_line)

    def _append_log_line(self, msg: str):
        self._log_buffer.append(msg)
        if len(self._log_buffer) > self._log_buffer_max:
            self._log_buffer.pop(0)
        if self._log_window and self._log_window.isVisible():
            self._log_window.append(msg)

    def _on_layer_change(self):
        p = self.provider_combo.currentText()
        l = self.layer_combo.currentText()
        self.map_widget.set_tile_layer(p, l)
        QTimer.singleShot(400, self._redraw_drone_trajectories)
        QTimer.singleShot(450, self._redraw_drone_markers)
    def _on_map_ready(self):
        """地图就绪。"""
        QTimer.singleShot(400, self._redraw_drone_trajectories)
        QTimer.singleShot(450, self._redraw_drone_markers)
    def _redraw_drone_trajectories(self):
        """切换底图后重新绘制各无人机轨迹线。点格式 (ts, lat, lon, alt, roll, pitch, yaw)。"""
        for did, points in self._drone_trajectories.items():
            if len(points) >= 2:
                self.map_widget.update_drone_trajectory(did, [(p[1], p[2]) for p in points])

    def _redraw_drone_markers(self):
        """切换底图后重新绘制各无人机图标与弹窗，并恢复操作者标记与关联高亮。"""
        for did, info in self._drone_current.items():
            if info.get("lat") is None or info.get("lon") is None:
                continue  # 无全球位置时不更新地图上的点
            # 重绘时补全操作者高度（来自 _operator_by_drone），保证弹窗完整信息
            info_for_popup = dict(info)
            if did in self._operator_by_drone:
                info_for_popup["operator_alt"] = self._operator_by_drone[did].get("alt", 0)
            popup_html = self._format_drone_popup_html(info_for_popup)
            self.map_widget.update_drone(
                did,
                info["lat"],
                info["lon"],
                info.get("alt", 0),
                type=info.get("type", ""),
                detail_html=popup_html,
                operator_lat=info.get("operator_lat"),
                operator_lon=info.get("operator_lon"),
                alarm_area=False,
                height_alarm=info.get("height_alarm", False),
                heading=info.get("yaw", info.get("heading", 0)),
            )
        for did, pos in self._operator_by_drone.items():
            self.map_widget.update_operator(did, pos["lat"], pos["lon"], pos.get("alt", 0))

    def _send_serial_gcs_heartbeat(self):
        """发送 GCS HEARTBEAT，让飞控识别地面站并开始下传遥测（多数飞控仅对已连接 GCS 发数据）。"""
        send_fn = self._serial_send
        if not send_fn or not _MAVLINK_AVAILABLE:
            return
        try:
            from pymavlink.dialects.v20 import ardupilotmega as mav
            # MAV_TYPE_GCS=6, MAV_AUTOPILOT_INVALID=8, base_mode=0, custom_mode=0, system_status=MAV_STATE_ACTIVE=4
            m = mav.MAVLink(None, srcSystem=255, srcComponent=1)
            pkt = m.heartbeat_encode(6, 8, 0, 0, 4)
            data = pkt.pack(m)
            send_fn(data)
            self._link_stats.add_tx(len(data), 1)
            self._append_log_line("已发送 GCS HEARTBEAT")
            # 串口连接时定期发送 HEARTBEAT 保持“已连接”状态
            if self._serial_heartbeat_timer is not None:
                try:
                    self._serial_heartbeat_timer.stop()
                except Exception:
                    pass
            self._serial_heartbeat_timer = QTimer(self)
            self._serial_heartbeat_timer.timeout.connect(self._send_serial_gcs_heartbeat_once)
            self._serial_heartbeat_timer.start(1000)
        except Exception as e:
            logger.warning("Send GCS heartbeat failed: %s", e)

    def _send_serial_gcs_heartbeat_once(self):
        """定时器回调：仅发送一次 HEARTBEAT 包（不重启定时器）。"""
        send_fn = self._serial_send
        if not send_fn or not _MAVLINK_AVAILABLE:
            return
        try:
            from pymavlink.dialects.v20 import ardupilotmega as mav
            m = mav.MAVLink(None, srcSystem=255, srcComponent=1)
            pkt = m.heartbeat_encode(6, 8, 0, 0, 4)
            data = pkt.pack(m)
            send_fn(data)
            self._link_stats.add_tx(len(data), 1)
        except Exception:
            pass

    def _send_serial_mavlink_stream_requests(self):
        """串口连接后发送 MAVLink 数据流请求，使飞控按设定帧率发送遥测（REQUEST_DATA_STREAM + 可选 SET_MESSAGE_INTERVAL）。"""
        send_fn = self._serial_send
        if not send_fn or not _MAVLINK_AVAILABLE:
            return
        try:
            from pymavlink.dialects.v20 import ardupilotmega as mav
            rate_hz = max(1, min(50, int(self.config.get("serial_stream_rate_hz", 5))))
            target_system = getattr(self, "_target_system", 1)
            # 真实飞控常用 component 1（AUTOPILOT）
            target_component = getattr(self, "_target_component", 1)
            m = mav.MAVLink(None, srcSystem=255, srcComponent=1)
            # REQUEST_DATA_STREAM：请求流 0（全部）按 rate_hz 发送，start_stop=1 开启
            msg = m.request_data_stream_encode(target_system, target_component, 0, rate_hz, 1)
            pkt = msg.pack(m)
            send_fn(pkt)
            self._link_stats.add_tx(len(pkt), 1)
            self._append_log_line(f"已发送 REQUEST_DATA_STREAM(流=全部, {rate_hz}Hz)")
            if self.config.get("serial_use_set_message_interval"):
                interval_us = int(self.config.get("serial_message_interval_us", 200000))
                MAV_CMD_SET_MESSAGE_INTERVAL = 511
                for msg_id in (0, 1, 24, 30, 33, 74):
                    cmd = m.command_long_encode(
                        target_system, target_component,
                        MAV_CMD_SET_MESSAGE_INTERVAL, 0,
                        float(msg_id), float(interval_us), 0, 0, 0, 0, 0,
                    )
                    pkt_cmd = cmd.pack(m)
                    send_fn(pkt_cmd)
                    self._link_stats.add_tx(len(pkt_cmd), 1)
                self._append_log_line(f"已发送 SET_MESSAGE_INTERVAL(间隔={interval_us}us)")
        except Exception as e:
            logger.warning("Send serial MAVLink stream request failed: %s", e)

    def _send_mavlink_command_long(self, command: int, param1: float = 0, param2: float = 0, param3: float = 0, param4: float = 0, param5: float = 0, param6: float = 0, param7: float = 0) -> bool:
        """通过当前连接发送 MAVLink COMMAND_LONG，目标为 _target_system/_target_component。"""
        send_fn = self._udp_send or self._serial_send
        if not send_fn or not _MAVLINK_AVAILABLE:
            return False
        try:
            from pymavlink.dialects.v20 import ardupilotmega as mav
            gcs = mav.MAVLink(None, srcSystem=255, srcComponent=1)
            msg = gcs.command_long_encode(
                self._target_system,
                self._target_component,
                command,
                0,
                param1, param2, param3, param4, param5, param6, param7,
            )
            packet = msg.pack(gcs)
            send_fn(packet)
            self._link_stats.add_tx(len(packet), 1)
            hex_str = " ".join(f"{b:02x}" for b in packet)
            self._append_realtime_to_buffer(f"SEND {hex_str}", "TX")
            if self.raw_log_file:
                self.raw_log_file.write(f"SEND {hex_str}\n")
                self.raw_log_file.flush()
            if _MAVLINK_AVAILABLE:
                try:
                    from datetime import datetime
                    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                    for one in decode_mavlink_to_annotated(packet):
                        parsed_line = f"[{ts}] [TX] {one}"
                        self._parsed_buffer.append(parsed_line)
                        while len(self._parsed_buffer) > self._parsed_buffer_max:
                            self._parsed_buffer.pop(0)
                        if self._raw_message_window and self._raw_message_window.isVisible():
                            self._raw_message_window.append_parsed(parsed_line)
                except Exception as e:
                    logger.debug("decode_mavlink_to_annotated(send): %s", e)
            return True
        except Exception as e:
            logger.warning("Send MAVLink command failed: %s", e)
            return False

    def _on_arm_click(self):
        """解锁/上锁：发送 ARM_DISARM，param1=1 解锁，0 上锁。"""
        # MAV_CMD_COMPONENT_ARM_DISARM = 400
        if self._send_mavlink_command_long(400, 1):
            self._append_log_line("已发送解锁指令")
        else:
            QMessageBox.warning(self, "控制", "未连接或发送失败")

    def _on_takeoff_click(self):
        """起飞：发送 NAV_TAKEOFF。"""
        # MAV_CMD_NAV_TAKEOFF = 22
        if self._send_mavlink_command_long(22):
            self._append_log_line("已发送起飞指令")
        else:
            QMessageBox.warning(self, "控制", "未连接或发送失败")

    def _on_land_click(self):
        """降落：发送 NAV_LAND。"""
        # MAV_CMD_NAV_LAND = 21
        if self._send_mavlink_command_long(21):
            self._append_log_line("已发送降落指令")
        else:
            QMessageBox.warning(self, "控制", "未连接或发送失败")

    def _on_rtl_click(self):
        """返航：发送 NAV_RETURN_TO_LAUNCH。"""
        # MAV_CMD_NAV_RETURN_TO_LAUNCH = 20
        if self._send_mavlink_command_long(20):
            self._append_log_line("已发送返航指令")
        else:
            QMessageBox.warning(self, "控制", "未连接或发送失败")

        def on_bounds(lat_min, lat_max, lon_min, lon_max):
            bounds = (lat_min, lat_max, lon_min, lon_max) if all(v is not None for v in (lat_min, lat_max, lon_min, lon_max)) else None
            dlg = OfflineDownloadDialog(self, bounds=bounds)
            dlg.exec()
        self.map_widget.get_map_bounds(on_bounds)

    def _screenshot(self):
        path = self.screenshots_dir / f"screen_{time.strftime('%Y%m%d_%H%M%S')}.png"
        pix = self.grab()
        if pix.save(str(path)):
            self._append_log_line(f"截图已保存: {path}")
            logger.info("Screenshot saved: %s", path)
        else:
            QMessageBox.warning(self, "截图", "保存失败")


    def _on_udp_data(self, data: bytes, addr: str):
        """UDP 收包回调（在后台线程），通过信号转到主线程处理。"""
        try:
            if data:
                self._link_stats.add_rx(len(data), 1)
            source = f"UDP:{addr}"
            if data:
                self.raw_packet_received.emit(data, source)
            if self._mavlink_parser is not None and data:
                records = list(self._mavlink_parser.feed(data))
                if records:
                    self.mavlink_records_received.emit(records, source)
                    return
            text = data.decode("utf-8", errors="replace")
            self.message_received.emit(text, source)
        except Exception as e:
            logger.exception("_on_udp_data: %s", e)

    @pyqtSlot(bytes, str)
    def _on_raw_packet_received(self, data: bytes, source: str):
        """主线程：将收到的 MAVLink 原始字节以十六进制写入原始报文窗口；解码后写入解析注释标签页。"""
        from datetime import datetime
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        hex_str = " ".join(f"{b:02x}" for b in data)
        line = f"RECV {hex_str}"
        self._append_realtime_to_buffer(line, source)
        if self.raw_log_file:
            try:
                self.raw_log_file.write(line + "\n")
                self.raw_log_file.flush()
            except (ValueError, OSError):
                self.raw_log_file = None
        if data and _MAVLINK_AVAILABLE:
            try:
                decoded = decode_mavlink_to_annotated(data)
                for one in decoded:
                    parsed_line = f"[{ts}] [{source}] {one}"
                    self._parsed_buffer.append(parsed_line)
                    while len(self._parsed_buffer) > self._parsed_buffer_max:
                        self._parsed_buffer.pop(0)
                    if self._raw_message_window and self._raw_message_window.isVisible():
                        self._raw_message_window.append_parsed(parsed_line)
            except Exception as e:
                logger.debug("decode_mavlink_to_annotated: %s", e)

    @pyqtSlot(list, str)
    def _on_mavlink_records_received(self, records: list, source: str):
        """主线程：MAVLink 解析结果，入库与地图（原始报文由 _on_raw_packet_received 写入）。"""
        import time
        for r in records:
            r["ts"] = time.time()
        self._process_records(records, source)

    def _save_current_trajectory_run(self):
        """将当前连接期间的一条轨迹保存到数据库（单机一次运行一条）。"""
        if not self._drone_trajectories or not self.conn or self._current_run_start_ts is None:
            return
        did = next(iter(self._drone_trajectories.keys()))
        points = self._drone_trajectories[did]
        if len(points) < 2:
            return
        from datetime import datetime
        start_ts = points[0][0]
        name = "起飞 " + datetime.fromtimestamp(start_ts).strftime("%Y-%m-%d %H:%M")
        end_ts = points[-1][0]
        with self._db_lock:
            run_id = database.trajectory_insert_run(self.conn, name, start_ts, end_ts, did)
            database.trajectory_insert_points(self.conn, run_id, points)
        self._append_log_line(f"已保存轨迹记录: {name} ({len(points)} 点)")

    def _disconnect(self):
        if self.udp_stop:
            self.udp_stop()
            self.udp_stop = None
        logger.info("UDP disconnected")

    def _disconnect_serial(self):
        if self.serial_stop:
            self.serial_stop()
            self.serial_stop = None
        logger.info("Serial disconnected")

    def closeEvent(self, event):
        self._save_current_trajectory_run()
        if self.udp_stop:
            self.udp_stop()
        if self.serial_stop:
            self.serial_stop()
        if self.raw_log_file:
            try:
                self.raw_log_file.close()
            except Exception:
                pass
            self.raw_log_file = None
        if self.conn:
            try:
                self.conn.close()
            except Exception:
                pass
        # 保存当前地图中心与缩放，下次启动恢复
        pending_close = [event]

        def on_map_view(lat, lon, zoom):
            if pending_close and lat is not None and lon is not None and zoom is not None:
                self.config["default_lat"] = round(lat, 6)
                self.config["default_lon"] = round(lon, 6)
                self.config["default_zoom"] = int(zoom)
                self._save_config()
            if pending_close:
                pending_close.pop().accept()

        self.map_widget.get_map_view(on_map_view)
        QTimer.singleShot(400, lambda: pending_close.pop().accept() if pending_close else None)
