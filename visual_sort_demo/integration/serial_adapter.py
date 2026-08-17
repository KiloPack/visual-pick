# -*- coding: utf-8 -*-
"""串口适配器：统一「发送分拣指令」的接口。

第一版默认 Mock 模式（不依赖 pyserial），只返回指令、不真正打开串口。
接入真实 STM32 时用 mode="real"（或 use_real()），内部延迟导入并委托给
visual_pick/pc/serial_manager.py 的 SerialManager。

协议与真实工程一致：115200 8N1；指令 N=螺母 / W=垫片 / X=未知。
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

# 标签 -> 指令（与真实 sorter.py 的 LABEL_TO_COMMAND 一致）
LABEL_TO_COMMAND = {
    "NUT": "N",
    "WASHER": "W",
    "UNKNOWN": "X",
}


class SerialAdapter(QObject):
    """串口适配器。Mock 模式不发 IO，Real 模式委托 SerialManager。"""

    ack_received = Signal(str)   # 收到固件应答（NUT / WASHER / UNKNOWN / BUSY）

    def __init__(self, mode="mock", parent=None):
        super().__init__(parent)
        self.mode = mode
        self._manager = None

    def use_real(self):
        self.mode = "real"
        return self

    def command_for(self, label):
        """返回 label 对应的指令字符（不发送）。"""
        return LABEL_TO_COMMAND.get(label, "X")

    def send_command(self, label):
        """发送分拣指令，返回实际发送的指令字符（N/W/X）。"""
        cmd = self.command_for(label)
        if self.mode == "real":
            self._real_send(cmd)
        else:
            self._mock_send(cmd)
        return cmd

    # ------------------------------------------------------------------
    # Mock / Real
    # ------------------------------------------------------------------
    def _mock_send(self, cmd):
        # 模拟模式：不做真实 IO。可在此扩展"模拟固件应答"：
        # 例如 QTimer.singleShot 后 self.ack_received.emit("NUT")
        pass

    def _real_send(self, cmd):
        manager = self._ensure_manager()
        if not manager.is_connected():
            raise RuntimeError("串口未连接，无法发送真实指令（请先 connect）")
        manager.send_data(cmd)

    def connect(self, port, baudrate=115200):
        """Real 模式下打开串口（Mock 模式忽略）。"""
        if self.mode == "real":
            self._ensure_manager().connect(port, baudrate)

    def disconnect(self):
        """断开串口（如已打开）。"""
        if self._manager is not None:
            self._manager.disconnect()

    def is_connected(self):
        return self._manager is not None and self._manager.is_connected()

    def _ensure_manager(self):
        if self._manager is None:
            import os
            import sys

            # 默认假设 visual_sort_demo 与 visual_pick 在同一个父目录下。
            pc_dir = os.path.abspath(
                os.path.join(os.path.dirname(__file__), "..", "..", "visual_pick", "pc")
            )
            if pc_dir not in sys.path:
                sys.path.insert(0, pc_dir)

            from serial_manager import SerialManager  # noqa: E402

            self._manager = SerialManager()
        return self._manager
