# -*- coding: utf-8 -*-
"""
UI重构测试脚本

测试主窗口的新布局架构是否正常工作
"""

import sys
import logging
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from PySide6.QtWidgets import QApplication
from ui.main_window import MainWindow

# 设置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


def test_main_window():
    """测试主窗口"""
    logger = logging.getLogger("test_ui_refactor")

    app = QApplication(sys.argv)

    logger.info("创建主窗口...")
    window = MainWindow()

    logger.info("验证主窗口组件...")

    # 验证基本组件存在
    assert window.central_widget is not None, "中央部件未创建"
    assert window.tab_widget is not None, "导航Tab未创建"
    assert window.content_stack is not None, "内容区未创建"

    logger.info("✓ 基本组件创建成功")

    # 验证左侧导航Tab
    tab_count = window.tab_widget.count()
    logger.info(f"导航Tab数量: {tab_count}")
    assert tab_count == 6, f"导航Tab数量不正确，期望6个，实际{tab_count}个"

    # 验证Tab文本
    expected_tabs = [
        "系统管理",
        "数据中心",
        "行情看板",
        "策略中心",
        "交易网关",
        "组合投资",
    ]
    for i, expected_name in enumerate(expected_tabs):
        actual_name = window.tab_widget.tabText(i)
        assert (
            actual_name == expected_name
        ), f"Tab {i} 名称不匹配: 期望'{expected_name}'，实际'{actual_name}'"

    logger.info("✓ 导航Tab验证成功")

    # 验证内容区
    content_count = window.content_stack.count()
    logger.info(f"内容区widget数量: {content_count}")
    assert content_count == 6, f"内容区widget数量不正确，期望6个，实际{content_count}个"

    logger.info("✓ 内容区验证成功")

    # 验证功能界面实例
    expected_interfaces = [
        "system",
        "data",
        "market",
        "strategy",
        "trading",
        "portfolio",
    ]
    for interface_id in expected_interfaces:
        assert (
            interface_id in window.function_interfaces
        ), f"功能界面 {interface_id} 未创建"

    logger.info("✓ 功能界面实例验证成功")

    # 测试切换功能
    logger.info("测试界面切换...")
    for i in range(tab_count):
        window.tab_widget.setCurrentIndex(i)
        current_content = window.content_stack.currentIndex()
        assert (
            current_content == i
        ), f"切换到Tab {i} 时，内容区索引应为 {i}，实际为 {current_content}"

    logger.info("✓ 界面切换功能正常")

    # 显示窗口进行手动检查
    logger.info("显示主窗口，按Ctrl+C退出...")
    window.show()

    logger.info("=" * 60)
    logger.info("测试通过！主窗口重构成功！")
    logger.info("=" * 60)
    logger.info("新架构特点:")
    logger.info("  • 左侧垂直Tab用于功能界面切换")
    logger.info("  • 右侧QStackedWidget显示当前功能界面")
    logger.info(
        "  • 6个功能界面：系统管理、数据中心、行情看板、策略中心、交易网关、组合投资"
    )
    logger.info("  • ops_center已删除")
    logger.info("=" * 60)

    return app.exec()


if __name__ == "__main__":
    try:
        sys.exit(test_main_window())
    except AssertionError as e:
        logging.error(f"测试失败: {e}")
        sys.exit(1)
    except Exception as e:
        logging.error(f"测试异常: {e}", exc_info=True)
        sys.exit(1)
