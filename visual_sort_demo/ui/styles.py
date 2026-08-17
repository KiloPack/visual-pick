# -*- coding: utf-8 -*-
"""统一配色与样式：简洁工程科技风（深色）。"""

from PySide6.QtGui import QColor

# ---------- 背景 ----------
BG_WINDOW = "#14161A"   # 主窗口背景
BG_PANEL = "#1B1F26"    # 右侧面板背景
BG_SCENE = "#181B21"    # 动画场景背景

# ---------- 模块静止态 ----------
MODULE_FILL = "#232833"
MODULE_BORDER = "#3A4351"
MODULE_TITLE = "#E8EBF0"
MODULE_SUBTEXT = "#8A93A3"

# ---------- 高亮 ----------
ACCENT = "#4DA3FF"
ACTIVE_FILL = "#22303F"

# ---------- 分类 / 信号色 ----------
C_NUT = "#43D17C"       # 螺母 绿
C_WASHER = "#F2C94C"    # 垫片 黄
C_UNKNOWN = "#F28C4B"   # 未知 橙
C_EMPTY = "#E5484D"     # 空   红
C_CAMERA = "#4DA3FF"    # 摄像头 蓝
C_STM32 = "#A78BFA"     # STM32 紫
C_UART = "#43D17C"      # 串口 绿
C_PWM = "#F2C94C"       # PWM 黄

# ---------- 文字 ----------
TEXT_PRIMARY = "#E8EBF0"
TEXT_SECONDARY = "#8A93A3"
TEXT_DIM = "#5A6373"

# 标签 -> 颜色
LABEL_COLOR = {
    "NUT": C_NUT,
    "WASHER": C_WASHER,
    "UNKNOWN": C_UNKNOWN,
    "EMPTY": C_EMPTY,
}

# 标签 -> 中文
LABEL_CN = {
    "NUT": "螺母",
    "WASHER": "垫片",
    "UNKNOWN": "未知",
    "EMPTY": "空",
}

# 标签 -> 串口指令（与 sorter.py 的 LABEL_TO_COMMAND 一致）
LABEL_COMMAND = {
    "NUT": "N",
    "WASHER": "W",
    "UNKNOWN": "X",
}


def lerp_color(c1, c2, t):
    """在两个十六进制颜色之间线性插值，返回 QColor。t 会被夹到 [0, 1]。"""
    a = QColor(c1)
    b = QColor(c2)
    t = max(0.0, min(1.0, t))
    return QColor(
        int(a.red() + (b.red() - a.red()) * t),
        int(a.green() + (b.green() - a.green()) * t),
        int(a.blue() + (b.blue() - a.blue()) * t),
    )


# 全局样式表
STYLESHEET = """
QMainWindow, QWidget {
    background: #14161A;
    color: #E8EBF0;
    font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
}
QLabel#titleLabel {
    font-size: 20px;
    font-weight: bold;
    color: #E8EBF0;
    padding: 10px;
}
QLabel#sectionHeader {
    font-size: 13px;
    font-weight: bold;
    color: #4DA3FF;
    padding: 2px;
}
QLabel#statKey {
    color: #8A93A3;
    font-size: 13px;
}
QLabel#statValue {
    color: #E8EBF0;
    font-size: 24px;
    font-weight: bold;
}
QLabel#statusKey {
    color: #8A93A3;
    font-size: 12px;
}
QLabel#statusValue {
    color: #E8EBF0;
    font-size: 13px;
    font-weight: bold;
}
QFrame#panel {
    background: #1B1F26;
    border: 1px solid #2A313C;
    border-radius: 8px;
}
QPushButton {
    background: #232833;
    border: 1px solid #3A4351;
    border-radius: 6px;
    color: #E8EBF0;
    padding: 8px 16px;
    font-size: 13px;
}
QPushButton:hover {
    border-color: #4DA3FF;
    background: #2A323F;
}
QPushButton:pressed {
    background: #1A2029;
}
QPushButton:checked {
    background: #1F3A5F;
    border-color: #4DA3FF;
    color: #FFFFFF;
}
QPlainTextEdit {
    background: #14161A;
    border: 1px solid #2A313C;
    border-radius: 6px;
    color: #9AA3AF;
    font-family: "Consolas", "Courier New", monospace;
    font-size: 12px;
}
QGraphicsView {
    background: #181B21;
    border: 1px solid #2A313C;
    border-radius: 8px;
}
"""
