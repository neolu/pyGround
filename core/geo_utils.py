# core/geo_utils.py
"""WGS84 经纬高与局部笛卡尔 (ENU) 转换，供 3D 轨迹等使用。"""

import math

# 地球长半轴（米）
EARTH_RADIUS = 6378137.0


def wgs84_to_local_enu(
    lat: float,
    lon: float,
    alt: float,
    lat0: float,
    lon0: float,
    alt0: float,
) -> tuple[float, float, float]:
    """
    将 WGS84 (lat, lon, alt) 转为以 (lat0, lon0, alt0) 为原点的局部 ENU 坐标 (x, y, z) 米。
    x 东、y 北、z 天（向上）。
    小范围内近似，适用于无人机轨迹显示。
    """
    lat_rad = math.radians(lat)
    lon_rad = math.radians(lon)
    lat0_rad = math.radians(lat0)
    lon0_rad = math.radians(lon0)
    cos_lat0 = math.cos(lat0_rad)
    dlat = lat_rad - lat0_rad
    dlon = lon_rad - lon0_rad
    x = EARTH_RADIUS * dlon * cos_lat0
    y = EARTH_RADIUS * dlat
    z = alt - alt0
    return (x, y, z)
