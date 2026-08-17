# -*- coding: utf-8 -*-
"""
worker.py —— 后台检测线程
============================================
职责：在后台线程里持续「抓帧 → 检测 → 发出结果信号」，
     避免耗时操作（读图、识别）卡住 GUI 主线程导致界面无响应。

GUI 侧只需要：
    1. 创建 DetectionWorker(camera, detector)
    2. 连接 result_ready / failed 信号
    3. start() 启动；stop() 停止
"""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal


class DetectionWorker(QThread):
    """后台检测线程。"""

    # 每一帧检测结果（dict），通过信号送到 GUI 线程刷新界面
    result_ready = Signal(dict)
    # 出错信息
    failed = Signal(str)

    def __init__(self, camera, detector, interval_ms: int = 30, parent=None) -> None:
        super().__init__(parent)
        self._camera = camera
        self._detector = detector
        # 每帧之间的最小间隔（毫秒），用于控制最大帧率；0 表示不限制
        self._interval_ms = interval_ms
        self._running = False

    def stop(self) -> None:
        """请求停止循环（线程会在下一轮检查后退出）。"""
        self._running = False

    def run(self) -> None:
        """线程主循环（在子线程中执行，这里绝不能碰任何 GUI 控件）。"""
        self._running = True
        read_failed = False  # 用于避免重复刷错误日志
        try:
            while self._running:
                ok, frame = self._camera.read()
                if not ok or frame is None:
                    if not read_failed:
                        self.failed.emit("读取画面失败")
                        read_failed = True
                    self.msleep(200)
                    continue
                read_failed = False

                # 调用识别，得到统一字典
                result = self._detector.detect(frame)
                # 把原始帧一并带上，供界面显示「原始图像」
                result["frame"] = frame
                self.result_ready.emit(result)

                # 控制帧率
                if self._interval_ms > 0:
                    self.msleep(self._interval_ms)
        finally:
            # 无论正常退出还是异常，都释放摄像头资源
            self._camera.release()
