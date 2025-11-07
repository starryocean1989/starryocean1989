# -*- coding: utf-8 -*-
# pyright: reportUnsupportedDunderAll=false
"""tdx_asyncio 常量聚合模块

本文件用于兼容历史引用路径 ``backend.infrastructure.tdx_asyncio.constants``，
并补充发布流程文档中提到的常量导出需求。

发布/安装流程建议：

1. 在更新券商服务器池或协议常量后，优先修改 ``network/constants.py``。
2. 运行 `python -m backend.infrastructure.tdx_asyncio.scripts.test_hq_api_methods`
   或自定义校验脚本，确认新增常量可用。
3. 确认本文件仍能成功导入并导出需要的常量，再执行打包/发布。

该模块简单地重新导出 ``network.constants`` 中的全部名称，保证旧代码可直接使用。
"""

from .network.constants import *  # noqa: F401,F403

# 为静态检查工具提供显式导出列表（动态收集 network.constants 中的公共成员）
__all__ = [name for name in globals().keys() if not name.startswith("_")]


