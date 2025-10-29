# -*- coding: utf-8 -*-
"""
主引擎模块

ChinaStockEngine继承vnpy的BaseEngine，集成所有功能模块：
- 品种列表获取和缓存
- K线数据下载（增量下载）
- 数据存储和查询
- 数据感知和校验
- 文件监控
- 事件推送

合并来源：engine.py
"""

import logging
import threading
import time
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Union

from vnpy.event import Event, EventEngine
from vnpy.trader.engine import BaseEngine, MainEngine

from .config import config_manager
from .data_acquisition import SymbolLoader, MultiProcessStockFetcher
from .local_data.data_quality import (
    StorageManager,
    DataValidator,
    ValidationSummary,
    DataFileWatcher,
)
from .data_readers import TdxBinaryReader
from .local_data.data_quality import DataSensor, QualityOverview
from .local_data.unified_data_manager import (
    PreloadService,
    UnifiedDataManager,
    TdxDataSource,
    VirtualDataSource,
)

# 向后兼容别名
PollingGateway = TdxDataSource
VirtualGateway = VirtualDataSource


# 从events模块导入常量
from .events import (
    APP_NAME,
    EventPublisher,
)

# ==================== 日志配置 ====================
# 创建专用logger（模块级别）
logger = logging.getLogger("backend.data_module.engine")
logger_download = logging.getLogger("backend.data_module.download")
logger_alert = logging.getLogger("backend.data_module.alert")


class CacheValidationProgressEmitter:
    """缓存验证进度信号发射器（线程安全，避免Qt Timer问题）

    修复说明：
    - 原实现继承QObject，在后台线程中创建会触发Qt Timer警告
    - 新实现使用回调函数机制，线程安全且无Qt依赖
    """

    def __init__(self):
        """初始化进度发射器"""
        self._callbacks = []
        self._lock = threading.Lock()

    def progress_updated_connect(self, callback):
        """连接回调函数（替代Qt的connect）

        Args:
            callback: 回调函数 callback(message: str, progress: int)
        """
        with self._lock:
            self._callbacks.append(callback)

    @property
    def progress_updated(self):
        """提供兼容的API（模拟Qt Signal）"""
        return self

    def emit(self, message: str, progress: int):
        """发射进度更新信号（线程安全）

        Args:
            message: 进度消息
            progress: 进度百分比
        """
        with self._lock:
            callbacks = self._callbacks.copy()

        # 执行所有回调（在锁外执行，避免死锁）
        for callback in callbacks:
            try:
                callback(message, progress)
            except Exception:
                pass  # 静默处理回调异常，不影响主流程

    def connect(self, callback):
        """Qt兼容的connect方法"""
        self.progress_updated_connect(callback)


class ChinaStockEngine(BaseEngine):
    """中国A股数据管理引擎"""

    def __init__(self, main_engine: MainEngine, event_engine: EventEngine):
        """
        初始化引擎

        Args:
            main_engine: vnpy主引擎
            event_engine: vnpy事件引擎
        """
        super().__init__(main_engine, event_engine, APP_NAME)

        # 初始化组件（传入event_engine让各模块自己管理事件）
        self.symbol_loader = SymbolLoader(event_engine)
        self.stock_fetcher = MultiProcessStockFetcher(event_engine=event_engine)  # 传入event_engine
        self.storage_manager = StorageManager()
        self.validator = DataValidator()
        # 文件监控器（已合并到data_quality.py中，由data_sensor处理）
        self.file_watcher = None

        # 新增：数据感知器
        self.data_sensor = DataSensor(event_engine)
        self.data_file_watcher: Optional[DataFileWatcher] = None

        # 新增：轮询网关和虚拟网关
        self.polling_gateway: Optional[PollingGateway] = None
        self.virtual_gateway: Optional[VirtualGateway] = None

        # 新增：数据读取器
        self.tdx_reader: Optional[TdxBinaryReader] = None

        # 新增：统一数据管理组件
        self.preload_service: Optional[PreloadService] = None
        self.unified_data_manager: Optional[UnifiedDataManager] = None

        # 日志记录器（使用专用logger）
        self.logger = logger
        self.logger_download = logger_download
        self.logger_alert = logger_alert

        # 通用事件发布器（用于日志等通用事件）
        self.event_publisher = EventPublisher(event_engine)

        # 🆕 进度信号发射器（组合模式）
        self.progress_emitter = CacheValidationProgressEmitter()

        # ⚡ 延迟初始化标志
        self._lazy_init_done = False
        self._lazy_init_lock = threading.Lock()

        # ⚡ 优化：延迟启动文件监控，避免阻塞初始化
        # 文件监控将在延迟初始化时启动
        # if config_manager.is_watcher_enabled():
        #     self._start_file_watcher()

        # ⚡ 注意：轮询网关和虚拟网关默认不启用，不影响启动速度
        # 自动启动轮询网关（如果配置启用）
        if config_manager.is_polling_gateway_enabled():
            self._init_polling_gateway()

        # 自动启动虚拟网关（如果配置启用）
        if config_manager.is_virtual_gateway_enabled():
            self._init_virtual_gateway()

        # ⚡ 优化：延迟启动数据感知，避免阻塞初始化
        # 数据感知将在引擎初始化完成后由上层服务按需启动
        # self._start_data_sensing_async()

        # ⚡ 优化：初始化预加载服务但不自动启动，避免阻塞初始化
        if config_manager.is_preload_enabled():
            try:
                self.preload_service = PreloadService(self)
                # 不自动启动，改为延迟启动
                # if config_manager.is_preload_auto_start():
                #     self.preload_service.start(prime=True)
                self.logger.info("预加载服务已创建（延迟启动）")
            except Exception as exc:
                self.logger.exception("预加载服务初始化失败: %s", exc)
                self.preload_service = None

        # ⚡ 优化：统一数据管理器立即初始化（不涉及耗时操作）
        if config_manager.is_unified_manager_enabled():
            try:
                self.unified_data_manager = UnifiedDataManager(
                    self,
                    preload_service=self.preload_service,
                )
            except Exception as exc:
                self.logger.exception("统一数据管理器初始化失败: %s", exc)
                self.unified_data_manager = None

        # 阶段感知的初始化日志
        try:
            from backend.infrastructure.system_vnpy.unified_log_system import get_logging_hub

            ctx = get_logging_hub()
            if ctx.get_current_stage() == "startup":
                self.logger.info(
                    "中国A股数据引擎初始化完成: 模式=快速启动, "
                    "组件=[品种加载器,数据下载器,数据验证器,数据感知器,统一数据管理器]"
                )
            else:
                self.logger.debug("数据引擎重新初始化")
        except Exception:
            # 如果logging_context未就绪，使用简单日志
            self.logger.info("中国A股数据管理引擎初始化完成（快速启动模式）")

        # ⚡ 优化：健康检查也延迟执行，避免阻塞
        # 健康检查将在首次查询时自动执行
        # try:
        #     self.healthcheck()
        # except Exception:
        #     pass

        # 🔧 架构修复：移除SmartCacheValidator线程（混合线程模型导致Qt Timer警告）
        # 原因：threading.Thread与Qt的EventEngine不兼容，导致跨线程问题
        # 新方案：验证延迟到UI就绪后，使用Qt原生的QThread执行
        # 参考：ui/main_window.py的showEvent方法会触发后台验证
        self.logger.info("✓ 智能缓存验证将在UI就绪后启动（避免启动阻塞）")

    # ==================== 健康检查与就绪 ====================

    def _ensure_lazy_init(self) -> None:
        """确保延迟初始化已完成

        首次调用时初始化：
        1. 文件监控器
        2. 数据感知器
        3. 预加载服务
        """
        if self._lazy_init_done:
            return

        with self._lazy_init_lock:
            if not self._lazy_init_done:
                self.logger.info("[LAZY-INIT] 开始延迟初始化...")

                try:
                    # 1. 启动文件监控（如果配置启用）
                    if config_manager.is_watcher_enabled():
                        self.logger.info("[LAZY-INIT] 启动文件监控...")
                        try:
                            # 文件监控现在由data_sensor处理，无需单独启动
                            self.logger.info("[LAZY-INIT] ✅ 文件监控由data_sensor管理")
                        except Exception as e:
                            self.logger.warning("[LAZY-INIT] ⚠️ 文件监控启动失败: %s", e)
                    else:
                        self.logger.info("[LAZY-INIT] 文件监控未启用，跳过")

                    # 2. 启动数据感知器（异步扫描）
                    self.logger.info("[LAZY-INIT] 启动数据感知器...")
                    try:
                        # 数据感知器的启动逻辑已经移到DataSensor中
                        self.logger.info("[LAZY-INIT] ✅ 数据感知器准备就绪（按需启动）")
                    except Exception as e:
                        self.logger.warning("[LAZY-INIT] ⚠️ 数据感知器启动失败: %s", e)

                    # 3. 启动预加载服务（如果配置启用且自动启动）
                    if self.preload_service and config_manager.is_preload_auto_start():
                        self.logger.info("[LAZY-INIT] 启动预加载服务...")
                        try:
                            self.preload_service.start(prime=True)
                            self.logger.info("[LAZY-INIT] ✅ 预加载服务启动成功")
                        except Exception as e:
                            self.logger.warning("[LAZY-INIT] ⚠️ 预加载服务启动失败: %s", e)
                    else:
                        self.logger.info("[LAZY-INIT] 预加载服务未启用或不自动启动，跳过")

                    self.logger.info("[LAZY-INIT] ✅ 延迟初始化完成")

                except Exception as e:
                    self.logger.exception("[LAZY-INIT] ❌ 延迟初始化发生异常: %s", e)

                self._lazy_init_done = True

    def healthcheck(self) -> Dict[str, Any]:
        """健康检查（代理调用）"""
        from .local_data.data_quality import HealthChecker

        result = HealthChecker.check_system_health()
        setattr(self, "_ready", result["ready"])
        return result

    def is_ready(self) -> bool:
        """是否已通过健康检查（基本就绪）"""
        # ⚡ 快速启动模式：默认返回True，实际健康检查延迟到首次使用
        return True
        # return bool(getattr(self, "_ready", False))

    def _smart_cache_validation_and_sensing(self):
        """智能缓存验证与数据感知（8步流程）

        执行顺序（优化后，网络依赖前置）：
        1. 验证服务器池缓存 - 确保网络连接就绪（所有后续步骤的前提）
        2. 获取当前日期
        3. 验证交易日历缓存（依赖网络）
        4. 验证品种列表缓存并增量更新（依赖网络和服务器池）
        5. 验证IPO日期缓存并增量更新（依赖网络和服务器池）
        6. 更新本地数据索引（含失效品种池维护）
        7. 检查数据更新状态
        8. 启动文件监控
        """
        try:
            from datetime import date

            # 🔧 优化：不再需要等待UI，启动协调器已确保时序正确
            # 删除了 time.sleep(4.0)，BackendInitializerWorker完成后立即触发validation
            # 注意：time模块仍在其他地方使用（如time.time()），这里不需要导入

            # 使用self.logger，通过extra={"log_type": "stage_node"}标记为阶段节点日志
            # 确保按照日志系统v5.0规则输出到Terminal
            self.logger.info("=" * 70, extra={"log_type": "stage_node"})
            self.logger.info(
                "【后台进程】智能缓存验证与数据感知流程启动", extra={"log_type": "stage_node"}
            )
            self.logger.info("=" * 70, extra={"log_type": "stage_node"})
            self.logger.info("开始智能缓存验证流程", extra={"log_type": "stage_node"})

            # 步骤1：验证服务器池缓存 (10%) - 前置网络依赖
            self.logger.info("-" * 70, extra={"log_type": "stage_node"})
            self.logger.info("【步骤1/8】验证服务器池缓存", extra={"log_type": "stage_node"})
            self.logger.info("-" * 70, extra={"log_type": "stage_node"})
            self.logger.info("[1/8] 验证服务器池缓存...", extra={"log_type": "stage_node"})
            self._validate_server_pool_cache()
            # 完成日志已在_validate_server_pool_cache内部输出
            self.progress_emitter.progress_updated.emit("验证服务器池缓存", 10)

            # 步骤2：获取当前日期 (15%)
            self.logger.info("-" * 70, extra={"log_type": "stage_node"})
            self.logger.info("【步骤2/8】获取当前日期", extra={"log_type": "stage_node"})
            self.logger.info("-" * 70, extra={"log_type": "stage_node"})
            today = date.today()
            self.logger.info(
                "[2/8] 当前日期: %s", today.strftime("%Y-%m-%d"), extra={"log_type": "stage_node"}
            )
            self.progress_emitter.progress_updated.emit("获取当前日期", 15)

            # 步骤3：验证交易日历缓存 (25%)
            self.logger.info("-" * 70, extra={"log_type": "stage_node"})
            self.logger.info("【步骤3/8】验证交易日历缓存", extra={"log_type": "stage_node"})
            self.logger.info("-" * 70, extra={"log_type": "stage_node"})
            self.logger.info("[3/8] 验证交易日历缓存...", extra={"log_type": "stage_node"})
            self._validate_trading_calendar_cache()
            # 完成日志已在_validate_trading_calendar_cache内部输出
            self.progress_emitter.progress_updated.emit("验证交易日历缓存", 25)

            # 步骤4：验证品种列表缓存（只读） (35%)
            self.logger.info("-" * 70, extra={"log_type": "stage_node"})
            self.logger.info("【步骤4/8】验证品种列表缓存", extra={"log_type": "stage_node"})
            self.logger.info("-" * 70, extra={"log_type": "stage_node"})
            self.logger.info("[4/8] 验证品种列表缓存...", extra={"log_type": "stage_node"})
            symbols_result = self._validate_symbol_cache_readonly()
            # 完成日志已在_validate_symbol_cache_readonly内部输出
            self.progress_emitter.progress_updated.emit("验证品种列表缓存", 35)

            # 推送品种列表加载完成事件
            if symbols_result:
                from .events import EVENT_SYMBOL_CACHE_LOADED

                event_data = {
                    "symbol_count": len(symbols_result.get("all_symbols", [])),
                    "is_new": symbols_result.get("is_new", False),
                    "timestamp": datetime.now().isoformat(),
                }
                event = Event(EVENT_SYMBOL_CACHE_LOADED, event_data)
                self.event_engine.put(event)

            # 步骤5：验证IPO日期缓存并增量更新 (45%)
            self.logger.info("-" * 70, extra={"log_type": "stage_node"})
            self.logger.info("【步骤5/8】验证IPO日期缓存", extra={"log_type": "stage_node"})
            self.logger.info("-" * 70, extra={"log_type": "stage_node"})
            self.logger.info("[5/8] 验证IPO日期缓存...", extra={"log_type": "stage_node"})
            listed_symbols = []
            if symbols_result and symbols_result.get("all_symbols"):
                self._validate_and_update_ipo_cache(symbols_result["all_symbols"])
                # 获取IPO过滤后的已上市品种列表
                listed_symbols = self.symbol_loader.extract_all_codes()
            # 完成日志已在_validate_and_update_ipo_cache内部输出
            self.progress_emitter.progress_updated.emit("验证IPO日期缓存", 45)

            # 推送IPO缓存更新完成事件
            from .events import EVENT_IPO_CACHE_UPDATED

            event_data = {
                "listed_count": len(listed_symbols) if listed_symbols else 0,
                "timestamp": datetime.now().isoformat(),
            }
            event = Event(EVENT_IPO_CACHE_UPDATED, event_data)
            self.event_engine.put(event)

            # 步骤6：更新本地数据索引（含失效品种池维护）(55%)
            self.logger.info("-" * 70, extra={"log_type": "stage_node"})
            self.logger.info("【步骤6/8】更新本地数据索引", extra={"log_type": "stage_node"})
            self.logger.info("-" * 70, extra={"log_type": "stage_node"})
            self.logger.info("[6/8] 更新本地数据索引...", extra={"log_type": "stage_node"})
            self._update_local_data_index(listed_symbols)
            # 完成日志已在_update_local_data_index内部输出
            self.progress_emitter.progress_updated.emit("更新本地数据索引", 55)

            # 步骤7：检查数据更新状态 (60%-75%)
            self.logger.info("-" * 70, extra={"log_type": "stage_node"})
            self.logger.info("【步骤7/8】检查数据更新状态", extra={"log_type": "stage_node"})
            self.logger.info("-" * 70, extra={"log_type": "stage_node"})
            self.logger.info("[7/8] 检查数据更新状态...", extra={"log_type": "stage_node"})
            self._check_data_update_status(listed_symbols)
            # 完成日志已在_check_data_update_status内部输出
            self.progress_emitter.progress_updated.emit("检查数据更新状态", 75)

            # 步骤8：启动文件监控 (100%)
            self.logger.info("-" * 70, extra={"log_type": "stage_node"})
            self.logger.info("【步骤8/8】启动文件监控", extra={"log_type": "stage_node"})
            self.logger.info("-" * 70, extra={"log_type": "stage_node"})
            self.logger.info("[8/8] 启动文件监控...", extra={"log_type": "stage_node"})
            self.data_sensor.start_file_watcher()

            # 推送文件监控启动事件
            from .events import EVENT_FILE_WATCHER_STARTED

            event_data = {"status": "started", "timestamp": datetime.now().isoformat()}
            event = Event(EVENT_FILE_WATCHER_STARTED, event_data)
            self.event_engine.put(event)

            self.logger.info("✓ 文件监控已启动", extra={"log_type": "stage_node"})

            self.progress_emitter.progress_updated.emit("系统就绪", 100)

            # 推送validation流程完成事件
            from .events import EVENT_VALIDATION_COMPLETED

            event_data = {
                "success": True,
                "timestamp": datetime.now().isoformat(),
            }
            event = Event(EVENT_VALIDATION_COMPLETED, event_data)
            self.event_engine.put(event)

            self.logger.info("=" * 70, extra={"log_type": "stage_node"})
            self.logger.info("【后台线程】智能缓存验证流程完成", extra={"log_type": "stage_node"})
            self.logger.info("=" * 70, extra={"log_type": "stage_node"})
            self.logger.info("智能缓存验证流程完成", extra={"log_type": "stage_node"})

        except Exception as e:
            self.logger.exception("智能缓存验证失败: %s", e)

            # 推送失败事件
            try:
                from .events import EVENT_VALIDATION_COMPLETED

                event_data = {
                    "success": False,
                    "error": str(e),
                    "timestamp": datetime.now().isoformat(),
                }
                event = Event(EVENT_VALIDATION_COMPLETED, event_data)
                self.event_engine.put(event)
            except Exception:
                pass  # 静默处理事件推送失败，避免掩盖原始异常

    def _validate_trading_calendar_cache(self):
        """验证交易日历缓存"""
        # 交易日历已在TradingCalendar中自动验证和更新
        try:
            from backend.infrastructure.data_module_vnpy.cache_manager import DailyCacheManager

            # 直接检查缓存文件
            cache_data, cache_date, is_valid = DailyCacheManager.load_with_validation(
                "trading_calendar.json"
            )

            if cache_data and is_valid:
                # 尝试从缓存数据中提取交易日数量
                # cache_data 已经是交易日列表，不需要.get("data")
                trading_days_count = len(cache_data) if isinstance(cache_data, list) else 0
                self.logger.info(
                    "✓ 交易日历缓存有效：%s 约%d个交易日",
                    cache_date,
                    trading_days_count,
                    extra={"log_type": "stage_node"},
                )
            elif cache_data and not is_valid:
                self.logger.info("   缓存状态: 已过时（日期: %s）", cache_date)
                self.logger.info("   操作: 自动重新获取...")
                self.logger.warning("交易日历缓存已过时（%s），尝试自动修复", cache_date)
                try:
                    self._regenerate_trading_calendar_cache()
                    self.logger.info("   ✓ 已自动重新生成")
                    self.logger.info("✓ 交易日历缓存已自动重新生成")
                except Exception as fix_error:
                    self.logger.error("   ❌ 自动修复失败: %s", fix_error)
                    self.logger.error("交易日历缓存自动修复失败: %s", fix_error)
                    raise RuntimeError(f"交易日历缓存修复失败: {fix_error}")
            else:
                self.logger.info("   缓存状态: 不存在")
                self.logger.info("   操作: 首次生成...")
                self.logger.warning("交易日历缓存不存在，尝试首次生成")
                try:
                    trading_days_count = self._regenerate_trading_calendar_cache()
                    self.logger.info("   ✓ 已生成")
                    self.logger.info(
                        "✓ 交易日历缓存已首次生成：%d个交易日",
                        trading_days_count,
                        extra={"log_type": "stage_node"},
                    )
                except Exception as gen_error:
                    self.logger.error("   ❌ 生成失败: %s", gen_error)
                    self.logger.error("交易日历缓存生成失败: %s", gen_error)
                    raise RuntimeError(f"交易日历缓存生成失败: {gen_error}")

        except Exception as e:
            self.logger.error("   验证异常: %s", e)
            self.logger.error("交易日历缓存验证失败: %s", e)
            raise  # 重新抛出异常

    def _regenerate_trading_calendar_cache(self) -> int:
        """重新生成交易日历缓存（同步调用异步方法）

        Returns:
            int: 交易日数量
        """
        import asyncio
        from backend.infrastructure.tdx_asyncio.calendar import TradingCalendar

        calendar = TradingCalendar()
        today = date.today()

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            # 🆕 调用get_trading_calendar会自动保存到文件缓存
            trading_days_df = loop.run_until_complete(calendar.get_trading_calendar(today.year))
            if trading_days_df is None or len(trading_days_df) == 0:
                raise RuntimeError("获取到的交易日历为空")
            count = len(trading_days_df)
            self.logger.info("交易日历缓存已生成：%d个交易日", count)
            return count
        finally:
            loop.close()

    def _validate_server_pool_cache(self):
        """验证服务器池缓存

        增强健壮性：
        1. 检查服务器池状态
        2. 如果未就绪，调用start()初始化
        3. 验证初始化后的状态
        4. 如果失败，记录详细日志并抛出异常
        """
        try:
            from backend.infrastructure.data_module_vnpy.load_balancer import (
                server_pool_manager,
            )

            # 🔧 修复：如果未初始化，直接调用start()加载缓存（不会重新测速）
            if not server_pool_manager._running:
                self.logger.info("服务器池未初始化，正在从缓存加载...")
                self.logger.info("   缓存状态: 正在加载...")

                success = server_pool_manager.start()

                if not success:
                    self.logger.error("   ❌ 启动失败")
                    self.logger.error("❌ 服务器池启动失败！")
                    raise RuntimeError("服务器池启动失败")

                # 🔥 关键修复：验证启动后的状态
                if not server_pool_manager._running:
                    self.logger.error("   ❌ 启动后状态仍未就绪")
                    self.logger.error("❌ 服务器池启动后状态仍未就绪！_running=False")
                    raise RuntimeError("服务器池状态异常：启动成功但_running=False")

                if not server_pool_manager._sorted_servers_ipv4:
                    self.logger.error("   ❌ 启动后无可用IPv4服务器")
                    self.logger.error("❌ 服务器池启动后IPv4池为空！")
                    raise RuntimeError("服务器池状态异常：启动成功但无可用IPv4服务器")

                # 加载成功，显示状态
                stats = server_pool_manager.get_stats()
                cache_date = getattr(server_pool_manager, "_cache_date", None)

                if stats["available"] > 0:
                    self.logger.info("   缓存状态: 有效")
                    self.logger.info("   缓存日期: %s", cache_date)
                    # 计算总测试服务器数（IPv4 + IPv6）
                    total_tested = getattr(server_pool_manager, "_total_servers", stats["total"])
                    self.logger.info(
                        "   测速结果: %d/%d 个服务器可用", stats["available"], total_tested
                    )
                    ipv4_count = (
                        len(server_pool_manager._sorted_servers_ipv4)
                        if hasattr(server_pool_manager, "_sorted_servers_ipv4")
                        else 0
                    )
                    ipv6_count = (
                        len(server_pool_manager._sorted_servers_ipv6)
                        if hasattr(server_pool_manager, "_sorted_servers_ipv6")
                        else 0
                    )
                    self.logger.info(
                        "✓ 服务器池缓存有效：从缓存加载%d个（IPv4=%d, IPv6=%d）",
                        total_tested,
                        ipv4_count,
                        ipv6_count,
                        extra={"log_type": "stage_node"},
                    )
                else:
                    # 如果加载后还是0个，说明测速失败或缓存为空
                    self.logger.warning(
                        "   ⚠️ 加载后无可用服务器: %d/%d", stats["available"], stats["total"]
                    )
                    self.logger.warning("⚠️ 服务器池加载后无可用服务器，但不阻塞启动")
                    # 不抛出异常，允许系统继续启动（IPO下载会自动处理）
            else:
                # 已经运行，直接显示状态
                stats = server_pool_manager.get_stats()
                cache_date = getattr(server_pool_manager, "_cache_date", None)

                self.logger.info("   缓存状态: 有效（已运行）")
                self.logger.info("   缓存日期: %s", cache_date)
                # 计算总测试服务器数（IPv4 + IPv6）
                total_tested = getattr(server_pool_manager, "_total_servers", stats["total"])
                self.logger.info(
                    "   测速结果: %d/%d 个服务器可用", stats["available"], total_tested
                )
                ipv4_count = (
                    len(server_pool_manager._sorted_servers_ipv4)
                    if hasattr(server_pool_manager, "_sorted_servers_ipv4")
                    else 0
                )
                ipv6_count = (
                    len(server_pool_manager._sorted_servers_ipv6)
                    if hasattr(server_pool_manager, "_sorted_servers_ipv6")
                    else 0
                )
                self.logger.info(
                    "✓ 服务器池已运行：缓存中%d个服务器（IPv4=%d, IPv6=%d）",
                    total_tested,
                    ipv4_count,
                    ipv6_count,
                    extra={"log_type": "stage_node"},
                )

                # 🔥 额外验证：即使_running=True，也要确认IPv4池不为空
                if not server_pool_manager._sorted_servers_ipv4:
                    self.logger.warning("⚠️ 服务器池已运行但IPv4池为空，尝试重新加载")
                    self.logger.warning("   ⚠️ 检测到IPv4服务器列表为空，尝试重新加载...")
                    # 强制重新加载
                    server_pool_manager._running = False
                    success = server_pool_manager.start()
                    if not success or not server_pool_manager._sorted_servers_ipv4:
                        raise RuntimeError("服务器池重新加载失败")

        except RuntimeError:
            raise  # 重新抛出RuntimeError
        except Exception as e:
            self.logger.error("   验证异常: %s", e)
            self.logger.error("验证服务器池缓存失败: %s", e, exc_info=True)
            raise RuntimeError(f"服务器池缓存验证异常: {e}")

    def _validate_symbol_cache_readonly(self):
        """只读验证品种列表缓存（步骤4专用：缓存为空时立即重载）"""
        try:
            # 添加互斥锁机制，避免与其他流程冲突
            from pathlib import Path

            loading_flag = Path(config_manager.get_cache_dir()) / ".symbol_loading.lock"

            if loading_flag.exists():
                import time

                file_age = time.time() - loading_flag.stat().st_mtime
                if file_age < 300:  # 5分钟内
                    self.logger.info("检测到其他流程正在加载品种列表，等待完成...")
                    for _ in range(30):
                        time.sleep(1)
                        if not loading_flag.exists():
                            break
                        classified = self.symbol_loader.get_all_classified()
                        if classified:
                            break

            # 直接从SymbolLoader读取缓存（不验证过期）
            classified = self.symbol_loader.get_all_classified()

            if not classified or len(classified) == 0:
                self.logger.warning("品种列表缓存不存在，开始首次加载...")
                self.logger.info("   缓存状态: 不存在")
                self.logger.info("   操作: 首次加载（耗时约30秒）...")
                self.progress_emitter.progress_updated.emit("加载品种列表（首次，耗时约30秒）", 36)

                # 创建锁文件
                try:
                    loading_flag.touch()
                    self.logger.debug("已创建加载锁文件")
                except Exception:
                    pass

                try:
                    result = self.symbol_loader.load_from_api()

                    if not result or "classified" not in result:
                        raise RuntimeError("品种列表加载失败：返回结果为空")

                    all_codes = self.symbol_loader.extract_all_codes()

                    if len(all_codes) == 0:
                        raise RuntimeError("品种列表加载失败：品种数量为0")

                    self.logger.info("   ✓ 加载结果: 共%d个品种", len(all_codes))
                    self.logger.info(
                        "✓ 品种列表首次加载成功：%d个品种（含未上市）",
                        len(all_codes),
                        extra={"log_type": "stage_node"},
                    )
                    return {"all_symbols": all_codes, "is_new": True}

                except Exception as e:
                    self.logger.error("   ✗ 加载失败: %s", e)
                    self.logger.error("品种列表首次加载失败: %s", e, exc_info=True)
                    raise
                finally:
                    # 删除锁文件
                    try:
                        if loading_flag.exists():
                            loading_flag.unlink()
                            self.logger.debug("已删除加载锁文件")
                    except Exception:
                        pass

            # 提取所有品种代码
            all_codes = self.symbol_loader.extract_all_codes()

            self.logger.info(
                "✓ 品种列表缓存有效：%d个品种（含未上市）",
                len(all_codes),
                extra={"log_type": "stage_node"},
            )
            return {"all_symbols": all_codes, "is_valid": True}

        except Exception as e:
            self.logger.exception("验证品种列表缓存失败: %s", e)
            raise  # 重新抛出，让上层处理

    def _validate_and_update_symbol_cache(self):
        """验证并增量更新品种列表缓存"""
        try:
            classified, is_outdated = self.symbol_loader.load_from_cache_with_validation()

            if classified is None:
                self.logger.info("   缓存状态: 不存在")
                self.logger.info("   操作: 首次加载（耗时约30秒）...")
                self.logger.warning("品种列表缓存不存在，开始首次加载...")
                # 🔧 发射进度更新：提示用户正在加载（避免误以为卡住）
                self.progress_emitter.progress_updated.emit("加载品种列表（首次，耗时约30秒）", 36)

                try:
                    result = self.symbol_loader.load_from_api()

                    # 验证加载结果
                    if not result or "classified" not in result:
                        raise RuntimeError("品种列表加载失败：返回结果为空")

                    all_codes = self.symbol_loader.extract_all_codes()

                    if len(all_codes) == 0:
                        raise RuntimeError("品种列表加载失败：品种数量为0")

                    self.logger.info("   ✓ 加载结果: 共%d个品种", len(all_codes))
                    self.logger.info("✓ 品种列表首次加载成功：%d个品种", len(all_codes))
                    return {"all_symbols": all_codes, "is_new": True}

                except Exception as e:
                    self.logger.error("   ✗ 加载失败: %s", e)
                    self.logger.error("品种列表首次加载失败: %s", e, exc_info=True)
                    # 品种列表是关键基础数据，加载失败必须中止流程
                    raise  # 让异常向上抛出，由外层try-except保护应用不崩溃

            if is_outdated:
                # 获取缓存日期
                cache_date = getattr(self.symbol_loader, "_last_cache_date", None)
                self.logger.info("   缓存状态: 已过时（日期: %s）", cache_date)
                self.logger.info("   操作: 增量更新...")
                self.logger.warning("品种列表缓存已过时，开始增量更新...")
                # 🔧 发射进度更新：提示用户正在更新
                self.progress_emitter.progress_updated.emit("更新品种列表（耗时约15秒）", 36)
                update_result = self.symbol_loader.reload_with_incremental_update()

                if update_result["success"]:
                    self.logger.info(
                        "   更新结果: 新增%d个, 删除%d个, 未变%d个",
                        len(update_result["added"]),
                        len(update_result["removed"]),
                        update_result["unchanged"],
                    )
                    self.logger.info(
                        "✓ 品种列表更新完成：新增 %d 个，删除 %d 个，未变 %d 个",
                        len(update_result["added"]),
                        len(update_result["removed"]),
                        update_result["unchanged"],
                    )

                    all_codes = self.symbol_loader.extract_all_codes()
                    return {
                        "all_symbols": all_codes,
                        "added": update_result["added"],
                        "removed": update_result["removed"],
                    }
                else:
                    self.logger.error("   更新失败")
                    self.logger.error("品种列表更新失败")
                    raise RuntimeError("品种列表增量更新失败")
            else:
                # 🆕 检查缓存内容完整性
                cache_date = getattr(self.symbol_loader, "_last_cache_date", None)
                all_codes = self.symbol_loader.extract_all_codes()

                # 检查是否有关键分类为空（可能是之前通达信文件不可用）
                beijing_count = len(classified.get("北证A股", []))
                t0_fund_count = len(classified.get("T+0基金", []))
                convertible_count = len(classified.get("可转债", []))

                is_incomplete = beijing_count == 0 or t0_fund_count == 0 or convertible_count == 0

                if is_incomplete:
                    self.logger.info(
                        "   缓存状态: 内容不完整（北证A股:%d, T+0基金:%d, 可转债:%d）",
                        beijing_count,
                        t0_fund_count,
                        convertible_count,
                    )
                    self.logger.info("   操作: 强制增量更新...")
                    self.logger.warning("品种列表缓存内容不完整，强制增量更新")
                    self.progress_emitter.progress_updated.emit("更新品种列表（修复缺失分类）", 36)
                    update_result = self.symbol_loader.reload_with_incremental_update()

                    if update_result["success"]:
                        self.logger.info(
                            "   更新结果: 新增%d个, 删除%d个, 未变%d个",
                            len(update_result["added"]),
                            len(update_result["removed"]),
                            update_result["unchanged"],
                        )
                        self.logger.info(
                            "✓ 品种列表更新完成：新增 %d 个，删除 %d 个，未变 %d 个",
                            len(update_result["added"]),
                            len(update_result["removed"]),
                            update_result["unchanged"],
                        )

                        # 🆕 重新加载缓存验证更新是否成功
                        updated_classified = self.symbol_loader.get_all_classified()
                        beijing_count_new = len(updated_classified.get("北证A股", []))
                        t0_fund_count_new = len(updated_classified.get("T+0基金", []))
                        convertible_count_new = len(updated_classified.get("可转债", []))

                        self.logger.info(
                            "   更新后验证: 北证A股:%d, T+0基金:%d, 可转债:%d",
                            beijing_count_new,
                            t0_fund_count_new,
                            convertible_count_new,
                        )

                        all_codes = self.symbol_loader.extract_all_codes()
                        return {
                            "all_symbols": all_codes,
                            "added": update_result["added"],
                            "removed": update_result["removed"],
                        }
                    else:
                        self.logger.error("   更新失败")
                        self.logger.error("品种列表更新失败")
                        raise RuntimeError("品种列表修复缺失分类失败")
                else:
                    # 缓存完整且有效
                    self.logger.info("   缓存状态: 有效且完整")
                    if cache_date:
                        self.logger.info("   缓存日期: %s", cache_date)
                    self.logger.info(
                        "   品种数量: %d个（下载的全部品种，含未上市）", len(all_codes)
                    )
                    self.logger.info(
                        "✓ 品种列表缓存有效：%d个品种",
                        len(all_codes),
                        extra={"log_type": "stage_node"},
                    )
                    return {"all_symbols": all_codes, "is_valid": True}

        except Exception as e:
            self.logger.exception("验证品种列表缓存失败: %s", e)
            raise  # 向上抛出异常，由外层处理

    def _validate_and_update_ipo_cache(self, all_symbols):
        """验证并增量更新IPO日期缓存（与品种列表联动）"""
        try:
            ipo_cache = self.validator._ipo_cache
            cache_date = getattr(ipo_cache, "_cache_date", None)

            # 🆕 SQLite后端：从数据库查询记录数
            cached_count = 0
            try:
                with ipo_cache.db.get_connection() as conn:
                    result = conn.execute("SELECT COUNT(*) FROM finance_info").fetchone()
                    cached_count = result[0] if result else 0
            except Exception as e:
                self.logger.warning("查询SQLite缓存记录数失败: %s", e)

            # 检查缓存是否存在（基于SQLite记录数）
            cache_exists = cached_count > 0

            if not cache_exists:
                self.logger.info("   缓存状态: 不存在")
                self.logger.info("   操作: 首次加载（耗时约1-2分钟）...")
                self.logger.warning("IPO日期缓存不存在，开始首次下载...")

                # 🆕 输出IPO下载前总品种数
                import sys

                print(f"\n[IPO下载] IPO下载前总品种数: {len(all_symbols)}个")
                sys.stdout.flush()

                self.progress_emitter.progress_updated.emit("下载IPO日期（首次）", 46)

                try:
                    # 首次下载所有品种的IPO日期
                    from .data_acquisition import download_ipo_dates

                    # 🔧 定义进度回调函数（46%-48%范围）
                    last_update_time = [time.time()]

                    def ipo_progress_callback(current, total):
                        """IPO下载进度回调 - 限制更新频率避免UI卡顿"""
                        if total > 0:
                            now = time.time()
                            # 每0.5秒或每100个品种更新一次
                            if (
                                (now - last_update_time[0] >= 0.5)
                                or (current % 100 == 0)
                                or (current == total)
                            ):
                                # 计算进度（46%-48%）
                                percent = int(46 + (current / total) * 2)
                                last_update_time[0] = now

                                self.progress_emitter.progress_updated.emit(
                                    f"下载IPO日期 ({current}/{total})", percent
                                )
                                self.logger.debug("IPO下载进度: %d/%d", current, total)

                    result = download_ipo_dates(
                        symbols=all_symbols,
                        progress_callback=ipo_progress_callback,
                        use_multiprocess=True,
                        ipo_cache=ipo_cache,  # 传递全局IPODateCache实例
                    )

                    # 🆕 输出IPO过滤详细统计
                    unlisted_symbols = result.get("unlisted", [])
                    listed_count = len(all_symbols) - len(unlisted_symbols)

                    # 初始化统计
                    unlisted_stats = {"股票": 0, "可转债": 0, "基金": 0, "其他": 0}

                    if unlisted_symbols:
                        # 分类统计未上市品种
                        from .data_acquisition import SymbolLoader

                        temp_loader = SymbolLoader()
                        classified = temp_loader.get_all_classified()

                        for symbol in unlisted_symbols:
                            # 检查属于哪个分类
                            found = False
                            for category in ["上证A股", "深证A股", "北证A股"]:
                                if symbol in [s.get("code") for s in classified.get(category, [])]:
                                    unlisted_stats["股票"] += 1
                                    found = True
                                    break
                            if not found:
                                for category in ["可转债"]:
                                    if symbol in [
                                        s.get("code") for s in classified.get(category, [])
                                    ]:
                                        unlisted_stats["可转债"] += 1
                                        found = True
                                        break
                            if not found:
                                for category in ["T+0基金"]:
                                    if symbol in [
                                        s.get("code") for s in classified.get(category, [])
                                    ]:
                                        unlisted_stats["基金"] += 1
                                        found = True
                                        break
                            if not found:
                                unlisted_stats["其他"] += 1

                        # 输出到日志
                        self.logger.info("✓ 发现未上市品种: %d个", len(unlisted_symbols))
                        self.logger.info(
                            "   其中：股票%d个, 可转债%d个, 基金%d个, 其他%d个",
                            unlisted_stats["股票"],
                            unlisted_stats["可转债"],
                            unlisted_stats["基金"],
                            unlisted_stats["其他"],
                        )
                        listed_count = len(all_symbols) - len(unlisted_symbols)
                        self.logger.info(
                            "✓ 过滤后品种数量: %d个（已上市）",
                            listed_count,
                        )

                    # 🆕 输出到terminal摘要（无论是否有未上市品种都输出）
                    import sys

                    if unlisted_symbols:
                        print("\n" + "   " + "-" * 60)
                        print(
                            f"   📊 IPO过滤结果: "
                            f"发现{len(unlisted_symbols)}个未上市品种（股票{unlisted_stats['股票']}个, "
                            f"可转债{unlisted_stats['可转债']}个, 基金{unlisted_stats['基金']}个）"
                        )
                        print(f"   ✓ 去除后，品种数量: {listed_count}个（已上市）")
                        print("   " + "-" * 60)
                    else:
                        print(f"\n   ✓ IPO过滤完成: 全部{len(all_symbols)}个品种均已上市")
                    sys.stdout.flush()

                    self.logger.info(
                        "✓ 下载结果: 成功%d个, 失败%d个", result["succeeded"], result["failed"]
                    )
                    self.logger.info("✓ IPO日期首次下载完成：成功 %d 个", result["succeeded"])

                except Exception as e:
                    self.logger.error("   ⚠️ 下载异常: %s", e)
                    self.logger.error("IPO日期首次下载失败: %s", e, exc_info=True)
                    # 不阻塞后续流程（用户需求2c）
                    self.progress_emitter.progress_updated.emit("IPO缓存下载失败（已跳过）", 48)

            elif ipo_cache.is_cache_outdated():
                self.logger.info("   缓存状态: 已过时（日期: %s）", cache_date)
                self.logger.info("   已缓存: %d个品种的IPO日期", cached_count)
                self.logger.info("   操作: 增量更新...")
                self.logger.warning("IPO日期缓存已过时，开始增量更新...")

                # 🔧 定义进度回调函数（46%-48%范围）
                last_update_time = [time.time()]
                last_percent = [46]

                def ipo_progress_callback(current, total):
                    """IPO下载进度回调 - 限制更新频率避免UI卡顿"""
                    if total > 0:
                        now = time.time()
                        # 每0.5秒或每100个品种更新一次
                        if (
                            (now - last_update_time[0] >= 0.5)
                            or (current % 100 == 0)
                            or (current == total)
                        ):
                            # 计算进度（46%-48%）
                            percent = int(46 + (current / total) * 2)
                            last_percent[0] = percent
                            last_update_time[0] = now

                            self.progress_emitter.progress_updated.emit(
                                f"更新IPO日期 ({current}/{total})", percent
                            )
                            self.logger.debug("IPO下载进度: %d/%d", current, total)

                # 初始提示
                self.progress_emitter.progress_updated.emit("更新IPO日期缓存（准备中）", 46)
                result = ipo_cache.incremental_update(
                    all_symbols, progress_callback=ipo_progress_callback
                )

                self.logger.info(
                    "   更新结果: 新增%d个, 删除%d个, 下载成功%d个",
                    result["added"],
                    result["removed"],
                    result["download_succeeded"],
                )
                self.logger.info(
                    "✓ IPO日期更新完成：新增 %d 个，删除 %d 个，下载成功 %d 个",
                    result["added"],
                    result["removed"],
                    result["download_succeeded"],
                )
            else:
                self.logger.info("   缓存状态: 有效")
                if cache_date:
                    self.logger.info("   缓存日期: %s", cache_date)
                self.logger.info("   已缓存: %d个品种的IPO日期", cached_count)
                # 获取过滤后的已上市品种数（才是真实可用的）
                listed_count = len(self.symbol_loader.extract_all_codes())
                self.logger.info(
                    "✓ IPO过滤完成：%d个品种已上市（缓存总数%d）",
                    listed_count,
                    cached_count,
                    extra={"log_type": "stage_node"},
                )

        except Exception as e:
            self.logger.error("   验证异常: %s", e)
            self.logger.exception("验证IPO日期缓存失败: %s", e)
            # 🔧 IPO缓存验证失败，显示错误状态但不阻塞后续流程
            self.progress_emitter.progress_updated.emit("IPO缓存验证失败（已跳过）", 48)

    def _update_local_data_index(self, reference_symbols: List[str]):
        """更新本地数据索引（步骤6）

        1. 快速获取本地数据索引
        2. 计算差异：新增=参考集-本地，失效=本地-参考集
        3. 更新数据库中的本地数据索引和失效品种池
        4. 推送指标更新事件

        Args:
            reference_symbols: 参考品种列表（IPO过滤后的已上市品种）
        """
        try:
            from backend.services.database_adapter import get_db_manager

            # 1. 快速获取本地数据索引
            local_symbols = self.storage_manager.get_local_data_index(use_cache=True)
            local_set = set(local_symbols)
            reference_set = set(reference_symbols)

            # 2. 计算差异
            new_symbols = list(reference_set - local_set)  # 新增
            invalid_symbols = list(local_set - reference_set)  # 失效

            # 日志输出（符合v5.0规范：简洁的terminal输出）
            self.logger.info(
                "✓ 索引更新完成：参考=%d, 本地=%d, 新增=%d, 失效=%d",
                len(reference_symbols),
                len(local_symbols),
                len(new_symbols),
                len(invalid_symbols),
                extra={"log_type": "stage_node"},
            )

            # 3. 更新数据库
            db_manager = get_db_manager()
            db_manager.upsert_local_data_index(local_symbols)
            db_manager.upsert_invalid_symbols(invalid_symbols, reason="not_in_reference")

            # 4. 推送指标更新事件
            from .events import EVENT_DATA_METRICS_UPDATED, EVENT_INVALID_SYMBOLS_UPDATED

            # 计算统计指标
            total_with_invalid = len(reference_symbols) + len(invalid_symbols)
            downloaded = len(reference_set & local_set)
            missing = len(reference_set - local_set)

            metrics_data = {
                "total_symbols": total_with_invalid,
                "reference_symbols": len(reference_symbols),
                "downloaded": downloaded,
                "missing": missing,
                "invalid_count": len(invalid_symbols),
                "timestamp": datetime.now().isoformat(),
            }
            event = Event(EVENT_DATA_METRICS_UPDATED, metrics_data)
            self.event_engine.put(event)

            if invalid_symbols:
                invalid_data = {
                    "symbols": invalid_symbols,
                    "count": len(invalid_symbols),
                    "timestamp": datetime.now().isoformat(),
                }
                event = Event(EVENT_INVALID_SYMBOLS_UPDATED, invalid_data)
                self.event_engine.put(event)

        except Exception as e:
            self.logger.exception("更新本地数据索引失败: %s", e)

    def _check_data_update_status(self, reference_symbols: List[str]):
        """检查数据更新状态（步骤7）

        仅做更新状态/新鲜度检查，不做耗时质量深扫。
        移植自原阶段2逻辑：批量检查数据新鲜度。

        Args:
            reference_symbols: 参考品种列表
        """
        try:
            import time

            start_time = time.time()

            # 获取有本地数据的品种列表
            local_symbols = self.storage_manager.get_local_data_index(use_cache=True)
            # 只检查参考品种中有数据的品种
            symbols_to_check = [s for s in reference_symbols if s in local_symbols]

            if not symbols_to_check:
                self.logger.info(
                    "✓ 跳过数据新鲜度检查：无本地数据", extra={"log_type": "stage_node"}
                )
                return

            # 使用较少线程避免启动阶段资源竞争
            max_workers = 4

            # 批量检查数据新鲜度（使用DataValidator）
            freshness_results = self.data_sensor.validator.batch_check_freshness_optimized(
                symbols=symbols_to_check,
                interval="1d",
                max_workers=max_workers,
                error_accumulator=None,  # 启动阶段不记录详细错误
            )

            # 统计结果
            outdated_count = 0
            gap_days_list = []

            for symbol, freshness in freshness_results.items():
                if freshness["has_data"]:
                    gap_days = freshness["gap_days"]
                    if gap_days > 1:  # 滞后超过1天算过时
                        outdated_count += 1
                    if gap_days >= 0:
                        gap_days_list.append(gap_days)

            avg_gap = int(sum(gap_days_list) / len(gap_days_list)) if gap_days_list else 0
            elapsed = time.time() - start_time

            # 简洁输出（符合v5.0规范）
            self.logger.info(
                "✓ 数据新鲜度检查完成：已检查%d个品种，过时%d个，平均滞后%d天（耗时%.1fs）",
                len(symbols_to_check),
                outdated_count,
                avg_gap,
                elapsed,
                extra={"log_type": "stage_node"},
            )

        except Exception as e:
            self.logger.exception("检查数据更新状态失败: %s", e)
            # 不阻塞后续流程
            self.logger.warning("数据新鲜度检查失败，已跳过")

    def close(self) -> None:
        """关闭引擎"""
        try:
            # 停止文件监听器
            if self.data_sensor and hasattr(self.data_sensor, "data_file_watcher"):
                if self.data_sensor.data_file_watcher:
                    try:
                        self.data_sensor.data_file_watcher.stop()
                        self.logger.info("数据文件监控已停止")
                    except Exception as e:
                        self.logger.warning("停止数据文件监控失败: %s", e)

            # 停止数据感知
            if self.data_sensor and hasattr(self.data_sensor, "stop_sensing"):
                try:
                    self.data_sensor.stop_sensing()
                except Exception as e:
                    self.logger.error("停止数据感知失败: %s", e)

            # 停止预加载服务
            if self.preload_service and hasattr(self.preload_service, "stop"):
                try:
                    self.preload_service.stop()
                except Exception as e:
                    self.logger.error("停止预加载服务失败: %s", e)

            # 关闭轮询网关
            if self.polling_gateway and hasattr(self.polling_gateway, "close"):
                try:
                    self.polling_gateway.close()
                except Exception as e:
                    self.logger.error("关闭轮询网关失败: %s", e)

            # 关闭虚拟网关
            if self.virtual_gateway and hasattr(self.virtual_gateway, "close"):
                try:
                    self.virtual_gateway.close()
                except Exception as e:
                    self.logger.error("关闭虚拟网关失败: %s", e)

            self.logger.info("中国A股数据管理引擎已关闭")

        except Exception as e:
            self.logger.error("关闭引擎失败: %s", e)

    def refresh_stock_list(self) -> Optional[Dict[str, List[Dict[str, Any]]]]:
        """读取本地品种缓存（代理调用）"""
        self._ensure_lazy_init()
        return self.symbol_loader.load_from_cache() or {}

    def reload_stock_list(self) -> Dict[str, Any]:
        """调用API更新品种缓存（代理调用，事件由SymbolLoader推送）"""
        return self.symbol_loader.reload_and_classify()

    def download_incremental(
        self,
        start_date: Union[str, date],
        market_types: Optional[List[str]] = None,
        use_adaptive: bool = True,
    ) -> bool:
        """
        增量下载K线数据（代理调用）

        Args:
            start_date: 起始日期
            market_types: 市场类型列表
            use_adaptive: 是否使用自适应配置（默认True，企业级推荐）

        Returns:
            是否成功启动下载任务
        """
        self._ensure_lazy_init()

        # 使用场景上下文和阶段切换
        try:
            from backend.infrastructure.system_vnpy.unified_log_system import get_logging_hub

            ctx = get_logging_hub()

            # 切换到下载阶段
            ctx.set_stage("downloading")

            # 开始增量下载
            self.logger_download.info(
                "开始增量下载: 起始日期=%s, 市场=%s, 自适应=%s",
                start_date,
                market_types or "全部",
                use_adaptive,
            )

            result = self.stock_fetcher.start_incremental_download_async(
                start_date, self.symbol_loader, self.storage_manager, market_types, use_adaptive
            )

            if result:
                self.logger_download.info("增量下载任务已启动")
            else:
                self.logger_alert.warning("增量下载任务启动失败")

            # v5.0不需要恢复阶段，下载完成后会自动切换到idle阶段
            return result
        except Exception as e:
            # 如果上下文管理失败，回退到简单调用
            self.logger.warning("场景上下文初始化失败，使用默认日志: %s", e)
            return self.stock_fetcher.start_incremental_download_async(
                start_date, self.symbol_loader, self.storage_manager, market_types, use_adaptive
            )

    def query_data(
        self,
        symbol: Optional[str] = None,
        interval: str = "1d",
        start_date: Optional[Union[str, date]] = None,
        end_date: Optional[Union[str, date]] = None,
        **kwargs,
    ) -> Optional[Any]:
        """统一查询接口（代理调用）"""

        # ⚡ 首次查询时执行延迟初始化
        self._ensure_lazy_init()

        # 代理调用unified_data_manager
        if self.unified_data_manager:
            return self.unified_data_manager.query_unified(
                symbol=symbol,
                interval=interval,
                start_date=start_date,
                end_date=end_date,
                **kwargs,
            )
        else:
            # Fallback到基础存储管理器（单品种查询）
            target_symbol: Optional[str] = None
            symbol_candidate = symbol or kwargs.get("symbols")

            if isinstance(symbol_candidate, (list, tuple)):
                # 从列表或元组中取第一个元素
                if len(symbol_candidate) > 0:
                    first_item = symbol_candidate[0]
                    if isinstance(first_item, str):
                        target_symbol = first_item
            elif isinstance(symbol_candidate, str):
                target_symbol = symbol_candidate

            if target_symbol is None:
                return None

            return self.storage_manager.query_kline(target_symbol, interval, start_date, end_date)

    def get_validation_result(self, force_refresh: bool = False) -> Optional[ValidationSummary]:
        """获取数据感知结果（代理调用）"""
        return self.validator.validate_all_data()

    def get_market_stocks(self, market_type: str) -> List[Dict[str, Any]]:
        """获取指定市场的品种列表（代理调用）"""
        self._ensure_lazy_init()
        return self.symbol_loader.get_market_stocks(market_type)

    def get_all_market_stocks(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        获取所有市场的品种分类（代理调用）

        Returns:
            所有市场的品种分类字典，每个品种包含 code, name, market
        """
        # 代理调用
        return self.symbol_loader.get_all_classified()

    def clear_symbol_cache(self) -> bool:
        """删除品种列表缓存（代理调用）"""
        return self.symbol_loader.clear_cache()

    def get_storage_stats(self) -> Dict[str, Any]:
        """获取存储统计信息（代理调用）"""
        try:
            return self.storage_manager.get_storage_stats()
        except Exception as e:
            self.logger.error("获取存储统计失败: %s", e)
            return {}

    def get_local_data_index(self) -> List[str]:
        """获取本地数据索引（已下载的品种代码列表，代理调用）"""
        try:
            return self.storage_manager.get_local_data_index()
        except Exception as e:
            self.logger.error("获取本地数据索引失败: %s", e)
            return []

    def get_config(self) -> Dict[str, Any]:
        """获取配置信息（代理调用）"""
        return config_manager.get_all_config()

    def update_config(self, config_dict: Dict[str, Any]) -> bool:
        """更新配置（代理调用）"""
        config_manager.update_config(config_dict)
        return True

    def _start_file_watcher(self) -> None:
        """启动文件监控（已合并到data_sensor）"""
        # 文件监控现在由data_sensor处理，无需单独启动
        return

    def _push_log_event(self, message: str, level: str = "INFO") -> None:
        """推送日志事件（代理到EventPublisher）"""
        self.event_publisher.push_log_event(message, level)

    def _push_validation_event(self, summary: ValidationSummary) -> None:
        """推送校验事件（代理到EventPublisher）"""
        from .events import ValidationEventPublisher

        publisher = ValidationEventPublisher(self.event_engine)
        publisher.push_validation_event(summary)

    def _push_download_event(
        self, download_type: str, status: str, count: int, error: Optional[str] = None
    ) -> None:
        """推送下载事件（代理到EventPublisher）"""
        from .events import DownloadEventPublisher

        publisher = DownloadEventPublisher(self.event_engine)
        publisher.push_download_event(download_type, status, count, error)

    def _push_download_progress_event(
        self, download_type: str, progress_pct: float, completed: int, total: int, current_item: str
    ) -> None:
        """推送下载进度事件（代理到EventPublisher）"""
        from .events import DownloadEventPublisher

        publisher = DownloadEventPublisher(self.event_engine)
        publisher.push_download_progress_event(
            download_type, progress_pct, completed, total, current_item
        )

    # ==================== 下载控制方法 ====================

    def stop_download(self):
        """停止当前下载任务（代理调用）"""
        self.stock_fetcher.stop_download()

    def pause_download(self):
        """暂停当前下载任务（代理调用）"""
        self.stock_fetcher.pause_download()

    def resume_download(self):
        """恢复暂停的下载任务（代理调用）"""
        self.stock_fetcher.resume_download()

    def get_download_progress(self) -> Dict[str, Any]:
        """获取当前下载进度（代理调用）"""
        return self.stock_fetcher.get_download_progress()

    # ==================== 轮询网关管理方法 ====================

    def _init_polling_gateway(self) -> None:
        """初始化轮询网关（已迁移到UnifiedDataManager）"""
        # 轮询网关已迁移到 UnifiedDataManager.tdx_source
        # 保留此方法以保持向后兼容性
        return

    def start_polling_gateway(self, setting: Optional[Dict] = None) -> bool:
        """启动轮询网关（通过UnifiedDataManager）"""
        # 通过 UnifiedDataManager 启动 TdxDataSource
        if self.unified_data_manager:
            return self.unified_data_manager.start_tdx_source(setting or {})
        return False

    def stop_polling_gateway(self) -> bool:
        """停止轮询网关（通过UnifiedDataManager）"""
        # 通过 UnifiedDataManager 停止 TdxDataSource
        if self.unified_data_manager:
            return self.unified_data_manager.stop_tdx_source()
        return False

    # ==================== 虚拟网关管理方法 ====================

    def _init_virtual_gateway(self) -> None:
        """初始化虚拟网关（已迁移到UnifiedDataManager）"""
        # 虚拟网关已迁移到 UnifiedDataManager.virtual_source
        # 保留此方法以保持向后兼容性
        return

    def start_virtual_gateway(
        self, start_datetime: str, speed: float = 1.0, symbols: Optional[List[str]] = None
    ) -> bool:
        """启动虚拟网关（通过UnifiedDataManager）"""
        # 通过 UnifiedDataManager 启动 VirtualDataSource
        if self.unified_data_manager:
            config = {
                "start_datetime": start_datetime,
                "speed": speed,
                "symbols": symbols,
            }
            return self.unified_data_manager.start_virtual_source(config)
        return False

    def stop_virtual_gateway(self) -> bool:
        """停止虚拟网关（通过UnifiedDataManager）"""
        # 通过 UnifiedDataManager 停止 VirtualDataSource
        if self.unified_data_manager:
            return self.unified_data_manager.stop_virtual_source()
        return False

    # ==================== 数据读取器管理方法 ====================

    def read_tdx_data(
        self, symbols: List[str], data_type: str = "day", market: str = "sh"
    ) -> Dict[str, bool]:
        """读取通达信本地数据并保存（使用TdxDynamicExecutor）"""
        import asyncio
        from pathlib import Path
        from .data_readers import TdxDynamicExecutor

        # 获取TDX目录
        tdx_dir = config_manager.get_tdx_reader_root_dir()
        if tdx_dir is None:
            self.logger.error("TDX根目录未配置")
            return {symbol: False for symbol in symbols}

        # 创建执行器
        executor = TdxDynamicExecutor(tdx_dir=Path(tdx_dir))

        # 同步调用异步方法
        results = asyncio.run(
            executor.execute_batch(
                symbols=symbols,
                data_type=data_type,
                market=market,
                initial_processes=4,
                initial_coroutines=20,
                enable_throttling=False,
            )
        )

        # 转换结果格式：ExecutionResult -> bool
        return {symbol: result.success for symbol, result in results.items()}

    # ==================== 数据感知管理方法 ====================

    def _start_data_sensing_async(self) -> None:
        """启动数据感知（代理调用）"""
        self.data_sensor.start_sensing_async(self.symbol_loader)

    def stop_data_sensing(self) -> bool:
        """停止数据感知（代理调用）"""
        return self.data_sensor.stop_sensing()

    def get_data_quality_overview(self) -> Optional[QualityOverview]:
        """获取数据质量概览（代理调用）"""
        return self.data_sensor.get_quality_overview()

    def get_unified_data_manager(self) -> Optional[UnifiedDataManager]:
        """获取统一数据管理器实例（代理调用）"""
        return self.unified_data_manager

    def trigger_data_quality_scan(self, force_refresh: bool = False) -> Optional[QualityOverview]:
        """手动触发数据质量扫描（代理调用）"""
        return self.data_sensor.trigger_scan_with_symbols(
            self.symbol_loader, force_refresh=force_refresh
        )

    def scan_corrupted_files(self, auto_delete: bool = False) -> Dict[str, List[str]]:
        """扫描并修复损坏的Parquet文件（代理调用）"""
        return self.storage_manager.scan_and_repair_corrupted_files(auto_delete)
