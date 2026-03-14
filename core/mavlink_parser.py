# core/mavlink_parser.py
"""从 MAVLink 二进制流解析出与 parser 统一结构兼容的遥测记录（含姿态、状态扩展）。"""

import logging
import math
from typing import Iterator

logger = logging.getLogger(__name__)

# MAVLink 消息类型名
MAVLINK_MSG_IDS = {
    0: "HEARTBEAT",
    1: "SYS_STATUS",
    24: "GPS_RAW_INT",
    30: "ATTITUDE",
    33: "GLOBAL_POSITION_INT",
    74: "VFR_HUD",
    76: "COMMAND_LONG",
}

# MAV_TYPE
MAV_TYPE_NAMES = {
    0: "Generic",
    1: "Fixed wing",
    2: "Quadrotor",
    3: "Coaxial",
    4: "Helicopter",
    5: "Hexarotor",
    6: "Octorotor",
    7: "Tricopter",
    8: "Flapping wing",
    9: "Kite",
    10: "Blimp",
    11: "Heli dual",
    12: "VTOL quad",
    13: "Tiltrotor",
    14: "VTOL reserved",
    15: "VTOL tri",
    16: "Tiltwing",
    17: "VTOL tailsitter",
    18: "VTOL quadplane",
    19: "Coaxial helicopter",
    20: "Balloon",
    21: "Airship",
    22: "UAV",
    23: "Generator",
    24: "Onboard controller",
    25: "GCS",
    26: "ADSB",
    27: "Steerable parachute",
    28: "Dodecarotor",
    29: "Camera",
    30: "Charging station",
    31: "Fly-through charger",
    32: "Solar panel",
}


def _rad_to_deg(rad: float) -> float:
    return math.degrees(rad) if rad is not None else 0.0


def _cdeg_to_deg(cdeg: float) -> float:
    """centidegrees to degrees"""
    return (cdeg / 100.0) if cdeg is not None else 0.0


class MavLinkParser:
    """维护 MAVLink 解码器与每架机（system_id）的状态，输出统一结构记录。"""

    def __init__(self):
        try:
            from pymavlink.dialects.v20 import ardupilotmega as mavlink
        except ImportError:
            try:
                from pymavlink import mavutil
                mavlink = mavutil.mavlink
            except ImportError:
                mavlink = None
        if mavlink is None:
            raise ImportError("pymavlink not installed. pip install pymavlink")
        self._mav = mavlink.MAVLink(None, srcSystem=0, srcComponent=0)
        # (system_id, component_id) -> 最新各消息
        self._state: dict[tuple[int, int], dict] = {}
        # 每次收到 HEARTBEAT 即更新，供 _build_record 使用，避免与 GLOBAL_POSITION_INT 同包顺序导致未更新
        self._last_arm_state: dict[tuple[int, int], bool] = {}

    def _drone_id(self, system_id: int, component_id: int) -> str:
        return f"MAV_{system_id}_{component_id}"

    def _get_state(self, system_id: int, component_id: int) -> dict:
        key = (system_id, component_id)
        if key not in self._state:
            self._state[key] = {}
        return self._state[key]

    def feed(self, data: bytes) -> Iterator[dict]:
        """喂入二进制数据，产出统一结构记录（每收到 GLOBAL_POSITION_INT 且可合并状态时产出一条）。"""
        for i in range(len(data)):
            try:
                # pymavlink 部分版本 parse_char 需传入单字节 bytes
                b = data[i : i + 1]
                msg = self._mav.parse_char(b)
            except Exception as e:
                logger.debug("MAVLink parse_char: %s", e)
                continue
            if msg is None:
                continue
            sid, cid = msg.get_srcSystem(), msg.get_srcComponent()
            state = self._get_state(sid, cid)
            # 注意：msg_id=0 是 HEARTBEAT，不能用 "x or fallback" 否则 0 会被当成 falsy 变成 -1
            _mid = getattr(msg, "get_msgId", lambda: None)()
            msg_id = _mid if _mid is not None else getattr(msg, "_message_id", -1)
            if msg_id == 0:  # HEARTBEAT
                state["heartbeat"] = msg
                state["type"] = MAV_TYPE_NAMES.get(getattr(msg, "type", 0), "UAV")
                bm = getattr(msg, "base_mode", 0)
                state["base_mode"] = bm
                state["custom_mode"] = getattr(msg, "custom_mode", 0)
                key = (sid, cid)
                self._last_arm_state[key] = bool(int(bm) & 0x80)
            elif msg_id == 30:  # ATTITUDE
                state["attitude"] = msg
            elif msg_id == 33:  # GLOBAL_POSITION_INT
                state["global_position"] = msg
                record = self._build_record(sid, cid, state)
                if record:
                    yield record
            elif msg_id == 74:  # VFR_HUD
                state["vfr_hud"] = msg
                # 无 GLOBAL_POSITION_INT 时用 VFR_HUD+ATTITUDE 合成记录（真实飞机可能只发 ODOMETRY/VFR_HUD）
                record = self._build_record_from_vfr_hud(sid, cid, state)
                if record:
                    yield record
            elif msg_id == 141:  # ALTITUDE（部分飞控发此不发 33）
                state["altitude"] = msg
            elif msg_id == 1:  # SYS_STATUS
                state["sys_status"] = msg
            elif msg_id == 24:  # GPS_RAW_INT
                state["gps_raw_int"] = msg

    def _build_record(self, system_id: int, component_id: int, state: dict) -> dict | None:
        """根据当前状态拼出与 parser 统一结构兼容的一条记录。"""
        gp = state.get("global_position")
        if gp is None:
            return None
        lat = getattr(gp, "lat", 0) / 1e7
        lon = getattr(gp, "lon", 0) / 1e7
        alt = getattr(gp, "alt", 0) / 1000.0
        relative_alt = getattr(gp, "relative_alt", 0) / 1000.0
        hdg = _cdeg_to_deg(getattr(gp, "hdg", 0))
        vx = getattr(gp, "vx", 0) / 100.0
        vy = getattr(gp, "vy", 0) / 100.0
        vz = getattr(gp, "vz", 0) / 100.0
        # 地速 m/s
        speed = (vx * vx + vy * vy) ** 0.5

        record = {
            "drone_id": self._drone_id(system_id, component_id),
            "system_id": system_id,
            "component_id": component_id,
            "lat": lat,
            "lon": lon,
            "alt": relative_alt if relative_alt != 0 else alt,
            "speed": speed,
            "heading": hdg,
            "timestamp": str(getattr(gp, "time_boot_ms", "")),
            "type": state.get("type", "UAV"),
            "raw": "",
        }

        att = state.get("attitude")
        if att is not None:
            record["roll"] = _rad_to_deg(getattr(att, "roll", 0))
            record["pitch"] = _rad_to_deg(getattr(att, "pitch", 0))
            record["yaw"] = _rad_to_deg(getattr(att, "yaw", 0))
        else:
            record["roll"] = 0.0
            record["pitch"] = 0.0
            record["yaw"] = 0.0

        # 解锁状态：优先用每次 HEARTBEAT 更新的 _last_arm_state，保证与最新心跳一致
        key = (system_id, component_id)
        record["arm_state"] = self._last_arm_state.get(key, False)
        record["flight_mode"] = state.get("custom_mode")
        if record["flight_mode"] is None:
            record["flight_mode"] = ""

        vfr = state.get("vfr_hud")
        if vfr is not None:
            record["airspeed"] = getattr(vfr, "airspeed", 0)
            record["groundspeed"] = getattr(vfr, "groundspeed", 0)
            record["climb_rate"] = getattr(vfr, "climb", 0)
            if "throttle" in dir(vfr):
                record["throttle"] = getattr(vfr, "throttle", 0)
        else:
            record["climb_rate"] = -vz

        sys_status = state.get("sys_status")
        if sys_status is not None and hasattr(sys_status, "battery_remaining"):
            record["battery_remaining"] = getattr(sys_status, "battery_remaining", -1)
        else:
            record["battery_remaining"] = -1
        # 电压（mV），0xFFFF 表示未发送；转为 V 存储
        if sys_status is not None and hasattr(sys_status, "voltage_battery"):
            v_mv = getattr(sys_status, "voltage_battery", 0xFFFF)
            if v_mv != 0xFFFF and v_mv != 0:
                record["battery_voltage"] = round(v_mv / 1000.0, 2)
            else:
                record["battery_voltage"] = None
        else:
            record["battery_voltage"] = None

        gps_raw = state.get("gps_raw_int")
        if gps_raw is not None:
            record["satellites_visible"] = getattr(gps_raw, "satellites_visible", None)
            record["gps_fix_type"] = getattr(gps_raw, "fix_type", None)
        else:
            record["satellites_visible"] = None
            record["gps_fix_type"] = None

        return record

    def _build_record_from_vfr_hud(self, system_id: int, component_id: int, state: dict) -> dict | None:
        """当没有 GLOBAL_POSITION_INT 时，用 VFR_HUD + ATTITUDE（+ 可选 ALTITUDE）合成一条记录，供状态/姿态显示。"""
        if state.get("global_position") is not None:
            return None  # 已有全球位置，不产备用记录
        vfr = state.get("vfr_hud")
        att = state.get("attitude")
        if vfr is None or att is None:
            return None
        key = (system_id, component_id)
        alt = getattr(vfr, "alt", None)
        if alt is None:
            alt_msg = state.get("altitude")
            if alt_msg is not None:
                alt = getattr(alt_msg, "altitude_amsl", None) or getattr(alt_msg, "altitude_local", None)
        if alt is None:
            alt = 0.0
        heading = getattr(vfr, "heading", 0)
        if heading is None:
            heading = 0
        record = {
            "drone_id": self._drone_id(system_id, component_id),
            "system_id": system_id,
            "component_id": component_id,
            "lat": None,
            "lon": None,
            "alt": float(alt),
            "speed": float(getattr(vfr, "groundspeed", 0) or 0),
            "heading": float(heading),
            "timestamp": str(getattr(att, "time_boot_ms", "")),
            "type": state.get("type", "UAV"),
            "raw": "",
            "no_global_position": True,
        }
        record["roll"] = _rad_to_deg(getattr(att, "roll", 0))
        record["pitch"] = _rad_to_deg(getattr(att, "pitch", 0))
        record["yaw"] = _rad_to_deg(getattr(att, "yaw", 0))
        record["arm_state"] = self._last_arm_state.get(key, False)
        record["flight_mode"] = state.get("custom_mode") or ""
        record["airspeed"] = float(getattr(vfr, "airspeed", 0) or 0)
        record["groundspeed"] = float(getattr(vfr, "groundspeed", 0) or 0)
        record["climb_rate"] = float(getattr(vfr, "climb", 0) or 0)
        record["battery_remaining"] = -1
        record["battery_voltage"] = None
        if state.get("sys_status") is not None:
            ss = state["sys_status"]
            record["battery_remaining"] = getattr(ss, "battery_remaining", -1)
            v_mv = getattr(ss, "voltage_battery", 0xFFFF)
            if v_mv != 0xFFFF and v_mv != 0:
                record["battery_voltage"] = round(v_mv / 1000.0, 2)
        record["satellites_visible"] = None
        record["gps_fix_type"] = None
        return record


def parse_mavlink_bytes(data: bytes) -> list[dict]:
    """从一段二进制解析 MAVLink，返回统一结构记录列表。"""
    parser = MavLinkParser()
    return list(parser.feed(data))


def decode_mavlink_to_annotated(data: bytes) -> list[str]:
    """将 MAVLink 二进制包解码为带注释的文本行（每行一条消息：类型 + 字段）。"""
    lines = []
    try:
        from pymavlink.dialects.v20 import ardupilotmega as mavlink
    except ImportError:
        try:
            from pymavlink import mavutil
            mavlink = mavutil.mavlink
        except ImportError:
            return ["(pymavlink 未安装)"]
    mav = mavlink.MAVLink(None, srcSystem=0, srcComponent=0)
    for i in range(len(data)):
        try:
            b = data[i : i + 1]
            msg = mav.parse_char(b)
        except Exception:
            continue
        if msg is None:
            continue
        _mid = getattr(msg, "get_msgId", lambda: None)()
        msg_id = _mid if _mid is not None else getattr(msg, "_message_id", -1)
        name = MAVLINK_MSG_IDS.get(msg_id, f"MSG_{msg_id}")
        parts = [f"{name}"]
        try:
            d = msg.to_dict()
            for k, v in d.items():
                if not k.startswith("_") and k not in ("mavlink_version",):
                    parts.append(f"{k}={v}")
        except Exception:
            try:
                for field in getattr(msg, "get_fieldnames", lambda: [])() or []:
                    if field.startswith("_"):
                        continue
                    val = getattr(msg, field, None)
                    if val is not None:
                        parts.append(f"{field}={val}")
            except Exception:
                parts.append("(无字段)")
        lines.append(" | ".join(parts))
    return lines
