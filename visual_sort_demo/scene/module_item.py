# -*- coding: utf-8 -*-
"""通用设备模块：圆角矩形 + 标题/副标题 + 状态行 + 可动画的高亮。"""

from PySide6.QtCore import QRectF, Qt, Property
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QBrush
from PySide6.QtWidgets import QGraphicsObject

from ui.styles import (
    MODULE_FILL,
    MODULE_BORDER,
    MODULE_TITLE,
    MODULE_SUBTEXT,
    ACCENT,
    ACTIVE_FILL,
    lerp_color,
)


class ModuleItem(QGraphicsObject):
    """一个带标题、副标题、底部状态文字的圆角模块框。

    ``highlight`` 是 0~1 的浮点属性，可用 QPropertyAnimation 平滑过渡，
    用于表现"当前正在工作的模块"。
    """

    def __init__(self, width, height, title="", subtitle="", parent=None):
        super().__init__(parent)
        self._w = float(width)
        self._h = float(height)
        self._title = title
        self._subtitle = subtitle
        self._status = ""
        self._highlight = 0.0
        self._accent = ACCENT

    # ---- highlight 属性（供 QPropertyAnimation 使用）----
    @Property(float)
    def highlight(self):
        return self._highlight

    @highlight.setter
    def highlight(self, value):
        self._highlight = value
        self.update()

    def boundingRect(self):
        return QRectF(0, 0, self._w, self._h)

    def set_status(self, text):
        self._status = text
        self.update()

    def set_title(self, text):
        self._title = text
        self.update()

    def set_accent(self, color):
        self._accent = color
        self.update()

    def set_highlight_level(self, level):
        self.highlight = level

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QPainter.Antialiasing, True)

        t = self._highlight
        fill = lerp_color(MODULE_FILL, ACTIVE_FILL, t)
        border = lerp_color(MODULE_BORDER, self._accent, t)

        # 圆角矩形
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, self._w, self._h), 10, 10)
        painter.setPen(QPen(QColor(border), 2))
        painter.setBrush(QBrush(QColor(fill)))
        painter.drawPath(path)

        # 标题（顶部居中）
        painter.setPen(QColor(MODULE_TITLE))
        title_font = QFont()
        title_font.setPointSize(13)
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.drawText(
            QRectF(0, 8, self._w, 24), Qt.AlignHCenter | Qt.AlignVCenter, self._title
        )

        # 副标题
        if self._subtitle:
            painter.setPen(QColor(MODULE_SUBTEXT))
            sub_font = QFont()
            sub_font.setPointSize(9)
            painter.setFont(sub_font)
            painter.drawText(
                QRectF(0, 32, self._w, 18),
                Qt.AlignHCenter | Qt.AlignVCenter,
                self._subtitle,
            )

        # 状态文字（底部，高亮时用强调色）
        if self._status:
            status_color = lerp_color(MODULE_SUBTEXT, self._accent, t)
            painter.setPen(QColor(status_color))
            status_font = QFont()
            status_font.setPointSize(10)
            status_font.setBold(t > 0.5)
            painter.setFont(status_font)
            painter.drawText(
                QRectF(0, self._h - 26, self._w, 20),
                Qt.AlignHCenter | Qt.AlignVCenter,
                self._status,
            )
