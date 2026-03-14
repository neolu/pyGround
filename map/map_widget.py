# map/map_widget.py
"""地图组件：QWebEngineView + Leaflet，支持图商/图层切换与无人机标记。"""

import json
import logging
from pathlib import Path

from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtCore import QUrl, QTimer, pyqtSignal
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QSizePolicy

logger = logging.getLogger(__name__)

# 图商与图层类型： (显示名, url_template, options)
# {z},{x},{y} 瓦片占位；部分图源需 key，用 MAP_KEY 占位
TILE_LAYERS = {
    "osm": {
        "road": ("OpenStreetMap 路网", "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {"attribution": "© OSM", "maxZoom": 19, "subdomains": "abc"}),
        "satellite": ("OpenStreetMap 卫星", "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", {"attribution": "© Esri", "maxZoom": 19}),
    },
    "bing": {
        "road": ("Bing 路网", "https://ecn.t{s}.tiles.virtualearth.net/tiles/r{q}.png?g=1", {"subdomains": "0123", "maxZoom": 19}),
        "satellite": ("Bing 卫星", "https://ecn.t{s}.tiles.virtualearth.net/tiles/a{q}.png?g=1", {"subdomains": "0123", "maxZoom": 19}),
    },
    "gaode": {
        "road": ("高德 路网", "https://webrd0{s}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}", {"subdomains": "1234", "maxZoom": 18}),
        "satellite": ("高德 卫星", "https://webst0{s}.is.autonavi.com/appmaptile?style=6&x={x}&y={y}&z={z}", {"subdomains": "1234", "maxZoom": 18}),
    },
    "baidu": {
        "road": ("百度 路网", "https://maponline{s}.map.bdimg.com/tile/?qt=tile&x={x}&y={y}&z={z}&styles=pl&scaler=1&udt=20200325", {"subdomains": "0123", "maxZoom": 18}),
        "satellite": ("百度 卫星", "https://maponline{s}.map.bdimg.com/tile/?qt=vtile&x={x}&y={y}&z={z}&styles=sl&scaler=1&udt=20200325", {"subdomains": "0123", "maxZoom": 18}),
    },
    "google": {
        "road": ("Google 全球路网", "https://mt{s}.google.com/vt?lyrs=m&x={x}&y={y}&z={z}", {"subdomains": "0123", "maxZoom": 20, "attribution": "© Google"}),
        "satellite": ("Google 全球卫星", "https://mt{s}.google.com/vt?lyrs=s&x={x}&y={y}&z={z}", {"subdomains": "0123", "maxZoom": 20, "attribution": "© Google"}),
    },
    "google_cn": {
        "road": ("Google 中国路网", "https://mt{s}.google.com/vt?lyrs=m&x={x}&y={y}&z={z}&hl=zh-CN", {"subdomains": "0123", "maxZoom": 20, "attribution": "© Google"}),
        "satellite": ("Google 中国卫星", "https://mt{s}.google.com/vt?lyrs=s&x={x}&y={y}&z={z}&hl=zh-CN", {"subdomains": "0123", "maxZoom": 20, "attribution": "© Google"}),
    },
}


class MapWidget(QWidget):
    """地图加载完成、可绘制图层时发出，用于主窗口加载报警点等。"""
    map_ready = pyqtSignal()

    def __init__(self, default_lat: float = 31.2304, default_lon: float = 121.4737, default_zoom: int = 14, parent=None):
        super().__init__(parent)
        self.default_lat = default_lat
        self.default_lon = default_lon
        self.default_zoom = default_zoom
        self._view = QWebEngineView()
        self._view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._view.setMinimumHeight(380)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._view)
        self._html_path = Path(__file__).parent / "index.html"
        self._load_finished = False
        self._load_map()

    def _load_map(self):
        if self._html_path.exists():
            html = self._html_path.read_text(encoding="utf-8")
            # 使用 http 避免混合内容：页面若为 https 会阻止加载 http://127.0.0.1 的离线瓦片
            base_url = QUrl("http://example.com/")
            self._view.setHtml(html, base_url)
            self._view.loadFinished.connect(self._on_load_finished)
        else:
            self._view.setHtml("<p>index.html not found.</p>")

    def _on_load_finished(self, ok: bool):
        if ok and not self._load_finished:
            self._load_finished = True
            self.set_tile_layer("osm", "road")
            for delay in (200, 500, 1000):
                QTimer.singleShot(delay, self._invalidate_map_size)
            QTimer.singleShot(1200, self._emit_map_ready)

    def _emit_map_ready(self):
        """地图与底图就绪后发出信号，主窗口可在此后绘制报警点等。"""
        self.map_ready.emit()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(80, self._invalidate_map_size)

    def _invalidate_map_size(self):
        """布局稳定后让 Leaflet 重新计算地图尺寸，避免地图区域为 0 不显示。"""
        self.run_js("if (typeof window.map !== 'undefined' && window.map) window.map.invalidateSize();")

    def run_js(self, script: str):
        self._view.page().runJavaScript(script)

    def get_map_bounds(self, callback):
        """异步获取当前地图可视范围，回调参数为 (lat_min, lat_max, lon_min, lon_max)，若地图未就绪则为 (None, None, None, None)。"""
        def on_result(result):
            if result and len(result) == 4:
                try:
                    callback(float(result[0]), float(result[1]), float(result[2]), float(result[3]))
                except (TypeError, ValueError):
                    callback(None, None, None, None)
            else:
                callback(None, None, None, None)
        self._view.page().runJavaScript(
            "(function(){ if (!window.map) return null; var b = window.map.getBounds(); return [b.getSouth(), b.getNorth(), b.getWest(), b.getEast()]; })()",
            on_result,
        )

    def get_map_view(self, callback):
        """异步获取当前地图中心与缩放，回调参数为 (lat, lon, zoom)，若地图未就绪则为 (None, None, None)。"""
        def on_result(result):
            if result and len(result) == 3:
                try:
                    callback(float(result[0]), float(result[1]), int(result[2]))
                except (TypeError, ValueError):
                    callback(None, None, None)
            else:
                callback(None, None, None)
        self._view.page().runJavaScript(
            "(function(){ if (!window.map) return null; var c = window.map.getCenter(); return [c.lat, c.lng, window.map.getZoom()]; })()",
            on_result,
        )

    def set_tile_layer(self, provider: str, layer: str):
        info = TILE_LAYERS.get(provider, {}).get(layer)
        center = [self.default_lat, self.default_lon]
        if not info:
            self.run_js(f"initMap({json.dumps(center)}, {self.default_zoom}, null, null);")
            return
        name, url, opts = info
        opts_json = json.dumps(opts)
        self.run_js(f"""
            (function(){{
              if (typeof initMap === 'function')
                initMap({json.dumps(center)}, {self.default_zoom}, {json.dumps(url)}, {opts_json});
            }})();
        """)

    def set_view(self, lat: float, lon: float, zoom: int | None = None):
        z = zoom if zoom is not None else self.default_zoom
        self.run_js(f"if (typeof setView === 'function') setView({lat}, {lon}, {z});")

    def set_center(self, lat: float, lon: float):
        """将地图中心移至指定经纬度，保持当前缩放级别不变。"""
        self.run_js(
            f"(function(){{ if (window.map) window.map.setView([{lat}, {lon}], window.map.getZoom()); }})();"
        )

    def update_drone(self, drone_id: str, lat: float, lon: float, alt: float = 0, **kwargs):
        tid = drone_id.replace("'", "\\'")
        tooltip = f"{drone_id} alt:{alt}m"
        ua_type = kwargs.get("type", "")
        detail_html = kwargs.get("detail_html", "")
        op_lat = kwargs.get("operator_lat")
        op_lon = kwargs.get("operator_lon")
        alarm_area = kwargs.get("alarm_area", False)
        height_alarm = kwargs.get("height_alarm", False)
        heading = kwargs.get("heading", 0)  # 航向角 0~360，用于箭头指向
        props = f"tooltip: {json.dumps(tooltip)}, type: {json.dumps(ua_type)}, alarmArea: {str(alarm_area).lower()}, heightAlarm: {str(height_alarm).lower()}, heading: {float(heading)}"
        if op_lat is not None and op_lon is not None:
            props += f", operatorLat: {op_lat}, operatorLon: {op_lon}"
        self.run_js(f"if (typeof updateDrone === 'function') updateDrone({json.dumps(tid)}, {lat}, {lon}, {alt}, {{{props}}});")
        # 单独设置弹窗内容，避免与 updateDrone 参数一起传时被截断或转义导致只显示 tooltip
        if detail_html and detail_html.strip():
            self.run_js(
                "if (typeof setDronePopupContent === 'function') setDronePopupContent("
                + json.dumps(tid) + ", "
                + json.dumps(detail_html) + ");"
            )

    def clear_drones(self):
        self.run_js("if (typeof clearDrones === 'function') clearDrones();")


    def update_operator(self, drone_id: str, lat: float, lon: float, alt: float = 0):
        """更新或显示某架飞机对应的操作者位置标记（每机一个操作者）。"""
        self.run_js(f"if (typeof updateOperator === 'function') updateOperator({json.dumps(drone_id)}, {lat}, {lon}, {alt});")

    def update_drone_trajectory(self, drone_id: str, points: list[tuple[float, float]]):
        """更新某架无人机的轨迹线，points 为 [(lat, lon), ...]。"""
        if len(points) < 2:
            return
        arr = json.dumps([[p[0], p[1]] for p in points])
        self.run_js(f"if (typeof updateDroneTrajectory === 'function') updateDroneTrajectory({json.dumps(drone_id)}, {arr});")
