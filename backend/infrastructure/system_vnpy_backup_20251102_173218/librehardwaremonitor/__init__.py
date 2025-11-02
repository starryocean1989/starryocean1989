# -*- coding: utf-8 -*-
"""LibreHardwareMonitor Python集成包.

通过pythonnet调用LibreHardwareMonitor的.NET库。
使用ExtendedLHMWrapper获取所有类型的硬件传感器数据。
"""

from .lhm_extended import ExtendedLHMWrapper, get_extended_lhm_wrapper

__all__ = [
    "ExtendedLHMWrapper",
    "get_extended_lhm_wrapper",
]
