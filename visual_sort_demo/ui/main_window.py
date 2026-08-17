# -*- coding: utf-8 -*-
"""主窗口：动画场景 + 右侧状态面板 + 底部按钮与日志。"""

from datetime import datetime

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QFrame,
    QGraphicsView,
    QPushButton,
    QPlainTextEdit,
    QGridLayout,
)

from ui.styles import STYLESHEET, C_NUT, C_WASHER, C_UNKNOWN
from scene.sorting_scene import SortingScene
from core.demo_controller import DemoController


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("视觉分拣系统运行原理动态演示")
        self.resize(1480, 900)
        self.setStyleSheet(STYLESHEET)

        self.scene = SortingScene()
        self.controller = DemoController(self.scene)

        self._build_ui()
        self._wire_controller()

        QTimer.singleShot(0, self._fit_scene)
        self._log("系统就绪。点击「演示 NUT / WASHER / UNKNOWN」或「自动循环」开始。")

    # ------------------------------------------------------------------
    # 界面构建
    # ------------------------------------------------------------------
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(10)

        # 标题
        title = QLabel("视觉分拣系统运行原理动态演示")
        title.setObjectName("titleLabel")
        title.setAlignment(Qt.AlignCenter)
        root.addWidget(title)

        # 中部：动画场景 + 右侧面板
        main_row = QHBoxLayout()
        main_row.setSpacing(12)
        main_row.addWidget(self._build_scene_view(), 3)
        main_row.addWidget(self._build_right_panel(), 1)
        root.addLayout(main_row, 1)

        # 底部按钮
        root.addLayout(self._build_buttons())

        # 底部日志
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumHeight(110)
        self.log_view.setPlaceholderText("运行日志")
        root.addWidget(self.log_view)

    def _build_scene_view(self):
        self.view = QGraphicsView(self.scene)
        self.view.setRenderHint(QPainter.Antialiasing, True)
        self.view.setRenderHint(QPainter.SmoothPixmapTransform, True)
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.view.setFrameShape(QFrame.NoFrame)
        return self.view

    def _build_right_panel(self):
        panel = QFrame()
        panel.setObjectName("panel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # ---- 状态区 ----
        status_header = QLabel("SYSTEM STATUS")
        status_header.setObjectName("sectionHeader")
        layout.addWidget(status_header)

        self.status_labels = {}
        status_grid = QGridLayout()
        status_grid.setHorizontalSpacing(12)
        status_grid.setVerticalSpacing(6)
        status_fields = [
            ("current_object", "Current Object", "--"),
            ("vision_result", "Vision Result", "--"),
            ("uart", "UART", "TX → --"),
            ("stm32", "STM32", "STANDBY"),
            ("feeder", "Feeder Servo", "CLOSED"),
            ("sorting", "Sorting Servo", "CENTER"),
            ("process", "Process", "IDLE"),
        ]
        for row, (key, name, default) in enumerate(status_fields):
            k = QLabel(name)
            k.setObjectName("statusKey")
            v = QLabel(default)
            v.setObjectName("statusValue")
            status_grid.addWidget(k, row, 0, Qt.AlignLeft)
            status_grid.addWidget(v, row, 1, Qt.AlignRight)
            self.status_labels[key] = v
        layout.addLayout(status_grid)

        # ---- 统计区 ----
        stats_header = QLabel("STATISTICS")
        stats_header.setObjectName("sectionHeader")
        layout.addWidget(stats_header)

        self.stat_labels = {}
        stats_grid = QGridLayout()
        stats_grid.setHorizontalSpacing(12)
        stats_grid.setVerticalSpacing(6)
        stats_fields = [
            ("total", "TOTAL", None),
            ("NUT", "NUT", C_NUT),
            ("WASHER", "WASHER", C_WASHER),
            ("UNKNOWN", "UNKNOWN", C_UNKNOWN),
        ]
        for row, (key, name, color) in enumerate(stats_fields):
            k = QLabel(name)
            k.setObjectName("statKey")
            v = QLabel("0")
            v.setObjectName("statValue")
            if color:
                v.setStyleSheet(f"color: {color};")
            stats_grid.addWidget(k, row, 0, Qt.AlignLeft)
            stats_grid.addWidget(v, row, 1, Qt.AlignRight)
            self.stat_labels[key] = v
        layout.addLayout(stats_grid)

        layout.addStretch(1)
        return panel

    def _build_buttons(self):
        row = QHBoxLayout()
        row.setSpacing(10)

        self.btn_start = QPushButton("开始演示")
        self.btn_pause = QPushButton("暂停")
        self.btn_reset = QPushButton("重置")
        self.btn_nut = QPushButton("演示 NUT")
        self.btn_washer = QPushButton("演示 WASHER")
        self.btn_unknown = QPushButton("演示 UNKNOWN")
        self.btn_auto = QPushButton("自动循环")
        self.btn_auto.setCheckable(True)

        for b in (self.btn_start, self.btn_pause, self.btn_reset):
            row.addWidget(b)
        row.addSpacing(24)
        for b in (self.btn_nut, self.btn_washer, self.btn_unknown):
            row.addWidget(b)
        row.addSpacing(24)
        row.addWidget(self.btn_auto)
        row.addStretch(1)

        self.btn_start.clicked.connect(self.controller.start)
        self.btn_pause.clicked.connect(self._on_pause)
        self.btn_reset.clicked.connect(self._on_reset)
        self.btn_nut.clicked.connect(lambda: self.controller.trigger_sort("NUT"))
        self.btn_washer.clicked.connect(lambda: self.controller.trigger_sort("WASHER"))
        self.btn_unknown.clicked.connect(lambda: self.controller.trigger_sort("UNKNOWN"))
        self.btn_auto.toggled.connect(self.controller.set_auto_loop)

        return row

    def _wire_controller(self):
        self.controller.log.connect(self._log)
        self.controller.status.connect(self._apply_status)
        self.controller.stats.connect(self._apply_stats)

    # ------------------------------------------------------------------
    # 按钮处理
    # ------------------------------------------------------------------
    def _on_pause(self):
        if self.controller.is_paused():
            self.controller.resume()
            self.btn_pause.setText("暂停")
        elif self.controller.is_running():
            self.controller.pause()
            self.btn_pause.setText("继续")
        # 空闲时不响应，避免按钮文字错乱

    def _on_reset(self):
        self.controller.reset()
        self.btn_pause.setText("暂停")

    # ------------------------------------------------------------------
    # 控制器信号 -> 界面更新
    # ------------------------------------------------------------------
    def _apply_status(self, d):
        for key, value in d.items():
            if key in self.status_labels:
                self.status_labels[key].setText(value)

    def _apply_stats(self, s):
        for key, value in s.items():
            if key in self.stat_labels:
                self.stat_labels[key].setText(str(value))

    # ------------------------------------------------------------------
    # 辅助
    # ------------------------------------------------------------------
    def _log(self, msg):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_view.appendPlainText(f"{ts}  {msg}")

    def _fit_scene(self):
        self.view.fitInView(self.scene.sceneRect(), Qt.KeepAspectRatio)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit_scene()
