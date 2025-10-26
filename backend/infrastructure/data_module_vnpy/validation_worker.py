# -*- coding: utf-8 -*-
"""
缓存验证工作对象（Qt原生，线程安全）

此模块实现Qt原生的后台验证工作对象，用于替代SmartCacheValidator线程。

架构说明：
- 使用QObject和QThread，完全兼容Qt的EventEngine
- 通过信号槽与UI线程通信，线程安全
- 在UI就绪后启动，不阻塞应用启动

使用方式：
    from PySide6.QtCore import QThread
    from backend.infrastructure.data_module_vnpy.validation_worker import CacheValidationWorker

    worker = CacheValidationWorker(china_stock_engine)
    thread = QThread()
    worker.moveToThread(thread)

    thread.started.connect(worker.run)
    worker.finished.connect(thread.quit)
    worker.progress.connect(on_progress)

    thread.start()
"""

import logging
from datetime import date

from PySide6.QtCore import QObject, Signal


class CacheValidationWorker(QObject):
    """缓存验证工作对象（Qt原生）

    在QThread中执行缓存验证和数据质量感知，完全兼容EventEngine。

    信号：
        progress(str, int): 进度更新 (消息, 百分比)
        finished(bool): 验证完成 (成功)
        error(str): 错误发生 (错误消息)
    """

    # Qt信号定义
    progress = Signal(str, int)  # (消息, 进度百分比)
    finished = Signal(bool)  # (成功)
    error = Signal(str)  # (错误消息)

    def __init__(self, china_stock_engine):
        """初始化验证工作对象

        Args:
            china_stock_engine: ChinaStockEngine实例
        """
        super().__init__()
        self.engine = china_stock_engine
        self.logger = logging.getLogger(__name__)

        # 快速访问组件
        self.symbol_loader = china_stock_engine.symbol_loader
        self.validator = china_stock_engine.validator
        self.data_sensor = china_stock_engine.data_sensor
        self.progress_emitter = china_stock_engine.progress_emitter

    def run(self):
        """执行完整的缓存验证和数据感知流程

        此方法在QThread中执行，可以安全使用EventEngine。
        """
        try:
            self.logger.info("=" * 70)
            self.logger.info("【后台进程】智能缓存验证与数据感知流程启动")
            self.logger.info("=" * 70)

            # 连接进度发射器到信号
            self.progress_emitter.progress_updated_connect(
                lambda msg, pct: self.progress.emit(msg, pct)
            )

            # 步骤1：获取当前日期
            self.progress.emit("获取当前日期", 5)
            current_date = date.today()
            self.logger.info("[1/6] 当前日期: %s", current_date)

            # 步骤2-5：验证各类缓存
            self._validate_trading_calendar()
            self._validate_server_pool()
            self._validate_symbol_list()
            self._validate_ipo_cache()

            # 步骤6：启动持续文件监控
            self._start_file_watcher()

            self.progress.emit("缓存验证完成", 100)
            self.logger.info("✅ 智能缓存验证流程完成")
            self.finished.emit(True)

        except Exception as e:
            error_msg = f"缓存验证失败: {e}"
            self.logger.error(error_msg, exc_info=True)
            self.error.emit(error_msg)
            self.finished.emit(False)

    def _validate_trading_calendar(self):
        """步骤2：验证交易日历缓存"""
        self.progress.emit("验证交易日历缓存", 10)
        self.logger.info("[2/6] 验证交易日历缓存...")

        try:
            from .cache_manager import DailyCacheManager

            cache_data, cache_date, is_valid = DailyCacheManager.load_with_validation(
                "trading_calendar.json"
            )

            if is_valid and cache_data:
                self.logger.info("✓ 交易日历缓存有效：%s", cache_date)
            else:
                self.logger.warning("⚠ 交易日历缓存过时或不存在")

        except Exception as e:
            self.logger.error("验证交易日历缓存失败: %s", e)

    def _validate_server_pool(self):
        """步骤3：验证服务器池缓存"""
        self.progress.emit("验证服务器池缓存", 20)
        self.logger.info("[3/6] 验证服务器池缓存...")

        try:
            from .load_balancer import server_pool_manager

            if server_pool_manager.is_cache_valid():
                stats = server_pool_manager.get_stats()
                self.logger.info(
                    "✓ 服务器池缓存有效：%d/%d 可用",
                    stats.get("available_count", 0),
                    stats.get("total_count", 0),
                )
            else:
                self.logger.warning("⚠ 服务器池缓存过期，需要重新测速")

        except Exception as e:
            self.logger.error("验证服务器池缓存失败: %s", e)

    def _validate_symbol_list(self):
        """步骤4：验证品种列表缓存"""
        self.progress.emit("验证品种列表缓存", 40)
        self.logger.info("[4/6] 验证品种列表缓存...")

        try:
            classified, is_outdated = self.symbol_loader.load_from_cache_with_validation()

            if classified and not is_outdated:
                all_codes = self.symbol_loader.extract_all_codes()
                self.logger.info("✓ 品种列表缓存有效：%d 个品种", len(all_codes))
            else:
                self.logger.warning("⚠ 品种列表缓存需要更新")
                # 增量更新
                result = self.symbol_loader.reload_with_incremental_update()
                if result["success"]:
                    self.logger.info(
                        "✓ 品种列表更新完成：新增 %d，删除 %d",
                        len(result.get("added", [])),
                        len(result.get("removed", [])),
                    )

        except Exception as e:
            self.logger.error("验证品种列表缓存失败: %s", e)

    def _validate_ipo_cache(self):
        """步骤5：验证IPO日期缓存状态（不执行下载）

        架构修复：验证流程只检查状态，不执行长时间的下载操作。
        IPO缓存更新延迟到数据质量扫描前执行，避免启动时大批量下载阻塞。
        """
        self.progress.emit("验证IPO日期缓存", 60)
        self.logger.info("[5/6] 验证IPO日期缓存...")

        try:
            ipo_cache = self.validator._ipo_cache  # noqa: SLF001
            cached_count = (
                len(ipo_cache._memory_cache) if hasattr(ipo_cache, "_memory_cache") else 0
            )

            if not ipo_cache.is_cache_outdated():
                self.logger.info("✓ IPO日期缓存有效：%d 个品种", cached_count)
            else:
                # 🎯 架构修复：只记录状态，不执行下载
                self.logger.warning("⚠ IPO日期缓存需要更新")
                self.logger.info("   → 缓存更新将在数据质量扫描前自动执行（延迟加载）")
                self.logger.info("   → 这样避免了启动时的大批量下载，提升启动速度")

        except Exception as e:
            self.logger.error("验证IPO日期缓存失败: %s", e)

    def _start_file_watcher(self):
        """步骤6：启动持续文件监控"""
        self.progress.emit("启动持续文件监控", 85)
        self.logger.info("[6/6] 启动持续文件监控...")

        try:
            # 启动文件监控（不依赖数据质量扫描）
            success = self.data_sensor.start_file_watcher()

            if success:
                self.logger.info("✅ 数据文件监控已启动")
            else:
                self.logger.warning("⚠️ 数据文件监控启动失败（watchdog可能不可用）")

        except Exception as e:
            self.logger.error("启动文件监控失败: %s", e)


def create_validation_worker_and_thread(china_stock_engine):
    """工厂函数：创建验证工作对象和线程

    便捷函数，用于快速创建和配置验证工作流程。

    Args:
        china_stock_engine: ChinaStockEngine实例

    Returns:
        (worker, thread): 工作对象和线程对象的元组

    使用示例:
        worker, thread = create_validation_worker_and_thread(engine)
        thread.started.connect(worker.run)
        worker.finished.connect(thread.quit)
        worker.progress.connect(on_progress_callback)
        thread.start()
    """
    from PySide6.QtCore import QThread

    worker = CacheValidationWorker(china_stock_engine)
    thread = QThread()
    worker.moveToThread(thread)

    return worker, thread
