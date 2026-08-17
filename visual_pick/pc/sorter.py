# -*- coding: utf-8 -*-
"""
sorter.py —— 自动分拣状态机（去抖动 + 确认）
====================================================
职责：接收每帧的识别结果，判断「该不该发送分拣指令」。
     通过「连续 N 帧一致才确认」的机制，避免识别抖动导致频繁误发送。

设计目标（纯逻辑，不依赖 Qt / 串口 / 摄像头，可独立测试）：
    - 输入：一帧的 label（EMPTY / NUT / WASHER / UNKNOWN）
    - 输出：本次需要发送的指令（"N" / "W" / "X"），无需发送返回 None
    - 内部维护：状态、连续一致帧数、各类计数

状态机（三个状态）：
    IDLE（空闲）      —— 画面为空，等待物料出现
    CONFIRMING（确认中）—— 有候选类别，正在数连续帧
    CONFIRMED（已确认） —— 已发送指令，等待物料离开（看到 EMPTY 才复位）

状态转移（每进来一帧 label）：
    IDLE        + EMPTY          -> 保持 IDLE
    IDLE        + 非空(label)     -> CONFIRMING，候选=label，计数=1
    CONFIRMING  + 同 label        -> 计数+1；达到 confirm_frames 则 CONFIRMED 并返回指令
    CONFIRMING  + 不同非空        -> 换成新候选，计数=1（重新确认）
    CONFIRMING  + EMPTY           -> 回 IDLE（物料在确认前消失，不发送）
    CONFIRMED   + 任意非空        -> 保持 CONFIRMED（物料没离开，不重复发送）
    CONFIRMED   + EMPTY           -> 回 IDLE（物料离开，准备下一件）

一个重要前提：相邻物料之间必须有一个 EMPTY 间隙（对应流程第 7 点
「若为空则不发送」）。这是传送带分拣的常见情况。
"""

from __future__ import annotations

from labels import LABEL_EMPTY, LABEL_NUT, LABEL_UNKNOWN, LABEL_WASHER

# 状态常量
STATE_IDLE = "IDLE"
STATE_CONFIRMING = "CONFIRMING"
STATE_CONFIRMED = "CONFIRMED"

# 分类 -> 需要发送的指令（EMPTY 不发送，故不在此表）
LABEL_TO_COMMAND = {
    LABEL_NUT: "N",
    LABEL_WASHER: "W",
    LABEL_UNKNOWN: "X",
}


class SortingController:
    """自动分拣状态机。"""

    def __init__(self, confirm_frames: int = 5) -> None:
        # 连续多少帧一致才确认；越大越抗抖，但响应越慢
        self.confirm_frames = confirm_frames
        self.reset()

    def reset(self) -> None:
        """复位状态、候选、计数（例如开始新一轮检测时调用）。"""
        self.state = STATE_IDLE
        self._candidate = None        # 当前候选类别
        self._counter = 0             # 连续一致帧数
        self.stable_label = None      # 最近一次确认的类别（稳定状态）
        self.counts = {LABEL_NUT: 0, LABEL_WASHER: 0, LABEL_UNKNOWN: 0}

    @property
    def state_name(self) -> str:
        """状态的中文描述，用于 GUI 显示。"""
        if self.state == STATE_IDLE:
            return "空闲"
        if self.state == STATE_CONFIRMING:
            return f"确认中 {self._candidate} {self._counter}/{self.confirm_frames}"
        return f"已确认 {self.stable_label}"

    def update(self, label: str) -> str | None:
        """
        输入一帧识别结果，返回需要发送的指令（"N"/"W"/"X"），无需发送返回 None。

        参数：
            label：识别结果，取 EMPTY / NUT / WASHER / UNKNOWN
        返回：
            需要发送的分拣指令字符串，或 None（本帧无需动作）
        """
        # 防御：把异常标签统一按「未知」处理
        if label not in (LABEL_EMPTY, LABEL_NUT, LABEL_WASHER, LABEL_UNKNOWN):
            label = LABEL_UNKNOWN

        # 1) 画面为空：物料离开或本来就没有 -> 复位到空闲
        if label == LABEL_EMPTY:
            self.state = STATE_IDLE
            self._candidate = None
            self._counter = 0
            return None

        # 2) 空闲状态下第一次看到物料 -> 开始确认
        if self.state == STATE_IDLE:
            self.state = STATE_CONFIRMING
            self._candidate = label
            self._counter = 1
            return None

        # 3) 确认中
        if self.state == STATE_CONFIRMING:
            if label == self._candidate:
                # 与候选一致，计数 +1
                self._counter += 1
                if self._counter >= self.confirm_frames:
                    # 连续 N 帧一致，确认！
                    self.state = STATE_CONFIRMED
                    self.stable_label = label
                    self.counts[label] += 1
                    return LABEL_TO_COMMAND.get(label)
                return None
            else:
                # 类别变了（可能是抖动），重新开始确认
                self._candidate = label
                self._counter = 1
                return None

        # 4) 已确认：物料还没离开，忽略后续波动，不重复发送
        if self.state == STATE_CONFIRMED:
            return None

        return None


if __name__ == "__main__":
    # 自测：不依赖 GUI / 串口，直接跑这段验证状态机逻辑
    print("=== 自测：验证「连续 N 帧一致才确认」 ===")
    ctrl = SortingController(confirm_frames=3)

    # 模拟一段识别序列，其中第 4 帧故意混入一次 WASHER 抖动
    seq = [
        LABEL_EMPTY, LABEL_EMPTY,
        LABEL_NUT, LABEL_NUT, LABEL_WASHER, LABEL_NUT, LABEL_NUT, LABEL_NUT,
        LABEL_EMPTY,
        LABEL_WASHER, LABEL_WASHER, LABEL_WASHER,
        LABEL_EMPTY,
        LABEL_UNKNOWN, LABEL_UNKNOWN, LABEL_UNKNOWN,
        LABEL_EMPTY,
    ]

    for i, label in enumerate(seq):
        command = ctrl.update(label)
        mark = f" -> 发送 {command}" if command else ""
        print(f"帧{i:02d}  {label:<8}  状态={ctrl.state_name:<22}{mark}")

    print("\n最终计数：", ctrl.counts)
    # 预期：NUT/WASHER/UNKNOWN 各确认 1 次、各发送 1 次，中间那次抖动被过滤掉
