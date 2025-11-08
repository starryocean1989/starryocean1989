# -*- coding: utf-8 -*-
"""pytest配置 - native扩展测试."""

from __future__ import annotations

import sys
from pathlib import Path

# 将项目根目录添加到sys.path以便导入backend模块
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# 将native目录添加到sys.path以便直接导入native模块
_NATIVE_DIR = Path(__file__).resolve().parent.parent
if str(_NATIVE_DIR) not in sys.path:
    sys.path.insert(0, str(_NATIVE_DIR))
