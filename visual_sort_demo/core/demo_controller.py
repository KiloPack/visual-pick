# -*- coding: utf-8 -*-
"""演示控制器：驱动状态机、触发动画、向界面发射状态/统计/日志信号。

统一入口（供 UI 与未来真实系统调用）：
    controller.trigger_sort("NUT")     # 触发一次螺母分拣演示
    controller.trigger_sort("WASHER")  # 触发一次垫片分拣演示
    controller.trigger_sort("UNKNOWN") # 触发一次未知物分拣演示

真实系统接入方式：
    识别端：label = vision_adapter.detect(frame)["label"]
            controller.trigger_sort(label)
    串口端：controller 在 TRANSMITTING 阶段调用 serial_adapter.send_command(label)，
            真实模式下会真正向 STM32 发送 N/W/X。
"""

import random

from PySide6.QtCore import QObject, QTimer, Signal

from core.state_machine import State, STATE_DURATIONS, FLOW
from scene import animations as anim
from ui.styles import LABEL_CN
from integration.serial_adapter import SerialAdapter


class DemoController(QObject):
    """分拣演示状态机控制器。"""

    log = Signal(str)        # 日志文本（不带时间戳，由界面补）
    status = Signal(dict)    # 状态面板的局部更新 {key: value}
    stats = Signal(dict)     # 统计面板的完整更新 {total, NUT, WASHER, UNKNOWN}

    TICK_MS = 30

    def __init__(self, scene, serial_adapter=None, parent=None):
        super().__init__(parent)
        self.scene = scene
        self._serial = serial_adapter or SerialAdapter()

        self._state = State.IDLE
        self._label = None
        self._elapsed = 0
        self._paused = False
        self._auto_loop = False
        self._auto_timer = None
        self._stats = {"total": 0, "NUT": 0, "WASHER": 0, "UNKNOWN": 0}
        self._active_anims = []

        self._timer = QTimer(self)
        self._timer.setInterval(self.TICK_MS)
        self._timer.timeout.connect(self._on_tick)

    # ------------------------------------------------------------------
    # 公共接口
    # ------------------------------------------------------------------
    def start(self):
        """开始演示：空闲时触发一次（自动循环开则随机，否则默认 NUT）。"""
        if self._state != State.IDLE:
            return
        if self._auto_loop:
            self._trigger_next_auto()
        else:
            self.trigger_sort("NUT")

    def trigger_sort(self, label):
        """统一入口：触发一次指定物料的分拣演示。"""
        if label not in ("NUT", "WASHER", "UNKNOWN"):
            label = "UNKNOWN"
        if self._state != State.IDLE:
            self.log.emit("流程进行中，忽略新的触发")
            return
        self._label = label
        self._goto(State.FEEDING)

    def set_auto_loop(self, on):
        self._auto_loop = bool(on)
        if self._auto_loop:
            self.log.emit("自动循环：开（NUT 45% / WASHER 45% / UNKNOWN 10%）")
            if self._state == State.IDLE:
                self._trigger_next_auto()
        else:
            self._cancel_auto_timer()
            self.log.emit("自动循环：关")

    def is_running(self):
        return self._state != State.IDLE

    def is_paused(self):
        return self._paused

    def pause(self):
        """暂停当前演示。成功返回 True，空闲/已暂停时返回 False。"""
        if self._paused or not self.is_running():
            return False
        self._paused = True
        self._timer.stop()
        for a in self._active_anims:
            a.pause()
        self.log.emit("已暂停")
        return True

    def resume(self):
        """恢复演示。成功返回 True，未暂停时返回 False。"""
        if not self._paused:
            return False
        self._paused = False
        self._timer.start()
        for a in self._active_anims:
            a.resume()
        self.log.emit("继续")
        return True

    def reset(self):
        """完整重置：停止当前流程、复位场景、清零统计。"""
        self._timer.stop()
        self._cancel_anims()
        self._cancel_auto_timer()
        self._state = State.IDLE
        self._label = None
        self._elapsed = 0
        self._paused = False
        self._stats = {"total": 0, "NUT": 0, "WASHER": 0, "UNKNOWN": 0}
        self.scene.reset()
        self.stats.emit(self._stats)
        self._emit_idle_status()
        self.log.emit("已重置")

    # ------------------------------------------------------------------
    # 状态机驱动
    # ------------------------------------------------------------------
    def _goto(self, state):
        self._state = state
        self._elapsed = 0
        self._enter_state(state)
        self._timer.start()

    def _on_tick(self):
        if self._paused:
            return
        self._elapsed += self.TICK_MS
        duration = STATE_DURATIONS.get(self._state, 0)
        if duration and self._elapsed >= duration:
            self._advance()

    def _advance(self):
        try:
            idx = FLOW.index(self._state)
        except ValueError:
            idx = -1
        if idx < 0 or idx == len(FLOW) - 1:
            self._finish_cycle()
        else:
            self._goto(FLOW[idx + 1])

    def _finish_cycle(self):
        self._timer.stop()
        self._state = State.IDLE
        self._label = None
        self.scene.reset()
        self._emit_idle_status()
        if self._auto_loop:
            self._schedule_auto_next()

    # ------------------------------------------------------------------
    # 各状态的进入动作
    # ------------------------------------------------------------------
    def _enter_state(self, state):
        self._emit_status("process", state.value)
        handler = getattr(self, f"_enter_{state.name.lower()}", None)
        if handler:
            handler()

    # ---- 阶段三：送料 / 下滑 / 采集 ----
    def _enter_feeding(self):
        self.scene.material.set_material(self._label)
        self.scene.material.setPos(self.scene.path_points["wait"])
        self.scene.material.setVisible(True)

        self.scene.feeder_servo.set_active(True)
        self.scene.set_active_module("feeder")
        self._emit_status("current_object", self._label)
        self._emit_status("feeder", "OPENING")
        self.log.emit("释放单个物料")

        sweep = anim.servo_sweep(self.scene.feeder_servo, peak_angle=45.0, duration_ms=600)
        self._run_anim(sweep)

    def _enter_moving_to_camera(self):
        self.scene.feeder_servo.set_active(False)
        self._emit_status("feeder", "CLOSED")
        self.log.emit("物料下滑中")

        move = anim.move_to(
            self.scene.material,
            self.scene.path_points["camera"],
            duration_ms=STATE_DURATIONS[State.MOVING_TO_CAMERA],
        )
        self._run_anim(move)

    def _enter_capturing(self):
        self.scene.set_active_module("camera")
        self._emit_status("vision_result", "Capturing...")
        self.log.emit("摄像头采集")

        self.scene.scan_line.setVisible(True)
        sweep = anim.scan_sweep(
            self.scene.scan_line,
            self.scene.scan_y1,
            self.scene.scan_y2,
            duration_ms=STATE_DURATIONS[State.CAPTURING],
        )
        self._run_anim(sweep)

    # ---- 阶段四：识别 / 串口 / STM32 ----
    def _enter_analyzing(self):
        self.scene.scan_line.setVisible(False)
        self.scene.set_active_module("opencv")
        self.scene.opencv_module.set_status("Analyzing...")
        self._emit_status("vision_result", "Analyzing...")
        self.log.emit("OpenCV 分析中")

        # 图像帧从摄像头流向 OpenCV
        start, end = self.scene.packet_paths["frame"]
        self.scene.frame_packet.setVisible(True)
        self.scene.frame_packet.setPos(start)
        self._run_anim(anim.move_to(self.scene.frame_packet, end, 450))

        # 分析完成 -> 揭示结果
        self._run_anim(anim.delayed(500, self._reveal_result))

    def _reveal_result(self):
        self.scene.opencv_module.set_status(f"Result: {self._label}")
        self._emit_status("vision_result", self._label)
        self.log.emit(f"识别结果: {self._label}")

    def _enter_transmitting(self):
        cmd = self._serial.send_command(self._label)
        self._emit_status("uart", f"TX → {cmd}")
        self.log.emit(f"UART TX: {cmd}  115200 baud")

        # 字符 N/W/X 沿 UART 线从 OpenCV 流向 STM32
        self.scene.frame_packet.setVisible(False)
        self.scene.uart_packet.text = cmd
        start, end = self.scene.packet_paths["uart"]
        self.scene.uart_packet.setVisible(True)
        self.scene.uart_packet.setPos(start)
        self._run_anim(
            anim.move_to(self.scene.uart_packet, end, STATE_DURATIONS[State.TRANSMITTING])
        )

    def _enter_stm32_processing(self):
        cmd = self._serial.command_for(self._label)
        self.scene.set_active_module("stm32")
        self.scene.stm32_module.set_status(f"RX: {cmd}  Processing...")
        self._emit_status("stm32", "PROCESSING")
        self.log.emit(f"STM32 RX: {cmd}")

        # 隐藏已到达的 UART 字符
        self.scene.uart_packet.setVisible(False)

        # 处理完成 -> 接受指令 -> PWM 流向分拣舵机
        self._run_anim(anim.delayed(300, lambda: self._stm32_accept(cmd)))

    def _stm32_accept(self, cmd):
        self.scene.stm32_module.set_status("Command Accepted")
        self._emit_status("stm32", "COMMAND ACCEPTED")
        self.log.emit("STM32 command accepted")

        start, end = self.scene.packet_paths["pwm"]
        self.scene.pwm_packet.setVisible(True)
        self.scene.pwm_packet.setPos(start)
        self._run_anim(anim.move_to(self.scene.pwm_packet, end, 300))

    # ---- 阶段五：分流 / 入箱 / 计数 ----
    def _enter_servo_sorting(self):
        self.scene.pwm_packet.setVisible(False)
        self.scene.set_active_module("sorting")
        direction = {"NUT": "LEFT", "WASHER": "RIGHT", "UNKNOWN": "CENTER"}[self._label]
        self._emit_status("sorting", direction)
        self.log.emit(f"分拣舵机转向 {LABEL_CN[self._label]}")

        # 挡板转向：NUT 左 / WASHER 右 / UNKNOWN 居中
        target = {"NUT": -40.0, "WASHER": 40.0, "UNKNOWN": 0.0}[self._label]
        self._run_anim(anim.rotate_to(self.scene.sorting_servo, target, 500))

        # 物料继续下落：摄像头 -> 分拣舵机
        self._run_anim(anim.move_to(
            self.scene.material,
            self.scene.path_points["diverter"],
            STATE_DURATIONS[State.SERVO_SORTING],
        ))

    def _enter_moving_to_bin(self):
        self.log.emit("物料滑入收集箱")
        self._run_anim(anim.move_to(
            self.scene.material,
            self.scene.path_points[self._bin_key()],
            STATE_DURATIONS[State.MOVING_TO_BIN],
        ))

    def _enter_complete(self):
        self._emit_status("process", "COMPLETE")
        self.scene.material.setVisible(False)
        self.scene.set_active_module(self._bin_key())
        self.log.emit(f"物料进入 {LABEL_CN[self._label]} 箱")
        # 短暂停顿后计数 +1
        self._run_anim(anim.delayed(300, self._finalize_count))

    def _bin_key(self):
        return {"NUT": "nut_bin", "WASHER": "washer_bin", "UNKNOWN": "unknown_bin"}[self._label]

    def _finalize_count(self):
        old = self._stats[self._label]
        new = old + 1
        self._stats[self._label] = new
        self._stats["total"] += 1
        self.stats.emit(self._stats)
        self.log.emit(f"{self._label} 计数: {old} → {new}")

    # ------------------------------------------------------------------
    # 辅助
    # ------------------------------------------------------------------
    def _run_anim(self, a):
        a.finished.connect(lambda: self._forget_anim(a))
        self._active_anims.append(a)
        a.start()

    def _forget_anim(self, a):
        if a in self._active_anims:
            self._active_anims.remove(a)

    def _cancel_anims(self):
        anims = list(self._active_anims)
        self._active_anims.clear()
        for a in anims:
            a.stop()

    def _trigger_next_auto(self):
        label = random.choices(["NUT", "WASHER", "UNKNOWN"], weights=[45, 45, 10], k=1)[0]
        self.trigger_sort(label)

    def _schedule_auto_next(self):
        self._cancel_auto_timer()
        self._auto_timer = QTimer(self)
        self._auto_timer.setSingleShot(True)
        self._auto_timer.timeout.connect(self._trigger_next_auto)
        self._auto_timer.start(700)

    def _cancel_auto_timer(self):
        if self._auto_timer is not None:
            self._auto_timer.stop()
            self._auto_timer = None

    def _emit_status(self, key, value):
        self.status.emit({key: value})

    def _emit_idle_status(self):
        self.status.emit({
            "current_object": "--",
            "vision_result": "--",
            "uart": "TX → --",
            "stm32": "STANDBY",
            "feeder": "CLOSED",
            "sorting": "CENTER",
            "process": "IDLE",
        })
