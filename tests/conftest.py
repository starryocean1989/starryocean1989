# -*- coding: utf-8 -*-
"""Pytest配置文件."""

import sys
import os

# 将项目根目录添加到Python路径中
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import logging
from pathlib import Path

import pytest

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """设置测试环境."""
    logger.info("=" * 80)
    logger.info("开始UI交互功能回路测试")
    logger.info("测试范围：43个功能链路，6个功能界面")
    logger.info("=" * 80)

    # 确保测试报告目录存在
    reports_dir = project_root / "tests" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    yield

    logger.info("=" * 80)
    logger.info("测试执行完成")
    logger.info("=" * 80)


@pytest.fixture(scope="session")
def project_root_path():
    """返回项目根目录路径."""
    return project_root


@pytest.fixture(scope="function")
def test_data_dir(tmp_path):
    """提供临时测试数据目录."""
    test_dir = tmp_path / "test_data"
    test_dir.mkdir(exist_ok=True)
    return test_dir


def pytest_configure(config):
    """pytest配置钩子."""
    # 添加自定义标记
    config.addinivalue_line("markers", "ui: UI集成测试标记")
    config.addinivalue_line("markers", "loop: 功能回路测试标记")


def pytest_collection_modifyitems(config, items):
    """修改测试收集项."""
    # 为所有测试添加loop标记
    for item in items:
        if "test_ui_integration" in str(item.fspath):
            item.add_marker(pytest.mark.loop)
            item.add_marker(pytest.mark.ui)


def pytest_report_header(config):
    """自定义测试报告头."""
    return [
        "UI交互功能回路测试套件",
        f"项目路径: {project_root}",
        "测试目标: 验证43个功能链路的完整业务回路",
    ]


# 导入所有fixtures，使其在所有测试中可用
pytest_plugins = [
    "tests.test_ui_integration.fixtures.app_fixture",
    "tests.test_ui_integration.fixtures.ui_fixture",
    "tests.test_ui_integration.fixtures.mock_backend",
]
