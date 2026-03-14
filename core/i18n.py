# core/i18n.py
"""轻量 i18n（方案 B）：中英文键值表与语言切换，供地面站界面可切换中文/英语。"""

from typing import Dict, Any

# 当前语言
_current_language = "zh"

# 文案键值表：key -> {"zh": "中文", "en": "English"}
_STRINGS: Dict[str, Dict[str, str]] = {
    "app_title": {"zh": "无人机地面站", "en": "UAV Ground Station"},
    "connect": {"zh": "连接", "en": "Connect"},
    "disconnect": {"zh": "断开", "en": "Disconnect"},
    "map": {"zh": "底图", "en": "Map"},
    "follow_map": {"zh": "跟随", "en": "Follow"},
    "screenshot": {"zh": "截图", "en": "Screenshot"},
    "app_log": {"zh": "应用日志", "en": "App log"},
    "raw_message": {"zh": "原始报文", "en": "Raw message"},
    "trajectory_3d": {"zh": "3D 轨迹", "en": "3D trajectory"},
    "data_search": {"zh": "数据检索", "en": "Data search"},
    "record_search": {"zh": "记录检索", "en": "Record search"},
    "records_and_trajectory": {"zh": "记录与轨迹管理", "en": "Records & trajectory"},
    "search_button": {"zh": "检索", "en": "Search"},
    "close": {"zh": "关闭", "en": "Close"},
    "drones_detected": {"zh": "无人机 ({n} 架)", "en": "UAVs ({n})"},
    "alarm_list": {"zh": "报警列表", "en": "Alarms"},
    "alarm_height_m": {"zh": "高度报警(m):", "en": "Height alarm (m):"},
    "drone_state": {"zh": "无人机状态", "en": "Drone state"},
    "flight_mode": {"zh": "飞行模式", "en": "Flight mode"},
    "armed": {"zh": "解锁", "en": "Armed"},
    "battery": {"zh": "电量", "en": "Battery"},
    "voltage": {"zh": "电压", "en": "Voltage"},
    "attitude": {"zh": "姿态", "en": "Attitude"},
    "heading_nose": {"zh": "机头方向", "en": "Heading (nose)"},
    "heading_course": {"zh": "飞行方向", "en": "Course"},
    "attitude_indicator": {"zh": "姿态仪表", "en": "Attitude indicator"},
    "airspeed": {"zh": "空速", "en": "Airspeed"},
    "groundspeed": {"zh": "地速", "en": "Groundspeed"},
    "altitude": {"zh": "高度", "en": "Altitude"},
    "latitude": {"zh": "纬度", "en": "Latitude"},
    "longitude": {"zh": "经度", "en": "Longitude"},
    "gnss_satellites": {"zh": "GNSS 卫星数", "en": "GNSS sats"},
    "gnss_count_fmt": {"zh": "{n} 颗", "en": "{n} sats"},
    "control": {"zh": "控制", "en": "Control"},
    "arm": {"zh": "解锁", "en": "Arm"},
    "takeoff": {"zh": "起飞", "en": "Takeoff"},
    "land": {"zh": "降落", "en": "Land"},
    "rtl": {"zh": "返航", "en": "RTL"},
    "trajectory_records": {"zh": "轨迹记录", "en": "Trajectory records"},
    "trajectory_playback": {"zh": "回放", "en": "Playback"},
    "trajectory_delete": {"zh": "删除", "en": "Delete"},
    "yes": {"zh": "是", "en": "Yes"},
    "no": {"zh": "否", "en": "No"},
    "language": {"zh": "语言", "en": "Language"},
    "zh": {"zh": "中文", "en": "Chinese"},
    "en": {"zh": "English", "en": "English"},
    "link_stats": {"zh": "链接统计", "en": "Link statistics"},
    "download": {"zh": "下载", "en": "Download"},
    "upload": {"zh": "上传", "en": "Upload"},
    "bytes_total": {"zh": "字节", "en": "Bytes"},
    "bytes_per_sec": {"zh": "字节/s", "en": "Bytes/s"},
    "packets": {"zh": "数据包", "en": "Packets"},
    "packets_per_sec": {"zh": "数据包/s", "en": "Packets/s"},
    "dropped": {"zh": "丢包", "en": "Dropped"},
    "quality": {"zh": "质量", "en": "Quality"},
    "max_interval_ms": {"zh": "数据包之间最大时间 (ms)", "en": "Max time between packets (ms)"},
    "reset": {"zh": "重置", "en": "Reset"},
    "settings": {"zh": "设置", "en": "Settings"},
    "attitude_display_type": {"zh": "姿态显示", "en": "Attitude display"},
    "attitude_classic": {"zh": "经典圆盘", "en": "Classic dial"},
    "attitude_pfd": {"zh": "PFD 样式", "en": "PFD style"},
    "gui_theme": {"zh": "配色", "en": "Theme"},
    "theme_dark": {"zh": "黑背景", "en": "Dark"},
    "theme_light": {"zh": "白背景", "en": "Light"},
    "ok": {"zh": "确定", "en": "OK"},
    "cancel": {"zh": "取消", "en": "Cancel"},
    "refresh_ports": {"zh": "刷新串口", "en": "Refresh ports"},
    "stop": {"zh": "停止", "en": "Stop"},
    "reset_view": {"zh": "重置视角", "en": "Reset view"},
    "connect_data_source": {"zh": "连接数据源", "en": "Connect"},
    "udp_esp32_bridge": {"zh": "UDP（ESP32 桥接 / 模拟器）", "en": "UDP (ESP32 bridge / simulator)"},
    "serial_port": {"zh": "串口", "en": "Serial port"},
    "host": {"zh": "主机", "en": "Host"},
    "port": {"zh": "端口", "en": "Port"},
    "baud_rate": {"zh": "波特率", "en": "Baud rate"},
    "no_serial_ports": {"zh": "(无串口)", "en": "(No serial ports)"},
    "select_valid_serial": {"zh": "请选择有效串口", "en": "Please select a valid serial port"},
    "already_connected_msg": {"zh": "当前已连接：{status}\n请先点击「断开」再更换连接方式。", "en": "Already connected: {status}\nPlease disconnect first to change connection."},
    "serial_open_failed": {"zh": "串口打开失败: {error}", "en": "Serial port open failed: {error}"},
    "host_placeholder": {"zh": "127.0.0.1 或 192.168.4.1", "en": "e.g. 127.0.0.1 or 192.168.4.1"},
}


def t(key: str, **kwargs: Any) -> str:
    """按当前语言取文案；kwargs 可替换占位符，如 t('drones_detected', n=3)。"""
    s = _STRINGS.get(key, {}).get(_current_language, key)
    for k, v in kwargs.items():
        s = s.replace("{" + k + "}", str(v))
    return s


def get_language() -> str:
    return _current_language


def set_language(lang: str) -> None:
    global _current_language
    if lang not in ("zh", "en"):
        lang = "zh"
    if _current_language == lang:
        return
    _current_language = lang
    if _language_changed_callback:
        _language_changed_callback(lang)


_language_changed_callback = None


def set_language_changed_callback(cb) -> None:
    """设置语言切换回调 cb(lang: str)，用于刷新界面。"""
    global _language_changed_callback
    _language_changed_callback = cb
