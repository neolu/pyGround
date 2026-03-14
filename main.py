#!/usr/bin/env python3
"""pyGround 入口：无人机监控 PyQt 主程序。"""

import logging
import os
import sys
import warnings
from pathlib import Path

# 抑制 Qt 字体库/OpenType/DirectWrite 相关警告（不影响功能）
if "QT_LOGGING_RULES" not in os.environ:
    os.environ["QT_LOGGING_RULES"] = "qt.text.font.db=false;qt.qpa.fonts=false"

# 抑制 matplotlib 缺 CJK 字体时的 Glyph missing 警告
warnings.filterwarnings("ignore", message=".*Glyph.*missing from font.*", category=UserWarning)

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

from ui.main_window import MainWindow


def setup_logging(logs_dir: Path) -> None:
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = logs_dir / "app.log"
    fmt = "%(asctime)s %(levelname)s [%(name)s] %(message)s"
    logging.basicConfig(
        level=logging.INFO,
        format=fmt,
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_file, encoding="utf-8"),
        ],
    )


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("DroneMonitor")
    logs_dir = Path("logs")
    try:
        import yaml
        cfg_path = Path(__file__).parent / "config.yaml"
        if cfg_path.exists():
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
            logs_dir = Path(cfg.get("logs_dir", "logs"))
    except Exception:
        pass
    setup_logging(logs_dir)
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
