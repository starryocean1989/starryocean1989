# -*- coding: utf-8 -*-
"""
缓存验证工作对象（Qt原生，线程安全）

此模块实现Qt原生的后台验证工作对象，用于在QThread中执行完整的缓存验证和数据感知流程。

架构说明：
- 使用QObject和QThread，完全兼容Qt的EventEngine
- 通过信号槽与UI线程通信，线程安全
- 在UI就绪后启动，不阻塞应用启动
- 直接调用 ChinaStockEngine._smart_cache_validation_and_sensing() 执行完整逻辑

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

            # 🔧 修复：调用完整的缓存验证逻辑（包含缓存生成）
            # 之前的简化版本只做检查不生成，导致缓存不存在时无法自动创建
            self.engine._smart_cache_validation_and_sensing()

            self.progress.emit("缓存验证完成", 100)
            self.logger.info("✅ 智能缓存验证流程完成")
            self.finished.emit(True)

        except Exception as e:
            error_msg = f"缓存验证失败: {e}"
            self.logger.error(error_msg, exc_info=True)
            self.error.emit(error_msg)
            self.finished.emit(False)


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
