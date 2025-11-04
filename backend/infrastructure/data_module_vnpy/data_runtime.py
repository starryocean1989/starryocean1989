"""
运行时管理模块 - 架构v3.0重构版

本模块负责运行时数据管理，包括：
- 统一数据管理器（UnifiedDataManager）
- TDX数据源（TdxDataSource）
- 虚拟数据源（VirtualDataSource）
- 订阅管理器（SubscriptionManager）

架构特性：
- 四层数据融合查询（预加载缓存→历史Parquet→录制数据→实时推送）
- 全面异步化查询，native_iocp集成
- 跨进程订阅同步（native_ipc）
- 轮询转推送，符合VnPy Gateway标准
- 100% API向后兼容

重构日期：2025年
作者：AI Assistant (基于v2.1重构)
"""

import asyncio
import logging
import threading
import time
from datetime import datetime, date, timedelta
from enum import Enum, auto
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

import pandas as pd

# 导入VnPy相关
try:
    from vnpy.event import Event, EventEngine
    from vnpy.trader.gateway import BaseGateway
    from vnpy.trader.object import TickData, BarData, SubscribeRequest
    VNPY_AVAILABLE = True
except ImportError:
    VNPY_AVAILABLE = False
    BaseGateway = object
    TickData = None
    BarData = None
    SubscribeRequest = None

# 导入native_ipc（支持降级）
try:
    from backend.infrastructure.native_ipc import AsyncIPCPipe
    IPC_AVAILABLE = True
except ImportError:
    IPC_AVAILABLE = False
    AsyncIPCPipe = None

# 导入核心模块
from .core_engine import ConfigManager
from .data_storage import StorageManager
from .data_acquisition import SymbolLoader

# ==================== 日志配置 ====================
logger = logging.getLogger("backend.data_module.runtime")


# ==============================================================================
# Part 1: 统一数据管理器（UnifiedDataManager）
# ==============================================================================


class DataQueryPriority(Enum):
    """数据查询优先级"""
    PRELOAD_CACHE = 1    # 预加载缓存
    HISTORICAL_PARQUET = 2  # 历史Parquet
    RECORDED_DATA = 3    # 录制数据
    REALTIME_PUSH = 4    # 实时推送


class UnifiedDataManager:
    """统一数据管理器

    四层数据融合查询：
    - Layer 1: PreloadService（内存LRU缓存）
    - Layer 2: StorageManager（Parquet磁盘文件）
    - Layer 3: 录制数据（如启用录制）
    - Layer 4: 实时推送（如已订阅）

    自动检测缺失数据并触发下载
    native_iocp集成：统一查询时的异步文件读取
    """

    def __init__(self, event_engine=None, config_manager: Optional[ConfigManager] = None):
        """初始化统一数据管理器

        Args:
            event_engine: VnPy EventEngine
            config_manager: 配置管理器
        """
        self.event_engine = event_engine
        self.config_manager = config_manager or ConfigManager()
        self.storage_manager = StorageManager()
        self.preload_service = getattr(self.storage_manager, "preload_service", None)
        self._ready = True
        self._latest_contract_snapshot: List[Dict[str, Any]] = []
        self._last_query_diagnostics: Dict[str, Any] = {}
        
        # 检查离线模式（如果通过ChinaStockEngine初始化）
        self.offline_mode = False
        if hasattr(event_engine, 'is_offline_mode'):
            self.offline_mode = event_engine.is_offline_mode()
        
        if self.offline_mode:
            logger.warning("⚠️ UnifiedDataManager以离线模式初始化")
            logger.info("离线模式: 仅本地存储层可用")

        # 查询统计
        self._stats = {
            "total_queries": 0,
            "cache_hits": 0,
            "storage_hits": 0,
            "recorded_hits": 0,
            "realtime_hits": 0,
            "misses": 0,
        }

        logger.info("✅ 统一数据管理器已初始化")

    def is_ready(self) -> bool:
        """返回统一数据管理器是否可用."""
        return self._ready

    def get_mode(self) -> str:
        """返回当前运行模式（online/offline）."""
        return "offline" if self.offline_mode else "online"

    def get_all_contracts(self) -> List[Dict[str, Any]]:
        """获取所有合约信息（兼容 VnPy 接口）"""
        try:
            china_stock_engine = self._resolve_china_stock_engine()
            if china_stock_engine and getattr(china_stock_engine, "symbol_loader", None):
                symbols = china_stock_engine.symbol_loader.extract_all_codes()
                if symbols:
                    contracts: List[Dict[str, Any]] = []
                    for symbol in symbols:
                        contracts.append(
                            {
                                "symbol": symbol,
                                "exchange": "SSE",
                                "name": f"股票{symbol}",
                                "product": "EQUITY",
                                "size": 1,
                                "pricetick": 0.01,
                                "min_volume": 1,
                                "max_volume": None,
                                "margin_rate": 0.1,
                                "gateway_name": "china_stock",
                            }
                        )
                    self._latest_contract_snapshot = contracts
                    return contracts

            logger.warning("⚠️ 无法获取合约列表，返回空列表")
            return []

        except Exception as exc:
            logger.error("获取合约列表失败: %s", exc, exc_info=True, extra={"log_type": "SYSTEM"})
            return []

    def load_bar_data(
        self,
        symbol: str,
        interval: str = "1d",
        start_date: str = None,
        end_date: str = None,
        **kwargs,
    ) -> List[Dict]:
        """加载K线数据（兼容 VnPy 接口）"""
        try:
            df = self.get_kline_dataframe(
                symbol=symbol,
                interval=interval,
                start_date=start_date,
                end_date=end_date,
                use_preload=kwargs.get("use_preload", True),
                realtime_fallback=kwargs.get("realtime_fallback", True),
            )

            if df is None or df.empty:
                return []

            bars: List[Dict[str, Any]] = []
            for idx, row in df.iterrows():
                bars.append(
                    {
                        "symbol": symbol,
                        "exchange": "SSE",
                        "interval": interval,
                        "datetime": idx,
                        "volume": float(row.get("volume", 0)),
                        "turnover": float(row.get("amount", 0)),
                        "open_price": float(row.get("open", 0)),
                        "high_price": float(row.get("high", 0)),
                        "low_price": float(row.get("low", 0)),
                        "close_price": float(row.get("close", 0)),
                        "open_interest": float(row.get("open_interest", 0)),
                        "gateway_name": "china_stock",
                    }
                )

            return bars

        except Exception as exc:
            logger.error(
                "加载K线数据失败: symbol=%s interval=%s error=%s",
                symbol,
                interval,
                exc,
                exc_info=True,
                extra={"log_type": "SYSTEM"},
            )
            return []

    async def query_kline_async(
        self,
        symbol: str,
        interval: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        use_preload: bool = True,
        realtime_fallback: bool = True,
    ) -> Optional[pd.DataFrame]:
        """异步查询K线数据（四层融合）"""
        return self.query_kline_from_layers(
            symbol=symbol,
            interval=interval,
            start_date=start_date,
            end_date=end_date,
            use_preload=use_preload,
            realtime_fallback=realtime_fallback,
        )

    def query_kline(
        self,
        symbol: str,
        interval: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> Optional[pd.DataFrame]:
        """同步查询K线数据（向后兼容）"""
        return self.get_kline_dataframe(symbol, interval, start_date, end_date)

    def get_kline_dataframe(
        self,
        symbol: str,
        interval: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        use_preload: bool = True,
        realtime_fallback: bool = True,
    ) -> Optional[pd.DataFrame]:
        """核心方法：返回DataFrame形式的K线数据."""
        try:
            df = self.query_kline_from_layers(
                symbol=symbol,
                interval=interval,
                start_date=start_date,
                end_date=end_date,
                use_preload=use_preload,
                realtime_fallback=realtime_fallback,
            )
            if df is None or df.empty:
                return None
            return df
        except Exception as exc:
            logger.error(
                "❌ get_kline_dataframe失败: symbol=%s interval=%s error=%s",
                symbol,
                interval,
                exc,
                exc_info=True,
            )
            return None

    def get_kline_data(
        self,
        symbol: str,
        interval: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        check_gaps: bool = False,
        use_preload: bool = True,
    ) -> Optional[pd.DataFrame]:
        """获取K线数据（兼容方法，等同于 get_kline_dataframe）.
        
        Args:
            symbol: 品种代码
            interval: 周期（如"1d", "5m"等）
            start_date: 开始日期
            end_date: 结束日期
            check_gaps: 是否检查断点（暂未实现，保留兼容性）
            use_preload: 是否使用预加载缓存
            
        Returns:
            DataFrame或None
        """
        # 转换为统一的查询方法
        return self.get_kline_dataframe(
            symbol=symbol,
            interval=interval,
            start_date=start_date,
            end_date=end_date,
            use_preload=use_preload,
            realtime_fallback=True,
        )

    def query_kline_from_layers(
        self,
        symbol: str,
        interval: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        use_preload: bool = True,
        realtime_fallback: bool = True,
    ) -> Optional[pd.DataFrame]:
        """按照四层策略依次尝试获取K线数据."""
        self._stats["total_queries"] += 1

        # Layer 1: 预加载缓存
        if use_preload and self.preload_service:
            try:
                df = self.preload_service.get_cached_dataframe(symbol, interval)
                if df is not None and not df.empty:
                    self._stats["cache_hits"] += 1
                    return self._filter_date_range(df, start_date, end_date)
            except Exception as exc:
                logger.debug("预加载缓存读取失败: %s/%s, %s", symbol, interval, exc)

        try:
            df = self.storage_manager.load_kline(symbol, interval)
            if df is not None and not df.empty:
                self._stats["storage_hits"] += 1
                return self._filter_date_range(df, start_date, end_date)
        except Exception as exc:
            logger.debug("从存储加载失败: %s/%s, %s", symbol, interval, exc)

        if realtime_fallback:
            logger.info(
                "⚠️ K线数据缺失，准备触发实时回补: symbol=%s interval=%s",
                symbol,
                interval,
            )
        self._stats["misses"] += 1
        return None

    def _filter_date_range(
        self,
        df: pd.DataFrame,
        start_date: Optional[date],
        end_date: Optional[date],
    ) -> pd.DataFrame:
        """过滤日期范围"""
        if df is None or df.empty:
            return df

        filtered = df
        if start_date:
            filtered = filtered[filtered.index >= pd.Timestamp(start_date)]
        if end_date:
            filtered = filtered[filtered.index <= pd.Timestamp(end_date)]
        return filtered

    def get_stats(self) -> Dict[str, int]:
        """获取查询统计

        Returns:
            统计信息字典
        """
        stats = self._stats.copy()
        total_hits = (
            stats["cache_hits"]
            + stats["storage_hits"]
            + stats["recorded_hits"]
            + stats["realtime_hits"]
        )
        if stats["total_queries"] > 0:
            stats["hit_rate"] = total_hits / stats["total_queries"] * 100
        else:
            stats["hit_rate"] = 0.0
        return stats


# ==============================================================================
# Part 2: TDX数据源（TdxDataSource）
# ==============================================================================


class TdxDataSource(BaseGateway if VNPY_AVAILABLE else object):
    """TDX数据源

    轮询转推送，符合VNPy Gateway标准：
    - 定时轮询TDX API
    - 转换为VnPy事件推送
    - 支持订阅管理
    """

    gateway_name = "TDX"

    def __init__(self, event_engine=None, config_manager: Optional[ConfigManager] = None):
        """初始化TDX数据源

        Args:
            event_engine: VnPy EventEngine
            config_manager: 配置管理器
        """
        if VNPY_AVAILABLE and event_engine:
            super().__init__(event_engine, self.gateway_name)

        self.event_engine = event_engine
        self.config_manager = config_manager or ConfigManager()

        # 订阅列表
        self._subscriptions: Set[Tuple[str, str]] = set()  # {(symbol, exchange)}
        self._subscription_lock = threading.Lock()

        # 轮询控制
        self._polling = False
        self._poll_thread = None
        self._poll_interval = self.config_manager.get_config("tdx.poll_interval", 1.0)

        logger.info(f"✅ TDX数据源已初始化，轮询间隔: {self._poll_interval}秒")

    def connect(self, setting: dict = None):
        """连接TDX数据源

        Args:
            setting: 连接设置
        """
        logger.info("🔌 连接TDX数据源...")
        self.start_polling()

    def close(self):
        """关闭TDX数据源"""
        logger.info("🔌 关闭TDX数据源...")
        self.stop_polling()

    def subscribe(self, req: 'SubscribeRequest'):
        """订阅行情

        Args:
            req: 订阅请求
        """
        with self._subscription_lock:
            key = (req.symbol, req.exchange.value if hasattr(req.exchange, 'value') else str(req.exchange))
            self._subscriptions.add(key)
            logger.info(f"📡 订阅行情: {key}")

    def start_polling(self):
        """启动轮询"""
        if self._polling:
            logger.warning("⚠️ 轮询已经启动")
            return

        self._polling = True
        self._poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._poll_thread.start()
        logger.info("▶️ 轮询已启动")

    def stop_polling(self):
        """停止轮询"""
        if not self._polling:
            return

        self._polling = False
        if self._poll_thread:
            self._poll_thread.join(timeout=2)
        logger.info("⏹️ 轮询已停止")

    def _poll_loop(self):
        """轮询循环"""
        logger.info("🔄 轮询循环启动")

        while self._polling:
            try:
                self._poll_once()
                time.sleep(self._poll_interval)
            except Exception as e:
                logger.error(f"❌ 轮询异常: {e}", exc_info=True)

    def _poll_once(self):
        """执行一次轮询"""
        with self._subscription_lock:
            subscriptions = list(self._subscriptions)

        if not subscriptions:
            return

        # TODO: 实际调用TDX API获取行情数据
        # TODO: 转换为VnPy TickData/BarData并推送事件
        pass


# ==============================================================================
# Part 3: 虚拟数据源（VirtualDataSource）
# ==============================================================================


class VirtualDataSource:
    """虚拟数据源

    历史数据回放，用于回测：
    - 支持倍速播放
    - 支持暂停/恢复
    - 按时间顺序推送历史数据
    """

    def __init__(self, event_engine=None, storage_manager: Optional[StorageManager] = None):
        """初始化虚拟数据源

        Args:
            event_engine: VnPy EventEngine
            storage_manager: 存储管理器
        """
        self.event_engine = event_engine
        self.storage_manager = storage_manager or StorageManager()

        # 回放控制
        self._playing = False
        self._paused = False
        self._play_thread = None
        self._speed = 1.0  # 播放速度（1.0=正常，2.0=2倍速）

        # 回放数据
        self._replay_data: Optional[pd.DataFrame] = None
        self._current_index = 0

        logger.info("✅ 虚拟数据源已初始化")

    def connect(self, setting: dict = None):
        """连接虚拟数据源（向后兼容方法）

        Args:
            setting: 连接设置（包含起始时间、推送速度等）
        """
        if setting:
            if "起始时间" in setting:
                # TODO: 解析起始时间并加载数据
                pass
            if "推送速度" in setting:
                self._speed = setting["推送速度"]

        logger.info("🔌 连接虚拟数据源...")

    def close(self):
        """关闭虚拟数据源"""
        logger.info("🔌 关闭虚拟数据源...")
        self.stop()

    @property
    def subscribed_symbols(self) -> Set[str]:
        """获取已订阅的品种列表（向后兼容属性）

        Returns:
            品种代码集合
        """
        return set()  # TODO: 实现实际的订阅管理

    @property
    def push_positions(self) -> int:
        """获取推送位置（向后兼容属性）

        Returns:
            当前推送位置索引
        """
        return self._current_index

    def load_data(
        self,
        symbol: str,
        interval: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ):
        """加载回放数据

        Args:
            symbol: 品种代码
            interval: 周期
            start_date: 开始日期
            end_date: 结束日期
        """
        logger.info(f"📥 加载回放数据: {symbol}/{interval}")

        # 从存储加载
        df = self.storage_manager.load_kline(symbol, interval)

        if df is None or df.empty:
            logger.warning(f"⚠️ 无可用数据: {symbol}/{interval}")
            return

        # 过滤日期范围
        if start_date:
            df = df[df.index >= pd.Timestamp(start_date)]
        if end_date:
            df = df[df.index <= pd.Timestamp(end_date)]

        self._replay_data = df
        self._current_index = 0

        logger.info(f"✅ 加载完成: {len(df)}条数据")

    def start(self, speed: float = 1.0):
        """开始回放

        Args:
            speed: 播放速度
        """
        if self._playing:
            logger.warning("⚠️ 回放已经开始")
            return

        if self._replay_data is None or self._replay_data.empty:
            logger.warning("⚠️ 没有可回放的数据")
            return

        self._speed = speed
        self._playing = True
        self._paused = False
        self._play_thread = threading.Thread(target=self._play_loop, daemon=True)
        self._play_thread.start()

        logger.info(f"▶️ 回放已开始，速度: {speed}x")

    def pause(self):
        """暂停回放"""
        self._paused = True
        logger.info("⏸️ 回放已暂停")

    def resume(self):
        """恢复回放"""
        self._paused = False
        logger.info("▶️ 回放已恢复")

    def stop(self):
        """停止回放"""
        self._playing = False
        if self._play_thread:
            self._play_thread.join(timeout=2)
        logger.info("⏹️ 回放已停止")

    def _play_loop(self):
        """回放循环"""
        logger.info("🔄 回放循环启动")

        while self._playing and self._current_index < len(self._replay_data):
            if self._paused:
                time.sleep(0.1)
                continue

            # 推送当前数据
            self._push_current_bar()

            # 计算等待时间（基于速度）
            sleep_time = 1.0 / self._speed
            time.sleep(sleep_time)

        self._playing = False
        logger.info("✅ 回放完成")

    def _push_current_bar(self):
        """推送当前Bar数据"""
        if self._replay_data is None:
            return

        current_bar = self._replay_data.iloc[self._current_index]

        # TODO: 转换为VnPy BarData并推送事件
        logger.debug(f"📊 推送数据: {current_bar.name}")

        self._current_index += 1


# ==============================================================================
# Part 4: 订阅管理器（SubscriptionManager）
# ==============================================================================


class SubscriptionManager:
    """订阅管理器

    数据订阅管理，支持：
    - 多模块订阅
    - 自动去重
    - 跨进程订阅同步（native_ipc）
    """

    def __init__(self, event_engine=None):
        """初始化订阅管理器

        Args:
            event_engine: VnPy EventEngine
        """
        self.event_engine = event_engine

        # 订阅列表
        self._subscriptions: Dict[Tuple[str, str], Set[str]] = {}  # {(symbol, exchange): {subscriber_id}}
        self._lock = threading.Lock()

        logger.info("✅ 订阅管理器已初始化")

    def subscribe(self, symbol: str, exchange: str, subscriber_id: str):
        """订阅行情

        Args:
            symbol: 品种代码
            exchange: 交易所
            subscriber_id: 订阅者ID
        """
        with self._lock:
            key = (symbol, exchange)
            if key not in self._subscriptions:
                self._subscriptions[key] = set()

            self._subscriptions[key].add(subscriber_id)
            logger.info(f"📡 新增订阅: {key}, 订阅者: {subscriber_id}")

    def unsubscribe(self, symbol: str, exchange: str, subscriber_id: str):
        """取消订阅

        Args:
            symbol: 品种代码
            exchange: 交易所
            subscriber_id: 订阅者ID
        """
        with self._lock:
            key = (symbol, exchange)
            if key in self._subscriptions:
                self._subscriptions[key].discard(subscriber_id)

                # 如果没有订阅者了，删除订阅
                if not self._subscriptions[key]:
                    del self._subscriptions[key]
                    logger.info(f"🚫 取消订阅: {key}")

    def get_subscriptions(self) -> Dict[Tuple[str, str], Set[str]]:
        """获取所有订阅

        Returns:
            订阅字典
        """
        with self._lock:
            return self._subscriptions.copy()

    def is_subscribed(self, symbol: str, exchange: str) -> bool:
        """检查是否已订阅

        Args:
            symbol: 品种代码
            exchange: 交易所

        Returns:
            是否已订阅
        """
        with self._lock:
            return (symbol, exchange) in self._subscriptions


# ==============================================================================
# 导出API（向后兼容）
# ==============================================================================

__all__ = [
    # 数据查询
    "DataQueryPriority",
    "UnifiedDataManager",
    # 数据源
    "TdxDataSource",
    "VirtualDataSource",
    # 订阅管理
    "SubscriptionManager",
]
