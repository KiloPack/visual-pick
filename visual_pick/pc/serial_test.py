"""Test the single sorter servo through USART1."""

from __future__ import annotations

import argparse
import sys
import time

try:
    import serial
    from serial.tools import list_ports
except ImportError:
    print(
        "缺少 pyserial。请先运行：python -m pip install -r pc/requirements.txt",
        file=sys.stderr,
    )
    raise SystemExit(1)


BAUD_RATE = 115200
READ_TIMEOUT_SECONDS = 1.0
WRITE_TIMEOUT_SECONDS = 1.0
POSITION_DELAY_SECONDS = 1.0
CH340_VID = 0x1A86
CH340_PID = 0x7523

EXPECTED_RESPONSES = {
    "C": "CENTER",
    "1": "SERVO:NUT",
    "2": "SERVO:CENTER",
    "3": "SERVO:WASHER",
}

POSITION_SEQUENCE = (
    ("2", "回到 CENTER 位置"),
    ("1", "进入 NUT 位置"),
    ("2", "回到 CENTER 位置"),
    ("3", "进入 WASHER 位置"),
    ("2", "最终回到 CENTER 位置"),
)


def select_port(explicit_port: str | None) -> tuple[str, list[str]]:
    """Select an explicit port or auto-detect the project's CH340 adapter."""
    port_infos = list(list_ports.comports())
    devices = [port.device for port in port_infos]

    if explicit_port is not None:
        return explicit_port, devices

    ch340_ports = [
        port.device
        for port in port_infos
        if (
            (port.vid == CH340_VID and port.pid == CH340_PID)
            or "CH340" in (port.description or "").upper()
        )
    ]

    if len(ch340_ports) == 1:
        return ch340_ports[0], devices

    if len(devices) == 1:
        return devices[0], devices

    raise RuntimeError(
        "无法唯一确定 USB-TTL 端口，请使用 --port COMx 明确指定。"
    )


def send_and_verify(
    connection: serial.Serial,
    command: str,
    description: str,
) -> bool:
    """Send one internal protocol byte and verify the controller response."""
    connection.reset_input_buffer()
    connection.write(command.encode("ascii"))
    connection.flush()

    response = connection.readline().decode(
        "ascii", errors="replace"
    ).strip()
    expected = EXPECTED_RESPONSES[command]

    if response == expected:
        print(f"通过：{description}，收到 {response}")
        return True

    if response:
        print(
            f"失败：{description}，预期 {expected}，"
            f"实际收到 {response!r}",
            file=sys.stderr,
        )
    else:
        print(
            f"超时：{description}，{READ_TIMEOUT_SECONDS:.1f}s 内无应答。",
            file=sys.stderr,
        )
    return False


def run_test(explicit_port: str | None, test_positions: bool) -> int:
    try:
        com_port, ports = select_port(explicit_port)
    except RuntimeError as error:
        print(f"串口选择失败：{error}", file=sys.stderr)
        return 1

    print("当前串口：", ", ".join(ports) if ports else "未检测到")

    if com_port not in ports:
        print(
            f"警告：当前列表中没有 {com_port}。请检查 USB-TTL 是否已连接。"
        )

    try:
        with serial.Serial(
            port=com_port,
            baudrate=BAUD_RATE,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=READ_TIMEOUT_SECONDS,
            write_timeout=WRITE_TIMEOUT_SECONDS,
        ) as connection:
            connection.reset_input_buffer()
            time.sleep(0.2)

            print(f"已打开 {connection.port}，参数：{BAUD_RATE} 8N1")
            if test_positions:
                print(
                    "三位置模式：PA0/TIM2_CH1 将依次执行 "
                    "CENTER → NUT → CENTER → WASHER → CENTER。"
                )
                for index, (command, description) in enumerate(
                    POSITION_SEQUENCE
                ):
                    if not send_and_verify(
                        connection, command, description
                    ):
                        return 1
                    if index + 1 < len(POSITION_SEQUENCE):
                        time.sleep(POSITION_DELAY_SECONDS)
                print("完成：单舵机已恢复到中心位 1500us。")
            else:
                print(
                    "安全模式：仅将 PA0/TIM2_CH1 单舵机设置为"
                    "中心位 1500us。"
                )
                if not send_and_verify(
                    connection, "C", "单舵机回到中心位"
                ):
                    return 1
                print("完成：未发送 NUT 或 WASHER 位置命令。")
            return 0
    except serial.SerialException as error:
        print(f"无法使用 {com_port}：{error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\n测试已停止。")
        return 130


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="单舵机串口测试")
    parser.add_argument(
        "--port",
        help="串口名称，例如 COM7；省略时自动识别 CH340",
    )
    parser.add_argument(
        "--positions",
        action="store_true",
        help=(
            "确认独立 5V、共地和机械余量后，执行 "
            "2→1→2→3→2 三位置测试"
        ),
    )
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    raise SystemExit(run_test(arguments.port, arguments.positions))
