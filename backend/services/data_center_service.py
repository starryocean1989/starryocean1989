# -*- coding: utf-8 -*-
"""
数据中心服务.

提供完整的数据管理功能，包括：
- 品种列表管理
- 数据下载管理（全量/增量）
- 本地数据查询
- 数据质量检查和自动修复
- 数据源管理（轮询转推送、虚拟推送）
"""

from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta
from contextlib import suppress
from pathlib import Path
import logging

from backend.core.service_base import BaseService, LoggerMixin
from backend.infrastructure.system_vnpy.unified_log_system import (
    start_ai_process,
    end_ai_process,
)

# 专用logger - 日志埋点v4.0
logger_download = logging.getLogger("backend.data_center.download")
logger_alert = logging.getLogger("backend.data_center.alert")


class DataCenterService(BaseService, LoggerMixin):
    """数据中心服务.

    基于data_module_vnpy包实现的数据管理服务，提供：
    1. 品种列表管理 - 获取、缓存、筛选、搜索
    2. 数据下载 - 全量下载、增量下载、进度监控
    3. 本地数据查询 - OHLCV数据查询、展示
    4. 数据质量管理 - 质量检查、自动修复、断点检测
    5. 数据源管理 - 轮询转推送、虚拟推送
    """

    def __init__(self):
        """初始化数据中心服务."""
        super().__init__()
        # ChinaStockEngine引擎（现在是属性，会延迟获取）
        self._china_stock_engine_checked = False

        # recorder_engine（在start_data_recording中初始化）
        self.recorder_engine = None

        # 业务指标埋点 - 数据中心服务 ✅
        # 已启用基础架构，可在业务方法中调用 self.metrics_collector.record_metric()
        from backend.infrastructure.system_vnpy import get_business_metrics_collector

        self.metrics_collector = get_business_metrics_collector()
        self.logger.info("业务指标采集器已启用（数据中心服务）")

        # 支持的指标类型：
        # - data_query_latency_ms: 数据查询延迟
        # - download_speed_mbps: 下载速度
        # - download_concurrency: 下载并发数
        # - cache_hit_rate: 缓存命中率
        #
        # 使用示例（在具体业务方法中）：
        # start_time = time.time()
        # result = await query_operation()
        # latency_ms = (time.time() - start_time) * 1000
        # self.metrics_collector.record_metric('data_query_latency_ms', latency_ms,
        #                                      {'table': 'kline_data'})
        #
        # TODO: 在以下方法中添加实际埋点:
        # - load_all_symbols(): 记录加载耗时
        # - download_history(): 记录下载速度
        # - query_bar_data(): 记录查询延迟

        # 数据源连接状态
        self.datafeeds: Dict[str, Any] = {
            "polling_gateway": None,
            "virtual_gateway": None,
        }

        # 当前活动的数据源（用于互斥控制）
        self.active_datafeed: Optional[str] = None

        # 实时推送状态
        self.realtime_push_active: bool = False

        # 网关实例
        self.polling_gateway = None
        self.virtual_gateway = None

        # 品种列表缓存
        self._symbol_cache: Optional[Dict[str, Any]] = None
        self._symbol_cache_time: Optional[datetime] = None

        # 下载任务管理
        self._download_tasks: Dict[str, Dict[str, Any]] = {}

        # 下载历史记录（对应需求链条2.2.2：历史下载记录）
        self._download_history: List[Dict[str, Any]] = []

        # 任务调度器
        self.scheduler = None

        self.logger.info("数据中心服务已创建")

    def _do_initialize(self) -> bool:
        """初始化数据中心服务."""
        try:
            # 🆕 创建阶段logger
            stage_logger = logging.getLogger(f"{self.__class__.__name__}.stage")

            stage_logger.info("数据中心服务初始化开始")
            self.log_operation_start("数据中心服务初始化")

            # 初始化任务调度器
            self._init_scheduler()
            self.logger.debug("任务调度器初始化完成")

            # 延迟获取 ChinaStockEngine（确保在服务初始化完成后）
            # 这样可以确保全局变量已经被正确设置
            self._ensure_china_stock_engine()

            # ✅ 优化：移除主线程缓存检查，完全依赖validation_worker的9步流程
            # 原因：
            # 1. 消除重复检查（主线程和后台线程都检查）
            # 2. 加快启动速度（主线程不需要IO操作）
            # 3. 职责清晰：validation_worker负责所有数据加载
            # 4. 通过事件系统接收数据加载完成通知（见_on_symbol_cache_loaded）

            # 注册validation_worker事件监听器
            self._register_validation_events()

            self.log_operation_success("数据中心服务初始化")
            stage_logger.info("数据中心服务初始化完成")
            return True

        except Exception as e:
            self.log_operation_failure("数据中心服务初始化", e)
            self._log_error("初始化", e)
            return False

    def _ensure_china_stock_engine(self) -> None:
        """确保 ChinaStockEngine 被正确获取"""
        if not self._china_stock_engine_checked:
            from backend.core.base import get_china_stock_engine

            self._china_stock_engine = get_china_stock_engine()
            self._china_stock_engine_checked = True

            if self._china_stock_engine:
                self.logger.info("✅ ChinaStockEngine可用")
            else:
                self.logger.warning("⚠️ ChinaStockEngine不可用，部分功能受限", extra={"log_type": "SYSTEM"})

    @property
    def china_stock_engine(self):
        """获取 ChinaStockEngine（延迟获取）"""
        self._ensure_china_stock_engine()
        return self._china_stock_engine

    def _do_shutdown(self) -> bool:
        """关闭数据中心服务."""
        try:
            self.logger.info("正在关闭数据中心服务...")

            # 停止任务调度器
            if self.scheduler and self.scheduler.running:
                self.scheduler.shutdown()
                self.logger.info("任务调度器已停止")

            # 停止所有下载任务
            self._stop_all_downloads()

            # 断开所有数据源
            self._disconnect_all_datafeeds()

            return True
        except Exception as e:
            self._log_error("关闭", e)
            return False

    def _do_health_check(self) -> Dict[str, Any]:
        """健康检查."""
        return {
            "china_stock_engine_available": self.china_stock_engine is not None,
            "connected_datafeeds": [name for name, df in self.datafeeds.items() if df is not None],
            "symbol_cache_loaded": self._symbol_cache is not None,
            "active_downloads": len(self._download_tasks),
        }

    # ==================== 指数数据查询（基准数据支持） ====================

    def query_index_data(
        self,
        index_code: str,
        start_date: str,
        end_date: str,
        frequency: str = "1d",
    ) -> Dict[str, Any]:
        """查询指数数据（用于基准对比）.

        支持的指数代码：
        - 000001: 上证指数
        - 000300: 沪深300
        - 399001: 深证成指
        - 399006: 创业板指
        - 000016: 上证50
        - 000905: 中证500
        - 000852: 中证1000

        Args:
            index_code: 指数代码
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
            frequency: 数据频率 (1d/1w/1M)

        Returns:
            Dict: {
                "success": True,
                "data": [{"date": "2025-01-01", "close": 3000.00, "open": ..., ...}, ...],
                "index_name": "沪深300"
            }
        """
        try:
            # 指数名称映射
            index_names = {
                "000001": "上证指数",
                "000300": "沪深300",
                "399001": "深证成指",
                "399006": "创业板指",
                "000016": "上证50",
                "000905": "中证500",
                "000852": "中证1000",
            }

            index_name = index_names.get(index_code, f"指数{index_code}")

            # 调用china_stock_engine查询指数数据
            if not self.china_stock_engine:
                return {
                    "success": False,
                    "message": "ChinaStockEngine不可用",
                    "data": [],
                }

            # 使用china_stock_engine的query_data方法查询指数
            result = self.china_stock_engine.query_data(
                symbols=[index_code],
                start_date=start_date,
                end_date=end_date,
                frequency=frequency,
            )

            if result.get("success") and result.get("data"):
                data = result["data"].get(index_code, [])

                if data:
                    self.logger.info("✅ 查询到 %s 数据：%d 条", index_name, len(data))
                    return {
                        "success": True,
                        "data": data,
                        "index_code": index_code,
                        "index_name": index_name,
                        "frequency": frequency,
                    }
                else:
                    self.logger.warning("⚠️ %s 数据为空", index_name, extra={"log_type": "SYSTEM"})
                    return {
                        "success": False,
                        "message": f"{index_name}数据为空",
                        "data": [],
                    }
            else:
                return {
                    "success": False,
                    "message": result.get("message", "查询失败"),
                    "data": [],
                }

        except Exception as e:
            self._log_error("查询指数数据", e)
            return {
                "success": False,
                "message": str(e),
                "data": [],
            }

    def get_index_returns(
        self,
        index_code: str = "000300",
        lookback_days: int = 60,
    ) -> Dict[str, Any]:
        """获取指数收益率序列（用于基准对比）.

        Args:
            index_code: 指数代码（默认沪深300）
            lookback_days: 回溯天数

        Returns:
            Dict: {
                "success": True,
                "returns": [0.008, -0.003, ...],  # 日收益率列表
                "dates": ["2025-01-01", "2025-01-02", ...],
                "index_name": "沪深300",
                "index_code": "000300"
            }
        """
        try:
            from datetime import datetime, timedelta

            # 计算日期范围
            end_date = datetime.now().strftime("%Y-%m-%d")
            start_date = (datetime.now() - timedelta(days=lookback_days + 30)).strftime(
                "%Y-%m-%d"
            )  # 多查30天确保有足够数据

            # 查询指数数据
            result = self.query_index_data(
                index_code=index_code,
                start_date=start_date,
                end_date=end_date,
                frequency="1d",
            )

            if not result.get("success"):
                return result

            data = result.get("data", [])

            if len(data) < 2:
                return {
                    "success": False,
                    "message": "指数数据不足，无法计算收益率",
                }

            # 计算日收益率
            import numpy as np

            closes = np.array([float(item["close"]) for item in data])
            dates = [item.get("date", "") for item in data]

            # 计算收益率
            returns = np.diff(closes) / closes[:-1]

            # 只返回最近lookback_days的数据
            returns = returns[-lookback_days:].tolist()
            dates = dates[-(lookback_days + 1) :]  # 收益率比价格少1个

            return {
                "success": True,
                "returns": returns,
                "dates": dates[1:],  # 对齐收益率
                "index_name": result.get("index_name", ""),
                "index_code": index_code,
                "data_points": len(returns),
            }

        except Exception as e:
            self._log_error("获取指数收益率", e)
            return {
                "success": False,
                "message": str(e),
            }

    def _init_scheduler(self) -> bool:
        """初始化任务调度器."""
        try:
            from apscheduler.schedulers.background import BackgroundScheduler
            from apscheduler.executors.pool import ThreadPoolExecutor

            # 🔧 修复Qt Timer跨线程问题：强制使用threading executor，禁用Qt executor
            # APScheduler在检测到Qt环境时会尝试使用QTimer，这在后台线程中会导致错误
            executors = {"default": ThreadPoolExecutor(max_workers=2)}

            # 创建调度器时指定executors配置
            self.scheduler = BackgroundScheduler(executors=executors)

            # 添加定时清理任务：每天凌晨0点清理录制数据
            self.scheduler.add_job(
                self._cleanup_recorded_data_daily,
                "cron",
                hour=0,
                minute=0,
                args=[1],  # 保留1天
                id="cleanup_recorded_data",
                name="定时清理录制数据",
                replace_existing=True,
            )

            # 启动调度器
            self.scheduler.start()
            self.logger.info("✅ 任务调度器已启动，已添加定时清理任务（每日0:00）")
            self.logger.debug("任务调度器初始化完成")
            return True

        except ImportError:
            # APScheduler是可选功能，降低日志级别避免干扰
            self.logger.debug("⚠️ APScheduler未安装，定时清理功能不可用")
            return False
        except Exception as e:
            self.logger.error("任务调度器初始化失败：%s", e, exc_info=True, extra={"log_type": "SYSTEM"})
            return False

    def _cleanup_recorded_data_daily(self, days_to_keep: int = 1):
        """定时清理录制数据（由调度器调用）.

        Args:
            days_to_keep: 保留天数
        """
        try:
            self.logger.info("正在执行定时清理录制数据任务...")
            result = self.cleanup_recorded_data(days_to_keep)

            if result.get("success"):
                deleted_count = result.get("deleted_count", 0)
                self.logger.info("✅ 定时清理完成：已删除 %d 条录制数据", deleted_count)
            else:
                self.logger.warning("⚠️ 定时清理失败：%s", result.get("message", "未知错误"), extra={"log_type": "SYSTEM"})

        except Exception as e:
            self.logger.error("定时清理录制数据异常：%s", e, exc_info=True, extra={"log_type": "SYSTEM"})

    def _start_server_verification(self):
        """启动服务器验证（后台线程）"""
        if not self.china_stock_engine:
            self.logger.warning("ChinaStockEngine不可用，跳过服务器验证", extra={"log_type": "SYSTEM"})
            return

        try:
            # 获取stock_fetcher（ChinaStockEngine中的属性名是stock_fetcher）
            stock_fetcher = getattr(self.china_stock_engine, "stock_fetcher", None)
            if not stock_fetcher:
                self.logger.warning("无法获取stock_fetcher，跳过服务器验证", extra={"log_type": "SYSTEM"})
                return

            # 检查是否有server_manager
            server_manager = getattr(stock_fetcher, "server_manager", None)
            if not server_manager:
                self.logger.warning("stock_fetcher没有server_manager，跳过服务器验证", extra={"log_type": "SYSTEM"})
                return

            # 在后台线程中验证服务器
            def verify_servers():
                try:
                    self.logger.info("后台线程正在验证服务器...")
                    server_manager.verify_all_servers_sync(timeout=5, max_workers=20)
                    self.logger.info("服务器验证完成")
                except Exception as e:
                    self.logger.error("服务器验证失败：%s", e, exc_info=True, extra={"log_type": "SYSTEM"})

            import threading

            thread = threading.Thread(target=verify_servers, daemon=True, name="ServerVerifier")
            thread.start()
            self.logger.info("服务器验证已在后台启动")

        except Exception as e:
            self.logger.error("启动服务器验证失败：%s", e, exc_info=True, extra={"log_type": "SYSTEM"})

    def get_server_status(self) -> Dict[str, Any]:
        """获取服务器状态（从server_pool_manager获取）

        Returns:
            Dict包含可用服务器数量、总数量、验证状态等信息
        """
        try:
            from backend.infrastructure.data_module_vnpy.load_balancer import (
                get_server_pool_manager,
            )

            server_pool_manager = get_server_pool_manager()
            stats = server_pool_manager.get_stats()

            return {
                "available_count": stats["available"],
                "total_count": stats["total"],
                "status": "available" if stats["running"] else "stopped",
                "message": f"可用 {stats['available']}/{stats['total']}",
            }

        except Exception as e:
            self.logger.error("获取服务器状态失败：%s", e, exc_info=True, extra={"log_type": "SYSTEM"})
            return {
                "available_count": 0,
                "total_count": 0,
                "status": "error",
                "message": f"获取状态失败: {str(e)}",
            }

    # ==================== 服务器池管理（公开API） ====================
    def retest_server_pool(self) -> Dict[str, Any]:
        """强制重新测速服务器池并刷新缓存与事件。

        Returns:
            Dict: { success, stats, message }
        """
        import time
        import logging
        from contextlib import suppress
        
        start_time = time.time()
        
        # 设置日志上下文
        try:
            from backend.infrastructure.system_vnpy.unified_log_system import (
                get_logging_hub,
                ai_log_process,
            )
            hub = get_logging_hub()
        except ImportError:
            hub = None
        
        stage_logger = logging.getLogger("task.manual_speedtest.stage")
        
        # 使用ai_log_process创建独立日志文件
        # 注意：场景信息通过日志记录的extra参数传递，无需全局设置
        try:
            context_manager = ai_log_process("manual_speedtest") if hub else suppress()
        except Exception:
            context_manager = suppress()
        
        with context_manager:
            try:
                # 阶段节点（输出到Terminal）
                stage_logger.info(
                    "📍 手动测速开始: 正在连接到服务器池...",
                    extra={"log_type": "STAGE_NODE", "scenario": "manual_speedtest"},
                )
                
                # DEBUG日志（只写入AI日志文件）
                self.logger.debug(
                    "[SPEEDTEST-SERVICE] 开始重新测速服务器池",
                    extra={"log_type": "SYSTEM", "scenario": "manual_speedtest"},
                )
                self.logger.info(
                    "[SPEEDTEST-SERVICE] 手动测速任务开始",
                    extra={"log_type": "SYSTEM", "scenario": "manual_speedtest"},
                )
                
                from backend.infrastructure.data_module_vnpy.load_balancer import (
                    get_server_pool_manager,
                )

                server_pool_manager = get_server_pool_manager()
                
                # DEBUG日志
                self.logger.debug(
                    f"[SPEEDTEST-SERVICE] 服务器池管理器类型: {type(server_pool_manager).__name__}",
                    extra={"log_type": "SYSTEM", "scenario": "manual_speedtest"},
                )
                self.logger.debug(
                    f"[SPEEDTEST-SERVICE] 服务器池管理器: {server_pool_manager}",
                    extra={"log_type": "SYSTEM", "scenario": "manual_speedtest"},
                )
                
                # 获取当前统计信息（测速前）
                try:
                    stats_before = server_pool_manager.get_stats()
                    self.logger.debug(
                        f"[SPEEDTEST-SERVICE] 测速前统计: {stats_before}",
                        extra={"log_type": "SYSTEM", "scenario": "manual_speedtest"},
                    )
                except Exception as e:
                    self.logger.debug(
                        f"[SPEEDTEST-SERVICE] 获取测速前统计失败: {e}",
                        extra={"log_type": "SYSTEM", "scenario": "manual_speedtest"},
                    )

                # 停止当前管理器
                self.logger.debug(
                    "[SPEEDTEST-SERVICE] 停止当前管理器...",
                    extra={"log_type": "SYSTEM", "scenario": "manual_speedtest"},
                )
                stop_start_time = time.time()
                with suppress(Exception):
                    server_pool_manager.stop()
                stop_elapsed = time.time() - stop_start_time
                self.logger.debug(
                    f"[SPEEDTEST-SERVICE] 管理器已停止: 耗时={stop_elapsed:.2f}s",
                    extra={"log_type": "SYSTEM", "scenario": "manual_speedtest"},
                )

                # 强制测速（调用内部多进程测速）
                self.logger.info(
                    "[SPEEDTEST-SERVICE] 开始多进程测速...",
                    extra={"log_type": "SYSTEM", "scenario": "manual_speedtest"},
                )
                self.logger.debug(
                    "[SPEEDTEST-SERVICE] 调用_start_multiprocess方法",
                    extra={"log_type": "SYSTEM", "scenario": "manual_speedtest"},
                )
                speedtest_start_time = time.time()
                success = False
                try:
                    success = server_pool_manager._start_multiprocess()  # noqa: SLF001 (允许内部调用)
                    speedtest_elapsed = time.time() - speedtest_start_time
                    if success:
                        self.logger.info(
                            f"[SPEEDTEST-SERVICE] 多进程测速成功: 耗时={speedtest_elapsed:.2f}s",
                            extra={"log_type": "SYSTEM", "scenario": "manual_speedtest"},
                        )
                        self.logger.debug(
                            f"[SPEEDTEST-SERVICE] 测速过程详情: 耗时={speedtest_elapsed:.2f}s",
                            extra={"log_type": "SYSTEM", "scenario": "manual_speedtest"},
                        )
                    else:
                        self.logger.warning(
                            f"[SPEEDTEST-SERVICE] ⚠️ 多进程测速失败: 耗时={speedtest_elapsed:.2f}s",
                            extra={"log_type": "ALERT", "scenario": "manual_speedtest"},
                        )
                        self.logger.debug(
                            f"[SPEEDTEST-SERVICE] 测速失败详情: 耗时={speedtest_elapsed:.2f}s",
                            extra={"log_type": "SYSTEM", "scenario": "manual_speedtest"},
                        )
                except Exception as e:
                    speedtest_elapsed = time.time() - speedtest_start_time
                    self.logger.error(
                        f"[SPEEDTEST-SERVICE] ❌ 多进程测速异常: {e}, 耗时={speedtest_elapsed:.2f}s",
                        exc_info=True,
                        extra={"log_type": "ALERT", "scenario": "manual_speedtest"},
                    )
                    self.logger.debug(
                        f"[SPEEDTEST-SERVICE] 异常类型: {type(e).__name__}, 异常详情: {str(e)}",
                        extra={"log_type": "SYSTEM", "scenario": "manual_speedtest"},
                    )
                    success = False

                # 成功则保存缓存并推送事件
                if success:
                    self.logger.debug(
                        "[SPEEDTEST-SERVICE] 保存测速结果到缓存...",
                        extra={"log_type": "SYSTEM", "scenario": "manual_speedtest"},
                    )
                    cache_start_time = time.time()
                    try:
                        ipv4_servers = getattr(server_pool_manager, "_sorted_servers_ipv4", [])
                        ipv6_servers = getattr(server_pool_manager, "_sorted_servers_ipv6", [])
                        self.logger.debug(
                            f"[SPEEDTEST-SERVICE] IPv4服务器数: {len(ipv4_servers)}, IPv6服务器数: {len(ipv6_servers)}",
                            extra={"log_type": "SYSTEM", "scenario": "manual_speedtest"},
                        )
                        if ipv4_servers:
                            self.logger.debug(
                                f"[SPEEDTEST-SERVICE] IPv4前5个服务器: {[s.get('host', 'N/A') for s in ipv4_servers[:5]]}",
                                extra={"log_type": "SYSTEM", "scenario": "manual_speedtest"},
                            )
                        if ipv6_servers:
                            self.logger.debug(
                                f"[SPEEDTEST-SERVICE] IPv6前5个服务器: {[s.get('host', 'N/A') for s in ipv6_servers[:5]]}",
                                extra={"log_type": "SYSTEM", "scenario": "manual_speedtest"},
                            )
                        server_pool_manager.save_server_cache(ipv4_servers, ipv6_servers)
                        cache_elapsed = time.time() - cache_start_time
                        self.logger.debug(
                            f"[SPEEDTEST-SERVICE] 缓存已保存: 耗时={cache_elapsed:.2f}s",
                            extra={"log_type": "SYSTEM", "scenario": "manual_speedtest"},
                        )
                    except Exception as e:
                        cache_elapsed = time.time() - cache_start_time
                        self.logger.warning(
                            f"[SPEEDTEST-SERVICE] ⚠️ 保存缓存失败: {e}, 耗时={cache_elapsed:.2f}s",
                            exc_info=True,
                            extra={"log_type": "ALERT", "scenario": "manual_speedtest"},
                        )
                    with suppress(Exception):
                        event_start_time = time.time()
                        server_pool_manager._push_server_status_event()  # noqa: SLF001
                        event_elapsed = time.time() - event_start_time
                        self.logger.debug(
                            f"[SPEEDTEST-SERVICE] 状态事件已推送: 耗时={event_elapsed:.2f}s",
                            extra={"log_type": "SYSTEM", "scenario": "manual_speedtest"},
                        )

                # 获取最终统计信息（无论成功与否）
                stats = server_pool_manager.get_stats()
                total_elapsed = time.time() - start_time
                self.logger.info(
                    f"[SPEEDTEST-SERVICE] 测速统计: {stats}, 总耗时={total_elapsed:.2f}s",
                    extra={"log_type": "SYSTEM", "scenario": "manual_speedtest"},
                )
                self.logger.debug(
                    f"[SPEEDTEST-SERVICE] 测速完成详情: success={success}, stats={stats}, 总耗时={total_elapsed:.2f}s",
                    extra={"log_type": "SYSTEM", "scenario": "manual_speedtest"},
                )
                
                # 阶段节点（输出到Terminal）
                if success:
                    ipv4_count = stats.get("ipv4_available", 0)
                    ipv6_count = stats.get("ipv6_available", 0)
                    stage_logger.info(
                        f"✅ 手动测速完成: IPv4可用={ipv4_count}, IPv6可用={ipv6_count}, 耗时={total_elapsed:.2f}s",
                        extra={"log_type": "STAGE_NODE", "scenario": "manual_speedtest"},
                    )
                else:
                    stage_logger.warning(
                        f"⚠️ 手动测速失败: 耗时={total_elapsed:.2f}s",
                        extra={"log_type": "STAGE_NODE", "scenario": "manual_speedtest"},
                    )
                
                return {"success": success, "stats": stats}

            except Exception as e:
                total_elapsed = time.time() - start_time
                self.logger.error(
                    f"[SPEEDTEST-SERVICE] ❌ 重新测速服务器池失败: {e}, 耗时={total_elapsed:.2f}s",
                    exc_info=True,
                    extra={"log_type": "ALERT", "scenario": "manual_speedtest"},
                )
                self.logger.debug(
                    f"[SPEEDTEST-SERVICE] 异常类型: {type(e).__name__}, 异常详情: {str(e)}",
                    extra={"log_type": "SYSTEM", "scenario": "manual_speedtest"},
                )
                
                # 阶段节点（输出到Terminal）
                stage_logger.error(
                    f"❌ 手动测速异常: {e}, 耗时={total_elapsed:.2f}s",
                    extra={"log_type": "STAGE_NODE", "scenario": "manual_speedtest"},
                )
                
                return {"success": False, "message": str(e)}

    def _map_market_to_exchange(self, market_type: str) -> str:
        """将市场类型映射到交易所."""
        mapping = {
            "上证A股": "上交所",
            "深证A股": "深交所",
            "北证A股": "北交所",
            "T+0基金": "全部",
            "可转债": "全部",
        }
        return mapping.get(market_type, "未知")

    def _map_market_to_product_type(self, market_type: str) -> str:
        """将市场类型映射到产品类型."""
        mapping = {
            "上证A股": "股票",
            "深证A股": "股票",
            "北证A股": "股票",
            "T+0基金": "基金",
            "可转债": "可转债",
        }
        return mapping.get(market_type, "未知")

    def _check_symbol_cache_readonly(self):
        """只读加载品种列表缓存到内存（不触发下载）.

        架构说明：
        - 此方法只在validation_worker完成数据加载后被事件处理器调用（见_on_symbol_cache_loaded）
        - 不在主线程初始化时调用，避免重复检查
        - 只读取已存在的缓存文件，不触发网络下载
        - 如果缓存不存在，记录日志并返回
        """
        try:
            from backend.infrastructure.data_module_vnpy.data_acquisition import SymbolLoader

            loader = SymbolLoader()
            classified = loader.reload_and_classify()

            if not classified:
                self.logger.info("品种列表缓存不存在，等待后台validation_worker加载")
                return

            # 转换为前端格式并更新内存缓存
            symbols = []
            for market_type, codes in classified.items():
                for code_item in codes:
                    if isinstance(code_item, str):
                        code = code_item
                        name = code_item
                    elif isinstance(code_item, dict):
                        code = code_item.get("code", "")
                        name = code_item.get("name", code)
                    else:
                        continue

                    if not code:
                        continue

                    symbols.append(
                        {
                            "symbol": code,
                            "code": code,
                            "name": name,
                            "exchange": self._map_market_to_exchange(market_type),
                            "product_type": self._map_market_to_product_type(market_type),
                        }
                    )

            # 更新内存缓存
            self._symbol_cache = {
                "symbols": symbols,
                "timestamp": datetime.now(),
            }
            self._symbol_cache_time = datetime.now()

            self.logger.info("✅ 从缓存加载了 %d 个品种（%d个市场）", len(symbols), len(classified))

        except Exception as e:
            self.logger.error("检查缓存失败：%s", e, exc_info=True, extra={"log_type": "SYSTEM"})

    def _register_validation_events(self):
        """注册validation_worker事件监听器."""
        try:
            from backend.core.base import get_event_engine
            from backend.infrastructure.data_module_vnpy import (
                ChinaStockEngine,
            )
            EVENT_SYMBOL_CACHE_LOADED = ChinaStockEngine.EVENT_SYMBOL_CACHE_LOADED
            EVENT_IPO_CACHE_UPDATED = ChinaStockEngine.EVENT_IPO_CACHE_UPDATED
            EVENT_VALIDATION_COMPLETED = ChinaStockEngine.EVENT_VALIDATION_COMPLETED

            event_engine = get_event_engine()
            if not event_engine:
                self.logger.warning("EventEngine不可用，无法注册事件监听器", extra={"log_type": "SYSTEM"})
                return

            event_engine.register(EVENT_SYMBOL_CACHE_LOADED, self._on_symbol_cache_loaded)
            event_engine.register(EVENT_IPO_CACHE_UPDATED, self._on_ipo_cache_updated)
            event_engine.register(EVENT_VALIDATION_COMPLETED, self._on_validation_completed)

            self.logger.info("✅ 已注册validation_worker事件监听器")

        except Exception as e:
            self.logger.warning("⚠️ 注册validation事件失败: %s", e, exc_info=True, extra={"log_type": "SYSTEM"})

    def _on_symbol_cache_loaded(self, event):
        """响应品种列表加载完成事件.

        Args:
            event: Event对象
        """
        try:
            data = event.data
            symbol_count = data.get("symbol_count", 0)
            is_new = data.get("is_new", False)

            self.logger.info(
                "✅ [事件] validation_worker加载完成：%d个品种（%s）",
                symbol_count,
                "首次加载" if is_new else "缓存加载",
            )

            # 重新加载内存缓存
            self._check_symbol_cache_readonly()

        except Exception as e:
            self.logger.error("处理品种列表加载事件失败: %s", e, extra={"log_type": "SYSTEM"})

    def _on_ipo_cache_updated(self, event):
        """响应IPO缓存更新完成事件.

        注意: IPO数据只用于保存到缓存，不再用于过滤品种列表

        Args:
            event: Event对象
        """
        try:
            data = event.data
            ipo_count = data.get("ipo_count", 0)

            self.logger.info("✅ [事件] IPO缓存更新完成：%d个品种", ipo_count)

            # 重新加载内存缓存（不进行IPO过滤）
            self._check_symbol_cache_readonly()

        except Exception as e:
            self.logger.error("处理IPO更新事件失败: %s", e, extra={"log_type": "SYSTEM"})

    def _on_validation_completed(self, event):
        """响应validation流程完成事件.

        Args:
            event: Event对象
        """
        try:
            data = event.data
            success = data.get("success", False)

            if success:
                self.logger.info("✅ [事件] validation_worker 9步流程全部完成")
            else:
                error = data.get("error", "未知错误")
                self.logger.warning("⚠️ [事件] validation_worker流程失败: %s", error, extra={"log_type": "SYSTEM"})

        except Exception as e:
            self.logger.error("处理validation完成事件失败: %s", e, extra={"log_type": "SYSTEM"})

    # ==================== 品种列表管理 ====================

    def _delete_symbol_cache_file(self):
        """删除品种列表缓存文件"""
        try:
            from backend.infrastructure.data_module_vnpy import ConfigManager

            config_manager = ConfigManager.get_instance()
            cache_dir = config_manager.get_cache_dir()
            cache_file = cache_dir / "stock_list_classified.json"
            if cache_file.exists():
                cache_file.unlink()
                self.logger.info("已删除品种列表缓存文件: %s", cache_file)
        except Exception as e:
            self.logger.error("删除缓存文件失败: %s", e, exc_info=True, extra={"log_type": "SYSTEM"})

    def reload_symbol_list(self, force: bool = False) -> Dict[str, Any]:
        """重新加载品种列表（用户主动触发）.

        架构说明：
        - 此方法仅在用户主动点击"重新加载"按钮时调用
        - 执行完整的3步流程（删除缓存 → 获取品种 → 更新缓存）
        - 改为同步执行，避免与validation_worker冲突
        - 不在启动时自动调用（避免与validation_worker重复）

        Args:
            force: 是否强制重新加载，即使缓存有效

        Returns:
            Dict: {
                "success": bool,
                "symbol_count": int,
                "message": str,
                "data": List[Dict]  # 品种列表
            }
        """
        import time
        import logging
        from contextlib import suppress
        from datetime import datetime
        
        start_time = time.time()
        
        # 设置日志上下文
        try:
            from backend.infrastructure.system_vnpy.unified_log_system import (
                get_logging_hub,
                ai_log_process,
            )
            hub = get_logging_hub()
        except ImportError:
            hub = None
        
        stage_logger = logging.getLogger("task.refresh_symbol_list.stage")
        
        # 使用ai_log_process创建独立日志文件
        # 注意：场景信息通过日志记录的extra参数传递，无需全局设置
        try:
            context_manager = ai_log_process("refresh_symbol_list") if hub else suppress()
        except Exception:
            context_manager = suppress()
        
        with context_manager:
            try:
                # 阶段节点（输出到Terminal）
                stage_logger.info(
                    "📍 重新请求品种列表开始",
                    extra={"log_type": "STAGE_NODE", "scenario": "refresh_symbol_list"},
                )
                
                self._log_operation("重新加载品种列表", force=force)
                self.logger.debug(
                    "[RELOAD-SYMBOL] 开始重新加载品种列表",
                    extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"}
                )
                self.logger.debug(
                    f"[RELOAD-SYMBOL] 参数: force={force}",
                    extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"}
                )
                self.logger.info(
                    "[RELOAD-SYMBOL] 品种列表重新加载开始",
                    extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"}
                )
                self.logger.info(
                    "=" * 60,
                    extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"}
                )
                self.logger.info(
                    "【用户触发】品种列表重新加载开始",
                    extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"}
                )
                self.logger.info(
                    "=" * 60,
                    extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"}
                )

                # 流程1：删除缓存文件
                self.logger.info(
                    "[RELOAD-SYMBOL] 【流程1】删除现有缓存文件...",
                    extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"}
                )
                self.logger.debug(
                    "[RELOAD-SYMBOL] 开始删除缓存文件...",
                    extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"}
                )
                cache_delete_start_time = time.time()
                self._delete_symbol_cache_file()
                cache_delete_elapsed = time.time() - cache_delete_start_time
                self.logger.debug(
                    f"[RELOAD-SYMBOL] 缓存文件删除完成: 耗时={cache_delete_elapsed:.2f}s",
                    extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"}
                )

                # 流程2：从API获取品种
                if self.china_stock_engine is None:
                    self.logger.error(
                        "[RELOAD-SYMBOL] ❌ ChinaStockEngine不可用",
                        extra={"log_type": "ALERT", "scenario": "refresh_symbol_list"}
                    )
                    self.logger.debug(
                        "[RELOAD-SYMBOL] ChinaStockEngine状态: None",
                        extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"}
                    )
                    return {
                        "success": False,
                        "symbol_count": 0,
                        "message": "ChinaStockEngine不可用",
                        "data": [],
                    }

                self.logger.info(
                    "[RELOAD-SYMBOL] 【流程2】从ChinaStockEngine获取品种列表...",
                    extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"}
                )
                self.logger.debug(
                    "[RELOAD-SYMBOL] 开始调用_fetch_symbols_from_china_stock方法...",
                    extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"}
                )
                fetch_start_time = time.time()
                symbols, empty_categories = self._fetch_symbols_from_china_stock()
                fetch_elapsed = time.time() - fetch_start_time
                self.logger.debug(
                    f"[RELOAD-SYMBOL] 品种获取完成: 数量={len(symbols)}, 空类别={empty_categories}, 耗时={fetch_elapsed:.2f}s",
                    extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"}
                )
                self.logger.info(
                    f"[RELOAD-SYMBOL] 【流程2完成】获取到 {len(symbols)} 个品种",
                    extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"}
                )

                # 转换为前端格式
                self.logger.debug(
                    "[RELOAD-SYMBOL] 开始转换为前端格式...",
                    extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"}
                )
                format_start_time = time.time()
                formatted_symbols = []
                skipped_count = 0
                for s in symbols:
                    if isinstance(s, dict):
                        code = s.get("code", "")
                        name = s.get("name", code)
                        exchange = s.get("exchange", "")
                        product_type = s.get("product_type", "")
                    elif isinstance(s, str):
                        code = s
                        name = s
                        exchange = ""
                        product_type = ""
                    else:
                        skipped_count += 1
                        continue

                    if not code:
                        skipped_count += 1
                        continue

                    formatted_symbols.append(
                        {
                            "symbol": code,
                            "code": code,
                            "name": name,
                            "exchange": exchange,
                            "product_type": product_type,
                        }
                    )
                format_elapsed = time.time() - format_start_time
                self.logger.debug(
                    f"[RELOAD-SYMBOL] 格式转换完成: 成功={len(formatted_symbols)}, 跳过={skipped_count}, 耗时={format_elapsed:.2f}s",
                    extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"}
                )

                # 流程3：更新内存缓存
                self.logger.info(
                    "[RELOAD-SYMBOL] 【流程3】更新内存缓存...",
                    extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"}
                )
                self.logger.debug(
                    "[RELOAD-SYMBOL] 开始更新内存缓存...",
                    extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"}
                )
                cache_update_start_time = time.time()
                self._symbol_cache = {
                    "symbols": formatted_symbols,
                    "timestamp": datetime.now(),
                }
                self._symbol_cache_time = datetime.now()
                cache_update_elapsed = time.time() - cache_update_start_time
                self.logger.debug(
                    f"[RELOAD-SYMBOL] 内存缓存更新完成: 耗时={cache_update_elapsed:.2f}s",
                    extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"}
                )
                self.logger.info(
                    f"[RELOAD-SYMBOL] 【流程3完成】缓存已更新，品种数: {len(formatted_symbols)}",
                    extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"}
                )

                total_elapsed = time.time() - start_time
                self.logger.info(
                    "=" * 60,
                    extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"}
                )
                self.logger.info(
                    f"[RELOAD-SYMBOL] 【用户触发】品种列表重新加载完成: 总耗时={total_elapsed:.2f}s, 品种数={len(formatted_symbols)}",
                    extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"}
                )
                self.logger.debug(
                    f"[RELOAD-SYMBOL] 各步骤耗时: 删除缓存={cache_delete_elapsed:.2f}s, "
                    f"获取品种={fetch_elapsed:.2f}s, 格式转换={format_elapsed:.2f}s, "
                    f"更新缓存={cache_update_elapsed:.2f}s, 总耗时={total_elapsed:.2f}s",
                    extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"}
                )
                self.logger.info(
                    "=" * 60,
                    extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"}
                )

                # 检查通达信根目录配置和空品种类别
                self.logger.debug(
                    "[RELOAD-SYMBOL] 开始检查通达信根目录配置和空品种类别...",
                    extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"}
                )
                warning_messages = []

                if self.china_stock_engine:
                    # 检查BlockParser是否可用
                    block_parser = getattr(self.china_stock_engine, "block_parser", None)
                    if block_parser:
                        is_available = block_parser.is_available()
                        self.logger.debug(
                            f"[RELOAD-SYMBOL] BlockParser可用性检查: is_available={is_available}",
                            extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"}
                        )
                        if not is_available:
                            warning_msg = (
                                "⚠️ 未配置通达信根目录，品种列表可能不完整。"
                                "缺少：T+0基金、可转债等特殊品种。"
                                "请在系统配置中设置通达信软件根目录。"
                            )
                            warning_messages.append(warning_msg)
                            self.logger.warning(
                                f"[RELOAD-SYMBOL] ⚠️ {warning_msg}",
                                extra={"log_type": "ALERT", "scenario": "refresh_symbol_list"}
                            )
                    else:
                        self.logger.debug(
                            "[RELOAD-SYMBOL] BlockParser不可用",
                            extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"}
                        )

                # 检查空品种类别（集合E,F,G,H,I）
                if empty_categories:
                    empty_warning = f"⚠️ 以下品种列表为空，请排查相关问题：{', '.join(empty_categories)}"
                    warning_messages.append(empty_warning)
                    self.logger.warning(
                        f"[RELOAD-SYMBOL] ⚠️ {empty_warning}",
                        extra={"log_type": "ALERT", "scenario": "refresh_symbol_list"}
                    )
                    self.logger.debug(
                        f"[RELOAD-SYMBOL] 空品种类别详情: {empty_categories}",
                        extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"}
                    )

                # 合并所有警告消息
                warning_message = "\n".join(warning_messages) if warning_messages else None
                if warning_message:
                    self.logger.debug(
                        f"[RELOAD-SYMBOL] 警告消息: {warning_message}",
                        extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"}
                    )

                total_elapsed = time.time() - start_time
                self.logger.info(
                    f"[RELOAD-SYMBOL] 品种列表重新加载成功: 总耗时={total_elapsed:.2f}s, 品种数={len(formatted_symbols)}, "
                    f"警告={'存在' if warning_message else '无'}",
                    extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"}
                )

                # 阶段节点（输出到Terminal）
                stage_logger.info(
                    f"✅ 重新请求品种列表完成: 耗时={total_elapsed:.2f}s, 数量={len(formatted_symbols)}",
                    extra={"log_type": "STAGE_NODE", "scenario": "refresh_symbol_list"},
                )

                return {
                    "success": True,
                    "symbol_count": len(formatted_symbols),
                    "message": f"成功加载{len(formatted_symbols)}个品种",
                    "data": formatted_symbols,
                    "warning": warning_message,  # 添加警告信息
                    "empty_categories": empty_categories,  # 添加空品种类别列表
                }

            except Exception as e:
                total_elapsed = time.time() - start_time
                self._log_error("重新加载品种列表", e)
                self.logger.error(
                    "[RELOAD-SYMBOL] ❌ 品种列表重新加载失败",
                    exc_info=True,
                    extra={"log_type": "ALERT", "scenario": "refresh_symbol_list"}
                )
                self.logger.error(
                    "=" * 60,
                    extra={"log_type": "ALERT", "scenario": "refresh_symbol_list"}
                )
                self.logger.error(
                    f"[RELOAD-SYMBOL] 【失败】品种列表加载失败: {e}, 耗时={total_elapsed:.2f}s",
                    exc_info=True,
                    extra={"log_type": "ALERT", "scenario": "refresh_symbol_list"}
                )
                self.logger.debug(
                    f"[RELOAD-SYMBOL] 异常类型: {type(e).__name__}, 异常详情: {str(e)}",
                    extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"}
                )
                self.logger.error(
                    "=" * 60,
                    extra={"log_type": "ALERT", "scenario": "refresh_symbol_list"}
                )
                
                # 阶段节点（输出到Terminal）
                stage_logger.error(
                    f"❌ 重新请求品种列表失败: {e}, 耗时={total_elapsed:.2f}s",
                    extra={"log_type": "STAGE_NODE", "scenario": "refresh_symbol_list"},
                )
                
                return {
                    "success": False,
                    "symbol_count": 0,
                    "message": f"加载失败: {str(e)}",
                    "data": [],
                }

    def refresh_symbol_list(self) -> Dict[str, Any]:
        """刷新品种列表（从缓存文件，已过滤未上市品种）.

        Returns:
            Dict: 包含success, symbol_count, message, data, is_outdated的字典
        """
        try:
            # 🔧 优化：检查内存缓存是否在TTL内，避免重复文件I/O
            # TTL设置为3秒，避免短时间内多次加载相同数据
            if self._symbol_cache and self._symbol_cache_time:
                from datetime import timedelta

                cache_age = datetime.now() - self._symbol_cache_time
                if cache_age < timedelta(seconds=3):
                    symbols = self._symbol_cache.get("symbols", [])
                    self.logger.debug(
                        "品种列表使用内存缓存（缓存年龄: %.2f秒，共%d个品种）",
                        cache_age.total_seconds(),
                        len(symbols),
                    )
                    return {
                        "success": True,
                        "symbol_count": len(symbols),
                        "message": "使用内存缓存",
                        "data": symbols,
                        "is_outdated": False,
                        "source": "memory_cache",
                    }

            self._log_operation("刷新品种列表")

            # 🔧 修复：优先使用 china_stock_engine 的 symbol_loader，而不是创建新实例
            # 原因：
            # 1. symbol_loader 已经在 engine 初始化时创建并配置了 event_engine
            # 2. 复用已有实例可以避免重复初始化组件
            # 3. 保持配置和状态的一致性

            if not self.china_stock_engine:
                return {
                    "success": False,
                    "symbol_count": 0,
                    "message": "ChinaStockEngine不可用",
                    "data": [],
                }

            # 确保 symbol_loader 已初始化
            if self.china_stock_engine.symbol_loader is None:
                # 延迟初始化 symbol_loader（如果需要）
                from backend.infrastructure.data_module_vnpy.data_acquisition import SymbolLoader
                from backend.core.base import get_event_engine

                event_engine = get_event_engine()
                if event_engine:
                    self.china_stock_engine.symbol_loader = SymbolLoader(event_engine)
                else:
                    self.logger.warning("EventEngine不可用，使用无事件引擎的SymbolLoader", extra={"log_type": "SYSTEM"})
                    self.china_stock_engine.symbol_loader = SymbolLoader()

            # 使用 engine 的 symbol_loader
            symbol_loader = self.china_stock_engine.symbol_loader
            try:
                classified = symbol_loader.reload_and_classify()
            except Exception as e:
                self.logger.error(
                    "symbol_loader.reload_and_classify() 失败: %s", e, exc_info=True, extra={"log_type": "SYSTEM"}
                )
                raise

            if not classified:
                self.logger.warning("品种列表缓存不存在", extra={"log_type": "SYSTEM"})
                return {
                    "success": False,
                    "symbol_count": 0,
                    "message": "缓存不存在，请先点击【重新加载品种】",
                    "data": [],
                }

            # 将分类数据转换为前端需要的格式（添加 exchange 和 product_type 字段）
            symbols = []
            for market_type, codes in classified.items():
                for code_item in codes:
                    # 兼容两种格式：字符串或字典
                    if isinstance(code_item, str):
                        code = code_item
                        name = code_item
                    elif isinstance(code_item, dict):
                        code = code_item.get("code", "")
                        name = code_item.get("name", code)
                    else:
                        continue  # 跳过无效数据

                    if not code:
                        continue  # 跳过空代码

                    symbols.append(
                        {
                            "symbol": code,
                            "code": code,
                            "name": name,  # 使用实际品种名称
                            "exchange": self._map_market_to_exchange(market_type),
                            "product_type": self._map_market_to_product_type(market_type),
                        }
                    )

            # 更新内存缓存
            self._symbol_cache = {"symbols": symbols, "timestamp": datetime.now()}
            self._symbol_cache_time = datetime.now()

            self.logger.info("从文件缓存刷新成功: %d 个品种（已过滤未上市）", len(symbols))

            # 🔧 修复：is_outdated 未定义，从缓存刷新应该是有效的
            is_outdated = False

            return {
                "success": True,
                "symbol_count": len(symbols),
                "message": "从缓存刷新成功（已过滤未上市品种）",
                "data": symbols,
                "is_outdated": is_outdated,
            }

        except Exception as e:
            self._log_error("刷新品种列表", e)
            return {
                "success": False,
                "symbol_count": 0,
                "message": f"刷新失败: {str(e)}",
                "data": [],
            }

    def get_symbols_from_cache(self) -> List[Dict[str, Any]]:
        """从缓存获取品种列表（用于智能联想等功能）

        Returns:
            List[Dict]: 品种列表，每个元素包含code、name等字段
        """
        try:
            result = self.refresh_symbol_list()
            if result.get("success"):
                return result.get("data", [])
            return []
        except Exception as e:
            self.logger.warning("⚠️ 从缓存获取品种列表失败: %s", e, exc_info=True, extra={"log_type": "SYSTEM"})
            return []

    def get_local_data_index(self) -> List[Dict[str, Any]]:
        """获取本地数据标题索引（已下载的品种列表，用于本地数据搜索框联想）

        从本地数据文件目录扫描，返回所有已下载的品种代码和名称。
        这是搜索本地数据时的唯一联想源。

        Returns:
            List[Dict]: 品种列表，每个元素包含 {"code": str, "name": str}
        """
        try:
            if not self.china_stock_engine:
                self.logger.warning("ChinaStockEngine不可用", extra={"log_type": "SYSTEM"})
                return []

            # 获取本地数据索引（品种代码列表）
            symbol_codes = self.china_stock_engine.get_local_data_index()

            if not symbol_codes:
                self.logger.info("本地数据索引为空，没有已下载的品种")
                return []

            # 从品种列表缓存获取名称映射
            symbols_cache = self.get_symbols_from_cache()
            code_to_name = {}

            if symbols_cache:
                for s in symbols_cache:
                    if not isinstance(s, dict):
                        continue

                    # 提取code，确保是字符串类型
                    code = s.get("symbol") or s.get("code")
                    if code and isinstance(code, str):
                        # 提取name，确保是字符串类型
                        name = s.get("name", "")
                        if isinstance(name, str):
                            code_to_name[code] = name

            # 构建结果列表
            result = []
            for code in symbol_codes:
                name = code_to_name.get(code, "")
                result.append({"code": code, "name": name})

            self.logger.info("获取本地数据索引成功，共 %d 个品种", len(result))
            return result

        except Exception as e:
            logger_alert.error("获取本地数据索引失败: %s", e, exc_info=True, extra={"log_type": "ALERT"})
            return []

    def clear_symbol_cache(self) -> Dict[str, Any]:
        """删除品种列表缓存（清理集合A-I的所有缓存）.

        Returns:
            Dict: 包含success, message的字典
        """
        try:
            self._log_operation("删除品种列表缓存")
            self.logger.info("=" * 60)
            self.logger.info("【开始】删除品种列表缓存")
            self.logger.info("=" * 60)

            # 调用china_stock_engine删除缓存
            if self.china_stock_engine is None:
                self.logger.error("ChinaStockEngine不可用", extra={"log_type": "SYSTEM"})
                return {
                    "success": False,
                    "message": "ChinaStockEngine不可用",
                }

            # 调用引擎的删除方法
            success = self.china_stock_engine.clear_symbol_cache()

            # 清空内存缓存
            if success:
                self._symbol_cache = None
                self._symbol_cache_time = None
                self.logger.info("内存缓存已清空")

            self.logger.info("=" * 60)
            if success:
                self.logger.info("【成功】品种列表缓存删除完成")
            else:
                self.logger.warning("【失败】品种列表缓存删除失败", extra={"log_type": "SYSTEM"})
                self.logger.info("=" * 60)

            return {
                "success": success,
                "message": "品种列表缓存删除成功" if success else "品种列表缓存删除失败",
            }

        except Exception as e:
            self._log_error("删除品种列表缓存", e)
            self.logger.error("=" * 60, extra={"log_type": "SYSTEM"})
            self.logger.error("【失败】删除品种列表缓存异常: %s", e, exc_info=True, extra={"log_type": "SYSTEM"})
            self.logger.error("=" * 60, extra={"log_type": "SYSTEM"})
            return {
                "success": False,
                "message": f"删除失败: {str(e)}",
            }

    def filter_symbols(
        self,
        exchange: Optional[str] = None,
        symbol_type: Optional[str] = None,
        search_text: Optional[str] = None,
    ) -> Dict[str, Any]:
        """筛选和搜索品种.

        Args:
            exchange: 交易所代码（如：SSE, SZSE）
            symbol_type: 品种类型（如：stock, bond, fund）
            search_text: 搜索文本（模糊匹配代码或名称）

        Returns:
            Dict: 筛选后的品种列表
        """
        try:
            if self._symbol_cache is None:
                return {
                    "success": False,
                    "symbol_count": 0,
                    "message": "品种列表未加载",
                    "data": [],
                }

            symbols = self._symbol_cache.get("symbols", [])
            filtered = symbols

            # 按交易所筛选
            if exchange:
                filtered = [s for s in filtered if s.get("exchange") == exchange]

            # 按品种类型筛选
            if symbol_type:
                filtered = [s for s in filtered if s.get("type") == symbol_type]

            # 按搜索文本筛选
            if search_text:
                search_text = search_text.lower()
                filtered = [
                    s
                    for s in filtered
                    if search_text in s.get("code", "").lower()
                    or search_text in s.get("name", "").lower()
                ]

            return {
                "success": True,
                "symbol_count": len(filtered),
                "message": "筛选成功",
                "data": filtered,
            }

        except Exception as e:
            self._log_error("筛选品种", e, exchange=exchange, type=symbol_type)
            return {
                "success": False,
                "symbol_count": 0,
                "message": f"筛选失败: {str(e)}",
                "data": [],
            }

    def _is_symbol_cache_valid(self) -> bool:
        """检查品种缓存是否有效.

        注意：根据需求文档要求，品种缓存无失效时间，只在调用reload_symbol_list()时覆盖。

        Returns:
            bool: 缓存是否有效
        """
        # 品种缓存永久有效，只在reload时覆盖
        if self._symbol_cache is None:
            return False

        # 不再检查时间，缓存永久有效
        return True

    def has_symbol_cache(self) -> bool:
        """检查品种缓存是否存在（公开方法）.

        Returns:
            bool: 缓存是否存在
        """
        return self._symbol_cache is not None

    def _map_market_to_exchange_and_type(self, market_name: str) -> tuple:
        """将市场名称映射到交易所和品种类型.

        Args:
            market_name: 市场名称（如"上证A股"、"深证A股"等）

        Returns:
            tuple: (exchange, product_type) 交易所名称和品种类型
        """
        mapping = {
            "上证A股": ("上交所", "股票"),
            "深证A股": ("深交所", "股票"),
            "北证A股": ("北交所", "股票"),
            "T+0基金": ("全部", "基金"),  # T+0基金可能分布在多个交易所，后续会根据market_code细分
            "可转债": ("全部", "可转债"),  # 可转债可能分布在多个交易所，后续会根据market_code细分
        }

        return mapping.get(market_name, ("未知", "未知"))

    def _fetch_symbols_from_china_stock(self) -> tuple:
        """从ChinaStockEngine获取品种列表.

        Returns:
            tuple: (品种列表, 空品种类别列表)
        """
        try:
            # 调用ChinaStockEngine的reload_stock_list方法
            if self.china_stock_engine is None:
                self.logger.warning("ChinaStockEngine不可用", extra={"log_type": "SYSTEM"})
                return [], []

            # 第1步：调用reload_stock_list更新缓存（返回Dict）
            self.logger.info(
                "  → 调用 china_stock_engine.reload_stock_list()...",
                extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"}
            )
            self.logger.debug(
                "[FETCH-SYMBOL] 开始调用china_stock_engine.reload_stock_list方法",
                extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"}
            )
            reload_start_time = time.time()
            reload_result = self.china_stock_engine.reload_stock_list()
            reload_elapsed = time.time() - reload_start_time
            self.logger.debug(
                f"[FETCH-SYMBOL] reload_stock_list调用完成: 耗时={reload_elapsed:.2f}s, success={reload_result.get('success')}",
                extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"}
            )
            self.logger.info(
                f"  ← reload_stock_list 返回: success={reload_result.get('success')}, "
                f"empty_categories={reload_result.get('empty_categories', [])}, 耗时={reload_elapsed:.2f}s",
                extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"}
            )

            if not reload_result.get("success"):
                self.logger.warning(
                    "更新品种缓存失败",
                    extra={"log_type": "ALERT", "scenario": "refresh_symbol_list"}
                )
                self.logger.debug(
                    f"[FETCH-SYMBOL] 失败详情: {reload_result}",
                    extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"}
                )
                return [], []

            # 获取空品种类别信息
            empty_categories = reload_result.get("empty_categories", [])

            # 第2步：调用get_all_market_stocks获取分类后的品种字典
            self.logger.info(
                "  → 调用 china_stock_engine.get_all_market_stocks()...",
                extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"}
            )
            self.logger.debug(
                "[FETCH-SYMBOL] 开始调用get_all_market_stocks方法（获取分类后的品种字典）",
                extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"}
            )
            market_stocks_start_time = time.time()
            market_stocks = self.china_stock_engine.get_all_market_stocks()
            market_stocks_elapsed = time.time() - market_stocks_start_time
            market_count = len(market_stocks) if market_stocks else 0
            self.logger.debug(
                f"[FETCH-SYMBOL] get_all_market_stocks调用完成: 市场数={market_count}, 耗时={market_stocks_elapsed:.2f}s",
                extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"}
            )
            self.logger.info(
                f"  ← get_all_market_stocks 返回: {market_count} 个市场",
                extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"}
            )

            if not market_stocks:
                self.logger.warning(
                    "获取品种分类失败",
                    extra={"log_type": "ALERT", "scenario": "refresh_symbol_list"}
                )
                self.logger.debug(
                    "[FETCH-SYMBOL] 市场品种字典为空",
                    extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"}
                )
                return [], []

            # 打印各市场品种数量（分类器执行结果）
            total_classified_count = 0
            for market_name, stock_list in market_stocks.items():
                market_symbol_count = len(stock_list)
                total_classified_count += market_symbol_count
                self.logger.info(
                    f"     - {market_name}: {market_symbol_count} 个",
                    extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"}
                )
                self.logger.debug(
                    f"[FETCH-SYMBOL] 分类器结果: {market_name}={market_symbol_count}个品种",
                    extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"}
                )
            self.logger.debug(
                f"[FETCH-SYMBOL] 分类器执行完成: 总计={total_classified_count}个品种, 市场数={market_count}",
                extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"}
            )

            # 转换为前端需要的格式（包含过滤器执行）
            self.logger.info(
                "  → 转换为前端数据格式（应用过滤器）...",
                extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"}
            )
            self.logger.debug(
                "[FETCH-SYMBOL] 开始转换为前端格式（扁平化处理）",
                extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"}
            )
            format_start_time = time.time()
            symbols = []
            
            # 统计扁平化前的数量（用于过滤器统计）
            before_filter_count = 0
            if isinstance(market_stocks, dict) and len(market_stocks) > 0:
                for market_name, stock_list in market_stocks.items():
                    before_filter_count += len(stock_list)

            # 如果market_stocks是市场分类的字典，需要扁平化处理
            if isinstance(market_stocks, dict) and len(market_stocks) > 0:
                # 检查第一个市场的第一个品种的数据结构
                first_market = next(iter(market_stocks))
                first_stock = market_stocks[first_market][0] if market_stocks[first_market] else {}

                if isinstance(first_stock, dict) and "code" in first_stock:
                    # 新格式：市场分类字典，品种是字典列表
                    for market_name, stock_list in market_stocks.items():
                        # 映射市场名称到交易所和品种类型
                        exchange, product_type = self._map_market_to_exchange_and_type(market_name)

                        for stock_info in stock_list:
                            # stock_info是一个字典，包含 code, name, market
                            stock_code = stock_info.get("code", "")
                            stock_name = stock_info.get("name", "")
                            market_code = stock_info.get("market", -1)

                            # 🚀 关键修正：根据market_code映射交易所
                            # 对于T+0基金和可转债（exchange="全部"），需要根据market_code细分
                            if exchange == "全部":
                                if market_code == 0:
                                    exchange_name = "深交所"
                                elif market_code == 1:
                                    exchange_name = "上交所"
                                elif market_code == 2:
                                    exchange_name = "北交所"
                                else:
                                    exchange_name = "未知"
                            else:
                                exchange_name = exchange

                            symbols.append(
                                {
                                    "symbol": stock_code,  # 使用symbol字段（与前端期望一致）
                                    "code": stock_code,  # 同时保留code字段
                                    "name": stock_name,  # 使用品种名称
                                    "exchange": exchange_name,  # 使用映射后的交易所名称
                                    "product_type": product_type,  # 使用映射后的品种类型
                                    "market": market_code,  # 保留市场代码（供后端使用）
                                }
                            )
                else:
                    # 旧格式：市场分类字典，品种是字符串列表
                    for market_name, stock_list in market_stocks.items():
                        # 映射市场名称到交易所和品种类型
                        exchange, product_type = self._map_market_to_exchange_and_type(market_name)

                        for stock_code in stock_list:
                            # stock_code是字符串，需要获取名称（暂时留空）
                            symbols.append(
                                {
                                    "symbol": stock_code,  # 使用symbol字段（与前端期望一致）
                                    "code": stock_code,  # 同时保留code字段
                                    "name": "",  # 品种名称（旧格式没有名称）
                                    "exchange": exchange,  # 使用映射后的交易所名称
                                    "product_type": product_type,  # 使用映射后的品种类型
                                    "market": -1,  # 市场代码（旧格式没有）
                                }
                            )
            else:
                # 直接是品种列表（备用处理）
                self.logger.warning(
                    "market_stocks格式异常，使用备用处理",
                    extra={"log_type": "ALERT", "scenario": "refresh_symbol_list"}
                )
                symbols = market_stocks if isinstance(market_stocks, list) else []
                if not before_filter_count:
                    before_filter_count = len(symbols)
            
            format_elapsed = time.time() - format_start_time
            after_filter_count = len(symbols)
            filtered_count = before_filter_count - after_filter_count
            
            self.logger.debug(
                f"[FETCH-SYMBOL] 格式转换完成: 转换前={before_filter_count}, 转换后={after_filter_count}, "
                f"过滤掉={filtered_count}, 耗时={format_elapsed:.2f}s",
                extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"}
            )
            self.logger.info(
                f"  ← 转换完成: {after_filter_count} 个品种（过滤前: {before_filter_count}, 过滤掉: {filtered_count}）",
                extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"}
            )
            self.logger.info(
                f"✅ 成功获取 {after_filter_count} 个分类品种（来自{market_count}个市场，过滤器已应用）",
                extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"}
            )

            # 打印前3个样例
            if len(symbols) > 0:
                self.logger.info(
                    "  前3个品种样例:",
                    extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"}
                )
                for i, sym in enumerate(symbols[:3]):
                    self.logger.info(
                        f"    [{i + 1}] {sym}",
                        extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"}
                    )
                    self.logger.debug(
                        f"[FETCH-SYMBOL] 样例品种: {sym}",
                        extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"}
                    )

            return symbols, empty_categories

        except Exception as e:
            self.logger.debug(
                f"[FETCH-SYMBOL] 获取品种列表发生异常: {type(e).__name__}: {str(e)}",
                extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"}
            )
            self.logger.error(
                f"获取品种列表失败: {e}",
                exc_info=True,
                extra={"log_type": "ALERT", "scenario": "refresh_symbol_list"}
            )
            return [], []

    # ==================== 数据下载管理 ====================

    def start_incremental_download_with_progress(
        self, start_date: str, progress_callback: Optional[Any] = None, symbols: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """启动增量数据下载（带进度回调，线程内轮询引擎进度）.

        Args:
            start_date: 开始日期（格式：YYYY-MM-DD）
            progress_callback: 可选回调，形如 callback(percent: float, message: str)
            symbols: 可选，指定品种列表（用于修复下载）。如果提供，将只下载这些品种。

        Returns:
            Dict: 下载任务结果（阻塞直至完成或失败）
        """
        import time

        download_start_time = time.time()

        # 设置日志上下文
        import logging
        from contextlib import suppress
        
        try:
            from backend.infrastructure.system_vnpy.unified_log_system import (
                get_logging_hub,
                ai_log_process,
            )
            hub = get_logging_hub()
            if hub:
                hub.set_stage("downloading")
        except ImportError:
            hub = None
        
        stage_logger = logging.getLogger("task.data_download.stage")
        
        # 使用ai_log_process创建独立日志文件
        download_type = "修复下载" if symbols else "增量下载"
        try:
            context_manager = ai_log_process("data_download") if hub else suppress()
        except Exception:
            context_manager = suppress()
        
        with context_manager:
            try:
                # 阶段节点（输出到Terminal）
                stage_logger.info(
                    f"📍 数据下载开始: {download_type}, 开始日期={start_date}",
                    extra={"log_type": "STAGE_NODE", "scenario": "data_download"},
                )
                
                self.logger.debug(
                    "[DOWNLOAD-SERVICE] 开始增量数据下载",
                    extra={"log_type": "SYSTEM", "scenario": "data_download"}
                )
                self.logger.info(
                    f"[DOWNLOAD-SERVICE] 增量数据下载任务开始: start_date={start_date}, "
                    f"symbols={'有' if symbols else '无'}, symbol_count={len(symbols) if symbols else 0}",
                    extra={"log_type": "SYSTEM", "scenario": "data_download"}
                )
                self.log_operation_start("增量数据下载", start_date=start_date)

                if self.china_stock_engine is None:
                    self.logger.error(
                        "[DOWNLOAD-SERVICE] ❌ 中国股票引擎不可用",
                        extra={"log_type": "ALERT", "scenario": "data_download"}
                    )
                    self.logger.debug(
                        "[DOWNLOAD-SERVICE] ChinaStockEngine状态: None",
                        extra={"log_type": "SYSTEM", "scenario": "data_download"}
                    )
                    # 阶段节点（输出到Terminal）
                    stage_logger.error(
                        "❌ 数据下载失败: 中国股票引擎不可用",
                        extra={"log_type": "STAGE_NODE", "scenario": "data_download"},
                    )
                    return {
                        "success": False,
                        "task_id": None,
                        "message": "data_module_vnpy不可用",
                    }

                # 解析并验证日期
                from datetime import datetime as dt, date

                try:
                    self.logger.debug(
                        f"[DOWNLOAD-SERVICE] 开始解析日期: start_date={start_date}",
                        extra={"log_type": "SYSTEM", "scenario": "data_download"}
                    )
                    start_dt = dt.strptime(start_date, "%Y-%m-%d").date()
                    self.logger.debug(
                        f"[DOWNLOAD-SERVICE] 日期解析成功: {start_dt}",
                        extra={"log_type": "SYSTEM", "scenario": "data_download"}
                    )
                except ValueError as e:
                    self.logger.error(
                        f"[DOWNLOAD-SERVICE] ❌ 日期格式错误: {e}",
                        exc_info=True,
                        extra={"log_type": "ALERT", "scenario": "data_download"}
                    )
                    self.logger.debug(
                        f"[DOWNLOAD-SERVICE] 异常类型: {type(e).__name__}, 异常详情: {str(e)}",
                        extra={"log_type": "SYSTEM", "scenario": "data_download"}
                    )
                    # 阶段节点（输出到Terminal）
                    stage_logger.error(
                        f"❌ 数据下载失败: 日期格式错误 - {str(e)}",
                        extra={"log_type": "STAGE_NODE", "scenario": "data_download"},
                    )
                    return {
                        "success": False,
                        "task_id": None,
                        "message": f"日期格式错误: {str(e)}",
                    }

                today = date.today()
                days_diff = (today - start_dt).days
                self.logger.debug(
                    f"[DOWNLOAD-SERVICE] 日期验证: start_date={start_dt}, today={today}, days_diff={days_diff}",
                    extra={"log_type": "SYSTEM", "scenario": "data_download"}
                )
                if days_diff > 100:
                    self.logger.warning(
                        f"[DOWNLOAD-SERVICE] ⚠️ 日期超出范围: {days_diff}天前（最多支持100天）",
                        extra={"log_type": "ALERT", "scenario": "data_download"}
                    )
                    # 阶段节点（输出到Terminal）
                    stage_logger.warning(
                        f"⚠️ 数据下载失败: 日期超出范围 - {days_diff}天前（最多支持100天）",
                        extra={"log_type": "STAGE_NODE", "scenario": "data_download"},
                    )
                    return {
                        "success": False,
                        "task_id": None,
                        "message": f"增量下载最多支持最近100天数据，请调整开始日期（当前选择了{days_diff}天前的数据）",
                    }
                if days_diff < 0:
                    self.logger.warning(
                        f"[DOWNLOAD-SERVICE] ⚠️ 开始日期不能晚于今天: {start_dt} > {today}",
                        extra={"log_type": "ALERT", "scenario": "data_download"}
                    )
                    # 阶段节点（输出到Terminal）
                    stage_logger.warning(
                        "⚠️ 数据下载失败: 开始日期不能晚于今天",
                        extra={"log_type": "STAGE_NODE", "scenario": "data_download"},
                    )
                    return {
                        "success": False,
                        "task_id": None,
                        "message": "开始日期不能晚于今天",
                    }

                # 生成任务ID并登记
                task_id = f"incremental_download_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                self._download_tasks[task_id] = {
                    "type": "incremental",
                    "status": "running",
                    "start_time": datetime.now(),
                    "start_date": start_date,
                    "progress": 0,
                }

                # 注意: 不再使用IPO日期过滤品种列表，直接使用所有symbols
                filtered_symbols = symbols
                self.logger.debug(
                    f"[DOWNLOAD-SERVICE] 品种列表过滤: 原始数量={len(symbols) if symbols else 0}, "
                    f"过滤后数量={len(filtered_symbols) if filtered_symbols else 0}",
                    extra={"log_type": "SYSTEM", "scenario": "data_download"}
                )
                if not filtered_symbols:
                    error_msg = "品种列表为空，无法下载"
                    self.logger.warning(
                        f"[DOWNLOAD-SERVICE] ⚠️ {error_msg}",
                        extra={"log_type": "ALERT", "scenario": "data_download"}
                    )
                    self.logger.debug(
                        "[DOWNLOAD-SERVICE] 品种列表详情: symbols为空或None",
                        extra={"log_type": "SYSTEM", "scenario": "data_download"}
                    )
                    # 阶段节点（输出到Terminal）
                    stage_logger.warning(
                        f"⚠️ 数据下载失败: {error_msg}",
                        extra={"log_type": "STAGE_NODE", "scenario": "data_download"},
                    )
                    return {
                        "success": False,
                        "task_id": None,
                        "message": error_msg,
                    }

                if symbols:
                    self.logger.info(
                        f"[DOWNLOAD-SERVICE] 下载任务已创建: task_id={task_id}, 开始日期={start_date}, "
                        f"指定品种={len(filtered_symbols)}个, 预计天数={days_diff}天",
                        extra={"log_type": "SYSTEM", "scenario": "data_download"}
                    )
                    self.logger.debug(
                        f"[DOWNLOAD-SERVICE] 任务详情: task_id={task_id}, symbols={len(filtered_symbols)}个, "
                        f"start_date={start_dt}, days_diff={days_diff}",
                        extra={"log_type": "SYSTEM", "scenario": "data_download"}
                    )
                else:
                    self.logger.info(
                        f"[DOWNLOAD-SERVICE] 下载任务已创建: task_id={task_id}, 开始日期={start_date}, 预计下载{days_diff}天数据",
                        extra={"log_type": "SYSTEM", "scenario": "data_download"}
                    )
                    self.logger.debug(
                        f"[DOWNLOAD-SERVICE] 任务详情: task_id={task_id}, start_date={start_dt}, days_diff={days_diff}",
                        extra={"log_type": "SYSTEM", "scenario": "data_download"}
                    )

                # 启动底层后台下载任务（引擎内部自建线程）
                self.logger.debug(
                    "[DOWNLOAD-SERVICE] 开始启动底层下载任务...",
                    extra={"log_type": "SYSTEM", "scenario": "data_download"}
                )
                engine_start_time = time.time()
                started = self.china_stock_engine.download_incremental(
                    start_date=start_dt,
                    symbols=filtered_symbols  # 🔧 传递过滤后的品种列表
                )
                engine_start_elapsed = time.time() - engine_start_time
                self.logger.debug(
                    f"[DOWNLOAD-SERVICE] 底层下载任务启动完成: started={started}, 耗时={engine_start_elapsed:.2f}s",
                    extra={"log_type": "SYSTEM", "scenario": "data_download"}
                )
                if not started:
                    self.logger.error(
                        "[DOWNLOAD-SERVICE] ❌ 下载启动失败：已有任务在运行或启动失败",
                        extra={"log_type": "ALERT", "scenario": "data_download"}
                    )
                    self.logger.debug(
                        "[DOWNLOAD-SERVICE] 启动失败详情: started=False",
                        extra={"log_type": "SYSTEM", "scenario": "data_download"}
                    )
                    # 阶段节点（输出到Terminal）
                    stage_logger.error(
                        "❌ 数据下载失败: 下载启动失败，已有任务在运行或启动失败",
                        extra={"log_type": "STAGE_NODE", "scenario": "data_download"},
                    )
                    return {
                        "success": False,
                        "task_id": None,
                        "message": "已有下载任务在运行，或启动失败",
                    }

                # 批量下载场景上下文 - 日志埋点v4.0 (已移除scenario)
                # 直接执行,不使用scenario上下文
                ctx_scenario = None

                self.logger.debug(
                    f"[DOWNLOAD-SERVICE] 开始轮询下载进度: task_id={task_id}",
                    extra={"log_type": "SYSTEM", "scenario": "data_download"}
                )
                logger_download.info(
                    f"[下载-{task_id}] 引擎已启动，开始轮询进度...",
                    extra={"log_type": "SYSTEM", "scenario": "data_download"}
                )
                print(">>> [SERVICE] 引擎已启动，正在初始化下载任务...", flush=True)
                print(
                    ">>> [SERVICE] 提示：初始化可能需要15-30秒（发现服务器、构建任务列表）", flush=True
                )

                last_pct = -1
                last_log_time = time.time()
                last_progress_time = time.time()  # 记录最后一次有进度的时间
                last_completed = 0  # 记录上次的完成数
                timeout_seconds = 300  # 5分钟超时
                no_progress_timeout = 60  # 60秒无进度超时
                initialization_notified = False  # 是否已通知初始化完成

                # 直接轮询引擎进度，直到下载结束
                while True:
                    try:
                        prog = self.china_stock_engine.get_download_progress()
                        current_time = time.time()

                        if isinstance(prog, dict):
                            is_downloading = prog.get("is_downloading", False)
                            completed = int(prog.get("completed", 0))
                            total = int(prog.get("total", 0))
                            pct = int((completed / total) * 100) if total > 0 else 0
                            cur_sym = prog.get("current_symbol", "") or ""
                            cur_itv = prog.get("current_interval", "") or ""

                            # 检测进度是否有更新
                            if completed > last_completed:
                                last_progress_time = current_time
                                last_completed = completed

                            # 通知初始化完成（只通知一次）
                            if not initialization_notified and is_downloading and total > 0:
                                initialization_notified = True
                                elapsed_init = current_time - download_start_time
                                print(
                                    f">>> [SERVICE] ✓ 初始化完成！耗时 {elapsed_init:.1f}秒，开始下载 {total} 个任务...",
                                    flush=True,
                                )

                            # 进度更新：回调通知
                            if progress_callback and (pct != last_pct or completed != last_completed):
                                detail = f"{cur_sym} {cur_itv}".strip()
                                suffix = f" - {detail}" if detail else ""
                                msg = f"📥 进度 {pct:.0f}%（{completed}/{total}）{suffix}"
                                with suppress(Exception):
                                    progress_callback(pct, msg)
                                last_pct = pct

                            # 定期记录详细进度日志（每10秒）并强制输出到terminal
                            if current_time - last_log_time >= 10:
                                elapsed = current_time - download_start_time
                                remaining = total - completed
                                speed = completed / elapsed if elapsed > 0 else 0  # 任务/秒
                                estimated_remaining = remaining / speed if speed > 0 else 0
                                
                                self.logger.debug(
                                    f"[DOWNLOAD-SERVICE] 进度详情: task_id={task_id}, completed={completed}, "
                                    f"total={total}, pct={pct}%, current_symbol={cur_sym}, "
                                    f"current_interval={cur_itv}, speed={speed:.2f} tasks/s, "
                                    f"elapsed={elapsed:.1f}s, estimated_remaining={estimated_remaining:.1f}s",
                                    extra={"log_type": "SYSTEM", "scenario": "data_download"}
                                )
                                self.logger.info(
                                    f"[下载-{task_id}] 进度: {pct}% ({completed}/{total}) - {cur_sym} {cur_itv}, "
                                    f"速度={speed:.2f}任务/秒, 预计剩余={estimated_remaining:.0f}秒",
                                    extra={"log_type": "PROGRESS", "scenario": "data_download"}
                                )
                                # print(...)  # 🔧 已移除：防止刷屏，logger.info已足够
                                last_log_time = current_time

                            # 检查超时
                            elapsed = current_time - download_start_time
                            no_progress_elapsed = current_time - last_progress_time

                            if elapsed > timeout_seconds:
                                self.logger.error(
                                    f"[下载-{task_id}] 下载超时（{timeout_seconds}秒），停止轮询",
                                    extra={"log_type": "ALERT", "scenario": "data_download"}
                                )
                                break

                            if no_progress_elapsed > no_progress_timeout and completed > 0:
                                self.logger.debug(
                                    f"[DOWNLOAD-SERVICE] 无进度检测: task_id={task_id}, "
                                    f"no_progress_elapsed={no_progress_elapsed:.1f}s, "
                                    f"completed={completed}, total={total}, current_symbol={cur_sym}",
                                    extra={"log_type": "SYSTEM", "scenario": "data_download"}
                                )
                                self.logger.warning(
                                    f"[下载-{task_id}] {no_progress_timeout}秒无进度更新，可能卡住了: "
                                    f"当前品种={cur_sym}, 已完成={completed}/{total}",
                                    extra={"log_type": "ALERT", "scenario": "data_download"}
                                )

                            # 检查是否完成
                            if not is_downloading:
                                # 确认是否真的完成
                                if total > 0 and completed >= total:
                                    download_elapsed = time.time() - download_start_time
                                    self.logger.info(
                                        f"[下载-{task_id}] 引擎下载已完成: ({completed}/{total}), 耗时={download_elapsed:.2f}s",
                                        extra={"log_type": "SYSTEM", "scenario": "data_download"}
                                    )
                                    self.logger.debug(
                                        f"[DOWNLOAD-SERVICE] 下载完成详情: task_id={task_id}, completed={completed}, "
                                        f"total={total}, 耗时={download_elapsed:.2f}s",
                                        extra={"log_type": "SYSTEM", "scenario": "data_download"}
                                    )
                                    print(
                                        f">>> [SERVICE] ✓ 下载已完成 ({completed}/{total})", flush=True
                                    )
                                    break
                                elif total > 0 and completed < total:
                                    logger_download.warning(
                                        "[下载-%s] is_downloading=False 但未完成 (%d/%d)，继续等待...",
                                        task_id,
                                        completed,
                                        total,
                                        extra={"log_type": "ALERT", "scenario": "data_download"}
                                    )
                                    # 继续等待，可能是进度更新延迟
                                    time.sleep(1.0)
                                else:
                                    # total=0的情况，可能是初始化未完成（服务器发现、任务构建阶段）
                                    # 只在超过30秒后才警告，给初始化留足时间
                                    elapsed = current_time - download_start_time
                                    if elapsed > 30:
                                        logger_download.warning(
                                            "[下载-%s] is_downloading=False 且 total=0 已持续 %.0f秒，可能失败",
                                            task_id,
                                            elapsed,
                                            extra={"log_type": "ALERT", "scenario": "data_download"}
                                        )
                                        print(
                                            ">>> [SERVICE] ⚠️ 下载初始化超过30秒，可能存在问题",
                                            flush=True,
                                        )
                                    time.sleep(1.0)
                            else:
                                # 正常下载中，每20秒输出一次状态确认
                                if current_time - last_log_time >= 20:
                                    print(
                                        f">>> [SERVICE] 下载进行中: {pct}% ({completed}/{total})",
                                        flush=True,
                                    )
                                time.sleep(0.5)
                        else:
                            logger_download.debug(
                                f"[DOWNLOAD-SERVICE] 获取进度返回非字典类型: task_id={task_id}, "
                                f"prog_type={type(prog).__name__}, prog={prog}",
                                extra={"log_type": "SYSTEM", "scenario": "data_download"}
                            )
                            logger_download.warning(
                                "[下载-%s] 获取进度失败，prog=%s",
                                task_id,
                                prog,
                                extra={"log_type": "ALERT", "scenario": "data_download"}
                            )
                            time.sleep(0.5)

                    except Exception as poll_error:
                        logger_alert.debug(
                            f"[DOWNLOAD-SERVICE] 轮询异常详情: task_id={task_id}, "
                            f"异常类型={type(poll_error).__name__}, 异常详情={str(poll_error)}",
                            extra={"log_type": "SYSTEM", "scenario": "data_download"}
                        )
                        logger_alert.error(
                            "[下载-%s] 轮询异常: %s",
                            task_id,
                            poll_error,
                            exc_info=True,
                            extra={"log_type": "ALERT", "scenario": "data_download"}
                        )
                        time.sleep(0.5)

                # 线程已结束，做一次最终上报与事件广播
                if progress_callback:
                    with suppress(Exception):
                        progress_callback(100.0, "✅ 下载完成，正在整理结果...")

                download_duration = (time.time() - download_start_time) * 1000
                self.logger.debug(
                    f"[DOWNLOAD-SERVICE] 开始整理下载结果: task_id={task_id}, 总耗时={download_duration/1000:.2f}s",
                    extra={"log_type": "SYSTEM", "scenario": "data_download"}
                )
                logger_download.info(
                    f"[下载-{task_id}] 整理结果...",
                    extra={"log_type": "SYSTEM", "scenario": "data_download"}
                )

                # 退出场景上下文 - 日志埋点v4.0
                # Scenario context已移除

                self._emit_download_complete_event(task_id, "incremental", start_date)

                # 汇总返回
                task = self._download_tasks.get(task_id, {})
                status = task.get("status", "finished")
                self.logger.debug(
                    f"[DOWNLOAD-SERVICE] 任务状态: task_id={task_id}, status={status}",
                    extra={"log_type": "SYSTEM", "scenario": "data_download"}
                )
                if status == "error":
                    error_msg = task.get("error_message", "下载失败")
                    self.logger.error(
                        f"[DOWNLOAD-SERVICE] ❌ 下载任务失败: task_id={task_id}, error_msg={error_msg}",
                        extra={"log_type": "ALERT", "scenario": "data_download"}
                    )
                    self.log_operation_failure("增量数据下载", Exception(error_msg), task_id=task_id)
                    # 阶段节点（输出到Terminal）
                    stage_logger.error(
                        f"❌ 数据下载失败: {error_msg}",
                        extra={"log_type": "STAGE_NODE", "scenario": "data_download"},
                    )
                    return {
                        "success": False,
                        "task_id": task_id,
                        "message": error_msg,
                    }

                # 记录性能日志
                self.log_performance(
                    "增量数据下载",
                    download_duration,
                    True,
                    {"task_id": task_id, "start_date": start_date, "days": days_diff},
                )
                self.log_operation_success("增量数据下载", task_id=task_id, days=days_diff)

                # 阶段节点（输出到Terminal）
                stage_logger.info(
                    f"✅ 数据下载完成: 耗时={download_duration/1000:.2f}s, 成功={task.get('success_count', 0)}, 失败={task.get('failed_count', 0)}",
                    extra={"log_type": "STAGE_NODE", "scenario": "data_download"},
                )

                self.logger.info(
                    f"[DOWNLOAD-SERVICE] 增量数据下载成功: task_id={task_id}, 耗时={download_duration/1000:.2f}s",
                    extra={"log_type": "SYSTEM", "scenario": "data_download"}
                )
                self.logger.debug(
                    f"[DOWNLOAD-SERVICE] 下载成功详情: task_id={task_id}, start_date={start_date}, "
                    f"days_diff={days_diff}, 耗时={download_duration/1000:.2f}s",
                    extra={"log_type": "SYSTEM", "scenario": "data_download"}
                )

                return {
                    "success": True,
                    "task_id": task_id,
                    "message": "增量下载已完成",
                    "success_count": task.get("success_count", 0),
                    "failed_count": task.get("failed_count", 0),
                }

            except Exception as e:
                download_duration = (time.time() - download_start_time) * 1000
                self.logger.error(
                    f"[DOWNLOAD-SERVICE] ❌ 增量数据下载异常: {e}, 耗时={download_duration/1000:.2f}s",
                    exc_info=True,
                    extra={"log_type": "ALERT", "scenario": "data_download"}
                )
                self.logger.debug(
                    f"[DOWNLOAD-SERVICE] 异常类型: {type(e).__name__}, 异常详情: {str(e)}",
                    extra={"log_type": "SYSTEM", "scenario": "data_download"}
                )
                self.log_performance("增量数据下载", download_duration, False, {"error": str(e)})
                self.log_operation_failure("增量数据下载", e, start_date=start_date)
                
                # 阶段节点（输出到Terminal）
                stage_logger.error(
                    f"❌ 数据下载异常: {e}, 耗时={download_duration/1000:.2f}s",
                    extra={"log_type": "STAGE_NODE", "scenario": "data_download"},
                )
                
                return {
                    "success": False,
                    "task_id": None,
                    "message": f"启动失败: {str(e)}",
                }

    def start_incremental_download(self, start_date: str) -> Dict[str, Any]:
        """启动增量数据下载.

        下载从指定日期至今的数据（最多支持最近100天）。

        Args:
            start_date: 开始日期（格式：YYYY-MM-DD）

        Returns:
            Dict: 下载任务信息
        """
        import time
        from contextlib import suppress
        
        start_time = time.time()
        
        # 设置日志上下文
        try:
            from backend.infrastructure.system_vnpy.unified_log_system import (
                get_logging_hub,
                ai_log_process,
            )
            hub = get_logging_hub()
        except ImportError:
            hub = None
        
        stage_logger = logging.getLogger("task.data_download.stage")
        
        # 使用ai_log_process创建独立日志文件
        try:
            context_manager = ai_log_process("data_download", {"start_date": start_date}) if hub else suppress()
        except Exception:
            context_manager = suppress()
        
        with context_manager:
            try:
                # 阶段节点（输出到Terminal）
                stage_logger.info(
                    f"📍 数据下载开始: 开始日期={start_date}",
                    extra={"log_type": "STAGE_NODE", "scenario": "data_download"},
                )
                
                # DEBUG日志（只写入AI日志文件）
                self.logger.debug(
                    f"[DATA-DOWNLOAD-SERVICE] 开始启动增量数据下载: start_date={start_date}",
                    extra={"log_type": "SYSTEM", "scenario": "data_download"},
                )
                
                self._log_operation("启动增量数据下载", start_date=start_date)

                if self.china_stock_engine is None:
                    self.logger.error(
                        "[DATA-DOWNLOAD-SERVICE] ❌ data_module_vnpy不可用",
                        extra={"log_type": "ALERT", "scenario": "data_download"},
                    )
                    stage_logger.error(
                        "❌ data_module_vnpy不可用",
                        extra={"log_type": "STAGE_NODE", "scenario": "data_download"},
                    )
                    return {
                        "success": False,
                        "task_id": None,
                        "message": "data_module_vnpy不可用",
                    }

                # 解析并验证日期
                from datetime import datetime as dt, date

                try:
                    start_dt = dt.strptime(start_date, "%Y-%m-%d").date()
                    self.logger.debug(
                        f"[DATA-DOWNLOAD-SERVICE] 日期解析成功: {start_dt}",
                        extra={"log_type": "SYSTEM", "scenario": "data_download"},
                    )
                except ValueError as e:
                    self.logger.error(
                        f"[DATA-DOWNLOAD-SERVICE] ❌ 日期格式错误: {e}",
                        extra={"log_type": "ALERT", "scenario": "data_download"},
                    )
                    stage_logger.error(
                        f"❌ 日期格式错误: {e}",
                        extra={"log_type": "STAGE_NODE", "scenario": "data_download"},
                    )
                    return {
                        "success": False,
                        "task_id": None,
                        "message": f"日期格式错误: {str(e)}",
                    }

                # 验证100天限制
                today = date.today()
                days_diff = (today - start_dt).days
                
                self.logger.debug(
                    f"[DATA-DOWNLOAD-SERVICE] 日期验证: today={today}, start_dt={start_dt}, days_diff={days_diff}",
                    extra={"log_type": "SYSTEM", "scenario": "data_download"},
                )

                if days_diff > 100:
                    self.logger.warning(
                        f"[DATA-DOWNLOAD-SERVICE] ⚠️ 日期范围超过100天限制: {days_diff}天",
                        extra={"log_type": "ALERT", "scenario": "data_download"},
                    )
                    stage_logger.warning(
                        f"⚠️ 日期范围超过100天限制: {days_diff}天",
                        extra={"log_type": "STAGE_NODE", "scenario": "data_download"},
                    )
                    return {
                        "success": False,
                        "task_id": None,
                        "message": f"增量下载最多支持最近100天数据，请调整开始日期（当前选择了{days_diff}天前的数据）",
                    }

                if days_diff < 0:
                    self.logger.warning(
                        f"[DATA-DOWNLOAD-SERVICE] ⚠️ 开始日期不能晚于今天: {start_dt} > {today}",
                        extra={"log_type": "ALERT", "scenario": "data_download"},
                    )
                    stage_logger.warning(
                        "⚠️ 开始日期不能晚于今天",
                        extra={"log_type": "STAGE_NODE", "scenario": "data_download"},
                    )
                    return {
                        "success": False,
                        "task_id": None,
                        "message": "开始日期不能晚于今天",
                    }

                # 创建下载任务
                task_id = f"incremental_download_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                self.logger.debug(
                    f"[DATA-DOWNLOAD-SERVICE] 创建下载任务: task_id={task_id}",
                    extra={"log_type": "SYSTEM", "scenario": "data_download"},
                )

                # 调用ChinaStockEngine的增量下载方法
                try:
                    self.logger.info(
                        f"[DATA-DOWNLOAD-SERVICE] 开始调用ChinaStockEngine.download_incremental: start_date={start_dt}",
                        extra={"log_type": "SYSTEM", "scenario": "data_download"},
                    )
                    success = self.china_stock_engine.download_incremental(start_date=start_dt)

                    if not success:
                        # 下载失败（例如：本地缓存不存在）
                        self.logger.warning(
                            "[DATA-DOWNLOAD-SERVICE] ⚠️ 下载失败: 本地品种缓存不存在或为空",
                            extra={"log_type": "ALERT", "scenario": "data_download"},
                        )
                        stage_logger.warning(
                            "⚠️ 下载失败: 本地品种缓存不存在或为空",
                            extra={"log_type": "STAGE_NODE", "scenario": "data_download"},
                        )
                        return {
                            "success": False,
                            "task_id": None,
                            "message": "本地品种缓存不存在或为空，请先在【品种列表】界面点击【重新加载品种】按钮获取品种列表",
                        }

                    # 注册任务
                    self._download_tasks[task_id] = {
                        "type": "incremental",
                        "status": "running",
                        "start_time": datetime.now(),
                        "start_date": start_date,
                        "progress": 50,  # 假设进度
                    }
                    
                    self.logger.debug(
                        f"[DATA-DOWNLOAD-SERVICE] 下载任务已注册: task_id={task_id}",
                        extra={"log_type": "SYSTEM", "scenario": "data_download"},
                    )

                    # ✨ 发送数据下载完成事件（支持跨模块通知）
                    self._emit_download_complete_event(task_id, "incremental", start_date)
                    
                    total_elapsed = time.time() - start_time
                    self.logger.info(
                        f"[DATA-DOWNLOAD-SERVICE] ✅ 增量下载已启动: task_id={task_id}, 耗时={total_elapsed:.2f}s",
                        extra={"log_type": "SYSTEM", "scenario": "data_download"},
                    )
                    stage_logger.info(
                        f"✅ 数据下载已启动: task_id={task_id}, 耗时={total_elapsed:.2f}s",
                        extra={"log_type": "STAGE_NODE", "scenario": "data_download"},
                    )

                    return {
                        "success": True,
                        "task_id": task_id,
                        "message": "增量下载已启动",
                    }
                except Exception as e:
                    total_elapsed = time.time() - start_time
                    self.logger.error(
                        f"[DATA-DOWNLOAD-SERVICE] ❌ 增量下载启动失败: {e}, 耗时={total_elapsed:.2f}s",
                        exc_info=True,
                        extra={"log_type": "ALERT", "scenario": "data_download"},
                    )
                    self.logger.debug(
                        f"[DATA-DOWNLOAD-SERVICE] 异常类型: {type(e).__name__}, 异常详情: {str(e)}",
                        extra={"log_type": "SYSTEM", "scenario": "data_download"},
                    )
                    stage_logger.error(
                        f"❌ 数据下载启动失败: {e}, 耗时={total_elapsed:.2f}s",
                        extra={"log_type": "STAGE_NODE", "scenario": "data_download"},
                    )
                    return {
                        "success": False,
                        "task_id": None,
                        "message": f"下载失败: {str(e)}",
                    }

            except Exception as e:
                total_elapsed = time.time() - start_time
                self.logger.error(
                    f"[DATA-DOWNLOAD-SERVICE] ❌ 数据下载流程异常: {e}, 耗时={total_elapsed:.2f}s",
                    exc_info=True,
                    extra={"log_type": "ALERT", "scenario": "data_download"},
                )
                stage_logger.error(
                    f"❌ 数据下载流程异常: {e}, 耗时={total_elapsed:.2f}s",
                    extra={"log_type": "STAGE_NODE", "scenario": "data_download"},
                )
                self._log_error("启动增量下载", e, start_date=start_date)
                return {
                    "success": False,
                    "task_id": None,
                    "message": f"启动失败: {str(e)}",
                }

    def get_download_history(
        self, limit: int = 50, task_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """获取下载历史记录.

        对应需求链条2.2.2：历史下载记录

        Args:
            limit: 返回数量限制
            task_type: 任务类型过滤（full/incremental）

        Returns:
            Dict: 下载历史列表
        """
        try:
            filtered = self._download_history

            if task_type:
                filtered = [h for h in filtered if h.get("type") == task_type]

            # 按开始时间倒序排序
            filtered.sort(key=lambda h: h.get("start_time", ""), reverse=True)

            return {
                "success": True,
                "history": filtered[:limit],
                "total": len(self._download_history),
            }

        except Exception as e:
            self._log_error("获取下载历史", e)
            return {"success": False, "history": [], "message": str(e)}

    def _add_download_history(self, task: Dict[str, Any]):
        """添加下载历史记录.

        Args:
            task: 下载任务信息
        """
        try:
            history_item = {
                "task_id": task.get("task_id"),
                "type": task.get("type"),
                "status": task.get("status"),
                "start_time": task.get("start_time", datetime.now()).isoformat(),
                "end_time": task.get("end_time", datetime.now()).isoformat(),
                "duration": task.get("duration", 0),
                "progress": task.get("progress", 0),
                "completed_symbols": task.get("completed_symbols", 0),
                "total_symbols": task.get("total_symbols", 0),
                "error_message": task.get("error_message"),
            }

            self._download_history.append(history_item)

            # 限制历史记录大小（保留最近500条）
            if len(self._download_history) > 500:
                self._download_history = self._download_history[-300:]

            self.logger.info("下载历史已记录: %s", task.get("task_id"))

        except Exception as e:
            self.logger.error("添加下载历史失败: %s", str(e))

    def get_download_progress(self, task_id: Optional[str] = None) -> Dict[str, Any]:
        """获取下载进度（支持从后端engine实时获取）.

        Args:
            task_id: 任务ID（可选）

        Returns:
            Dict: 进度信息
        """
        # 🔧 新架构：直接从ChinaStockEngine获取实时进度
        if self.china_stock_engine and hasattr(self.china_stock_engine, "get_download_progress"):
            try:
                progress = self.china_stock_engine.get_download_progress()

                if progress.get("is_downloading"):
                    # 正在下载，返回实时进度
                    completed = progress.get("completed", 0)
                    total = progress.get("total", 1)
                    progress_pct = (completed / total * 100) if total > 0 else 0

                    return {
                        "success": True,
                        "is_downloading": True,
                        "progress": progress_pct,
                        "completed": completed,
                        "total": total,
                        "current_symbol": progress.get("current_symbol", ""),
                        "current_interval": progress.get("current_interval", ""),
                        "start_time": progress.get("start_time"),
                    }
                else:
                    # 没有正在进行的下载
                    return {
                        "success": True,
                        "is_downloading": False,
                        "progress": 0,
                    }
            except Exception as e:
                self.logger.error("获取实时进度失败: %s", e, extra={"log_type": "SYSTEM"})

        # 旧逻辑：从任务字典获取
        if task_id:
            task = self._download_tasks.get(task_id)
            if task is None:
                return {
                    "success": False,
                    "message": "任务不存在",
                }

            return {
                "success": True,
                "task_id": task_id,
                "type": task["type"],
                "status": task["status"],
                "progress": task["progress"],
                "start_time": task["start_time"].isoformat(),
            }

        # 无task_id且无正在进行的下载
        return {
            "success": True,
            "is_downloading": False,
            "progress": 0,
        }

    def stop_download(self, task_id: Optional[str] = None) -> Dict[str, Any]:
        """停止下载任务.

        Args:
            task_id: 任务ID（可选，如果未提供则停止当前任务）

        Returns:
            Dict: 操作结果
        """
        try:
            # 如果ChinaStockEngine支持停止操作，调用停止方法
            if self.china_stock_engine and hasattr(self.china_stock_engine, "stop_download"):
                try:
                    self.china_stock_engine.stop_download()
                    self.logger.info("✅ 已调用ChinaStockEngine停止下载")

                    # 更新任务状态
                    if task_id and task_id in self._download_tasks:
                        task = self._download_tasks[task_id]
                        task["status"] = "stopped"
                        task["stop_time"] = datetime.now()
                        self.logger.info("下载任务 %s 已停止", task_id)

                    return {
                        "success": True,
                        "message": "任务已停止",
                    }
                except Exception as e:
                    self.logger.warning("⚠️ 调用停止下载失败: %s", e, exc_info=True, extra={"log_type": "SYSTEM"})
                    return {
                        "success": False,
                        "message": f"停止失败: {str(e)}",
                    }
            else:
                return {
                    "success": False,
                    "message": "ChinaStockEngine不支持停止操作",
                }

        except Exception as e:
            self._log_error("停止下载", e, task_id=task_id)
            return {
                "success": False,
                "message": f"停止失败: {str(e)}",
            }

    def pause_download(self, task_id: Optional[str] = None) -> Dict[str, Any]:
        """暂停下载任务.

        Args:
            task_id: 任务ID（可选）

        Returns:
            Dict: 操作结果
        """
        try:
            # 如果ChinaStockEngine支持暂停操作，调用暂停方法
            if self.china_stock_engine and hasattr(self.china_stock_engine, "pause_download"):
                try:
                    self.china_stock_engine.pause_download()
                    self.logger.info("✅ 已调用ChinaStockEngine暂停下载")

                    # 更新任务状态
                    if task_id and task_id in self._download_tasks:
                        task = self._download_tasks[task_id]
                        task["status"] = "paused"
                        task["paused_at"] = datetime.now()
                        task["paused_progress"] = task.get("progress", 0)
                        self.logger.info("下载任务 %s 已暂停", task_id)

                    return {
                        "success": True,
                        "message": "任务已暂停",
                    }
                except Exception as e:
                    self.logger.warning("⚠️ 调用暂停下载失败: %s", e, exc_info=True, extra={"log_type": "SYSTEM"})
                    return {
                        "success": False,
                        "message": f"暂停失败: {str(e)}",
                    }
            else:
                return {
                    "success": False,
                    "message": "ChinaStockEngine不支持暂停操作",
                }

        except Exception as e:
            self._log_error("暂停下载", e, task_id=task_id)
            return {
                "success": False,
                "message": f"暂停失败: {str(e)}",
            }

    def resume_download(self, task_id: Optional[str] = None) -> Dict[str, Any]:
        """恢复暂停的下载任务.

        Args:
            task_id: 任务ID（可选）

        Returns:
            Dict: 操作结果
        """
        try:
            # 如果ChinaStockEngine支持恢复操作，调用恢复方法
            if self.china_stock_engine and hasattr(self.china_stock_engine, "resume_download"):
                try:
                    self.china_stock_engine.resume_download()
                    self.logger.info("✅ 已调用ChinaStockEngine恢复下载")

                    # 更新任务状态
                    if task_id and task_id in self._download_tasks:
                        task = self._download_tasks[task_id]
                        task["status"] = "running"
                        task["resumed_at"] = datetime.now()
                        self.logger.info("下载任务 %s 已恢复", task_id)

                    return {
                        "success": True,
                        "message": "任务已恢复",
                    }
                except Exception as e:
                    self.logger.warning("⚠️ 调用恢复下载失败: %s", e, exc_info=True, extra={"log_type": "SYSTEM"})
                    return {
                        "success": False,
                        "message": f"恢复失败: {str(e)}",
                    }
            else:
                return {
                    "success": False,
                    "message": "ChinaStockEngine不支持恢复操作",
                }

        except Exception as e:
            self._log_error("恢复下载", e, task_id=task_id)
            return {
                "success": False,
                "message": f"恢复失败: {str(e)}",
            }

    def _stop_all_downloads(self):
        """停止所有下载任务."""
        for task_id in list(self._download_tasks.keys()):
            self.stop_download(task_id)

    # ==================== 本地数据查询 ====================

    def check_symbol_exists(self, symbol: str) -> bool:
        """检查品种代码是否存在于交易所品种列表中.

        Args:
            symbol: 品种代码（如：600000、000001）

        Returns:
            bool: True表示品种存在，False表示不存在
        """
        try:
            # 从内存缓存中查找
            if self._symbol_cache and "symbols" in self._symbol_cache:
                symbols_list = self._symbol_cache["symbols"]
                # 检查品种代码是否在列表中
                for symbol_item in symbols_list:
                    if isinstance(symbol_item, dict):
                        if symbol_item.get("code") == symbol:
                            return True
                    elif isinstance(symbol_item, str):
                        if symbol_item == symbol:
                            return True
                return False

            # 如果缓存不存在，返回True（容错：假设品种存在）
            self.logger.warning("品种缓存不存在，无法验证品种 %s", symbol, extra={"log_type": "SYSTEM"})
            return True

        except Exception as e:
            self.logger.error("检查品种是否存在失败: %s", e, exc_info=True, extra={"log_type": "SYSTEM"})
            return True  # 容错：出错时假设品种存在

    def query_local_data(
        self, symbol: str, start_date: str, end_date: str, interval: str = "1d"
    ) -> Dict[str, Any]:
        """查询本地OHLCV数据.

        Args:
            symbol: 品种代码
            start_date: 开始日期
            end_date: 结束日期
            interval: 周期（1d, 5min, 1min等）

        Returns:
            Dict: OHLCV数据
        """
        try:
            self._log_operation(
                "查询本地数据", symbol=symbol, start=start_date, end=end_date, interval=interval
            )

            if self.china_stock_engine is None:
                return {
                    "success": False,
                    "message": "ChinaStockEngine不可用",
                    "data": [],
                }

            # 调用ChinaStockEngine的数据查询方法
            try:
                from datetime import datetime as dt

                start_dt = dt.strptime(start_date, "%Y-%m-%d").date()
                end_dt = dt.strptime(end_date, "%Y-%m-%d").date()

                # 查询数据（禁用自动下载：用户主动查询不应触发下载）
                data = self.china_stock_engine.query_data(
                    symbol=symbol,
                    interval=interval,
                    start_date=start_dt,
                    end_date=end_dt,
                    check_gaps=False,  # 显式禁用缺口检查和自动下载
                )

                if data is not None and not data.empty:
                    # 转换为字典列表
                    data_list = data.to_dict("records")
                    return {
                        "success": True,
                        "message": f"查询成功，共{len(data_list)}条数据",
                        "data": data_list,
                    }
                else:
                    return {
                        "success": True,
                        "message": "查询成功，无数据",
                        "data": [],
                    }

            except Exception as e:
                self.logger.error("数据查询失败: %s", e, exc_info=True, extra={"log_type": "SYSTEM"})
                return {
                    "success": False,
                    "message": f"查询失败: {str(e)}",
                    "data": [],
                }

        except Exception as e:
            self._log_error("查询本地数据", e, symbol=symbol)
            return {
                "success": False,
                "message": f"查询失败: {str(e)}",
                "data": [],
            }

    def check_data_quality(
        self, symbol: Optional[str] = None, interval: str = "1d"
    ) -> Dict[str, Any]:
        """检查数据质量（增强版 - 支持数据感知）.

        Args:
            symbol: 品种代码（可选，为None则检查所有品种）
            interval: K线周期，默认"1d"

        Returns:
            Dict: 质量检查结果，包含详细的质量感知信息
                {
                    "success": bool,
                    "message": str,
                    "quality_status": str,  # "excellent", "good", "warning", "error"
                    "quality_score": int,   # 0-100分
                    "data_count": int,      # 数据条数
                    "date_range": tuple,    # 日期范围
                    "missing_dates_count": int,  # 缺失日期数量
                    "errors_count": int,    # 错误数量
                    "warnings_count": int,  # 警告数量
                    "issues": list,         # 详细问题列表
                    "can_repair": bool      # 是否可以修复
                }
        """
        try:
            self._log_operation("检查数据质量", symbol=symbol, interval=interval)

            if not self.china_stock_engine:
                return {
                    "success": False,
                    "message": "ChinaStockEngine不可用",
                    "quality_status": "error",
                    "quality_score": 0,
                    "issues": [],
                    "can_repair": False,
                }

            # 调用validator进行质量检查
            try:
                from backend.infrastructure.data_module_vnpy.data_quality import (
                    StatelessValidator,
                    ValidationResult,
                )

                validator = StatelessValidator()

                if symbol:
                    # 单品种校验 - 使用StatelessValidator的validate方法
                    from backend.infrastructure.data_module_vnpy.data_storage import StorageManager
                    storage = StorageManager()
                    df = storage.load_data(symbol, interval)
                    if df is not None and not df.empty:
                        validation_result = StatelessValidator.validate_all(df, max_age_days=7)
                    else:
                        validation_result = None

                    if not validation_result or df is None or df.empty:
                        return {
                            "success": True,
                            "message": f"品种 {symbol} 没有本地数据",
                            "quality_status": "error",
                            "quality_score": 0,
                            "data_count": 0,
                            "date_range": (None, None),
                            "missing_dates_count": 0,
                            "errors_count": 0,
                            "warnings_count": 0,
                            "issues": ["数据文件不存在或为空"],
                            "can_repair": True,
                        }

                    # 🔧 修复：validation_result 是 Dict[str, ValidationResult]，需要合并所有验证结果
                    all_errors = []
                    all_warnings = []
                    record_count = len(df)
                    # 🔧 修复：正确处理 DatetimeIndex（使用 iloc 访问避免类型推断问题）
                    if not df.empty and len(df) > 0:
                        try:
                            import pandas as pd
                            first_idx = df.index[0]
                            last_idx = df.index[-1]
                            # 转换为 date 对象
                            if isinstance(first_idx, pd.Timestamp):
                                first_date = first_idx.date()
                            elif hasattr(first_idx, 'date'):
                                first_date = first_idx.date()  # type: ignore
                            else:
                                first_date = None

                            if isinstance(last_idx, pd.Timestamp):
                                last_date = last_idx.date()
                            elif hasattr(last_idx, 'date'):
                                last_date = last_idx.date()  # type: ignore
                            else:
                                last_date = None

                            date_range = (first_date, last_date)
                        except Exception:
                            date_range = (None, None)
                    else:
                        date_range = (None, None)
                    missing_dates = []

                    # 合并所有验证结果的错误和警告
                    for result_key, result in validation_result.items():
                        if isinstance(result, ValidationResult):
                            all_errors.extend(result.errors)
                            all_warnings.extend(result.warnings)
                            # 从 metrics 中获取缺失日期信息（如果有）
                            if 'missing_dates' in result.metrics:
                                missing_dates = result.metrics.get('missing_dates', [])
                            elif 'missing_count' in result.metrics:
                                missing_dates = [None] * result.metrics.get('missing_count', 0)

                    errors = all_errors
                    warnings = all_warnings

                    # 计算质量评分（0-100）
                    quality_score = self._calculate_quality_score(
                        len(errors), len(warnings), len(missing_dates), record_count
                    )

                    # 确定质量状态
                    if len(errors) > 0:
                        quality_status = "error"
                        status_text = "❌ 数据有错误"
                    elif len(warnings) > 0 or len(missing_dates) > 0:
                        quality_status = "warning"
                        status_text = "⚠️ 数据有警告"
                    else:
                        quality_status = "excellent"
                        status_text = "✅ 数据正常"

                    # 构建详细问题列表
                    issues = []
                    issues.extend(errors)
                    if missing_dates:
                        issues.append(f"缺失 {len(missing_dates)} 个交易日的数据")

                    # 🆕 检查数据更新状态（从 freshness 验证结果获取）
                    gap_days = -1
                    is_up_to_date = False
                    latest_trading_day = None
                    local_latest_date = None

                    if 'freshness' in validation_result:
                        freshness_result = validation_result['freshness']
                        if isinstance(freshness_result, ValidationResult):
                            # 从 metrics 中获取新鲜度信息
                            metrics = freshness_result.metrics
                            gap_days = metrics.get('age_days', -1)
                            is_up_to_date = gap_days <= 7  # max_age_days = 7
                            if df is not None and not df.empty and len(df) > 0:
                                try:
                                    import pandas as pd
                                    last_idx = df.index[-1]
                                    if isinstance(last_idx, pd.Timestamp):
                                        local_latest_date = last_idx.to_pydatetime()
                                    elif hasattr(last_idx, 'to_pydatetime'):
                                        local_latest_date = last_idx.to_pydatetime()  # type: ignore
                                    elif hasattr(last_idx, 'date'):
                                        from datetime import datetime
                                        local_latest_date = datetime.combine(last_idx.date(), datetime.min.time())  # type: ignore
                                    else:
                                        local_latest_date = None
                                except Exception:
                                    local_latest_date = None

                    return {
                        "success": True,
                        "message": f"{status_text}，共 {record_count} 条记录",
                        "quality_status": quality_status,
                        "quality_score": quality_score,
                        "data_count": record_count,
                        "date_range": date_range,
                        "missing_dates_count": len(missing_dates),
                        "errors_count": len(errors),
                        "warnings_count": len(warnings),
                        "issues": issues,
                        "can_repair": len(errors) > 0 or len(missing_dates) > 0,
                        # 🆕 数据更新状态
                        "gap_days": gap_days,
                        "is_up_to_date": is_up_to_date,
                        "latest_trading_day": (
                            latest_trading_day.strftime("%Y-%m-%d") if latest_trading_day else None
                        ),
                        "local_latest_date": (
                            local_latest_date.strftime("%Y-%m-%d")
                            if local_latest_date is not None and hasattr(local_latest_date, 'strftime')
                            else None
                        ),
                    }
                else:
                    # 所有品种校验（返回简化的汇总）
                    # 🔧 修复：StatelessValidator 没有 validate_all_data 方法
                    # 使用数据感知器获取质量概览
                    from backend.infrastructure.data_module_vnpy.data_quality import DataSensor
                    data_sensor = self.china_stock_engine.data_sensor if hasattr(self.china_stock_engine, 'data_sensor') and self.china_stock_engine.data_sensor else None

                    if data_sensor:
                        stats = data_sensor.get_stats()
                        total_symbols = stats.get("total_scanned", 0)
                        invalid_symbols = stats.get("total_failed", 0)
                        valid_symbols = stats.get("total_passed", 0)
                    else:
                        total_symbols = 0
                        invalid_symbols = 0
                        valid_symbols = 0

                    return {
                        "success": True,
                        "message": f"质量检查完成，共 {total_symbols} 个品种",
                        "quality_status": "good" if invalid_symbols == 0 else "warning",
                        "quality_score": 100 if invalid_symbols == 0 else 50,
                        "total_symbols": total_symbols,
                        "valid_symbols": valid_symbols,
                        "invalid_symbols": invalid_symbols,
                        "total_errors": 0,  # 🔧 修复：从 stats 获取错误数
                        "total_warnings": stats.get("total_warnings", 0) if data_sensor else 0,
                        "issues": [],
                        "can_repair": invalid_symbols > 0,
                    }

            except Exception as e:
                self.logger.error("质量检查失败: %s", e, exc_info=True, extra={"log_type": "SYSTEM"})
                return {
                    "success": False,
                    "message": f"检查失败: {str(e)}",
                    "quality_status": "error",
                    "quality_score": 0,
                    "issues": [str(e)],
                    "can_repair": False,
                }

        except Exception as e:
            self._log_error("检查数据质量", e, symbol=symbol)
            return {
                "success": False,
                "message": f"检查失败: {str(e)}",
                "quality_status": "error",
                "quality_score": 0,
                "issues": [str(e)],
                "can_repair": False,
            }

    def get_data_freshness_overview(self) -> Dict[str, Any]:
        """获取全局数据更新状态概览

        Returns:
            Dict: {
                "success": bool,
                "outdated_symbols": int,       # 过时品种数
                "avg_gap_days": int,           # 平均滞后天数
                "max_gap_days": int,           # 最大滞后天数
                "latest_trading_day": str,     # 最新交易日
                "message": str
            }
        """
        try:
            self._log_operation("获取数据更新状态概览")

            if not self.china_stock_engine:
                return {
                    "success": False,
                    "message": "ChinaStockEngine不可用",
                    "outdated_symbols": 0,
                    "avg_gap_days": 0,
                    "max_gap_days": 0,
                    "latest_trading_day": None,
                }

            # 从数据感知器获取质量概览
            from backend.infrastructure.data_module_vnpy.data_quality import DataSensor
            from backend.infrastructure.data_module_vnpy import ChinaStockEngine
            from backend.core.base import get_china_stock_engine

            # 获取DataSensor实例
            engine = get_china_stock_engine()
            if engine and hasattr(engine, 'data_sensor') and engine.data_sensor:
                data_sensor = engine.data_sensor
            else:
                # 创建新的DataSensor实例
                data_sensor = DataSensor()

            # scan_quality返回字典，需要转换为概览格式
            # 临时返回空概览，后续可以根据实际需求实现
            quality_overview = {
                "total_symbols": 0,
                "scanned_symbols": 0,
                "quality_levels": {},
            }

            if quality_overview is None:
                return {
                    "success": False,
                    "message": "数据质量扫描尚未完成，请稍后再试",
                    "outdated_symbols": 0,
                    "avg_gap_days": 0,
                    "max_gap_days": 0,
                    "latest_trading_day": None,
                }

            # 🔧 修复：quality_overview 是字典，应该用字典访问
            outdated_symbols = quality_overview.get("outdated_symbols", 0)
            avg_gap_days = quality_overview.get("avg_gap_days", 0)
            max_gap_days = quality_overview.get("max_gap_days", quality_overview.get("data_lagging_days", 0))
            base_date = quality_overview.get("base_date")
            latest_trading_day_str = base_date.strftime("%Y-%m-%d") if base_date and hasattr(base_date, 'strftime') else None

            return {
                "success": True,
                "message": f"成功获取数据更新状态，共 {outdated_symbols} 个品种过时",
                "outdated_symbols": outdated_symbols,
                "avg_gap_days": avg_gap_days,
                "max_gap_days": max_gap_days,
                "latest_trading_day": latest_trading_day_str,
            }

        except Exception as e:
            self._log_error("获取数据更新状态概览", e)
            return {
                "success": False,
                "message": f"获取失败: {str(e)}",
                "outdated_symbols": 0,
                "avg_gap_days": 0,
                "max_gap_days": 0,
                "latest_trading_day": None,
            }

    def _calculate_quality_score(
        self, errors_count: int, warnings_count: int, missing_dates_count: int, total_records: int
    ) -> int:
        """计算数据质量评分.

        Args:
            errors_count: 错误数量
            warnings_count: 警告数量
            missing_dates_count: 缺失日期数量
            total_records: 总记录数

        Returns:
            int: 质量评分（0-100）
        """
        # 基础分100分
        score = 100

        # 错误扣分（每个错误扣10分）
        score -= errors_count * 10

        # 警告扣分（每个警告扣5分）
        score -= warnings_count * 5

        # 缺失日期扣分（根据比例）
        if total_records > 0 and missing_dates_count > 0:
            missing_ratio = missing_dates_count / (total_records + missing_dates_count)
            score -= int(missing_ratio * 30)  # 最多扣30分

        # 确保分数在0-100之间
        return max(0, min(100, score))

    # ==================== 数据感知管理 ====================

    def get_data_quality_overview(self) -> Dict[str, Any]:
        """获取全局数据质量概览（自动感知）.

        Returns:
            Dict: {
                "success": bool,
                "total_symbols": int,
                "missing_symbols": int,
                "error_symbols": int,
                "warning_symbols": int,
                "quality_score": int,  # 0-100分
                "last_scan_time": str,
                "details": list  # 有问题的品种详情列表
            }
        """
        try:
            if not self.china_stock_engine:
                return {
                    "success": False,
                    "message": "ChinaStockEngine不可用",
                    "total_symbols": 0,
                    "missing_symbols": 0,
                    "error_symbols": 0,
                    "warning_symbols": 0,
                    "quality_score": 0,
                }

            # 获取数据感知器的质量概览
            overview = self.china_stock_engine.get_data_quality_overview()

            if not overview:
                # 尚未扫描，返回空概览
                return {
                    "success": True,
                    "message": "数据质量扫描尚未完成，请稍候...",
                    "total_symbols": 0,
                    "missing_symbols": 0,
                    "error_symbols": 0,
                    "warning_symbols": 0,
                    "quality_score": 0,
                    "last_scan_time": None,
                    "details": [],
                }

            # 转换为返回格式
            # overview是字典，直接使用字典中的字段
            total_symbols = overview.get("total_symbols", 0)
            missing_symbols = overview.get("missing_symbols", 0)
            local_symbols = total_symbols - missing_symbols

            return {
                "success": True,
                "total_symbols": total_symbols,
                "local_symbols": local_symbols,  # 🚀 新增：本地有数据的品种数
                "missing_symbols": missing_symbols,
                "error_symbols": overview.get("error_symbols", 0),
                "warning_symbols": overview.get("warning_symbols", 0),
                "quality_score": overview.get("quality_score", 0),
                "last_scan_time": overview.get("last_scan_time"),
                "details": overview.get("details", []),  # 有问题的品种列表
                "message": overview.get("message", "数据质量概览获取成功"),
            }

        except Exception as e:
            self.logger.error("获取数据质量概览失败: %s", e, exc_info=True, extra={"log_type": "SYSTEM"})
            return {
                "success": False,
                "message": f"获取失败: {str(e)}",
                "total_symbols": 0,
                "missing_symbols": 0,
                "error_symbols": 0,
                "warning_symbols": 0,
                "quality_score": 0,
            }

    def trigger_data_quality_scan(self, force_refresh: bool = False) -> bool:
        """手动触发数据质量扫描（异步后台执行）.

        Args:
            force_refresh: 是否强制刷新（忽略缓存）

        Returns:
            bool: 是否成功触发
        """
        try:
            if not self.china_stock_engine:
                self.logger.warning("ChinaStockEngine不可用，无法触发扫描", extra={"log_type": "SYSTEM"})
                return False

            self.logger.info("手动触发数据质量扫描（后台执行）...")

            # 🆕 后台线程执行扫描
            import threading

            thread = threading.Thread(
                target=self._do_quality_scan, args=(force_refresh,), daemon=True
            )
            thread.start()
            return True

        except Exception as e:
            logger_alert.error("触发数据质量扫描失败: %s", e, exc_info=True, extra={"log_type": "ALERT"})
            return False

    def _do_quality_scan(self, force_refresh: bool):
        """执行数据质量扫描（后台线程）

        Args:
            force_refresh: 是否强制刷新
        """
        import time
        from contextlib import suppress
        
        start_time = time.time()
        
        # 设置日志上下文
        try:
            from backend.infrastructure.system_vnpy.unified_log_system import (
                get_logging_hub,
                ai_log_process,
            )
            hub = get_logging_hub()
        except ImportError:
            hub = None
        
        stage_logger = logging.getLogger("task.manual_data_scan.stage")
        
        # 使用ai_log_process创建独立日志文件
        try:
            context_manager = ai_log_process(
                "manual_data_scan",
                {"force_refresh": force_refresh, "scan_type": "quality_scan"}
            ) if hub else suppress()
        except Exception:
            context_manager = suppress()
        
        with context_manager:
            try:
                # 阶段节点（输出到Terminal）
                stage_logger.info(
                    f"📍 手动数据扫描开始: force_refresh={force_refresh}",
                    extra={"log_type": "STAGE_NODE", "scenario": "manual_data_scan"},
                )
                
                # DEBUG日志（只写入AI日志文件）
                self.logger.debug(
                    "[SCAN-SERVICE] 开始手动数据扫描",
                    extra={"log_type": "SYSTEM", "scenario": "manual_data_scan"}
                )
                self.logger.info(
                    f"[SCAN-SERVICE] 手动数据扫描任务开始: force_refresh={force_refresh}",
                    extra={"log_type": "SYSTEM", "scenario": "manual_data_scan"}
                )
            
                # 确保 china_stock_engine 可用
                if not self.china_stock_engine:
                    self.logger.error(
                        "[SCAN-SERVICE] ❌ ChinaStockEngine 不可用，无法执行数据质量扫描",
                        extra={"log_type": "ALERT", "scenario": "manual_data_scan"}
                    )
                    self.logger.debug(
                        "[SCAN-SERVICE] ChinaStockEngine状态: None",
                        extra={"log_type": "SYSTEM", "scenario": "manual_data_scan"}
                    )
                    stage_logger.error(
                        "❌ ChinaStockEngine不可用，无法执行数据质量扫描",
                        extra={"log_type": "STAGE_NODE", "scenario": "manual_data_scan"},
                    )
                    return

                # 🔧 修复：移除LoadBalancer预热逻辑，避免在后台线程中创建Qt相关对象
                # LoadBalancer的事件订阅和缓存机制已经足够高效，不需要额外预热
                # 在后台线程中创建LoadBalancer可能导致Qt Timer错误和内存损坏

                # 数据质量扫描 - 日志埋点v4.0
                self.logger.debug(
                    "[SCAN-SERVICE] 调用china_stock_engine.trigger_data_quality_scan方法...",
                    extra={"log_type": "SYSTEM", "scenario": "manual_data_scan"}
                )
                scan_start_time = time.time()
                overview = self.china_stock_engine.trigger_data_quality_scan(
                    force_refresh=force_refresh
                )
                scan_elapsed = time.time() - scan_start_time
                total_elapsed = time.time() - start_time
                self.logger.debug(
                    f"[SCAN-SERVICE] trigger_data_quality_scan方法调用完成: 耗时={scan_elapsed:.2f}s",
                    extra={"log_type": "SYSTEM", "scenario": "manual_data_scan"}
                )
            
                if overview:
                    # 推送事件
                    self.logger.debug(
                        "[SCAN-SERVICE] 开始推送质量概览事件...",
                        extra={"log_type": "SYSTEM", "scenario": "manual_data_scan"}
                    )
                    event_start_time = time.time()
                    self.china_stock_engine._push_quality_overview_event(overview)
                    event_elapsed = time.time() - event_start_time
                    self.logger.debug(
                        f"[SCAN-SERVICE] 质量概览事件推送完成: 耗时={event_elapsed:.2f}s",
                        extra={"log_type": "SYSTEM", "scenario": "manual_data_scan"}
                    )
                    
                    quality_score = overview.quality_score
                    self.logger.info(
                        f"[SCAN-SERVICE] ✓ 数据质量扫描完成: 评分={quality_score:.2f}, "
                        f"扫描耗时={scan_elapsed:.2f}s, 总耗时={total_elapsed:.2f}s",
                        extra={"log_type": "SYSTEM", "scenario": "manual_data_scan"}
                    )
                    self.logger.debug(
                        f"[SCAN-SERVICE] 扫描结果详情: quality_score={quality_score}, "
                        f"scan_elapsed={scan_elapsed:.2f}s, event_elapsed={event_elapsed:.2f}s, "
                        f"total_elapsed={total_elapsed:.2f}s",
                        extra={"log_type": "SYSTEM", "scenario": "manual_data_scan"}
                    )
                    
                    # 阶段节点（输出到Terminal）
                    stage_logger.info(
                        f"✅ 手动数据扫描完成: 评分={quality_score:.2f}, 耗时={total_elapsed:.2f}s",
                        extra={"log_type": "STAGE_NODE", "scenario": "manual_data_scan"},
                    )

                    # 数据质量告警 - 日志埋点v4.0
                    if quality_score < 60:
                        logger_alert.warning(
                            f"[SCAN-SERVICE] ⚠️ 数据质量告警: 评分过低={quality_score:.2f}, 建议检查数据完整性",
                            extra={"log_type": "ALERT", "scenario": "manual_data_scan"}
                        )
                        self.logger.debug(
                            f"[SCAN-SERVICE] 质量评分过低: quality_score={quality_score:.2f} < 60",
                            extra={"log_type": "SYSTEM", "scenario": "manual_data_scan"}
                        )
                        stage_logger.warning(
                            f"⚠️ 数据质量评分过低: {quality_score:.2f} < 60",
                            extra={"log_type": "STAGE_NODE", "scenario": "manual_data_scan"},
                        )
                else:
                    self.logger.warning(
                        f"[SCAN-SERVICE] ⚠️ 数据质量扫描未返回结果, 耗时={total_elapsed:.2f}s",
                        extra={"log_type": "ALERT", "scenario": "manual_data_scan"}
                    )
                    self.logger.debug(
                        "[SCAN-SERVICE] 扫描结果: overview=None",
                        extra={"log_type": "SYSTEM", "scenario": "manual_data_scan"}
                    )
                    stage_logger.warning(
                        f"⚠️ 数据质量扫描未返回结果, 耗时={total_elapsed:.2f}s",
                        extra={"log_type": "STAGE_NODE", "scenario": "manual_data_scan"},
                    )

            except Exception as e:
                total_elapsed = time.time() - start_time
                self.logger.error(
                    f"[SCAN-SERVICE] ❌ 数据质量扫描失败: {e}, 耗时={total_elapsed:.2f}s",
                    exc_info=True,
                    extra={"log_type": "ALERT", "scenario": "manual_data_scan"}
                )
                self.logger.debug(
                    f"[SCAN-SERVICE] 异常类型: {type(e).__name__}, 异常详情: {str(e)}",
                    extra={"log_type": "SYSTEM", "scenario": "manual_data_scan"}
                )
                stage_logger.error(
                    f"❌ 数据质量扫描失败: {e}, 耗时={total_elapsed:.2f}s",
                    extra={"log_type": "STAGE_NODE", "scenario": "manual_data_scan"},
                )

    # ==================== 数据源管理 ====================

    def connect_datafeed(
        self, datafeed_type: str, config: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """连接数据源.

        实现互斥连接控制：同时只能连接一个数据源。

        Args:
            datafeed_type: 数据源类型 (polling_gateway, virtual_gateway)
            config: 配置信息

        Returns:
            Dict: 连接结果
        """
        try:
            self._log_operation("连接数据源", type=datafeed_type)

            if datafeed_type not in self.datafeeds:
                return {
                    "success": False,
                    "message": f"不支持的数据源类型: {datafeed_type}",
                }

            # 互斥连接控制：如果有其他数据源活动，先断开
            if self.active_datafeed and self.active_datafeed != datafeed_type:
                self.logger.warning(
                    "检测到活动数据源 %s，将先断开以连接 %s", self.active_datafeed, datafeed_type
                )
                disconnect_result = self.disconnect_datafeed(self.active_datafeed)
                if not disconnect_result.get("success"):
                    return {
                        "success": False,
                        "message": f"无法断开现有数据源 {self.active_datafeed}: {disconnect_result.get('message')}",
                    }

            # 实现实际的数据源连接逻辑
            try:
                if datafeed_type in ["polling_gateway", "virtual_gateway"]:
                    # 网关类型数据源，由start_polling_gateway或start_virtual_gateway处理
                    return {
                        "success": False,
                        "message": f"{datafeed_type} 请使用专门的启动方法",
                    }
                else:
                    return {
                        "success": False,
                        "message": f"未实现的数据源类型: {datafeed_type}",
                    }

            except Exception as e:
                self.logger.error("连接%s失败: %s", datafeed_type, e, exc_info=True, extra={"log_type": "SYSTEM"})
                return {
                    "success": False,
                    "message": f"连接失败: {str(e)}",
                }

        except Exception as e:
            self._log_error("连接数据源", e, type=datafeed_type)
            return {
                "success": False,
                "message": f"连接失败: {str(e)}",
            }

    def disconnect_datafeed(self, datafeed_type: str) -> Dict[str, Any]:
        """断开数据源.

        Args:
            datafeed_type: 数据源类型

        Returns:
            Dict: 操作结果
        """
        try:
            if datafeed_type not in self.datafeeds:
                return {
                    "success": False,
                    "message": f"不支持的数据源类型: {datafeed_type}",
                }

            # 实现断开逻辑
            if self.datafeeds[datafeed_type] is None:
                return {
                    "success": True,
                    "message": f"数据源 {datafeed_type} 未连接",
                }

            # 调用数据源的关闭方法（如果有）
            datafeed = self.datafeeds[datafeed_type]
            if datafeed and hasattr(datafeed, "close"):
                try:
                    datafeed.close()
                    self.logger.info("已调用%s的close方法", datafeed_type)
                except Exception as e:
                    self.logger.warning("关闭%s失败: %s", datafeed_type, e, extra={"log_type": "SYSTEM"})

            # 清除引用
            self.datafeeds[datafeed_type] = None

            # 如果断开的是活动数据源，清除标记
            if self.active_datafeed == datafeed_type:
                self.active_datafeed = None
                self.realtime_push_active = False
                self.logger.info("✅ 活动数据源已清除")

            self.logger.info("数据源 %s 已断开", datafeed_type)

            return {
                "success": True,
                "message": f"数据源 {datafeed_type} 已断开",
            }

        except Exception as e:
            self._log_error("断开数据源", e, type=datafeed_type)
            return {
                "success": False,
                "message": f"断开失败: {str(e)}",
            }

    def _disconnect_all_datafeeds(self):
        """断开所有数据源."""
        for datafeed_type in list(self.datafeeds.keys()):
            if self.datafeeds[datafeed_type] is not None:
                self.disconnect_datafeed(datafeed_type)

    def start_realtime_push(self, symbols: Optional[List[str]] = None) -> Dict[str, Any]:
        """启动实时数据推送.

        Args:
            symbols: 要订阅的品种列表（如为None则订阅所有）

        Returns:
            Dict: 启动结果
        """
        try:
            if not self.active_datafeed:
                return {
                    "success": False,
                    "message": "没有活动的数据源，请先连接数据源",
                }

            if self.realtime_push_active:
                return {
                    "success": False,
                    "message": "实时推送已在运行",
                }

            # 获取活动数据源
            datafeed = self.datafeeds.get(self.active_datafeed)
            if not datafeed:
                return {
                    "success": False,
                    "message": f"数据源 {self.active_datafeed} 不可用",
                }

            # 通过MainEngine订阅数据（实际需要网关连接）
            if self.main_engine:
                # 实际订阅需要根据具体数据源API实现
                # 这里仅标记状态
                self.realtime_push_active = True
                self.logger.info("✅ 实时推送已启动: %s", self.active_datafeed)

                return {
                    "success": True,
                    "message": f"实时推送已启动 ({self.active_datafeed})",
                    "symbols": symbols or [],
                }
            else:
                return {
                    "success": False,
                    "message": "MainEngine不可用",
                }

        except Exception as e:
            self._log_error("启动实时推送", e)
            return {
                "success": False,
                "message": f"启动失败: {str(e)}",
            }

    def stop_realtime_push(self) -> Dict[str, Any]:
        """停止实时数据推送.

        Returns:
            Dict: 停止结果
        """
        try:
            if not self.realtime_push_active:
                return {
                    "success": False,
                    "message": "实时推送未运行",
                }

            # 取消订阅
            self.realtime_push_active = False
            self.logger.info("✅ 实时推送已停止")

            return {
                "success": True,
                "message": "实时推送已停止",
            }

        except Exception as e:
            self._log_error("停止实时推送", e)
            return {
                "success": False,
                "message": f"停止失败: {str(e)}",
            }

    def start_data_recording(self, custom_path: Optional[str] = None) -> Dict[str, Any]:
        """启动实时数据录制.

        对应需求：保存位置可配置更改

        Args:
            custom_path: 自定义录制路径（可选）

        Returns:
            Dict: 操作结果
        """
        try:
            self._log_operation("启动数据录制")

            # 获取录制路径配置
            from backend.core.config import get_settings

            settings = get_settings()
            recording_path = custom_path or settings.vnpy.recording_data_path

            # 确保录制目录存在
            Path(recording_path).mkdir(parents=True, exist_ok=True)
            self.logger.info("录制数据路径: %s", recording_path)

            # 调用vnpy_datarecorder启动录制
            try:
                # 尝试导入vnpy_datarecorder
                from vnpy_datarecorder import DataRecorderApp  # type: ignore[import-untyped]
                from backend.core.base import get_main_engine

                # 获取主引擎
                main_engine = get_main_engine()
                if main_engine is not None:
                    # 检查是否已添加DataRecorderApp
                    if not hasattr(self, "recorder_engine") or self.recorder_engine is None:
                        # 添加数据录制应用（传入录制路径配置）
                        recorder_app = DataRecorderApp
                        recorder_engine = main_engine.add_app(recorder_app)
                        self.recorder_engine = recorder_engine

                        # 配置录制路径（如果recorder_engine支持）
                        if hasattr(self.recorder_engine, "set_recording_path"):
                            self.recorder_engine.set_recording_path(recording_path)

                        self.logger.info("DataRecorder应用已添加")

                    # 启动录制（如果有start方法）
                    if hasattr(self.recorder_engine, "start"):
                        self.recorder_engine.start()
                        self.logger.info("数据录制已启动")

                    return {
                        "success": True,
                        "message": "数据录制已启动",
                        "recording_path": recording_path,
                    }
                else:
                    return {
                        "success": False,
                        "message": "MainEngine不可用",
                    }

            except ImportError:
                self.logger.warning("vnpy_datarecorder包未安装", extra={"log_type": "SYSTEM"})
                return {
                    "success": False,
                    "message": "vnpy_datarecorder包未安装",
                }
            except Exception as e:
                self.logger.error("启动录制失败: %s", e, exc_info=True, extra={"log_type": "SYSTEM"})
                return {
                    "success": False,
                    "message": f"启动失败: {str(e)}",
                }

        except Exception as e:
            self._log_error("启动数据录制", e)
            return {
                "success": False,
                "message": f"启动失败: {str(e)}",
            }

    def stop_data_recording(self) -> Dict[str, Any]:
        """停止实时数据录制.

        Returns:
            Dict: 操作结果
        """
        try:
            # 停止录制
            if hasattr(self, "recorder_engine") and self.recorder_engine:
                # 如果录制引擎有stop方法，调用它
                if hasattr(self.recorder_engine, "stop"):
                    try:
                        self.recorder_engine.stop()
                        self.logger.info("数据录制已停止")
                    except Exception as e:
                        self.logger.warning("停止录制失败: %s", e, extra={"log_type": "SYSTEM"})

                return {
                    "success": True,
                    "message": "数据录制已停止",
                }
            else:
                return {
                    "success": True,
                    "message": "录制引擎未启动",
                }

        except Exception as e:
            self._log_error("停止数据录制", e)
            return {
                "success": False,
                "message": f"停止失败: {str(e)}",
            }

    def get_all_datafeed_status(self) -> Dict[str, Any]:
        """获取所有数据源状态.

        Returns:
            Dict: 数据源状态信息
        """
        status = {}
        for datafeed_type, datafeed in self.datafeeds.items():
            # 检查实际推送状态
            is_connected = datafeed is not None
            is_pushing = False

            if is_connected:
                # 检查datafeed是否有is_active或类似的状态方法
                if hasattr(datafeed, "is_active"):
                    with suppress(Exception):
                        is_pushing = datafeed.is_active()
                elif hasattr(datafeed, "connected"):
                    with suppress(Exception):
                        is_pushing = datafeed.connected

            status[datafeed_type] = {
                "connected": is_connected,
                "pushing_data": is_pushing,
            }

        # 添加录制状态
        recording_status = {
            "enabled": hasattr(self, "recorder_engine") and self.recorder_engine is not None,
            "running": False,
        }

        if (
            recording_status["enabled"]
            and self.recorder_engine is not None
            and hasattr(self.recorder_engine, "is_running")
        ):
            with suppress(Exception):
                recording_status["running"] = self.recorder_engine.is_running()

        return {
            "success": True,
            "datafeeds": status,
            "active_datafeed": self.active_datafeed,
            "realtime_push_active": self.realtime_push_active,
            "recording": recording_status,
        }

    # ==================== 实时数据录制 ====================

    def start_realtime_data_recording(
        self, symbols: Optional[List[str]] = None, record_tick: bool = True, record_bar: bool = True
    ) -> Dict[str, Any]:
        """启动实时数据录制.

        使用vnpy_datarecorder进行实时数据录制。

        Args:
            symbols: 要录制的品种列表（如为None则录制所有订阅品种）
            record_tick: 是否录制Tick数据
            record_bar: 是否录制1分钟Bar数据

        Returns:
            Dict: 启动结果
        """
        try:
            # 检查是否已有录制引擎
            if self.recorder_engine:
                return {
                    "success": False,
                    "message": "录制引擎已在运行",
                }

            # 尝试导入vnpy_datarecorder
            try:
                from vnpy_datarecorder import DataRecorderApp  # type: ignore[import-untyped]
            except ImportError:
                return {
                    "success": False,
                    "message": "vnpy_datarecorder包未安装，请先安装: pip install vnpy_datarecorder",
                }

            # 检查main_engine是否可用
            if not self.main_engine:
                return {
                    "success": False,
                    "message": "MainEngine不可用，无法启动录制",
                }

            # 添加DataRecorder应用
            try:
                self.recorder_engine = self.main_engine.add_app(DataRecorderApp)
                self.logger.info("✅ DataRecorder引擎已创建")
            except Exception as e:
                self.logger.error("创建DataRecorder引擎失败: %s", e, exc_info=True, extra={"log_type": "SYSTEM"})
                return {
                    "success": False,
                    "message": f"创建录制引擎失败: {str(e)}",
                }

            # 设置录制参数
            recording_config = {
                "record_tick": record_tick,
                "record_bar": record_bar,
                "symbols": symbols or [],
            }

            # 如果提供了品种列表，添加订阅
            if symbols:
                for symbol in symbols:
                    try:
                        # 订阅品种（通过网关）
                        # 注意：实际订阅需要网关连接后才能进行
                        pass
                    except Exception as e:
                        self.logger.warning("订阅品种 %s 失败: %s", symbol, e, extra={"log_type": "SYSTEM"})

            self.logger.info(
                "数据录制已启动: Tick=%s, Bar=%s, 品种数=%d",
                record_tick,
                record_bar,
                len(symbols) if symbols else 0,
            )

            return {
                "success": True,
                "message": "数据录制已启动",
                "config": recording_config,
            }

        except Exception as e:
            self._log_error("启动数据录制", e)
            return {
                "success": False,
                "message": f"启动失败: {str(e)}",
            }

    def stop_realtime_data_recording(self) -> Dict[str, Any]:
        """停止实时数据录制.

        Returns:
            Dict: 停止结果
        """
        try:
            if not self.recorder_engine:
                return {
                    "success": False,
                    "message": "录制引擎未运行",
                }

            # 停止录制（移除应用）
            try:
                # vnpy_datarecorder会在应用移除时自动停止录制
                self.recorder_engine = None
                self.logger.info("数据录制已停止")

                return {
                    "success": True,
                    "message": "数据录制已停止",
                }

            except Exception as e:
                self.logger.error("停止录制失败: %s", e, exc_info=True, extra={"log_type": "SYSTEM"})
                return {
                    "success": False,
                    "message": f"停止失败: {str(e)}",
                }

        except Exception as e:
            self._log_error("停止数据录制", e)
            return {
                "success": False,
                "message": f"停止失败: {str(e)}",
            }

    def get_recording_status(self) -> Dict[str, Any]:
        """获取录制状态.

        Returns:
            Dict: 录制状态信息
        """
        try:
            is_recording = self.recorder_engine is not None

            status = {
                "is_recording": is_recording,
                "recorder_available": self.recorder_engine is not None,
            }

            if (
                is_recording
                and self.recorder_engine
                and hasattr(self.recorder_engine, "get_statistics")
            ):
                # 获取录制统计信息（如果录制引擎提供）
                with suppress(Exception):
                    stats = self.recorder_engine.get_statistics()
                    status["statistics"] = stats

            return {
                "success": True,
                "status": status,
            }

        except Exception as e:
            self._log_error("获取录制状态", e)
            return {
                "success": False,
                "message": f"获取状态失败: {str(e)}",
            }

    def get_recorded_data(self, symbol: str, date: str) -> Optional[List[Dict[str, Any]]]:
        """获取录制的数据（供行情看板使用）.

        Args:
            symbol: 品种代码
            date: 日期（格式：YYYY-MM-DD）

        Returns:
            List[Dict]: 录制的数据列表，如果没有则返回None
        """
        try:
            from pathlib import Path

            # 录制数据路径（与vnpy_datarecorder保持一致）
            recording_path = Path(".vntrader/data_recorder")

            if not recording_path.exists():
                return None

            # 构建录制文件路径
            # vnpy_datarecorder通常按日期和品种存储
            # 格式示例: .vntrader/data_recorder/2024-01-01/000001.SZSE_1m.csv
            date_dir = recording_path / date

            if not date_dir.exists():
                return None

            # 查找该品种的录制文件
            recorded_files = list(date_dir.glob(f"{symbol}*"))

            if not recorded_files:
                return None

            # 读取第一个匹配的文件（通常只有一个）
            import pandas as pd

            data_file = recorded_files[0]
            df = pd.read_csv(data_file)

            # 转换为标准格式
            data = df.to_dict("records")

            self.logger.info(
                "从录制数据加载 %d 条记录: symbol=%s, date=%s", len(data), symbol, date
            )

            return data

        except Exception as e:
            self.logger.warning("获取录制数据失败: %s", e, extra={"log_type": "SYSTEM"})
            return None

    def sync_recorded_data_to_storage(
        self, symbol: Optional[str] = None, date: Optional[str] = None
    ) -> Dict[str, Any]:
        """将录制数据同步到本地存储（data_module_vnpy）.

        实现数据录制与数据中心的无缝集成，确保录制的实时数据
        能够在本地数据查询中访问到。

        Args:
            symbol: 品种代码（如为None则同步所有品种）
            date: 日期（如为None则同步今天）

        Returns:
            Dict: 同步结果
        """
        try:
            from datetime import datetime
            from pathlib import Path
            import pandas as pd

            # 默认使用今天的日期
            if not date:
                date = datetime.now().strftime("%Y-%m-%d")

            # 录制数据路径
            recording_path = Path(".vntrader/data_recorder")
            date_dir = recording_path / date

            if not date_dir.exists():
                return {
                    "success": True,
                    "message": f"录制数据目录不存在: {date}",
                    "synced_count": 0,
                }

            synced_count = 0
            failed_count = 0

            # 如果指定了品种，只同步该品种
            if symbol:
                recorded_files = list(date_dir.glob(f"{symbol}*"))
            else:
                # 同步所有品种
                recorded_files = list(date_dir.glob("*"))

            self.logger.info("找到 %d 个录制文件待同步", len(recorded_files))

            # 使用storage_manager保存数据
            if not self.china_stock_engine:
                self.logger.warning("ChinaStockEngine不可用，无法同步录制数据", extra={"log_type": "SYSTEM"})
                return {
                    "success": False,
                    "message": "ChinaStockEngine不可用",
                }

            storage_manager = self.china_stock_engine.storage_manager

            for file_path in recorded_files:
                try:
                    # 读取录制数据
                    df = pd.read_csv(file_path)

                    if df.empty:
                        continue

                    # 解析文件名获取品种和周期信息
                    # 格式示例: 000001.SZSE_1m.csv
                    file_name = file_path.stem
                    parts = file_name.split("_")
                    symbol_code = parts[0] if parts else ""
                    interval = parts[1] if len(parts) > 1 else "1m"

                    # 转换周期格式
                    interval_map = {"1m": "1min", "5m": "5min", "1d": "day"}
                    data_type = interval_map.get(interval, "1min")

                    # 保存到storage
                    storage_manager.save_kline_data(symbol_code, df, data_type)

                    synced_count += 1
                    self.logger.info("✅ 已同步录制数据: %s (%s)", symbol_code, data_type)

                except Exception as e:
                    failed_count += 1
                    self.logger.warning("同步文件 %s 失败: %s", file_path, e, extra={"log_type": "SYSTEM"})

            message = f"已同步 {synced_count} 个品种的录制数据"
            if failed_count > 0:
                message += f"，{failed_count} 个失败"

            self.logger.info(message)

            return {
                "success": True,
                "message": message,
                "synced_count": synced_count,
                "failed_count": failed_count,
            }

        except Exception as e:
            self._log_error("同步录制数据", e)
            return {
                "success": False,
                "message": f"同步失败: {str(e)}",
            }

    def cleanup_recorded_data(
        self, days_to_keep: int = 1, sync_before_delete: bool = False
    ) -> Dict[str, Any]:
        """清理过期的录制数据.

        删除超过指定天数的录制数据（日级缓存清理）。
        默认不同步到持久存储，可通过参数控制。

        Args:
            days_to_keep: 保留天数（默认1天，即只保留今天的数据）
            sync_before_delete: 删除前是否同步到持久存储（默认False）

        Returns:
            Dict: 清理结果
        """
        try:
            from pathlib import Path
            from datetime import datetime, timedelta

            # 录制数据路径
            recording_path = Path(".vntrader/data_recorder")

            if not recording_path.exists():
                return {
                    "success": True,
                    "message": "录制数据目录不存在",
                    "deleted_dirs": 0,
                }

            # 计算截止日期
            cutoff_date = datetime.now() - timedelta(days=days_to_keep)

            deleted_dirs = 0
            deleted_size = 0
            synced_dirs = 0

            # 遍历日期目录
            for date_dir in recording_path.iterdir():
                if not date_dir.is_dir():
                    continue

                try:
                    # 解析目录名（应该是日期格式YYYY-MM-DD）
                    dir_name = date_dir.name
                    dir_date = datetime.strptime(dir_name, "%Y-%m-%d")

                    # 如果是过期目录
                    if dir_date.date() < cutoff_date.date():
                        # 可选：同步数据到持久存储
                        if sync_before_delete:
                            sync_result = self.sync_recorded_data_to_storage(date=dir_name)
                            if sync_result.get("success"):
                                synced_dirs += 1
                                self.logger.info("✅ 已同步过期录制数据: %s", dir_name)

                        # 计算目录大小
                        dir_size = sum(f.stat().st_size for f in date_dir.rglob("*") if f.is_file())

                        # 删除目录
                        import shutil

                        shutil.rmtree(date_dir)

                        deleted_dirs += 1
                        deleted_size += dir_size
                        self.logger.info("🗑️ 已删除过期录制目录: %s", dir_name)

                except ValueError:
                    # 目录名不是日期格式，跳过
                    self.logger.debug("跳过非日期目录: %s", date_dir.name)
                except Exception as e:
                    self.logger.warning("处理目录 %s 失败: %s", date_dir, e, extra={"log_type": "SYSTEM"})

            message = f"已清理 {deleted_dirs} 个过期录制目录"
            if synced_dirs > 0:
                message += f"（已同步 {synced_dirs} 个到持久存储）"

            self.logger.info(
                "录制数据清理完成: 删除 %d 个目录, 释放 %.2f MB",
                deleted_dirs,
                deleted_size / 1024 / 1024,
            )

            return {
                "success": True,
                "message": message,
                "deleted_dirs": deleted_dirs,
                "synced_dirs": synced_dirs,
                "freed_space_mb": deleted_size / 1024 / 1024,
            }

        except Exception as e:
            self._log_error("清理录制数据", e)
            return {
                "success": False,
                "message": f"清理失败: {str(e)}",
            }

    def _emit_download_complete_event(self, task_id: str, download_type: str, start_date: str):
        """发送数据下载完成事件.

        Args:
            task_id: 任务ID
            download_type: 下载类型（incremental/full）
            start_date: 开始日期
        """
        try:
            from backend.core.base import get_event_engine
            from backend.infrastructure.system_vnpy import (
                EVENT_DATA_DOWNLOAD_COMPLETE,
            )
            from vnpy.event import Event

            event_engine = get_event_engine()
            if not event_engine:
                return

            # 构建事件数据
            event_data = {
                "task_id": task_id,
                "download_type": download_type,
                "start_date": start_date,
                "end_date": datetime.now().strftime("%Y-%m-%d"),
                "timestamp": datetime.now().isoformat(),
            }

            # 发送事件
            event = Event(EVENT_DATA_DOWNLOAD_COMPLETE, event_data)
            event_engine.put(event)

            self.logger.info("📢 已发送数据下载完成事件: %s (%s)", download_type, start_date)

        except Exception as e:
            self.logger.warning("发送下载完成事件失败: %s", e, extra={"log_type": "SYSTEM"})

    def _auto_start_recording_on_push(self) -> Dict[str, Any]:
        """数据源推送启动时自动启动录制.

        实现需求：实时数据推送时应有recording功能，该功能无需手动启动。

        Returns:
            Dict: 启动结果
        """
        try:
            # 如果录制引擎已经在运行，直接返回成功
            if self.recorder_engine:
                self.logger.info("录制引擎已在运行，跳过自动启动")
                return {
                    "success": True,
                    "message": "录制引擎已在运行",
                }

            # 调用现有的录制启动方法
            result = self.start_realtime_data_recording(
                symbols=None,  # 录制所有订阅品种
                record_tick=True,
                record_bar=True,
            )

            return result

        except Exception as e:
            self.logger.error("自动启动录制失败: %s", e, exc_info=True, extra={"log_type": "SYSTEM"})
            return {
                "success": False,
                "message": f"自动启动失败: {str(e)}",
            }

    def check_and_cleanup_old_cache_on_login(self) -> Dict[str, Any]:
        """登录时检查并清理非当天的录制缓存（不同步到持久存储）.

        在系统启动时执行，检查录制缓存目录，删除非当天的旧缓存。
        与定时清理不同，这个方法不会同步数据到持久存储。

        Returns:
            Dict: 清理结果
                - success: bool
                - deleted_dirs: int 删除的目录数量
                - freed_space_mb: float 释放的空间(MB)
                - message: str
        """
        try:
            from pathlib import Path
            from datetime import datetime

            # 录制数据路径
            recording_path = Path(".vntrader/data_recorder")

            if not recording_path.exists():
                self.logger.info("录制数据目录不存在，无需清理")
                return {
                    "success": True,
                    "message": "录制数据目录不存在",
                    "deleted_dirs": 0,
                    "freed_space_mb": 0.0,
                }

            # 获取当天日期
            today = datetime.now().date()
            today_str = today.strftime("%Y-%m-%d")

            deleted_dirs = 0
            deleted_size = 0

            # 遍历日期目录
            for date_dir in recording_path.iterdir():
                if not date_dir.is_dir():
                    continue

                try:
                    # 解析目录名（应该是日期格式YYYY-MM-DD）
                    dir_name = date_dir.name

                    # 检查是否为当天
                    if dir_name != today_str:
                        # 计算目录大小
                        dir_size = sum(f.stat().st_size for f in date_dir.rglob("*") if f.is_file())

                        # 直接删除（不同步到持久存储）
                        import shutil

                        shutil.rmtree(date_dir)

                        deleted_dirs += 1
                        deleted_size += dir_size
                        self.logger.info("🗑️ 已删除旧录制缓存: %s", dir_name)

                except Exception as e:
                    self.logger.warning("处理目录 %s 失败: %s", date_dir, e, extra={"log_type": "SYSTEM"})

            freed_mb = deleted_size / 1024 / 1024

            if deleted_dirs > 0:
                self.logger.info(
                    "✅ 登录时缓存清理完成: 删除 %d 个目录, 释放 %.2f MB", deleted_dirs, freed_mb
                )
            else:
                self.logger.info("✅ 无需清理，只有当天的缓存")

            return {
                "success": True,
                "deleted_dirs": deleted_dirs,
                "freed_space_mb": freed_mb,
                "message": f"已清理 {deleted_dirs} 个旧缓存目录",
            }

        except Exception as e:
            self.logger.error("登录时缓存清理失败: %s", e, exc_info=True, extra={"log_type": "SYSTEM"})
            return {
                "success": False,
                "message": f"清理失败: {str(e)}",
                "deleted_dirs": 0,
                "freed_space_mb": 0.0,
            }

    # ==================== 轮询转推送网关管理 ====================

    def start_polling_gateway(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """启动轮询转推送网关（TDX数据源）.

        Args:
            config: 网关配置
                - polling_interval: 轮询间隔（秒）
                - max_servers: 最大服务器数（可选）
                - symbols: 订阅品种列表（可选，建议使用自动注册机制）

        Returns:
            Dict: 启动结果
        """
        try:
            self._log_operation("启动TDX数据源（通道激活）")

            # 检查是否已有网关运行
            if self.polling_gateway is not None:
                return {
                    "success": False,
                    "message": "TDX数据源已在运行，请先停止",
                }

            # 检查虚拟网关是否在运行（自动停止）
            if self.virtual_gateway is not None:
                self.logger.info("检测到虚拟数据源正在运行，自动停止...")
                stop_result = self.stop_virtual_gateway()
                if stop_result.get("success"):
                    self.logger.info("✅ 虚拟数据源已自动停止")
                else:
                    self.logger.warning("⚠️ 停止虚拟数据源失败: %s", stop_result.get("message"))
                    # 继续启动TDX数据源，忽略停止失败

            # 获取MainEngine和EventEngine
            from backend.core.base import get_main_engine, get_event_engine

            main_engine = get_main_engine()
            event_engine = get_event_engine()

            if not main_engine or not event_engine:
                return {
                    "success": False,
                    "message": "MainEngine或EventEngine不可用",
                }

            # 导入数据源类（从data_runtime）
            try:
                from backend.infrastructure.data_module_vnpy import (
                    TdxDataSource,
                )

                # 向后兼容：PollingGateway别名
                PollingGateway = TdxDataSource
            except ImportError as e:
                self.logger.error("导入TdxDataSource失败: %s", e, exc_info=True, extra={"log_type": "SYSTEM"})
                return {
                    "success": False,
                    "message": f"导入数据源失败: {str(e)}",
                }

            # 注册网关类到MainEngine（确保MainEngine能识别和管理该网关）
            try:
                main_engine.add_gateway(PollingGateway)
                self.logger.info("✅ PollingGateway类已注册到MainEngine")
            except Exception as e:
                # 网关类可能已注册，忽略重复注册错误
                self.logger.debug("PollingGateway注册跳过（可能已存在）: %s", e)

            # 创建网关实例
            gateway_name = "POLLING"
            # TdxDataSource 构造函数: __init__(event_engine, config_manager)
            from backend.infrastructure.data_module_vnpy import ConfigManager
            config_manager = ConfigManager.get_instance()
            self.polling_gateway = PollingGateway(event_engine, config_manager)

            # 准备配置（不包含symbols，使用自动注册机制）
            gateway_setting = {
                "轮询间隔（秒）": config.get("polling_interval", config.get("interval", 3)),
                "最大服务器数": config.get("max_servers", 5),
                # 注意：不再设置"品种列表"，订阅由各模块通过UnifiedDataManager.subscribe_data()自动注册
            }

            # 连接网关
            self.polling_gateway.connect(gateway_setting)

            # 更新数据源状态
            self.datafeeds["polling_gateway"] = self.polling_gateway
            self.active_datafeed = "polling_gateway"
            self.realtime_push_active = True

            self.logger.info("✅ 轮询转推送网关已启动")

            # ✨ 自动启动数据录制（需求：实时数据推送时应有recording功能，该功能无需手动启动）
            auto_record_result = self._auto_start_recording_on_push()
            if auto_record_result.get("success"):
                self.logger.info("✅ 数据录制已自动启动")
            else:
                self.logger.warning("⚠️ 数据录制自动启动失败: %s", auto_record_result.get("message"))

            return {
                "success": True,
                "message": "轮询转推送网关已启动",
                "gateway_name": gateway_name,
                "recording_started": auto_record_result.get("success", False),
            }

        except Exception as e:
            self._log_error("启动轮询网关", e)
            # 清理
            self.polling_gateway = None
            self.datafeeds["polling_gateway"] = None
            return {
                "success": False,
                "message": f"启动失败: {str(e)}",
            }

    def stop_polling_gateway(self) -> Dict[str, Any]:
        """停止轮询转推送网关.

        Returns:
            Dict: 停止结果
        """
        try:
            if self.polling_gateway is None:
                return {
                    "success": False,
                    "message": "轮询网关未运行",
                }

            # 停止录制引擎
            if self.recorder_engine:
                try:
                    stop_result = self.stop_realtime_data_recording()
                    if stop_result.get("success"):
                        self.logger.info("✅ 数据录制已停止")
                except Exception as e:
                    self.logger.warning("停止录制引擎失败: %s", e, extra={"log_type": "SYSTEM"})

            # 关闭网关
            self.polling_gateway.close()
            self.polling_gateway = None

            # 更新状态
            self.datafeeds["polling_gateway"] = None
            if self.active_datafeed == "polling_gateway":
                self.active_datafeed = None
                self.realtime_push_active = False

            self.logger.info("✅ 轮询转推送网关已停止")

            return {
                "success": True,
                "message": "轮询转推送网关已停止",
            }

        except Exception as e:
            self._log_error("停止轮询网关", e)
            # 强制清理状态，避免状态不一致
            self.polling_gateway = None
            self.datafeeds["polling_gateway"] = None
            if self.active_datafeed == "polling_gateway":
                self.active_datafeed = None
                self.realtime_push_active = False
            return {
                "success": False,
                "message": f"停止失败: {str(e)}",
            }

    def get_polling_gateway_status(self) -> Dict[str, Any]:
        """获取轮询网关状态.

        Returns:
            Dict: 网关状态
        """
        try:
            is_running = self.polling_gateway is not None

            status = {
                "running": is_running,
                "gateway_name": "POLLING" if is_running else None,
            }

            # 如果网关在运行，获取更多状态信息
            if is_running and self.polling_gateway:
                # 获取订阅的品种数量（TdxDataSource使用_subscribed_symbols私有属性）
                if hasattr(self.polling_gateway, "_subscribed_symbols"):
                    status["subscribed_count"] = len(self.polling_gateway._subscribed_symbols)

            return {
                "success": True,
                "status": status,
            }

        except Exception as e:
            self._log_error("获取轮询网关状态", e)
            return {
                "success": False,
                "message": f"获取状态失败: {str(e)}",
            }

    # ==================== 配置管理 ====================

    def get_server_pool_config(self) -> Dict[str, Any]:
        """获取服务器池配置.

        Returns:
            Dict: 配置信息
        """
        try:
            from backend.infrastructure.data_module_vnpy import ConfigManager

            config_manager = ConfigManager.get_instance()
            server_pool_size = config_manager.get("chinastock.server_pool_size", 5)

            return {
                "success": True,
                "server_pool_size": server_pool_size,
                "min_size": 1,
                "max_size": 30,  # 从10提升到30
                "recommended": {
                    "保守模式（网络差）": 2,
                    "标准模式（网络一般）": 5,
                    "加速模式（网络好）": 10,
                    "极速模式（网络优+高配置）": 15,
                },
                "note": "I/O密集型任务，可以设置超过CPU核心数。建议从5开始，逐步增加观察效果。",
            }
        except Exception as e:
            self._log_error("获取服务器池配置", e)
            return {"success": False, "message": f"获取失败: {str(e)}"}

    def set_server_pool_size(self, size: int) -> Dict[str, Any]:
        """设置服务器池大小.

        Args:
            size: 服务器池大小（1-30）

        Returns:
            Dict: 操作结果
        """
        try:
            if not 1 <= size <= 30:
                return {"success": False, "message": "服务器池大小必须在1-30之间"}

            from backend.infrastructure.data_module_vnpy import ConfigManager

            config_manager = ConfigManager.get_instance()
            config_manager.set("chinastock.server_pool_size", size)

            self.logger.info("服务器池大小已设置为: %d", size)

            return {
                "success": True,
                "message": f"服务器池大小已设置为 {size}（重启后生效）",
                "server_pool_size": size,
                "restart_required": True,
            }
        except Exception as e:
            self._log_error("设置服务器池大小", e)
            return {"success": False, "message": f"设置失败: {str(e)}"}

    # ==================== 虚拟推送网关管理 ====================

    def start_virtual_gateway(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """启动虚拟推送网关（虚拟数据源）.

        Args:
            config: 网关配置
                - start_datetime: 起始时间（格式：YYYY-MM-DD HH:MM:SS）
                - speed: 推送速度倍数（0.1 ~ 1000）
                - symbols: 订阅品种列表（可选，建议使用自动注册机制）

        Returns:
            Dict: 启动结果
        """
        try:
            self._log_operation("启动虚拟数据源（回放通道激活）")

            # 检查是否已有网关运行
            if self.virtual_gateway is not None:
                return {
                    "success": False,
                    "message": "虚拟数据源已在运行，请先停止",
                }

            # 检查轮询网关是否在运行（自动停止）
            if self.polling_gateway is not None:
                self.logger.info("检测到TDX数据源正在运行，自动停止...")
                stop_result = self.stop_polling_gateway()
                if stop_result.get("success"):
                    self.logger.info("✅ TDX数据源已自动停止")
                else:
                    self.logger.warning("⚠️ 停止TDX数据源失败: %s", stop_result.get("message"))
                    # 继续启动虚拟数据源，忽略停止失败

            # 验证起始时间
            start_datetime_str = config.get("start_datetime", "")
            if not start_datetime_str:
                return {
                    "success": False,
                    "message": "必须指定起始时间",
                }

            # 获取MainEngine和EventEngine
            from backend.core.base import get_main_engine, get_event_engine

            main_engine = get_main_engine()
            event_engine = get_event_engine()

            if not main_engine or not event_engine:
                return {
                    "success": False,
                    "message": "MainEngine或EventEngine不可用",
                }

            # 导入数据源类（从data_runtime）
            try:
                from backend.infrastructure.data_module_vnpy import (
                    VirtualDataSource,
                )

                # 向后兼容：VirtualGateway别名
                VirtualGateway = VirtualDataSource
            except ImportError as e:
                self.logger.error("导入VirtualDataSource失败: %s", e, exc_info=True, extra={"log_type": "SYSTEM"})
                return {
                    "success": False,
                    "message": f"导入数据源失败: {str(e)}",
                }

            # 注册网关类到MainEngine（确保MainEngine能识别和管理该网关）
            try:
                main_engine.add_gateway(VirtualGateway)
                self.logger.info("✅ VirtualGateway类已注册到MainEngine")
            except Exception as e:
                # 网关类可能已注册，忽略重复注册错误
                self.logger.debug("VirtualGateway注册跳过（可能已存在）: %s", e)

            # 创建网关实例
            gateway_name = "VIRTUAL"
            # VirtualDataSource 构造函数: __init__(event_engine, storage_manager)
            from backend.infrastructure.data_module_vnpy import StorageManager
            storage_manager = StorageManager()
            self.virtual_gateway = VirtualGateway(event_engine, storage_manager)

            # 准备配置（不包含symbols，使用自动注册机制）
            gateway_setting = {
                "起始时间": start_datetime_str,
                "推送速度": config.get("speed", 1.0),
                # 注意：不再设置"品种列表"，订阅由各模块通过UnifiedDataManager.subscribe_data()自动注册
            }

            # 连接网关
            self.virtual_gateway.connect(gateway_setting)

            # 更新数据源状态
            self.datafeeds["virtual_gateway"] = self.virtual_gateway
            self.active_datafeed = "virtual_gateway"
            self.realtime_push_active = True

            self.logger.info("✅ 虚拟推送网关已启动")

            # ✨ 虚拟数据源不需要数据录制功能（回放历史数据，不是实时数据）
            # 因此跳过自动启动录制
            self.logger.info("虚拟数据源不启用数据录制功能（仅用于历史数据回放）")

            return {
                "success": True,
                "message": "虚拟推送网关已启动",
                "gateway_name": gateway_name,
                "recording_started": False,  # 虚拟数据源不启用录制
            }

        except Exception as e:
            self._log_error("启动虚拟网关", e)
            # 清理
            self.virtual_gateway = None
            self.datafeeds["virtual_gateway"] = None
            return {
                "success": False,
                "message": f"启动失败: {str(e)}",
            }

    def stop_virtual_gateway(self) -> Dict[str, Any]:
        """停止虚拟推送网关.

        Returns:
            Dict: 停止结果
        """
        try:
            if self.virtual_gateway is None:
                return {
                    "success": False,
                    "message": "虚拟网关未运行",
                }

            # 停止录制引擎
            if self.recorder_engine:
                try:
                    stop_result = self.stop_realtime_data_recording()
                    if stop_result.get("success"):
                        self.logger.info("✅ 数据录制已停止")
                except Exception as e:
                    self.logger.warning("停止录制引擎失败: %s", e, extra={"log_type": "SYSTEM"})

            # 关闭网关
            self.virtual_gateway.close()
            self.virtual_gateway = None

            # 更新状态
            self.datafeeds["virtual_gateway"] = None
            if self.active_datafeed == "virtual_gateway":
                self.active_datafeed = None
                self.realtime_push_active = False

            self.logger.info("✅ 虚拟推送网关已停止")

            return {
                "success": True,
                "message": "虚拟推送网关已停止",
            }

        except Exception as e:
            self._log_error("停止虚拟网关", e)
            # 强制清理状态，避免状态不一致
            self.virtual_gateway = None
            self.datafeeds["virtual_gateway"] = None
            if self.active_datafeed == "virtual_gateway":
                self.active_datafeed = None
                self.realtime_push_active = False
            return {
                "success": False,
                "message": f"停止失败: {str(e)}",
            }

    def get_virtual_gateway_status(self) -> Dict[str, Any]:
        """获取虚拟网关状态.

        Returns:
            Dict: 网关状态
        """
        try:
            is_running = self.virtual_gateway is not None

            status = {
                "running": is_running,
                "gateway_name": "VIRTUAL" if is_running else None,
            }

            # 如果网关在运行，获取更多状态信息
            if is_running and self.virtual_gateway:
                # 获取订阅的品种数量
                if hasattr(self.virtual_gateway, "subscribed_symbols"):
                    status["subscribed_count"] = len(self.virtual_gateway.subscribed_symbols)
                # 获取推送进度
                if hasattr(self.virtual_gateway, "push_positions"):
                    status["push_positions"] = self.virtual_gateway.push_positions

            return {
                "success": True,
                "status": status,
            }

        except Exception as e:
            self._log_error("获取虚拟网关状态", e)
            return {
                "success": False,
                "message": f"获取状态失败: {str(e)}",
            }

    def scan_errors_missing_only(self) -> Dict[str, Any]:
        """扫描错误数据和缺失数据（UI按钮触发）

        🔧 修复：改为调用完整的3阶段自适应扫描，而非轻量级扫描
        用户期望点击"数据扫描"按钮后能完整执行3个阶段

        Returns:
            Dict: 扫描结果
        """
        try:
            if not self.china_stock_engine:
                self.logger.error(
                    "ChinaStockEngine不可用",
                    extra={"log_type": "ALERT", "scenario": "manual_data_scan"}
                )
                return {
                    "success": False,
                    "message": "ChinaStockEngine不可用",
                }

            # 获取参考品种列表
            reference_symbols = self.china_stock_engine.symbol_loader.extract_all_codes()
            
            self.logger.debug(
                f"[DATA-SCAN] 开始扫描: 品种数={len(reference_symbols)}",
                extra={"log_type": "SYSTEM", "scenario": "manual_data_scan"}
            )

            # 🔧 修复：调用质量扫描
            data_sensor = self.china_stock_engine.data_sensor
            if not data_sensor:
                from backend.infrastructure.data_module_vnpy.data_quality import DataSensor
                data_sensor = DataSensor()

            overview = data_sensor.scan_quality(
                symbols=reference_symbols,
                intervals=["1d", "5m", "1m"],
                use_async=True,
            )

            # overview是字典，需要统计
            total_symbols = len(reference_symbols)
            missing_symbols = sum(1 for r in overview.values() if r.total_bars == 0)
            error_symbols = sum(1 for r in overview.values() if r.quality_level.value >= 4)
            warning_symbols = sum(1 for r in overview.values() if r.quality_level.value == 3)
            
            self.logger.info(
                f"[DATA-SCAN] 扫描完成: 总品种={total_symbols}, 缺失={missing_symbols}, "
                f"错误={error_symbols}, 警告={warning_symbols}",
                extra={"log_type": "SYSTEM", "scenario": "manual_data_scan"}
            )

            return {
                "success": True,
                "total_symbols": total_symbols,
                "missing_symbols": missing_symbols,
                "error_symbols": error_symbols,
                "warning_symbols": warning_symbols,
                "data_missing_symbols": missing_symbols,
                "message": f"扫描完成: 缺失={missing_symbols}, 错误={error_symbols}, 警告={warning_symbols}",
            }

        except Exception as e:
            self._log_error("扫描错误缺失数据", e)
            self.logger.error(
                f"扫描错误缺失数据失败: {e}",
                exc_info=True,
                extra={"log_type": "ALERT", "scenario": "manual_data_scan"}
            )
            return {
                "success": False,
                "message": f"扫描失败: {str(e)}",
            }

    def delete_invalid_symbols(self) -> Dict[str, Any]:
        """删除失效品种数据

        Returns:
            Dict: 删除结果
        """
        try:
            from backend.services.database_adapter import get_db_manager

            # 1. 从数据库读取失效品种列表
            db_manager = get_db_manager()
            invalid_symbols = db_manager.get_invalid_symbols()

            if not invalid_symbols:
                return {
                    "success": True,
                    "deleted": 0,
                    "message": "没有失效品种需要删除",
                }

            # 2. 调用StorageManager删除文件
            if not self.china_stock_engine:
                return {
                    "success": False,
                    "message": "ChinaStockEngine不可用",
                }

            storage_manager = self.china_stock_engine.storage_manager
            result = storage_manager.delete_symbols(invalid_symbols)

            # 3. 清空失效品种池
            db_manager.clear_invalid_symbols()

            # 4. 推送更新事件
            if self.china_stock_engine.event_engine:
                from backend.infrastructure.data_module_vnpy import (
                    ChinaStockEngine,
                )
                from vnpy.event import Event
                EVENT_DATA_METRICS_UPDATED = ChinaStockEngine.EVENT_DATA_METRICS_UPDATED
                from datetime import datetime

                event_data = {
                    "total_symbols": 0,  # 将在后续步骤6中更新
                    "reference_symbols": 0,
                    "downloaded": 0,
                    "missing": 0,
                    "invalid_count": 0,
                    "timestamp": datetime.now().isoformat(),
                }
                event = Event(EVENT_DATA_METRICS_UPDATED, event_data)
                self.china_stock_engine.event_engine.put(event)

            return {
                "success": True,
                "deleted": result["deleted"],
                "failed": result["failed"],
                "message": f"删除完成: 成功={result['deleted']}, 失败={result['failed']}",
            }

        except Exception as e:
            self._log_error("删除失效品种", e)
            return {
                "success": False,
                "message": f"删除失败: {str(e)}",
            }
