# -*- coding: utf-8 -*-
"""
main.py —— 视觉分拣上位机程序入口
============================================

功能：
    1. 创建 Qt 应用程序对象
    2. 创建并显示主窗口
    3. 进入 Qt 事件循环

运行方式（在工程根目录执行）：
    python pc/main.py
"""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

# 从界面模块导入主窗口类（main.py 与 ui_main_window.py 位于同一目录）
from ui_main_window import MainWindow


def main() -> int:
    """程序主入口函数。"""
    # 1. 创建应用对象；sys.argv 用于接收命令行参数
    app = QApplication(sys.argv)

    # 2. 设置应用名称（在任务栏 / 系统内显示）
    app.setApplicationName("视觉分拣上位机")
    app.setOrganizationName("PickProject")

    # 3. 创建主窗口并显示
    window = MainWindow()
    window.show()

    # 4. 进入事件循环，直到窗口关闭后返回退出码
    return app.exec()


if __name__ == "__main__":
    # 把 main() 的返回值作为进程退出码交给操作系统
    sys.exit(main())
