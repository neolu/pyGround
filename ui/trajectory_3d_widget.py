# ui/trajectory_3d_widget.py
"""3D 轨迹显示窗口：WGS84 转局部 ENU 后用 matplotlib Axes3D 绘制。"""

import logging
import warnings
from typing import Optional

# 抑制 matplotlib 因缺 CJK 字体产生的 Glyph missing 警告
warnings.filterwarnings("ignore", message=".*Glyph.*missing from font.*", category=UserWarning)

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QComboBox, QHBoxLayout
from PyQt6.QtCore import Qt

from core import i18n

logger = logging.getLogger(__name__)

try:
    import matplotlib
    matplotlib.use("QtAgg")
    # 使用支持 CJK 的字体，避免 "Glyph missing from font(s) DejaVu Sans" 警告
    matplotlib.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "SimSun", "DejaVu Sans"]
    matplotlib.rcParams["axes.unicode_minus"] = False
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
    from matplotlib.figure import Figure
    from mpl_toolkits.mplot3d import Axes3D
    _MATPLOTLIB_AVAILABLE = True
except ImportError:
    FigureCanvasQTAgg = None
    Figure = None
    Axes3D = None
    _MATPLOTLIB_AVAILABLE = False

from core.geo_utils import wgs84_to_local_enu


class Trajectory3DWidget(QWidget):
    """显示一架或多架无人机 3D 轨迹的子窗口。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowCloseButtonHint | Qt.WindowType.WindowMinMaxButtonsHint)
        self.setWindowTitle(i18n.t("trajectory_3d"))
        self.setMinimumSize(500, 450)
        self._trajectories: dict[str, list[tuple[float, float, float]]] = {}
        self._current_drone_id: Optional[str] = None
        layout = QVBoxLayout(self)
        if not _MATPLOTLIB_AVAILABLE:
            from PyQt6.QtWidgets import QLabel
            layout.addWidget(QLabel("需要安装 matplotlib 以显示 3D 轨迹。"))
            return
        self._fig = Figure(figsize=(5, 4))
        self._ax: Axes3D = self._fig.add_subplot(111, projection="3d")
        self._canvas = FigureCanvasQTAgg(self._fig)
        layout.addWidget(self._canvas)
        btn_layout = QHBoxLayout()
        self._drone_combo = QComboBox()
        self._drone_combo.setMinimumWidth(120)
        self._drone_combo.currentTextChanged.connect(self._on_drone_selected)
        btn_layout.addWidget(self._drone_combo)
        reset_btn = QPushButton(i18n.t("reset_view"))
        reset_btn.clicked.connect(self._redraw)
        btn_layout.addWidget(reset_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

    def set_trajectories(self, trajectories: dict[str, list[tuple[float, float, float]]]):
        """设置轨迹数据：drone_id -> [(lat, lon, alt), ...]。"""
        self._trajectories = {k: list(v) for k, v in trajectories.items() if len(v) >= 2}
        self._drone_combo.clear()
        self._drone_combo.addItems(list(self._trajectories.keys()))
        if self._trajectories and not self._current_drone_id:
            self._current_drone_id = next(iter(self._trajectories.keys()))
        if self._current_drone_id and self._current_drone_id in self._trajectories:
            idx = self._drone_combo.findText(self._current_drone_id)
            if idx >= 0:
                self._drone_combo.setCurrentIndex(idx)
        self._redraw()

    def _on_drone_selected(self, drone_id: str):
        self._current_drone_id = drone_id
        self._redraw()

    def _redraw(self):
        if not _MATPLOTLIB_AVAILABLE or not self._trajectories:
            return
        self._ax.clear()
        drone_id = self._drone_combo.currentText() if self._drone_combo.count() else None
        if not drone_id or drone_id not in self._trajectories:
            self._ax.set_xlabel("X (东, m)")
            self._ax.set_ylabel("Y (北, m)")
            self._ax.set_zlabel("Z (高, m)")
            self._canvas.draw()
            return
        points = self._trajectories[drone_id]
        if len(points) < 2:
            self._canvas.draw()
            return
        lat0, lon0, alt0 = points[0][0], points[0][1], points[0][2]
        enu = [wgs84_to_local_enu(p[0], p[1], p[2], lat0, lon0, alt0) for p in points]
        xs = [e[0] for e in enu]
        ys = [e[1] for e in enu]
        zs = [e[2] for e in enu]
        self._ax.plot(xs, ys, zs, "b-", linewidth=1.5, label=drone_id)
        self._ax.scatter([xs[-1]], [ys[-1]], [zs[-1]], color="r", s=40, label="当前")
        self._ax.set_xlabel("X (东, m)")
        self._ax.set_ylabel("Y (北, m)")
        self._ax.set_zlabel("Z (高, m)")
        self._ax.legend()
        self._canvas.draw()
