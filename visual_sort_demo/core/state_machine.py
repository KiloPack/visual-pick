# -*- coding: utf-8 -*-
"""状态机定义：分拣流程的各个阶段、停留时长与推进顺序。"""

from enum import Enum


class State(Enum):
    """分拣演示的状态。"""
    IDLE = "IDLE"                          # 等待物料
    FEEDING = "FEEDING"                    # 送料舵机释放单个物料
    MOVING_TO_CAMERA = "MOVING_TO_CAMERA"  # 物料下滑到检测区
    CAPTURING = "CAPTURING"                # 摄像头采集
    ANALYZING = "ANALYZING"                # OpenCV 识别
    TRANSMITTING = "TRANSMITTING"          # 串口发送指令
    STM32_PROCESSING = "STM32_PROCESSING"  # STM32 处理
    SERVO_SORTING = "SERVO_SORTING"        # 分拣舵机转向
    MOVING_TO_BIN = "MOVING_TO_BIN"        # 物料滑入收集箱
    COMPLETE = "COMPLETE"                  # 完成并计数


# 每个状态的停留时长（毫秒）。IDLE 为 0，表示等待外部触发。
STATE_DURATIONS = {
    State.IDLE: 0,
    State.FEEDING: 900,
    State.MOVING_TO_CAMERA: 800,
    State.CAPTURING: 700,
    State.ANALYZING: 800,
    State.TRANSMITTING: 600,
    State.STM32_PROCESSING: 600,
    State.SERVO_SORTING: 700,
    State.MOVING_TO_BIN: 900,
    State.COMPLETE: 600,
}

# 状态推进顺序（不含 IDLE）
FLOW = [
    State.FEEDING,
    State.MOVING_TO_CAMERA,
    State.CAPTURING,
    State.ANALYZING,
    State.TRANSMITTING,
    State.STM32_PROCESSING,
    State.SERVO_SORTING,
    State.MOVING_TO_BIN,
    State.COMPLETE,
]
