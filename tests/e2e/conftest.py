# -*- coding: utf-8 -*-
"""E2E测试夹具配置.

提供：
- Qt应用环境
- 数据中心服务实例
- 临时缓存目录
- 测试数据清理
"""

import logging
import shutil
from pathlib import Path
from typing import Generator

import pytest
from PySide6.QtWidgets import QApplication

# 配置日志
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

logger = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def qapp() -> Generator[QApplication, None, None]:
    """创建Qt应用实例（会话级别）.

    Yields:
        QApplication实例
    """
    # 检查是否已有QApplication实例
    instance = QApplication.instance()
    if instance is None:
        app = QApplication([])
        logger.info("创建新的QApplication实例")
    elif isinstance(instance, QApplication):
        app = instance
        logger.info("使用已存在的QApplication实例")
    else:
        # instance is QCoreApplication but not QApplication, create a new QApplication
        app = QApplication([])
        logger.info("已有QCoreApplication实例，创建新的QApplication实例")

    yield app

    # 清理（会话结束时）
    if app is not None:
        logger.info("清理QApplication实例")


@pytest.fixture(scope="function")
def cache_dir() -> Generator[Path, None, None]:
    """提供测试用的缓存目录.

    每个测试函数都会获得一个干净的缓存目录。

    Yields:
        缓存目录路径
    """
    # 使用项目实际的缓存目录
    cache_path = Path("data/cache")
    cache_path.mkdir(parents=True, exist_ok=True)

    # 备份现有的stock_list.parquet（如果存在）
    stock_list_file = cache_path / "stock_list.parquet"
    backup_file = cache_path / "stock_list.parquet.backup"

    if stock_list_file.exists():
        shutil.copy2(stock_list_file, backup_file)
        logger.info("已备份现有缓存文件: %s", stock_list_file)

    yield cache_path

    # 测试后恢复备份（如果存在）
    if backup_file.exists():
        if stock_list_file.exists():
            stock_list_file.unlink()
        shutil.move(str(backup_file), str(stock_list_file))
        logger.info("已恢复缓存文件备份")


@pytest.fixture(scope="function")
def data_center_service():
    """提供数据中心服务实例.

    Returns:
        DataCenterService实例
    """
    from backend.core.base import get_service_manager, initialize_services

    service_manager = get_service_manager()

    # 如果服务尚未初始化，先初始化
    data_center_service = service_manager.get_service("data_center_service")
    if data_center_service is None:
        logger.info("服务尚未初始化，正在初始化所有服务...")
        init_result = initialize_services()
        if init_result.get("success"):
            logger.info("服务初始化成功")
            data_center_service = service_manager.get_service("data_center_service")
        else:
            logger.error("服务初始化失败: %s", init_result.get("user_friendly_report"))

    if data_center_service is None:
        pytest.skip("数据中心服务不可用")

    logger.info("数据中心服务已准备就绪")

    return data_center_service


@pytest.fixture(scope="function")
def data_center_widget(qapp):  # noqa: ARG001,F841
    """提供数据中心界面组件实例.

    Args:
        qapp: Qt应用实例 (确保Qt应用已初始化)

    Returns:
        DataCenter界面组件
    """
    # qapp参数虽然未使用，但必须存在以确保Qt应用已初始化
    from ui.components.data_center.main_view import DataCenter

    widget = DataCenter()
    logger.info("数据中心界面组件已创建")

    yield widget

    # 清理
    widget.close()
    widget.deleteLater()
    logger.info("数据中心界面组件已清理")


@pytest.fixture(scope="function")
def china_stock_engine():
    """提供ChinaStockEngine实例.

    Returns:
        ChinaStockEngine实例
    """
    from backend.core.base import get_china_stock_engine, initialize_services

    engine = get_china_stock_engine()

    # 如果引擎尚未初始化，先初始化服务
    if engine is None:
        logger.info("ChinaStockEngine尚未初始化，正在初始化服务...")
        init_result = initialize_services()
        if init_result.get("success"):
            logger.info("服务初始化成功")
            engine = get_china_stock_engine()
        else:
            logger.error("服务初始化失败: %s", init_result.get("user_friendly_report"))

    if engine is None:
        pytest.skip("ChinaStockEngine不可用")

    logger.info("ChinaStockEngine已准备就绪")

    return engine


# ==================== 网络请求E2E测试专用Fixture ====================

# 从fixtures模块导入
pytest_plugins = ["tests.e2e.fixtures.network_request_fixtures"]