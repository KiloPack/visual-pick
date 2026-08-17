# -*- coding: utf-8 -*-
"""
labels.py —— 共享的分类标签常量
============================================
识别结果分类标签，供 detector.py / sorter.py / ui_main_window.py 共用，
避免各处硬编码字符串造成不一致。

取值：
    EMPTY   —— 空（无物料）
    NUT     —— 螺母
    WASHER  —— 垫片 / 平垫
    UNKNOWN —— 未知
"""

LABEL_EMPTY = "EMPTY"
LABEL_NUT = "NUT"
LABEL_WASHER = "WASHER"
LABEL_UNKNOWN = "UNKNOWN"
