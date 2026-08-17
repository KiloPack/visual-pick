# STM32 视觉分拣系统

这是一个面向 M6 六角螺母与平垫的低成本视觉分拣项目。PC 端使用 Python/OpenCV 识别零件，经 USB-TTL 和 USART1 向 STM32F103C8T6 发送分类结果，再由一个 SG90 舵机完成挡料与左右分流。

## 系统链路

```text
摄像头 → Python/OpenCV → USB-TTL（USART1）
      → STM32F103C8T6 → SG90 → NUT / WASHER 料道
```

## 仓库结构

```text
visual_pick/        STM32CubeIDE 固件工程与 PC 端识别/串口程序
visual_sort_demo/   PySide6 原理动画，可使用 Mock 模式独立运行
```

`visual_sort_demo` 的真实硬件与视觉适配器会按相对路径加载 `visual_pick/pc`，因此两个目录应保持在同一个仓库根目录下。

## 硬件配置

| 项目 | 配置 |
|---|---|
| MCU | STM32F103C8T6，LQFP48 |
| 系统时钟 | HSE 8 MHz，PLL ×9，72 MHz |
| 串口 | USART1，PA9/PA10，115200 8N1 |
| 舵机 PWM | TIM2_CH1 / PA0，50 Hz |
| 舵机位置 | NUT 1100 µs，CENTER 1500 µs，WASHER 1900 µs |
| 调试接口 | SWD，PA13/PA14 |

## PC 端快速开始

以下命令在仓库根目录执行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r visual_pick\pc\requirements.txt
```

先使用纯视觉模式调试，不连接串口、不驱动舵机：

```powershell
.\.venv\Scripts\python.exe visual_pick\pc\visual_sort.py --vision-only
```

确认供电、共地、机械余量和分类结果后，再连接实际串口：

```powershell
.\.venv\Scripts\python.exe visual_pick\pc\visual_sort.py --port COM3
```

程序也会尝试自动识别 CH340；串口号会随电脑和 USB 端口变化。

## 动画演示

```powershell
.\.venv\Scripts\python.exe -m pip install -r visual_sort_demo\requirements.txt
.\.venv\Scripts\python.exe visual_sort_demo\main.py
```

Mock 模式只需要 PySide6。接入真实识别与串口时，还需要安装 `visual_pick/pc/requirements.txt` 中的依赖。

## STM32 固件

使用 STM32CubeIDE 导入 `visual_pick` 工程，或从 `visual_pick/visual_pick.ioc` 打开并生成工程。当前目标工具链是 STM32CubeIDE/GCC。

固件串口协议的主要命令：

| 命令 | 行为 | 回复 |
|---|---|---|
| `N` / `n` | 转到螺母侧并保持 | `SERVO:NUT` |
| `W` / `w` | 转到平垫侧并保持 | `SERVO:WASHER` |
| `C` / `X` / `x` | 人工回中 | `CENTER` |

## 安全说明

- SG90 使用独立、稳定的 5 V 电源，不得由 STM32 GPIO 或 3.3 V 引脚供电。
- 舵机电源 GND、STM32 GND 和 USB-TTL GND 必须共地。
- USB-TTL 优先使用 3.3 V 逻辑，TX/RX 交叉连接；VCC 默认不接 STM32。
- 首次动作前先使用纯视觉模式，并确认舵机机械余量；实际安装仍需标定三位置。

## 当前状态

固件已完成 STM32CubeIDE/GCC 构建、CMSIS-DAP 烧录校验和串口闭环测试；PC 端已完成螺母/平垫识别到 STM32 应答的联调。机械分流成功率、长期稳定性及 USB-TTL 高电平仍需按实际装机继续验证。
