# -*- coding: utf-8 -*-
"""
image_utils.py —— 图像格式转换工具
============================================
职责：把 OpenCV 的 numpy 图像转成 Qt 能显示的 QPixmap。
GUI 只关心「显示」，不应在界面代码里混入太多图像格式转换细节。
"""

from __future__ import annotations

import cv2
import numpy as np
from PySide6.QtGui import QImage, QPixmap


def numpy_to_pixmap(image: np.ndarray) -> QPixmap:
    """
    把 OpenCV 图像转成 QPixmap。
      - 三通道图按 BGR 处理（OpenCV 默认颜色顺序）
      - 单通道图按灰度处理（例如二值图）
    """
    if image is None:
        return QPixmap()

    if image.ndim == 2:
        # 单通道（灰度 / 二值）→ 转成三通道 RGB
        rgb = cv2.cvtColor(image, cv2.COLOR_GRAY2RGB)
    else:
        # 三通道 BGR → RGB
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

    # 保证内存连续，QImage 才能直接引用该缓冲区
    rgb = np.ascontiguousarray(rgb)

    height, width, channels = rgb.shape
    qimage = QImage(
        rgb.data, width, height, channels * width, QImage.Format_RGB888
    )
    # fromImage 会复制数据，返回的 pixmap 独立于 numpy 数组
    return QPixmap.fromImage(qimage)
