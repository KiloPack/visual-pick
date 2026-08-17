# -*- coding: utf-8 -*-
"""动画场景：组装所有设备，维护布局与引用，供控制器驱动动画。

布局说明（横向 900 × 纵向 940 的场景坐标系）：
    - 左侧 x=340 为「物理通道」：储料 → 送料舵机 → 摄像头 → 分拣舵机 → 收集箱，
      物料沿这条竖直滑道下落。
    - 右侧 x=660 为「信号通道」：OpenCV → STM32，数据箭头从摄像头右侧引出、
      依次经过 OpenCV / STM32，再回到分拣舵机。
    这样物料下落路径与信息流互不遮挡。
"""

import math

from PySide6.QtCore import QRectF, Qt, QPointF
from PySide6.QtGui import QColor, QPen, QPainterPath
from PySide6.QtWidgets import QGraphicsScene, QGraphicsPathItem, QGraphicsLineItem

from ui.styles import (
    BG_SCENE,
    TEXT_DIM,
    C_NUT,
    C_WASHER,
    C_UNKNOWN,
    C_CAMERA,
    C_STM32,
    C_UART,
    C_PWM,
)
from scene.module_item import ModuleItem
from scene.servo_item import ServoItem
from scene.material_item import MaterialItem
from scene.data_packet import DataPacketItem

# 场景关键坐标
CHUTE_X = 340   # 物理通道 x
DATA_X = 660    # 信号通道 x


class SortingScene(QGraphicsScene):
    """视觉分拣系统的静态原理图。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setBackgroundBrush(QColor(BG_SCENE))
        self.setSceneRect(0, 0, 900, 940)
        self._build_layout()

    # ------------------------------------------------------------------
    # 静态布局
    # ------------------------------------------------------------------
    def _build_layout(self):
        # 1. 储料区
        self.hopper = ModuleItem(240, 70, "储料区", "HOPPER")
        self._add_centered(self.hopper, CHUTE_X, 16)

        # 2. 送料舵机 #1
        self.feeder_servo = ServoItem("SG90 #1 送料", body_w=150, body_h=46, arm_len=46)
        self._add_centered(self.feeder_servo, CHUTE_X, 96)

        # 3. 当前物料（初始放在送料口下方，隐藏，等待送料动画触发）
        self.material = MaterialItem("NUT", size=40)
        self.material.setPos(CHUTE_X, 220)
        self.material.setVisible(False)
        self.addItem(self.material)

        # 4. 摄像头检测区（物理通道上）
        self.camera_module = ModuleItem(300, 130, "摄像头检测区", "CAMERA")
        self.camera_module.set_accent(C_CAMERA)
        self._add_centered(self.camera_module, CHUTE_X, 236)

        # 摄像头扫描线（水平亮线，采集时上下扫动）
        self.scan_line = QGraphicsLineItem(0, 0, 260, 0)
        self.scan_line.setPen(QPen(QColor(C_CAMERA), 3))
        self.scan_line.setPos(210, 262)
        self.scan_line.setVisible(False)
        self.addItem(self.scan_line)
        self.scan_y1 = 262.0
        self.scan_y2 = 352.0

        # 5. OpenCV 识别（信号通道上）
        self.opencv_module = ModuleItem(260, 96, "OpenCV 识别", "VISION")
        self.opencv_module.set_accent(C_CAMERA)
        self.opencv_module.set_status("Result: --")
        self._add_centered(self.opencv_module, DATA_X, 396)

        # 6. STM32（信号通道上）
        self.stm32_module = ModuleItem(260, 96, "STM32F103C8T6", "MCU")
        self.stm32_module.set_accent(C_STM32)
        self.stm32_module.set_status("Command: --")
        self._add_centered(self.stm32_module, DATA_X, 540)

        # 7. 分拣舵机 #2（物理通道上）
        self.sorting_servo = ServoItem("SG90 #2 分拣", body_w=150, body_h=46, arm_len=52)
        self._add_centered(self.sorting_servo, CHUTE_X, 676)

        # 8. 收集箱（底部三个：左 NUT / 中 UNKNOWN / 右 WASHER）
        self.bins = {}
        self.bins["NUT"] = ModuleItem(190, 92, "NUT BIN", "螺母")
        self.bins["NUT"].set_accent(C_NUT)
        self._add_centered(self.bins["NUT"], 135, 816)

        self.bins["UNKNOWN"] = ModuleItem(190, 92, "UNKNOWN BIN", "未知")
        self.bins["UNKNOWN"].set_accent(C_UNKNOWN)
        self._add_centered(self.bins["UNKNOWN"], CHUTE_X, 816)

        self.bins["WASHER"] = ModuleItem(190, 92, "WASHER BIN", "垫片")
        self.bins["WASHER"].set_accent(C_WASHER)
        self._add_centered(self.bins["WASHER"], 545, 816)

        # 9. 静态连接箭头
        self._add_arrow(CHUTE_X, 86, CHUTE_X, 96)        # 储料 → 送料舵机
        self._add_arrow(CHUTE_X, 188, CHUTE_X, 236)      # 送料舵机 → 摄像头（物料滑道）
        self._add_arrow(490, 301, 530, 444)              # 摄像头 → OpenCV（图像）
        self._add_arrow(DATA_X, 492, DATA_X, 540)        # OpenCV → STM32（UART）
        self._add_arrow(530, 588, 415, 676)              # STM32 → 分拣舵机（PWM）
        self._add_arrow(CHUTE_X, 774, 135, 816)          # 分拣舵机 → NUT 箱
        self._add_arrow(CHUTE_X, 774, 545, 816)          # 分拣舵机 → WASHER 箱
        self._add_arrow(CHUTE_X, 774, CHUTE_X, 816)      # 分拣舵机 → UNKNOWN 箱

        # 10. 数据包（沿箭头流动的小标签，默认隐藏）
        self.frame_packet = DataPacketItem("FRAME", C_CAMERA)
        self.frame_packet.setVisible(False)
        self.addItem(self.frame_packet)

        self.uart_packet = DataPacketItem("N", C_UART)
        self.uart_packet.setVisible(False)
        self.addItem(self.uart_packet)

        self.pwm_packet = DataPacketItem("PWM", C_PWM)
        self.pwm_packet.setVisible(False)
        self.addItem(self.pwm_packet)

        # 数据包流动路径（起点 -> 终点，均为中心点坐标）
        self.packet_paths = {
            "frame": (QPointF(490, 301), QPointF(530, 444)),
            "uart": (QPointF(DATA_X, 492), QPointF(DATA_X, 540)),
            "pwm": (QPointF(530, 588), QPointF(415, 676)),
        }

        # 物料动画路径锚点（供控制器使用）
        self.path_points = {
            "wait": QPointF(CHUTE_X, 220),       # 送料口下方等待
            "camera": QPointF(CHUTE_X, 301),     # 摄像头检测中心
            "diverter": QPointF(CHUTE_X, 720),   # 分拣舵机枢轴
            "nut_bin": QPointF(135, 862),        # NUT 箱中心
            "washer_bin": QPointF(545, 862),     # WASHER 箱中心
            "unknown_bin": QPointF(CHUTE_X, 862),  # UNKNOWN 箱中心
        }

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------
    def _add_centered(self, item, cx, top_y):
        """按中心 x 坐标放置图形项。"""
        rect = item.boundingRect()
        item.setPos(cx - rect.width() / 2, top_y)
        self.addItem(item)

    def _add_arrow(self, x1, y1, x2, y2, color=TEXT_DIM, width=2, head=9):
        """画一条带箭头的静态连线。"""
        path = QPainterPath()
        path.moveTo(x1, y1)
        path.lineTo(x2, y2)

        angle = math.atan2(y2 - y1, x2 - x1)
        a1 = angle + math.radians(150)
        a2 = angle - math.radians(150)
        path.moveTo(x2, y2)
        path.lineTo(x2 + head * math.cos(a1), y2 + head * math.sin(a1))
        path.lineTo(x2 + head * math.cos(a2), y2 + head * math.sin(a2))
        path.closeSubpath()

        item = QGraphicsPathItem(path)
        item.setPen(QPen(QColor(color), width))
        self.addItem(item)

    # ------------------------------------------------------------------
    # 场景级操作
    # ------------------------------------------------------------------
    def set_active_module(self, name):
        """高亮指定模块、其余模块降为低权重。name 为 None 时全部熄灭。"""
        modules = {
            "hopper": self.hopper,
            "camera": self.camera_module,
            "opencv": self.opencv_module,
            "stm32": self.stm32_module,
            "nut_bin": self.bins["NUT"],
            "washer_bin": self.bins["WASHER"],
            "unknown_bin": self.bins["UNKNOWN"],
        }
        for key, m in modules.items():
            m.set_highlight_level(1.0 if key == name else 0.0)

        self.feeder_servo.set_active(name == "feeder")
        self.sorting_servo.set_active(name == "sorting")

    def clear_active(self):
        """清除所有高亮（待机状态）。"""
        self.set_active_module(None)

    def reset(self):
        """复位到初始静态状态。"""
        self.material.setVisible(False)
        self.material.set_material("NUT")
        self.feeder_servo.set_arm_angle(0.0)
        self.feeder_servo.set_active(False)
        self.sorting_servo.set_arm_angle(0.0)
        self.sorting_servo.set_active(False)
        self.scan_line.setVisible(False)
        self.scan_line.setY(self.scan_y1)
        for p in (self.frame_packet, self.uart_packet, self.pwm_packet):
            p.setVisible(False)
        self.opencv_module.set_status("Result: --")
        self.stm32_module.set_status("Command: --")
        self.clear_active()
