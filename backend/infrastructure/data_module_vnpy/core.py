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


# 事件类型常量
EVENT_CHINASTOCK_LOG = "eChinaStockLog"
EVENT_CHINASTOCK_VALIDATION = "eChinaStockValidation"
EVENT_CHINASTOCK_FILE_CHANGE = "eChinaStockFileChange"
EVENT_CHINASTOCK_DOWNLOAD = "eChinaStockDownload"
EVENT_DATA_QUALITY_UPDATE = "eDataQualityUpdate"  # 数据质量更新事件
EVENT_DATA_SCAN_COMPLETE = "eDataScanComplete"  # 扫描完成事件

# 应用名称
APP_NAME = "ChinaStock"


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

        # 初始化组件
        self.symbol_loader = SymbolLoader()
        self.stock_fetcher = MultiProcessStockFetcher()  # 用于下载功能
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

        # 🔧 异步下载管理
        self._download_thread: Optional[threading.Thread] = None
        self._download_lock = threading.Lock()

        # 启动文件监控
        if config_manager.is_watcher_enabled():
            self._start_file_watcher()

        # 自动启动轮询网关（如果配置启用）
        if config_manager.is_polling_gateway_enabled():
            self._init_polling_gateway()

        # 自动启动虚拟网关（如果配置启用）
        if config_manager.is_virtual_gateway_enabled():
            self._init_virtual_gateway()

        # 启动数据感知（后台线程）
        self._start_data_sensing_async()

        # 初始化预加载与统一数据管理器
        if config_manager.is_preload_enabled():
            try:
                self.preload_service = PreloadService(self)
                if config_manager.is_preload_auto_start():
                    self.preload_service.start(prime=True)
            except Exception as exc:
                self.logger.error("预加载服务初始化失败: %s", exc, exc_info=True)
                self.preload_service = None

        if config_manager.is_unified_manager_enabled():
            try:
                self.unified_data_manager = UnifiedDataManager(
                    self,
                    preload_service=self.preload_service,
                )
            except Exception as exc:
                self.logger.error("统一数据管理器初始化失败: %s", exc, exc_info=True)
                self.unified_data_manager = None

        self.logger.info("中国A股数据管理引擎初始化完成")
        # 初始化后执行一次健康检查（不抛异常，仅记录）
        try:
            self.healthcheck()
        except Exception:
            pass

    # ==================== 健康检查与就绪 ====================

    def healthcheck(self) -> Dict[str, Any]:
        """
        健康检查：验证关键目录与最小数据可用性。
        Returns: {"ready": bool, "message": str, "details": {...}}
        """
        details: Dict[str, Any] = {}
        ready = True
        message = "OK"
        try:
            from .config import config_manager
            from pathlib import Path
            import os

            cache_dir = config_manager.get_cache_dir()
            data_dir = config_manager.get_data_dir()
            details["cache_dir"] = str(cache_dir)
            details["data_dir"] = str(data_dir)

            # 目录存在性与可写性
            cache_dir.mkdir(parents=True, exist_ok=True)
            data_dir.mkdir(parents=True, exist_ok=True)
            details["cache_dir_exists"] = cache_dir.exists()
            details["data_dir_exists"] = data_dir.exists()

            # 尝试写入/读取探针文件（权限检测）
            probe = cache_dir / ".probe"
            try:
                probe.write_text("ok", encoding="utf-8")
                details["cache_dir_writable"] = True
                with probe.open("r", encoding="utf-8") as f:
                    _ = f.read()
                probe.unlink(missing_ok=True)
            except Exception:
                details["cache_dir_writable"] = False
                ready = False
                message = "cache_dir 不可写"

            # 最小数据可用性（非强制）
            parquet_count = 0
            try:
                for root, _, files in os.walk(data_dir):
                    for fn in files:
                        if fn.lower().endswith(".parquet"):
                            parquet_count += 1
                            if parquet_count >= 1:
                                break
                    if parquet_count >= 1:
                        break
            except Exception:
                pass
            details["parquet_files"] = parquet_count

            if parquet_count == 0 and ready:
                message = "未检测到最小数据集（可后续通过增量下载或导入TDX生成）"

        except Exception as e:
            ready = False
            message = f"健康检查异常: {e}"

        setattr(self, "_ready", bool(ready))
        return {"ready": bool(ready), "message": message, "details": details}

    def is_ready(self) -> bool:
        """是否已通过健康检查（基本就绪）"""
        return bool(getattr(self, "_ready", False))

    def close(self) -> None:
        """关闭引擎"""
        try:
            # 停止数据感知
            self.stop_data_sensing()

            # 停止文件监控
            # 文件监控已合并到data_sensor，无需单独停止

            if self.preload_service:
                self.preload_service.stop()
                self.preload_service = None

            # 关闭轮询网关
            if self.polling_gateway:
                self.polling_gateway.close()

            # 关闭虚拟网关
            if self.virtual_gateway:
                self.virtual_gateway.close()

            self.logger.info("中国A股数据管理引擎已关闭")

        except Exception as e:
            self.logger.error(f"关闭引擎失败: {e}")

    def refresh_stock_list(self) -> Optional[Dict[str, List[Dict[str, Any]]]]:
        """
        读取本地品种缓存

        Returns:
            品种分类字典
        """
        try:
            self.logger.info("读取本地品种缓存...")
            result = self.symbol_loader.load_from_cache()

            if result is None:
                self.logger.warning("本地缓存不存在，返回空字典")
                return {}

            # 推送日志事件
            total_stocks = sum(len(stocks) for stocks in result.values())
            self._push_log_event(f"成功读取本地品种缓存: {total_stocks} 个品种")

            return result

        except Exception as e:
            self.logger.error(f"读取品种缓存失败: {e}")
            self._push_log_event(f"读取品种缓存失败: {e}", "ERROR")
            return None

    def reload_stock_list(self) -> bool:
        """
        调用API更新品种缓存（带完整异常处理）

        Returns:
            是否更新成功
        """
        try:
            self.logger.info("开始更新品种列表...")

            # 调用SymbolLoader从API加载
            classified = self.symbol_loader.load_from_api()

            # 验证数据
            total_count = sum(len(stocks) for stocks in classified.values())
            if total_count == 0:
                self.logger.error("获取品种列表失败: 数据为空")
                self._push_download_event("stock_list", "error", 0, "获取的数据为空")
                self._push_log_event("获取品种列表失败: 数据为空", "ERROR")
                return False

            # 推送下载事件
            self._push_download_event("stock_list", "success", total_count)
            self._push_log_event(f"品种列表更新成功: {total_count} 个品种")

            return True

        except Exception as e:
            # 最外层兜底异常处理
            self.logger.error(f"更新品种列表失败: {e}", exc_info=True)
            self._push_download_event("stock_list", "error", 0, f"错误: {str(e)}")
            self._push_log_event(f"更新品种列表失败: {e}", "ERROR")
            return False

    def download_incremental(
        self, start_date: Union[str, date], market_types: Optional[List[str]] = None
    ) -> bool:
        """
        增量下载K线数据（异步执行，立即返回）

        Args:
            start_date: 开始日期
            market_types: 市场类型列表

        Returns:
            是否成功启动下载任务
        """
        with self._download_lock:
            # 检查是否有正在运行的下载任务
            if self._download_thread and self._download_thread.is_alive():
                self.logger.warning("已有下载任务正在运行")
                return False

            # 重置下载状态
            self.stock_fetcher.reset_download_state()

            # 创建并启动后台下载线程
            self._download_thread = threading.Thread(
                target=self._do_download_incremental,
                args=(start_date, market_types),
                daemon=True,
                name="IncrementalDownloadThread",
            )
            self._download_thread.start()

            self.logger.info("✅ 增量下载任务已启动（后台线程）")
            return True

    def _do_download_incremental(
        self, start_date: Union[str, date], market_types: Optional[List[str]] = None
    ):
        """
        实际执行增量下载的后台方法（在独立线程中运行）

        Args:
            start_date: 开始日期
            market_types: 市场类型列表
        """
        try:
            if market_types is None:
                market_types = ["上证A股", "深证A股", "北证A股", "T+0基金", "可转债"]

            self.logger.info(f"开始增量下载K线数据: 从 {start_date} 开始")

            # 🚀 关键修正：通过SymbolLoader缓存获取品种列表
            classified_stocks = self.symbol_loader.load_from_cache() or {}

            if not classified_stocks:
                self.logger.warning("本地品种缓存为空，尝试重新加载品种列表…")
                if not self.reload_stock_list():
                    error_msg = "无法获取品种列表，请先在【品种列表】界面点击【重新加载品种】按钮"
                    self.logger.error(error_msg)
                    self._push_download_event("incremental_kline", "error", 0, error_msg)
                    self._push_log_event(error_msg, "ERROR")
                    return
                classified_stocks = self.symbol_loader.load_from_cache() or {}

            if not classified_stocks:
                error_msg = "品种缓存仍为空，增量下载任务已取消"
                self.logger.error(error_msg)
                self._push_download_event("incremental_kline", "error", 0, error_msg)
                self._push_log_event(error_msg, "ERROR")
                return

            all_stocks: List[str] = []
            market_stock_counts: Dict[str, int] = {}

            for market_type in market_types:
                stocks = classified_stocks.get(market_type, [])
                if stocks and isinstance(stocks[0], str):
                    stock_codes = [code for code in stocks if code]
                else:
                    stock_codes = [stock.get("code", "") for stock in stocks if stock.get("code")]
                market_stock_counts[market_type] = len(stock_codes)
                all_stocks.extend(stock_codes)

            # 🚀 调试：品种缓存统计（这些就是最终要下载的品种）
            self.logger.info("📊 品种缓存统计（最终下载品种）:")
            for market_type, count in market_stock_counts.items():
                self.logger.info("  • %s: %d 个品种", market_type, count)
            self.logger.info("  • 总品种数: %d", len(all_stocks))

            if not all_stocks:
                error_msg = "本地品种缓存不存在或为空，请先在【品种列表】界面点击【重新加载品种】按钮获取品种列表"
                self.logger.error(error_msg)
                self._push_download_event("incremental_kline", "error", 0, error_msg)
                self._push_log_event(error_msg, "ERROR")
                return

            # 🚀 调试：记录实际下载参数
            from datetime import date

            today = date.today()
            actual_start_date = start_date

            if isinstance(start_date, str):
                from datetime import datetime

                actual_start_date = datetime.strptime(start_date, "%Y-%m-%d").date()

            days_diff = (today - actual_start_date).days
            self.logger.info("📅 增量下载日期范围:")
            self.logger.info("  • 开始日期: %s", actual_start_date)
            self.logger.info("  • 结束日期: %s", today)
            self.logger.info("  • 天数差: %d 天", days_diff)

            # 🚀 检查日期范围合理性
            if days_diff <= 0:
                error_msg = f"日期范围无效：开始日期{actual_start_date}晚于或等于今天{today}"
                self.logger.error(error_msg)
                self._push_download_event("incremental_kline", "error", 0, error_msg)
                self._push_log_event(error_msg, "ERROR")
                return

            if days_diff > 100:
                self.logger.warning("⚠️ 日期范围超过100天，可能导致下载大量历史数据")

            self.logger.info("✅ 日期范围验证通过，开始下载...")

            # 定义进度回调函数
            def progress_callback(completed: int, total: int, symbol: str, interval: str):
                """进度回调：通过事件推送进度"""
                progress_pct = (completed / total) * 100

                # 🚀 限制事件推送频率：只在每100个或特殊节点推送（避免UI崩溃）
                should_push = (
                    completed % 100 == 0
                    or completed == 1  # 第一个
                    or completed == total  # 最后一个
                )

                if not should_push:
                    return

                # 🔧 调试日志（每100个打印一次）
                if completed % 100 == 0:
                    self.logger.info(
                        "推送进度事件: %d/%d (%.1f%%) - %s %s",
                        completed,
                        total,
                        progress_pct,
                        symbol,
                        interval,
                    )

                self._push_download_progress_event(
                    "incremental_kline", progress_pct, completed, total, f"{symbol} {interval}"
                )

            # 下载增量K线数据（带进度回调）
            download_results = self.stock_fetcher.download_incremental_kline(
                all_stocks, start_date, progress_callback=progress_callback
            )

            # 检查是否被停止
            if self.stock_fetcher.is_stopped():
                self.logger.warning("⛔ 下载被停止")
                self._push_download_event("incremental_kline", "stopped", len(download_results))
                self._push_log_event("增量下载已停止", "WARNING")
                return

            # 合并并保存数据
            saved_count = 0
            skipped_count = 0
            failed_count = 0

            # 🚀 统计下载结果的详细状态
            none_count = sum(1 for v in download_results.values() if v is None)
            empty_count = sum(1 for v in download_results.values() if v is not None and v.empty)

            self.logger.info("=" * 60)
            self.logger.info("开始保存下载结果...")
            self.logger.info("📊 下载结果分析:")
            self.logger.info("  • 下载结果总数: %d", len(download_results))
            self.logger.info("  • 下载返回None: %d (下载失败)", none_count)
            self.logger.info("  • 下载返回空数据: %d (品种无数据/停牌等)", empty_count)
            self.logger.info(
                "  • 下载返回有效数据: %d (待保存)",
                len(download_results) - none_count - empty_count,
            )

            for key, data in download_results.items():
                symbol, interval = key.split("_", 1)

                # 🚀 检查数据有效性（防止保存空DataFrame导致损坏文件）
                if data is None:
                    self.logger.debug("跳过保存（下载失败）: %s %s", symbol, interval)
                    skipped_count += 1
                elif data.empty or len(data) == 0:
                    self.logger.debug("跳过保存（空数据）: %s %s", symbol, interval)
                    skipped_count += 1
                else:
                    # 有数据，尝试保存
                    try:
                        success = self.storage_manager.merge_data(symbol, interval, data)
                        if success:
                            saved_count += 1
                            self.logger.debug(
                                "✓ 保存成功: %s %s (%d行)", symbol, interval, len(data)
                            )
                        else:
                            failed_count += 1
                            self.logger.error("✗ 保存失败: %s %s", symbol, interval)
                    except Exception as e:
                        self.logger.error("保存 %s %s 异常: %s", symbol, interval, e)
                        failed_count += 1

            # 统计汇总
            self.logger.info("=" * 60)
            self.logger.info("📊 保存统计:")
            self.logger.info("  • 下载结果总数: %d", len(download_results))
            self.logger.info("  • 成功保存: %d", saved_count)
            self.logger.info("  • 跳过（下载失败/空数据）: %d", skipped_count)
            self.logger.info("  • 保存失败: %d", failed_count)
            self.logger.info(
                "  • 保存成功率: %.1f%%",
                (
                    (saved_count / (saved_count + failed_count) * 100)
                    if (saved_count + failed_count) > 0
                    else 0
                ),
            )
            self.logger.info("=" * 60)

            # 推送下载事件
            self._push_download_event("incremental_kline", "success", saved_count)
            self._push_log_event(
                f"增量下载完成: {saved_count} 个数据集（跳过{skipped_count}个空数据）"
            )

        except Exception as e:
            self.logger.error(f"增量下载失败: {e}", exc_info=True)
            self._push_download_event("incremental_kline", "error", 0, str(e))
            self._push_log_event(f"增量下载失败: {e}", "ERROR")

    def query_data(
        self,
        symbol: Optional[str] = None,
        interval: str = "1d",
        start_date: Optional[Union[str, date]] = None,
        end_date: Optional[Union[str, date]] = None,
        **kwargs,
    ) -> Optional[Any]:
        """统一查询接口，兼容单品种与多品种调用."""

        symbols_param = kwargs.get("symbols")
        frequency = kwargs.get("frequency") or interval
        check_gaps = kwargs.get("check_gaps", True)

        # 多品种查询路径
        if symbols_param is not None:
            symbols_list = (
                [symbols_param]
                if isinstance(symbols_param, str)
                else list(symbols_param)
            )
            if not symbols_list:
                return {"success": True, "data": {}, "interval": frequency}

            if self.unified_data_manager:
                datasets = self.unified_data_manager.get_multi_kline_data(
                    symbols_list,
                    interval=frequency,
                    start_date=start_date,
                    end_date=end_date,
                    check_gaps=check_gaps,
                )
            else:
                datasets = {
                    sym: self.storage_manager.query_kline(sym, frequency, start_date, end_date)
                    for sym in symbols_list
                }

            payload = {
                sym: (df.to_dict("records") if df is not None else [])
                for sym, df in datasets.items()
            }

            success = any(payload.values())
            return {
                "success": success,
                "data": payload,
                "interval": frequency,
                "message": None if success else "未查询到数据",
            }

        # 单品种查询
        target_symbol = symbol or kwargs.get("symbols")
        if isinstance(target_symbol, (list, tuple)):
            target_symbol = target_symbol[0] if target_symbol else None
        if target_symbol is None:
            return None

        try:
            if self.unified_data_manager:
                data = self.unified_data_manager.get_kline_data(
                    target_symbol,
                    interval=interval,
                    start_date=start_date,
                    end_date=end_date,
                    check_gaps=check_gaps,
                )
            else:
                data = self.storage_manager.query_kline(
                    target_symbol, interval, start_date, end_date
                )

            if data is not None and hasattr(data, "__len__"):
                self.logger.info(
                    "查询数据成功: %s %s, %d 条记录", target_symbol, interval, len(data)
                )
            else:
                self.logger.warning("未找到数据: %s %s", target_symbol, interval)

            return data

        except Exception as e:
            self.logger.error("查询数据失败: %s %s, %s", target_symbol, interval, e)
            return None

    def get_validation_result(self, force_refresh: bool = False) -> Optional[ValidationSummary]:
        """
        获取数据感知结果

        Args:
            force_refresh: 是否强制刷新校验结果

        Returns:
            校验汇总结果
        """
        try:
            if force_refresh:
                summary = self.validator.validate_all_data(force_refresh=True)
            else:
                summary = self.validator.get_validation_summary()
                if summary is None:
                    summary = self.validator.validate_all_data()  # type: ignore[assignment]

            if summary:
                # 推送校验事件
                self._push_validation_event(summary)
                self.logger.info(
                    f"数据校验完成: " f"{summary.valid_symbols}/{summary.total_symbols} 有效"
                )

            return summary

        except Exception as e:
            self.logger.error(f"获取校验结果失败: {e}")
            return None

    def get_market_stocks(self, market_type: str) -> List[Dict[str, Any]]:
        """
        获取指定市场的品种列表

        Args:
            market_type: 市场类型

        Returns:
            品种列表，每个品种包含 code, name, market
        """
        try:
            classified = self.symbol_loader.load_from_cache()
            if classified is None:
                self.logger.warning("本地缓存不存在")
                return []
            return classified.get(market_type, [])
        except Exception as e:
            self.logger.error(f"获取 {market_type} 品种列表失败: {e}")
            return []

    def get_all_market_stocks(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        获取所有市场的品种分类

        Returns:
            所有市场的品种分类字典，每个品种包含 code, name, market
        """
        try:
            classified = self.symbol_loader.load_from_cache()
            if classified is None:
                self.logger.warning("本地缓存不存在")
                return {}
            return classified
        except Exception as e:
            self.logger.error(f"获取所有品种分类失败: {e}")
            return {}

    def get_storage_stats(self) -> Dict[str, Any]:
        """
        获取存储统计信息

        Returns:
            存储统计字典
        """
        try:
            return self.storage_manager.get_storage_stats()
        except Exception as e:
            self.logger.error(f"获取存储统计失败: {e}")
            return {}

    def get_config(self) -> Dict[str, Any]:
        """
        获取配置信息

        Returns:
            配置字典
        """
        try:
            return config_manager.get_all_config()
        except Exception as e:
            self.logger.error(f"获取配置失败: {e}")
            return {}

    def update_config(self, config_dict: Dict[str, Any]) -> bool:
        """
        更新配置

        Args:
            config_dict: 配置字典

        Returns:
            是否更新成功
        """
        try:
            config_manager.update_config(config_dict)
            self.logger.info("配置更新成功")
            return True
        except Exception as e:
            self.logger.error(f"更新配置失败: {e}")
            return False

    def _start_file_watcher(self) -> None:
        """启动文件监控（已合并到data_sensor）"""
        # 文件监控现在由data_sensor处理，无需单独启动
        pass

    def _push_log_event(self, message: str, level: str = "INFO") -> None:
        """
        推送日志事件

        Args:
            message: 日志消息
            level: 日志级别
        """
        try:
            event_data = {
                "message": message,
                "level": level,
                "timestamp": datetime.now(),
                "engine": APP_NAME,
            }

            event = Event(EVENT_CHINASTOCK_LOG, event_data)
            self.event_engine.put(event)

        except Exception as e:
            self.logger.error(f"推送日志事件失败: {e}")

    def _push_validation_event(self, summary: ValidationSummary) -> None:
        """
        推送校验事件

        Args:
            summary: 校验汇总
        """
        try:
            event_data = {
                "summary": {
                    "total_symbols": summary.total_symbols,
                    "valid_symbols": summary.valid_symbols,
                    "invalid_symbols": summary.invalid_symbols,
                    "total_errors": summary.total_errors,
                    "total_warnings": summary.total_warnings,
                    "check_time": summary.check_time.isoformat(),
                    "base_date": summary.base_date.isoformat(),
                },
                "timestamp": datetime.now(),
                "engine": APP_NAME,
            }

            event = Event(EVENT_CHINASTOCK_VALIDATION, event_data)
            self.event_engine.put(event)

        except Exception as e:
            self.logger.error(f"推送校验事件失败: {e}")

    def _push_download_event(
        self, download_type: str, status: str, count: int, error: Optional[str] = None
    ) -> None:
        """
        推送下载事件

        Args:
            download_type: 下载类型
            status: 状态
            count: 数量
            error: 错误信息
        """
        try:
            event_data = {
                "download_type": download_type,
                "status": status,
                "count": count,
                "error": error,
                "timestamp": datetime.now(),
                "engine": APP_NAME,
            }

            event = Event(EVENT_CHINASTOCK_DOWNLOAD, event_data)
            self.event_engine.put(event)

        except Exception as e:
            self.logger.error(f"推送下载事件失败: {e}")

    def _push_download_progress_event(
        self, download_type: str, progress_pct: float, completed: int, total: int, current_item: str
    ) -> None:
        """
        推送下载进度事件

        Args:
            download_type: 下载类型
            progress_pct: 进度百分比
            completed: 已完成数量
            total: 总数量
            current_item: 当前项目
        """
        try:
            event_data = {
                "download_type": download_type,
                "status": "progress",
                "progress": progress_pct,
                "completed": completed,
                "total": total,
                "current_item": current_item,
                "timestamp": datetime.now(),
                "engine": APP_NAME,
            }

            event = Event(EVENT_CHINASTOCK_DOWNLOAD, event_data)
            self.event_engine.put(event)

        except Exception as e:
            self.logger.error(f"推送下载进度事件失败: {e}")

    # ==================== 下载控制方法 ====================

    def stop_download(self):
        """停止当前下载任务"""
        self.stock_fetcher.stop_download()
        self.logger.info("已请求停止下载")

    def pause_download(self):
        """暂停当前下载任务"""
        self.stock_fetcher.pause_download()
        self.logger.info("已请求暂停下载")

    def resume_download(self):
        """恢复暂停的下载任务"""
        self.stock_fetcher.resume_download()
        self.logger.info("已请求恢复下载")

    def get_download_progress(self) -> Dict[str, Any]:
        """获取当前下载进度（供前端轮询）"""
        return self.stock_fetcher.get_download_progress()

    # ==================== 轮询网关管理方法 ====================

    def _init_polling_gateway(self) -> None:
        """初始化轮询网关"""
        try:
            self.polling_gateway = PollingGateway(self.event_engine, "POLLING")
            # 使用默认设置连接
            self.polling_gateway.connect({})
            self.logger.info("轮询网关已初始化")
        except Exception as e:
            self.logger.error("初始化轮询网关失败: %s", e)

    def start_polling_gateway(self, setting: Optional[Dict] = None) -> bool:
        """
        启动轮询网关

        Args:
            setting: 网关设置（可选）

        Returns:
            是否启动成功
        """
        try:
            if self.polling_gateway is None:
                self.polling_gateway = PollingGateway(self.event_engine, "POLLING")

            if setting is None:
                setting = {}

            self.polling_gateway.connect(setting)
            self.logger.info("轮询网关已启动")
            self._push_log_event("✅ 轮询网关已成功启动", "INFO")
            return True

        except ValueError as e:
            # 配置错误（如缓存不存在），给出明确提示
            error_msg = f"启动轮询网关失败: {str(e)}"
            self.logger.error(error_msg)
            self._push_log_event(error_msg, "ERROR")
            return False
        except Exception as e:
            # 其他未知错误
            error_msg = f"启动轮询网关失败（未知错误）: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            self._push_log_event(error_msg, "ERROR")
            return False

    def stop_polling_gateway(self) -> bool:
        """
        停止轮询网关

        Returns:
            是否停止成功
        """
        try:
            if self.polling_gateway:
                self.polling_gateway.close()
                self.logger.info("轮询网关已停止")
            return True

        except Exception as e:
            self.logger.error("停止轮询网关失败: %s", e)
            return False

    # ==================== 虚拟网关管理方法 ====================

    def _init_virtual_gateway(self) -> None:
        """初始化虚拟网关"""
        try:
            self.virtual_gateway = VirtualGateway(self.event_engine, "VIRTUAL")
            # 使用默认设置连接
            self.virtual_gateway.connect({})
            self.logger.info("虚拟网关已初始化")
        except Exception as e:
            self.logger.error("初始化虚拟网关失败: %s", e)

    def start_virtual_gateway(
        self, start_datetime: str, speed: float = 1.0, symbols: Optional[List[str]] = None
    ) -> bool:
        """
        启动虚拟网关

        Args:
            start_datetime: 起始时间（格式：YYYY-MM-DD HH:MM:SS）
            speed: 推送速度倍数（1.0=实时，2.0=2倍速）
            symbols: 品种列表（可选）

        Returns:
            是否启动成功
        """
        try:
            if self.virtual_gateway is None:
                self.virtual_gateway = VirtualGateway(self.event_engine, "VIRTUAL")

            setting = {
                "起始时间": start_datetime,
                "推送速度": speed,
                "品种列表": ",".join(symbols) if symbols else "",
            }

            self.virtual_gateway.connect(setting)
            self.logger.info("虚拟网关已启动")
            self._push_log_event("✅ 虚拟网关已成功启动", "INFO")
            return True

        except ValueError as e:
            # 配置错误（如缓存不存在），给出明确提示
            error_msg = f"启动虚拟网关失败: {str(e)}"
            self.logger.error(error_msg)
            self._push_log_event(error_msg, "ERROR")
            return False
        except Exception as e:
            # 其他未知错误
            error_msg = f"启动虚拟网关失败（未知错误）: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            self._push_log_event(error_msg, "ERROR")
            return False

    def stop_virtual_gateway(self) -> bool:
        """
        停止虚拟网关

        Returns:
            是否停止成功
        """
        try:
            if self.virtual_gateway:
                self.virtual_gateway.close()
                self.logger.info("虚拟网关已停止")
            return True

        except Exception as e:
            self.logger.error("停止虚拟网关失败: %s", e)
            return False

    # ==================== 数据读取器管理方法 ====================

    def read_tdx_data(
        self,
        symbols: List[str],
        data_type: str = "day",
        market: str = "sh",
    ) -> Dict[str, bool]:
        """
        读取通达信本地数据并保存

        Args:
            symbols: 品种代码列表
            data_type: 数据类型（'day', '5min', '1min'）
            market: 市场代码（'sh', 'sz', 'bj'）

        Returns:
            品种代码到处理结果的映射字典
        """
        try:
            # 初始化读取器（如果尚未初始化）
            if self.tdx_reader is None:
                self.tdx_reader = TdxBinaryReader()

            # 批量处理
            results = self.tdx_reader.process_batch(
                symbols=symbols, data_type=data_type, market=market
            )

            success_count = sum(1 for v in results.values() if v)
            self.logger.info("读取通达信数据完成: %d/%d 成功", success_count, len(symbols))
            self._push_log_event(f"读取通达信数据完成: {success_count}/{len(symbols)} 成功")

            return results

        except Exception as e:
            self.logger.error("读取通达信数据失败: %s", e)
            self._push_log_event(f"读取通达信数据失败: {e}", "ERROR")
            return {symbol: False for symbol in symbols}

    # ==================== 数据感知管理方法 ====================

    def _start_data_sensing_async(self) -> None:
        """启动数据感知（后台线程，不阻塞初始化）"""

        def scan_in_background():
            try:
                self.logger.info("【后台线程】开始数据质量扫描...")

                # 获取参考品种列表
                reference_symbols = []
                all_stocks_dict = self.stock_fetcher.get_all_market_stocks()
                if all_stocks_dict:
                    for stocks in all_stocks_dict.values():
                        # stocks现在是一个字典列表，提取code
                        # 🚀 兼容性处理：如果stocks是字符串列表，直接使用
                        if stocks and isinstance(stocks[0], str):
                            stock_codes = stocks
                        else:
                            stock_codes = [stock["code"] for stock in stocks]
                        reference_symbols.extend(stock_codes)

                # 执行全量扫描
                overview = self.data_sensor.scan_all_data(
                    reference_symbols=reference_symbols,
                    force_refresh=True,
                )

                self.logger.info(
                    "【后台线程】数据质量扫描完成: 评分=%s, 缺失=%s, 错误=%s",
                    overview.quality_score,
                    overview.missing_symbols,
                    overview.error_symbols,
                )

                # 启动文件监控
                self._start_data_file_watcher()

            except Exception as e:
                self.logger.error("【后台线程】数据质量扫描失败: %s", e, exc_info=True)

        # 启动守护线程
        scan_thread = threading.Thread(
            target=scan_in_background,
            daemon=True,
            name="DataSensingScanThread",
        )
        scan_thread.start()
        self.logger.info("数据感知后台扫描线程已启动")

    def _start_data_file_watcher(self) -> bool:
        """启动数据文件监控

        Returns:
            是否启动成功
        """
        try:
            if self.data_file_watcher and self.data_file_watcher.is_running:
                self.logger.warning("数据文件监控已在运行")
                return False

            # 创建文件监控器
            data_dir = config_manager.get_data_dir()
            self.data_file_watcher = DataFileWatcher(
                data_dir=data_dir,
                callback=self.data_sensor.on_file_changed,
            )

            # 启动监控
            success = self.data_file_watcher.start()

            if success:
                self.logger.info("✅ 数据文件监控已启动")
            else:
                self.logger.warning("⚠️ 数据文件监控启动失败（可能是watchdog不可用）")

            return success

        except Exception as e:
            self.logger.error("启动数据文件监控失败: %s", e, exc_info=True)
            return False

    def stop_data_sensing(self) -> bool:
        """停止数据感知

        Returns:
            是否停止成功
        """
        try:
            # 停止文件监控
            if self.data_file_watcher:
                self.data_file_watcher.stop()
                self.data_file_watcher = None
                self.logger.info("数据文件监控已停止")

            return True

        except Exception as e:
            self.logger.error("停止数据感知失败: %s", e)
            return False

    def get_data_quality_overview(self) -> Optional[QualityOverview]:
        """获取数据质量概览

        Returns:
            质量概览（如果尚未扫描则返回None）
        """
        return self.data_sensor.get_quality_overview()

    def get_unified_data_manager(self) -> Optional[UnifiedDataManager]:
        """获取统一数据管理器实例"""
        return self.unified_data_manager

    def trigger_data_quality_scan(self, force_refresh: bool = False) -> Optional[QualityOverview]:
        """手动触发数据质量扫描

        Args:
            force_refresh: 是否强制刷新（忽略缓存）

        Returns:
            质量概览
        """
        try:
            self.logger.info("开始手动数据质量扫描...")

            # 获取参考品种列表
            reference_symbols = []
            all_stocks_dict = self.stock_fetcher.get_all_market_stocks()
            if all_stocks_dict:
                for stocks in all_stocks_dict.values():
                    # stocks现在是一个字典列表，提取code
                    # 🚀 兼容性处理：如果stocks是字符串列表，直接使用
                    if stocks and isinstance(stocks[0], str):
                        stock_codes = stocks
                    else:
                        stock_codes = [stock["code"] for stock in stocks]
                    reference_symbols.extend(stock_codes)

            # 执行扫描
            overview = self.data_sensor.scan_all_data(
                reference_symbols=reference_symbols,
                force_refresh=force_refresh,
            )

            self.logger.info("手动数据质量扫描完成")
            return overview

        except Exception as e:
            self.logger.error("手动数据质量扫描失败: %s", e, exc_info=True)
            return None

    def scan_corrupted_files(self, auto_delete: bool = False) -> Dict[str, List[str]]:
        """扫描并修复损坏的Parquet文件

        Args:
            auto_delete: 是否自动删除损坏文件

        Returns:
            损坏文件报告 {"corrupted": [...], "deleted": [...]}
        """
        try:
            self.logger.info("开始扫描损坏的Parquet文件（auto_delete=%s）...", auto_delete)

            result = self.storage_manager.scan_and_repair_corrupted_files(auto_delete)

            self.logger.info(
                "扫描完成：发现 %d 个损坏文件，已删除 %d 个",
                len(result.get("corrupted", [])),
                len(result.get("deleted", [])),
            )

            # 推送日志事件
            if result.get("corrupted"):
                self._push_log_event(
                    f"发现 {len(result['corrupted'])} 个损坏文件"
                    + (f"，已删除 {len(result['deleted'])} 个" if auto_delete else ""),
                    "WARNING" if not auto_delete else "INFO",
                )

            return result

        except Exception as e:
            self.logger.error("扫描损坏文件失败: %s", e, exc_info=True)
            self._push_log_event(f"扫描损坏文件失败: {e}", "ERROR")
            return {"corrupted": [], "deleted": []}
