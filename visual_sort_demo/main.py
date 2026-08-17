# -*- coding: utf-8 -*-
"""程序入口：视觉分拣系统运行原理动态演示。

运行方式：
    python main.py
"""

import sys

from PySide6.QtWidgets import QApplication

from ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
