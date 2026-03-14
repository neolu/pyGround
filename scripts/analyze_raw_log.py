#!/usr/bin/env python3
"""从 raw_YYYYMMDD.log 提取 RECV 行，转成 bytes 重放给 MAVLink 解析器，诊断为何解析不出可用信息。"""
import sys
from pathlib import Path

# 项目根
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))

def main():
    path = root / "logs" / "raw_20260313.log"
    if not path.exists():
        print("File not found:", path)
        return 1
    with open(path, "rb") as f:
        raw = f.read()
    lines = raw.split(b"\n")
    recv_lines = [ln for ln in lines if ln.strip().startswith(b"RECV ")]
    print("RECV lines:", len(recv_lines))
    if not recv_lines:
        print("No RECV lines")
        return 0

    def line_to_bytes(ln):
        if not ln.strip().startswith(b"RECV "):
            return b""
        rest = ln.strip()[5:]
        parts = rest.split()
        out = []
        for p in parts:
            try:
                out.append(int(p, 16))
            except ValueError:
                pass
        return bytes(out)

    all_bytes = b"".join(line_to_bytes(ln) for ln in recv_lines[:50])
    print("Total bytes (first 50 RECV):", len(all_bytes))
    print("First 60 bytes hex:", all_bytes[:60].hex(" "))
    print("First 0xFD at:", all_bytes.find(0xFD), "First 0xFE at:", all_bytes.find(0xFE))

    from core.mavlink_parser import MavLinkParser, decode_mavlink_to_annotated

    # 用 decode_mavlink_to_annotated 看能解析出哪些消息类型
    annotated = decode_mavlink_to_annotated(all_bytes)
    print("Decoded message lines:", len(annotated))
    msg_ids_seen = {}
    for line in annotated:
        name = line.split(" | ")[0].strip()
        msg_ids_seen[name] = msg_ids_seen.get(name, 0) + 1
    for name, count in sorted(msg_ids_seen.items(), key=lambda x: -x[1]):
        print("  ", name, count)
    has_33 = "GLOBAL_POSITION_INT" in msg_ids_seen or "MSG_33" in msg_ids_seen
    print("Has GLOBAL_POSITION_INT or MSG_33:", has_33)
    has_0 = "HEARTBEAT" in msg_ids_seen or "MSG_0" in msg_ids_seen
    print("Has HEARTBEAT or MSG_0:", has_0)

    p = MavLinkParser()
    recs = list(p.feed(all_bytes))
    print("Records from parser:", len(recs))
    if recs:
        r0 = recs[0]
        print("First record sample:", {k: r0.get(k) for k in ["drone_id", "lat", "lon", "alt", "no_global_position", "roll", "yaw", "groundspeed"]})
    return 0

if __name__ == "__main__":
    sys.exit(main())
