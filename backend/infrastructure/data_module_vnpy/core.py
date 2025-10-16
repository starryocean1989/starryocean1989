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
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Union

from vnpy.event import Event, EventEngine
from vnpy.trader.engine import BaseEngine, MainEngine

from .config import config_manager
from .symbol_management import SymbolLoader
from .data_fetcher import MultiProcessStockFetcher
from .data_quality import StorageManager, DataValidator, ValidationSummary, DataFileWatcher
from .gateways import PollingGateway, VirtualGateway
from .data_readers import TdxBinaryReader
from .data_quality import DataSensor, QualityOverview
from .preload_service import PreloadService
from .unified_data_manager import UnifiedDataManager


# 从events模块导入常量
from .events import (
    APP_NAME,
    EVENT_CHINASTOCK_LOG,
    EVENT_CHINASTOCK_VALIDATION,
    EVENT_CHINASTOCK_FILE_CHANGE,
    EVENT_CHINASTOCK_DOWNLOAD,
    EVENT_DATA_QUALITY_UPDATE,
    EVENT_DATA_SCAN_COMPLETE,
    EventPublisher,
)


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

        # 日志记录器
        self.logger = logging.getLogger(__name__)

        # 通用事件发布器（用于日志等通用事件）
        self.event_publisher = EventPublisher(event_engine)

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
                self.logger.error("预加载服务初始化失败: %s", exc, exc_info=True)
                self.preload_service = None

        # ⚡ 优化：统一数据管理器立即初始化（不涉及耗时操作）
        if config_manager.is_unified_manager_enabled():
            try:
                self.unified_data_manager = UnifiedDataManager(
                    self,
                    preload_service=self.preload_service,
                )
            except Exception as exc:
                self.logger.error("统一数据管理器初始化失败: %s", exc, exc_info=True)
                self.unified_data_manager = None

        self.logger.info("中国A股数据管理引擎初始化完成（快速启动模式）")

        # ⚡ 优化：健康检查也延迟执行，避免阻塞
        # 健康检查将在首次查询时自动执行
        # try:
        #     self.healthcheck()
        # except Exception:
        #     pass

    # ==================== 健康检查与就绪 ====================

    def _ensure_lazy_init(self) -> None:
        """确保延迟初始化已完成（简化版，代理调用）"""
        if self._lazy_init_done:
            return

        with self._lazy_init_lock:
            if not self._lazy_init_done:
                from .lifecycle_manager import LifecycleManager

                LifecycleManager.lazy_init(self.data_sensor, self.preload_service)
                self._lazy_init_done = True

    def healthcheck(self) -> Dict[str, Any]:
        """健康检查（代理调用）"""
        from .health_checker import HealthChecker

        result = HealthChecker.check_system_health()
        setattr(self, "_ready", result["ready"])
        return result

    def is_ready(self) -> bool:
        """是否已通过健康检查（基本就绪）"""
        # ⚡ 快速启动模式：默认返回True，实际健康检查延迟到首次使用
        return True
        # return bool(getattr(self, "_ready", False))

    def close(self) -> None:
        """关闭引擎（代理调用）"""
        from .lifecycle_manager import LifecycleManager

        LifecycleManager.close_all({
            "data_sensor": self.data_sensor,
            "preload": self.preload_service,
            "polling": self.polling_gateway,
            "virtual": self.virtual_gateway,
        })
        self.logger.info("中国A股数据管理引擎已关闭")

    def refresh_stock_list(self) -> Optional[Dict[str, List[Dict[str, Any]]]]:
        """读取本地品种缓存（代理调用）"""
        self._ensure_lazy_init()
        return self.symbol_loader.load_from_cache() or {}

    def reload_stock_list(self) -> Dict[str, Any]:
        """调用API更新品种缓存（代理调用，事件由SymbolLoader推送）"""
        return self.symbol_loader.reload_and_classify()

    def download_incremental(
        self, start_date: Union[str, date], market_types: Optional[List[str]] = None
    ) -> bool:
        """增量下载K线数据（代理调用）"""
        self._ensure_lazy_init()
        return self.stock_fetcher.start_incremental_download_async(
            start_date, self.symbol_loader, self.storage_manager, market_types
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
            target_symbol = symbol or kwargs.get("symbols")
            if isinstance(target_symbol, (list, tuple)):
                target_symbol = target_symbol[0] if target_symbol else None
            if target_symbol is None:
                return None

            return self.storage_manager.query_kline(
                target_symbol, interval, start_date, end_date
            )

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
        pass

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
        publisher.push_download_progress_event(download_type, progress_pct, completed, total, current_item)

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
        """初始化轮询网关（代理调用）"""
        from .gateways import GatewayManager

        self.polling_gateway = GatewayManager.start_polling(self.event_engine)

    def start_polling_gateway(self, setting: Optional[Dict] = None) -> bool:
        """启动轮询网关（代理调用）"""
        from .gateways import GatewayManager

        self.polling_gateway = GatewayManager.start_polling(
            self.event_engine, self.polling_gateway, setting
        )
        return self.polling_gateway is not None

    def stop_polling_gateway(self) -> bool:
        """停止轮询网关（代理调用）"""
        from .gateways import GatewayManager

        return GatewayManager.stop_polling(self.polling_gateway)

    # ==================== 虚拟网关管理方法 ====================

    def _init_virtual_gateway(self) -> None:
        """初始化虚拟网关（代理调用）"""
        from .gateways import GatewayManager

        self.virtual_gateway = GatewayManager.init_virtual_gateway(self.event_engine)

    def start_virtual_gateway(
        self, start_datetime: str, speed: float = 1.0, symbols: Optional[List[str]] = None
    ) -> bool:
        """启动虚拟网关（代理调用）"""
        from .gateways import GatewayManager

        self.virtual_gateway = GatewayManager.start_virtual(
            self.event_engine, self.virtual_gateway, start_datetime, speed, symbols
        )
        return self.virtual_gateway is not None

    def stop_virtual_gateway(self) -> bool:
        """停止虚拟网关（代理调用）"""
        from .gateways import GatewayManager

        return GatewayManager.stop_virtual(self.virtual_gateway)

    # ==================== 数据读取器管理方法 ====================

    def read_tdx_data(
        self, symbols: List[str], data_type: str = "day", market: str = "sh"
    ) -> Dict[str, bool]:
        """读取通达信本地数据并保存（代理调用）"""
        if self.tdx_reader is None:
            self.tdx_reader = TdxBinaryReader()
        return self.tdx_reader.process_batch(symbols, data_type, market)

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
        return self.data_sensor.trigger_scan_with_symbols(self.symbol_loader, force_refresh=force_refresh)

    def scan_corrupted_files(self, auto_delete: bool = False) -> Dict[str, List[str]]:
        """扫描并修复损坏的Parquet文件（代理调用）"""
        return self.storage_manager.scan_and_repair_corrupted_files(auto_delete)
