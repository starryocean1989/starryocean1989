# -*- coding: utf-8 -*-
"""
数据标准化读取工具

提供统一的接口读取各种格式的本地数据文件并标准化保存。
采用模块化设计，每种数据类型一个独立的读取器。

当前支持的数据类型：
- 通达信二进制数据（日线、5分钟线、1分钟线）

扩展方式：
每增加一种数据类型，在data_readers目录下创建一个新的读取器文件，
继承BaseReader基类并实现read()、standardize()、save()方法。
"""

from .base_reader import BaseReader
from .tdx_reader import TdxBinaryReader

__all__ = [
    "BaseReader",
    "TdxBinaryReader",
]
