# -*- coding: utf-8 -*-
"""视觉适配器：统一「一帧图像 -> 识别结果」的接口。

第一版默认 Mock 模式（不依赖 opencv/numpy），返回与真实 detector.detect()
完全相同的字典结构，方便上层不做区分地使用。

接入真实工程（visual_pick/pc/detector.py）的方式：
    adapter = VisionAdapter(mode="real")   # 或 adapter.use_real()
    result = adapter.detect(frame)          # frame 为 BGR numpy 数组
    label = result["label"]                 # EMPTY / NUT / WASHER / UNKNOWN
    demo_controller.trigger_sort(label)

真实 detector.detect() 返回字典的键：
    label / area / circularity / vertices / binary / debug_frame
"""

from __future__ import annotations

# 与真实 detector.py 保持一致的返回键
KEY_LABEL = "label"
KEY_AREA = "area"
KEY_CIRCULARITY = "circularity"
KEY_VERTICES = "vertices"
KEY_BINARY = "binary"
KEY_DEBUG_FRAME = "debug_frame"


class VisionAdapter:
    """视觉识别适配器。Mock 模式返回模拟结果，Real 模式委托真实 Detector。"""

    def __init__(self, mode="mock"):
        self.mode = mode
        self._detector = None

    def use_real(self):
        self.mode = "real"
        return self

    def detect(self, frame=None, label="NUT"):
        """返回识别结果字典。

        参数：
            frame：Real 模式下的 BGR 图像（numpy 数组）；Mock 模式忽略。
            label：Mock 模式下返回的分类结果。
        """
        if self.mode == "real":
            return self._real_detect(frame)
        return self._mock_detect(label)

    # ------------------------------------------------------------------
    # Mock / Real
    # ------------------------------------------------------------------
    def _mock_detect(self, label):
        # 与真实 detector.detect() 同构，上层无需区分来源
        return {
            KEY_LABEL: label,
            KEY_AREA: 1234.0,
            KEY_CIRCULARITY: 0.82 if label == "WASHER" else 0.71,
            KEY_VERTICES: 6 if label == "NUT" else 0,
            KEY_BINARY: None,
            KEY_DEBUG_FRAME: None,
        }

    def _real_detect(self, frame):
        # 延迟导入，避免 Mock 阶段强依赖 cv2 / numpy
        if self._detector is None:
            import os
            import sys

            # 默认假设 visual_sort_demo 与 visual_pick 在同一个父目录下。
            # 如果你的路径不同，直接把 pc_dir 改成你 detector.py 所在目录即可。
            pc_dir = os.path.abspath(
                os.path.join(os.path.dirname(__file__), "..", "..", "visual_pick", "pc")
            )
            if pc_dir not in sys.path:
                sys.path.insert(0, pc_dir)

            from detector import Detector  # noqa: E402

            self._detector = Detector()

        return self._detector.detect(frame)
