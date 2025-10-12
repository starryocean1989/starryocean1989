# -*- coding: utf-8 -*-
"""
主引擎模块

ChinaStockEngine继承vnpy的BaseEngine，集成所有功能模块：
- 品种列表获取和缓存
- K线数据下载（全量和增量）
- 数据存储和查询
- 数据感知和校验
- 文件监控
- 事件推送
"""

import logging
import threading
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Union

from vnpy.event import Event, EventEngine
from vnpy.trader.engine import BaseEngine, MainEngine

from .config import config_manager
from .multiprocess_fetcher import MultiProcessStockFetcher as StockFetcher
from .stock_fetcher import NetworkTimeoutError
from .storage import StorageManager
from .validator import DataValidator, ValidationSummary
from .file_watcher import EventDrivenFileWatcher
from .block_parser import BlockParser
from .polling_gateway import PollingGateway
from .virtual_gateway import VirtualGateway
from .data_readers import TdxBinaryReader


# 事件类型常量
EVENT_CHINASTOCK_LOG = "eChinaStockLog"
EVENT_CHINASTOCK_VALIDATION = "eChinaStockValidation"
EVENT_CHINASTOCK_FILE_CHANGE = "eChinaStockFileChange"
EVENT_CHINASTOCK_DOWNLOAD = "eChinaStockDownload"

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
        self.block_parser = BlockParser(config_manager.get_tdx_dir())
        self.stock_fetcher = StockFetcher(self.block_parser)
        self.storage_manager = StorageManager()
        self.validator = DataValidator()
        self.file_watcher = EventDrivenFileWatcher(event_engine)

        # 新增：轮询网关和虚拟网关
        self.polling_gateway: Optional[PollingGateway] = None
        self.virtual_gateway: Optional[VirtualGateway] = None

        # 新增：数据读取器
        self.tdx_reader: Optional[TdxBinaryReader] = None

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

        self.logger.info("中国A股数据管理引擎初始化完成")

    def close(self) -> None:
        """关闭引擎"""
        try:
            # 停止文件监控
            if self.file_watcher.is_running():
                self.file_watcher.stop()

            # 关闭轮询网关
            if self.polling_gateway:
                self.polling_gateway.close()

            # 关闭虚拟网关
            if self.virtual_gateway:
                self.virtual_gateway.close()

            self.logger.info("中国A股数据管理引擎已关闭")

        except Exception as e:
            self.logger.error(f"关闭引擎失败: {e}")

    def refresh_stock_list(self) -> Optional[Dict[str, List[str]]]:
        """
        读取本地品种缓存

        Returns:
            品种分类字典
        """
        try:
            self.logger.info("读取本地品种缓存...")
            result = self.stock_fetcher.get_all_market_stocks()

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

            # 重新初始化block_parser（如果用户刚配置了通达信路径）
            try:
                tdx_dir = config_manager.get_tdx_dir()
                self.block_parser = BlockParser(tdx_dir)
                self.stock_fetcher.block_parser = self.block_parser
                spblock_status = "可用" if self.block_parser.is_available() else "不可用"
                self.logger.info("BlockParser已重新初始化: spblock.dat %s", spblock_status)
            except Exception as e:
                self.logger.warning(f"重新初始化BlockParser失败: {e}，将继续使用现有实例")

            # 获取所有品种（这里可能会超时）
            try:
                stocks_df = self.stock_fetcher.fetch_all_stocks()
            except (NetworkTimeoutError, TimeoutError) as e:
                self.logger.error(f"获取品种列表超时: {e}")
                self._push_download_event("stock_list", "error", 0, "网络请求超时，请检查网络连接")
                self._push_log_event("获取品种列表超时，请检查网络连接", "ERROR")
                return False
            except ConnectionError as e:
                self.logger.error(f"网络连接失败: {e}")
                self._push_download_event("stock_list", "error", 0, "网络连接失败，请检查网络状态")
                self._push_log_event("网络连接失败，请检查网络状态", "ERROR")
                return False
            except ValueError as e:
                self.logger.error(f"数据格式错误: {e}")
                self._push_download_event("stock_list", "error", 0, "数据格式错误")
                self._push_log_event(f"数据格式错误: {e}", "ERROR")
                return False
            except Exception as e:
                self.logger.error(f"获取品种列表失败: {e}", exc_info=True)
                self._push_download_event("stock_list", "error", 0, str(e))
                self._push_log_event(f"获取品种列表失败: {e}", "ERROR")
                return False

            # 验证数据
            if stocks_df is None or stocks_df.empty:
                self.logger.error("获取品种列表失败: 数据为空")
                self._push_download_event("stock_list", "error", 0, "获取的数据为空")
                self._push_log_event("获取品种列表失败: 数据为空", "ERROR")
                return False

            # 缓存品种列表
            try:
                self.stock_fetcher.cache_stock_list(stocks_df)
            except Exception as e:
                self.logger.error(f"缓存品种列表失败: {e}")
                # 即使缓存失败，也认为更新成功（因为已经获取到数据）
                self.logger.warning("缓存失败但数据已获取，继续执行")

            # 推送下载事件
            self._push_download_event("stock_list", "success", len(stocks_df))
            self._push_log_event(f"品种列表更新成功: {len(stocks_df)} 个品种")

            return True

        except Exception as e:
            # 最外层兜底异常处理
            self.logger.error(f"更新品种列表失败（未知错误）: {e}", exc_info=True)
            self._push_download_event("stock_list", "error", 0, f"未知错误: {str(e)}")
            self._push_log_event(f"更新品种列表失败: {e}", "ERROR")
            return False

    def download_full(self, market_types: Optional[List[str]] = None) -> bool:
        """
        全量下载K线数据

        Args:
            market_types: 市场类型列表，默认下载所有类型

        Returns:
            是否下载成功
        """
        try:
            if market_types is None:
                market_types = ["上证A股", "深证A股", "北证A股", "T+0基金", "含可转债"]

            self.logger.info(f"开始全量下载K线数据: {market_types}")

            # 获取所有品种（仅使用本地缓存，不允许重新获取）
            all_stocks = []
            for market_type in market_types:
                stocks = self.stock_fetcher.get_market_stocks(market_type, allow_fetch=False)
                all_stocks.extend(stocks)

            if not all_stocks:
                error_msg = "本地品种缓存不存在或为空，请先在【品种列表】界面点击【重新加载品种】按钮获取品种列表"
                self.logger.error(error_msg)
                self._push_download_event("full_kline", "error", 0, error_msg)
                self._push_log_event(error_msg, "ERROR")
                return False

            # 下载K线数据
            download_results = self.stock_fetcher.download_full_kline(all_stocks)

            # 保存数据
            saved_count = 0
            for key, data in download_results.items():
                symbol, interval = key.split("_", 1)
                file_path = self.storage_manager.save_kline(symbol, interval, data)
                if file_path:
                    saved_count += 1

            # 推送下载事件
            self._push_download_event("full_kline", "success", saved_count)
            self._push_log_event(f"全量下载完成: {saved_count} 个数据集")

            return True

        except Exception as e:
            self.logger.error(f"全量下载失败: {e}")
            self._push_download_event("full_kline", "error", 0, str(e))
            self._push_log_event(f"全量下载失败: {e}", "ERROR")
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
                market_types = ["上证A股", "深证A股", "北证A股", "T+0基金", "含可转债"]

            self.logger.info(f"开始增量下载K线数据: 从 {start_date} 开始")

            # 获取所有品种（仅使用本地缓存，不允许重新获取）
            all_stocks = []
            for market_type in market_types:
                stocks = self.stock_fetcher.get_market_stocks(market_type, allow_fetch=False)
                all_stocks.extend(stocks)

            if not all_stocks:
                error_msg = "本地品种缓存不存在或为空，请先在【品种列表】界面点击【重新加载品种】按钮获取品种列表"
                self.logger.error(error_msg)
                self._push_download_event("incremental_kline", "error", 0, error_msg)
                self._push_log_event(error_msg, "ERROR")
                return

            # 定义进度回调函数
            def progress_callback(completed: int, total: int, symbol: str, interval: str):
                """进度回调：通过事件推送进度"""
                progress_pct = (completed / total) * 100
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
            for key, data in download_results.items():
                symbol, interval = key.split("_", 1)
                success = self.storage_manager.merge_data(symbol, interval, data)
                if success:
                    saved_count += 1

            # 推送下载事件
            self._push_download_event("incremental_kline", "success", saved_count)
            self._push_log_event(f"增量下载完成: {saved_count} 个数据集")

        except Exception as e:
            self.logger.error(f"增量下载失败: {e}", exc_info=True)
            self._push_download_event("incremental_kline", "error", 0, str(e))
            self._push_log_event(f"增量下载失败: {e}", "ERROR")

    def query_data(
        self,
        symbol: str,
        interval: str,
        start_date: Optional[Union[str, date]] = None,
        end_date: Optional[Union[str, date]] = None,
    ) -> Optional[Any]:
        """
        查询数据

        Args:
            symbol: 品种代码
            interval: K线周期
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            查询结果
        """
        try:
            data = self.storage_manager.query_kline(symbol, interval, start_date, end_date)

            if data is not None:
                self.logger.info(f"查询数据成功: {symbol} {interval}, {len(data)} 条记录")
            else:
                self.logger.warning(f"未找到数据: {symbol} {interval}")

            return data

        except Exception as e:
            self.logger.error(f"查询数据失败: {symbol} {interval}, {e}")
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

    def get_market_stocks(self, market_type: str) -> List[str]:
        """
        获取指定市场的品种列表

        Args:
            market_type: 市场类型

        Returns:
            品种代码列表
        """
        try:
            return self.stock_fetcher.get_market_stocks(market_type)
        except Exception as e:
            self.logger.error(f"获取 {market_type} 品种列表失败: {e}")
            return []

    def get_all_market_stocks(self) -> Dict[str, List[str]]:
        """
        获取所有市场的品种分类

        Returns:
            所有市场的品种分类字典
        """
        try:
            return self.stock_fetcher.get_all_market_stocks()
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
        """启动文件监控"""
        try:
            if self.file_watcher.start():
                self.logger.info("文件监控启动成功")
            else:
                self.logger.warning("文件监控启动失败")
        except Exception as e:
            self.logger.error(f"启动文件监控失败: {e}")

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
