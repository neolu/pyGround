# core/serial_client.py
"""串口客户端：打开串口、可选上电发送格式指令、按行读取并回调。"""

import logging
import threading

# 串口连接后可选发送的格式指令（留空则不发送）
DEFAULT_SERIAL_FORMAT_CMD = ""
from typing import Callable

logger = logging.getLogger(__name__)

try:
    import serial
    from serial.tools import list_ports
    SERIAL_AVAILABLE = True
except ImportError:
    SERIAL_AVAILABLE = False
    serial = None
    list_ports = None


def list_serial_ports() -> list[tuple[str, str]]:
    """返回 [(port, description), ...]，如 [('COM3', 'USB-SERIAL CH340')]。"""
    if not SERIAL_AVAILABLE:
        return []
    out = []
    for p in list_ports.comports():
        out.append((p.device, p.description or p.device))
    return out


def run_serial_client(
    port: str,
    baud: int = 115200,
    on_data: Callable[[bytes, str], None] | None = None,
    format_cmd: str | bytes | None = None,
    use_binary: bool = False,
) -> tuple[Callable[[], None], Callable[[bytes], None]]:
    """
    打开串口，若 format_cmd 非空则先发送，然后后台读取并回调 on_data。
    use_binary=False：按行读取，on_data(一行字节, source_label)；
    use_binary=True：按块读取原始字节（用于 MAVLink 等二进制协议），on_data(块字节, source_label)。
    返回 (stop, send_fn)：send_fn(data) 向串口发送字节（可主线程调用）。
    """
    if not SERIAL_AVAILABLE:
        raise RuntimeError("pyserial not installed: pip install pyserial")

    ser = serial.Serial(port=port, baudrate=baud, timeout=0.5)
    source_label = f"Serial:{port}"
    stop_flag = threading.Event()

    if format_cmd:
        if isinstance(format_cmd, str):
            format_cmd = format_cmd.encode("utf-8", errors="replace")
        if not format_cmd.endswith(b"\r\n") and not format_cmd.endswith(b"\n"):
            format_cmd = format_cmd + b"\r\n"
        try:
            ser.write(format_cmd)
            logger.info("Sent format command to %s", port)
        except Exception as e:
            logger.warning("Format command send failed: %s", e)

    buf = b""

    def send_data(data: bytes) -> None:
        try:
            ser.write(data)
        except Exception as e:
            logger.warning("Serial send failed: %s", e)

    def loop():
        nonlocal buf
        while not stop_flag.is_set():
            try:
                chunk = ser.read(ser.in_waiting or 1024)
                if not chunk:
                    continue
                if use_binary:
                    if on_data:
                        on_data(chunk, source_label)
                else:
                    buf += chunk
                    while b"\n" in buf or b"\r" in buf:
                        line = None
                        if b"\n" in buf:
                            line, _, buf = buf.partition(b"\n")
                        elif b"\r" in buf:
                            line, _, buf = buf.partition(b"\r")
                        if line is not None and line.strip() and on_data:
                            on_data(line.strip(), source_label)
            except (OSError, Exception) as e:
                if stop_flag.is_set():
                    break
                logger.debug("Serial read: %s", e)
        try:
            ser.close()
        except Exception:
            pass

    th = threading.Thread(target=loop, daemon=True)
    th.start()

    def stop():
        stop_flag.set()
        try:
            ser.close()
        except Exception:
            pass

    return stop, send_data
