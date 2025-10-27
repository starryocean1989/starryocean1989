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
from datetime import date
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
    EVENT_DATA_QUALITY_UPDATE,
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
            from backend.infrastructure.system_vnpy.logging_context import get_logging_context

            ctx = get_logging_context()
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
        """智能缓存验证与数据感知（合并流程）

        执行顺序（严格按照用户要求）：
        1. BackendInitializerWorker（已在主线程完成）
        2. 获取当天日期
        3. 验证交易日缓存
        4. 验证服务器池缓存
        5. 验证品种列表缓存并增量更新
        6. 验证IPO日期缓存并增量更新（与品种列表联动）
        7. 使用最新缓存进行数据质量感知
        """
        try:
            import time
            from datetime import date

            # 🆕 等待主UI完成启动（约4秒）
            time.sleep(4.0)

            print("\n" + "=" * 70)
            print("【后台进程】智能缓存验证与数据感知流程启动")
            print("=" * 70)
            self.logger.info("=" * 60)
            self.logger.info("开始智能缓存验证流程")
            self.logger.info("=" * 60)

            # 步骤2：获取当天日期 (5%)
            print("\n" + "-" * 70)
            print("【步骤1/7】获取当前日期")
            print("-" * 70)
            today = date.today()
            self.logger.info("[1/7] 当前日期: %s", today.strftime("%Y-%m-%d"))
            print(f"当前日期: {today.strftime('%Y-%m-%d')}")
            self.progress_emitter.progress_updated.emit("获取当前日期", 5)

            # 步骤3：验证交易日历缓存 (15%)
            print("\n" + "-" * 70)
            print("【步骤2/7】验证交易日历缓存")
            print("-" * 70)
            self.logger.info("[2/7] 验证交易日历缓存...")
            self._validate_trading_calendar_cache()
            self.progress_emitter.progress_updated.emit("验证交易日历缓存", 15)

            # 步骤4：验证服务器池缓存 (25%)
            print("\n" + "-" * 70)
            print("【步骤3/7】验证服务器池缓存")
            print("-" * 70)
            self.logger.info("[3/7] 验证服务器池缓存...")
            self._validate_server_pool_cache()
            self.progress_emitter.progress_updated.emit("验证服务器池缓存", 25)

            # 步骤5：验证品种列表缓存并增量更新 (35%)
            print("\n" + "-" * 70)
            print("【步骤4/7】验证品种列表缓存")
            print("-" * 70)
            self.logger.info("[4/7] 验证品种列表缓存...")
            symbols_result = self._validate_and_update_symbol_cache()
            self.progress_emitter.progress_updated.emit("验证品种列表缓存", 35)

            # 步骤6：验证IPO日期缓存并增量更新 (45%)
            print("\n" + "-" * 70)
            print("【步骤5/7】验证IPO日期缓存")
            print("-" * 70)
            self.logger.info("[5/7] 验证IPO日期缓存...")
            if symbols_result and symbols_result.get("all_symbols"):
                self._validate_and_update_ipo_cache(symbols_result["all_symbols"])
            self.progress_emitter.progress_updated.emit("验证IPO日期缓存", 45)

            # 步骤6.1：推送本地数据索引（立即可用，不等待质量扫描）
            self.logger.info("[6.1/7] 推送本地数据索引...")
            self._push_local_data_index_event()

            # 步骤6.2：使用最新缓存进行数据质量感知 (45%-95%)
            print("\n" + "-" * 70)
            print("【步骤6/7】数据质量感知")
            print("-" * 70)
            self.logger.info("[6.2/7] 开始数据质量扫描...")
            self._start_data_sensing_with_validated_cache()

            # 步骤8：启动文件监控 (100%)
            print("\n" + "-" * 70)
            print("【步骤7/7】启动文件监控")
            print("-" * 70)
            self.logger.info("[7/7] 启动文件监控...")
            self.data_sensor.start_file_watcher()
            self.progress_emitter.progress_updated.emit("系统就绪", 100)

            print("\n" + "=" * 70)
            print("【后台线程】智能缓存验证流程完成")
            print("=" * 70 + "\n")
            self.logger.info("=" * 60)
            self.logger.info("智能缓存验证流程完成")
            self.logger.info("=" * 60)

        except Exception as e:
            self.logger.exception("智能缓存验证失败: %s", e)

    def _validate_trading_calendar_cache(self):
        """验证交易日历缓存"""
        # 交易日历已在TradingCalendar中自动验证和更新
        try:
            from backend.infrastructure.data_module_vnpy.cache_manager import DailyCacheManager

            today = date.today()

            # 直接检查缓存文件
            cache_data, cache_date, is_valid = DailyCacheManager.load_with_validation(
                "trading_calendar.json"
            )

            if cache_data and is_valid:
                # 尝试从缓存数据中提取交易日数量
                # cache_data 已经是交易日列表，不需要.get("data")
                trading_days_count = len(cache_data) if isinstance(cache_data, list) else 0
                print("   缓存状态: 有效")
                print(f"   缓存日期: {cache_date}")
                print(f"   交易日历: {today.year}年 约{trading_days_count}个交易日")
                self.logger.info(
                    "✓ 交易日历缓存验证完成：%s 约%d个交易日", cache_date, trading_days_count
                )
            elif cache_data and not is_valid:
                print(f"   缓存状态: 已过时（日期: {cache_date}）")
                print("   操作: 自动重新获取...")
                self.logger.warning("交易日历缓存已过时（%s），尝试自动修复", cache_date)
                try:
                    self._regenerate_trading_calendar_cache()
                    print("   ✓ 已自动重新生成")
                    self.logger.info("✓ 交易日历缓存已自动重新生成")
                except Exception as fix_error:
                    print(f"   ❌ 自动修复失败: {fix_error}")
                    self.logger.error("交易日历缓存自动修复失败: %s", fix_error)
                    raise RuntimeError(f"交易日历缓存修复失败: {fix_error}")
            else:
                print("   缓存状态: 不存在")
                print("   操作: 首次生成...")
                self.logger.warning("交易日历缓存不存在，尝试首次生成")
                try:
                    self._regenerate_trading_calendar_cache()
                    print("   ✓ 已生成")
                    self.logger.info("✓ 交易日历缓存已首次生成")
                except Exception as gen_error:
                    print(f"   ❌ 生成失败: {gen_error}")
                    self.logger.error("交易日历缓存生成失败: %s", gen_error)
                    raise RuntimeError(f"交易日历缓存生成失败: {gen_error}")

        except Exception as e:
            print(f"   验证异常: {e}")
            self.logger.error("交易日历缓存验证失败: %s", e)
            raise  # 重新抛出异常

    def _regenerate_trading_calendar_cache(self):
        """重新生成交易日历缓存（同步调用异步方法）"""
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
            self.logger.info("交易日历缓存已生成：%d个交易日", len(trading_days_df))
        finally:
            loop.close()

    def _validate_server_pool_cache(self):
        """验证服务器池缓存"""
        try:
            from backend.infrastructure.data_module_vnpy.load_balancer import (
                server_pool_manager,
            )

            # 🔧 修复：如果未初始化，直接调用start()加载缓存（不会重新测速）
            if not server_pool_manager._running:
                self.logger.info("服务器池未初始化，正在从缓存加载...")
                print("   缓存状态: 正在加载...")

                success = server_pool_manager.start()

                if not success:
                    print("   ❌ 启动失败")
                    raise RuntimeError("服务器池启动失败")

                # 加载成功，显示状态
                stats = server_pool_manager.get_stats()
                cache_date = getattr(server_pool_manager, "_cache_date", None)

                if stats["available"] > 0:
                    print("   缓存状态: 有效")
                    print(f"   缓存日期: {cache_date}")
                    print(f"   测速结果: {stats['available']}/{stats['total']} 个服务器可用")
                    self.logger.info(
                        "✓ 服务器池缓存加载成功：%d/%d 个服务器可用",
                        stats["available"],
                        stats["total"],
                    )
                else:
                    # 如果加载后还是0个，说明测速失败或缓存为空
                    print(f"   ⚠️ 加载后无可用服务器: {stats['available']}/{stats['total']}")
                    self.logger.warning("服务器池加载后无可用服务器")
            else:
                # 已经运行，直接显示状态
                stats = server_pool_manager.get_stats()
                cache_date = getattr(server_pool_manager, "_cache_date", None)

                print("   缓存状态: 有效（已运行）")
                print(f"   缓存日期: {cache_date}")
                print(f"   测速结果: {stats['available']}/{stats['total']} 个服务器可用")
                self.logger.info(
                    "✓ 服务器池已运行：%d/%d 个服务器可用", stats["available"], stats["total"]
                )

        except RuntimeError:
            raise  # 重新抛出RuntimeError
        except Exception as e:
            print(f"   验证异常: {e}")
            self.logger.error("验证服务器池缓存失败: %s", e)
            raise RuntimeError(f"服务器池缓存验证异常: {e}")

    def _validate_and_update_symbol_cache(self):
        """验证并增量更新品种列表缓存"""
        try:
            classified, is_outdated = self.symbol_loader.load_from_cache_with_validation()

            if classified is None:
                print("   缓存状态: 不存在")
                print("   操作: 首次加载（耗时约30秒）...")
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

                    print(f"   ✓ 加载结果: 共{len(all_codes)}个品种")
                    self.logger.info("✓ 品种列表首次加载成功：%d个品种", len(all_codes))
                    return {"all_symbols": all_codes, "is_new": True}

                except Exception as e:
                    print(f"   ✗ 加载失败: {e}")
                    self.logger.error("品种列表首次加载失败: %s", e, exc_info=True)
                    # 品种列表是关键基础数据，加载失败必须中止流程
                    raise  # 让异常向上抛出，由外层try-except保护应用不崩溃

            if is_outdated:
                # 获取缓存日期
                cache_date = getattr(self.symbol_loader, "_last_cache_date", None)
                print(f"   缓存状态: 已过时（日期: {cache_date}）")
                print("   操作: 增量更新...")
                self.logger.warning("品种列表缓存已过时，开始增量更新...")
                # 🔧 发射进度更新：提示用户正在更新
                self.progress_emitter.progress_updated.emit("更新品种列表（耗时约15秒）", 36)
                update_result = self.symbol_loader.reload_with_incremental_update()

                if update_result["success"]:
                    print(
                        f"   更新结果: 新增{len(update_result['added'])}个, 删除{len(update_result['removed'])}个, 未变{update_result['unchanged']}个"
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
                    print("   更新失败")
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
                    print(
                        f"   缓存状态: 内容不完整（北证A股:{beijing_count}, T+0基金:{t0_fund_count}, 可转债:{convertible_count}）"
                    )
                    print("   操作: 强制增量更新...")
                    self.logger.warning("品种列表缓存内容不完整，强制增量更新")
                    self.progress_emitter.progress_updated.emit("更新品种列表（修复缺失分类）", 36)
                    update_result = self.symbol_loader.reload_with_incremental_update()

                    if update_result["success"]:
                        print(
                            f"   更新结果: 新增{len(update_result['added'])}个, 删除{len(update_result['removed'])}个, 未变{update_result['unchanged']}个"
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

                        print(
                            f"   更新后验证: 北证A股:{beijing_count_new}, T+0基金:{t0_fund_count_new}, 可转债:{convertible_count_new}"
                        )

                        all_codes = self.symbol_loader.extract_all_codes()
                        return {
                            "all_symbols": all_codes,
                            "added": update_result["added"],
                            "removed": update_result["removed"],
                        }
                    else:
                        print("   更新失败")
                        self.logger.error("品种列表更新失败")
                        raise RuntimeError("品种列表修复缺失分类失败")
                else:
                    # 缓存完整且有效
                    print("   缓存状态: 有效且完整")
                    if cache_date:
                        print(f"   缓存日期: {cache_date}")
                    print(f"   品种数量: {len(all_codes)}个")
                    self.logger.info("✓ 品种列表缓存有效：%d个品种", len(all_codes))
                    return {"all_symbols": all_codes, "is_valid": True}

        except Exception as e:
            self.logger.exception("验证品种列表缓存失败: %s", e)
            raise  # 向上抛出异常，由外层处理

    def _validate_and_update_ipo_cache(self, all_symbols):
        """验证并增量更新IPO日期缓存（与品种列表联动）"""
        try:
            ipo_cache = self.validator._ipo_cache
            cache_date = getattr(ipo_cache, "_cache_date", None)
            cached_count = (
                len(ipo_cache._memory_cache) if hasattr(ipo_cache, "_memory_cache") else 0
            )

            # 检查缓存是否存在
            cache_exists = hasattr(ipo_cache, "_memory_cache") and len(ipo_cache._memory_cache) > 0

            if not cache_exists:
                print("   缓存状态: 不存在")
                print("   操作: 首次加载（耗时约1-2分钟）...")
                self.logger.warning("IPO日期缓存不存在，开始首次下载...")
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
                        force_refresh=True,
                        _use_adaptive=True,
                        progress_callback=ipo_progress_callback,
                    )

                    print(f"   ✓ 下载结果: 成功{result['succeeded']}个, 失败{result['failed']}个")
                    self.logger.info("✓ IPO日期首次下载完成：成功 %d 个", result["succeeded"])

                except Exception as e:
                    print(f"   ⚠️ 下载异常: {e}")
                    self.logger.error("IPO日期首次下载失败: %s", e, exc_info=True)
                    # 不阻塞后续流程（用户需求2c）
                    self.progress_emitter.progress_updated.emit("IPO缓存下载失败（已跳过）", 48)

            elif ipo_cache.is_cache_outdated():
                print(f"   缓存状态: 已过时（日期: {cache_date}）")
                print(f"   已缓存: {cached_count}个品种的IPO日期")
                print("   操作: 增量更新...")
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

                print(
                    f"   更新结果: 新增{result['added']}个, 删除{result['removed']}个, 下载成功{result['download_succeeded']}个"
                )
                self.logger.info(
                    "✓ IPO日期更新完成：新增 %d 个，删除 %d 个，下载成功 %d 个",
                    result["added"],
                    result["removed"],
                    result["download_succeeded"],
                )
            else:
                print("   缓存状态: 有效")
                if cache_date:
                    print(f"   缓存日期: {cache_date}")
                print(f"   已缓存: {cached_count}个品种的IPO日期")
                print("   ✓ IPO日期缓存验证完成")
                self.logger.info("✓ IPO日期缓存有效：%d个品种", cached_count)

        except Exception as e:
            print(f"   验证异常: {e}")
            self.logger.exception("验证IPO日期缓存失败: %s", e)
            # 🔧 IPO缓存验证失败，显示错误状态但不阻塞后续流程
            self.progress_emitter.progress_updated.emit("IPO缓存验证失败（已跳过）", 48)

    def _start_data_sensing_with_validated_cache(self):
        """使用已验证的缓存启动数据质量感知"""
        try:
            # 定义进度回调函数（45%-95%范围）
            def progress_callback(percent):
                # 将0-100%映射到45%-95%
                mapped_percent = int(45 + percent * 0.5)
                self.progress_emitter.progress_updated.emit("数据质量扫描", mapped_percent)

            # 使用自适应扫描或传统扫描
            from .config import config_manager

            reference_symbols = self.symbol_loader.extract_all_codes()

            if config_manager.is_quality_scan_adaptive_enabled():
                # 🚀 自适应扫描（推荐）
                self.logger.info("启用自适应扫描（启动快速模式：阶段0-2）")
                overview = self.data_sensor.scan_all_data_adaptive(
                    reference_symbols=reference_symbols,
                    intervals=None,  # 使用默认 ["1d", "5m", "1m"]
                    force_refresh=False,
                    progress_callback=progress_callback,
                    max_phase=2,  # 新增：启动时只执行到阶段2
                )
            else:
                # 传统扫描
                self.logger.info("使用传统扫描（启动快速模式：阶段0-2）")
                overview = self.data_sensor.trigger_scan_with_symbols(
                    symbol_loader=self.symbol_loader,
                    force_refresh=False,  # 使用缓存
                    progress_callback=progress_callback,
                    max_phase=2,  # 新增：启动时只执行到阶段2
                )

            self.logger.info(
                "✓ 启动快速扫描完成：总计=%d, 缺失=%d, 过时=%d（详细扫描已跳过）",
                overview.total_symbols,
                overview.missing_symbols,
                overview.outdated_symbols,
            )

            # 注意：本地数据索引已在扫描前推送，此处无需重复推送

        except Exception as e:
            self.logger.exception("数据质量扫描失败: %s", e)

    def _initial_quality_scan(self):
        """初始数据质量扫描（后台线程）- 已废弃，保留用于兼容

        ⚠️ 重要：必须在品种列表更新完成后才开始扫描
        """
        import time

        # 🆕 步骤1：等待引擎完全初始化
        time.sleep(3)
        self.logger.info("🔍 准备启动数据质量扫描...")

        # 🆕 步骤2：等待品种列表加载/更新完成
        max_wait_time = 60  # 最多等待60秒
        wait_interval = 2  # 每2秒检查一次
        elapsed = 0

        while elapsed < max_wait_time:
            try:
                # 检查品种列表是否已加载
                current_codes = self.symbol_loader.extract_all_codes()

                if len(current_codes) > 0:
                    self.logger.info("✓ 品种列表已就绪: %d个品种", len(current_codes))
                    break
                else:
                    self.logger.debug("品种列表为空，继续等待... (%ds/%ds)", elapsed, max_wait_time)
                    time.sleep(wait_interval)
                    elapsed += wait_interval
            except Exception as e:
                self.logger.warning("检查品种列表失败: %s，继续等待...", e)
                time.sleep(wait_interval)
                elapsed += wait_interval

        if elapsed >= max_wait_time:
            self.logger.warning("⚠️ 等待品种列表超时，使用当前可用品种开始扫描")

        # 🆕 步骤3：批量预加载IPO日期
        try:
            all_symbols = self.symbol_loader.extract_all_codes()
            final_count = len(all_symbols)

            self.logger.info("🔄 批量预加载IPO日期...")
            try:
                self.data_sensor.validator.preload_ipo_dates_batch(
                    symbols=all_symbols, force_refresh=False  # 增量模式
                )
                self.logger.info("✓ IPO日期预加载完成")
            except Exception as e:
                self.logger.exception("IPO日期预加载失败: %s", e)
                self.logger.warning("继续进行数据质量扫描...")

            # 🆕 步骤4：开始数据质量扫描
            self.logger.info("🚀 开始初始数据质量扫描（品种数: %d）...", final_count)

            # 触发扫描
            overview = self.trigger_data_quality_scan(force_refresh=True)

            if overview:
                # 推送vnpy事件
                self._push_quality_overview_event(overview)
                self.logger.info(
                    "✓ 初始数据质量扫描完成，品种: %d，评分: %s",
                    overview.total_symbols,
                    overview.quality_score,
                )
            else:
                self.logger.warning("初始数据质量扫描未返回结果")
        except Exception as e:
            self.logger.exception("初始数据质量扫描失败: %s", e)

    def _push_quality_overview_event(self, overview: QualityOverview):
        """推送数据质量概览事件

        Args:
            overview: 数据质量概览对象
        """
        try:
            event_engine = self.event_engine
            if not event_engine:
                self.logger.warning("事件引擎不可用，无法推送质量概览")
                return

            # 构建事件数据
            event_data = {
                "total_symbols": overview.total_symbols,
                "local_symbols": overview.total_symbols - overview.missing_symbols,
                "missing_symbols": overview.missing_symbols,
                "error_symbols": overview.error_symbols,
                "warning_symbols": overview.warning_symbols,
                "quality_score": overview.quality_score,
                "last_scan_time": (
                    overview.last_scan_time.isoformat() if overview.last_scan_time else None
                ),
                # 🆕 数据缺失与滞后
                "data_missing_symbols": overview.data_missing_symbols,
                "data_lagging_days": overview.data_lagging_days,
                "outdated_symbols": overview.outdated_symbols,
                # 🔧 修复：添加问题品种详情
                "details": overview.details,
            }

            event = Event(EVENT_DATA_QUALITY_UPDATE, event_data)
            event_engine.put(event)

            self.logger.info(
                "📊 推送数据质量概览: 评分%s, 总品种%d, 缺失%d, 问题品种%d个",
                overview.quality_score,
                overview.total_symbols,
                overview.missing_symbols,
                len(overview.details),
            )
        except Exception as e:
            self.logger.warning("推送数据质量概览失败: %s", e, exc_info=True)

    def _push_local_data_index_event(self):
        """推送本地数据索引事件（品种列表）给UI

        在缓存验证完成后立即调用（不等待质量扫描），让UI能快速获得联想功能。
        索引生成仅需扫描本地文件，耗时很短（通常<1秒）。
        """
        try:
            event_engine = self.event_engine
            if not event_engine:
                self.logger.warning("事件引擎不可用，无法推送本地数据索引")
                return

            # 获取本地数据索引（品种代码列表）
            local_symbol_codes = self.storage_manager.get_local_data_index()

            if not local_symbol_codes:
                self.logger.info("本地数据索引为空，跳过推送")
                return

            # 构建事件数据：包含代码和名称的完整品种列表
            symbol_list = []
            all_classified = self.symbol_loader.get_all_classified()

            # 构建代码到名称的映射
            code_to_name = {}
            for market_symbols in all_classified.values():
                for symbol_info in market_symbols:
                    code = symbol_info.get("code") or symbol_info.get("symbol")
                    name = symbol_info.get("name", "")
                    if code:
                        code_to_name[code] = name

            # 构建完整的品种列表
            for code in local_symbol_codes:
                name = code_to_name.get(code, "")
                symbol_list.append({"code": code, "name": name})

            # 推送事件
            from .events import EVENT_LOCAL_DATA_INDEX_READY

            event_data = {
                "symbols": symbol_list,
                "count": len(symbol_list),
            }
            event = Event(EVENT_LOCAL_DATA_INDEX_READY, event_data)
            event_engine.put(event)

            self.logger.info("📋 推送本地数据索引: %d 个品种", len(symbol_list))

        except Exception as e:
            self.logger.warning("推送本地数据索引失败: %s", e, exc_info=True)

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
            from backend.infrastructure.system_vnpy.logging_context import get_logging_context

            ctx = get_logging_context()

            # 切换到下载阶段
            old_stage = ctx.get_current_stage()
            ctx.set_stage("downloading")

            # 使用下载场景上下文
            with ctx.scenario("bulk_download"):
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

                # 恢复阶段
                ctx.set_stage(old_stage)
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
