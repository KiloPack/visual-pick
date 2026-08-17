# 视觉分拣原理动画

本目录是项目的辅助 PySide6 动画，用于展示“视觉检测 → 分类决策 → 串口数据 → STM32 → 舵机分流”的信息流。它不是最终实机分类算法，最终硬件入口请使用：

```text
visual_pick/pc/visual_sort.py
```

## Mock 模式

在仓库根目录运行：

```powershell
python -m pip install -r visual_sort_demo\requirements.txt
python visual_sort_demo\main.py
```

Mock 模式只依赖 PySide6，不需要摄像头、串口或 STM32。

## 真实适配器

`integration/vision_adapter.py` 和 `integration/serial_adapter.py` 会按相对路径加载 `visual_pick/pc` 中的旧 GUI 兼容模块。该路径用于动画集成；实机演示和最终顶点分类仍以 `visual_pick/pc/visual_sort.py` 为准。
