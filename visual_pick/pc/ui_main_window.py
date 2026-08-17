# -*- coding: utf-8 -*-
"""
ui_main_window.py —— 视觉分拣上位机主窗口界面
====================================================
职责：只负责「界面框架」与「事件调度」，不写具体算法。
      - 识别算法：detector.py
      - 摄像头：camera.py
      - 后台检测线程：worker.py
      - 串口：serial_manager.py
      - 自动分拣状态机：sorter.py

界面分为四大区域：
    左侧  —— 摄像头原始画面显示区
    中间  —— 二值图显示区
    中间右 —— 检测框图显示区（叠加检测框与标签）
    右侧  —— 状态面板（分类结果、分拣状态、最近发送、面积/圆度/顶点、计数、串口状态）
    下方  —— 日志输出区

自动分拣流程（自动模式下）：
    摄像头 -> 识别(label) -> 状态机去抖确认 -> 发 N/W/X -> 更新计数/最近发送
"""

from __future__ import annotations

import time
from html import escape as html_escape

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

# ---- 项目内各模块 ----
from camera import DemoCamera, create_camera
from detector import (
    Detector,
    KEY_AREA,
    KEY_BINARY,
    KEY_CIRCULARITY,
    KEY_DEBUG_FRAME,
    KEY_LABEL,
    KEY_VERTICES,
    LABEL_EMPTY,
    LABEL_NUT,
    LABEL_UNKNOWN,
    LABEL_WASHER,
)
from image_utils import numpy_to_pixmap
from worker import DetectionWorker
from serial_manager import SerialManager, SerialReader, SerialError
from sorter import SortingController

# ---------------------------------------------------------------------------
# 尝试导入 pyserial 用于枚举可用串口；若未安装，则使用占位串口列表。
# ---------------------------------------------------------------------------
try:
    from serial.tools import list_ports
    HAS_PYSERIAL = True
except ImportError:  # pragma: no cover - 未安装 pyserial 时走这里
    HAS_PYSERIAL = False

# 常用波特率列表，默认选中 115200（与固件 USART1 一致）
BAUD_RATES = ["9600", "19200", "38400", "57600", "115200", "230400", "460800", "921600"]
DEFAULT_BAUD = "115200"

# CH340 USB-TTL 的 VID / PID，用于自动识别（与 serial_test.py 保持一致）
CH340_VID = 0x1A86
CH340_PID = 0x7523

# 手动发送指令及其含义（供 STM32 分拣机构识别）
MANUAL_COMMANDS = {
    "N": "螺母（NUT）",
    "W": "垫片（WASHER）",
    "X": "未知（UNKNOWN）",
}

# 摄像头源：0 表示默认摄像头；也可改成 "demo"（演示画面）或视频文件路径
CAMERA_INDEX = 0

# 连续多少帧一致才确认分拣结果（越大越抗抖，但响应越慢）
CONFIRM_FRAMES = 5

# 指令的中文名，用于「最近发送」显示
COMMAND_NAMES = {"N": "螺母", "W": "垫片", "X": "未知"}

# 分类结果对应的圆点颜色（Qt 十六进制颜色）
RESULT_COLORS = {
    LABEL_EMPTY: "#e74c3c",      # 红
    LABEL_NUT: "#2ecc71",        # 绿
    LABEL_WASHER: "#f1c40f",     # 黄
    LABEL_UNKNOWN: "#e67e22",    # 橙
}


class MainWindow(QMainWindow):
    """视觉分拣上位机主窗口。"""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("视觉分拣上位机")
        self.resize(1440, 900)
        self.setMinimumSize(1100, 640)

        # ---- 运行状态变量 ----
        self.detecting = False  # 是否正在检测

        # 后台检测线程（视觉）
        self._worker = None

        # 串口与后台读取线程
        self._serial = SerialManager()
        self._serial_reader = None

        # 自动分拣状态机
        self.sorter = SortingController(confirm_frames=CONFIRM_FRAMES)

        # 图像占位：保存最近一帧原图，用于窗口缩放时重新缩放
        self.img_camera = None
        self.img_binary = None
        self.img_debug = None
        self._camera_pixmap = None
        self._binary_pixmap = None
        self._debug_pixmap = None

        # ---- 构建界面 ----
        self._init_ui()
        self._init_connections()

        # ---- 初始化串口列表与状态显示 ----
        self._refresh_ports()
        self._update_serial_status()
        self._reset_result()
        self._update_sorter_display()

        self.log("程序启动，界面初始化完成。", "OK")

    # ------------------------------------------------------------------
    # 界面构建
    # ------------------------------------------------------------------
    def _init_ui(self) -> None:
        """构建整个界面布局。"""
        central = QWidget()
        self.setCentralWidget(central)

        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(8, 8, 8, 8)
        root_layout.setSpacing(8)

        # 顶部控制区
        root_layout.addWidget(self._build_control_bar())

        # 左：原始画面
        left_group = QGroupBox("摄像头原始画面")
        left_layout = QVBoxLayout(left_group)
        self.img_camera = self._make_image_label("摄像头原始画面\n（待接入）")
        left_layout.addWidget(self.img_camera)

        # 中：二值图
        binary_group = QGroupBox("二值图")
        binary_layout = QVBoxLayout(binary_group)
        self.img_binary = self._make_image_label("二值图\n（待接入）")
        binary_layout.addWidget(self.img_binary)

        # 中右：检测框图
        debug_group = QGroupBox("检测框图")
        debug_layout = QVBoxLayout(debug_group)
        self.img_debug = self._make_image_label("检测框图\n（待接入）")
        debug_layout.addWidget(self.img_debug)

        # 右：状态面板
        status_group = self._build_status_panel()

        # 四列水平分割（可拖动调整宽度）
        h_splitter = QSplitter(Qt.Horizontal)
        h_splitter.addWidget(left_group)
        h_splitter.addWidget(binary_group)
        h_splitter.addWidget(debug_group)
        h_splitter.addWidget(status_group)
        h_splitter.setStretchFactor(0, 3)
        h_splitter.setStretchFactor(1, 3)
        h_splitter.setStretchFactor(2, 3)
        h_splitter.setStretchFactor(3, 2)
        h_splitter.setSizes([360, 360, 360, 280])

        # 下方：日志输出区
        log_group = QGroupBox("日志输出")
        log_layout = QVBoxLayout(log_group)
        self.log_edit = QPlainTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setMaximumBlockCount(2000)
        log_layout.addWidget(self.log_edit)

        # 上（图像区）下（日志区）垂直分割
        v_splitter = QSplitter(Qt.Vertical)
        v_splitter.addWidget(h_splitter)
        v_splitter.addWidget(log_group)
        v_splitter.setStretchFactor(0, 4)
        v_splitter.setStretchFactor(1, 1)
        v_splitter.setSizes([640, 200])

        root_layout.addWidget(v_splitter)

    def _build_control_bar(self) -> QWidget:
        """构建顶部控制区。"""
        bar = QWidget()
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(0, 0, 0, 0)

        # 串口选择
        layout.addWidget(QLabel("串口："))
        self.combo_port = QComboBox()
        self.combo_port.setMinimumWidth(90)
        layout.addWidget(self.combo_port)

        # 波特率选择
        layout.addWidget(QLabel("波特率："))
        self.combo_baud = QComboBox()
        self.combo_baud.addItems(BAUD_RATES)
        self.combo_baud.setCurrentText(DEFAULT_BAUD)
        layout.addWidget(self.combo_baud)

        # 刷新串口列表
        self.btn_refresh = QPushButton("刷新串口")
        layout.addWidget(self.btn_refresh)

        # 连接 / 断开串口
        self.btn_connect = QPushButton("连接串口")
        layout.addWidget(self.btn_connect)

        layout.addSpacing(20)

        # 开始 / 停止检测
        self.btn_start = QPushButton("开始检测")
        self.btn_stop = QPushButton("停止检测")
        self.btn_stop.setEnabled(False)
        layout.addWidget(self.btn_start)
        layout.addWidget(self.btn_stop)

        layout.addSpacing(20)

        # 自动模式开关
        self.chk_auto = QCheckBox("自动模式")
        layout.addWidget(self.chk_auto)

        layout.addSpacing(20)

        # 手动发送 N / W / X
        layout.addWidget(QLabel("手动发送："))
        self.btn_n = QPushButton("N 螺母")
        self.btn_w = QPushButton("W 垫片")
        self.btn_x = QPushButton("X 未知")
        layout.addWidget(self.btn_n)
        layout.addWidget(self.btn_w)
        layout.addWidget(self.btn_x)

        layout.addStretch(1)
        return bar

    def _build_status_panel(self) -> QGroupBox:
        """构建右侧状态面板。"""
        group = QGroupBox("状态面板")
        outer = QVBoxLayout(group)

        form = QFormLayout()
        form.setVerticalSpacing(10)

        # 分类结果（带彩色圆点）
        self.state_dot = QLabel()
        self.state_dot.setFixedSize(12, 12)
        self.state_dot.setStyleSheet("background-color: #95a5a6; border-radius: 6px;")
        self.lbl_result = QLabel("—")
        self.lbl_result.setStyleSheet("font-size: 20px; font-weight: bold;")
        result_widget = QWidget()
        result_row = QHBoxLayout(result_widget)
        result_row.setContentsMargins(0, 0, 0, 0)
        result_row.addWidget(self.state_dot)
        result_row.addWidget(self.lbl_result)
        result_row.addStretch(1)
        form.addRow("分类结果：", result_widget)

        # 分拣状态 / 最近发送
        self.lbl_sorter_state = self._make_value_label("手动模式")
        self.lbl_last_sent = self._make_value_label("—")
        form.addRow("分拣状态：", self.lbl_sorter_state)
        form.addRow("最近发送：", self.lbl_last_sent)

        # 面积 / 圆度 / 顶点
        self.lbl_area = self._make_value_label("—")
        self.lbl_circularity = self._make_value_label("—")
        self.lbl_vertices = self._make_value_label("—")
        form.addRow("面积 area：", self.lbl_area)
        form.addRow("圆度 circularity：", self.lbl_circularity)
        form.addRow("顶点 vertices：", self.lbl_vertices)

        # 各类计数
        self.lbl_nut = self._make_value_label()
        self.lbl_washer = self._make_value_label()
        self.lbl_unknown = self._make_value_label()
        self.lbl_total = self._make_value_label()
        form.addRow("螺母计数：", self.lbl_nut)
        form.addRow("垫片计数：", self.lbl_washer)
        form.addRow("未知计数：", self.lbl_unknown)
        form.addRow("总次数：", self.lbl_total)

        # 串口状态
        self.lbl_serial = self._make_value_label("未连接")
        form.addRow("串口状态：", self.lbl_serial)

        outer.addLayout(form)
        outer.addStretch(1)
        return group

    @staticmethod
    def _make_image_label(placeholder_text: str) -> QLabel:
        """创建一个用于显示图像的 QLabel 占位标签。"""
        label = QLabel(placeholder_text)
        label.setAlignment(Qt.AlignCenter)
        label.setMinimumSize(280, 220)
        label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        label.setStyleSheet(
            "QLabel {"
            " background-color: #1e1e1e;"
            " color: #7f8c8d;"
            " border: 1px solid #3a3a3a;"
            " font-size: 14px;"
            "}"
        )
        return label

    @staticmethod
    def _make_value_label(text: str = "0") -> QLabel:
        """创建一个状态数值标签。"""
        label = QLabel(text)
        label.setStyleSheet("font-size: 15px; font-weight: bold;")
        return label

    # ------------------------------------------------------------------
    # 信号连接
    # ------------------------------------------------------------------
    def _init_connections(self) -> None:
        """把所有控件的信号连接到对应的槽函数。"""
        self.btn_refresh.clicked.connect(self._refresh_ports)
        self.btn_connect.clicked.connect(self._on_connect_clicked)
        self.btn_start.clicked.connect(self._on_start_clicked)
        self.btn_stop.clicked.connect(self._on_stop_clicked)
        self.btn_n.clicked.connect(lambda: self._on_manual_clicked("N"))
        self.btn_w.clicked.connect(lambda: self._on_manual_clicked("W"))
        self.btn_x.clicked.connect(lambda: self._on_manual_clicked("X"))
        self.chk_auto.toggled.connect(self._on_auto_toggled)

    # ------------------------------------------------------------------
    # 串口相关
    # ------------------------------------------------------------------
    def _refresh_ports(self) -> None:
        """刷新可用串口列表，并尽量自动选中 CH340。"""
        self.combo_port.clear()

        if not HAS_PYSERIAL:
            self.combo_port.addItems(["COM1", "COM2", "COM3", "COM4", "COM5", "COM6"])
            self.log("未安装 pyserial，显示占位串口列表。", "WARN")
            return

        infos = list(list_ports.comports())
        devices = [p.device for p in infos]
        if not devices:
            self.log("未检测到可用串口，请检查 USB-TTL 连接。", "WARN")
            return

        self.combo_port.addItems(devices)

        ch340 = next(
            (
                p.device
                for p in infos
                if (p.vid == CH340_VID and p.pid == CH340_PID)
                or "CH340" in (p.description or "").upper()
            ),
            None,
        )
        if ch340:
            self.combo_port.setCurrentText(ch340)
        elif len(devices) == 1:
            self.combo_port.setCurrentText(devices[0])

        self.log(f"检测到 {len(devices)} 个串口。")

    def _on_connect_clicked(self) -> None:
        """连接 / 断开串口。"""
        if self._serial.is_connected():
            self._disconnect_serial()
        else:
            self._connect_serial()

    def _connect_serial(self) -> None:
        """打开串口，并启动后台读取线程。"""
        port = self.combo_port.currentText().strip()
        baud = int(self.combo_baud.currentText())
        if not port:
            self.log("请先选择串口。", "ERROR")
            return

        try:
            self._serial.connect(port, baud)
        except SerialError as e:
            self.log(str(e), "ERROR")
            return

        # 启动后台读取线程，把固件回包显示到日志
        self._serial_reader = SerialReader(self._serial)
        self._serial_reader.data_received.connect(
            lambda text: self.log(f"收到：{text}", "OK")
        )
        self._serial_reader.error.connect(lambda text: self.log(text, "ERROR"))
        self._serial_reader.start()

        self.log(f"串口 {port} @ {baud} 已连接。", "OK")
        self._update_serial_status()

    def _disconnect_serial(self) -> None:
        """停止读线程并断开串口。"""
        if self._serial_reader is not None:
            self._serial_reader.stop()
            self._serial_reader.wait(1000)
            self._serial_reader = None

        if self._serial.is_connected():
            self._serial.disconnect()
            self.log("串口已断开。")

        self._update_serial_status()

    def _on_manual_clicked(self, command: str) -> None:
        """手动发送 N / W / X 指令。"""
        description = MANUAL_COMMANDS.get(command, command)
        if not self._serial.is_connected():
            self.log(f"串口未连接，无法发送 '{command}'（{description}）。", "WARN")
            return
        try:
            self._serial.send_data(command)
            self.lbl_last_sent.setText(f"{command}（{COMMAND_NAMES[command]}）")
            self.log(f"手动发送：{command}（{description}）", "OK")
        except SerialError as e:
            self.log(str(e), "ERROR")

    def _on_auto_toggled(self, checked: bool) -> None:
        """自动模式开关切换。"""
        if checked:
            self.sorter.reset()  # 开启自动模式时复位状态机，重新计数
            self._update_sorter_display()
            self.log("自动模式已开启，开始自动分拣。")
        else:
            self.lbl_sorter_state.setText("手动模式")
            self.log("自动模式已关闭，切换为手动。")

    def _update_serial_status(self) -> None:
        """根据串口连接状态刷新状态面板与按钮文字。"""
        if self._serial.is_connected():
            self.lbl_serial.setText("已连接")
            self.lbl_serial.setStyleSheet(
                "font-size: 15px; font-weight: bold; color: #2ecc71;"
            )
            self.btn_connect.setText("断开串口")
        else:
            self.lbl_serial.setText("未连接")
            self.lbl_serial.setStyleSheet(
                "font-size: 15px; font-weight: bold; color: #e74c3c;"
            )
            self.btn_connect.setText("连接串口")

    # ------------------------------------------------------------------
    # 检测启停 + 后台线程管理
    # ------------------------------------------------------------------
    def _on_start_clicked(self) -> None:
        """开始检测：复位状态机，创建摄像头与识别器，启动后台线程。"""
        self.detecting = True
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.sorter.reset()  # 新一轮检测，重新计数
        self._update_sorter_display()
        self.log("开始检测...")
        self._start_worker()

    def _on_stop_clicked(self) -> None:
        """停止检测：停止后台线程并释放摄像头。"""
        self.detecting = False
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.log("停止检测。")
        self._stop_worker()
        self._reset_result()

    def _start_worker(self) -> None:
        """创建并启动后台检测线程。"""
        camera = create_camera(CAMERA_INDEX)
        if not camera.open():
            camera.release()
            camera = DemoCamera()
            camera.open()
            self.log("未检测到摄像头，已切换到演示模式（合成画面）。", "WARN")
        else:
            self.log("摄像头已打开。", "OK")

        detector = Detector()
        self._worker = DetectionWorker(camera, detector, interval_ms=30)
        self._worker.result_ready.connect(self._on_result_ready)
        self._worker.failed.connect(lambda msg: self.log(msg, "ERROR"))
        self._worker.start()

    def _stop_worker(self) -> None:
        """停止后台线程并释放资源。"""
        worker = self._worker
        self._worker = None
        if worker is not None:
            worker.stop()
            worker.wait(2000)
            worker.deleteLater()

    def _on_result_ready(self, result: dict) -> None:
        """
        接收后台线程送来的检测结果并刷新界面（在 GUI 线程执行）。
        """
        # 1. 显示三张图
        frame = result.get("frame")
        binary = result.get(KEY_BINARY)
        debug = result.get(KEY_DEBUG_FRAME)

        if frame is not None:
            self.set_camera_image(numpy_to_pixmap(frame))
        if binary is not None:
            self.set_processed_image(numpy_to_pixmap(binary))
        if debug is not None:
            self.set_debug_image(numpy_to_pixmap(debug))

        # 2. 更新分类结果与特征指标
        label = result.get(KEY_LABEL, LABEL_EMPTY)
        area = result.get(KEY_AREA, 0.0)
        circularity = result.get(KEY_CIRCULARITY, 0.0)
        vertices = result.get(KEY_VERTICES, 0)
        self._set_result(label, area, circularity, vertices)

        # 3. 自动分拣：仅在「自动模式」下运行状态机
        if self.chk_auto.isChecked():
            command = self.sorter.update(label)
            if command is not None:
                self._send_sort_command(command)
            self._update_sorter_display()

    # ------------------------------------------------------------------
    # 自动分拣：发送指令 + 显示状态/计数
    # ------------------------------------------------------------------
    def _send_sort_command(self, command: str) -> None:
        """把确认后的分拣指令发给 STM32，并更新「最近发送」。"""
        name = COMMAND_NAMES.get(command, command)
        if not self._serial.is_connected():
            self.lbl_last_sent.setText(f"{command}（{name}）未连接")
            self.log(f"已确认 {name}，但串口未连接，未发送。", "WARN")
            return
        try:
            self._serial.send_data(command)
            self.lbl_last_sent.setText(f"{command}（{name}）")
            self.log(f"分拣指令已发送：{command}（{name}）", "OK")
        except SerialError as e:
            self.lbl_last_sent.setText(f"{command}（发送失败）")
            self.log(str(e), "ERROR")

    def _update_sorter_display(self) -> None:
        """把状态机的状态与计数刷新到界面。"""
        counts = self.sorter.counts
        self.lbl_nut.setText(str(counts[LABEL_NUT]))
        self.lbl_washer.setText(str(counts[LABEL_WASHER]))
        self.lbl_unknown.setText(str(counts[LABEL_UNKNOWN]))
        self.lbl_total.setText(str(sum(counts.values())))

        if self.chk_auto.isChecked():
            self.lbl_sorter_state.setText(self.sorter.state_name)
        else:
            self.lbl_sorter_state.setText("手动模式")

    # ------------------------------------------------------------------
    # 状态 / 图像更新
    # ------------------------------------------------------------------
    def _set_result(self, label: str, area: float,
                    circularity: float, vertices: int) -> None:
        """更新分类结果与特征指标显示。"""
        self.lbl_result.setText(label)
        color = RESULT_COLORS.get(label, "#95a5a6")
        self.state_dot.setStyleSheet(f"background-color: {color}; border-radius: 6px;")
        self.lbl_area.setText(f"{int(area)}")
        self.lbl_circularity.setText(f"{circularity:.3f}")
        self.lbl_vertices.setText(f"{int(vertices)}")

    def _reset_result(self) -> None:
        """把分类结果显示复位为「—」（未检测时）。"""
        self.lbl_result.setText("—")
        self.state_dot.setStyleSheet("background-color: #95a5a6; border-radius: 6px;")
        self.lbl_area.setText("—")
        self.lbl_circularity.setText("—")
        self.lbl_vertices.setText("—")

    def set_camera_image(self, pixmap: QPixmap) -> None:
        self._camera_pixmap = pixmap
        self._rescale_image(self.img_camera, pixmap)

    def set_processed_image(self, pixmap: QPixmap) -> None:
        self._binary_pixmap = pixmap
        self._rescale_image(self.img_binary, pixmap)

    def set_debug_image(self, pixmap: QPixmap) -> None:
        self._debug_pixmap = pixmap
        self._rescale_image(self.img_debug, pixmap)

    @staticmethod
    def _rescale_image(label: QLabel, pixmap: QPixmap) -> None:
        """按标签当前尺寸缩放显示，保持宽高比，并清除占位文字。"""
        if pixmap.isNull():
            return
        label.setPixmap(
            pixmap.scaled(label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        )
        label.setText("")

    def resizeEvent(self, event) -> None:
        """窗口尺寸变化时，重新缩放已显示的画面。"""
        super().resizeEvent(event)
        if self.img_camera is not None and self._camera_pixmap is not None:
            self._rescale_image(self.img_camera, self._camera_pixmap)
        if self.img_binary is not None and self._binary_pixmap is not None:
            self._rescale_image(self.img_binary, self._binary_pixmap)
        if self.img_debug is not None and self._debug_pixmap is not None:
            self._rescale_image(self.img_debug, self._debug_pixmap)

    def closeEvent(self, event) -> None:
        """关闭窗口前，先停止后台线程、读线程并释放摄像头/串口。"""
        self._stop_worker()
        self._disconnect_serial()
        super().closeEvent(event)

    # ------------------------------------------------------------------
    # 日志
    # ------------------------------------------------------------------
    def log(self, message: str, level: str = "INFO") -> None:
        """向日志区追加一行带时间戳的日志，level 控制颜色。"""
        if not hasattr(self, "log_edit") or self.log_edit is None:
            return
        colors = {
            "INFO": "#cccccc",
            "OK": "#2ecc71",
            "WARN": "#f1c40f",
            "ERROR": "#e74c3c",
        }
        color = colors.get(level, "#cccccc")
        timestamp = time.strftime("%H:%M:%S")
        safe_message = html_escape(message)
        self.log_edit.appendHtml(
            f'<span style="color:{color};">[{timestamp}] {safe_message}</span>'
        )
        scrollbar = self.log_edit.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
