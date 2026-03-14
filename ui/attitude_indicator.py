# ui/attitude_indicator.py
"""姿态仪（人工地平线）：经典圆盘 ADI 与 PFD 样式（参考 Mission Planner 等玻璃座舱）。"""

import math
from PyQt6.QtWidgets import QWidget, QSizePolicy
from PyQt6.QtCore import Qt, QRectF, QPointF
from PyQt6.QtGui import (
    QPainter, QColor, QPen, QBrush, QLinearGradient,
    QPolygonF, QPainterPath, QFont,
)
from core import i18n

# 参考 qfi Adi.hpp: m_originalWidth/Height=240, m_originalPixPerDeg=1.7
QFI_ORIGINAL_SIZE = 240
QFI_PIX_PER_DEG = 1.7
PITCH_LIMIT_DEG = 90   # 俯仰刻度 ±90°
ROLL_RANGE = 60        # 滚转刻度显示 ±60°


class AttitudeIndicatorWidget(QWidget):
    """姿态仪：俯仰 ±90°、横滚 ±180°，按控件尺寸缩放像素/度。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(120, 120)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._roll_deg = 0.0
        self._pitch_deg = 0.0

    def set_attitude(self, roll_deg: float, pitch_deg: float):
        self._roll_deg = max(-180.0, min(180.0, float(roll_deg)))
        self._pitch_deg = max(-PITCH_LIMIT_DEG, min(PITCH_LIMIT_DEG, float(pitch_deg)))
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        w, h = self.width(), self.height()
        if w < 20 or h < 20:
            return
        size = min(w, h)
        cx, cy = w / 2.0, h / 2.0
        r_outer = size / 2.0 - 2.0
        # 与 qfi 一致：按 240 参考尺寸缩放俯仰像素/度
        scale_xy = size / float(QFI_ORIGINAL_SIZE)
        pix_per_deg = QFI_PIX_PER_DEG * scale_xy
        pitch_off = self._pitch_deg * pix_per_deg
        pitch_margin = 90 * pix_per_deg
        half_h = max(r_outer * 1.8, size * 0.6, r_outer + pitch_margin * 1.5)

        clip_path = QPainterPath()
        clip_path.addEllipse(QRectF(cx - r_outer, cy - r_outer, r_outer * 2, r_outer * 2))
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        p.save()
        p.setClipPath(clip_path)
        p.translate(cx, cy)
        p.rotate(-self._roll_deg)
        p.translate(0, pitch_off)

        # 变换后地平线在 y=0：上方为天、下方为地（qfi: face 旋转 -roll 后平移 delta）
        grad_sky = QLinearGradient(0, -half_h, 0, 0)
        grad_sky.setColorAt(0, QColor(28, 70, 130))
        grad_sky.setColorAt(0.5, QColor(50, 110, 190))
        grad_sky.setColorAt(1, QColor(90, 150, 220))
        p.setBrush(QBrush(grad_sky))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRect(QRectF(-half_h, -half_h, half_h * 2, half_h))

        grad_ground = QLinearGradient(0, 0, 0, half_h * 2)
        grad_ground.setColorAt(0, QColor(139, 90, 43))
        grad_ground.setColorAt(0.5, QColor(101, 67, 33))
        grad_ground.setColorAt(1, QColor(80, 52, 25))
        p.setBrush(QBrush(grad_ground))
        p.drawRect(QRectF(-half_h, 0, half_h * 2, half_h * 2))

        p.setPen(QPen(QColor(255, 255, 255), 2.5))
        p.drawLine(QPointF(-half_h, 0), QPointF(half_h, 0))
        # 俯仰刻度：仅 20° 标文字，其余用刻度长短表示（5° 短、10° 中、20° 长+数字）
        p.setPen(QPen(QColor(255, 255, 255), 1.0))
        ladder_short = r_outer * 0.18
        ladder_mid = r_outer * 0.28
        ladder_long = r_outer * 0.36
        font = QFont()
        font.setPointSize(max(7, int(8 * scale_xy)))
        p.setFont(font)
        for step in range(5, PITCH_LIMIT_DEG + 1, 5):
            dy = step * pix_per_deg
            if step % 20 == 0:
                ln = ladder_long
            elif step % 10 == 0:
                ln = ladder_mid
            else:
                ln = ladder_short
            p.drawLine(QPointF(-ln, -dy), QPointF(ln, -dy))
            p.drawLine(QPointF(-ln, dy), QPointF(ln, dy))
            if step % 20 == 0:
                p.drawText(QRectF(ladder_long + 2, -dy - 6, 22, 12), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, str(step))
                p.drawText(QRectF(-ladder_long - 24, -dy - 6, 22, 12), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, str(step))
                p.drawText(QRectF(ladder_long + 2, dy - 6, 22, 12), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, str(-step))
                p.drawText(QRectF(-ladder_long - 24, dy - 6, 22, 12), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, str(-step))

        p.restore()

        # 滚转刻度：10° 标文字、5° 短刻线，黄色在天空色上更易辨认
        roll_color = QColor(220, 180, 0)
        p.setPen(QPen(roll_color, 1.0))
        tick_long_in = 6.0
        tick_short_in = 3.0
        for r in range(-ROLL_RANGE, ROLL_RANGE + 1, 5):
            if r == 0:
                continue
            rad = math.radians(r)
            x1 = cx + r_outer * math.sin(rad)
            y1 = cy - r_outer * math.cos(rad)
            inward = tick_long_in if r % 10 == 0 else tick_short_in
            x2 = cx + (r_outer - inward) * math.sin(rad)
            y2 = cy - (r_outer - inward) * math.cos(rad)
            p.drawLine(QPointF(x1, y1), QPointF(x2, y2))
        p.setFont(font)
        for r in (-60, -45, -30, -20, -10, 10, 20, 30, 45, 60):
            rad = math.radians(r)
            x = cx + (r_outer - tick_long_in - 2) * math.sin(rad)
            y = cy - (r_outer - tick_long_in - 2) * math.cos(rad)
            p.drawText(QRectF(x - 12, y - 6, 24, 12), Qt.AlignmentFlag.AlignCenter, str(r))

        # 固定外圈与内圈（仪表边框，参考 qfi case/ring）
        p.setPen(QPen(QColor(60, 60, 60), 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QRectF(cx - r_outer, cy - r_outer, r_outer * 2, r_outer * 2))
        p.setPen(QPen(QColor(100, 100, 100), 1))
        p.drawEllipse(QRectF(cx - r_outer + 3, cy - r_outer + 3, (r_outer - 3) * 2, (r_outer - 3) * 2))

        # 滚转指针（顶部三角）：随 roll 旋转，指向固定刻度上的当前滚转角
        tri_h = 10.0
        tri_w = 6.0
        p.save()
        p.translate(cx, cy)
        p.rotate(self._roll_deg)
        tri = QPolygonF([
            QPointF(0, -r_outer + 2),
            QPointF(-tri_w, -r_outer + 2 + tri_h),
            QPointF(tri_w, -r_outer + 2 + tri_h),
        ])
        p.setBrush(QBrush(QColor(255, 255, 255)))
        p.setPen(QPen(QColor(40, 40, 40), 1))
        p.drawPolygon(tri)
        p.restore()

        # 中心固定飞机符号（机翼 + 机头，参考 PFD）
        wing_half = 14.0
        nose_len = 8.0
        p.setPen(QPen(QColor(255, 255, 255), 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawLine(QPointF(cx - wing_half, cy), QPointF(cx + wing_half, cy))
        p.drawLine(QPointF(cx, cy), QPointF(cx, cy + nose_len))
        p.drawLine(QPointF(cx, cy), QPointF(cx - 6, cy + 6))
        p.drawLine(QPointF(cx, cy), QPointF(cx + 6, cy + 6))

        p.end()


# PFD 样式（参考 Mission Planner）：航向带、姿态区、垂直速度、高度带、空速/地速/模式/电量
PFD_PITCH_LIMIT = 90
PFD_PIX_PER_DEG = 2.2
PFD_HEADING_BAR_H = 26
PFD_BOTTOM_H = 34
PFD_VS_WIDTH = 46
PFD_ALT_WIDTH = 52
CARDINALS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")


class AttitudeIndicatorPfdWidget(QWidget):
    """PFD 样式姿态仪：航向带、人工地平线、垂直速度、高度带、空速/地速/模式/电量（Mission Planner 风格）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(320, 280)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._roll_deg = 0.0
        self._pitch_deg = 0.0
        self._pfd_data = {}  # heading, alt, climb_rate, airspeed, groundspeed, flight_mode, battery_*, arm_state

    def set_attitude(self, roll_deg: float, pitch_deg: float):
        self._roll_deg = max(-180.0, min(180.0, float(roll_deg)))
        self._pitch_deg = max(-PFD_PITCH_LIMIT, min(PFD_PITCH_LIMIT, float(pitch_deg)))
        self.update()

    def set_flight_data(self, info: dict | None):
        """设置 PFD 显示的飞行数据（航向、高度、爬升率、空速、地速、模式、电量等）。"""
        self._pfd_data = dict(info) if info else {}
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        w, h = self.width(), self.height()
        if w < 80 or h < 120:
            return
        d = self._pfd_data
        is_light = (d.get("gui_theme") == "light")
        if is_light:
            text_primary = QColor(40, 40, 40)
            scale_color = QColor(70, 70, 70)
            box_bg = QColor(248, 248, 248)
            box_border = QColor(100, 100, 100)
        else:
            text_primary = QColor(220, 220, 220)
            scale_color = QColor(180, 180, 180)
            box_bg = QColor(30, 30, 30)
            box_border = QColor(200, 200, 200)

        heading_deg = float(d.get("heading") if d.get("heading") is not None else d.get("yaw", 0)) % 360
        alt = d.get("alt")
        climb = d.get("climb_rate")
        airspeed = d.get("airspeed")
        groundspeed = d.get("groundspeed")
        flight_mode = str(d.get("flight_mode") or "—")
        bat_pct = d.get("battery_remaining", -1)
        bat_v = d.get("battery_voltage")

        heading_bar_h = PFD_HEADING_BAR_H
        bottom_h = PFD_BOTTOM_H
        vs_w = PFD_VS_WIDTH
        alt_w = PFD_ALT_WIDTH
        center_w = w - vs_w - alt_w
        mid_h = h - heading_bar_h - bottom_h
        if center_w < 80 or mid_h < 80:
            return
        # 姿态区中心（在中心带内的坐标）
        att_cx = vs_w + center_w / 2.0
        att_cy = heading_bar_h + mid_h / 2.0
        scale_xy = min(center_w, mid_h) / 200.0
        pix_per_deg = PFD_PIX_PER_DEG * scale_xy
        pitch_off = self._pitch_deg * pix_per_deg
        diag = math.sqrt((center_w / 2.0) ** 2 + (mid_h / 2.0) ** 2) * 1.3
        pitch_margin = 90 * pix_per_deg
        half_extent = max(diag, mid_h / 2.0 + pitch_margin * 1.8, center_w / 2.0 + pitch_margin)
        half_w = half_extent
        half_h = half_extent

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        small_font = QFont()
        small_font.setPointSize(max(7, int(8 * scale_xy)))

        # ---------- 1) 顶部航向带：参考 Mission Planner，10° 标文字、5° 短横线 ----------
        p.setPen(QPen(scale_color, 1))
        deg_per_pix = 1.8
        tape_left = vs_w
        tape_right = w - alt_w
        center_heading = heading_deg
        tick_y = heading_bar_h - 2
        tick_short = 2
        tick_10 = 4
        label_w = 38
        min_spacing = 36
        skip_center = 30
        last_x = -1e9
        for hd in range(0, 360, 5):
            offset_deg = (hd - center_heading + 180) % 360 - 180
            x = att_cx + offset_deg * deg_per_pix
            if x < tape_left + 4 or x > tape_right - 4:
                continue
            if hd % 10 == 0:
                tick_len = tick_10
            else:
                tick_len = tick_short
            p.drawLine(QPointF(x, tick_y - tick_len), QPointF(x, tick_y))
            if hd % 10 != 0:
                continue
            if abs(x - att_cx) < skip_center:
                continue
            if abs(x - last_x) < min_spacing:
                continue
            p.setPen(QPen(text_primary, 1))
            p.setFont(small_font)
            if hd % 90 == 0:
                lbl = CARDINALS[hd // 45]
            else:
                lbl = str(hd)
            p.drawText(QRectF(x - label_w / 2, 0, label_w, tick_y - tick_len - 2), Qt.AlignmentFlag.AlignCenter, lbl)
            p.setPen(QPen(scale_color, 1))
            last_x = x
        # 当前航向三角（红色）与数值
        tri = QPolygonF([
            QPointF(att_cx, 4),
            QPointF(att_cx - 6, heading_bar_h - 4),
            QPointF(att_cx + 6, heading_bar_h - 4),
        ])
        p.setBrush(QBrush(QColor(220, 60, 60)))
        p.setPen(QPen(QColor(160, 40, 40), 1))
        p.drawPolygon(tri)
        p.setPen(QPen(text_primary, 1))
        p.drawText(QRectF(att_cx - 24, 2, 48, 14), Qt.AlignmentFlag.AlignCenter, f"{int(round(center_heading))}")

        # ---------- 2) 左侧垂直速度 ----------
        vs_rect = QRectF(2, heading_bar_h, vs_w - 4, mid_h)
        p.setPen(QPen(scale_color, 1))
        vs_center_y = att_cy
        vs_step_pix = 18
        for v in range(-10, 11, 5):
            if v == 0:
                continue
            y = vs_center_y + v * vs_step_pix
            if y < vs_rect.top() or y > vs_rect.bottom():
                continue
            p.drawLine(QPointF(vs_rect.left(), y), QPointF(vs_rect.left() + 5, y))
            p.drawText(QRectF(vs_rect.left(), y - 6, vs_rect.width() - 10, 12), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, str(v))
        climb_val = climb if climb is not None else 0
        climb_val = max(-10, min(10, climb_val))
        box_y = vs_center_y + climb_val * vs_step_pix - 10
        box_y = max(vs_rect.top(), min(vs_rect.bottom() - 20, box_y))
        p.setBrush(QBrush(box_bg))
        p.setPen(QPen(box_border, 1))
        p.drawRect(QRectF(vs_rect.left(), box_y, vs_rect.width() - 4, 20))
        p.setPen(QPen(text_primary, 1))
        p.drawText(QRectF(vs_rect.left(), box_y, vs_rect.width() - 8, 20), Qt.AlignmentFlag.AlignCenter, f"{climb_val:.1f}")
        p.drawText(QRectF(vs_rect.left(), vs_rect.bottom() - 16, vs_rect.width(), 14), Qt.AlignmentFlag.AlignCenter, "m/s")

        # ---------- 3) 中央姿态区（人工地平线） ----------
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(vs_w, heading_bar_h, center_w, mid_h), 6, 6)
        p.save()
        p.setClipPath(clip)
        p.translate(att_cx, att_cy)
        p.rotate(-self._roll_deg)
        p.translate(0, pitch_off)

        grad_sky = QLinearGradient(0, -half_h, 0, 0)
        grad_sky.setColorAt(0, QColor(145, 195, 245))
        grad_sky.setColorAt(1, QColor(180, 220, 255))
        p.setBrush(QBrush(grad_sky))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRect(QRectF(-half_w, -half_h, half_w * 2, half_h))

        grad_ground = QLinearGradient(0, 0, 0, half_h)
        grad_ground.setColorAt(0, QColor(100, 140, 80))
        grad_ground.setColorAt(1, QColor(60, 100, 50))
        p.setBrush(QBrush(grad_ground))
        p.drawRect(QRectF(-half_w, 0, half_w * 2, half_h * 2))

        p.setPen(QPen(QColor(255, 255, 255), 2.5))
        p.drawLine(QPointF(-half_w, 0), QPointF(half_w, 0))

        p.setPen(QPen(QColor(255, 255, 255), 1.2))
        p.setFont(small_font)
        ladder_short = 16
        ladder_mid = 26
        ladder_long = 34
        for step in range(5, PFD_PITCH_LIMIT + 1, 5):
            for sign, label in [(1, step), (-1, -step)]:
                if sign == 1 and step == 0:
                    continue
                dy = sign * step * pix_per_deg
                if step % 20 == 0:
                    ln = ladder_long
                elif step % 10 == 0:
                    ln = ladder_mid
                else:
                    ln = ladder_short
                p.drawLine(QPointF(-ln, -dy), QPointF(ln, -dy))
                if step % 20 != 0:
                    continue
                txt = str(label)
                p.drawText(QRectF(ladder_long + 2, -dy - 8, 24, 16), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, txt)
                if step > 0:
                    p.drawText(QRectF(-ladder_long - 26, -dy - 8, 24, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, txt)
        p.restore()

        # 姿态区顶部滚转刻度与指针：黑色刻度和数字
        roll_scale_color = QColor(0, 0, 0)
        r_arc = min(center_w, mid_h) / 2.0 - 6
        arc_cx = att_cx
        arc_cy = heading_bar_h + r_arc + 4
        tick_long = 4
        tick_short = 2
        p.setPen(QPen(roll_scale_color, 1))
        for r in range(-60, 61, 5):
            rad = math.radians(r)
            x = arc_cx + r_arc * math.sin(rad)
            y = arc_cy - r_arc * math.cos(rad)
            if y < heading_bar_h + 2 or y > heading_bar_h + mid_h * 0.42:
                continue
            if r % 10 == 0:
                x_in = arc_cx + (r_arc - tick_long) * math.sin(rad)
                y_in = arc_cy - (r_arc - tick_long) * math.cos(rad)
                p.drawLine(QPointF(x_in, y_in), QPointF(x, y))
            else:
                x_in = arc_cx + (r_arc - tick_short) * math.sin(rad)
                y_in = arc_cy - (r_arc - tick_short) * math.cos(rad)
                p.drawLine(QPointF(x_in, y_in), QPointF(x, y))
        p.setFont(small_font)
        p.setPen(QPen(roll_scale_color, 1))
        for r in (-60, -45, -30, -20, -10, 0, 10, 20, 30, 45, 60):
            rad = math.radians(r)
            x = arc_cx + r_arc * math.sin(rad)
            y = arc_cy - r_arc * math.cos(rad)
            if y < heading_bar_h + 2 or y > heading_bar_h + mid_h * 0.42:
                continue
            tangent_deg = math.degrees(math.atan2(math.sin(rad), math.cos(rad)))
            p.save()
            p.translate(x, y)
            p.rotate(-tangent_deg)
            p.drawText(QRectF(-12, -6, 24, 12), Qt.AlignmentFlag.AlignCenter, str(r))
            p.restore()
        p.save()
        p.translate(arc_cx, arc_cy)
        p.rotate(self._roll_deg)
        tri = QPolygonF([
            QPointF(0, -r_arc + 2),
            QPointF(-5, -r_arc + 12),
            QPointF(5, -r_arc + 12),
        ])
        p.setBrush(QBrush(QColor(220, 60, 60)))
        p.setPen(QPen(QColor(180, 40, 40), 1))
        p.drawPolygon(tri)
        p.restore()

        # 中心红色飞机符号
        wing_half = 18.0 * scale_xy
        p.setBrush(QBrush(QColor(220, 60, 60)))
        p.setPen(QPen(QColor(180, 40, 40), 1.5))
        ac = QPolygonF([
            QPointF(att_cx, att_cy - 6),
            QPointF(att_cx - wing_half, att_cy + 10),
            QPointF(att_cx, att_cy + 6),
            QPointF(att_cx + wing_half, att_cy + 10),
        ])
        p.drawPolygon(ac)
        p.setPen(QPen(QColor(255, 255, 255), 1))
        p.drawLine(QPointF(att_cx - wing_half * 0.7, att_cy), QPointF(att_cx + wing_half * 0.7, att_cy))

        # ---------- 4) 右侧高度带（当前高度居中） ----------
        alt_rect = QRectF(w - alt_w + 2, heading_bar_h, alt_w - 6, mid_h)
        p.setPen(QPen(scale_color, 1))
        alt_center = float(alt) if alt is not None else 0
        alt_pix_per_m = 1.2
        for step in range(-120, 121, 20):
            a = int(alt_center) + step
            if a < 0:
                continue
            y = att_cy - step * alt_pix_per_m
            if y < alt_rect.top() + 10 or y > alt_rect.bottom() - 10:
                continue
            p.drawLine(QPointF(alt_rect.right() - 5, y), QPointF(alt_rect.right(), y))
            p.drawText(QRectF(alt_rect.left(), y - 8, alt_rect.width() - 14, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, str(a))
        p.setBrush(QBrush(box_bg))
        p.setPen(QPen(box_border, 1))
        alt_str = f"{int(round(alt_center))}" if alt is not None else "—"
        p.drawRect(QRectF(alt_rect.left(), att_cy - 10, alt_rect.width(), 20))
        p.setPen(QPen(text_primary, 1))
        p.drawText(QRectF(alt_rect.left(), att_cy - 10, alt_rect.width() - 4, 20), Qt.AlignmentFlag.AlignCenter, alt_str)
        p.drawText(QRectF(alt_rect.left(), alt_rect.bottom() - 16, alt_rect.width(), 14), Qt.AlignmentFlag.AlignCenter, "m")

        # ---------- 5) 底部：空速/地速 | 模式/电量 ----------
        p.setFont(small_font)
        p.setPen(text_primary)
        bl_y = h - bottom_h + 4
        air_str = f"{airspeed:.1f}" if airspeed is not None else "—"
        gnd_str = f"{groundspeed:.1f}" if groundspeed is not None else "—"
        p.drawText(QRectF(vs_w, bl_y, center_w // 2, 14), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, f"{i18n.t('airspeed')} {air_str} m/s")
        p.drawText(QRectF(vs_w + center_w // 2, bl_y, center_w // 2, 14), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, f"{i18n.t('groundspeed')} {gnd_str} m/s")
        bat_str = f"{bat_v:.1f}V" if bat_v is not None else "—"
        if bat_pct >= 0:
            bat_str += f" {bat_pct}%"
        p.drawText(QRectF(vs_w, bl_y + 14, center_w, 14), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, f"{flight_mode}  |  {i18n.t('battery')} {bat_str}")

        p.end()
