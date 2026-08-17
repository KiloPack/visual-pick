# -*- coding: utf-8 -*-
"""数据包图形：沿连线流动的小标签（FRAME / N / W / X / PWM）。"""

from PySide6.QtCore import QRectF, Qt, Property
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QBrush
from PySide6.QtWidgets import QGraphicsObject

from ui.styles import BG_SCENE, lerp_color


class DataPacketItem(QGraphicsObject):
    """一个带文字的小圆角标签，以原点为中心（pos 即中心点）。

    用 ``pos`` 动画即可让它沿任意连线流动。
    """

    def __init__(self, text="N", color="#4DA3FF", parent=None):
        super().__init__(parent)
        self._text = text
        self._color = QColor(color)
        self._w = 14 * len(text) + 18
        self._h = 24

    @Property(str)
    def text(self):
        return self._text

    @text.setter
    def text(self, value):
        self._text = value
        self._w = 14 * len(value) + 18
        self.prepareGeometryChange()
        self.update()

    def set_color(self, color):
        self._color = QColor(color)
        self.update()

    def boundingRect(self):
        return QRectF(-self._w / 2, -self._h / 2, self._w, self._h)

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(-self._w / 2, -self._h / 2, self._w, self._h)

        fill = lerp_color(BG_SCENE, self._color.name(), 0.3)
        painter.setPen(QPen(self._color, 2))
        painter.setBrush(QBrush(fill))
        painter.drawRoundedRect(rect, 8, 8)

        painter.setPen(self._color)
        font = QFont()
        font.setPointSize(10)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(rect, Qt.AlignCenter, self._text)
