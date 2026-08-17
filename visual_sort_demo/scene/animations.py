# -*- coding: utf-8 -*-
"""动画辅助：统一封装 QPropertyAnimation / QVariantAnimation 的缓动与组合。

所有函数都返回一个 QAbstractAnimation，由控制器统一 start / pause / resume，
从而保证暂停、继续、重置时动画与状态机同步。
"""

from PySide6.QtCore import (
    QPropertyAnimation,
    QVariantAnimation,
    QEasingCurve,
    QSequentialAnimationGroup,
    QPointF,
)


def move_to(item, target, duration_ms, easing=QEasingCurve.InOutCubic):
    """把图形项（QGraphicsObject）从当前位置平滑移动到 target（QPointF）。"""
    anim = QPropertyAnimation(item, b"pos")
    anim.setDuration(duration_ms)
    anim.setStartValue(item.pos())
    anim.setEndValue(target)
    anim.setEasingCurve(easing)
    return anim


def rotate_to(servo, target_angle, duration_ms, easing=QEasingCurve.InOutCubic):
    """把舵机摇臂从当前角转到目标角。"""
    anim = QPropertyAnimation(servo, b"angle")
    anim.setDuration(duration_ms)
    anim.setStartValue(servo.angle)
    anim.setEndValue(target_angle)
    anim.setEasingCurve(easing)
    return anim


def servo_sweep(servo, peak_angle, duration_ms, easing=QEasingCurve.InOutCubic):
    """舵机摇臂从 0 转到峰值再转回 0，返回顺序动画组。"""
    half = duration_ms // 2
    out = QPropertyAnimation(servo, b"angle")
    out.setDuration(half)
    out.setStartValue(0.0)
    out.setEndValue(float(peak_angle))
    out.setEasingCurve(easing)

    back = QPropertyAnimation(servo, b"angle")
    back.setDuration(half)
    back.setStartValue(float(peak_angle))
    back.setEndValue(0.0)
    back.setEasingCurve(easing)

    group = QSequentialAnimationGroup()
    group.addAnimation(out)
    group.addAnimation(back)
    return group


def scan_sweep(scan_line, y1, y2, duration_ms, easing=QEasingCurve.InOutSine):
    """扫描线（QGraphicsLineItem）从 y1 竖直扫到 y2，保持 x 不变。"""
    va = QVariantAnimation()
    va.setStartValue(float(y1))
    va.setEndValue(float(y2))
    va.setDuration(duration_ms)
    va.setEasingCurve(easing)
    va.valueChanged.connect(lambda v: scan_line.setY(float(v)))
    return va


def delayed(duration_ms, callback):
    """在 duration_ms 后自然结束的动画，结束时触发 callback。

    用动画承载"延迟"而不是 QTimer.singleShot，这样暂停 / 恢复 / 重置时
    延迟与状态机保持同步（stop() 不会误触发 finished）。
    """
    va = QVariantAnimation()
    va.setStartValue(0)
    va.setEndValue(1)
    va.setDuration(duration_ms)
    va.finished.connect(callback)
    return va
