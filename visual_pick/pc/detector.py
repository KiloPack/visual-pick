# -*- coding: utf-8 -*-
"""
detector.py —— 视觉分拣识别逻辑封装
============================================
职责：把「一帧图像 → 分类结果 + 特征 + 中间图」封装成统一接口，供 GUI、后台线程等调用。
识别算法本身集中在这里，便于独立调试、替换。

统一接口：
    result = detect(frame)
    result 是一个字典，包含：
        "label"        : 分类结果，取值 EMPTY / NUT / WASHER / UNKNOWN
        "area"         : 目标面积（像素数）
        "circularity"  : 圆度（0~1，越接近 1 越圆）
        "vertices"     : 轮廓顶点数（多边形逼近结果，六边形 ≈ 6）
        "binary"       : 二值图（单通道 0/255）
        "debug_frame"  : 叠加了检测框与标签的彩色图

如何接入你自己的识别代码：
    只需要把 Detector.detect() 内部的「处理流程」替换成你自己的逻辑，
    保持返回字典的键名不变即可，GUI 完全不用改。
"""

from __future__ import annotations

import cv2
import numpy as np

# 分类结果标签（与固件 / 上位机约定一致），统一定义在 labels.py
from labels import LABEL_EMPTY, LABEL_NUT, LABEL_UNKNOWN, LABEL_WASHER

# ---- detect() 返回字典的键名，集中定义，避免各处拼写不一致 ----
KEY_LABEL = "label"
KEY_AREA = "area"
KEY_CIRCULARITY = "circularity"
KEY_VERTICES = "vertices"
KEY_BINARY = "binary"
KEY_DEBUG_FRAME = "debug_frame"


class Detector:
    """视觉分拣识别器：输入一帧 BGR 图像，输出分类与特征。"""

    def __init__(self, min_area: int = 800, blur_ksize: int = 5) -> None:
        # 小于该面积的目标视为「空 / 噪声」
        self.min_area = min_area
        # 高斯模糊核尺寸（需为奇数），用于去噪
        self.blur_ksize = blur_ksize

    def detect(self, frame: np.ndarray) -> dict:
        """
        对一帧图像做识别，返回统一字典。

        参数：
            frame：BGR 彩色图（numpy 数组，shape 为 HxWx3）
        返回：
            见模块顶部说明的字典。
        """
        if frame is None:
            return self._empty_result(None, None)

        # 兼容灰度输入
        if frame.ndim == 2:
            frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)

        # 1. 灰度化 + 高斯模糊去噪
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(gray, (self.blur_ksize, self.blur_ksize), 0)

        # 2. 二值化（Otsu 自动阈值；现场光照不均时可改用自适应阈值）
        _, binary = cv2.threshold(
            blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
        )

        # 3. 查找轮廓（带层级，用于判断垫片是否有内孔）
        contours, hierarchy = cv2.findContours(
            binary, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE
        )

        # 4. 准备调试图：在彩色图上叠加检测框
        debug = frame.copy()

        # 没有轮廓或轮廓为空 → 空结果
        if not contours:
            return self._empty_result(binary, debug)

        # 5. 找到面积最大的「外轮廓」（忽略内孔）
        largest_index, largest_area = self._find_largest_outer_contour(
            contours, hierarchy
        )

        # 面积过小 → 视为空 / 噪声
        if largest_index < 0 or largest_area < self.min_area:
            return self._empty_result(binary, debug)

        # 6. 计算特征
        contour = contours[largest_index]
        area = float(largest_area)
        perimeter = cv2.arcLength(contour, True)
        circularity = (
            4.0 * np.pi * area / (perimeter * perimeter) if perimeter > 0 else 0.0
        )
        vertices = self._count_vertices(contour, perimeter)
        has_hole = self._has_hole(hierarchy, largest_index)

        # 7. 分类
        label = self._classify(circularity, vertices, has_hole)

        # 8. 绘制检测框、轮廓与标签
        self._draw(debug, contour, label, area, circularity, vertices)

        return {
            KEY_LABEL: label,
            KEY_AREA: area,
            KEY_CIRCULARITY: circularity,
            KEY_VERTICES: vertices,
            KEY_BINARY: binary,
            KEY_DEBUG_FRAME: debug,
        }

    # ------------------------------------------------------------------
    # 内部辅助方法
    # ------------------------------------------------------------------
    def _empty_result(self, binary, debug) -> dict:
        """构造「空」结果，并在 debug 图上标注 EMPTY。"""
        if debug is not None:
            cv2.putText(
                debug, LABEL_EMPTY, (20, 40),
                cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 2,
            )
        return {
            KEY_LABEL: LABEL_EMPTY,
            KEY_AREA: 0.0,
            KEY_CIRCULARITY: 0.0,
            KEY_VERTICES: 0,
            KEY_BINARY: binary,
            KEY_DEBUG_FRAME: debug,
        }

    @staticmethod
    def _find_largest_outer_contour(contours, hierarchy):
        """返回面积最大的外轮廓的 (索引, 面积)。"""
        largest_index = -1
        largest_area = 0.0
        for i, contour in enumerate(contours):
            # 外轮廓的父轮廓为 -1；父轮廓 != -1 的是内孔，跳过
            if hierarchy is not None and hierarchy[0][i][3] != -1:
                continue
            area = cv2.contourArea(contour)
            if area > largest_area:
                largest_area = area
                largest_index = i
        return largest_index, largest_area

    @staticmethod
    def _count_vertices(contour, perimeter: float) -> int:
        """用多边形逼近估算轮廓顶点数。"""
        if perimeter <= 0:
            return 0
        epsilon = 0.02 * perimeter  # 逼近精度：周长的 2%
        approx = cv2.approxPolyDP(contour, epsilon, True)
        return len(approx)

    @staticmethod
    def _has_hole(hierarchy, index: int) -> bool:
        """判断外轮廓是否包含内孔（垫片通常是带孔的圆环）。"""
        if hierarchy is None:
            return False
        # hierarchy[0][i] = [next, prev, first_child, parent]
        return hierarchy[0][index][2] != -1  # first_child != -1 表示有内孔

    @staticmethod
    def _classify(circularity: float, vertices: int, has_hole: bool) -> str:
        """
        根据特征判定分类。这里是「示例规则」，请替换成你真实的判定逻辑：
          - 垫片：带内孔的圆环
          - 螺母：六边形（顶点数 ≈ 6）
          - 其他：未知
        """
        # TODO: 在这里填入你自己的判定规则
        if has_hole and circularity > 0.7:
            return LABEL_WASHER
        if 5 <= vertices <= 7:
            return LABEL_NUT
        return LABEL_UNKNOWN

    @staticmethod
    def _draw(debug, contour, label: str, area: float,
              circularity: float, vertices: int) -> None:
        """在 debug 图上绘制检测框、轮廓与文字（颜色为 BGR）。"""
        color = Detector._label_color(label)
        x, y, w, h = cv2.boundingRect(contour)
        cv2.rectangle(debug, (x, y), (x + w, y + h), color, 2)
        cv2.drawContours(debug, [contour], -1, color, 1)
        text = f"{label}  A={int(area)}  C={circularity:.2f}  V={vertices}"
        cv2.putText(
            debug, text, (x, max(y - 8, 16)),
            cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2,
        )

    @staticmethod
    def _label_color(label: str):
        """返回标签对应的 BGR 颜色。"""
        return {
            LABEL_EMPTY: (0, 0, 255),      # 红
            LABEL_NUT: (0, 255, 0),        # 绿
            LABEL_WASHER: (0, 255, 255),   # 黄
            LABEL_UNKNOWN: (0, 165, 255),  # 橙
        }.get(label, (255, 255, 255))      # 默认白


# ---- 模块级便捷函数：直接用默认参数的识别器识别一帧 ----
_default_detector = Detector()


def detect(frame: np.ndarray) -> dict:
    """便捷入口：使用默认参数的识别器识别一帧。"""
    return _default_detector.detect(frame)
