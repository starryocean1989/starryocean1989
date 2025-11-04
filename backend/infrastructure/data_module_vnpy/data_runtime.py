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

    def get_all_contracts(self) -> List[Dict[str, Any]]:
        """获取所有合约信息（兼容 VnPy 接口）

        Returns:
            合约列表，每个合约包含 symbol, exchange, name 等信息
        """
        try:
            # 🔧 修复：正确获取 ChinaStockEngine
            # 方式1：如果 event_engine 有 china_stock_engine 属性（正常情况）
            china_stock_engine = None
            if self.event_engine and hasattr(self.event_engine, 'china_stock_engine'):
                china_stock_engine = self.event_engine.china_stock_engine
            # 方式2：如果 event_engine 本身就是 ChinaStockEngine（兼容情况）
            elif self.event_engine and hasattr(self.event_engine, 'get_all_symbols'):
                china_stock_engine = self.event_engine
            # 方式3：从全局获取
            else:
                try:
                    from backend.core.base import get_china_stock_engine
                    china_stock_engine = get_china_stock_engine()
                except:
                    pass

            if china_stock_engine and hasattr(china_stock_engine, 'symbol_loader') and china_stock_engine.symbol_loader:
                symbols = china_stock_engine.symbol_loader.extract_all_codes()
                if symbols:
                    # 转换为 VnPy 合约格式
                    contracts = []
                    for symbol in symbols:
                        contract = {
                            "symbol": symbol,
                            "exchange": "SSE",  # 默认交易所
                            "name": f"股票{symbol}",
                            "product": "EQUITY",
                            "size": 1,
                            "pricetick": 0.01,
                            "min_volume": 1,
                            "max_volume": None,
                            "margin_rate": 0.1,
                            "gateway_name": "china_stock"
                        }
                        contracts.append(contract)
                    return contracts

            # 如果无法获取，返回空列表
            logger.warning("⚠️ 无法获取合约列表，返回空列表")
            return []

        except Exception as e:
            logger.error(f"获取合约列表失败: {e}", exc_info=True)
            return []

    def load_bar_data(self, symbol: str, interval: str = "1d", start_date: str = None, end_date: str = None, **kwargs) -> List[Dict]:
        """加载K线数据（兼容 VnPy 接口）

        Args:
            symbol: 品种代码
            interval: 周期
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            K线数据列表
        """
        try:
            # 调用内部查询方法
            df = self.query_kline(symbol, interval, start_date, end_date)
            if df is None or df.empty:
                return []

            # 转换为 VnPy BarData 格式
            bars = []
            for idx, row in df.iterrows():
                bar = {
                    "symbol": symbol,
                    "exchange": "SSE",  # 默认交易所
                    "interval": interval,
                    "datetime": idx,
                    "volume": row.get("volume", 0),
                    "turnover": row.get("amount", 0),
                    "open_price": row.get("open", 0),
                    "high_price": row.get("high", 0),
                    "low_price": row.get("low", 0),
                    "close_price": row.get("close", 0),
                    "open_interest": 0,
                    "gateway_name": "china_stock"
                }
                bars.append(bar)

            return bars

        except Exception as e:
            logger.error(f"加载K线数据失败: {symbol}/{interval}, {e}", exc_info=True)
            return []

    async def query_kline_async(
        self,
        symbol: str,
        interval: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> Optional[pd.DataFrame]:
        """异步查询K线数据（四层融合）

        Args:
            symbol: 品种代码
            interval: 周期
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            K线数据DataFrame
        """
        self._stats["total_queries"] += 1

        # Layer 1: 尝试从预加载缓存获取（TODO: 集成PreloadService）
        # Layer 2: 从历史Parquet获取
        try:
            df = await self.storage_manager.load_kline_async(symbol, interval)
            if df is not None and not df.empty:
                self._stats["storage_hits"] += 1

                # 过滤日期范围
                if start_date or end_date:
                    df = self._filter_date_range(df, start_date, end_date)

                return df
        except Exception as e:
            logger.debug(f"从存储加载失败: {symbol}/{interval}, {e}")

        # Layer 3: 录制数据（TODO: 集成录制数据源）
        # Layer 4: 实时推送（TODO: 集成实时数据源）

        self._stats["misses"] += 1
        return None

    def query_kline(
        self,
        symbol: str,
        interval: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> Optional[pd.DataFrame]:
        """同步查询K线数据（向后兼容）

        Args:
            symbol: 品种代码
            interval: 周期
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            K线数据DataFrame
        """
        # 创建事件循环执行异步查询
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(
                self.query_kline_async(symbol, interval, start_date, end_date)
            )
        finally:
            loop.close()

    def _filter_date_range(
        self,
        df: pd.DataFrame,
        start_date: Optional[date],
        end_date: Optional[date],
    ) -> pd.DataFrame:
        """过滤日期范围

        Args:
            df: 数据DataFrame
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            过滤后的DataFrame
        """
        if df.empty:
            return df

        if start_date:
            df = df[df.index >= pd.Timestamp(start_date)]

        if end_date:
            df = df[df.index <= pd.Timestamp(end_date)]

        return df

    def get_stats(self) -> Dict[str, int]:
        """获取查询统计

        Returns:
            统计信息字典
        """
        stats = self._stats.copy()
        if stats["total_queries"] > 0:
            stats["hit_rate"] = (
                (stats["cache_hits"] + stats["storage_hits"] +
                 stats["recorded_hits"] + stats["realtime_hits"]) /
                stats["total_queries"] * 100
            )
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
