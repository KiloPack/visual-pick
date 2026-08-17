# -*- coding: utf-8 -*-
"""
camera.py —— 摄像头图像源封装
============================================
职责：把「图像从哪来」抽象成统一接口，屏蔽真实摄像头 / 视频文件 / 演示画面的差异。
这样识别模块(GUI/worker)只需要调用 read()，不关心画面到底来自哪里。

统一接口（每个图像源类都实现）：
    open()      -> bool              打开图像源，成功返回 True
    read()      -> (ok, frame)       读取一帧；ok=False 表示读取失败
    release()   -> None              释放资源
    is_opened() -> bool              是否已打开
"""

from __future__ import annotations

import math

import cv2
import numpy as np


class WebcamCamera:
    """基于 cv2.VideoCapture 的真实摄像头 / 视频文件 / 网络流。"""

    def __init__(self, source=0) -> None:
        # source 可以是：摄像头索引(0,1,2...)、视频文件路径、rtsp/http 流地址
        self._source = source
        self._cap = None

    def open(self) -> bool:
        self._cap = cv2.VideoCapture(self._source)
        return self._cap.isOpened()

    def read(self):
        if self._cap is None:
            return False, None
        return self._cap.read()

    def release(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    def is_opened(self) -> bool:
        return self._cap is not None and self._cap.isOpened()


class DemoCamera:
    """
    演示图像源：合成画面，无需真实摄像头即可跑通整条流水线。
    画面会依次循环出现：空(EMPTY) / 螺母(六边形) / 垫片(圆环) / 未知(实心圆)，
    方便在没有硬件时先调试界面与识别流程。
    """

    def __init__(self, width: int = 640, height: int = 480) -> None:
        self._width = width
        self._height = height
        self._frame_index = 0
        # 每个场景停留的帧数（约 60 帧 ≈ 2 秒）
        self._frames_per_scene = 60
        # 依次循环的场景
        self._scenes = ["EMPTY", "NUT", "WASHER", "UNKNOWN"]

    def open(self) -> bool:
        return True

    def is_opened(self) -> bool:
        return True

    def read(self):
        scene = self._scenes[
            (self._frame_index // self._frames_per_scene) % len(self._scenes)
        ]
        frame = self._render(scene)
        self._frame_index += 1
        return True, frame

    def release(self) -> None:
        pass

    def _render(self, scene: str) -> np.ndarray:
        # 深灰背景
        frame = np.full((self._height, self._width, 3), 40, dtype=np.uint8)
        # 加一点噪声，让画面更接近真实
        noise = np.random.randint(0, 12, frame.shape, dtype=np.uint8)
        frame = cv2.add(frame, noise)

        # 物体中心随帧数左右移动，模拟传送带上的物料
        cx = int(self._width / 2 + 120 * math.sin(self._frame_index / 20.0))
        cy = int(self._height / 2)

        if scene == "NUT":
            # 六边形（螺母）
            pts = self._hexagon_points(cx, cy, 70)
            cv2.fillConvexPoly(frame, pts, (200, 200, 200))
        elif scene == "WASHER":
            # 圆环（垫片）：先画实心圆，再挖掉中间
            cv2.circle(frame, (cx, cy), 70, (200, 200, 200), -1)
            cv2.circle(frame, (cx, cy), 26, (40, 40, 40), -1)
        elif scene == "UNKNOWN":
            # 实心圆（故意让它被判定为未知）
            cv2.circle(frame, (cx, cy), 58, (200, 200, 200), -1)
        # EMPTY：什么都不画
        return frame

    @staticmethod
    def _hexagon_points(cx: int, cy: int, radius: int) -> np.ndarray:
        """生成正六边形的六个顶点。"""
        points = []
        for i in range(6):
            angle = math.pi / 3.0 * i
            points.append([
                int(cx + radius * math.cos(angle)),
                int(cy + radius * math.sin(angle)),
            ])
        return np.array(points, dtype=np.int32)


def create_camera(source=0):
    """
    工厂函数：根据 source 创建对应的图像源。
      - int：摄像头索引（默认 0）
      - str：视频文件路径 / rtsp 流地址；"demo" 表示演示画面
    """
    if isinstance(source, str) and source.lower() == "demo":
        return DemoCamera()
    return WebcamCamera(source)
