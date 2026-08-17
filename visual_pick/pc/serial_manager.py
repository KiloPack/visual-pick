# -*- coding: utf-8 -*-
"""
serial_manager.py —— 串口通信模块（基于 pyserial）
====================================================
职责：封装与 STM32 的串口收发，供 GUI 调用。串口逻辑集中在这里，
     界面代码不直接碰 pyserial，便于维护与单独测试。

对外接口：
    list_ports()                  -> list[str]   扫描可用串口，返回设备名列表
    SerialManager.connect(port, baudrate)        打开串口（失败抛 SerialError）
    SerialManager.disconnect()                   关闭串口
    SerialManager.send_data(text)                发送字符串指令
    SerialManager.read_data()     -> str         读取一行返回数据
    SerialManager.is_connected() -> bool         是否已连接

    SerialReader(QThread)         —— 供 GUI 后台持续读取，通过 data_received 信号回调

协议约定（与固件 / serial_test.py 一致）：
    115200 8N1，无流控；
    指令：N=螺母 / W=垫片 / X=未知；
    固件应答以换行结尾：NUT / WASHER / UNKNOWN / BUSY 等。
"""

from __future__ import annotations

try:
    import serial
    from serial.tools import list_ports as _list_ports
except ImportError as e:  # 缺少 pyserial 时给出明确提示
    raise ImportError(
        "缺少 pyserial，请先运行：python -m pip install -r pc/requirements.txt"
    ) from e

from PySide6.QtCore import QThread, Signal

# 默认参数
DEFAULT_BAUD = 115200
DEFAULT_READ_TIMEOUT = 0.1   # 秒；后台轮询时用短超时
DEFAULT_WRITE_TIMEOUT = 1.0  # 秒


class SerialError(Exception):
    """串口相关操作的统一异常，GUI 捕获这一个类型即可。"""


def list_ports() -> list[str]:
    """扫描可用串口，返回设备名列表，例如 ['COM7', 'COM3']。"""
    return [p.device for p in _list_ports.comports()]


class SerialManager:
    """串口管理器：负责连接、断开、收发数据。"""

    def __init__(self, read_timeout: float = DEFAULT_READ_TIMEOUT,
                 write_timeout: float = DEFAULT_WRITE_TIMEOUT) -> None:
        self._serial = None
        self._port = None
        self._baudrate = None
        self.read_timeout = read_timeout
        self.write_timeout = write_timeout

    # ------------------------------------------------------------------
    # 连接 / 断开
    # ------------------------------------------------------------------
    def connect(self, port: str, baudrate: int = DEFAULT_BAUD) -> None:
        """
        打开串口。串口不存在 / 被占用 / 无权限时抛 SerialError。
        若已连接，会先断开旧连接再重连，避免重复打开。
        """
        if not port:
            raise SerialError("串口名为空")

        if self.is_connected():
            self.disconnect()

        try:
            self._serial = serial.Serial(
                port=port,
                baudrate=baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=self.read_timeout,
                write_timeout=self.write_timeout,
            )
        except serial.SerialException as e:
            self._serial = None
            raise SerialError(f"无法打开串口 {port}：{e}") from e
        except (PermissionError, OSError) as e:
            self._serial = None
            raise SerialError(f"串口 {port} 被占用或无权限：{e}") from e

        self._port = port
        self._baudrate = baudrate
        # 清空输入缓冲区，避免读到连接前的残留数据
        self._serial.reset_input_buffer()

    def disconnect(self) -> None:
        """关闭串口并清理状态。重复调用无副作用。"""
        if self._serial is not None:
            try:
                self._serial.close()
            finally:
                self._serial = None
                self._port = None
                self._baudrate = None

    def is_connected(self) -> bool:
        """是否已连接。"""
        return self._serial is not None and self._serial.is_open

    @property
    def port(self):
        """当前连接的串口名（未连接时为 None）。"""
        return self._port

    @property
    def baudrate(self):
        """当前连接的波特率（未连接时为 None）。"""
        return self._baudrate

    # ------------------------------------------------------------------
    # 收发
    # ------------------------------------------------------------------
    def send_data(self, text: str) -> None:
        """
        发送字符串指令（不自动加换行）。发送失败抛 SerialError。
        指令应为 ASCII，例如 "N" / "W" / "X"。
        """
        if not self.is_connected():
            raise SerialError("串口未连接，无法发送")
        try:
            self._serial.write(text.encode("ascii"))
            self._serial.flush()
        except UnicodeEncodeError as e:
            raise SerialError("指令只能包含 ASCII 字符") from e
        except serial.SerialTimeoutException as e:
            raise SerialError("发送超时") from e
        except serial.SerialException as e:
            raise SerialError(f"发送失败：{e}") from e

    def read_data(self, timeout: float | None = None) -> str:
        """
        读取一行返回数据（固件应答以换行结尾）。
        超时未收到完整行时返回空字符串 ""。
        参数 timeout 只在本次调用内生效，不会影响后续读取。
        """
        if not self.is_connected():
            raise SerialError("串口未连接，无法读取")

        old_timeout = self._serial.timeout
        if timeout is not None:
            self._serial.timeout = timeout
        try:
            line = self._serial.readline()
            return line.decode("ascii", errors="replace").strip()
        except serial.SerialException as e:
            raise SerialError(f"读取失败：{e}") from e
        finally:
            self._serial.timeout = old_timeout  # 恢复原超时，避免影响后台轮询


class SerialReader(QThread):
    """
    后台串口读取线程（供 GUI 使用）：
    持续调用 read_data()，一旦收到数据就通过 data_received 信号发出去，
    避免在 GUI 主线程里阻塞读串口。

    用法：
        reader = SerialReader(manager)
        reader.data_received.connect(on_data)   # on_data(text)
        reader.start()
        # 退出时：reader.stop(); reader.wait()
    """

    data_received = Signal(str)   # 收到一行数据
    error = Signal(str)           # 读取出错信息

    def __init__(self, manager: SerialManager, poll_ms: int = 20, parent=None) -> None:
        super().__init__(parent)
        self._manager = manager
        self._poll_ms = poll_ms
        self._running = False

    def stop(self) -> None:
        """请求停止（线程在下一轮检查后退出）。"""
        self._running = False

    def run(self) -> None:
        self._running = True
        while self._running:
            if not self._manager.is_connected():
                self.msleep(self._poll_ms)
                continue
            try:
                data = self._manager.read_data()
                if data:
                    self.data_received.emit(data)
            except SerialError as e:
                self.error.emit(str(e))
            self.msleep(self._poll_ms)
