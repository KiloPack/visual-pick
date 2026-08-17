# -*- coding: utf-8 -*-
"""物料图形：螺母(六边形带孔) / 垫片(圆环) / 未知(不规则多边形)。"""

import math

from PySide6.QtCore import QRectF, Qt, Property, QPointF
from PySide6.QtGui import QColor, QPainter, QPen, QBrush, QPolygonF, QPainterPath
from PySide6.QtWidgets import QGraphicsObject

from ui.styles import LABEL_COLOR, C_UNKNOWN


class MaterialItem(QGraphicsObject):
    """一个分拣物料。``label`` 决定形状与颜色（NUT / WASHER / UNKNOWN）。"""

    def __init__(self, label="NUT", size=40, parent=None):
        super().__init__(parent)
        self._size = float(size)
        self._label = label
        self._color = LABEL_COLOR.get(label, C_UNKNOWN)

    # ---- label 属性（切换物料种类时自动变色重绘）----
    @Property(str)
    def label(self):
        return self._label

    @label.setter
    def label(self, value):
        self._label = value
        self._color = LABEL_COLOR.get(value, C_UNKNOWN)
        self.update()

    def boundingRect(self):
        m = 6.0
        return QRectF(
            -self._size / 2 - m,
            -self._size / 2 - m,
            self._size + 2 * m,
            self._size + 2 * m,
        )

    def set_material(self, label):
        self.label = label

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QPainter.Antialiasing, True)
        c = QColor(self._color)
        r = self._size / 2

        path = QPainterPath()
        if self._label == "NUT":
            # 六边形 + 中心圆孔（OddEvenFill 挖出真实孔洞，背景透明）
            path.addPolygon(self._hexagon(QPointF(0, 0), r))
            path.addEllipse(QPointF(0, 0), r * 0.35, r * 0.35)
        elif self._label == "WASHER":
            # 圆环
            path.addEllipse(QPointF(0, 0), r, r)
            path.addEllipse(QPointF(0, 0), r * 0.38, r * 0.38)
        else:
            # UNKNOWN / 其他：不规则多边形
            path = self._blob(r)

        path.setFillRule(Qt.OddEvenFill)
        painter.setPen(QPen(c.lighter(125), 2))
        painter.setBrush(QBrush(c))
        painter.drawPath(path)

    @staticmethod
    def _hexagon(center, r):
        pts = []
        for i in range(6):
            ang = math.pi / 3.0 * i - math.pi / 6.0  # 让一条边水平朝上
            pts.append(
                QPointF(
                    center.x() + r * math.cos(ang),
                    center.y() + r * math.sin(ang),
                )
            )
        return QPolygonF(pts)

    @staticmethod
    def _blob(r):
        """不规则多边形，代表"未知物体"，随尺寸缩放。"""
        s = r / 20.0
        pts = [
            QPointF(-14 * s, -8 * s),
            QPointF(-4 * s, -16 * s),
            QPointF(8 * s, -14 * s),
            QPointF(16 * s, -2 * s),
            QPointF(10 * s, 10 * s),
            QPointF(0, 16 * s),
            QPointF(-12 * s, 10 * s),
        ]
        path = QPainterPath()
        path.addPolygon(QPolygonF(pts))
        return path
