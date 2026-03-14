# core/udp_client.py
"""UDP 客户端：向桥接/模拟器发送一包“注册”，然后在本机端口接收数据。"""

import logging
import socket
import threading
from typing import Callable

logger = logging.getLogger(__name__)


def run_udp_client(
    host: str,
    port: int,
    on_data: Callable[[bytes, str], None],
    listen_port: int = 0,
) -> tuple[Callable[[], None], Callable[[bytes], None]]:
    """
    在后台线程中：绑定 listen_port，向 (host, port) 发一包注册，然后循环 recv 并调用 on_data(data, addr).
    返回 (stop, send_fn)：stop 结束循环；send_fn(data) 向 (host, port) 发送数据（可主线程调用）。
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("", listen_port))
    sock.settimeout(1.0)
    dest = (host, port)
    stop_flag = threading.Event()

    def send_register():
        try:
            sock.sendto(b"\n", dest)
            logger.info("Sent register packet to %s:%s", host, port)
        except Exception as e:
            logger.warning("Register send failed: %s", e)

    def send_data(data: bytes) -> None:
        try:
            sock.sendto(data, dest)
        except Exception as e:
            logger.warning("UDP send failed: %s", e)

    def loop():
        send_register()
        while not stop_flag.is_set():
            try:
                data, addr = sock.recvfrom(65535)
                on_data(data, f"{addr[0]}:{addr[1]}")
            except socket.timeout:
                continue
            except OSError:
                if stop_flag.is_set():
                    break
                raise

    th = threading.Thread(target=loop, daemon=True)
    th.start()

    def stop():
        stop_flag.set()
        try:
            sock.close()
        except Exception:
            pass

    return stop, send_data
