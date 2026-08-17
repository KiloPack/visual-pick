# USART1 单舵机安全测试

当前固件只启动 TIM2_CH1 / PA0 上的一个 SG90。TIM2_CH2 / PA1 不启动，
最终三位置范围为 1100/1500/1900 us，实际机械位置仍需装机标定。

## 接线

### SG90

| SG90 | 连接位置 |
|---|---|
| 橙/黄信号线 | PA0 / TIM2_CH1 |
| 红色电源线 | 独立稳定 5 V 正极 |
| 棕/黑地线 | 独立 5 V GND，并与 STM32 GND 共地 |

- 当前源码和本地 Debug 构建使用 **PA0 / TIM2_CH1**；板卡仍需重新烧录该固件。
- 舵机不得由 STM32 GPIO、3.3 V 引脚或 USB-TTL 供电。
- 独立 5 V GND、STM32 GND、USB-TTL GND 必须连在一起。

### USB-TTL

| USB-TTL | STM32F103C8T6 |
|---|---|
| TX | PA10 / USART1_RX |
| RX | PA9 / USART1_TX |
| GND | GND |

- USB-TTL 使用 3.3 V 逻辑。
- TX 与 RX 交叉连接。
- USB-TTL 的 VCC 默认不接 STM32。

## 串口参数

```text
端口：自动识别 CH340（端口号可能随重插变化）
波特率：115200
数据位：8
校验：None
停止位：1
流控：None
```

## 准备 Python 环境

在工程根目录运行：

```powershell
python -m pip install -r pc\requirements.txt
```

## 测试步骤

1. 在 STM32CubeIDE 中构建并烧录当前固件。
2. 关闭 CubeIDE 的串口终端或其他正在占用 USB-TTL 串口的软件。
3. 在工程根目录运行：

```powershell
python pc\serial_test.py
```

脚本会自动识别 CH340。如需明确指定：

```powershell
python pc\serial_test.py --port COM9
```

4. 无需输入任何动作命令。脚本只执行安全回中：

```text
CH1 / PA0 → 1500 us（中心）
```

脚本不会自动发送 1100 或 1900 us。确认独立 5 V 供电、共地和机械余量后，
可以显式执行三位置测试：

```powershell
python pc\serial_test.py --port COM9 --positions
```

执行顺序为：

```text
2 → 1 → 2 → 3 → 2
CENTER → NUT → CENTER → WASHER → CENTER
```

USB-TTL 的 VCC 不接，舵机不能从 STM32 或 CH340 取电。

单舵机安装在检测区末端、Y 型岔道入口；识别 NUT/WASHER 后分别到
1100/1900 us 并持续保持，直到收到下一条位置命令。上电只发送
`SYSTEM READY`，PA0 PWM 保持关闭；第一次收到位置命令时才启动 PWM。
不存在启动回中、超时自动回中和 `DONE:*`。
视觉 UNKNOWN 不发送命令；未知串口字节也不改变当前舵机位置。

手动命令表：

| 命令 | 动作 | 回复 |
|---|---|---|
| `1` | NUT 位置，1100 us | `SERVO:NUT` |
| `2` | CENTER 位置，1500 us | `SERVO:CENTER` |
| `3` | WASHER 位置，1900 us | `SERVO:WASHER` |
| `4` | PA0 标定位置，1100 us | `CH1:1100us` |
| `5` | PA0 标定位置，1500 us | `CH1:1500us` |
| `6` | PA0 标定位置，1900 us | `CH1:1900us` |
| `N/n` | NUT 位置并持续保持 | `SERVO:NUT` |
| `W/w` | WASHER 位置并持续保持 | `SERVO:WASHER` |
| `X/x` | 人工调试回中 | `CENTER` |

串口终端附加的回车和换行会被忽略，不再产生额外 `UNKNOWN`。

如果自动识别失败，运行 `python -m serial.tools.list_ports` 查看端口，然后使用
`--port COMx` 指定，不需要再修改源码。

## 最终视觉分拣程序

最终入口是 `pc/visual_sort.py`。视觉核心保留已验证的 ROI、背景差分、
最大连通区域和原有单件锁定。分类按已验证的原始外轮廓顶点方案执行：
`RETR_EXTERNAL + CHAIN_APPROX_SIMPLE` 取得最大外轮廓，直接执行
`approxPolyDP(contour, 0.03 * perimeter, True)`，不经过凸包。
每帧 `5～7` 个顶点判为 `NUT`、`≥8` 判为 `WASHER`、其余为
`UNKNOWN`；等待8帧稳定后采样10帧，对10个单帧类别做严格多数票。
圆度、面积和椭圆误差只用于画面与日志诊断，不参与类别决定；画面会
同时绘制实际参与分类的近似多边形。
外围功能包括：

- `WAIT_OBJECT → CLASSIFYING → WAIT_EMPTY` 三态流程；
- Python启动并打开串口后不发送 `C`，保持板卡当前舵机位置；
- NUT/WASHER 每件只发送一次 `N/W`；
- UNKNOWN 不发送，保持舵机当前位置；零件仍在ROI时自动重新稳定采样；
- 连续 8 帧 EMPTY 后才允许识别下一件；
- 启动、识别完成后和EMPTY解锁时都不自动回中，保持到下一次分类命令；
- CH340 自动识别和 `--port COMx` 手动指定；
- `--vision-only` 只运行识别，不打开串口、不驱动舵机。

在工程根目录运行：

```powershell
python pc\visual_sort.py
```

如需指定串口：

```powershell
python pc\visual_sort.py --port COM3
```

调整识别时先使用纯视觉模式，避免误分类驱动舵机：

```powershell
python pc\visual_sort.py --vision-only
```

启动后保持 ROI 为空并按 `B` 保存白纸背景，按 `Q` 退出。
