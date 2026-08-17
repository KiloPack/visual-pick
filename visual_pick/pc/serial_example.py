# -*- coding: utf-8 -*-
"""
serial_example.py —— SerialManager 最小可运行示例
====================================================
用法（在工程根目录执行）：
    python pc/serial_example.py              # 自动识别 CH340，或唯一的串口
    python pc/serial_example.py --port COM7  # 明确指定串口

会依次发送 N / W / X，并打印收到的应答。
"""

from __future__ import annotations

import argparse
import sys

from serial_manager import SerialManager, SerialError, list_ports

CH340_VID = 0x1A86
CH340_PID = 0x7523


def pick_port(explicit: str | None) -> str:
    """选一个串口：优先命令行指定，其次 CH340，再次唯一串口。"""
    from serial.tools import list_ports as lp

    infos = list(lp.comports())
    devices = [p.device for p in infos]

    if explicit:
        return explicit

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
        return ch340
    if len(devices) == 1:
        return devices[0]
    raise SystemExit("无法自动确定串口，请用 --port COMx 指定。")


def main() -> int:
    parser = argparse.ArgumentParser(description="SerialManager 最小示例")
    parser.add_argument("--port", help="串口名，例如 COM7")
    args = parser.parse_args()

    print("可用串口：", list_ports() or "无")

    manager = SerialManager()
    try:
        port = pick_port(args.port)
        manager.connect(port)
        print(f"已连接 {port} @ {manager.baudrate}")

        # 依次发送 N / W / X，各读一次应答
        for cmd in ("N", "W", "X"):
            manager.send_data(cmd)
            reply = manager.read_data(timeout=1.0)  # 最多等 1 秒
            print(f"发送 {cmd} -> 收到 {reply!r}")
    except SerialError as e:
        print(f"串口错误：{e}", file=sys.stderr)
        return 1
    finally:
        manager.disconnect()
        print("已断开")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
