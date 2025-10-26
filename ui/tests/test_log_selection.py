# -*- coding: utf-8 -*-
"""
最小化测试：验证 LogTableModel 的三态表头与单行选择切换。

运行方式：
    python ui/tests/test_log_selection.py
"""

import sys
import os
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

# 确保可以导入顶层 ui 包
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from ui.modules.log_table_model import LogTableModel
from PySide6.QtGui import QBrush, QColor


def assert_equal(actual, expected, msg):
    if actual != expected:
        raise AssertionError(f"{msg}: expected={expected!r}, actual={actual!r}")


def main():
    # 保证Qt环境初始化，不持有变量避免lint告警
    QApplication.instance() or QApplication(sys.argv)

    model = LogTableModel()
    data = [
        {
            "timestamp": "2025-10-24T10:00:00",
            "level": "INFO",
            "module": "m1",
            "function": "f",
            "line": 1,
            "message": "a",
        },
        {
            "timestamp": "2025-10-24T10:01:00",
            "level": "ERROR",
            "module": "m2",
            "function": "g",
            "line": 2,
            "message": "b",
        },
        {
            "timestamp": "2025-10-24T10:02:00",
            "level": "DEBUG",
            "module": "m3",
            "function": "h",
            "line": 3,
            "message": "c",
        },
    ]

    model.update_data(data)

    # 初始：全未选
    header0 = model.headerData(0, Qt.Orientation.Horizontal, role=Qt.ItemDataRole.DisplayRole)
    assert_equal(header0, "☐", "初始表头应为全未选")

    # 单行选中 -> 部分
    idx0 = model.index(0, 0)
    ok = model.setData(idx0, Qt.CheckState.Checked, Qt.ItemDataRole.CheckStateRole)
    assert_equal(ok, True, "设置第一行选中应返回True")
    header1 = model.headerData(0, Qt.Orientation.Horizontal, role=Qt.ItemDataRole.DisplayRole)
    assert_equal(header1, "◩", "单行选中后表头应为部分")

    # 全选 -> ☑
    model.select_all()
    header2 = model.headerData(0, Qt.Orientation.Horizontal, role=Qt.ItemDataRole.DisplayRole)
    assert_equal(header2, "☑", "全选后表头应为☑")

    # 清除 -> ☐
    model.clear_selection()
    header3 = model.headerData(0, Qt.Orientation.Horizontal, role=Qt.ItemDataRole.DisplayRole)
    assert_equal(header3, "☐", "清除选择后表头应为☐")

    # 断言：第0列未选中时背景不是纯白（避免白底）
    bg0 = model.data(model.index(0, 0), Qt.ItemDataRole.BackgroundRole)
    assert isinstance(bg0, QBrush), "第0列未选中单元格应返回背景画刷"
    color0: QColor = bg0.color()
    assert not (color0.red() == 255 and color0.green() == 255 and color0.blue() == 255), "未选中背景不应为纯白"

    print("OK: LogTableModel selection tri-state and single toggle verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
