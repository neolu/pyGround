# core/parser.py
"""解析无人机 JSON 报文（兼容旧版 devId+data 及扁平 JSON）。"""

import json
import logging

logger = logging.getLogger(__name__)

# 机型编号 -> 名称
UATYPE_NAMES = {
    0: "未知",
    1: "固定翼",
    2: "多旋翼",
    3: "直升机",
    4: "飞艇",
    5: "气球",
}


def _parse_legacy_json(obj: dict, raw: str) -> dict | None:
    """旧版 JSON：{"devId":"...","data":{...}} 含 osid, Lon, Lat, AltGeo 等 -> 统一结构。"""
    data = obj.get("data")
    if not isinstance(data, dict):
        return None
    try:
        lat = float(data.get("Lat"))
        lon = float(data.get("Lon"))
        alt = float(data.get("AltGeo") or data.get("AltBaro") or 0)
    except (TypeError, ValueError):
        return None
    drone_id = str(data.get("osid") or data.get("id") or obj.get("devId") or "")
    uatype_num = data.get("UAType")
    ua_type = UATYPE_NAMES.get(uatype_num, str(uatype_num) if uatype_num is not None else "")
    uatime = data.get("UATime")
    timestamp = str(uatime) if uatime is not None else ""
    out = {
        "drone_id": drone_id,
        "lat": lat,
        "lon": lon,
        "alt": alt,
        "speed": float(data.get("Speed", 0)),
        "heading": float(data.get("Heading", 0)),
        "timestamp": timestamp,
        "type": ua_type.strip(),
        "raw": raw,
    }
    try:
        op_lat = data.get("Op_Lat")
        op_lon = data.get("Op_Lon")
        if op_lat is not None and op_lon is not None:
            out["operator_lat"] = float(op_lat)
            out["operator_lon"] = float(op_lon)
            out["operator_alt"] = float(data.get("Op_Alt", 0))
    except (TypeError, ValueError):
        pass
    return out


def parse_drone_message(raw: str) -> dict | None:
    """
    解析单条报文，返回统一结构；不符合则返回 None。
    支持：旧版 devId+data JSON 或扁平 JSON（drone_id, lat, lon, alt, ...）。
    """
    raw = raw.strip()
    if not raw:
        return None
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.debug("Parse error: %s", e)
        return None
    if not isinstance(obj, dict):
        return None
    # 旧版：含 devId 与 data
    if "data" in obj and isinstance(obj.get("data"), dict):
        return _parse_legacy_json(obj, raw)
    # 扁平 JSON
    try:
        lat = float(obj.get("lat"))
        lon = float(obj.get("lon"))
        alt = float(obj.get("alt", 0))
    except (TypeError, ValueError):
        return None
    drone_id = obj.get("drone_id") or obj.get("id") or ""
    ua_type = obj.get("type") or obj.get("ua_type") or obj.get("aircraft_type") or ""
    out = {
        "drone_id": str(drone_id),
        "lat": lat,
        "lon": lon,
        "alt": alt,
        "speed": float(obj.get("speed", 0)),
        "heading": float(obj.get("heading", 0)),
        "timestamp": obj.get("timestamp", ""),
        "type": str(ua_type).strip(),
        "raw": raw,
    }
    try:
        olat = obj.get("operator_lat")
        olon = obj.get("operator_lon")
        if olat is not None and olon is not None:
            out["operator_lat"] = float(olat)
            out["operator_lon"] = float(olon)
            out["operator_alt"] = float(obj.get("operator_alt", 0))
    except (TypeError, ValueError):
        pass
    return out
