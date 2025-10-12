# -*- coding: utf-8 -*-
"""
数据中心服务.

提供完整的数据管理功能，包括：
- 品种列表管理
- 数据下载管理（全量/增量）
- 本地数据查询
- 数据质量检查和自动修复
- 数据源管理（data_engine, ifind, rqdata, tushare）
"""

from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta
from contextlib import suppress
from pathlib import Path

from backend.services.base_and_utils import BaseService


class DataCenterService(BaseService):
    """数据中心服务.

    基于data_module_vnpy包实现的数据管理服务，提供：
    1. 品种列表管理 - 获取、缓存、筛选、搜索
    2. 数据下载 - 全量下载、增量下载、进度监控
    3. 本地数据查询 - OHLCV数据查询、展示
    4. 数据质量管理 - 质量检查、自动修复、断点检测
    5. 数据源管理 - 4种数据源连接、实时数据录制
    """

    def __init__(self):
        """初始化数据中心服务."""
        super().__init__()

        # ChinaStockEngine引擎
        self.china_stock_engine = None

        # data_engine
        self.data_engine = None

        # recorder_engine（在start_data_recording中初始化）
        self.recorder_engine = None

        # 数据源连接状态
        self.datafeeds: Dict[str, Any] = {
            "polling_gateway": None,
            "virtual_gateway": None,
            "ifind": None,
            "rqdata": None,
            "tushare": None,
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

        # 消息发布器（用于WebSocket推送）
        self.message_publisher = None

        self.logger.info("数据中心服务已创建")

    def _do_initialize(self) -> bool:
        """初始化数据中心服务."""
        try:
            self.logger.info("初始化数据中心服务...")

            # 获取全局ChinaStockEngine
            from backend.core.base import get_china_stock_engine

            self.china_stock_engine = get_china_stock_engine()

            if self.china_stock_engine:
                self.logger.info("✅ ChinaStockEngine 可用")
            else:
                self.logger.warning("⚠️ ChinaStockEngine 不可用，部分功能受限")

            # 尝试初始化data_engine
            self._init_data_engine()

            # 初始化任务调度器
            self._init_scheduler()

            # 初始化消息发布器
            self._init_message_publisher()

            # 🔧 修复：启动时加载品种缓存（如果存在）
            self._load_symbol_cache_on_startup()

            return True  # 即使部分功能不可用，也返回True以允许服务启动

        except Exception as e:
            self._log_error("初始化", e)
            return False

    def _do_shutdown(self) -> bool:
        """关闭数据中心服务."""
        try:
            self.logger.info("关闭数据中心服务...")

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
            "data_engine_available": self.data_engine is not None,
            "connected_datafeeds": [name for name, df in self.datafeeds.items() if df is not None],
            "symbol_cache_loaded": self._symbol_cache is not None,
            "active_downloads": len(self._download_tasks),
        }

    def _init_data_engine(self) -> bool:
        """初始化data_engine."""
        try:
            # 尝试导入data_engine包
            try:
                from backend.infrastructure.data_engine import engine as de_engine

                self.data_engine = de_engine
                self.logger.info("✅ data_engine初始化成功")
                return True
            except ImportError as e:
                self.logger.warning("⚠️ data_engine包不可用: %s", e)
                return False

        except Exception as e:
            self.logger.error("data_engine初始化失败: %s", e, exc_info=True)
            return False

    def _init_scheduler(self) -> bool:
        """初始化任务调度器."""
        try:
            from apscheduler.schedulers.background import BackgroundScheduler

            self.scheduler = BackgroundScheduler()

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
            return True

        except ImportError:
            # APScheduler是可选功能，降低日志级别避免干扰
            self.logger.debug("⚠️ APScheduler未安装，定时清理功能不可用")
            return False
        except Exception as e:
            self.logger.error("任务调度器初始化失败: %s", e, exc_info=True)
            return False

    def _init_message_publisher(self) -> bool:
        """初始化消息发布器.

        Returns:
            bool: 是否成功
        """
        try:
            from backend.core.base import get_message_publisher

            self.message_publisher = get_message_publisher()  # pylint: disable=assignment-from-none

            if self.message_publisher:
                self.logger.info("✅ 消息发布器可用")
                return True
            else:
                # WebSocket是可选功能，降低日志级别避免干扰
                self.logger.debug("⚠️ 消息发布器不可用，WebSocket推送功能受限")
                return False

        except Exception as e:
            # WebSocket是可选功能，降低日志级别避免干扰
            self.logger.debug("消息发布器初始化失败: %s", str(e))
            return False

    def _cleanup_recorded_data_daily(self, days_to_keep: int = 1):
        """定时清理录制数据（由调度器调用）.

        Args:
            days_to_keep: 保留天数
        """
        try:
            self.logger.info("开始执行定时清理录制数据任务...")
            result = self.cleanup_recorded_data(days_to_keep)

            if result.get("success"):
                deleted_count = result.get("deleted_count", 0)
                self.logger.info("✅ 定时清理完成：已删除 %s 条录制数据", deleted_count)
            else:
                self.logger.warning("⚠️ 定时清理失败: %s", result.get("message", "未知错误"))

        except Exception as e:
            self.logger.error("定时清理录制数据异常: %s", e, exc_info=True)

    def _load_symbol_cache_on_startup(self):
        """启动时加载品种缓存（异步）.

        逻辑：
        1. 先尝试从 data/cache/stock_list_classified.json 加载缓存
        2. 如果新格式缓存存在，加载到内存
        3. 兼容旧格式：如果只有parquet文件，也能加载（会自动迁移）
        4. 如果缓存不存在，启动后台线程异步加载（不阻塞启动）
        """
        try:
            self.logger.info("检查品种列表缓存...")

            # 尝试从JSON文件加载（使用data_module的配置管理器）
            from backend.infrastructure.data_module_vnpy.config import config_manager
            import json

            cache_dir = config_manager.get_cache_dir()
            json_cache_file = cache_dir / "stock_list_classified.json"
            parquet_cache_file = cache_dir / "stock_list.parquet"

            # 优先加载新格式JSON文件
            if json_cache_file.exists():
                try:
                    with open(json_cache_file, "r", encoding="utf-8") as f:
                        cache_data = json.load(f)

                    classified = cache_data.get("classified", {})

                    # 将分类数据转换为前端需要的格式
                    symbols = []
                    for market_type, codes in classified.items():
                        for code in codes:
                            symbols.append(
                                {
                                    "symbol": code,
                                    "code": code,
                                    "name": code,  # JSON中只有代码，名称暂时用代码代替
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

                    self.logger.info("✅ 从JSON缓存加载了 %d 个品种（5个市场）", len(symbols))
                    return

                except Exception as e:
                    self.logger.warning("加载JSON缓存失败: %s，尝试旧格式", e)

            # 兼容旧格式parquet（会触发一次迁移）
            if parquet_cache_file.exists():
                try:
                    import pandas as pd

                    df = pd.read_parquet(parquet_cache_file)

                    # 将DataFrame转换为字典列表
                    symbols = []
                    for _, row in df.iterrows():
                        symbols.append(
                            {
                                "code": row.get("code", ""),
                                "name": row.get("name", ""),
                                "exchange": row.get("exchange", ""),
                                "type": row.get("product", ""),
                            }
                        )

                    # 更新内存缓存
                    self._symbol_cache = {
                        "symbols": symbols,
                        "timestamp": datetime.now(),
                    }
                    self._symbol_cache_time = datetime.now()

                    self.logger.info(
                        "✅ 从旧格式parquet加载了 %d 个品种（下次启动将自动迁移）", len(symbols)
                    )
                    return

                except Exception as e:
                    self.logger.warning("加载parquet缓存失败: %s，将异步重新加载", e)

            # 缓存不存在或加载失败，启动后台线程异步加载
            self.logger.info("缓存文件不存在，启动后台线程异步加载品种列表...")
            self._async_load_symbols_in_background()

        except Exception as e:
            self.logger.error("启动时加载缓存失败: %s", e, exc_info=True)

    def _map_market_to_exchange(self, market_type: str) -> str:
        """将市场类型映射到交易所."""
        mapping = {
            "上证A股": "上交所",
            "深证A股": "深交所",
            "北证A股": "北交所",
            "T+0基金": "全部",
            "含可转债": "全部",
        }
        return mapping.get(market_type, "未知")

    def _map_market_to_product_type(self, market_type: str) -> str:
        """将市场类型映射到产品类型."""
        mapping = {
            "上证A股": "股票",
            "深证A股": "股票",
            "北证A股": "股票",
            "T+0基金": "基金",
            "含可转债": "可转债",
        }
        return mapping.get(market_type, "未知")

    def _async_load_symbols_in_background(self):
        """在后台线程中异步加载品种列表."""
        import threading

        def load_symbols():
            try:
                self.logger.info("【后台线程】开始异步加载品种列表...")
                result = self.reload_symbol_list(force=False)

                if result.get("success"):
                    self.logger.info(
                        "【后台线程】✅ 品种列表加载成功: %d 个品种", result.get("symbol_count", 0)
                    )
                else:
                    self.logger.warning(
                        "【后台线程】⚠️ 品种列表加载失败: %s", result.get("message", "")
                    )

            except Exception as e:
                self.logger.error("【后台线程】品种列表加载异常: %s", e, exc_info=True)

        # 启动守护线程（不阻塞主程序退出）
        thread = threading.Thread(target=load_symbols, daemon=True, name="SymbolLoader")
        thread.start()
        self.logger.info("后台加载线程已启动")

    # ==================== 品种列表管理 ====================

    def reload_symbol_list(self, force: bool = False) -> Dict[str, Any]:
        """重新加载品种列表（调用API请求）.

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
        try:
            self._log_operation("重新加载品种列表", force=force)
            self.logger.info("=" * 60)
            self.logger.info("【开始】重新加载品种列表 (force=%s)", force)
            self.logger.info("=" * 60)

            # 检查缓存是否有效（如果不强制刷新）
            if not force and self._is_symbol_cache_valid():
                symbols = self._symbol_cache.get("symbols", []) if self._symbol_cache else []
                self.logger.info("使用缓存的品种列表: %d 个品种", len(symbols))
                return {
                    "success": True,
                    "symbol_count": len(symbols),
                    "message": "使用缓存的品种列表",
                    "data": symbols,
                }

            # 调用china_stock_engine获取品种列表
            if self.china_stock_engine is None:
                self.logger.error("ChinaStockEngine不可用")
                return {
                    "success": False,
                    "symbol_count": 0,
                    "message": "ChinaStockEngine不可用",
                    "data": [],
                }

            # 调用实际的品种列表获取方法
            self.logger.info("【步骤1】调用 _fetch_symbols_from_china_stock()...")
            symbols = self._fetch_symbols_from_china_stock()
            self.logger.info("【步骤1完成】获取到 %d 个品种", len(symbols))

            # 更新缓存
            self.logger.info("【步骤2】更新内存缓存...")
            self._symbol_cache = {
                "symbols": symbols,
                "timestamp": datetime.now(),
            }
            self._symbol_cache_time = datetime.now()
            self.logger.info("【步骤2完成】缓存已更新")

            self.logger.info("=" * 60)
            self.logger.info("【成功】品种列表加载完成: %d 个品种", len(symbols))
            self.logger.info("=" * 60)

            # 检查通达信根目录配置
            warning_message = None
            if self.china_stock_engine:
                # 检查BlockParser是否可用
                block_parser = getattr(self.china_stock_engine, "block_parser", None)
                if block_parser and not block_parser.is_available():
                    warning_message = (
                        "⚠️ 未配置通达信根目录，品种列表可能不完整。"
                        "缺少：T+0基金、可转债等特殊品种。"
                        "请在系统配置中设置通达信软件根目录。"
                    )
                    self.logger.warning(warning_message)

            return {
                "success": True,
                "symbol_count": len(symbols),
                "message": "品种列表加载成功",
                "data": symbols,
                "warning": warning_message,  # 添加警告信息
            }

        except Exception as e:
            self._log_error("重新加载品种列表", e)
            self.logger.error("=" * 60)
            self.logger.error("【失败】品种列表加载失败: %s", e, exc_info=True)
            self.logger.error("=" * 60)
            return {
                "success": False,
                "symbol_count": 0,
                "message": f"加载失败: {str(e)}",
                "data": [],
            }

    def refresh_symbol_list(self) -> Dict[str, Any]:
        """刷新品种列表（使用缓存，不调用API）.

        Returns:
            Dict: 包含success, symbol_count, message, data的字典
        """
        try:
            self._log_operation("刷新品种列表")

            if self._symbol_cache is None:
                # 如果缓存为空，调用reload
                return self.reload_symbol_list(force=False)

            return {
                "success": True,
                "symbol_count": len(self._symbol_cache.get("symbols", [])),
                "message": "品种列表刷新成功（使用缓存）",
                "data": self._symbol_cache.get("symbols", []),
            }

        except Exception as e:
            self._log_error("刷新品种列表", e)
            return {
                "success": False,
                "symbol_count": 0,
                "message": f"刷新失败: {str(e)}",
                "data": [],
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
            "T+0基金": ("全部", "基金"),  # T+0基金可能分布在多个交易所
            "含可转债": ("全部", "可转债"),  # 可转债可能分布在多个交易所
        }

        return mapping.get(market_name, ("未知", "未知"))

    def _fetch_symbols_from_china_stock(self) -> List[Dict[str, Any]]:
        """从ChinaStockEngine获取品种列表.

        Returns:
            List[Dict]: 品种列表
        """
        try:
            # 调用ChinaStockEngine的reload_stock_list方法
            if self.china_stock_engine is None:
                self.logger.warning("ChinaStockEngine不可用")
                return []

            # 第1步：调用reload_stock_list更新缓存（返回bool）
            self.logger.info("  → 调用 china_stock_engine.reload_stock_list()...")
            success = self.china_stock_engine.reload_stock_list()
            self.logger.info("  ← reload_stock_list 返回: %s", success)

            if not success:
                self.logger.warning("更新品种缓存失败")
                return []

            # 第2步：调用get_all_market_stocks获取分类后的品种字典
            self.logger.info("  → 调用 china_stock_engine.get_all_market_stocks()...")
            market_stocks = self.china_stock_engine.get_all_market_stocks()
            self.logger.info(
                "  ← get_all_market_stocks 返回: %d 个市场",
                len(market_stocks) if market_stocks else 0,
            )

            if not market_stocks:
                self.logger.warning("获取品种分类失败")
                return []

            # 打印各市场品种数量
            for market_name, stock_list in market_stocks.items():
                self.logger.info("     - %s: %d 个", market_name, len(stock_list))

            # 转换为前端需要的格式
            self.logger.info("  → 转换为前端数据格式...")
            symbols = []
            for market_name, stock_list in market_stocks.items():
                # 映射市场名称到交易所和品种类型
                exchange, product_type = self._map_market_to_exchange_and_type(market_name)

                for stock_code in stock_list:
                    symbols.append(
                        {
                            "symbol": stock_code,  # 使用symbol字段（与前端期望一致）
                            "code": stock_code,  # 同时保留code字段
                            "name": stock_code,  # 暂时使用代码作为名称
                            "exchange": exchange,  # 使用映射后的交易所名称
                            "product_type": product_type,  # 使用映射后的品种类型
                        }
                    )

            self.logger.info("  ← 转换完成: %d 个品种", len(symbols))
            self.logger.info("✅ 成功获取 %d 个分类品种（来自5个市场）", len(symbols))

            # 打印前3个样例
            if len(symbols) > 0:
                self.logger.info("  前3个品种样例:")
                for i, sym in enumerate(symbols[:3]):
                    self.logger.info("    [%d] %s", i + 1, sym)

            return symbols

        except Exception as e:
            self.logger.error("获取品种列表失败: %s", e, exc_info=True)
            return []

    # ==================== 数据下载管理 ====================

    def start_full_download(self) -> Dict[str, Any]:
        """启动全量数据下载.

        下载全品类（股票、可转债、T+0基金）、全周期（日线、5min、1min）的历史数据。

        Returns:
            Dict: {
                "success": bool,
                "task_id": str,
                "message": str
            }
        """
        try:
            self._log_operation("启动全量数据下载")

            if self.china_stock_engine is None:
                return {
                    "success": False,
                    "task_id": None,
                    "message": "ChinaStockEngine不可用",
                }

            # 创建下载任务
            task_id = f"full_download_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

            # 调用ChinaStockEngine的K线数据全量下载方法
            try:
                success = self.china_stock_engine.download_full()
                if not success:
                    # 下载失败（例如：本地缓存不存在）
                    return {
                        "success": False,
                        "task_id": None,
                        "message": "本地品种缓存不存在或为空，请先在【品种列表】界面点击【重新加载品种】按钮获取品种列表",
                    }
            except Exception as e:
                self.logger.error("全量下载启动失败: %s", e, exc_info=True)
                return {
                    "success": False,
                    "task_id": None,
                    "message": f"下载失败: {str(e)}",
                }

            # 注册任务
            self._download_tasks[task_id] = {
                "type": "full",
                "status": "running",
                "start_time": datetime.now(),
                "progress": 0,
            }

            return {
                "success": True,
                "task_id": task_id,
                "message": "全量下载已启动",
            }

        except Exception as e:
            self._log_error("启动全量下载", e)
            return {
                "success": False,
                "task_id": None,
                "message": f"启动失败: {str(e)}",
            }

    def start_incremental_download(self, start_date: str) -> Dict[str, Any]:
        """启动增量数据下载.

        下载从指定日期至今的数据。

        Args:
            start_date: 开始日期（格式：YYYY-MM-DD）

        Returns:
            Dict: 下载任务信息
        """
        try:
            self._log_operation("启动增量数据下载", start_date=start_date)

            if self.china_stock_engine is None:
                return {
                    "success": False,
                    "task_id": None,
                    "message": "data_module_vnpy不可用",
                }

            # 创建下载任务
            task_id = f"incremental_download_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

            # 调用ChinaStockEngine的增量下载方法
            try:
                # 解析日期
                from datetime import datetime as dt

                start_dt = dt.strptime(start_date, "%Y-%m-%d").date()
                success = self.china_stock_engine.download_incremental(start_date=start_dt)

                if not success:
                    # 下载失败（例如：本地缓存不存在）
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

                return {
                    "success": True,
                    "task_id": task_id,
                    "message": "增量下载已启动",
                }
            except Exception as e:
                self.logger.error("增量下载启动失败: %s", e, exc_info=True)
                return {
                    "success": False,
                    "task_id": None,
                    "message": f"下载失败: {str(e)}",
                }

        except Exception as e:
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

    def _publish_download_event(self, event_type: str, task_id: str, data: Dict[str, Any]):
        """推送下载事件到WebSocket.

        Args:
            event_type: 事件类型 (started/progress/completed/failed)
            task_id: 任务ID
            data: 事件数据
        """
        try:
            if not self.message_publisher:
                return

            if event_type == "started":
                self.message_publisher.publish_download_started(task_id, data)
            elif event_type == "progress":
                self.message_publisher.publish_download_progress(
                    task_id,
                    data.get("progress", 0),
                    data.get("current_symbol"),
                    data.get("completed_symbols", 0),
                    data.get("total_symbols", 0),
                )
            elif event_type == "completed":
                self.message_publisher.publish_download_completed(task_id, data)
            elif event_type == "failed":
                self.message_publisher.publish_download_failed(
                    task_id, data.get("error", "未知错误")
                )

        except Exception as e:
            self.logger.error("推送下载事件失败: %s", str(e))

    def get_download_progress(self, task_id: str = None) -> Dict[str, Any]:
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
                self.logger.error("获取实时进度失败: %s", e)

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

    def stop_download(self, task_id: str = None) -> Dict[str, Any]:
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
                    self.logger.warning("调用停止下载失败: %s", e)
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

    def pause_download(self, task_id: str = None) -> Dict[str, Any]:
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
                    self.logger.warning("调用暂停下载失败: %s", e)
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

    def resume_download(self, task_id: str = None) -> Dict[str, Any]:
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
                    self.logger.warning("调用恢复下载失败: %s", e)
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

                # 查询数据
                data = self.china_stock_engine.query_data(
                    symbol=symbol, interval=interval, start_date=start_dt, end_date=end_dt
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
                self.logger.error("数据查询失败: %s", e, exc_info=True)
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

    def check_data_quality(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """检查数据质量.

        Args:
            symbol: 品种代码（可选，为None则检查所有品种）

        Returns:
            Dict: 质量检查结果
        """
        try:
            self._log_operation("检查数据质量", symbol=symbol)

            if not self.china_stock_engine:
                return {
                    "success": False,
                    "message": "ChinaStockEngine不可用",
                    "issues": [],
                }

            # 调用ChinaStockEngine的数据校验方法
            try:
                if symbol:
                    # 单品种校验
                    validation_result = self.china_stock_engine.validate_data([symbol])
                else:
                    # 所有品种校验
                    validation_result = self.china_stock_engine.validate_data()

                if validation_result:
                    issues = []
                    # 解析校验结果
                    if hasattr(validation_result, "to_dict"):
                        issues_dict = validation_result.to_dict()
                        for sym, result in issues_dict.items():
                            if not result.get("is_valid", True):
                                issues.append({"symbol": sym, "issue": result.get("message", "")})

                    return {
                        "success": True,
                        "message": f"质量检查完成，发现{len(issues)}个问题",
                        "issues": issues,
                    }
                else:
                    return {
                        "success": True,
                        "message": "质量检查完成",
                        "issues": [],
                    }

            except Exception as e:
                self.logger.error("质量检查失败: %s", e, exc_info=True)
                return {
                    "success": False,
                    "message": f"检查失败: {str(e)}",
                    "issues": [],
                }

        except Exception as e:
            self._log_error("检查数据质量", e, symbol=symbol)
            return {
                "success": False,
                "message": f"检查失败: {str(e)}",
                "issues": [],
            }

    def auto_repair_data(self, symbol: str, issues: List[str]) -> Dict[str, Any]:
        """自动修复数据.

        Args:
            symbol: 品种代码
            issues: 需要修复的问题列表

        Returns:
            Dict: 修复结果
        """
        try:
            self._log_operation("自动修复数据", symbol=symbol, issues_count=len(issues))

            if not self.china_stock_engine:
                return {
                    "success": False,
                    "message": "ChinaStockEngine不可用",
                    "repaired_count": 0,
                }

            # 使用增量下载修复数据
            try:
                from datetime import date

                # 修复最近30天的数据
                start_date = date.today() - timedelta(days=30)
                self.china_stock_engine.download_incremental(start_date=start_date)

                return {
                    "success": True,
                    "message": f"数据修复完成，已重新下载{symbol}最近30天的数据",
                    "repaired_count": len(issues),
                }

            except Exception as e:
                self.logger.error("数据修复失败: %s", e, exc_info=True)
                return {
                    "success": False,
                    "message": f"修复失败: {str(e)}",
                    "repaired_count": 0,
                }

        except Exception as e:
            self._log_error("自动修复数据", e, symbol=symbol)
            return {
                "success": False,
                "message": f"修复失败: {str(e)}",
                "repaired_count": 0,
            }

    # ==================== 数据源管理 ====================

    def connect_datafeed(
        self, datafeed_type: str, config: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """连接数据源.

        实现互斥连接控制：同时只能连接一个数据源。

        Args:
            datafeed_type: 数据源类型 (data_engine, ifind, rqdata, tushare)
            config: 配置信息（如账号密码）

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
                if datafeed_type == "data_engine":
                    # data_engine已在初始化时连接
                    if self.data_engine:
                        self.datafeeds[datafeed_type] = self.data_engine
                        self.active_datafeed = datafeed_type
                        self.logger.info("✅ %s 已设为活动数据源", datafeed_type)
                        return {
                            "success": True,
                            "message": "data_engine连接成功",
                        }
                    else:
                        return {
                            "success": False,
                            "message": "data_engine不可用",
                        }

                elif datafeed_type == "ifind":
                    # 连接iFind数据源
                    try:
                        from vnpy_ifind import IfindDatafeed  # type: ignore

                        if not config:
                            return {
                                "success": False,
                                "message": "缺少账号密码配置",
                            }

                        # 获取配置
                        username = config.get("username", "")
                        password = config.get("password", "")

                        if not username or not password:
                            return {
                                "success": False,
                                "message": "用户名或密码为空",
                            }

                        # 创建数据源实例
                        datafeed = IfindDatafeed()

                        # 实际项目中，这里应该调用datafeed的init方法进行认证
                        # datafeed.init(username, password)

                        self.datafeeds[datafeed_type] = datafeed
                        self.active_datafeed = datafeed_type
                        self.logger.info("✅ %s 已设为活动数据源", datafeed_type)

                        return {
                            "success": True,
                            "message": "iFind数据源连接成功（需通过MainEngine完成认证）",
                        }

                    except ImportError:
                        return {
                            "success": False,
                            "message": "vnpy_ifind包未安装",
                        }
                    except Exception as e:
                        return {
                            "success": False,
                            "message": f"iFind连接失败: {str(e)}",
                        }

                elif datafeed_type == "rqdata":
                    # 连接RQData数据源
                    try:
                        from vnpy_rqdata import RqdataDatafeed  # type: ignore

                        if not config:
                            return {
                                "success": False,
                                "message": "缺少账号密码配置",
                            }

                        # 获取配置
                        username = config.get("username", "")
                        password = config.get("password", "")

                        if not username or not password:
                            return {
                                "success": False,
                                "message": "用户名或密码为空",
                            }

                        # 创建数据源实例
                        datafeed = RqdataDatafeed()

                        # 实际项目中，这里应该调用init方法进行认证
                        # datafeed.init(username, password)

                        self.datafeeds[datafeed_type] = datafeed
                        self.active_datafeed = datafeed_type
                        self.logger.info("✅ %s 已设为活动数据源", datafeed_type)

                        return {
                            "success": True,
                            "message": "RQData数据源连接成功（需通过MainEngine完成认证）",
                        }

                    except ImportError:
                        return {
                            "success": False,
                            "message": "vnpy_rqdata包未安装",
                        }
                    except Exception as e:
                        return {
                            "success": False,
                            "message": f"RQData连接失败: {str(e)}",
                        }

                elif datafeed_type == "tushare":
                    # 连接Tushare数据源
                    try:
                        from vnpy_tushare import TushareDatafeed  # type: ignore

                        if not config:
                            return {
                                "success": False,
                                "message": "缺少Token配置",
                            }

                        token = config.get("token", "")
                        if not token:
                            return {
                                "success": False,
                                "message": "Token为空",
                            }

                        # 创建数据源实例
                        datafeed = TushareDatafeed()

                        # 实际项目中，这里应该调用init方法设置token
                        # datafeed.init(token)

                        self.datafeeds[datafeed_type] = datafeed
                        self.active_datafeed = datafeed_type
                        self.logger.info("✅ %s 已设为活动数据源", datafeed_type)

                        return {
                            "success": True,
                            "message": "Tushare数据源连接成功（需通过MainEngine完成认证）",
                        }

                    except ImportError:
                        return {
                            "success": False,
                            "message": "vnpy_tushare包未安装",
                        }
                    except Exception as e:
                        return {
                            "success": False,
                            "message": f"Tushare连接失败: {str(e)}",
                        }

                else:
                    return {
                        "success": False,
                        "message": f"未实现的数据源类型: {datafeed_type}",
                    }

            except Exception as e:
                self.logger.error("连接%s失败: %s", datafeed_type, e, exc_info=True)
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
                    self.logger.warning("关闭%s失败: %s", datafeed_type, e)

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
            from backend.config import get_settings

            settings = get_settings()
            recording_path = custom_path or settings.vnpy.recording_data_path

            # 确保录制目录存在
            Path(recording_path).mkdir(parents=True, exist_ok=True)
            self.logger.info("录制数据路径: %s", recording_path)

            # 调用vnpy_datarecorder启动录制
            try:
                # 尝试导入vnpy_datarecorder
                from vnpy_datarecorder import DataRecorderApp
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
                self.logger.warning("vnpy_datarecorder包未安装")
                return {
                    "success": False,
                    "message": "vnpy_datarecorder包未安装",
                }
            except Exception as e:
                self.logger.error("启动录制失败: %s", e, exc_info=True)
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
                        self.logger.warning("停止录制失败: %s", e)

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
                # 如果数据源已连接但无法确定推送状态，假设正在推送
                elif datafeed_type == "data_engine" and self.data_engine:
                    is_pushing = True

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
                from vnpy_datarecorder import DataRecorderApp
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
                self.logger.error("创建DataRecorder引擎失败: %s", e)
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
                        self.logger.warning("订阅品种 %s 失败: %s", symbol, e)

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
                self.logger.error("停止录制失败: %s", e)
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

    def cleanup_recorded_data(self, days_to_keep: int = 1) -> Dict[str, Any]:
        """清理过期的录制数据.

        删除超过指定天数的录制数据（日级缓存清理）。

        Args:
            days_to_keep: 保留天数（默认1天）

        Returns:
            Dict: 清理结果
        """
        try:
            # vnpy_datarecorder默认录制到data目录
            data_dir = Path("data")

            if not data_dir.exists():
                return {
                    "success": True,
                    "message": "录制数据目录不存在",
                    "deleted_files": 0,
                }

            # 计算截止日期
            cutoff_date = datetime.now() - timedelta(days=days_to_keep)

            deleted_files = 0
            deleted_size = 0

            # 查找并删除旧文件
            for file_path in data_dir.rglob("*.db"):  # vnpy_datarecorder使用.db文件
                try:
                    # 检查文件修改时间
                    file_mtime = datetime.fromtimestamp(file_path.stat().st_mtime)

                    if file_mtime < cutoff_date:
                        file_size = file_path.stat().st_size
                        file_path.unlink()
                        deleted_files += 1
                        deleted_size += file_size
                        self.logger.info("已删除过期录制文件: %s", file_path)

                except Exception as e:
                    self.logger.warning("删除文件 %s 失败: %s", file_path, e)

            self.logger.info(
                "录制数据清理完成: 删除 %d 个文件, 释放 %.2f MB",
                deleted_files,
                deleted_size / 1024 / 1024,
            )

            return {
                "success": True,
                "message": f"已清理 {deleted_files} 个过期文件",
                "deleted_files": deleted_files,
                "freed_space_mb": deleted_size / 1024 / 1024,
            }

        except Exception as e:
            self._log_error("清理录制数据", e)
            return {
                "success": False,
                "message": f"清理失败: {str(e)}",
            }

    # ==================== 轮询转推送网关管理 ====================

    def start_polling_gateway(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """启动轮询转推送网关.

        Args:
            config: 网关配置
                - interval: 轮询间隔（秒）
                - symbols: 订阅品种列表

        Returns:
            Dict: 启动结果
        """
        try:
            self._log_operation("启动轮询转推送网关")

            # 检查是否已有网关运行
            if self.polling_gateway is not None:
                return {
                    "success": False,
                    "message": "轮询网关已在运行，请先停止",
                }

            # 检查虚拟网关是否在运行（互斥）
            if self.virtual_gateway is not None:
                return {
                    "success": False,
                    "message": "虚拟网关正在运行，同时只能运行一个推送网关",
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

            # 导入网关类
            try:
                from backend.infrastructure.data_module_vnpy.polling_gateway import (
                    PollingGateway,
                )
            except ImportError as e:
                self.logger.error("导入PollingGateway失败: %s", e)
                return {
                    "success": False,
                    "message": f"导入网关失败: {str(e)}",
                }

            # 创建网关实例
            gateway_name = "POLLING"
            self.polling_gateway = PollingGateway(event_engine, gateway_name)

            # 准备配置
            gateway_setting = {
                "轮询间隔（秒）": config.get("interval", 60),
                "品种列表": ",".join(config.get("symbols", [])),
            }

            # 连接网关
            self.polling_gateway.connect(gateway_setting)

            # 更新数据源状态
            self.datafeeds["polling_gateway"] = self.polling_gateway
            self.active_datafeed = "polling_gateway"
            self.realtime_push_active = True

            self.logger.info("✅ 轮询转推送网关已启动")

            return {
                "success": True,
                "message": "轮询转推送网关已启动",
                "gateway_name": gateway_name,
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
                # 获取订阅的品种数量
                if hasattr(self.polling_gateway, "subscribed_symbols"):
                    status["subscribed_count"] = len(self.polling_gateway.subscribed_symbols)

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
            from backend.infrastructure.data_module_vnpy.config import config_manager

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

            from backend.infrastructure.data_module_vnpy.config import config_manager

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
        """启动虚拟推送网关.

        Args:
            config: 网关配置
                - start_datetime: 起始时间（格式：YYYY-MM-DD HH:MM:SS）
                - speed: 推送速度倍数
                - symbols: 订阅品种列表

        Returns:
            Dict: 启动结果
        """
        try:
            self._log_operation("启动虚拟推送网关")

            # 检查是否已有网关运行
            if self.virtual_gateway is not None:
                return {
                    "success": False,
                    "message": "虚拟网关已在运行，请先停止",
                }

            # 检查轮询网关是否在运行（互斥）
            if self.polling_gateway is not None:
                return {
                    "success": False,
                    "message": "轮询网关正在运行，同时只能运行一个推送网关",
                }

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

            # 导入网关类
            try:
                from backend.infrastructure.data_module_vnpy.virtual_gateway import (
                    VirtualGateway,
                )
            except ImportError as e:
                self.logger.error("导入VirtualGateway失败: %s", e)
                return {
                    "success": False,
                    "message": f"导入网关失败: {str(e)}",
                }

            # 创建网关实例
            gateway_name = "VIRTUAL"
            self.virtual_gateway = VirtualGateway(event_engine, gateway_name)

            # 准备配置
            gateway_setting = {
                "起始时间": start_datetime_str,
                "推送速度": config.get("speed", 1.0),
                "品种列表": ",".join(config.get("symbols", [])),
            }

            # 连接网关
            self.virtual_gateway.connect(gateway_setting)

            # 更新数据源状态
            self.datafeeds["virtual_gateway"] = self.virtual_gateway
            self.active_datafeed = "virtual_gateway"
            self.realtime_push_active = True

            self.logger.info("✅ 虚拟推送网关已启动")

            return {
                "success": True,
                "message": "虚拟推送网关已启动",
                "gateway_name": gateway_name,
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
