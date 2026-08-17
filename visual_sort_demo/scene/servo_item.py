# -*- coding: utf-8 -*-
"""舵机图形：机身方块 + 绕枢轴旋转的摇臂（供送料舵机、分拣舵机复用）。"""

from PySide6.QtCore import QRectF, Qt, Property, QPointF
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QBrush
from PySide6.QtWidgets import QGraphicsObject

from ui.styles import MODULE_FILL, MODULE_BORDER, MODULE_TITLE, ACCENT, lerp_color


class ServoItem(QGraphicsObject):
    """舵机：上方机身，下方摇臂绕枢轴旋转。角度 0 = 竖直向下。

    ``angle`` 是浮点属性（度），可用 QPropertyAnimation 平滑旋转摇臂。
    正角度 = 顺时针（向右），负角度 = 逆时针（向左）。
    """

    def __init__(self, label="SG90", body_w=150, body_h=46, arm_len=46, parent=None):
        super().__init__(parent)
        self._label = label
        self._body_w = float(body_w)
        self._body_h = float(body_h)
        self._arm_len = float(arm_len)
        self._angle = 0.0
        self._active = False

    # ---- angle 属性（供 QPropertyAnimation 使用）----
    @Property(float)
    def angle(self):
        return self._angle

    @angle.setter
    def angle(self, value):
        self._angle = value
        self.update()

    def boundingRect(self):
        # 上方机身 + 下方摇臂活动范围
        return QRectF(0, 0, self._body_w, self._body_h + self._arm_len + 8)

    def set_label(self, text):
        self._label = text
        self.update()

    def set_active(self, active):
        self._active = active
        self.update()

    def set_arm_angle(self, deg):
        self.angle = deg

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QPainter.Antialiasing, True)

        # 机身
        body_rect = QRectF(0, 0, self._body_w, self._body_h)
        border = ACCENT if self._active else MODULE_BORDER
        fill = lerp_color(MODULE_FILL, "#2A3A52", 1.0 if self._active else 0.0)
        painter.setPen(QPen(QColor(border), 2))
        painter.setBrush(QBrush(QColor(fill)))
        painter.drawRoundedRect(body_rect, 6, 6)

        # 机身文字
        painter.setPen(QColor(MODULE_TITLE))
        font = QFont()
        font.setPointSize(10)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(body_rect, Qt.AlignCenter, self._label)

        # 枢轴点：机身底部中心
        pivot = QPointF(self._body_w / 2, self._body_h)

        # 摇臂（绕枢轴旋转）
        painter.save()
        painter.translate(pivot)
        painter.rotate(self._angle)
        arm_color = ACCENT if self._active else "#C0C7D1"
        arm_pen = QPen(QColor(arm_color), 5)
        arm_pen.setCapStyle(Qt.RoundCap)
        painter.setPen(arm_pen)
        painter.drawLine(QPointF(0, 2), QPointF(0, self._arm_len))
        # 摇臂末端圆点
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor("#C0C7D1")))
        painter.drawEllipse(QPointF(0, self._arm_len), 5, 5)
        painter.restore()

        # 枢轴圆点
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor("#C0C7D1")))
        painter.drawEllipse(pivot, 5, 5)
