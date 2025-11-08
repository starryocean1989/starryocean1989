# -*- coding: utf-8 -*-
"""
数据获取模块 - 架构v3.6重构版

本模块负责品种管理和数据下载,采用全新的模块化架构:
- 品种分类器:5种分类器(上证、深证、北证、T+0基金、可转债)
- 品种过滤器:3种过滤器(未上市、重复、无效数据)
- 数据下载器:多进程+多协程,支持两段式下载(IPv4→IPv6)
- TDX读取器:本地二进制文件读取,native_iocp加速
- 辅助功能:IPO日期下载、任务日志记录

架构特性:
- native_iocp集成:TDX文件读取性能提升40-60%
- native_ipc集成:跨进程进度同步
- 智能负载均衡:调用LoadBalancer动态调整并发
- 两段式下载:IPv4池→IPv6池,自动降级
- 代码精简:通用工具函数已迁移到 tdx_asyncio
- 100% API向后兼容

v3.6 更新:
- 工具函数迁移:safe_put_queue、configure_subprocess_logging 等已迁移到 tdx_asyncio.utils.helper
- 性能优化:集成 native C 扩展,优化关键性能路径
- 引用链更新:所有引用已更新,从 tdx_asyncio 导入

重构日期:2025年
作者:AI Assistant (基于v2.1重构)
"""

import asyncio
import csv
import importlib
import logging
import os
import queue
import threading
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, date
from enum import Enum, auto
from io import BytesIO
import multiprocessing as mp
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, TYPE_CHECKING

import os
import pandas as pd

try:
    from .native_scheduler_bridge import NativeSchedulerBridge
except Exception:  # pragma: no cover - 调度扩展缺失时降级
    NativeSchedulerBridge = None  # type: ignore

# 类型提示支持
if TYPE_CHECKING:
    from multiprocessing.context import BaseContext as MPBaseContext
else:
    MPBaseContext = Any

# 导入native_iocp(支持降级)
from typing import Union, Coroutine, Any

try:
    from backend.infrastructure.native.native_dataframe_ops import (
        DATAFRAME_OPS_AVAILABLE,
        dataframe_to_records as native_df_to_records,
        filter_symbols as native_filter_symbols,
    )
except ImportError:
    DATAFRAME_OPS_AVAILABLE = False
    native_df_to_records = None  # type: ignore
    native_filter_symbols = None  # type: ignore

    def native_filter_symbols(  # type: ignore[override]
        records,
        *,
        deduplicate: bool = True,
        drop_empty_code: bool = True,
        require_name: bool = False,
    ):
        seen = set()
        results = []

        for symbol in records:
            if not isinstance(symbol, dict):
                continue

            code = symbol.get("code")
            if code is None:
                continue

            code_text = str(code).strip()
            if drop_empty_code and not code_text:
                continue

            if require_name:
                name = symbol.get("name")
                if name is None or str(name).strip() == "":
                    continue

            if deduplicate:
                if code_text in seen:
                    continue
                seen.add(code_text)

            results.append(symbol)

        return results

try:
    from backend.infrastructure.native.native_iocp.compat import aopen as compat_aopen  # type: ignore

    IOCP_AVAILABLE = True
except ImportError:
    try:
        import aiofiles

        async def compat_aopen(filepath: Union[str, Path], mode: str = "r", **kwargs: Any) -> Any:
            """兼容的异步文件打开函数"""
            return await aiofiles.open(filepath, mode, **kwargs)

        IOCP_AVAILABLE = False
    except ImportError:
        compat_aopen = None  # type: ignore
        IOCP_AVAILABLE = False

# 导入native_ipc(支持降级)
try:
    from backend.infrastructure.native.native_ipc import AsyncIPCPipe

    IPC_AVAILABLE = True
except ImportError:
    IPC_AVAILABLE = False
    AsyncIPCPipe = None

# 导入native_collections(支持降级)
try:
    from backend.infrastructure.native.native_collections import (
        HighPerfPriorityQueue,
        COLLECTIONS_AVAILABLE,
    )
except ImportError:
    COLLECTIONS_AVAILABLE = False
    HighPerfPriorityQueue = None

try:
    _native_async_module = importlib.import_module("backend.infrastructure.native.native_async")
    native_reduce_task_results = getattr(_native_async_module, "reduce_task_results")
except Exception as _async_import_error:  # noqa: BLE001
    raise RuntimeError("native_async 模块不可用") from _async_import_error

# 导入TDX异步API
from backend.infrastructure.tdx_asyncio import (
    AsyncTdxHq_API,
    TdxBinaryReader,
    TdxDataReader,
    BjStockDecoder,
    TdxConfigFileParser,
    BlockParser,
    # v2.2新增:底层工具
    batch_get_ipo_dates,
    batch_get_ipo_dates_multiprocess,
    batch_get_finance_info,
    ServerTester,
    test_server,
    batch_test_servers,
    get_fastest_servers,
    TdxPathHelper,
    find_tdx_root,
    get_market_from_code,
    tdx_bars_to_dataframe,
    tdx_quotes_to_dataframe,
    normalize_tdx_data,
    # v2.3新增:高级封装函数
    get_security_list_batch,
    get_security_bars_by_interval,
    get_security_bars_safe,
    get_ipo_date_safe,
    bars_to_dataframe_safe,
    interval_to_category,
    category_to_interval,
    # v2.4新增:队列和子进程辅助函数(迁移自data_module_vnpy)
    safe_put_queue,
    get_queue_skip_stats,
    reset_queue_skip_stats,
    configure_subprocess_logging,
    # 向后兼容:保留带下划线的函数名
    _safe_put_queue,
    _get_queue_skip_stats,
    _reset_queue_skip_stats,
    _configure_subprocess_logging,
)

# 导入核心引擎
from .core_engine import (
    ConfigManager,
    DailyCacheManager,
    NetworkTimeSync,
)

# 导入存储管理
from .data_storage import StorageManager

_DISABLE_NATIVE_SCHEDULER = os.getenv("DISABLE_NATIVE_SCHEDULER", "0").strip().lower() in {"1", "true", "yes"}

if NativeSchedulerBridge is not None and not _DISABLE_NATIVE_SCHEDULER:
    try:
        _NATIVE_SCHEDULER_BRIDGE = NativeSchedulerBridge(
            categories={
                "network_download": {"queue_capacity": 8192, "max_workers": 16},
                "local_scan": {"queue_capacity": 8192, "max_workers": 8},
                "local_read": {"queue_capacity": 4096, "max_workers": 8},
            }
        )
    except Exception:  # pragma: no cover
        _NATIVE_SCHEDULER_BRIDGE = None
else:
    _NATIVE_SCHEDULER_BRIDGE = None

# ==================== 日志配置 ====================
logger = logging.getLogger("backend.data_module.acquisition")
logger_alert = logging.getLogger("backend.data_module.alert")


# ==============================================================================
# 全局配置和辅助函数
# ==============================================================================

# 注意:队列和子进程辅助函数已迁移到 tdx_asyncio.utils.helper
# 请使用:from backend.infrastructure.tdx_asyncio import safe_put_queue, configure_subprocess_logging


# ==============================================================================
# Part 1: 任务详细日志记录器
# ==============================================================================


class TaskDetailLogger:
    """任务详细日志记录器

    负责记录每个下载任务的详细信息到CSV文件,包括:
    - 任务ID、品种代码、周期
    - 服务器IP、端口、券商名称
    - 任务状态、错误信息、数据条数、耗时
    - Worker ID、Connection ID、Phase
    """

    def __init__(self, worker_id: int = 0, log_dir: str = "logs"):
        """初始化日志记录器

        Args:
            worker_id: Worker进程ID(用于生成独立的日志文件)
            log_dir: 日志目录
        """
        # 确保使用绝对路径
        if not Path(log_dir).is_absolute():
            project_root = Path(__file__).parent.parent.parent.parent.parent
            self.log_dir = project_root / log_dir
        else:
            self.log_dir = Path(log_dir)

        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.worker_id = worker_id

        # 生成worker专属的日志文件名(避免并发写入冲突)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = self.log_dir / f"kline_task_details_{timestamp}_worker{worker_id}.csv"

        # 构建服务器->券商映射
        self.server_broker_map = self._build_server_broker_map()

        # 初始化文件句柄
        self._init_file_handles()

    def _build_server_broker_map(self) -> Dict[str, str]:
        """构建服务器->券商映射"""
        try:
            from backend.infrastructure.tdx_asyncio.constants import BROKER_SERVERS_7709

            server_broker_map: Dict[str, str] = {}
            server_max_conn_map: Dict[str, int] = {}

            # ✅ 直接使用BROKER_SERVERS_7709(4字段格式:券商名称, IP, 端口, 最大连接数)
            for broker_name, ip, port, max_conn in BROKER_SERVERS_7709:
                key = f"{ip}:{port}"
                if key not in server_broker_map:
                    server_broker_map[key] = broker_name
                    server_max_conn_map[key] = max_conn

            logger.debug(
                f"📊 [Worker {self.worker_id}] 已加载 {len(server_broker_map)} 个服务器-券商映射",
                extra={"log_type": "SYSTEM", "scenario": "data_download"},
            )
            return server_broker_map
        except ImportError:
            logger.warning(
                "⚠️ 无法导入服务器常量,使用空映射",
                extra={"log_type": "SYSTEM", "scenario": "data_download"},
            )
            return {}

    def _init_file_handles(self):
        """初始化文件句柄和CSV写入器"""
        try:
            self.file_handle = open(self.log_file, "w", encoding="utf-8", newline="")
            self.csv_writer = csv.writer(self.file_handle)
            self._init_csv_file()
            logger.info(
                f"✅ [Worker {self.worker_id}] 任务日志文件已创建: {self.log_file}",
                extra={"log_type": "SYSTEM", "scenario": "data_download"},
            )
        except Exception as e:
            logger.error(
                f"❌ [Worker {self.worker_id}] 创建日志文件失败: {e}",
                exc_info=True,
                extra={"log_type": "ALERT", "scenario": "data_download"},
            )
            self.file_handle = None
            self.csv_writer = None

    def _init_csv_file(self):
        """初始化CSV文件头"""
        headers = [
            "时间戳",
            "任务ID",
            "品种代码",
            "周期",
            "服务器IP",
            "服务器Port",
            "所属券商/机构",
            "任务状态",
            "错误信息",
            "数据条数",
            "耗时(秒)",
            "Worker ID",
            "Connection ID",
            "Phase",
        ]
        if self.csv_writer and self.file_handle:
            self.csv_writer.writerow(headers)
            self.file_handle.flush()

    def log_task(
        self,
        symbol: str,
        interval: str,
        server: Union[str, Tuple[str, int]],
        status: str,
        error_msg: str = "",
        data_count: int = 0,
        elapsed_time: float = 0.0,
        worker_id: int = 0,
        connection_id: int = 0,
        phase: str = "Phase1",
        task_id: Optional[str] = None,
    ):
        """记录单个任务详情

        Args:
            symbol: 品种代码
            interval: 周期(1m, 5m, 1d等)
            server: 服务器元组 (ip, port)
            status: 任务状态 (success/failed/timeout/retry)
            error_msg: 错误信息(如果有)
            data_count: 返回的数据条数
            elapsed_time: 任务耗时(秒)
            worker_id: Worker ID
            connection_id: 连接ID
            phase: 阶段标识(Phase1/Phase2)
            task_id: 任务唯一ID(可选)
        """
        try:
            if not self.csv_writer or not self.file_handle:
                return

            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

            # 解析服务器信息
            if isinstance(server, tuple) and len(server) == 2:
                server_ip, server_port = server
            elif isinstance(server, dict):
                server_ip = server.get("ip", "unknown")
                server_port = server.get("port", 0)
            else:
                server_ip = str(server)
                server_port = 0

            # 查找券商名称
            server_key = f"{server_ip}:{server_port}"
            broker_name = self.server_broker_map.get(server_key, "未知机构")

            # 生成任务ID
            if task_id is None:
                task_id = f"{symbol}_{interval}_{int(time.time()*1000)}"

            # 写入CSV
            row = [
                timestamp,
                task_id,
                symbol,
                interval,
                server_ip,
                server_port,
                broker_name,
                status,
                error_msg,
                data_count,
                f"{elapsed_time:.3f}",
                worker_id,
                connection_id,
                phase,
            ]
            self.csv_writer.writerow(row)

            # 立即刷新到磁盘
            self.file_handle.flush()
            os.fsync(self.file_handle.fileno())

        except Exception as e:
            logger.warning(
                f"⚠️ [Worker {self.worker_id}] 任务日志记录失败: {e}",
                extra={"log_type": "ALERT", "scenario": "data_download"},
            )

    def close(self):
        """关闭日志文件"""
        try:
            if hasattr(self, "file_handle") and self.file_handle:
                self.file_handle.close()
                logger.info(
                    f"✅ 任务详细日志已保存: {self.log_file}",
                    extra={"log_type": "SYSTEM", "scenario": "data_download"},
                )
        except Exception as e:
            logger.warning(
                f"⚠️ 关闭任务日志文件失败: {e}",
                extra={"log_type": "ALERT", "scenario": "data_download"},
            )

    def __del__(self):
        """析构函数,确保文件被关闭"""
        self.close()


# ==============================================================================
# Part 2: TDX配置文件解析器(已迁移到 tdx_asyncio.parsers.config_parser)
# ==============================================================================
# TdxConfigFileParser 已迁移到 backend.infrastructure.tdx_asyncio.parsers.config_parser
# 请使用:from backend.infrastructure.tdx_asyncio import TdxConfigFileParser

# BlockParser 已迁移到 backend.infrastructure.tdx_asyncio.parsers.block_parser
# 请使用:from backend.infrastructure.tdx_asyncio import BlockParser


# ==============================================================================
# Part 3: 品种分类器框架
# ==============================================================================


class BaseClassifier:
    """品种分类器基类

    所有分类器必须继承此类并实现classify方法。
    """

    def __init__(self, name: str):
        """初始化分类器

        Args:
            name: 分类器名称
        """
        self.name = name

    def classify(self, all_symbols: pd.DataFrame, **kwargs) -> List[Dict[str, Any]]:
        """分类方法(抽象方法)

        Args:
            all_symbols: 所有品种的DataFrame(包含code, name, market列)
            **kwargs: 额外参数

        Returns:
            分类后的品种列表,每个元素为字典
        """
        raise NotImplementedError("Subclass must implement classify method")

    def __repr__(self):
        return f"<{self.__class__.__name__}(name='{self.name}')>"


class ClassifierRegistry:
    """分类器注册表

    管理所有品种分类器,支持注册、注销和按名称获取。
    """

    def __init__(self):
        self._classifiers: Dict[str, BaseClassifier] = {}

    def register(self, classifier: BaseClassifier):
        """注册分类器

        Args:
            classifier: 分类器实例
        """
        self._classifiers[classifier.name] = classifier
        logger.debug(f"✅ 注册分类器: {classifier.name}")

    def unregister(self, name: str):
        """注销分类器

        Args:
            name: 分类器名称
        """
        if name in self._classifiers:
            del self._classifiers[name]
            logger.debug(f"❌ 注销分类器: {name}")

    def get(self, name: str) -> Optional[BaseClassifier]:
        """获取分类器

        Args:
            name: 分类器名称

        Returns:
            分类器实例,如果不存在则返回None
        """
        return self._classifiers.get(name)

    def get_all(self) -> Dict[str, BaseClassifier]:
        """获取所有分类器"""
        return self._classifiers.copy()

    def classify_all(self, all_symbols: pd.DataFrame, **kwargs) -> Dict[str, List[Dict[str, Any]]]:
        """执行所有分类器

        Args:
            all_symbols: 所有品种的DataFrame
            **kwargs: 传递给分类器的额外参数

        Returns:
            分类结果字典,key为分类器名称,value为品种列表
        """
        results = {}
        for name, classifier in self._classifiers.items():
            try:
                classified = classifier.classify(all_symbols, **kwargs)
                results[name] = classified
                logger.debug(f"✅ 分类器 {name} 执行完成,分类出 {len(classified)} 个品种")
            except Exception as e:
                logger.error(f"❌ 分类器 {name} 执行失败: {e}", extra={"log_type": "SYSTEM"})
                results[name] = []

        return results


# ==============================================================================
# Part 4: 品种分类器实现
# ==============================================================================


class ShanghaiStockClassifier(BaseClassifier):
    """上证A股分类器

    规则:
    - market=1(上证)
    - code以60或688开头
    - code长度为6位数字
    - 排除可转债(11开头)
    """

    def __init__(self):
        super().__init__("上证A股")

    def classify(self, all_symbols: pd.DataFrame, **kwargs) -> List[Dict[str, Any]]:
        """分类上证A股

        Args:
            all_symbols: 所有品种的DataFrame

        Returns:
            上证A股列表
        """
        if all_symbols.empty:
            return []

        # 确保code列为字符串,并补齐6位
        all_symbols["code"] = all_symbols["code"].astype(str).str.zfill(6)

        # 过滤条件:market=1,code以60或688开头,排除11开头(可转债)
        shanghai_stocks = all_symbols[
            (all_symbols["market"] == 1)
            & (all_symbols["code"].str.len() == 6)
            & (all_symbols["code"].str.isdigit())
            & (
                (all_symbols["code"].str.startswith("60"))
                | (all_symbols["code"].str.startswith("688"))
            )
            & (~all_symbols["code"].str.startswith("11"))
        ]

        results_df = shanghai_stocks.loc[:, ["code", "name"]].copy()
        results_df = results_df.assign(market=1, exchange="SSE", category="上证A股")

        if DATAFRAME_OPS_AVAILABLE and native_df_to_records is not None:
            results = native_df_to_records(results_df)
        else:
            results = results_df.to_dict("records")

        logger.debug(f"✅ 上证A股分类完成,共 {len(results)} 个品种")
        return results


class ShenzhenStockClassifier(BaseClassifier):
    """深证A股分类器

    规则:
    - market=0(深证)
    - code以00/001/002(主板/中小板)或300/301(创业板)开头
    - code长度为6位数字
    - 排除可转债(12开头)
    - 排除T+0基金(由T0FundClassifier处理)
    """

    def __init__(self):
        super().__init__("深证A股")

    def classify(self, all_symbols: pd.DataFrame, **kwargs) -> List[Dict[str, Any]]:
        """分类深证A股

        Args:
            all_symbols: 所有品种的DataFrame
            **kwargs: 可选参数,包括t0_fund_codes(T+0基金代码集合)

        Returns:
            深证A股列表
        """
        if all_symbols.empty:
            return []

        # 确保code列为字符串,并补齐6位
        all_symbols["code"] = all_symbols["code"].astype(str).str.zfill(6)

        # 获取T+0基金代码集合(用于排除)
        t0_fund_codes = kwargs.get("t0_fund_codes", set())

        # 过滤条件
        shenzhen_stocks = all_symbols[
            (all_symbols["market"] == 0)
            & (all_symbols["code"].str.len() == 6)
            & (all_symbols["code"].str.isdigit())
            & ((all_symbols["code"].str.startswith(("000", "001", "002", "300", "301"))))
            & (~all_symbols["code"].str.startswith("12"))
            & (~all_symbols["code"].isin(t0_fund_codes))
        ]

        results_df = shenzhen_stocks.loc[:, ["code", "name"]].copy()
        results_df = results_df.assign(market=0, exchange="SZSE", category="深证A股")

        if DATAFRAME_OPS_AVAILABLE and native_df_to_records is not None:
            results = native_df_to_records(results_df)
        else:
            results = results_df.to_dict("records")

        logger.debug(f"✅ 深证A股分类完成,共 {len(results)} 个品种")
        return results


class BeijingStockClassifier(BaseClassifier):
    """北证A股分类器

    规则:
    - 从TDX配置文件 addedcode_bj.cfg 获取北证品种列表
    - market=2(北证)
    - code通常以43/83/87开头
    """

    def __init__(self):
        super().__init__("北证A股")

    def classify(self, all_symbols: pd.DataFrame, **kwargs) -> List[Dict[str, Any]]:
        """分类北证A股

        Args:
            all_symbols: 所有品种的DataFrame
            **kwargs: 额外参数,包括tdx_parser(TdxConfigFileParser实例)

        Returns:
            北证A股列表
        """
        # 获取TDX配置文件解析器
        tdx_parser = kwargs.get("tdx_parser")
        if tdx_parser is None:
            logger.warning(
                "⚠️ 未提供TdxConfigFileParser实例,无法分类北证A股(请检查TDX配置文件路径)",
                extra={"log_type": "SYSTEM"},
            )
            return []

        # 从配置文件解析北证品种(按照文档:从addedcode_bj.cfg解析,市场代码硬编码为2)
        try:
            beijing_stocks = tdx_parser.parse_addedcode_bj()
        except Exception as e:
            logger.warning(
                f"⚠️ 解析北证A股配置文件失败: {e},无法分类北证A股", extra={"log_type": "SYSTEM"}
            )
            return []

        if not beijing_stocks:
            logger.warning(
                "⚠️ 北证A股配置文件为空或不存在,无法分类北证A股", extra={"log_type": "SYSTEM"}
            )
            return []

        # 按照旧版架构:parse_addedcode_bj已经返回包含market:2的字典,只需添加category字段
        for stock in beijing_stocks:
            stock["category"] = "北证A股"
            # 确保有exchange字段(如果解析时没有添加)
            if "exchange" not in stock:
                stock["exchange"] = "BSE"

        logger.info(f"✅ 北证A股分类完成,共 {len(beijing_stocks)} 个品种")
        return beijing_stocks


class T0FundClassifier(BaseClassifier):
    """T+0基金分类器

    规则:
    - 从spblock.dat文件获取标记为"T+0基金"的品种
    - market=0(深证)或1(上证)
    - 主要是ETF基金
    """

    def __init__(self):
        super().__init__("T+0基金")

    def classify(self, all_symbols: pd.DataFrame, **kwargs) -> List[Dict[str, Any]]:
        """分类T+0基金

        Args:
            all_symbols: 所有品种的DataFrame
            **kwargs: 额外参数,包括block_parser(BlockParser实例)

        Returns:
            T+0基金列表
        """
        # 获取板块解析器
        block_parser = kwargs.get("block_parser")
        if block_parser is None:
            logger.warning(
                "⚠️ 未提供BlockParser实例,无法分类T+0基金(请检查TDX板块文件路径)",
                extra={"log_type": "SYSTEM"},
            )
            return []

        # 从板块文件获取T+0基金代码(按照文档:从spblock.dat获取,然后从complete_df匹配名称)
        try:
            t0_fund_codes = block_parser.get_t0_fund_codes()
        except Exception as e:
            logger.warning(
                f"⚠️ 解析T+0基金板块文件失败: {e},无法分类T+0基金", extra={"log_type": "SYSTEM"}
            )
            return []

        if not t0_fund_codes:
            logger.warning(
                "⚠️ T+0基金板块文件为空或不存在,无法分类T+0基金", extra={"log_type": "SYSTEM"}
            )
            return []

        # 按照旧版架构:使用简单的字典匹配方式,不要求品种必须在API中存在
        if not all_symbols.empty:
            all_symbols["code"] = all_symbols["code"].astype(str).str.zfill(6)
            code_to_name = dict(zip(all_symbols["code"], all_symbols["name"]))
        else:
            code_to_name = {}
            logger.warning("⚠️ 品种列表为空,T+0基金名称将无法匹配", extra={"log_type": "SYSTEM"})

        # 合并名称信息(从all_symbols中查找,按照旧版架构方式)
        for fund in t0_fund_codes:
            code = str(fund["code"]).zfill(6)
            if code in code_to_name:
                fund["name"] = code_to_name[code]
            # 如果没有匹配到名称,仍然保留品种(name为空),按照旧版架构逻辑

        # 添加category字段
        for fund in t0_fund_codes:
            fund["category"] = "T+0基金"

        matched_name_count = sum(1 for f in t0_fund_codes if f.get("name"))
        logger.debug(
            f"[CLASSIFIER] T+0基金分类器执行完成: 总品种数={len(t0_fund_codes)}, 匹配到名称={matched_name_count}",
            extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"},
        )
        logger.info(
            f"✅ T+0基金分类完成,共 {len(t0_fund_codes)} 个品种(匹配到名称: {matched_name_count} 个)",
            extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"},
        )
        return t0_fund_codes


class ConvertibleBondClassifier(BaseClassifier):
    """可转债分类器

    规则:
    - 从TDX配置文件 tdxstat2.cfg 获取可转债列表
    - market=0(深证,code以12开头)或1(上证,code以11开头)
    """

    def __init__(self):
        super().__init__("可转债")

    def classify(self, all_symbols: pd.DataFrame, **kwargs) -> List[Dict[str, Any]]:
        """分类可转债

        Args:
            all_symbols: 所有品种的DataFrame
            **kwargs: 额外参数,包括tdx_parser(TdxConfigFileParser实例)

        Returns:
            可转债列表
        """
        # 获取TDX配置文件解析器
        tdx_parser = kwargs.get("tdx_parser")
        if tdx_parser is None:
            logger.warning(
                "⚠️ 未提供TdxConfigFileParser实例,无法分类可转债(请检查TDX配置文件路径)",
                extra={"log_type": "SYSTEM"},
            )
            return []

        # 从配置文件解析可转债(按照文档:从tdxstat2.cfg获取,然后从complete_df匹配名称,支持市场代码容错)
        try:
            convertible_bonds_dict = tdx_parser.parse_tdxstat2()
        except Exception as e:
            logger.warning(
                f"⚠️ 解析可转债配置文件失败: {e},无法分类可转债", extra={"log_type": "SYSTEM"}
            )
            return []

        if not convertible_bonds_dict:
            logger.warning(
                "⚠️ 可转债配置文件为空或不存在,无法分类可转债", extra={"log_type": "SYSTEM"}
            )
            return []

        # 按照旧版架构:使用简单的字典匹配方式,不要求品种必须在API中存在
        # 合并深证和上证可转债
        results = []

        # 深证可转债(market=0)
        for code in convertible_bonds_dict.get(0, []):
            results.append(
                {
                    "code": code.zfill(6),
                    "name": "",  # 配置文件不包含名称,先设为空
                    "market": 0,
                    "exchange": "SZSE",
                    "category": "可转债",
                }
            )

        # 上证可转债(market=1)
        for code in convertible_bonds_dict.get(1, []):
            results.append(
                {
                    "code": code.zfill(6),
                    "name": "",  # 配置文件不包含名称,先设为空
                    "market": 1,
                    "exchange": "SSE",
                    "category": "可转债",
                }
            )

        # 合并名称信息(从all_symbols中查找,按照旧版架构方式)
        if not all_symbols.empty:
            all_symbols["code"] = all_symbols["code"].astype(str).str.zfill(6)
            code_to_name = dict(zip(all_symbols["code"], all_symbols["name"]))

            for bond in results:
                code = bond["code"]
                # 尝试匹配名称(支持市场代码容错)
                if code in code_to_name:
                    bond["name"] = code_to_name[code]
                else:
                    # 如果当前市场匹配不到,尝试另一个市场(0↔1容错)
                    # 但只更新名称,不改变market值(按照旧版架构逻辑)
                    pass  # 旧版架构中,如果匹配不到名称,name保持为空

        logger.info(
            f"✅ 可转债分类完成,深证 {len(convertible_bonds_dict.get(0, []))} 个,上证 {len(convertible_bonds_dict.get(1, []))} 个,共 {len(results)} 个(匹配到名称: {sum(1 for b in results if b.get('name'))} 个)"
        )
        return results


# ==============================================================================
# Part 5: 品种过滤器框架
# ==============================================================================


class BaseFilter:
    """品种过滤器基类

    所有过滤器必须继承此类并实现filter方法。
    """

    def __init__(self, name: str):
        """初始化过滤器

        Args:
            name: 过滤器名称
        """
        self.name = name

    def filter(self, symbols: List[Dict[str, Any]], **kwargs) -> List[Dict[str, Any]]:
        """过滤方法(抽象方法)

        Args:
            symbols: 品种列表
            **kwargs: 额外参数

        Returns:
            过滤后的品种列表
        """
        raise NotImplementedError("Subclass must implement filter method")

    def __repr__(self):
        return f"<{self.__class__.__name__}(name='{self.name}')>"


class FilterChain:
    """过滤器链

    按顺序执行多个过滤器。
    """

    def __init__(self):
        self._filters: List[BaseFilter] = []

    def add_filter(self, filter_: BaseFilter):
        """添加过滤器

        Args:
            filter_: 过滤器实例
        """
        self._filters.append(filter_)
        logger.debug(f"✅ 添加过滤器: {filter_.name}")

    def remove_filter(self, name: str):
        """移除过滤器

        Args:
            name: 过滤器名称
        """
        self._filters = [f for f in self._filters if f.name != name]
        logger.debug(f"❌ 移除过滤器: {name}")

    def apply(self, symbols: List[Dict[str, Any]], **kwargs) -> List[Dict[str, Any]]:
        """应用所有过滤器

        Args:
            symbols: 品种列表
            **kwargs: 传递给过滤器的额外参数

        Returns:
            过滤后的品种列表
        """
        result = symbols
        original_count = len(result)

        for filter_ in self._filters:
            try:
                before_count = len(result)
                logger.debug(
                    f"[FILTER-CHAIN] 开始执行过滤器: {filter_.name}, 当前品种数={before_count}",
                    extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"},
                )
                result = filter_.filter(result, **kwargs)
                after_count = len(result)
                filtered_count = before_count - after_count
                logger.debug(
                    f"✅ 过滤器 {filter_.name} 执行完成,过滤掉 {filtered_count} 个品种",
                    extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"},
                )
                logger.debug(
                    f"[FILTER-CHAIN] 过滤器 {filter_.name} 执行结果: 过滤前={before_count}, "
                    f"过滤后={after_count}, 过滤掉={filtered_count}",
                    extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"},
                )
            except Exception as e:
                logger.debug(
                    f"[FILTER-CHAIN] 过滤器 {filter_.name} 执行异常: {type(e).__name__}: {str(e)}",
                    extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"},
                )
                logger.error(
                    f"❌ 过滤器 {filter_.name} 执行失败: {e}",
                    exc_info=True,
                    extra={"log_type": "ALERT", "scenario": "refresh_symbol_list"},
                )

        total_filtered = original_count - len(result)
        logger.debug(
            f"[FILTER-CHAIN] 过滤器链执行完成: 原始={original_count}, 过滤掉={total_filtered}, 剩余={len(result)}",
            extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"},
        )
        logger.info(
            f"✅ 过滤器链执行完成,原始 {original_count} 个,过滤掉 {total_filtered} 个,剩余 {len(result)} 个",
            extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"},
        )
        return result


# ==============================================================================
# Part 6: 品种过滤器实现
# ==============================================================================


class UnlistedSymbolFilter(BaseFilter):
    """未上市品种过滤器

    规则:
    - 过滤IPO日期<19900000或为None的品种
    - 需要IPO日期数据作为输入
    """

    def __init__(self):
        super().__init__("未上市品种过滤器")

    def filter(self, symbols: List[Dict[str, Any]], **kwargs) -> List[Dict[str, Any]]:
        """过滤未上市品种

        Args:
            symbols: 品种列表
            **kwargs: 额外参数,包括ipo_dates(IPO日期字典)

        Returns:
            过滤后的品种列表
        """
        ipo_dates = kwargs.get("ipo_dates", {})
        if not ipo_dates:
            logger.warning("⚠️ 未提供IPO日期数据,跳过未上市品种过滤", extra={"log_type": "SYSTEM"})
            return symbols

        results = []
        for symbol in symbols:
            code = symbol.get("code")
            if code is None:
                continue

            # 获取IPO日期
            ipo_date = ipo_dates.get(code)

            # 如果IPO日期有效(>=19900000),保留
            if ipo_date is not None and ipo_date >= 19900000:
                results.append(symbol)

        logger.debug(f"✅ 未上市品种过滤完成,过滤前 {len(symbols)} 个,过滤后 {len(results)} 个")
        return results


class DuplicateSymbolFilter(BaseFilter):
    """重复品种过滤器

    规则:
    - 基于code字段去重
    - 保留第一个出现的品种
    """

    def __init__(self):
        super().__init__("重复品种过滤器")

    def filter(self, symbols: List[Dict[str, Any]], **kwargs) -> List[Dict[str, Any]]:
        """过滤重复品种

        Args:
            symbols: 品种列表
            **kwargs: 额外参数

        Returns:
            过滤后的品种列表
        """
        filtered = native_filter_symbols(
            symbols,
            deduplicate=True,
            drop_empty_code=False,
            require_name=False,
        )

        logger.debug(
            f"✅ 重复品种过滤完成,过滤前 {len(symbols)} 个,过滤后 {len(filtered)} 个"
        )
        return filtered


class InvalidDataFilter(BaseFilter):
    """无效数据过滤器

    规则:
    - 过滤code为空或None的品种
    - 过滤name为空或None的品种(可选)
    """

    def __init__(self, check_name: bool = False):
        """初始化过滤器

        Args:
            check_name: 是否检查name字段
        """
        super().__init__("无效数据过滤器")
        self.check_name = check_name

    def filter(self, symbols: List[Dict[str, Any]], **kwargs) -> List[Dict[str, Any]]:
        """过滤无效数据

        Args:
            symbols: 品种列表
            **kwargs: 额外参数

        Returns:
            过滤后的品种列表
        """
        filtered = native_filter_symbols(
            symbols,
            deduplicate=False,
            drop_empty_code=True,
            require_name=self.check_name,
        )

        logger.debug(
            f"✅ 无效数据过滤完成,过滤前 {len(symbols)} 个,过滤后 {len(filtered)} 个"
        )
        return filtered


# ==============================================================================
# Part 7: SymbolLoader(品种加载器)
# ==============================================================================


def _should_use_native_symbol_index() -> bool:
    value = os.getenv("NATIVE_SYMBOL_INDEX", "1").strip().lower()
    return value not in {"0", "false", "off"}


class SymbolLoader:
    """品种加载器

    负责:
    - 从TDX API加载所有品种
    - 执行品种分类(5种分类器)
    - 执行品种过滤(3种过滤器)
    - 管理品种缓存(DailyCacheManager)
    - 提供品种查询接口
    """

    def __init__(self, event_engine=None):
        """初始化品种加载器

        Args:
            event_engine: 事件引擎(可选)
        """
        self.event_engine = event_engine
        self.config_manager = ConfigManager.get_instance()

        # 🔧 修复:使用 ConfigManager 的 get_cache_dir() 方法,确保统一使用 data/cache 目录
        cache_dir = self.config_manager.get_cache_dir()
        self.cache_file = cache_dir / "stock_list_classified.json"

        # 初始化解析器
        self.tdx_parser = TdxConfigFileParser()
        self.block_parser = BlockParser()

        # 初始化分类器注册表
        self.classifier_registry = ClassifierRegistry()
        self._register_classifiers()

        # 初始化过滤器链
        self.filter_chain = FilterChain()
        self._register_filters()

        # 品种数据
        self.all_symbols: Optional[pd.DataFrame] = None
        self.classified_symbols: Dict[str, List[Dict[str, Any]]] = {}

        # 原生索引
        self._symbol_index = None
        self._symbol_index_factory = None
        self._python_symbol_index_cls = None
        self._using_native_symbol_index = False
        self._symbol_index_impl = "python"
        self._symbol_index_engine: str = "python"
        self._init_symbol_index()

        logger.info(
            "✅ SymbolLoader 初始化完成",
            extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"},
        )

    def _register_classifiers(self):
        """注册所有分类器"""
        self.classifier_registry.register(ShanghaiStockClassifier())
        self.classifier_registry.register(ShenzhenStockClassifier())
        self.classifier_registry.register(BeijingStockClassifier())
        self.classifier_registry.register(T0FundClassifier())
        self.classifier_registry.register(ConvertibleBondClassifier())
        logger.info(
            "✅ 已注册 5 个品种分类器",
            extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"},
        )

    def _register_filters(self):
        """注册所有过滤器"""
        self.filter_chain.add_filter(InvalidDataFilter(check_name=False))
        self.filter_chain.add_filter(DuplicateSymbolFilter())
        logger.info(
            "✅ 已注册 2 个品种过滤器",
            extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"},
        )

    def _init_symbol_index(self) -> None:
        if self._symbol_index is not None:
            return

        try:
            from backend.infrastructure.native.native_symbol_index import (  # type: ignore
                LOCKFREE_INDEX_AVAILABLE,
                SYMBOL_INDEX_AVAILABLE,
                LockFreeSymbolIndex,
                NativeSymbolIndex,
                PythonSymbolIndex,
                create_symbol_index,
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug(
                "native_symbol_index 模块导入失败, 使用轻量Python索引: %s",
                exc,
                exc_info=True,
            )

            class _InlinePythonSymbolIndex:
                IS_NATIVE = False

                def __init__(self) -> None:
                    self._code_index: Dict[str, Dict[str, Any]] = {}
                    self._market_index: Dict[str, List[str]] = {}
                    self._sorted_codes: List[str] = []

                def build(self, records: List[Dict[str, Any]]) -> None:
                    self._code_index.clear()
                    self._market_index.clear()
                    for record in records:
                        code = str(record.get("code", "")).zfill(6)
                        if not code:
                            continue
                        market = str(record.get("market", record.get("market_name", "")))
                        self._code_index[code] = dict(record)
                        self._market_index.setdefault(market, []).append(code)
                    self._sorted_codes = sorted(self._code_index.keys())

                def get_symbol(self, code: str) -> Optional[Dict[str, Any]]:
                    return self._code_index.get(code.zfill(6))

                def get_codes_by_market(self, market: str) -> List[str]:
                    return sorted(self._market_index.get(market, []))

                def all_codes(self) -> List[str]:
                    return list(self._sorted_codes)

                def size(self) -> int:
                    return len(self._code_index)

            self._python_symbol_index_cls = _InlinePythonSymbolIndex
            self._symbol_index_factory = lambda use_native=False: _InlinePythonSymbolIndex()
            self._symbol_index = _InlinePythonSymbolIndex()
            self._using_native_symbol_index = False
            self._symbol_index_impl = "python-inline"
            self._symbol_index_engine = "python-inline"
            return

        self._python_symbol_index_cls = PythonSymbolIndex
        self._symbol_index_factory = create_symbol_index

        use_native = _should_use_native_symbol_index() and SYMBOL_INDEX_AVAILABLE
        index = create_symbol_index(use_native=use_native)
        self._symbol_index = index
        self._using_native_symbol_index = bool(getattr(index, "IS_NATIVE", False))
        self._symbol_index_impl = type(index).__name__
        self._symbol_index_engine = getattr(index, "ENGINE", "python")
        lockfree_status = (
            "LOCKFREE_INDEX_AVAILABLE" in locals() and LOCKFREE_INDEX_AVAILABLE and isinstance(index, LockFreeSymbolIndex)
        )
        logger.debug(
            "SymbolLoader: 索引初始化结果 -> impl=%s, engine=%s, native=%s, lockfree_active=%s",
            self._symbol_index_impl,
            self._symbol_index_engine,
            self._using_native_symbol_index,
            lockfree_status,
        )
        if self._using_native_symbol_index:
            logger.info(
                "native_symbol_index 已启用，用于快速查询品种信息 (engine=%s)",
                self._symbol_index_engine,
            )
        elif use_native:
            logger.warning(
                "native_symbol_index 未成功启用，回退到 Python 索引实现 (engine=%s)",
                self._symbol_index_engine,
            )
        else:
            logger.debug(
                "native_symbol_index 已根据环境变量禁用，当前使用引擎=%s",
                self._symbol_index_engine,
            )

    def _ensure_symbol_index(self) -> None:
        if self._symbol_index is None:
            self._init_symbol_index()
        if self._symbol_index is not None and self.classified_symbols:
            if getattr(self._symbol_index, "size", None):
                try:
                    if self._symbol_index.size() > 0:
                        return
                except Exception:  # noqa: BLE001 - 如果 size 不可用则忽略
                    pass
            self._rebuild_symbol_index(self.classified_symbols)

    def has_native_symbol_index(self) -> bool:
        """判断当前是否启用了原生索引实现."""

        return bool(
            self._symbol_index is not None
            and getattr(self._symbol_index, "IS_NATIVE", False)
            and self._using_native_symbol_index
        )

    def _rebuild_symbol_index(self, classified: Dict[str, List[Dict[str, Any]]]) -> None:
        if not classified:
            return
        if self._symbol_index is None:
            self._init_symbol_index()
        if self._symbol_index is None:
            return

        records: List[Dict[str, Any]] = []
        for market_name, symbols in classified.items():
            for symbol in symbols:
                if not symbol:
                    continue
                record = dict(symbol)
                record.setdefault("market", market_name)
                records.append(record)

        try:
            self._symbol_index.build(records)
            self._symbol_index_engine = getattr(self._symbol_index, "ENGINE", "python")
            self._using_native_symbol_index = bool(
                getattr(self._symbol_index, "IS_NATIVE", False)
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "native_symbol_index 构建失败，自动降级到 Python 实现: %s",
                exc,
                exc_info=True,
            )
            if self._python_symbol_index_cls is not None:
                self._symbol_index = self._python_symbol_index_cls()
                self._using_native_symbol_index = bool(
                    getattr(self._symbol_index, "IS_NATIVE", False)
                )
                self._symbol_index_engine = getattr(self._symbol_index, "ENGINE", "python")
                self._symbol_index.build(records)
        else:
            engine = self._symbol_index_engine
            logger.info(
                "SymbolLoader: %s 索引构建完成（记录数=%d）",
                engine,
                len(records),
            )

    def get_all_codes_native(self) -> Optional[List[str]]:
        """返回全部代码列表。

        - 优先调用当前索引的 `all_codes` 方法（无论是否为原生实现）。
        - 如索引未初始化或方法缺失/异常，回退到 `classified_symbols` 聚合生成。
        """
        self._ensure_symbol_index()
        if self._symbol_index is None:
            logger.debug(
                "symbol_index 尚未初始化，无法获取全部代码 (engine=%s)",
                self._symbol_index_engine,
            )
            return None

        getter = getattr(self._symbol_index, "all_codes", None)
        if getter is not None:
            try:
                codes = getter()
                if codes:
                    return sorted(set(str(code).zfill(6) for code in codes))
            except Exception:
                logger.debug("symbol_index.all_codes 调用失败，使用回退路径", exc_info=True)

        # 回退：基于分类字典聚合代码
        if not self.classified_symbols:
            return []
        agg: List[str] = []
        for records in self.classified_symbols.values():
            for rec in records:
                code = str(rec.get("code", "")).zfill(6)
                if code:
                    agg.append(code)
        return sorted(set(agg))

    def get_codes_by_market_native(self, market: str) -> Optional[List[str]]:
        """返回指定市场的代码列表，原生不可用时回退到 Python 实现。"""
        self._ensure_symbol_index()
        if self._symbol_index is None:
            return None

        getter = getattr(self._symbol_index, "get_codes_by_market", None)
        if getter is not None:
            try:
                result = getter(market)
                if result:
                    return sorted(str(code).zfill(6) for code in result)
            except Exception:
                logger.debug(
                    "symbol_index.get_codes_by_market 失败 (market=%s, engine=%s)",
                    market,
                    self._symbol_index_engine,
                    exc_info=True,
                )

        # 回退：从分类字典提取
        records = self.classified_symbols.get(market, [])
        if not records:
            return []
        return sorted(set(str(rec.get("code", "")).zfill(6) for rec in records))

    def get_symbol_info_native(self, code: str) -> Optional[Dict[str, Any]]:
        """返回单个品种信息，原生不可用时回退到 Python 实现。"""
        self._ensure_symbol_index()
        if self._symbol_index is None:
            return None

        getter = getattr(self._symbol_index, "get_symbol", None)
        normalised = code.zfill(6)
        if getter is not None:
            try:
                result = getter(normalised)
                if result is not None:
                    return dict(result)
            except Exception:
                logger.debug(
                    "symbol_index.get_symbol 失败 (code=%s, engine=%s)",
                    normalised,
                    self._symbol_index_engine,
                    exc_info=True,
                )

        # 回退：在分类字典中查找
        for records in self.classified_symbols.values():
            for rec in records:
                if str(rec.get("code", "")).zfill(6) == normalised:
                    return dict(rec)
        return None

    async def load_from_api_async(
        self, startup_mode: bool = False, shared_retry_pool=None
    ) -> pd.DataFrame:
        """异步从TDX API加载所有品种

        Args:
            startup_mode: 是否为启动模式(步骤4),如果是则使用固定最快2个IPv4服务器(1进程2协程)

        Returns:
            包含所有品种的DataFrame(code, name, market列)
        """
        scenario = "refresh_symbol_list"

        # 启动模式:使用固定最快2个IPv4服务器
        if startup_mode:
            return await self._load_from_api_async_startup()

        logger.debug(
            "[SYMBOL-LOADER] 开始从TDX API加载品种列表",
            extra={"log_type": "SYSTEM", "scenario": scenario},
        )
        logger.info(
            "[SYMBOL-LOADER] ℹ️ 开始从TDX API加载品种列表...",
            extra={"log_type": "SYSTEM", "scenario": scenario},
        )

        # 使用RetryConnectionPool进行两阶段重试
        from backend.infrastructure.tdx_asyncio.retry_connection_pool import RetryConnectionPool
        from backend.infrastructure.data_module_vnpy.load_balancer import get_server_pool_manager

        # 获取ServerPoolManager实例
        pool_mgr = get_server_pool_manager()

        # 🔧 修复:确保服务器池中有可用服务器
        # 如果服务器池中没有可用服务器,使用默认服务器列表
        mixed_servers = pool_mgr.get_mixed_servers(shuffle=False, exclude=None)
        if not mixed_servers:
            logger.warning(
                "⚠️ 服务器池中无可用服务器,使用默认服务器列表(回退方案)",
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )
            # 使用默认服务器列表(从constants.py)
            from backend.infrastructure.tdx_asyncio.constants import BROKER_SERVERS_7709

            if not BROKER_SERVERS_7709:
                logger.error(
                    "[SYMBOL-LOADER] ❌ 默认服务器列表为空,无法加载品种",
                    extra={"log_type": "ALERT", "scenario": scenario},
                )
                return pd.DataFrame()

            # ✅ 使用BROKER_SERVERS_7709的第一个服务器作为回退方案
            broker_name, ip, port, max_conn = BROKER_SERVERS_7709[0]

            logger.info(
                f"[SYMBOL-LOADER] 使用默认服务器回退方案: {ip}:{port}",
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )

            # 回退到单连接方式(使用原有逻辑)
            # 创建临时API连接
            api = AsyncTdxHq_API()
            try:
                connected = await api.connect(ip, port, time_out=5.0)
                if not connected:
                    logger.error(
                        f"[SYMBOL-LOADER] ❌ 连接默认服务器失败: {ip}:{port}",
                        extra={"log_type": "ALERT", "scenario": scenario},
                    )
                    return pd.DataFrame()

                logger.info(
                    f"[SYMBOL-LOADER] ✅ 已连接到默认服务器: {ip}:{port}",
                    extra={"log_type": "SYSTEM", "scenario": scenario},
                )

                # 使用单连接方式获取品种列表(保持原有逻辑)
                return await self._load_with_single_connection(api, scenario)
            finally:
                try:
                    await api.disconnect()
                except Exception:
                    pass

        # 使用共享连接池(如果提供)或创建新的连接池
        if shared_retry_pool is not None:
            logger.debug(
                "[SYMBOL-LOADER] 使用共享RetryConnectionPool(步骤4仅使用其中2个连接:深证和上证各一个)",
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )
            retry_pool = shared_retry_pool
            # 步骤4使用共享连接池时,连接池已包含所有服务器连接,但实际使用时会自动选择最优服务器
        else:
            logger.debug(
                "[SYMBOL-LOADER] 开始创建RetryConnectionPool: phase1_max=10, phase2_max=5",
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )

            # 创建RetryConnectionPool
            retry_pool = RetryConnectionPool(
                server_pool_manager=pool_mgr,
                phase1_max_attempts=10,
                phase2_max_attempts=5,
                connection_timeout=5.0,
                enable_connection_pool=True,
            )

        logger.info(
            "[SYMBOL-LOADER] ✅ RetryConnectionPool已创建,使用两阶段重试机制",
            extra={"log_type": "SYSTEM", "scenario": scenario},
        )

        try:
            # 并发获取深证和上证品种(分页获取所有数据)
            async def fetch_all_market_symbols(market: int) -> pd.DataFrame:
                """分页获取指定市场的所有品种(使用RetryConnectionPool实现真正并发)

                Args:
                    market: 市场代码(0=深证,1=上证)

                Returns:
                    包含所有品种的DataFrame
                """
                all_results = []
                start = 0
                page_size = 1000  # 每页最多1000条
                market_name = "深证" if market == 0 else "上证"
                attempted_servers = []  # 每个市场独立维护已尝试服务器列表

                logger.debug(
                    f"[SYMBOL-LOADER] 开始获取{market_name}品种列表",
                    extra={"log_type": "SYSTEM", "scenario": scenario},
                )
                logger.info(
                    f"[SYMBOL-LOADER] ℹ️ 开始获取{market_name}品种列表",
                    extra={"log_type": "SYSTEM", "scenario": scenario},
                )

                while True:
                    try:
                        # 获取当前页数据
                        page_num = start // page_size + 1
                        logger.debug(
                            f"[SYMBOL-LOADER] 获取{market_name}第{page_num}页数据: start={start}",
                            extra={"log_type": "SYSTEM", "scenario": scenario},
                        )

                        # 使用RetryConnectionPool获取分页数据(使用新的封装函数)
                        async def fetch_page_task(api):
                            """Task executed within the retry pool to fetch a page."""
                            # 使用新的封装函数,但只获取一页数据
                            return await get_security_list_batch(
                                api=api,
                                market=market,
                                start=start,
                                page_size=page_size,
                                max_pages=1,  # 只获取一页
                            )

                        page_result, success = await retry_pool.execute_with_retry(
                            fetch_page_task, attempted_servers, scenario=scenario
                        )

                        if (
                            not success
                            or page_result is None
                            or (isinstance(page_result, list) and len(page_result) == 0)
                        ):
                            # 没有更多数据,退出循环
                            logger.debug(
                                f"[SYMBOL-LOADER] {market_name}第{page_num}页无数据,结束分页获取",
                                extra={"log_type": "SYSTEM", "scenario": scenario},
                            )
                            break

                        all_results.extend(page_result)
                        logger.debug(
                            f"[SYMBOL-LOADER] {market_name}第{page_num}页: 获取{len(page_result)}个品种,累计{len(all_results)}个",
                            extra={"log_type": "SYSTEM", "scenario": scenario},
                        )

                        # 如果返回的数据少于1000条,说明已经是最后一页
                        if len(page_result) < page_size:
                            logger.debug(
                                f"[SYMBOL-LOADER] {market_name}第{page_num}页为最后一页(返回{len(page_result)}<{page_size})",
                                extra={"log_type": "SYSTEM", "scenario": scenario},
                            )
                            break

                        # 继续获取下一页
                        start += page_size

                    except Exception as e:
                        page_num = start // page_size + 1
                        logger.debug(
                            f"[SYMBOL-LOADER] 获取{market_name}第{page_num}页异常详情: {type(e).__name__}: {str(e)}",
                            extra={"log_type": "SYSTEM", "scenario": scenario},
                        )
                        logger.error(
                            f"[SYMBOL-LOADER] ❌ 获取{market_name}第{page_num}页失败: {e}",
                            exc_info=True,
                            extra={"log_type": "ALERT", "scenario": scenario},
                        )
                        logger.warning(
                            f"[SYMBOL-LOADER] ⚠️ 获取{market_name}第{page_num}页失败,已获取{len(all_results)}个品种",
                            extra={"log_type": "ALERT", "scenario": scenario},
                        )
                        break

                if not all_results:
                    logger.debug(
                        f"[SYMBOL-LOADER] {market_name}未获取到任何品种",
                        extra={"log_type": "SYSTEM", "scenario": scenario},
                    )
                    logger.warning(
                        f"[SYMBOL-LOADER] ⚠️ {market_name}未获取到任何品种",
                        extra={"log_type": "ALERT", "scenario": scenario},
                    )
                    return pd.DataFrame()

                # 转换为DataFrame
                df = pd.DataFrame(all_results)
                df["market"] = market
                logger.debug(
                    f"[SYMBOL-LOADER] {market_name}品种转换为DataFrame完成: 记录数={len(df)}",
                    extra={"log_type": "SYSTEM", "scenario": scenario},
                )
                logger.info(
                    f"[SYMBOL-LOADER] ✅ {market_name}总共获取{len(df)}个品种",
                    extra={"log_type": "SYSTEM", "scenario": scenario},
                )
                return df

            # 并发获取两个市场的所有品种
            logger.debug(
                "[SYMBOL-LOADER] 开始并发获取深证和上证品种列表",
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )
            logger.info(
                "[SYMBOL-LOADER] ℹ️ 开始并发获取深证和上证品种列表",
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )
            tasks = [
                fetch_all_market_symbols(market=0),  # 深证
                fetch_all_market_symbols(market=1),  # 上证
            ]

            results = await asyncio.gather(*tasks, return_exceptions=True)

            # 处理结果
            all_symbols = []

            for market, result in enumerate(results):
                market_name = "深证" if market == 0 else "上证"
                if isinstance(result, Exception):
                    logger.debug(
                        f"[SYMBOL-LOADER] 获取{market_name}品种异常详情: {type(result).__name__}: {str(result)}",
                        extra={"log_type": "SYSTEM", "scenario": scenario},
                    )
                    logger.error(
                        f"[SYMBOL-LOADER] ❌ 获取{market_name}品种失败: {result}",
                        extra={"log_type": "ALERT", "scenario": scenario},
                    )
                    continue

                if result is None or (isinstance(result, pd.DataFrame) and result.empty):
                    logger.debug(
                        f"[SYMBOL-LOADER] {market_name}品种列表为空",
                        extra={"log_type": "SYSTEM", "scenario": scenario},
                    )
                    logger.warning(
                        f"[SYMBOL-LOADER] ⚠️ {market_name}品种列表为空",
                        extra={"log_type": "ALERT", "scenario": scenario},
                    )
                    continue

                # result已经是DataFrame,直接添加
                if isinstance(result, pd.DataFrame):
                    all_symbols.append(result)
                    logger.debug(
                        f"[SYMBOL-LOADER] {market_name}品种添加成功: 记录数={len(result)}",
                        extra={"log_type": "SYSTEM", "scenario": scenario},
                    )
                else:
                    logger.warning(
                        f"[SYMBOL-LOADER] ⚠️ {market_name}品种加载失败: 意外的返回类型 {type(result)}",
                        extra={"log_type": "ALERT", "scenario": scenario},
                    )

            # 合并结果
            if not all_symbols:
                logger.debug(
                    "[SYMBOL-LOADER] 未获取到任何品种数据",
                    extra={"log_type": "SYSTEM", "scenario": scenario},
                )
                logger.error(
                    "[SYMBOL-LOADER] ❌ 未获取到任何品种数据",
                    extra={"log_type": "ALERT", "scenario": scenario},
                )
                return pd.DataFrame()

            logger.debug(
                f"[SYMBOL-LOADER] 开始合并品种数据: 市场数={len(all_symbols)}",
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )
            merged_df = pd.concat(all_symbols, ignore_index=True)

            # 代码标准化(补齐6位)
            merged_df["code"] = merged_df["code"].astype(str).str.zfill(6)
            logger.debug(
                f"[SYMBOL-LOADER] 品种代码标准化完成: 总记录数={len(merged_df)}",
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )

            logger.debug(
                f"[SYMBOL-LOADER] 从TDX API加载品种完成: 总记录数={len(merged_df)}",
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )
            logger.info(
                f"[SYMBOL-LOADER] ✅ 从TDX API加载品种完成,共{len(merged_df)}个品种(使用RetryConnectionPool)",
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )

            # 关闭RetryConnectionPool
            try:
                await retry_pool.close_all()
            except Exception as e:
                logger.debug(
                    f"[SYMBOL-LOADER] 关闭RetryConnectionPool异常: {e}",
                    extra={"log_type": "SYSTEM", "scenario": scenario},
                )

            return merged_df

        except Exception as e:
            logger.debug(
                f"[SYMBOL-LOADER] 从TDX API加载品种异常详情: {type(e).__name__}: {str(e)}",
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )
            logger.error(
                f"[SYMBOL-LOADER] ❌ 从TDX API加载品种失败: {e}",
                exc_info=True,
                extra={"log_type": "ALERT", "scenario": scenario},
            )
            logger.critical(
                f"[SYMBOL-LOADER] 🔥 从TDX API加载品种严重失败,可能影响品种分类: {e}",
                exc_info=True,
                extra={"log_type": "ALERT", "scenario": scenario},
            )
            return pd.DataFrame()

        finally:
            # 确保RetryConnectionPool关闭(仅当使用临时连接池时)
            if shared_retry_pool is None:
                try:
                    if "retry_pool" in locals():
                        await retry_pool.close_all()
                except Exception:
                    pass

    async def _load_from_api_async_startup(self) -> pd.DataFrame:
        """Startup mode loader using the two fastest IPv4 servers."""
        scenario = "startup_symbol_load"
        logger.debug(
            "[SYMBOL-LOADER-STARTUP] 🚀 启动模式:开始使用固定最快2个IPv4服务器加载品种列表",
            extra={"log_type": "SYSTEM", "scenario": scenario},
        )
        logger.info(
            "[SYMBOL-LOADER-STARTUP] ℹ️ 启动模式:使用固定最快2个IPv4服务器,分别同步请求上交所和深交所品种",
            extra={"log_type": "SYSTEM", "scenario": scenario},
        )

        # 获取最快2个IPv4服务器
        from backend.infrastructure.data_module_vnpy.load_balancer import get_server_pool_manager

        pool_mgr = get_server_pool_manager()

        fastest_servers = pool_mgr.get_ipv4_servers(limit=2)
        if not fastest_servers:
            logger.error(
                "[SYMBOL-LOADER-STARTUP] ❌ 无可用IPv4服务器,启动模式失败",
                extra={"log_type": "ALERT", "scenario": scenario},
            )
            return pd.DataFrame()

        logger.info(
            f"[SYMBOL-LOADER-STARTUP] ✅ 获取到最快2个IPv4服务器: {len(fastest_servers)}个",
            extra={"log_type": "SYSTEM", "scenario": scenario},
        )

        # 分配服务器:服务器1给深交所,服务器2给上交所
        market_servers = {
            0: fastest_servers[0],  # 深交所使用服务器1
            1: (
                fastest_servers[1] if len(fastest_servers) > 1 else fastest_servers[0]
            ),  # 上交所使用服务器2(如果有的话)
        }

        logger.debug(
            "[SYMBOL-LOADER-STARTUP] 服务器分配完成: 深交所={}:{}, 上交所={}:{}, 连接超时=2秒",
            market_servers[0]["ip"],
            market_servers[0]["port"],
            market_servers[1]["ip"],
            market_servers[1]["port"],
            extra={"log_type": "SYSTEM", "scenario": scenario},
        )

        # 定义市场加载任务(同步请求,每个市场独立使用自己的服务器)
        async def load_market_symbols_sync(market: int) -> pd.DataFrame:
            """同步加载指定市场的所有品种(分页获取)

            Args:
                market: 市场代码(0=深交所,1=上交所)

            Returns:
                该市场的品种DataFrame
            """
            market_name = "深交所" if market == 0 else "上交所"
            server_info = market_servers[market]

            logger.debug(
                f"[SYMBOL-LOADER-STARTUP] 开始同步加载{market_name}品种: 服务器={server_info['ip']}:{server_info['port']}",
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )

            # 尝试列表:先用分配的服务器,如果失败则依次尝试其他服务器
            attempt_servers = (
                [server_info] + [s for s in fastest_servers if s != server_info] + fastest_servers
            )  # 最后再次尝试所有服务器

            all_results = []
            attempted_servers = []  # 已尝试的服务器列表
            max_retries = 5  # 最大重试次数
            page_size = 1000

            for attempt in range(max_retries):
                if not attempt_servers:
                    logger.warning(
                        f"[SYMBOL-LOADER-STARTUP] ⚠️ {market_name}已无可用服务器,停止重试",
                        extra={"log_type": "ALERT", "scenario": scenario},
                    )
                    break

                # 选择当前尝试的服务器
                current_server = attempt_servers.pop(0)
                server_key = f"{current_server['ip']}:{current_server['port']}"

                if server_key in attempted_servers:
                    continue

                attempted_servers.append(server_key)

                logger.debug(
                    f"[SYMBOL-LOADER-STARTUP] {market_name}第{attempt+1}次尝试: 服务器={server_key}",
                    extra={"log_type": "SYSTEM", "scenario": scenario},
                )

                # 创建API连接
                api = AsyncTdxHq_API()
                try:
                    # 快速连接:2秒超时
                    connected = await api.connect(
                        current_server["ip"], current_server["port"], time_out=2.0  # 压低等待时间
                    )

                    if not connected:
                        logger.debug(
                            f"[SYMBOL-LOADER-STARTUP] {market_name}连接失败: {server_key},尝试下一个服务器",
                            extra={"log_type": "SYSTEM", "scenario": scenario},
                        )
                        continue

                    logger.debug(
                        f"[SYMBOL-LOADER-STARTUP] {market_name}连接成功: {server_key},开始分页获取",
                        extra={"log_type": "SYSTEM", "scenario": scenario},
                    )

                    # 分页获取所有品种
                    start = 0
                    page_count = 0

                    while True:
                        try:
                            # 快速获取:使用新的封装函数,但只获取一页数据
                            page_result = await get_security_list_batch(
                                api=api,
                                market=market,
                                start=start,
                                page_size=page_size,
                                max_pages=1,  # 只获取一页
                            )

                            if page_result is None or (
                                isinstance(page_result, list) and len(page_result) == 0
                            ):
                                # 没有更多数据
                                logger.debug(
                                    f"[SYMBOL-LOADER-STARTUP] {market_name}分页结束: 服务器={server_key}, 页数={page_count}, 总品种={len(all_results)}",
                                    extra={"log_type": "SYSTEM", "scenario": scenario},
                                )
                                break

                            all_results.extend(page_result)
                            page_count += 1

                            logger.debug(
                                f"[SYMBOL-LOADER-STARTUP] {market_name}第{page_count}页完成: 服务器={server_key}, 获取{len(page_result)}个,累计{len(all_results)}个",
                                extra={"log_type": "SYSTEM", "scenario": scenario},
                            )

                            # 检查是否为最后一页
                            if len(page_result) < page_size:
                                break

                            # 继续下一页
                            start += page_size

                        except Exception as e:
                            logger.warning(
                                f"[SYMBOL-LOADER-STARTUP] ⚠️ {market_name}分页获取异常: 服务器={server_key}, 页数={page_count}, 错误={e}",
                                extra={"log_type": "ALERT", "scenario": scenario},
                            )
                            # 分页失败,切换服务器重试
                            break

                    # 如果获取到了数据,成功完成
                    if all_results:
                        logger.info(
                            f"[SYMBOL-LOADER-STARTUP] ✅ {market_name}加载成功: 服务器={server_key}, 页数={page_count}, 总品种={len(all_results)}",
                            extra={"log_type": "SYSTEM", "scenario": scenario},
                        )
                        break
                    else:
                        logger.debug(
                            f"[SYMBOL-LOADER-STARTUP] {market_name}未获取到数据: 服务器={server_key},尝试下一个服务器",
                            extra={"log_type": "SYSTEM", "scenario": scenario},
                        )

                except Exception as e:
                    logger.debug(
                        f"[SYMBOL-LOADER-STARTUP] {market_name}连接异常: 服务器={server_key}, 错误={type(e).__name__}: {str(e)}",
                        extra={"log_type": "SYSTEM", "scenario": scenario},
                    )
                finally:
                    # 关闭连接
                    try:
                        await api.disconnect()
                    except Exception:
                        pass

            # 返回结果
            if all_results:
                df = pd.DataFrame(all_results)
                df["market"] = market
                logger.debug(
                    f"[SYMBOL-LOADER-STARTUP] {market_name}数据处理完成: 品种数={len(df)}",
                    extra={"log_type": "SYSTEM", "scenario": scenario},
                )
                return df
            else:
                logger.error(
                    f"[SYMBOL-LOADER-STARTUP] ❌ {market_name}加载失败: 所有服务器重试均失败",
                    extra={"log_type": "ALERT", "scenario": scenario},
                )
                return pd.DataFrame()

        # 并发执行两个市场的加载任务(1进程2协程)
        logger.debug(
            "[SYMBOL-LOADER-STARTUP] 开始并发加载深交所和上交所品种(1进程2协程)",
            extra={"log_type": "SYSTEM", "scenario": scenario},
        )

        tasks = [
            load_market_symbols_sync(market=0),  # 深交所
            load_market_symbols_sync(market=1),  # 上交所
        ]

        # 等待两个任务完成
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 处理结果
        all_symbols = []

        for market, result in enumerate(results):
            market_name = "深交所" if market == 0 else "上交所"
            if isinstance(result, Exception):
                logger.error(
                    f"[SYMBOL-LOADER-STARTUP] ❌ {market_name}加载异常: {result}",
                    extra={"log_type": "ALERT", "scenario": scenario},
                )
                continue

            if result is None or (isinstance(result, pd.DataFrame) and result.empty):
                logger.warning(
                    f"[SYMBOL-LOADER-STARTUP] ⚠️ {market_name}品种列表为空",
                    extra={"log_type": "ALERT", "scenario": scenario},
                )
                continue

            if isinstance(result, pd.DataFrame):
                all_symbols.append(result)
                logger.debug(
                    f"[SYMBOL-LOADER-STARTUP] {market_name}数据合并: 品种数={len(result)}",
                    extra={"log_type": "SYSTEM", "scenario": scenario},
                )

        # 合并结果
        if not all_symbols:
            logger.error(
                "[SYMBOL-LOADER-STARTUP] ❌ 启动模式:所有市场加载失败",
                extra={"log_type": "ALERT", "scenario": scenario},
            )
            return pd.DataFrame()

        logger.debug(
            f"[SYMBOL-LOADER-STARTUP] 开始合并市场数据: 市场数={len(all_symbols)}",
            extra={"log_type": "SYSTEM", "scenario": scenario},
        )

        merged_df = pd.concat(all_symbols, ignore_index=True)

        # 代码标准化(补齐6位)
        merged_df["code"] = merged_df["code"].astype(str).str.zfill(6)

        logger.info(
            f"[SYMBOL-LOADER-STARTUP] ✅ 启动模式完成: 总品种数={len(merged_df)},"
            f"深交所={len([r for r in results if not isinstance(r, Exception) and isinstance(r, pd.DataFrame) and 0 in r['market'].values]) if results[0] is not None and isinstance(results[0], pd.DataFrame) else 0},"
            f"上交所={len([r for r in results if not isinstance(r, Exception) and isinstance(r, pd.DataFrame) and 1 in r['market'].values]) if len(results) > 1 and results[1] is not None and isinstance(results[1], pd.DataFrame) else 0}",
            extra={"log_type": "SYSTEM", "scenario": scenario},
        )

        return merged_df

    async def _load_with_single_connection(
        self, api: AsyncTdxHq_API, scenario: str
    ) -> pd.DataFrame:
        """使用单连接方式加载品种列表(回退方案)

        Args:
            api: AsyncTdxHq_API 连接实例
            scenario: 场景标识

        Returns:
            包含所有品种的DataFrame
        """

        # 并发获取深证和上证品种(分页获取所有数据)
        async def fetch_all_market_symbols(market: int) -> pd.DataFrame:
            """分页获取指定市场的所有品种"""
            all_results = []
            start = 0
            page_size = 1000  # 每页最多1000条
            market_name = "深证" if market == 0 else "上证"

            logger.debug(
                f"[SYMBOL-LOADER] 开始获取{market_name}品种列表",
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )
            logger.info(
                f"[SYMBOL-LOADER] ℹ️ 开始获取{market_name}品种列表",
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )

            while True:
                try:
                    # 获取当前页数据
                    page_num = start // page_size + 1
                    logger.debug(
                        f"[SYMBOL-LOADER] 获取{market_name}第{page_num}页数据: start={start}",
                        extra={"log_type": "SYSTEM", "scenario": scenario},
                    )
                    # 使用新的封装函数,但只获取一页数据
                    page_result = await get_security_list_batch(
                        api=api,
                        market=market,
                        start=start,
                        page_size=page_size,
                        max_pages=1,  # 只获取一页
                    )

                    if page_result is None or (
                        isinstance(page_result, list) and len(page_result) == 0
                    ):
                        # 没有更多数据,退出循环
                        logger.debug(
                            f"[SYMBOL-LOADER] {market_name}第{page_num}页无数据,结束分页获取",
                            extra={"log_type": "SYSTEM", "scenario": scenario},
                        )
                        break

                    all_results.extend(page_result)
                    logger.debug(
                        f"[SYMBOL-LOADER] {market_name}第{page_num}页: 获取{len(page_result)}个品种,累计{len(all_results)}个",
                        extra={"log_type": "SYSTEM", "scenario": scenario},
                    )

                    # 如果返回的数据少于1000条,说明已经是最后一页
                    if len(page_result) < page_size:
                        logger.debug(
                            f"[SYMBOL-LOADER] {market_name}第{page_num}页为最后一页(返回{len(page_result)}<{page_size})",
                            extra={"log_type": "SYSTEM", "scenario": scenario},
                        )
                        break

                    # 继续获取下一页
                    start += page_size

                except Exception as e:
                    page_num = start // page_size + 1
                    logger.debug(
                        f"[SYMBOL-LOADER] 获取{market_name}第{page_num}页异常详情: {type(e).__name__}: {str(e)}",
                        extra={"log_type": "SYSTEM", "scenario": scenario},
                    )
                    logger.error(
                        f"[SYMBOL-LOADER] ❌ 获取{market_name}第{page_num}页失败: {e}",
                        exc_info=True,
                        extra={"log_type": "ALERT", "scenario": scenario},
                    )
                    logger.warning(
                        f"[SYMBOL-LOADER] ⚠️ 获取{market_name}第{page_num}页失败,已获取{len(all_results)}个品种",
                        extra={"log_type": "ALERT", "scenario": scenario},
                    )
                    break

            if not all_results:
                logger.debug(
                    f"[SYMBOL-LOADER] {market_name}未获取到任何品种",
                    extra={"log_type": "SYSTEM", "scenario": scenario},
                )
                logger.warning(
                    f"[SYMBOL-LOADER] ⚠️ {market_name}未获取到任何品种",
                    extra={"log_type": "ALERT", "scenario": scenario},
                )
                return pd.DataFrame()

            # 转换为DataFrame
            df = pd.DataFrame(all_results)
            df["market"] = market
            logger.debug(
                f"[SYMBOL-LOADER] {market_name}品种转换为DataFrame完成: 记录数={len(df)}",
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )
            logger.info(
                f"[SYMBOL-LOADER] ✅ {market_name}总共获取{len(df)}个品种",
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )
            return df

        # 并发获取两个市场的所有品种
        logger.debug(
            "[SYMBOL-LOADER] 开始并发获取深证和上证品种列表(单连接回退模式)",
            extra={"log_type": "SYSTEM", "scenario": scenario},
        )
        logger.info(
            "[SYMBOL-LOADER] ℹ️ 开始并发获取深证和上证品种列表(单连接回退模式)",
            extra={"log_type": "SYSTEM", "scenario": scenario},
        )
        tasks = [
            fetch_all_market_symbols(market=0),  # 深证
            fetch_all_market_symbols(market=1),  # 上证
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 处理结果
        all_symbols = []

        for market, result in enumerate(results):
            market_name = "深证" if market == 0 else "上证"
            if isinstance(result, Exception):
                logger.debug(
                    f"[SYMBOL-LOADER] 获取{market_name}品种异常详情: {type(result).__name__}: {str(result)}",
                    extra={"log_type": "SYSTEM", "scenario": scenario},
                )
                logger.error(
                    f"[SYMBOL-LOADER] ❌ 获取{market_name}品种失败: {result}",
                    extra={"log_type": "ALERT", "scenario": scenario},
                )
                continue

            if result is None or (isinstance(result, pd.DataFrame) and result.empty):
                logger.debug(
                    f"[SYMBOL-LOADER] {market_name}品种列表为空",
                    extra={"log_type": "SYSTEM", "scenario": scenario},
                )
                logger.warning(
                    f"[SYMBOL-LOADER] ⚠️ {market_name}品种列表为空",
                    extra={"log_type": "ALERT", "scenario": scenario},
                )
                continue

            # result已经是DataFrame,直接添加
            if isinstance(result, pd.DataFrame):
                all_symbols.append(result)
                logger.debug(
                    f"[SYMBOL-LOADER] {market_name}品种添加成功: 记录数={len(result)}",
                    extra={"log_type": "SYSTEM", "scenario": scenario},
                )
            else:
                logger.warning(
                    f"[SYMBOL-LOADER] ⚠️ {market_name}品种加载失败: 意外的返回类型 {type(result)}",
                    extra={"log_type": "ALERT", "scenario": scenario},
                )

        # 合并结果
        if not all_symbols:
            logger.debug(
                "[SYMBOL-LOADER] 未获取到任何品种数据",
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )
            logger.error(
                "[SYMBOL-LOADER] ❌ 未获取到任何品种数据",
                extra={"log_type": "ALERT", "scenario": scenario},
            )
            return pd.DataFrame()

        logger.debug(
            f"[SYMBOL-LOADER] 开始合并品种数据: 市场数={len(all_symbols)}",
            extra={"log_type": "SYSTEM", "scenario": scenario},
        )
        merged_df = pd.concat(all_symbols, ignore_index=True)

        # 代码标准化(补齐6位)
        merged_df["code"] = merged_df["code"].astype(str).str.zfill(6)
        logger.debug(
            f"[SYMBOL-LOADER] 品种代码标准化完成: 总记录数={len(merged_df)}",
            extra={"log_type": "SYSTEM", "scenario": scenario},
        )

        logger.debug(
            f"[SYMBOL-LOADER] 从TDX API加载品种完成: 总记录数={len(merged_df)}",
            extra={"log_type": "SYSTEM", "scenario": scenario},
        )
        logger.info(
            f"[SYMBOL-LOADER] ✅ 从TDX API加载品种完成,共{len(merged_df)}个品种(单连接回退模式)",
            extra={"log_type": "SYSTEM", "scenario": scenario},
        )

        return merged_df

    def reload_and_classify(
        self,
        force_reload: bool = False,
        shared_retry_pool=None,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """重新加载并分类品种

        Args:
            force_reload: 是否强制重新加载(忽略缓存)

        Returns:
            分类结果字典,key为分类器名称,value为品种列表
        """
        # 1. 检查缓存
        if not force_reload:
            # 🔧 修复:架构v3.0重构后,方法名从 load_with_date 改为 load_with_validation
            # 返回格式从单个值改为 Tuple[Any, str, bool] (数据, 缓存日期, 是否有效)
            cached_data, cache_date, is_valid = DailyCacheManager.load_with_validation(
                self.cache_file
            )
            if cached_data is not None and is_valid:
                logger.info(
                    f"✅ 从缓存加载品种分类,共 {sum(len(v) for v in cached_data.values())} 个品种"
                )
                self.classified_symbols = cached_data
                self._rebuild_symbol_index(self.classified_symbols)
                return cached_data
            else:
                # 🔧 修复:缓存不存在或已过时,自动从API请求数据生成
                if cached_data is None:
                    logger.info("🔧 品种列表缓存不存在,开始从API自动加载...")
                else:
                    logger.info(
                        f"🔧 品种列表缓存已过时(日期: {cache_date}),开始从API自动重新加载..."
                    )

        # 2. 从API加载(自动生成缓存)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            # 如果提供了共享连接池,传递给load_from_api_async
            self.all_symbols = loop.run_until_complete(
                self.load_from_api_async(shared_retry_pool=shared_retry_pool)
            )
        finally:
            loop.close()

        if self.all_symbols is None or self.all_symbols.empty:
            logger.error("❌ 加载品种失败,返回空结果", extra={"log_type": "ALERT"})
            return {}

        # 3. 执行分类
        scenario = "symbol_list_reload"
        classify_start_time = time.time()
        logger.debug(
            f"[SYMBOL-LOADER] 开始执行品种分类: 总品种数={len(self.all_symbols)}",
            extra={"log_type": "SYSTEM", "scenario": scenario},
        )
        logger.info(
            f"[SYMBOL-LOADER] ℹ️ 开始执行品种分类: 总品种数={len(self.all_symbols)}",
            extra={"log_type": "SYSTEM", "scenario": scenario},
        )

        # 先获取T+0基金代码(用于深证A股过滤)
        t0_fund_classifier = self.classifier_registry.get("T+0基金")
        t0_fund_codes = set()
        if t0_fund_classifier:
            logger.debug(
                "[SYMBOL-LOADER] 开始分类T+0基金",
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )
            logger.info(
                "[SYMBOL-LOADER] ℹ️ 开始分类T+0基金(用于深证A股过滤)",
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )
            t0_funds = t0_fund_classifier.classify(
                self.all_symbols,
                block_parser=self.block_parser,
            )
            t0_fund_codes = {fund["code"] for fund in t0_funds}
            logger.debug(
                f"[SYMBOL-LOADER] T+0基金分类完成: 数量={len(t0_fund_codes)}",
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )
            logger.info(
                f"[SYMBOL-LOADER] ✅ T+0基金分类完成: 数量={len(t0_fund_codes)}",
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )

        # 执行所有分类器
        logger.debug(
            f"[SYMBOL-LOADER] 开始执行所有分类器: 分类器数量={len(self.classifier_registry._classifiers)}",
            extra={"log_type": "SYSTEM", "scenario": scenario},
        )
        logger.info(
            f"[SYMBOL-LOADER] ℹ️ 开始执行所有分类器: 分类器数量={len(self.classifier_registry._classifiers)}",
            extra={"log_type": "SYSTEM", "scenario": scenario},
        )
        try:
            classified = self.classifier_registry.classify_all(
                self.all_symbols,
                tdx_parser=self.tdx_parser,
                block_parser=self.block_parser,
                t0_fund_codes=t0_fund_codes,
            )
            classify_elapsed = time.time() - classify_start_time
        except Exception as e:
            classify_elapsed = time.time() - classify_start_time
            logger.debug(
                f"[SYMBOL-LOADER] 分类执行异常详情: {type(e).__name__}: {str(e)}, 耗时={classify_elapsed:.2f}s",
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )
            logger.error(
                f"[SYMBOL-LOADER] ❌ 分类执行失败: {e}, 耗时={classify_elapsed:.2f}s",
                exc_info=True,
                extra={"log_type": "ALERT", "scenario": scenario},
            )
            logger.critical(
                f"[SYMBOL-LOADER] 🔥 分类执行严重失败,可能影响品种列表加载: {e}, 耗时={classify_elapsed:.2f}s",
                exc_info=True,
                extra={"log_type": "ALERT", "scenario": scenario},
            )
            raise

        # 统计分类结果
        total_classified = sum(len(v) for v in classified.values())
        logger.debug(
            f"[SYMBOL-LOADER] 分类完成: 分类数={len(classified)}, 总品种数={total_classified}, 耗时={classify_elapsed:.2f}s",
            extra={"log_type": "SYSTEM", "scenario": scenario},
        )
        logger.info(
            f"[SYMBOL-LOADER] ✅ 分类完成: 分类数={len(classified)}, 总品种数={total_classified}, 耗时={classify_elapsed:.2f}s",
            extra={"log_type": "SYSTEM", "scenario": scenario},
        )
        for category, symbols in classified.items():
            logger.debug(
                f"[SYMBOL-LOADER] 分类详情: {category}={len(symbols)}个品种",
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )
            if len(symbols) > 0:
                logger.info(
                    f"[SYMBOL-LOADER] ✅ {category}: {len(symbols)}个品种",
                    extra={"log_type": "SYSTEM", "scenario": scenario},
                )

        # 4. 执行过滤
        filter_start_time = time.time()
        logger.debug(
            f"[SYMBOL-LOADER] 开始执行过滤器链: 过滤器数量={len(self.filter_chain._filters)}",
            extra={"log_type": "SYSTEM", "scenario": scenario},
        )
        logger.info(
            f"[SYMBOL-LOADER] ℹ️ 开始执行过滤器链: 过滤器数量={len(self.filter_chain._filters)}",
            extra={"log_type": "SYSTEM", "scenario": scenario},
        )
        # 对每个分类结果应用过滤器链
        filtered_classified = {}
        try:
            for category, symbols in classified.items():
                before_count = len(symbols)
                logger.debug(
                    f"[SYMBOL-LOADER] 开始过滤分类: {category}, 过滤前={before_count}个品种",
                    extra={"log_type": "SYSTEM", "scenario": scenario},
                )
                filtered = self.filter_chain.apply(symbols)
                after_count = len(filtered)
                filtered_count = before_count - after_count
                logger.debug(
                    f"[SYMBOL-LOADER] 过滤完成: {category}, 过滤前={before_count}, 过滤后={after_count}, 过滤掉={filtered_count}",
                    extra={"log_type": "SYSTEM", "scenario": scenario},
                )
                if filtered_count > 0:
                    logger.info(
                        f"[SYMBOL-LOADER] ✅ {category}过滤完成: 过滤前={before_count}, 过滤后={after_count}, 过滤掉={filtered_count}",
                        extra={"log_type": "SYSTEM", "scenario": scenario},
                    )
                filtered_classified[category] = filtered
            filter_elapsed = time.time() - filter_start_time
        except Exception as e:
            filter_elapsed = time.time() - filter_start_time
            logger.debug(
                f"[SYMBOL-LOADER] 过滤执行异常详情: {type(e).__name__}: {str(e)}, 耗时={filter_elapsed:.2f}s",
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )
            logger.error(
                f"[SYMBOL-LOADER] ❌ 过滤执行失败: {e}, 耗时={filter_elapsed:.2f}s",
                exc_info=True,
                extra={"log_type": "ALERT", "scenario": scenario},
            )
            logger.critical(
                f"[SYMBOL-LOADER] 🔥 过滤执行严重失败,可能影响品种列表质量: {e}, 耗时={filter_elapsed:.2f}s",
                exc_info=True,
                extra={"log_type": "ALERT", "scenario": scenario},
            )
            raise

        # 统计过滤结果
        total_filtered = sum(len(v) for v in filtered_classified.values())
        logger.debug(
            f"[SYMBOL-LOADER] 过滤完成: 分类数={len(filtered_classified)}, 总品种数={total_filtered}, 耗时={filter_elapsed:.2f}s",
            extra={"log_type": "SYSTEM", "scenario": scenario},
        )
        logger.info(
            f"[SYMBOL-LOADER] ✅ 过滤完成: 分类数={len(filtered_classified)}, 总品种数={total_filtered}, 耗时={filter_elapsed:.2f}s",
            extra={"log_type": "SYSTEM", "scenario": scenario},
        )

        # 5. 保存缓存
        cache_save_start_time = time.time()
        logger.debug(
            f"[SYMBOL-LOADER] 开始保存品种分类缓存: {self.cache_file}",
            extra={"log_type": "SYSTEM", "scenario": scenario},
        )
        try:
            DailyCacheManager.save_with_date(filtered_classified, self.cache_file)
            cache_save_elapsed = time.time() - cache_save_start_time
            logger.debug(
                f"[SYMBOL-LOADER] 缓存保存完成: 耗时={cache_save_elapsed:.2f}s",
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )
            logger.info(
                f"[SYMBOL-LOADER] ✅ 品种分类缓存已保存: {self.cache_file}, 耗时={cache_save_elapsed:.2f}s",
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )
        except Exception as e:
            cache_save_elapsed = time.time() - cache_save_start_time
            logger.debug(
                f"[SYMBOL-LOADER] 缓存保存异常详情: {type(e).__name__}: {str(e)}, 耗时={cache_save_elapsed:.2f}s",
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )
            logger.error(
                f"[SYMBOL-LOADER] ❌ 缓存保存失败: {e}, 耗时={cache_save_elapsed:.2f}s",
                exc_info=True,
                extra={"log_type": "ALERT", "scenario": scenario},
            )
            logger.warning(
                f"[SYMBOL-LOADER] ⚠️ 缓存保存失败,但品种分类结果已生成: {e}, 耗时={cache_save_elapsed:.2f}s",
                extra={"log_type": "ALERT", "scenario": scenario},
            )

        self.classified_symbols = filtered_classified
        self._rebuild_symbol_index(self.classified_symbols)
        return filtered_classified

    def extract_all_codes(self) -> List[str]:
        """提取所有品种代码

        Returns:
            品种代码列表
        """
        if not self.classified_symbols:
            logger.warning(
                "⚠️ 品种分类结果为空,请先调用 reload_and_classify", extra={"log_type": "SYSTEM"}
            )
            return []

        native_codes = self.get_all_codes_native()
        if native_codes is not None:
            return native_codes

        self._ensure_symbol_index()
        if self._symbol_index is not None:
            try:
                codes = self._symbol_index.all_codes()
                if codes:
                    return list(codes)
            except Exception as exc:  # noqa: BLE001
                logger.debug("native_symbol_index all_codes 查询失败: %s", exc, exc_info=True)

        all_codes = set()
        for symbols in self.classified_symbols.values():
            for symbol in symbols:
                code = symbol.get("code")
                if code:
                    all_codes.add(str(code))

        return sorted(all_codes)

    def extract_codes_by_market(self, markets: List[str]) -> List[str]:
        """按市场提取品种代码

        Args:
            markets: 市场列表,例如 ["上证A股", "深证A股"]

        Returns:
            品种代码列表
        """
        if not self.classified_symbols:
            logger.warning(
                "⚠️ 品种分类结果为空,请先调用 reload_and_classify", extra={"log_type": "SYSTEM"}
            )
            return []

        native_results: List[str] = []
        native_hit = False
        for market in markets:
            native_codes = self.get_codes_by_market_native(market)
            if native_codes is None:
                continue
            native_hit = True
            native_results.extend(native_codes)

        if native_hit and native_results:
            return sorted(set(native_results))

        codes = set()
        for market in markets:
            symbols = self.classified_symbols.get(market, [])
            for symbol in symbols:
                code = symbol.get("code")
                if code:
                    codes.add(str(code))

        return sorted(codes)

    def get_symbol_info(self, code: str) -> Optional[Dict[str, Any]]:
        """获取品种详细信息

        Args:
            code: 品种代码

        Returns:
            品种信息字典,如果不存在则返回None
        """
        if not self.classified_symbols:
            logger.warning(
                "⚠️ 品种分类结果为空,请先调用 reload_and_classify", extra={"log_type": "SYSTEM"}
            )
            return None

        # 标准化代码
        code = code.zfill(6)

        native = self.get_symbol_info_native(code)
        if native is not None:
            return native

        self._ensure_symbol_index()
        if self._symbol_index is not None:
            try:
                result = self._symbol_index.get_symbol(code)
                if result is not None:
                    return dict(result)
            except Exception as exc:  # noqa: BLE001
                logger.debug("native_symbol_index get_symbol 查询失败: %s", exc, exc_info=True)

        # 遍历所有分类查找
        for symbols in self.classified_symbols.values():
            for symbol in symbols:
                if symbol.get("code") == code:
                    return symbol

        return None

    def get_all_classified(self) -> Dict[str, List[Dict[str, Any]]]:
        """获取所有分类的品种列表

        Returns:
            分类结果字典,key为分类器名称,value为品种列表
        """
        return self.classified_symbols


# ==============================================================================
# 导出API(向后兼容)
# ==============================================================================

__all__ = [
    # 日志记录器
    "TaskDetailLogger",
    "get_task_logger",
    "close_task_logger",
    # TDX解析器
    "TdxConfigFileParser",
    "BlockParser",
    # 分类器框架
    "BaseClassifier",
    "ClassifierRegistry",
    "ShanghaiStockClassifier",
    "ShenzhenStockClassifier",
    "BeijingStockClassifier",
    "T0FundClassifier",
    "ConvertibleBondClassifier",
    # 过滤器框架
    "BaseFilter",
    "FilterChain",
    "UnlistedSymbolFilter",
    "DuplicateSymbolFilter",
    "InvalidDataFilter",
    # 品种加载器
    "SymbolLoader",
]


# ==============================================================================
# Part 8: 下载状态机
# ==============================================================================


class DownloadState(Enum):
    """下载状态枚举"""

    IDLE = auto()  # 空闲
    PREPARING = auto()  # 准备中(加载品种列表、连接服务器等)
    RUNNING = auto()  # 运行中
    PAUSED = auto()  # 暂停
    STOPPING = auto()  # 停止中
    COMPLETED = auto()  # 完成
    FAILED = auto()  # 失败
    CANCELLED = auto()  # 取消


class DownloadStateMachine:
    """下载状态机

    管理下载任务的状态流转,支持状态转换验证和事件通知。

    状态流转规则:
    IDLE -> PREPARING -> RUNNING -> COMPLETED
                     -> RUNNING -> PAUSED -> RUNNING
                     -> RUNNING -> STOPPING -> IDLE
                     -> PREPARING/RUNNING -> FAILED -> IDLE
                     -> PREPARING/RUNNING -> CANCELLED -> IDLE
    """

    # 允许的状态转换映射
    ALLOWED_TRANSITIONS = {
        DownloadState.IDLE: [DownloadState.PREPARING],
        DownloadState.PREPARING: [
            DownloadState.RUNNING,
            DownloadState.FAILED,
            DownloadState.CANCELLED,
        ],
        DownloadState.RUNNING: [
            DownloadState.PAUSED,
            DownloadState.STOPPING,
            DownloadState.COMPLETED,
            DownloadState.FAILED,
            DownloadState.CANCELLED,
        ],
        DownloadState.PAUSED: [
            DownloadState.RUNNING,
            DownloadState.STOPPING,
            DownloadState.CANCELLED,
        ],
        DownloadState.STOPPING: [DownloadState.IDLE],
        DownloadState.COMPLETED: [DownloadState.IDLE],
        DownloadState.FAILED: [DownloadState.IDLE],
        DownloadState.CANCELLED: [DownloadState.IDLE],
    }

    def __init__(self, event_engine=None):
        """初始化状态机

        Args:
            event_engine: VnPy EventEngine(用于发送状态变化事件)
        """
        self._state = DownloadState.IDLE
        self._event_engine = event_engine
        self._state_lock = threading.Lock()
        self._state_history = []  # 状态历史记录
        self._transition_callbacks = {}  # 状态转换回调

    @property
    def state(self) -> DownloadState:
        """获取当前状态"""
        with self._state_lock:
            return self._state

    def is_state(self, state: DownloadState) -> bool:
        """检查是否处于指定状态"""
        return self.state == state

    def is_running(self) -> bool:
        """检查是否正在运行"""
        return self.state == DownloadState.RUNNING

    def is_idle(self) -> bool:
        """检查是否空闲"""
        return self.state == DownloadState.IDLE

    def can_start(self) -> bool:
        """检查是否可以开始下载"""
        return self.state == DownloadState.IDLE

    def can_pause(self) -> bool:
        """检查是否可以暂停"""
        return self.state == DownloadState.RUNNING

    def can_resume(self) -> bool:
        """检查是否可以恢复"""
        return self.state == DownloadState.PAUSED

    def can_stop(self) -> bool:
        """检查是否可以停止"""
        return self.state in [DownloadState.PREPARING, DownloadState.RUNNING, DownloadState.PAUSED]

    def transition_to(self, new_state: DownloadState, reason: str = "") -> bool:
        """转换到新状态

        Args:
            new_state: 新状态
            reason: 转换原因(用于日志)

        Returns:
            bool: 转换是否成功
        """
        with self._state_lock:
            old_state = self._state

            # 检查转换是否允许
            allowed = self.ALLOWED_TRANSITIONS.get(old_state, [])
            if new_state not in allowed:
                logger.warning(
                    f"⚠️ 状态转换被拒绝: {old_state.name} -> {new_state.name}, "
                    f"允许的转换: {[s.name for s in allowed]}"
                )
                return False

            # 执行转换
            self._state = new_state

            # 记录历史
            self._state_history.append(
                {
                    "timestamp": datetime.now(),
                    "from": old_state,
                    "to": new_state,
                    "reason": reason,
                }
            )

            logger.info(
                f"✅ 状态转换: {old_state.name} -> {new_state.name}"
                + (f" ({reason})" if reason else "")
            )

            # 执行回调
            self._execute_callbacks(old_state, new_state)

            # 发送事件
            if self._event_engine:
                try:
                    from vnpy.event import Event

                    event = Event(
                        type="download_state_changed",
                        data={
                            "old_state": old_state.name,
                            "new_state": new_state.name,
                            "reason": reason,
                        },
                    )
                    self._event_engine.put(event)
                except Exception as e:
                    logger.warning(f"⚠️ 发送状态变化事件失败: {e}", extra={"log_type": "SYSTEM"})

            return True

    def register_callback(
        self, from_state: DownloadState, to_state: DownloadState, callback: Callable
    ):
        """注册状态转换回调

        Args:
            from_state: 源状态
            to_state: 目标状态
            callback: 回调函数,签名为 callback(from_state, to_state)
        """
        key = (from_state, to_state)
        if key not in self._transition_callbacks:
            self._transition_callbacks[key] = []
        self._transition_callbacks[key].append(callback)

    def _execute_callbacks(self, from_state: DownloadState, to_state: DownloadState):
        """执行状态转换回调"""
        key = (from_state, to_state)
        callbacks = self._transition_callbacks.get(key, [])
        for callback in callbacks:
            try:
                callback(from_state, to_state)
            except Exception as e:
                logger.error(
                    f"❌ 状态转换回调执行失败: {e}", exc_info=True, extra={"log_type": "SYSTEM"}
                )

    def get_state_history(self, limit: int = 10) -> List[Dict]:
        """获取状态历史记录

        Args:
            limit: 返回最近的记录数

        Returns:
            状态历史记录列表
        """
        with self._state_lock:
            return self._state_history[-limit:]

    def reset(self):
        """重置状态机到IDLE状态"""
        with self._state_lock:
            self._state = DownloadState.IDLE
            self._state_history.append(
                {
                    "timestamp": datetime.now(),
                    "from": self._state,
                    "to": DownloadState.IDLE,
                    "reason": "手动重置",
                }
            )


# ==============================================================================
# Part 9: 任务队列管理
# ==============================================================================


# 映射表:为了跨进程传输尽量使用紧凑的数值编码
_DOWNLOAD_INTERVAL_TO_CODE = {"1d": 1, "5m": 2, "1m": 3}
_DOWNLOAD_CODE_TO_INTERVAL = {v: k for k, v in _DOWNLOAD_INTERVAL_TO_CODE.items()}


@dataclass(slots=True)
class DownloadTask:
    """下载任务数据类"""

    symbol: str  # 品种代码
    interval: str  # 周期(1d, 5m, 1m)
    market: str = ""  # 市场(上证、深证、北证)
    category: str = ""  # 分类(上证A股、深证A股等)
    start_date: Optional[date] = None  # 开始日期
    end_date: Optional[date] = None  # 结束日期
    priority: int = 0  # 优先级(数字越大越优先)
    retry_count: int = 0  # 重试次数
    max_retries: int = 3  # 最大重试次数
    task_id: str = field(default_factory=lambda: f"{int(time.time() * 1000000)}")
    created_at: datetime = field(default_factory=datetime.now)
    phase: int = 1  # 下载阶段(1=阶段1混合池,2=阶段2最快30%)
    attempted_servers: List[str] = field(
        default_factory=list
    )  # 已尝试服务器列表(格式:"ip:port")
    phase1_attempts: int = 0  # 阶段1尝试次数
    phase2_attempts: int = 0  # 阶段2尝试次数

    def __hash__(self):
        """支持集合操作"""
        return hash((self.symbol, self.interval))

    def __eq__(self, other):
        """支持比较"""
        if not isinstance(other, DownloadTask):
            return False
        return self.symbol == other.symbol and self.interval == other.interval

    def to_wire_payload(self) -> "DownloadTaskWire":
        """转换为跨进程紧凑载荷."""

        interval_code = _DOWNLOAD_INTERVAL_TO_CODE.get(self.interval, 0)
        start_ordinal = self.start_date.toordinal() if self.start_date else -1
        end_ordinal = self.end_date.toordinal() if self.end_date else -1

        return DownloadTaskWire(
            symbol=self.symbol,
            interval_code=interval_code,
            interval_text=self.interval,
            market=self.market or "",
            category=self.category or "",
            start_ordinal=start_ordinal,
            end_ordinal=end_ordinal,
            priority=int(self.priority),
            retry_count=int(self.retry_count),
            max_retries=int(self.max_retries),
            task_id=self.task_id,
            phase=int(self.phase),
            created_at_ts=self.created_at.timestamp(),
        )

    @classmethod
    def from_wire_payload(cls, payload: "DownloadTaskWire") -> "DownloadTask":
        """从跨进程载荷还原 DownloadTask."""

        interval = _DOWNLOAD_CODE_TO_INTERVAL.get(payload.interval_code, payload.interval_text)
        start_date = date.fromordinal(payload.start_ordinal) if payload.start_ordinal > 0 else None
        end_date = date.fromordinal(payload.end_ordinal) if payload.end_ordinal > 0 else None

        created_at = (
            datetime.fromtimestamp(payload.created_at_ts)
            if payload.created_at_ts > 0
            else datetime.now()
        )

        task_id = payload.task_id or f"{int(time.time() * 1_000_000)}"

        return cls(
            symbol=payload.symbol,
            interval=interval,
            market=payload.market,
            category=payload.category,
            start_date=start_date,
            end_date=end_date,
            priority=payload.priority,
            retry_count=payload.retry_count,
            max_retries=payload.max_retries,
            task_id=task_id,
            created_at=created_at,
            phase=payload.phase,
        )


@dataclass(slots=True)
class DownloadTaskWire:
    """跨进程传输的精简任务载荷."""

    symbol: str
    interval_code: int
    interval_text: str
    market: str
    category: str
    start_ordinal: int
    end_ordinal: int
    priority: int
    retry_count: int
    max_retries: int
    task_id: str
    phase: int
    created_at_ts: float

    def to_download_task(self) -> DownloadTask:
        """便捷还原为 DownloadTask."""

        return DownloadTask.from_wire_payload(self)


class TaskQueueManager:
    """任务队列管理器

    负责管理下载任务队列,支持:
    - FIFO队列
    - 背压控制(队列满时拒绝新任务)
    - 任务去重
    - 任务统计
    """

    def __init__(self, max_queue_size: int = 10000):
        """初始化任务队列管理器

        Args:
            max_queue_size: 最大队列长度
        """
        self.max_queue_size = max_queue_size

        # ✨ 使用高性能优先级队列(支持降级)
        if COLLECTIONS_AVAILABLE and HighPerfPriorityQueue is not None:
            # 使用native实现的高性能优先级队列
            self._task_queue = HighPerfPriorityQueue()
            self._use_native_queue = True
            logger.info("✅ TaskQueueManager使用高性能优先级队列(native_collections)")
        else:
            # 降级到标准FIFO队列
            self._task_queue = queue.Queue(maxsize=max_queue_size)
            self._use_native_queue = False
            logger.info("⚠️ TaskQueueManager使用标准FIFO队列(降级模式)")

        self._pending_tasks = set()  # 待处理任务集合(用于去重)
        self._completed_tasks = set()  # 已完成任务集合
        self._failed_tasks = {}  # 失败任务字典 {task: error_msg}
        self._lock = threading.Lock()

        # 统计信息
        self._stats = {
            "total_added": 0,
            "total_completed": 0,
            "total_failed": 0,
            "total_skipped": 0,
            "queue_full_count": 0,
        }

    def add_task(self, task: DownloadTask, force: bool = False) -> bool:
        """添加任务到队列

        Args:
            task: 下载任务
            force: 是否强制添加(忽略去重)

        Returns:
            bool: 是否成功添加
        """
        with self._lock:
            # 检查队列是否已满(仅对标准队列有效)
            if not self._use_native_queue:
                if self._task_queue.qsize() >= self.max_queue_size:
                    self._stats["queue_full_count"] += 1
                    logger.warning(
                        f"⚠️ 任务队列已满({self.max_queue_size}),拒绝添加任务: "
                        f"{task.symbol}/{task.interval}"
                    )
                    return False
            else:
                # native队列没有固定大小限制,但我们可以检查统计信息
                if self.get_pending_count() >= self.max_queue_size:
                    self._stats["queue_full_count"] += 1
                    logger.warning(
                        f"⚠️ 任务队列已满({self.max_queue_size}),拒绝添加任务: "
                        f"{task.symbol}/{task.interval}"
                    )
                    return False

            # 检查任务是否已存在
            if not force:
                if task in self._pending_tasks or task in self._completed_tasks:
                    self._stats["total_skipped"] += 1
                    logger.debug(f"跳过重复任务: {task.symbol}/{task.interval}")
                    return False

            # 添加到队列
            try:
                if self._use_native_queue:
                    # 使用优先级队列:priority越大越优先
                    self._task_queue.put(task, task.priority)  # type: ignore
                else:
                    # 使用标准FIFO队列
                    self._task_queue.put(task, block=False)
                self._pending_tasks.add(task)
                self._stats["total_added"] += 1
                return True
            except Exception as e:
                logger.error(
                    f"❌ 添加任务失败: {task.symbol}/{task.interval}, 错误: {e}",
                    extra={"log_type": "SYSTEM"},
                )
                return False

    def add_tasks_batch(self, tasks: List[DownloadTask]) -> int:
        """批量添加任务

        Args:
            tasks: 任务列表

        Returns:
            成功添加的任务数量
        """
        success_count = 0
        for task in tasks:
            if self.add_task(task):
                success_count += 1

        logger.info(f"✅ 批量添加任务完成: 成功{success_count}/{len(tasks)}")
        return success_count

    def get_task(self, timeout: Optional[float] = None) -> Optional[DownloadTask]:
        """从队列获取任务

        Args:
            timeout: 超时时间(秒),None表示阻塞等待(仅对标准队列有效)

        Returns:
            下载任务,队列为空则返回None
        """
        try:
            if self._use_native_queue:
                # native优先级队列:get()会返回优先级最高的任务
                # 如果没有任务,返回None(非阻塞)
                if self._task_queue.size() == 0:  # type: ignore
                    return None
                task = self._task_queue.get()  # type: ignore
                return task
            else:
                # 标准队列:支持超时
                task = self._task_queue.get(timeout=timeout)
                return task
        except Exception as e:
            logger.debug(
                f"⚠️ [DownloadTaskQueue] 获取任务超时或失败: {e}", extra={"log_type": "SYSTEM"}
            )
            return None

    def mark_completed(self, task: DownloadTask):
        """标记任务完成

        Args:
            task: 下载任务
        """
        with self._lock:
            if task in self._pending_tasks:
                self._pending_tasks.remove(task)
            self._completed_tasks.add(task)
            self._stats["total_completed"] += 1

    def mark_failed(self, task: DownloadTask, error_msg: str = ""):
        """标记任务失败

        Args:
            task: 下载任务
            error_msg: 错误信息
        """
        with self._lock:
            if task in self._pending_tasks:
                self._pending_tasks.remove(task)
            self._failed_tasks[task] = error_msg
            self._stats["total_failed"] += 1

    def retry_task(self, task: DownloadTask) -> bool:
        """重试任务

        Args:
            task: 下载任务

        Returns:
            bool: 是否成功添加到重试队列
        """
        if task.retry_count >= task.max_retries:
            logger.debug(
                f"[RETRY] 任务重试次数已达上限: symbol={task.symbol}, interval={task.interval}, "
                f"retry_count={task.retry_count}, max_retries={task.max_retries}",
                extra={"log_type": "SYSTEM", "scenario": "data_download"},
            )
            logger.warning(
                f"⚠️ 任务重试次数已达上限: {task.symbol}/{task.interval}, "
                f"重试次数: {task.retry_count}/{task.max_retries}",
                extra={"log_type": "ALERT", "scenario": "data_download"},
            )
            return False

        task.retry_count += 1
        task.priority += 10  # 提高重试任务的优先级

        logger.debug(
            f"[RETRY] 任务加入重试队列: symbol={task.symbol}, interval={task.interval}, "
            f"retry_count={task.retry_count}, priority={task.priority}",
            extra={"log_type": "SYSTEM", "scenario": "data_download"},
        )
        logger.info(
            f"🔄 任务重试: {task.symbol}/{task.interval}, 第{task.retry_count}次重试",
            extra={"log_type": "SYSTEM", "scenario": "data_download"},
        )

        success = self.add_task(task, force=True)
        if success:
            logger.debug(
                f"[RETRY] 任务已成功加入重试队列: symbol={task.symbol}, interval={task.interval}",
                extra={"log_type": "SYSTEM", "scenario": "data_download"},
            )
        else:
            logger.warning(
                f"[RETRY] ⚠️ 任务加入重试队列失败: symbol={task.symbol}, interval={task.interval}",
                extra={"log_type": "ALERT", "scenario": "data_download"},
            )

        return success

    def get_pending_count(self) -> int:
        """获取待处理任务数量"""
        if self._use_native_queue:
            return self._task_queue.size()  # type: ignore
        else:
            return self._task_queue.qsize()

    def get_completed_count(self) -> int:
        """获取已完成任务数量"""
        with self._lock:
            return len(self._completed_tasks)

    def get_failed_count(self) -> int:
        """获取失败任务数量"""
        with self._lock:
            return len(self._failed_tasks)

    def get_stats(self) -> Dict[str, int]:
        """获取统计信息"""
        with self._lock:
            stats = self._stats.copy()
            stats["pending"] = self.get_pending_count()
            stats["completed"] = len(self._completed_tasks)
            stats["failed"] = len(self._failed_tasks)
            return stats

    def get_failed_tasks(self) -> Dict[DownloadTask, str]:
        """获取失败任务列表"""
        with self._lock:
            return self._failed_tasks.copy()

    def clear_completed(self):
        """清空已完成任务记录"""
        with self._lock:
            self._completed_tasks.clear()

    def clear_failed(self):
        """清空失败任务记录"""
        with self._lock:
            self._failed_tasks.clear()

    def reset(self):
        """重置队列管理器"""
        with self._lock:
            # 清空队列
            while not self._task_queue.empty():
                try:
                    self._task_queue.get_nowait()
                except Exception as e:
                    logger.debug(
                        f"⚠️ [DownloadTaskQueue] 清空队列时异常: {e}", extra={"log_type": "SYSTEM"}
                    )
                    break

            # 清空集合
            self._pending_tasks.clear()
            self._completed_tasks.clear()
            self._failed_tasks.clear()

            # 重置统计
            for key in self._stats:
                self._stats[key] = 0

        logger.info("✅ 任务队列管理器已重置")


# ==============================================================================
# Part 10: 连接生命周期管理(已废弃,使用 RetryConnectionPool)
# ==============================================================================
# ConnectionLifecycleManager 类已移除,现在使用 RetryConnectionPool
# RetryConnectionPool 位于 backend/infrastructure/tdx_asyncio/retry_connection_pool.py
# 重构说明:K线下载和IPO日期下载现在都使用 RetryConnectionPool 的两阶段重试机制
# - 阶段1: IPv4+IPv6混合池,最多10次尝试
# - 阶段2: IPv4最快30%服务器,最多5次尝试
# - 每个任务独立维护已尝试服务器列表,避免重复尝试


# ==============================================================================
# Part 11: MultiProcessStockFetcher(多进程股票数据下载器)
# ==============================================================================


class MultiProcessStockFetcher:
    """多进程K线数据下载器

    支持特性:
    - 多进程+多协程:最大2000并发连接
    - 两段式下载:IPv4池→IPv6池(剩余≤ 50任务时切换)
    - 智能负载均衡:集成LoadBalancer动态调整并发
    - 状态管理:支持暂停/恢复/取消
    - 进度同步:使用native_ipc(如可用)
    - 数据存储:集成StorageManager
    """

    def __init__(self, event_engine=None, config_manager: Optional[ConfigManager] = None):
        """初始化下载器

        Args:
            event_engine: VnPy EventEngine(用于事件通知)
            config_manager: 配置管理器
        """
        self.event_engine = event_engine
        self.config_manager = config_manager or ConfigManager()

        # 状态机
        self.state_machine = DownloadStateMachine(event_engine)

        # 任务队列管理器
        self.task_queue_manager = TaskQueueManager(max_queue_size=20000)

        # 存储管理器
        self.storage_manager = StorageManager()

        # 进程管理
        self._worker_processes = []
        self._process_executor = None
        self._stop_event = None
        self._pause_event = None

        # 统计信息
        self._stats = {
            "total_symbols": 0,
            "total_tasks": 0,
            "completed_tasks": 0,
            "failed_tasks": 0,
            "total_bars": 0,
            "start_time": None,
            "end_time": None,
        }

        # 进度回调
        self._progress_callbacks = []

        # 负载均衡器(延迟加载)
        self._load_balancer = None

    def register_progress_callback(self, callback: Callable):
        """注册进度回调函数

        Args:
            callback: 回调函数,签名为 callback(completed, total, message)
        """
        self._progress_callbacks.append(callback)

    def _notify_progress(self, completed: int, total: int, message: str = ""):
        """通知进度更新"""
        for callback in self._progress_callbacks:
            try:
                callback(completed, total, message)
            except Exception as e:
                logger.warning(f"⚠️ 进度回调执行失败: {e}", extra={"log_type": "SYSTEM"})

    def download_incremental_kline(
        self,
        symbols: List[str],
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        intervals: Optional[List[str]] = None,
        use_adaptive: bool = True,
        use_two_phase: bool = True,
        max_workers: int = 4,
        coroutines_per_worker: int = 50,
    ) -> Dict[str, Any]:
        """增量K线数据下载(主入口)

        Args:
            symbols: 品种代码列表
            start_date: 开始日期
            end_date: 结束日期
            intervals: 周期列表,默认 ["1d", "5m", "1m"]
            use_adaptive: 是否启用自适应负载均衡
            use_two_phase: 是否启用两段式下载(IPv4→IPv6)
            max_workers: 最大进程数
            coroutines_per_worker: 每个进程的协程数

        Returns:
            下载结果统计
        """
        import time
        import logging

        start_time = time.time()
        stage_logger = logging.getLogger("task.data_download.stage")

        # 1. 状态检查
        logger.debug(
            "[DOWNLOAD] 检查下载状态", extra={"log_type": "SYSTEM", "scenario": "data_download"}
        )
        if not self.state_machine.can_start():
            current_state = self.state_machine.state.name
            logger.error(
                f"[DOWNLOAD] ❌ 无法开始下载,当前状态: {current_state}",
                extra={"log_type": "ALERT", "scenario": "data_download"},
            )
            raise RuntimeError(f"无法开始下载,当前状态: {current_state}")

        # 2. 转换到PREPARING状态
        logger.debug(
            "[DOWNLOAD] 转换到PREPARING状态",
            extra={"log_type": "SYSTEM", "scenario": "data_download"},
        )
        self.state_machine.transition_to(DownloadState.PREPARING, "开始准备下载")

        try:
            # 3. 准备参数
            intervals = intervals or ["1d", "5m", "1m"]
            start_date = start_date or date(2010, 1, 1)
            end_date = end_date or date.today()

            logger.debug(
                f"[DOWNLOAD] 参数准备: 品种数={len(symbols)}, 周期={intervals}, "
                f"日期范围={start_date} ~ {end_date}, "
                f"进程数={max_workers}, 协程数={coroutines_per_worker}, "
                f"自适应={use_adaptive}, 两段式={use_two_phase}",
                extra={"log_type": "SYSTEM", "scenario": "data_download"},
            )

            # 阶段节点日志(输出到Terminal)
            stage_logger.info(
                f"📍 数据下载开始: 品种数={len(symbols)}, 周期={intervals}, "
                f"日期范围={start_date} ~ {end_date}",
                extra={"log_type": "STAGE_NODE", "scenario": "data_download"},
            )

            logger.info(
                f"[DOWNLOAD] 🚀 开始增量K线下载: "
                f"品种数={len(symbols)}, 周期={intervals}, "
                f"日期范围={start_date} ~ {end_date}, "
                f"进程数={max_workers}, 协程数={coroutines_per_worker}",
                extra={"log_type": "SYSTEM", "scenario": "data_download"},
            )

            # 4. 获取负载均衡配置
            if use_adaptive:
                logger.debug(
                    "[DOWNLOAD] 开始获取负载均衡配置",
                    extra={"log_type": "SYSTEM", "scenario": "data_download"},
                )
                lb_config = self._get_load_balancer_config()
                if lb_config:
                    old_max_workers = max_workers
                    old_coroutines = coroutines_per_worker
                    max_workers = lb_config.get("max_workers", max_workers)
                    coroutines_per_worker = lb_config.get(
                        "coroutines_per_worker", coroutines_per_worker
                    )
                    logger.info(
                        f"[DOWNLOAD] 🧠 负载均衡调整: 进程数={old_max_workers}→{max_workers}, "
                        f"协程数={old_coroutines}→{coroutines_per_worker}",
                        extra={"log_type": "SYSTEM", "scenario": "data_download"},
                    )
                    logger.debug(
                        f"[DOWNLOAD] 负载均衡配置详情: {lb_config}",
                        extra={"log_type": "SYSTEM", "scenario": "data_download"},
                    )
                else:
                    logger.debug(
                        "[DOWNLOAD] 负载均衡配置不可用,使用默认配置",
                        extra={"log_type": "SYSTEM", "scenario": "data_download"},
                    )
            else:
                logger.debug(
                    "[DOWNLOAD] 自适应负载均衡已禁用",
                    extra={"log_type": "SYSTEM", "scenario": "data_download"},
                )

            # 5. 准备任务队列
            logger.debug(
                "[DOWNLOAD] 开始准备任务队列",
                extra={"log_type": "SYSTEM", "scenario": "data_download"},
            )
            task_prep_start_time = time.time()
            tasks = self._prepare_tasks(symbols, intervals, start_date, end_date)
            task_prep_elapsed = time.time() - task_prep_start_time
            logger.info(
                f"[DOWNLOAD] ✅ 任务准备完成: 总数={len(tasks)}, 耗时={task_prep_elapsed:.2f}s",
                extra={"log_type": "SYSTEM", "scenario": "data_download"},
            )
            logger.debug(
                f"[DOWNLOAD] 任务准备详情: 品种数={len(symbols)}, 周期数={len(intervals)}, "
                f"每品种任务数={len(intervals)}, 总任务数={len(tasks)}",
                extra={"log_type": "SYSTEM", "scenario": "data_download"},
            )

            # 6. 加载任务到队列
            logger.debug(
                "[DOWNLOAD] 开始加载任务到队列",
                extra={"log_type": "SYSTEM", "scenario": "data_download"},
            )
            self.task_queue_manager.reset()
            queue_load_start_time = time.time()
            added_count = self.task_queue_manager.add_tasks_batch(tasks)
            queue_load_elapsed = time.time() - queue_load_start_time
            logger.info(
                f"[DOWNLOAD] ✅ 任务已加载到队列: {added_count}/{len(tasks)}, 耗时={queue_load_elapsed:.2f}s",
                extra={"log_type": "SYSTEM", "scenario": "data_download"},
            )
            if added_count < len(tasks):
                skipped_count = len(tasks) - added_count
                logger.warning(
                    f"[DOWNLOAD] ⚠️ 部分任务被跳过: {skipped_count}个任务",
                    extra={"log_type": "ALERT", "scenario": "data_download"},
                )

            # 7. 获取服务器列表
            logger.debug(
                "[DOWNLOAD] 开始获取服务器列表",
                extra={"log_type": "SYSTEM", "scenario": "data_download"},
            )
            server_load_start_time = time.time()
            servers = self._get_servers(use_two_phase)
            server_load_elapsed = time.time() - server_load_start_time
            ipv4_count = len(servers.get("ipv4", []))
            ipv6_count = len(servers.get("ipv6", []))
            logger.info(
                f"[DOWNLOAD] 🌐 服务器列表已加载: IPv4={ipv4_count}, IPv6={ipv6_count}, 耗时={server_load_elapsed:.3f}s",
                extra={"log_type": "SYSTEM", "scenario": "data_download"},
            )
            logger.debug(
                f"[DOWNLOAD] 服务器详情: IPv4服务器={ipv4_count}个, IPv6服务器={ipv6_count}个, "
                f"两段式下载={use_two_phase}",
                extra={"log_type": "SYSTEM", "scenario": "data_download"},
            )

            # 8. 转换到RUNNING状态
            logger.debug(
                "[DOWNLOAD] 转换到RUNNING状态",
                extra={"log_type": "SYSTEM", "scenario": "data_download"},
            )
            self.state_machine.transition_to(DownloadState.RUNNING, "开始下载")

            # 9. 启动多进程下载
            logger.debug(
                f"[DOWNLOAD] 开始启动多进程下载: 进程数={max_workers}, 协程数={coroutines_per_worker}",
                extra={"log_type": "SYSTEM", "scenario": "data_download"},
            )
            download_start_time = time.time()
            results = self._run_multiprocess_download(
                max_workers=max_workers,
                coroutines_per_worker=coroutines_per_worker,
                servers=servers,
                use_two_phase=use_two_phase,
            )
            download_elapsed = time.time() - download_start_time
            logger.debug(
                f"[DOWNLOAD] 多进程下载完成: 耗时={download_elapsed:.2f}s, 结果={results}",
                extra={"log_type": "SYSTEM", "scenario": "data_download"},
            )

            # 10. 转换到COMPLETED状态
            logger.debug(
                "[DOWNLOAD] 转换到COMPLETED状态",
                extra={"log_type": "SYSTEM", "scenario": "data_download"},
            )
            self.state_machine.transition_to(DownloadState.COMPLETED, "下载完成")

            elapsed_ms = (time.time() - start_time) * 1000
            completed = results.get("completed", 0)
            failed = results.get("failed", 0)
            total_bars = results.get("total_bars", 0)
            total_tasks = results.get("total_tasks", 0)

            # 阶段节点日志(输出到Terminal)
            stage_logger.info(
                f"✅ 数据下载完成: 耗时={elapsed_ms:.0f}ms, 成功={completed}, 失败={failed}, 总K线数={total_bars}",
                extra={"log_type": "STAGE_NODE", "scenario": "data_download"},
            )

            logger.info(
                f"[DOWNLOAD] ✅ 增量K线下载完成: 总任务={total_tasks}, 成功={completed}, "
                f"失败={failed}, 总K线数={total_bars}, 总耗时={elapsed_ms:.0f}ms",
                extra={"log_type": "SYSTEM", "scenario": "data_download"},
            )
            logger.debug(
                f"[DOWNLOAD] 下载结果详情: {results}",
                extra={"log_type": "SYSTEM", "scenario": "data_download"},
            )
            return results

        except Exception as e:
            # 转换到FAILED状态
            logger.error(
                f"[DOWNLOAD] ❌ 下载过程发生异常: {e}",
                exc_info=True,
                extra={"log_type": "ALERT", "scenario": "data_download"},
            )
            logger.debug(
                f"[DOWNLOAD] 异常详情: 异常类型={type(e).__name__}, 异常消息={str(e)}",
                extra={"log_type": "SYSTEM", "scenario": "data_download"},
            )
            self.state_machine.transition_to(DownloadState.FAILED, f"下载失败: {e}")

            elapsed_ms = (time.time() - start_time) * 1000

            # 阶段节点日志(输出到Terminal)
            stage_logger.error(
                f"❌ 数据下载失败: {e}, 耗时={elapsed_ms:.0f}ms",
                extra={"log_type": "STAGE_NODE", "scenario": "data_download"},
            )

            logger.error(
                f"[DOWNLOAD] ❌ 增量K线下载失败: {e}, 总耗时={elapsed_ms:.0f}ms",
                exc_info=True,
                extra={"log_type": "ALERT", "scenario": "data_download"},
            )
            raise

    def _prepare_tasks(
        self, symbols: List[str], intervals: List[str], start_date: date, end_date: date
    ) -> List[DownloadTask]:
        """准备下载任务列表

        Args:
            symbols: 品种代码列表
            intervals: 周期列表
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            任务列表
        """
        tasks = []

        for symbol in symbols:
            for interval in intervals:
                task = DownloadTask(
                    symbol=symbol,
                    interval=interval,
                    start_date=start_date,
                    end_date=end_date,
                    phase=1,  # 默认从阶段1开始
                )
                tasks.append(task)

        return tasks

    def _get_servers(self, use_two_phase: bool = True) -> Dict[str, List[Dict]]:
        """获取服务器列表

        Args:
            use_two_phase: 是否启用两段式下载

        Returns:
            {"ipv4": [...], "ipv6": [...]}
        """
        servers = {"ipv4": [], "ipv6": []}

        # 获取IPv4服务器列表
        ipv4_servers = self.config_manager.get("tdx.servers.ipv4", [])
        if isinstance(ipv4_servers, list):
            servers["ipv4"] = ipv4_servers

        # 如果启用两段式,获取IPv6服务器列表
        if use_two_phase:
            ipv6_servers = self.config_manager.get("tdx.servers.ipv6", [])
            if isinstance(ipv6_servers, list):
                servers["ipv6"] = ipv6_servers

        # 如果配置为空,使用默认服务器
        if not servers["ipv4"]:
            servers["ipv4"] = [
                {"ip": "119.147.212.81", "port": 7709, "name": "广东电信1"},
                {"ip": "113.105.73.88", "port": 7709, "name": "广东电信2"},
                {"ip": "113.105.73.86", "port": 7709, "name": "广东电信3"},
            ]

        return servers

    def _get_load_balancer_config(self) -> Optional[Dict[str, Any]]:
        """获取负载均衡配置

        Returns:
            配置字典,如 {"max_workers": 4, "coroutines_per_worker": 50}
        """
        try:
            # 延迟加载 LoadBalancer
            if self._load_balancer is None:
                from .load_balancer import LoadBalancer

                self._load_balancer = LoadBalancer()

            # 获取最优配置
            config = self._load_balancer.get_optimal_config()
            return config
        except Exception as e:
            logger.warning(f"⚠️ 获取负载均衡配置失败: {e}", extra={"log_type": "SYSTEM"})
            return None

    def _run_multiprocess_download(
        self,
        max_workers: int,
        coroutines_per_worker: int,
        servers: Dict[str, List[Dict]],
        use_two_phase: bool,
    ) -> Dict[str, Any]:
        """运行多进程下载

        Args:
            max_workers: 最大进程数
            coroutines_per_worker: 每个进程的协程数
            servers: 服务器列表
            use_two_phase: 是否启用两段式下载

        Returns:
            下载结果统计
        """
        # 创建进程间通信对象(优先使用mp.Queue以避免Manager开销)
        queue_backend = "mp.Queue"
        ctx: Optional[MPBaseContext] = None
        try:
            ctx = mp.get_context("spawn")
            if ctx is None:
                raise RuntimeError("spawn context is unavailable")
            task_queue = ctx.Queue()
            result_queue = ctx.Queue()
            self._stop_event = ctx.Event()
            self._pause_event = ctx.Event()
        except Exception as init_error:  # pragma: no cover - 安全回退
            queue_backend = "manager.Queue"
            logger.warning(
                "[DOWNLOAD] ⚠️ mp.Queue 初始化失败,将回退到 Manager 队列: %s",
                init_error,
                extra={"log_type": "SYSTEM", "scenario": "data_download"},
            )
            manager = mp.Manager()
            task_queue = manager.Queue()
            result_queue = manager.Queue()
            self._stop_event = manager.Event()
            self._pause_event = manager.Event()
            ctx = None

        # 加载任务到进程队列
        logger.debug(
            "[DOWNLOAD] 开始加载任务到进程队列",
            extra={"log_type": "SYSTEM", "scenario": "data_download"},
        )
        total_tasks = 0
        queue_load_start_time = time.time()
        while True:
            task = self.task_queue_manager.get_task(timeout=0.1)
            if task is None:
                break
            payload = task.to_wire_payload()
            task_queue.put(payload)
            total_tasks += 1
        queue_load_elapsed = time.time() - queue_load_start_time

        logger.info(
            f"[DOWNLOAD] 🚀 启动多进程下载: 进程数={max_workers}, 任务数={total_tasks}, "
            f"队列加载耗时={queue_load_elapsed:.2f}s, 队列实现={queue_backend}",
            extra={"log_type": "SYSTEM", "scenario": "data_download"},
        )
        logger.debug(
            f"[DOWNLOAD] 进程队列详情: 进程数={max_workers}, 每进程协程数={coroutines_per_worker}, "
            f"总并发数={max_workers * coroutines_per_worker}, 任务数={total_tasks}",
            extra={"log_type": "SYSTEM", "scenario": "data_download"},
        )

        # 启动Worker进程
        logger.debug(
            "[DOWNLOAD] 开始启动Worker进程",
            extra={"log_type": "SYSTEM", "scenario": "data_download"},
        )
        self._worker_processes = []
        process_start_time = time.time()
        for worker_id in range(max_workers):
            try:
                process_factory = ctx.Process if ctx is not None else mp.Process
                process = process_factory(
                    target=self._worker_process,
                    args=(
                        worker_id,
                        task_queue,
                        result_queue,
                        self.config_manager._config.copy(),
                        servers,
                        self._stop_event,
                        self._pause_event,
                        coroutines_per_worker,
                        use_two_phase,
                    ),
                )
                process.start()
                self._worker_processes.append(process)
                logger.debug(
                    f"[DOWNLOAD] Worker {worker_id} 进程已启动: PID={process.pid}",
                    extra={"log_type": "SYSTEM", "scenario": "data_download"},
                )
            except Exception as e:
                logger.error(
                    f"[DOWNLOAD] ❌ Worker {worker_id} 进程启动失败: {e}",
                    exc_info=True,
                    extra={"log_type": "ALERT", "scenario": "data_download"},
                )
        process_start_elapsed = time.time() - process_start_time
        logger.info(
            f"[DOWNLOAD] ✅ Worker进程启动完成: 进程数={len(self._worker_processes)}/{max_workers}, "
            f"耗时={process_start_elapsed:.2f}s",
            extra={"log_type": "SYSTEM", "scenario": "data_download"},
        )

        # 收集结果
        logger.debug(
            "[DOWNLOAD] 开始收集下载结果", extra={"log_type": "SYSTEM", "scenario": "data_download"}
        )
        results = self._collect_results(result_queue, total_tasks)
        logger.debug(
            f"[DOWNLOAD] 结果收集完成: {results}",
            extra={"log_type": "SYSTEM", "scenario": "data_download"},
        )

        # 等待所有进程结束
        logger.debug(
            "[DOWNLOAD] 开始等待Worker进程结束",
            extra={"log_type": "SYSTEM", "scenario": "data_download"},
        )
        process_join_start_time = time.time()
        for process in self._worker_processes:
            process.join(timeout=5)
            if process.is_alive():
                logger.warning(
                    f"[DOWNLOAD] ⚠️ Worker进程未正常退出,强制终止: PID={process.pid}",
                    extra={"log_type": "ALERT", "scenario": "data_download"},
                )
                process.terminate()
            else:
                logger.debug(
                    f"[DOWNLOAD] Worker进程已正常退出: PID={process.pid}",
                    extra={"log_type": "SYSTEM", "scenario": "data_download"},
                )
        process_join_elapsed = time.time() - process_join_start_time
        logger.debug(
            f"[DOWNLOAD] Worker进程等待完成: 耗时={process_join_elapsed:.2f}s",
            extra={"log_type": "SYSTEM", "scenario": "data_download"},
        )

        return results

    def _collect_results(self, result_queue, total_tasks: int) -> Dict[str, Any]:
        """收集下载结果

        Args:
            result_queue: 结果队列
            total_tasks: 总任务数

        Returns:
            结果统计
        """
        scenario = "data_download"
        completed = 0
        failed = 0
        total_bars = 0
        last_progress_time = time.time()
        progress_report_interval = 5.0  # 每5秒报告一次进度

        logger.debug(
            f"[DOWNLOAD] 开始收集结果: 总任务数={total_tasks}",
            extra={"log_type": "SYSTEM", "scenario": scenario},
        )

        while completed + failed < total_tasks:
            try:
                result = result_queue.get(timeout=1.0)

                if result.get("status") == "success":
                    completed += 1
                    total_bars += result.get("bars", 0)
                    logger.debug(
                        f"[DOWNLOAD] 任务完成: symbol={result.get('symbol')}, "
                        f"interval={result.get('interval')}, bars={result.get('bars', 0)}",
                        extra={"log_type": "SYSTEM", "scenario": scenario},
                    )
                else:
                    failed += 1
                    logger.debug(
                        f"[DOWNLOAD] 任务失败: symbol={result.get('symbol')}, "
                        f"interval={result.get('interval')}, 错误={result.get('error', '未知')}",
                        extra={"log_type": "SYSTEM", "scenario": scenario},
                    )

                # 定期报告进度(每5秒或每100个任务)
                current_time = time.time()
                if (current_time - last_progress_time >= progress_report_interval) or (
                    (completed + failed) % 100 == 0
                ):
                    progress_pct = (
                        ((completed + failed) / total_tasks * 100) if total_tasks > 0 else 0
                    )
                    logger.info(
                        f"[DOWNLOAD] 下载进度: {completed + failed}/{total_tasks} ({progress_pct:.1f}%), "
                        f"成功={completed}, 失败={failed}, K线数={total_bars}",
                        extra={"log_type": "PROGRESS", "scenario": scenario},
                    )
                    last_progress_time = current_time

                # 通知进度
                self._notify_progress(
                    completed + failed, total_tasks, f"已完成: {completed}, 失败: {failed}"
                )

            except Exception as e:
                # 超时,继续等待
                current_progress = completed + failed
                if current_progress < total_tasks:
                    remaining = total_tasks - current_progress
                    logger.debug(
                        f"[DOWNLOAD] 等待结果超时: 已完成={current_progress}/{total_tasks}, "
                        f"剩余={remaining}",
                        extra={"log_type": "SYSTEM", "scenario": scenario},
                    )
                pass

        logger.debug(
            f"[DOWNLOAD] 结果收集完成: 总任务={total_tasks}, 成功={completed}, "
            f"失败={failed}, 总K线数={total_bars}",
            extra={"log_type": "SYSTEM", "scenario": scenario},
        )

        return {
            "total_tasks": total_tasks,
            "completed": completed,
            "failed": failed,
            "total_bars": total_bars,
        }

    @staticmethod
    def _worker_process(
        worker_id: int,
        task_queue,
        result_queue,
        config_dict,
        servers,
        stop_event,
        pause_event,
        coroutines_per_worker: int,
        use_two_phase: bool,
    ):
        """
        Worker进程主函数

                Args:
                    worker_id: Worker ID
                    task_queue: 任务队列
                    result_queue: 结果队列
                    config_dict: 配置字典
                    servers: 服务器列表
                    stop_event: 停止事件
                    pause_event: 暂停事件
                    coroutines_per_worker: 协程数
                    use_two_phase: 是否使用两段式下载
        """
        # 配置子进程日志(传入场景标记data_download)
        subprocess_logger = configure_subprocess_logging(
            worker_id, "kline_download", scenario="data_download"
        )

        try:
            subprocess_logger.info(
                f"🚀 Worker {worker_id} 启动 (数据下载)",
                extra={"log_type": "SYSTEM", "scenario": "data_download"},
            )

            # 创建新的事件循环
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            subprocess_logger.debug(
                f"[SUBPROCESS-{worker_id}] 事件循环已创建",
                extra={"log_type": "SYSTEM", "scenario": "data_download"},
            )

            # 运行异步下载
            loop.run_until_complete(
                MultiProcessStockFetcher._download_worker_async(
                    worker_id=worker_id,
                    task_queue=task_queue,
                    result_queue=result_queue,
                    config_dict=config_dict,
                    servers=servers,
                    stop_event=stop_event,
                    pause_event=pause_event,
                    coroutines_per_worker=coroutines_per_worker,
                    use_two_phase=use_two_phase,
                    subprocess_logger=subprocess_logger,
                )
            )

            subprocess_logger.info(
                f"✅ Worker {worker_id} 正常退出 (数据下载完成)",
                extra={"log_type": "SYSTEM", "scenario": "data_download"},
            )

        except Exception as e:
            subprocess_logger.error(
                f"❌ Worker {worker_id} 异常退出: {e}",
                exc_info=True,
                extra={"log_type": "ALERT", "scenario": "data_download"},
            )
        finally:
            try:
                loop.close()
                subprocess_logger.debug(
                    f"[SUBPROCESS-{worker_id}] 事件循环已关闭",
                    extra={"log_type": "SYSTEM", "scenario": "data_download"},
                )
            except Exception as e:
                subprocess_logger.debug(
                    f"⚠️ [Worker {worker_id}] 关闭事件循环失败: {e}",
                    extra={"log_type": "SYSTEM", "scenario": "data_download"},
                )
                pass

    @staticmethod
    async def _download_worker_async(
        worker_id: int,
        task_queue,
        result_queue,
        config_dict,
        servers,
        stop_event,
        pause_event,
        coroutines_per_worker: int,
        use_two_phase: bool,
        subprocess_logger,
    ):
        """异步下载Worker

        Args:
            worker_id: Worker ID
            task_queue: 任务队列
            result_queue: 结果队列
            config_dict: 配置字典
            servers: 服务器列表
            stop_event: 停止事件
            pause_event: 暂停事件
            coroutines_per_worker: 协程数
            use_two_phase: 是否使用两段式下载
            subprocess_logger: 子进程日志记录器
        """
        # 创建存储管理器
        storage_manager = StorageManager()

        # 创建任务详细日志记录器
        task_logger = TaskDetailLogger(worker_id=worker_id)

        scenario = "data_download"

        # 创建ServerPoolManager并初始化RetryConnectionPool
        from .load_balancer import get_server_pool_manager
        from backend.infrastructure.tdx_asyncio.retry_connection_pool import RetryConnectionPool

        subprocess_logger.debug(
            f"[DOWNLOAD-WORKER] Worker {worker_id} 创建ServerPoolManager和RetryConnectionPool",
            extra={"log_type": "SYSTEM", "scenario": scenario},
        )

        server_pool_manager = get_server_pool_manager()
        retry_pool = RetryConnectionPool(
            server_pool_manager=server_pool_manager,
            phase1_max_attempts=10,
            phase2_max_attempts=5,
            connection_timeout=5.0,
        )

        subprocess_logger.info(
            f"[DOWNLOAD-WORKER] ✅ Worker {worker_id} RetryConnectionPool已创建,使用两阶段重试机制",
            extra={"log_type": "SYSTEM", "scenario": scenario},
        )

        # 创建下载协程(每个worker创建多个协程并发处理任务)
        download_tasks = []
        for i in range(coroutines_per_worker):
            task = asyncio.create_task(
                MultiProcessStockFetcher._download_coroutine(
                    worker_id=worker_id,
                    retry_pool=retry_pool,
                    task_queue=task_queue,
                    result_queue=result_queue,
                    storage_manager=storage_manager,
                    task_logger=task_logger,
                    stop_event=stop_event,
                    pause_event=pause_event,
                    subprocess_logger=subprocess_logger,
                )
            )
            download_tasks.append(task)

        # 等待所有下载协程完成
        subprocess_logger.debug(
            f"[DOWNLOAD-WORKER] Worker {worker_id} 启动下载协程: 协程数={len(download_tasks)}",
            extra={"log_type": "SYSTEM", "scenario": scenario},
        )
        subprocess_logger.info(
            f"[DOWNLOAD-WORKER] ℹ️ Worker {worker_id} 启动{len(download_tasks)}个下载协程",
            extra={"log_type": "SYSTEM", "scenario": scenario},
        )
        await asyncio.gather(*download_tasks, return_exceptions=True)

        subprocess_logger.info(
            f"✅ Worker {worker_id} 下载完成", extra={"log_type": "SYSTEM", "scenario": scenario}
        )
        subprocess_logger.debug(
            f"[DOWNLOAD-WORKER] Worker {worker_id} 所有协程已结束",
            extra={"log_type": "SYSTEM", "scenario": scenario},
        )

    @staticmethod
    async def _download_coroutine(
        worker_id: int,
        retry_pool,
        task_queue,
        result_queue,
        storage_manager,
        task_logger,
        stop_event,
        pause_event,
        subprocess_logger,
    ):
        """下载协程(使用RetryConnectionPool)

        Args:
            worker_id: Worker ID
            retry_pool: RetryConnectionPool 实例
            task_queue: 任务队列
            result_queue: 结果队列
            storage_manager: 存储管理器
            task_logger: 任务日志记录器
            stop_event: 停止事件
            pause_event: 暂停事件
            subprocess_logger: 子进程日志记录器
        """
        scenario = "data_download"
        while not stop_event.is_set():
            # 检查暂停
            while pause_event.is_set() and not stop_event.is_set():
                await asyncio.sleep(0.1)

            # 获取任务
            try:
                payload = task_queue.get_nowait()
                if isinstance(payload, DownloadTask):
                    task = payload
                else:
                    task = DownloadTask.from_wire_payload(payload)
                subprocess_logger.debug(
                    f"[DOWNLOAD-WORKER] Worker {worker_id} 获取任务: symbol={task.symbol}, "
                    f"interval={task.interval}",
                    extra={"log_type": "SYSTEM", "scenario": scenario},
                )
            except Exception:
                # 队列为空,退出
                subprocess_logger.debug(
                    f"[DOWNLOAD-WORKER] Worker {worker_id} 任务队列为空,退出协程",
                    extra={"log_type": "SYSTEM", "scenario": scenario},
                )
                break

            # 下载数据(使用RetryConnectionPool)
            start_time = time.time()

            # 确保任务有 attempted_servers 列表
            if not hasattr(task, "attempted_servers") or task.attempted_servers is None:
                task.attempted_servers = []

            try:
                subprocess_logger.debug(
                    f"[DOWNLOAD-WORKER] Worker {worker_id} 开始下载: symbol={task.symbol}, "
                    f"interval={task.interval}, 已尝试服务器={len(task.attempted_servers)}",
                    extra={"log_type": "SYSTEM", "scenario": scenario},
                )
                subprocess_logger.info(
                    f"[DOWNLOAD-WORKER] ℹ️ Worker {worker_id} 开始下载: symbol={task.symbol}, interval={task.interval}",
                    extra={"log_type": "SYSTEM", "scenario": scenario},
                )

                # 定义任务函数
                async def download_task(api):
                    """使用RetryConnectionPool执行下载任务"""
                    return await MultiProcessStockFetcher._download_single_task(
                        api=api,
                        symbol=task.symbol,
                        interval=task.interval,
                        start_date=task.start_date,
                        end_date=task.end_date,
                        subprocess_logger=subprocess_logger,
                    )

                # 使用RetryConnectionPool执行带重试的下载
                bars, success = await retry_pool.execute_with_retry(
                    download_task, task.attempted_servers, scenario=scenario
                )

                # 处理下载结果
                elapsed = time.time() - start_time

                if success and bars is not None and not bars.empty:
                    # 下载成功,保存数据
                    save_start_time = time.time()
                    await storage_manager.save_data_async(
                        symbol=task.symbol,
                        interval=task.interval,
                        df=bars,
                    )
                    save_elapsed = time.time() - save_start_time
                    total_elapsed = time.time() - start_time

                    subprocess_logger.debug(
                        f"[DOWNLOAD-WORKER] Worker {worker_id} 下载成功: symbol={task.symbol}, "
                        f"interval={task.interval}, bars={len(bars)}, "
                        f"尝试服务器={len(task.attempted_servers)}, "
                        f"下载耗时={total_elapsed - save_elapsed:.3f}s, 保存耗时={save_elapsed:.3f}s, 总耗时={total_elapsed:.3f}s",
                        extra={"log_type": "SYSTEM", "scenario": scenario},
                    )
                    subprocess_logger.info(
                        f"[DOWNLOAD-WORKER] ✅ Worker {worker_id} 下载成功: symbol={task.symbol}, "
                        f"interval={task.interval}, bars={len(bars)}, 总耗时={total_elapsed:.3f}s",
                        extra={"log_type": "SYSTEM", "scenario": scenario},
                    )

                    # 记录成功
                    server_info = (
                        f"{len(task.attempted_servers)}个服务器"
                        if task.attempted_servers
                        else "未知服务器"
                    )
                    task_logger.log_task(
                        symbol=task.symbol,
                        interval=task.interval,
                        server=server_info,
                        status="success",
                        data_count=len(bars),
                        elapsed_time=total_elapsed,
                    )

                    # 发送结果
                    safe_put_queue(
                        result_queue,
                        {
                            "status": "success",
                            "symbol": task.symbol,
                            "interval": task.interval,
                            "bars": len(bars),
                            "worker_id": worker_id,
                            "attempted_servers": len(task.attempted_servers),
                        },
                        timeout=1.0,
                        queue_name="result_queue",
                        worker_id=worker_id,
                    )
                elif success and (bars is None or bars.empty):
                    # 下载成功但数据为空
                    subprocess_logger.debug(
                        f"[DOWNLOAD-WORKER] Worker {worker_id} 下载数据为空: symbol={task.symbol}, "
                        f"interval={task.interval}, 尝试服务器={len(task.attempted_servers)}, "
                        f"耗时={elapsed:.3f}s",
                        extra={"log_type": "SYSTEM", "scenario": scenario},
                    )
                    subprocess_logger.warning(
                        f"[DOWNLOAD-WORKER] ⚠️ Worker {worker_id} 下载数据为空: symbol={task.symbol}, "
                        f"interval={task.interval}",
                        extra={"log_type": "ALERT", "scenario": scenario},
                    )

                    server_info = (
                        f"{len(task.attempted_servers)}个服务器"
                        if task.attempted_servers
                        else "未知服务器"
                    )
                    task_logger.log_task(
                        symbol=task.symbol,
                        interval=task.interval,
                        server=server_info,
                        status="empty",
                        data_count=0,
                        elapsed_time=elapsed,
                    )

                    safe_put_queue(
                        result_queue,
                        {
                            "status": "success",
                            "symbol": task.symbol,
                            "interval": task.interval,
                            "bars": 0,
                            "worker_id": worker_id,
                            "attempted_servers": len(task.attempted_servers),
                        },
                        timeout=1.0,
                        queue_name="result_queue",
                        worker_id=worker_id,
                    )
                else:
                    # 两阶段重试均失败
                    subprocess_logger.debug(
                        f"[DOWNLOAD-WORKER] Worker {worker_id} 两阶段重试均失败: symbol={task.symbol}, "
                        f"interval={task.interval}, 总计尝试服务器={len(task.attempted_servers)}, "
                        f"耗时={elapsed:.3f}s",
                        extra={"log_type": "SYSTEM", "scenario": scenario},
                    )
                    subprocess_logger.warning(
                        f"[DOWNLOAD-WORKER] ⚠️ Worker {worker_id} 两阶段重试均失败: symbol={task.symbol}, "
                        f"interval={task.interval}, 尝试了{len(task.attempted_servers)}个服务器",
                        extra={"log_type": "ALERT", "scenario": scenario},
                    )

                    server_info = (
                        f"{len(task.attempted_servers)}个服务器"
                        if task.attempted_servers
                        else "未知服务器"
                    )
                    task_logger.log_task(
                        symbol=task.symbol,
                        interval=task.interval,
                        server=server_info,
                        status="failed_all_servers",
                        data_count=0,
                        elapsed_time=elapsed,
                        error_msg=f"两阶段重试失败,尝试了{len(task.attempted_servers)}个服务器",
                    )

                    safe_put_queue(
                        result_queue,
                        {
                            "status": "failed_all_servers",
                            "symbol": task.symbol,
                            "interval": task.interval,
                            "error": f"两阶段重试失败,尝试了{len(task.attempted_servers)}个服务器",
                            "worker_id": worker_id,
                            "attempted_servers": len(task.attempted_servers),
                        },
                        timeout=1.0,
                        queue_name="result_queue",
                        worker_id=worker_id,
                    )

            except Exception as e:
                # 异常情况
                elapsed = time.time() - start_time
                error_type = type(e).__name__
                error_msg = str(e)

                subprocess_logger.debug(
                    f"[DOWNLOAD-WORKER] Worker {worker_id} 下载异常: symbol={task.symbol}, "
                    f"interval={task.interval}, error_type={error_type}, "
                    f"error_msg={error_msg}, elapsed={elapsed:.2f}s",
                    extra={"log_type": "SYSTEM", "scenario": scenario},
                )
                subprocess_logger.error(
                    f"❌ [Worker {worker_id}] 下载异常: {task.symbol}/{task.interval}, "
                    f"错误: {e}",
                    exc_info=True,
                    extra={"log_type": "ALERT", "scenario": scenario},
                )

                server_info = (
                    f"{len(task.attempted_servers)}个服务器"
                    if task.attempted_servers
                    else "未知服务器"
                )
                task_logger.log_task(
                    symbol=task.symbol,
                    interval=task.interval,
                    server=server_info,
                    status="failed",
                    data_count=0,
                    elapsed_time=elapsed,
                    error_msg=str(e),
                )

                safe_put_queue(
                    result_queue,
                    {
                        "status": "failed",
                        "symbol": task.symbol,
                        "interval": task.interval,
                        "error": str(e),
                        "worker_id": worker_id,
                        "attempted_servers": (
                            len(task.attempted_servers) if hasattr(task, "attempted_servers") else 0
                        ),
                    },
                    timeout=1.0,
                    queue_name="result_queue",
                    worker_id=worker_id,
                )

    @staticmethod
    async def _download_single_task(
        api: AsyncTdxHq_API,
        symbol: str,
        interval: str,
        start_date: Optional[date],
        end_date: Optional[date],
        subprocess_logger,
    ) -> Optional[pd.DataFrame]:
        """下载单个任务的数据

        Args:
            api: TDX API对象
            symbol: 品种代码
            interval: 周期
            start_date: 开始日期
            end_date: 结束日期
            subprocess_logger: 日志记录器

        Returns:
            K线数据 DataFrame
        """
        scenario = "data_download"
        try:
            # 确定市场
            market = get_market_from_code(symbol, strict=False)
            subprocess_logger.debug(
                f"[DOWNLOAD-TASK] 开始下载: symbol={symbol}, interval={interval}, market={market}",
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )

            # 调用TDX API(使用新的封装函数)
            api_start_time = time.time()
            bars = await get_security_bars_safe(
                api=api,
                symbol=symbol,
                interval=interval,
                market=market,
                start=0,
                count=10000,
                timeout=10.0,
            )
            api_elapsed = time.time() - api_start_time

            subprocess_logger.debug(
                f"[DOWNLOAD-TASK] API调用完成: symbol={symbol}, interval={interval}, "
                f"bars_count={len(bars) if bars else 0}, 耗时={api_elapsed:.3f}s",
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )

            # 转换为DataFrame(使用新的封装函数)
            if bars:
                convert_start_time = time.time()
                df = bars_to_dataframe_safe(
                    bars=bars,
                    symbol=symbol,
                    interval=interval,
                    normalize_datetime=True,
                )
                convert_elapsed = time.time() - convert_start_time

                subprocess_logger.debug(
                    f"[DOWNLOAD-TASK] 数据转换完成: symbol={symbol}, interval={interval}, "
                    f"rows={len(df)}, 耗时={convert_elapsed:.3f}s",
                    extra={"log_type": "SYSTEM", "scenario": scenario},
                )
                return df
            else:
                subprocess_logger.debug(
                    f"[DOWNLOAD-TASK] API返回空数据: symbol={symbol}, interval={interval}",
                    extra={"log_type": "SYSTEM", "scenario": scenario},
                )
                return None

        except Exception as e:
            # 错误分类
            error_type = type(e).__name__
            error_msg = str(e)

            # 判断错误类型
            if "timeout" in error_msg.lower() or "timed out" in error_msg.lower():
                error_category = "timeout"
            elif "connection" in error_msg.lower() or "connect" in error_msg.lower():
                error_category = "connection"
            elif "network" in error_msg.lower() or "network" in error_type.lower():
                error_category = "network"
            elif "permission" in error_msg.lower() or "permission denied" in error_msg.lower():
                error_category = "permission"
            else:
                error_category = "unknown"

            subprocess_logger.debug(
                f"[DOWNLOAD-TASK] 下载失败详情: symbol={symbol}, interval={interval}, "
                f"error_type={error_type}, error_category={error_category}, error_msg={error_msg}",
                extra={"log_type": "SYSTEM", "scenario": "data_download"},
            )
            subprocess_logger.error(
                f"❌ [TdxDataReader] 下载数据失败: {symbol}/{interval}, 错误类型={error_category}, 错误: {e}",
                exc_info=True,
                extra={"log_type": "ALERT", "scenario": "data_download"},
            )
            raise

    def pause(self):
        """暂停下载"""
        if self.state_machine.can_pause():
            self.state_machine.transition_to(DownloadState.PAUSED, "用户请求暂停")
            if self._pause_event:
                self._pause_event.set()
            logger.info("⏸️ 下载已暂停")

    def resume(self):
        """恢复下载"""
        if self.state_machine.can_resume():
            self.state_machine.transition_to(DownloadState.RUNNING, "用户请求恢复")
            if self._pause_event:
                self._pause_event.clear()
            logger.info("▶️ 下载已恢复")

    def stop(self):
        """停止下载"""
        if self.state_machine.can_stop():
            self.state_machine.transition_to(DownloadState.STOPPING, "用户请求停止")
            if self._stop_event:
                self._stop_event.set()
            logger.info("⏹️ 下载正在停止...")

            # 等待所有Worker进程结束
            for process in self._worker_processes:
                process.join(timeout=2)

            self.state_machine.transition_to(DownloadState.IDLE, "下载已停止")
            logger.info("✅ 下载已停止")


# ==============================================================================
# Part 12: TaskDetailLogger辅助函数
# ==============================================================================

# 全局TaskDetailLogger实例管理
_task_loggers: Dict[int, TaskDetailLogger] = {}
_task_logger_lock = threading.Lock()


def get_task_logger(worker_id: int = 0, log_dir: str = "logs") -> TaskDetailLogger:
    """获取或创建TaskDetailLogger实例

    Args:
        worker_id: Worker ID
        log_dir: 日志目录

    Returns:
        TaskDetailLogger实例
    """
    with _task_logger_lock:
        if worker_id not in _task_loggers:
            _task_loggers[worker_id] = TaskDetailLogger(worker_id, log_dir)
        return _task_loggers[worker_id]


def close_task_logger(worker_id: int):
    """关闭并移除TaskDetailLogger实例

    Args:
        worker_id: Worker ID
    """
    with _task_logger_lock:
        if worker_id in _task_loggers:
            logger_instance = _task_loggers.pop(worker_id)
            try:
                if hasattr(logger_instance, "close"):
                    logger_instance.close()
            except Exception as e:
                logger.warning(f"⚠️ 关闭任务日志记录器失败: {e}", extra={"log_type": "SYSTEM"})


def close_all_task_loggers():
    """关闭所有TaskDetailLogger实例"""
    with _task_logger_lock:
        for worker_id in list(_task_loggers.keys()):
            close_task_logger(worker_id)


# ==============================================================================
# 导出API(向后兼容)- 更新版
# ==============================================================================

__all__ = [
    # 日志记录器
    "TaskDetailLogger",
    "get_task_logger",
    "close_task_logger",
    "close_all_task_loggers",
    # TDX解析器
    "TdxConfigFileParser",
    "BlockParser",
    # 分类器框架
    "BaseClassifier",
    "ClassifierRegistry",
    "ShanghaiStockClassifier",
    "ShenzhenStockClassifier",
    "BeijingStockClassifier",
    "T0FundClassifier",
    "ConvertibleBondClassifier",
    # 过滤器框架
    "BaseFilter",
    "FilterChain",
    "UnlistedSymbolFilter",
    "DuplicateSymbolFilter",
    "InvalidDataFilter",
    # 品种加载器
    "SymbolLoader",
    # 下载状态管理
    "DownloadState",
    "DownloadStateMachine",
    "DownloadTask",
    "DownloadTaskWire",
    "TaskQueueManager",
    # 数据下载器
    "MultiProcessStockFetcher",
]


# ==============================================================================
# Part 13: TDX二进制数据读取器(已迁移到 tdx_asyncio.readers)
# ==============================================================================
# BaseReader, BjStockDecoder, TdxBinaryReader 已迁移到 backend.infrastructure.tdx_asyncio.readers
# 请使用:from backend.infrastructure.tdx_asyncio import BaseReader, BjStockDecoder, TdxBinaryReader
#
# TdxDataReader 已迁移到 backend.infrastructure.tdx_asyncio.readers.data_reader
# 请使用:from backend.infrastructure.tdx_asyncio import TdxDataReader


# ==============================================================================
# Part 14: TdxDynamicExecutor(动态并发执行器)
# ==============================================================================


class TdxDynamicExecutor:
    """动态并发执行器

    ⚠️ 注意:此类主要用于本地TDX文件的批量读取,属于高级业务逻辑封装。
    如果需要纯底层的并发执行工具,建议使用:
    - asyncio.gather() - 协程并发
    - ProcessPoolExecutor - 多进程并发
    - tdx_asyncio.api.finance.batch_get_ipo_dates_multiprocess - 多进程+协程混合

    用于执行大量并发任务,支持:
    - 多进程+协程执行
    - 动态负载均衡
    - 进度回调
    """

    def __init__(self, max_workers: int = 4, coroutines_per_worker: int = 20):
        """初始化执行器

        Args:
            max_workers: 最大进程数
            coroutines_per_worker: 每个进程的协程数
        """
        self.max_workers = max_workers
        self.coroutines_per_worker = coroutines_per_worker
        self.logger = logging.getLogger("TdxDynamicExecutor")

    def execute(
        self,
        tasks: List[Any],
        task_func: Callable,
        progress_callback: Optional[Callable] = None,
    ) -> List[Any]:
        """执行任务列表

        Args:
            tasks: 任务列表
            task_func: 任务函数,签名为 async task_func(task) -> result
            progress_callback: 进度回调函数

        Returns:
            结果列表
        """
        # 创建进程间通信对象(避免Manager带来的Pickle代理开销)
        executor_ctx: Optional[MPBaseContext] = None
        try:
            executor_ctx = mp.get_context("spawn")
            if executor_ctx is None:
                raise RuntimeError("spawn context is unavailable")
            task_queue = executor_ctx.Queue()
            result_queue = executor_ctx.Queue()
        except Exception as exec_ctx_error:  # pragma: no cover - 兼容回退
            logger.warning(
                "[TdxDynamicExecutor] ⚠️ mp.Queue 初始化失败,回退到 Manager 队列: %s",
                exec_ctx_error,
                extra={"log_type": "SYSTEM", "scenario": "tdx_data_read"},
            )
            manager = mp.Manager()
            task_queue = manager.Queue()
            result_queue = manager.Queue()
            executor_ctx = None

        # 加载任务
        for task in tasks:
            task_queue.put(task)

        # 启动Worker进程
        processes = []
        for worker_id in range(self.max_workers):
            process_factory = (
                executor_ctx.Process if executor_ctx is not None else mp.Process
            )
            process = process_factory(
                target=self._worker_process,
                args=(worker_id, task_queue, result_queue, task_func, self.coroutines_per_worker),
            )
            process.start()
            processes.append(process)

        # 收集结果
        results = []
        total = len(tasks)
        completed = 0

        while completed < total:
            try:
                result = result_queue.get(timeout=1.0)
                results.append(result)
                completed += 1

                if progress_callback:
                    try:
                        progress_callback(completed, total, "")
                    except Exception as e:
                        logger.warning(
                            f"⚠️ [TdxDataReader] 进度回调执行失败: {e}",
                            extra={"log_type": "SYSTEM", "scenario": "tdx_data_read"},
                        )
                        pass
            except Exception as e:
                logger.warning(
                    f"⚠️ [TdxDataReader] 批量读取异常: {e}",
                    extra={"log_type": "ALERT", "scenario": "tdx_data_read"},
                )
                pass

        # 等待所有进程结束
        for process in processes:
            process.join(timeout=2)

        return results

    @staticmethod
    def _worker_process(
        worker_id: int,
        task_queue,
        result_queue,
        task_func: Callable,
        coroutines_per_worker: int,
    ):
        """
        Worker进程主函数

        Args:
            worker_id: Worker ID
            task_queue: 任务队列
            result_queue: 结果队列
            task_func: 任务函数
            coroutines_per_worker: 协程数
        """
        # 配置子进程日志(传入场景标记tdx_data_read)
        subprocess_logger = configure_subprocess_logging(
            worker_id, "tdx_executor", scenario="tdx_data_read"
        )

        try:
            # 创建事件循环
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            # 运行异步Worker
            loop.run_until_complete(
                TdxDynamicExecutor._async_worker(
                    worker_id,
                    task_queue,
                    result_queue,
                    task_func,
                    coroutines_per_worker,
                    subprocess_logger,
                )
            )
        except Exception as e:
            subprocess_logger.error(
                f"Worker {worker_id} 异常: {e}", exc_info=True, extra={"log_type": "SYSTEM"}
            )
        finally:
            try:
                loop.close()
            except Exception as e:
                subprocess_logger.debug(
                    f"⚠️ [Worker {worker_id}] 关闭事件循环失败: {e}", extra={"log_type": "SYSTEM"}
                )
                pass

    @staticmethod
    async def _async_worker(
        worker_id: int,
        task_queue,
        result_queue,
        task_func: Callable,
        coroutines_per_worker: int,
        subprocess_logger,
    ):
        """Execute tasks within the asyncio worker process."""

        # 创建协程池
        async def execute_task():
            while True:
                try:
                    task = task_queue.get_nowait()
                except Exception:
                    break

                try:
                    result = await task_func(task)
                    result_queue.put(result)
                except Exception as e:
                    subprocess_logger.warning(f"任务执行失败: {e}", extra={"log_type": "SYSTEM"})
                    result_queue.put(None)

        # 启动协程池
        scenario = "tdx_data_read"
        subprocess_logger.debug(
            f"[TDX-EXECUTOR-WORKER] Worker {worker_id} 启动协程池: 协程数={coroutines_per_worker}",
            extra={"log_type": "SYSTEM", "scenario": scenario},
        )
        subprocess_logger.info(
            f"[TDX-EXECUTOR-WORKER] ℹ️ Worker {worker_id} 开始处理任务,协程数={coroutines_per_worker}",
            extra={"log_type": "SYSTEM", "scenario": scenario},
        )
        coroutines = [execute_task() for _ in range(coroutines_per_worker)]
        await asyncio.gather(*coroutines, return_exceptions=True)
        subprocess_logger.debug(
            f"[TDX-EXECUTOR-WORKER] Worker {worker_id} 所有协程任务已完成",
            extra={"log_type": "SYSTEM", "scenario": scenario},
        )
        subprocess_logger.info(
            f"[TDX-EXECUTOR-WORKER] ✅ Worker {worker_id} 完成",
            extra={"log_type": "SYSTEM", "scenario": scenario},
        )


# ==============================================================================
# Part 15: IPO日期下载
# ==============================================================================


def download_ipo_dates(
    symbols: List[str],
    progress_callback: Optional[Callable] = None,
    use_multiprocess: bool = True,
    max_workers: int = 4,
    shared_retry_pool=None,
    max_concurrent: Optional[int] = None,
) -> Dict[str, Optional[date]]:
    """Download IPO listing dates.

    Args:
        symbols: Security codes to query.
        progress_callback: Optional progress reporting callback.
        use_multiprocess: Whether to use multiprocessing for fetching.
        max_workers: Maximum worker processes when multiprocessing.
        shared_retry_pool: Optional shared RetryConnectionPool instance.
        max_concurrent: Optional cross-worker concurrency limit.

    Returns:
        Mapping of symbol to IPO date.
    """
    logger.debug(
        f"[IPO-DOWNLOAD] 🚀 开始IPO日期下载: 品种数={len(symbols)}, "
        f"多进程={'是' if use_multiprocess else '否'}, max_workers={max_workers}",
        extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"},
    )

    # 检查缓存
    cache_manager = DailyCacheManager
    # 🔧 修复:使用 ConfigManager 获取缓存目录,确保使用 data/cache 目录
    from backend.infrastructure.data_module_vnpy.core_engine import ConfigManager

    config_manager = ConfigManager.get_instance()
    cache_dir = config_manager.get_cache_dir()
    cache_file = cache_dir / "ipo_dates.json"
    # 🔧 修复:架构v3.0重构后,方法名从 load_with_date 改为 load_with_validation
    cached_data, cache_date, is_valid = cache_manager.load_with_validation(cache_file)

    # 🔧 修复:IPO日期缓存特殊处理 - 即使过期也使用增量更新(不重新下载全部)
    # 使用统一的提取函数处理缓存格式
    from backend.infrastructure.data_module_vnpy.core_engine import ChinaStockEngine

    # 提取已缓存的IPO日期(兼容新旧两种格式)
    cached_dates = ChinaStockEngine._extract_ipo_data_from_cache(cached_data) if cached_data else {}

    # 如果缓存有效,使用增量更新策略
    symbols_to_download: List[str] = []

    if is_valid and cached_dates:
        uncached_symbols = [s for s in symbols if s not in cached_dates]
        if not uncached_symbols:
            logger.debug(
                "[IPO-DOWNLOAD] ✅ 所有IPO日期已缓存",
                extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"},
            )
            return cached_dates
        logger.debug(
            f"[IPO-DOWNLOAD] 📋 缓存命中: {len(symbols) - len(uncached_symbols)}/{len(symbols)}, "
            f"增量下载: {len(uncached_symbols)} 个",
            extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"},
        )
        symbols_to_download = uncached_symbols
    else:
        # 缓存无效或不存在,但即使过期也尝试加载已有数据作为基础(增量更新)
        if cached_data is None:
            logger.debug(
                f"[IPO-DOWNLOAD] 🔧 IPO日期缓存不存在,开始自动下载全部品种(共{len(symbols)}个)...",
                extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"},
            )
        else:
            logger.debug(
                f"[IPO-DOWNLOAD] 🔧 IPO日期缓存已过时(日期: {cache_date}),使用增量更新策略...",
                extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"},
            )
        # 即使过期也尝试加载已有数据作为基础(增量更新)
        # cached_dates已经在上面提取了,这里只需要确定下载列表
        symbols_to_download = symbols

    # 下载未缓存的品种
    if not symbols_to_download:
        logger.warning("⚠️ 没有需要下载的IPO日期(所有品种都已缓存)", extra={"log_type": "SYSTEM"})
        return cached_dates if cached_dates else {}

    # 使用多进程多协程模型:任意协程不会阻塞
    # 当品种数>50时,使用多进程(每个进程内多协程并发)
    # 当品种数<=50时,使用单进程多协程并发
    if use_multiprocess and len(symbols_to_download) > 50:
        logger.info(
            f"[IPO-DOWNLOAD] 开始下载 {len(symbols_to_download)} 个品种的IPO日期: "
            f"模式=多进程多协程, 进程数={max_workers}, 使用LoadBalancer=是",
            extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"},
        )
        new_dates = _download_ipo_dates_multiprocess(
            symbols_to_download, progress_callback, max_workers
        )
    else:
        # 单进程异步模式(支持共享连接池和并发限制)
        if shared_retry_pool is not None:
            logger.info(
                f"[IPO-DOWNLOAD] 开始下载 {len(symbols_to_download)} 个品种的IPO日期: "
                f"模式=单进程异步(共享连接池), 最大并发={max_concurrent if max_concurrent else '无限制'}",
                extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"},
            )
        else:
            logger.info(
                f"[IPO-DOWNLOAD] 开始下载 {len(symbols_to_download)} 个品种的IPO日期: "
                f"模式=单进程多协程, 使用LoadBalancer=是",
                extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"},
            )

        if shared_retry_pool is not None and max_concurrent is not None:
            # 使用共享连接池和并发限制
            new_dates = _download_ipo_dates_async(
                symbols_to_download,
                progress_callback,
                shared_retry_pool=shared_retry_pool,
                max_concurrent=max_concurrent,
            )
        else:
            # 使用原有逻辑(创建新连接池)
            new_dates = _download_ipo_dates_single(symbols_to_download, progress_callback)

    # 合并结果
    all_dates = {**cached_dates, **new_dates}

    # 统计下载结果
    success_count = sum(1 for v in new_dates.values() if v is not None)
    null_count = sum(1 for v in new_dates.values() if v is None)
    logger.info(
        f"[IPO-DOWNLOAD] IPO日期下载完成: 新下载={len(symbols_to_download)}, "
        f"成功={success_count}, null={null_count}, 总缓存={len(all_dates)}/{len(symbols)}",
        extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"},
    )

    # 保存缓存(将日期对象转换为字符串格式)
    # 🎯 关键修复:保存所有品种,包括None值,确保ipo_dates.json与stock_list_classified.json数量一致
    try:
        # 转换日期对象为ISO格式字符串,None值保存为字符串"null"
        serializable_dates = {}
        for symbol, ipo_date in all_dates.items():
            if ipo_date is not None:
                if isinstance(ipo_date, date):
                    serializable_dates[symbol] = ipo_date.isoformat()
                else:
                    serializable_dates[symbol] = ipo_date
            else:
                # ✅ None值保存为字符串"null",确保所有品种都被保存
                serializable_dates[symbol] = "null"

        # 统计有效日期和null值数量
        valid_count = sum(1 for v in serializable_dates.values() if v is not None and v != "null")
        null_count = sum(1 for v in serializable_dates.values() if v is None or v == "null")

        cache_manager.save_with_date(serializable_dates, cache_file)
        logger.info(
            f"[IPO-DOWNLOAD] ✅ IPO日期缓存已保存: {cache_file}, "
            f"总品种={len(serializable_dates)}, 有效日期={valid_count}, null={null_count}",
            extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"},
        )
    except Exception as e:
        logger.error(
            f"[IPO-DOWNLOAD] ❌ 保存IPO日期缓存失败: {e}",
            exc_info=True,
            extra={"log_type": "ALERT", "scenario": "refresh_symbol_list"},
        )
        # 即使保存失败,也返回已下载的数据

    return all_dates


def _download_ipo_dates_single(
    symbols: List[str],
    progress_callback: Optional[Callable] = None,
) -> Dict[str, Optional[date]]:
    # 使用单进程异步并发方式下载IPO日期
    # Args:
    #     symbols: 需要查询的品种代码列表
    #     progress_callback: 可选的进度回调
    # Returns:
    #     品种到IPO日期的映射
    results = {}
    total = len(symbols)

    if not symbols:
        return results

    # 🎯 集成LoadBalancer获取最优配置
    from .load_balancer import LoadBalancer, TaskConfig, TaskCategory, get_server_pool_manager

    # 获取可用服务器数量
    pool_mgr = get_server_pool_manager()
    ipv4_servers = pool_mgr.get_ipv4_servers(limit=1000)
    ipv6_servers = pool_mgr.get_ipv6_servers(limit=1000)
    available_servers = len(ipv4_servers) + len(ipv6_servers)

    logger.debug(
        f"[IPO-DOWNLOAD] 服务器池状态: IPv4={len(ipv4_servers)}, IPv6={len(ipv6_servers)}, 总可用={available_servers}",
        extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"},
    )

    # 创建任务配置
    task_config = TaskConfig(
        name="IPO日期下载",
        category=TaskCategory.NETWORK_DOWNLOAD,
        total_count=total,
        is_io_intensive=True,
        is_cpu_intensive=False,
        estimated_memory_mb=50.0,
        estimated_duration_sec=30.0,
    )

    # 获取LoadBalancer配置
    load_balancer = LoadBalancer()
    config = load_balancer.get_optimal_config(task=task_config, available_servers=available_servers)

    logger.info(
        f"[IPO-DOWNLOAD] 准备使用RetryConnectionPool进行两阶段重试下载",
        extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"},
    )

    # 创建事件循环
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    symbols_for_download: List[str] = list(symbols)

    try:
        # 使用RetryConnectionPool进行两阶段重试
        from backend.infrastructure.tdx_asyncio.retry_connection_pool import RetryConnectionPool

        logger.debug(
            f"[IPO-DOWNLOAD] 开始创建RetryConnectionPool: phase1_max=10, phase2_max=5",
            extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"},
        )

        async def download_with_retry_pool(symbol_list: List[str]):
            # 使用RetryConnectionPool并发下载
            # 创建重试连接池
            retry_pool = RetryConnectionPool(
                server_pool_manager=pool_mgr,
                phase1_max_attempts=10,
                phase2_max_attempts=5,
                connection_timeout=5.0,
            )

            logger.debug(
                f"[IPO-DOWNLOAD] RetryConnectionPool已创建",
                extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"},
            )

            # 创建所有协程任务(每个品种一个协程)
            tasks = []
            for symbol in symbol_list:
                # 为每个品种创建协程任务(使用默认参数避免闭包问题)
                async def fetch_symbol(sym: str = symbol):
                    # 通过 RetryConnectionPool 获取单个品种的 IPO 日期
                    # 每个品种独立维护已尝试服务器列表
                    attempted_servers = []

                    async def fetch_task(api):
                        # 在重试池中执行的单次 IPO 日期抓取任务
                        return await _fetch_single_ipo_date_with_pool(sym, api)

                    # 使用RetryConnectionPool执行带重试的下载
                    result, success = await retry_pool.execute_with_retry(
                        fetch_task, attempted_servers, scenario="refresh_symbol_list"
                    )

                    # 无论成功失败都返回结果(失败为None)
                    return sym, result

                tasks.append(fetch_symbol())

            # 并发执行所有任务,使用asyncio.gather收集结果
            # 使用return_exceptions=True确保单个协程异常不影响其他协程
            logger.info(
                f"[IPO-DOWNLOAD] 开始并发下载: 品种数={len(tasks)}, 使用两阶段重试机制",
                extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"},
            )
            task_results = await asyncio.gather(*tasks, return_exceptions=True)

            progress_stride = max(1, total // 10) if total > 0 else 0
            progress_cb = progress_callback
            callback_wrapper = None
            if progress_cb is not None:
                def _progress_wrapper(current: int, total_count: int, symbol_value: Any) -> None:
                    progress_cb(current, total_count, f"已处理: {symbol_value}")

                callback_wrapper = _progress_wrapper
            reduce_payload = native_reduce_task_results(
                task_results,
                total=total,
                progress_stride=progress_stride,
                progress_callback=callback_wrapper,
                symbols=symbol_list,
            )

            summary = reduce_payload.get("summary", {})
            success_count = int(summary.get("success_count", 0))
            null_count = int(summary.get("null_count", 0))
            error_count = int(summary.get("error_count", 0))
            completed = int(summary.get("total", 0))

            for sym, ipo_date in reduce_payload.get("items", []):
                results[sym] = ipo_date

            for error_msg in reduce_payload.get("errors", []):
                logger.debug(
                    f"[IPO-DOWNLOAD] 协程执行异常: {error_msg}",
                    extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"},
                )

            for milestone in reduce_payload.get("milestones", []):
                if not isinstance(milestone, (list, tuple)) or len(milestone) != 4:
                    continue
                milestone_completed, milestone_success, milestone_null, milestone_errors = milestone
                percent = (milestone_completed / total * 100) if total > 0 else 0
                logger.debug(
                    f"[IPO-DOWNLOAD] 下载进度: {milestone_completed}/{total} ({percent:.1f}%), "
                    f"成功={milestone_success}, null={milestone_null}, 失败={milestone_errors}",
                    extra={"log_type": "PROGRESS", "scenario": "refresh_symbol_list"},
                )

            logger.info(
                f"[IPO-DOWNLOAD] 下载完成: 总数={total}, 成功={success_count}, null={null_count}, 失败={error_count}",
                extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"},
            )

            return results

        # 运行异步函数
        results = loop.run_until_complete(download_with_retry_pool(symbols_for_download))

    except Exception as e:
        logger.error(
            f"[IPO-DOWNLOAD] ❌ IPO日期下载失败: {e}",
            exc_info=True,
            extra={"log_type": "ALERT", "scenario": "refresh_symbol_list"},
        )
        # 失败时返回空结果
        for symbol in symbols:
            if symbol not in results:
                results[symbol] = None
    finally:
        loop.close()

    return results


def _download_ipo_dates_async(
    symbols: List[str],
    progress_callback: Optional[Callable] = None,
    shared_retry_pool=None,
    max_concurrent: Optional[int] = None,
) -> Dict[str, Optional[date]]:
    # 异步下载IPO日期(使用共享连接池和并发限制)
    # Args:
    #     symbols: 品种代码列表
    #     progress_callback: 进度回调函数
    #     shared_retry_pool: 共享的RetryConnectionPool实例
    #     max_concurrent: 最大并发数限制(None=无限制)
    # Returns:
    #     {symbol: ipo_date}
    results = {}
    total = len(symbols)

    if not symbols:
        return results

    scenario = "refresh_symbol_list"
    logger.debug(
        f"[IPO-DOWNLOAD-ASYNC] 开始异步下载IPO日期: 品种数={len(symbols)}, "
        f"共享连接池={'是' if shared_retry_pool else '否'}, "
        f"最大并发={max_concurrent if max_concurrent else '无限制'}",
        extra={"log_type": "SYSTEM", "scenario": scenario},
    )

    # 创建事件循环
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:

        async def download_with_shared_pool(symbol_list: List[str]):
            # 使用共享连接池并发下载
            # 使用共享连接池
            retry_pool = shared_retry_pool

            # 创建并发控制信号量(限制同时运行的协程数)
            semaphore = asyncio.Semaphore(max_concurrent) if max_concurrent else None

            # 🎯 性能埋点:协程创建阶段
            task_creation_start = time.time()

            # 创建所有协程任务(每个品种一个协程)
            async def fetch_symbol_with_limit(sym: str):
                # 获取单个品种的IPO日期(带并发限制)
                # 如果设置了并发限制,先获取信号量
                if semaphore:
                    async with semaphore:
                        return await _fetch_ipo_date_with_retry_pool(sym, retry_pool, scenario)
                else:
                    return await _fetch_ipo_date_with_retry_pool(sym, retry_pool, scenario)

            tasks = [fetch_symbol_with_limit(sym) for sym in symbol_list]
            task_creation_elapsed = (time.time() - task_creation_start) * 1000

            # 🎯 性能埋点:记录连接池状态(执行前)
            pool_stats_before_exec = {}
            try:
                if retry_pool and hasattr(retry_pool, "_phase1_pool") and retry_pool._phase1_pool:
                    phase1_pool = retry_pool._phase1_pool
                    if hasattr(phase1_pool, "get_stats"):
                        pool_stats_before_exec = phase1_pool.get_stats()
            except Exception:
                pass

            logger.info(
                f"[IPO-DOWNLOAD-ASYNC-性能埋点] 协程创建完成: "
                f"任务数={len(tasks)}, "
                f"最大并发={max_concurrent if max_concurrent else '无限制'}, "
                f"协程创建耗时={task_creation_elapsed:.1f}ms, "
                f"连接池状态_执行前={pool_stats_before_exec}",
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )

            logger.info(
                f"[IPO-DOWNLOAD-ASYNC] 开始并发下载: 品种数={len(tasks)}, "
                f"最大并发={max_concurrent if max_concurrent else '无限制'}, 使用共享连接池",
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )

            # 并发执行所有任务
            gather_start_time = time.time()
            task_results = await asyncio.gather(*tasks, return_exceptions=True)
            gather_elapsed = time.time() - gather_start_time

            # 🎯 性能埋点:记录连接池状态(执行后)
            pool_stats_after_exec = {}
            try:
                if retry_pool and hasattr(retry_pool, "_phase1_pool") and retry_pool._phase1_pool:
                    phase1_pool = retry_pool._phase1_pool
                    if hasattr(phase1_pool, "get_stats"):
                        pool_stats_after_exec = phase1_pool.get_stats()
            except Exception:
                pass

            logger.info(
                f"[IPO-DOWNLOAD-ASYNC-性能埋点] 所有协程执行完成: "
                f"任务数={len(tasks)}, "
                f"执行耗时={gather_elapsed:.2f}秒, "
                f"吞吐量={len(tasks)/gather_elapsed:.1f}任务/秒, "
                f"连接池状态_执行后={pool_stats_after_exec}",
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )

            logger.debug(
                f"[IPO-DOWNLOAD-ASYNC] 所有协程任务执行完成: 任务数={len(tasks)}, 耗时={gather_elapsed:.2f}s",
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )

            result_processing_start = time.time()

            progress_stride = max(1, total // 10) if total > 0 else 0
            progress_cb = progress_callback
            callback_wrapper = None
            if progress_cb is not None:
                def _async_progress_wrapper(current: int, total_count: int, symbol_value: Any) -> None:
                    progress_cb(current, total_count, f"已处理: {symbol_value}")

                callback_wrapper = _async_progress_wrapper
            reduce_payload = native_reduce_task_results(
                task_results,
                total=total,
                progress_stride=progress_stride,
                progress_callback=callback_wrapper,
                symbols=symbol_list,
            )

            summary = reduce_payload.get("summary", {})
            success_count = int(summary.get("success_count", 0))
            null_count = int(summary.get("null_count", 0))
            error_count = int(summary.get("error_count", 0))
            completed = int(summary.get("total", 0))

            item_symbols = set()
            for sym, ipo_date in reduce_payload.get("items", []):
                results[sym] = ipo_date
                item_symbols.add(sym)

            for error_msg in reduce_payload.get("errors", []):
                logger.debug(
                    f"[IPO-DOWNLOAD-ASYNC] 协程执行异常: {error_msg}",
                    extra={"log_type": "SYSTEM", "scenario": scenario},
                )

            for sym in reduce_payload.get("error_symbols", []):
                if sym is None or sym in item_symbols:
                    continue
                results[sym] = None

            for milestone in reduce_payload.get("milestones", []):
                if not isinstance(milestone, (list, tuple)) or len(milestone) != 4:
                    continue
                milestone_completed, milestone_success, milestone_null, milestone_errors = milestone
                percent = (milestone_completed / total * 100) if total > 0 else 0
                logger.debug(
                    f"[IPO-DOWNLOAD-ASYNC] 下载进度: {milestone_completed}/{total} ({percent:.1f}%), "
                    f"成功={milestone_success}, null={milestone_null}, 失败={milestone_errors}",
                    extra={"log_type": "PROGRESS", "scenario": scenario},
                )

            result_processing_elapsed = (time.time() - result_processing_start) * 1000

            # 🎯 性能埋点:完整统计信息
            total_elapsed = (time.time() - gather_start_time) * 1000
            avg_time_per_task = (gather_elapsed / total * 1000) if total > 0 else 0
            success_rate = (success_count / total * 100) if total > 0 else 0

            logger.info(
                f"[IPO-DOWNLOAD-ASYNC-性能埋点] 完整统计: "
                f"总耗时={total_elapsed:.1f}ms, "
                f"协程创建耗时={task_creation_elapsed:.1f}ms, "
                f"并发执行耗时={gather_elapsed*1000:.1f}ms, "
                f"结果处理耗时={result_processing_elapsed:.1f}ms, "
                f"总任务数={total}, "
                f"成功数={success_count}, "
                f"null数={null_count}, "
                f"失败数={error_count}, "
                f"成功率={success_rate:.1f}%, "
                f"吞吐量={total/gather_elapsed:.1f}任务/秒, "
                f"平均耗时={avg_time_per_task:.1f}ms/任务, "
                f"最大并发={max_concurrent if max_concurrent else '无限制'}",
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )

            logger.info(
                f"[IPO-DOWNLOAD-ASYNC] 下载完成: 总数={total}, 成功={success_count}, "
                f"null={null_count}, 失败={error_count}, 耗时={gather_elapsed:.2f}s",
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )

            return results

        # 运行异步函数
        results = loop.run_until_complete(download_with_shared_pool(symbols))

    except Exception as e:
        logger.error(
            f"[IPO-DOWNLOAD-ASYNC] ❌ IPO日期下载失败: {e}",
            exc_info=True,
            extra={"log_type": "ALERT", "scenario": scenario},
        )
        # 失败时返回空结果
        for symbol in symbols:
            if symbol not in results:
                results[symbol] = None
    finally:
        loop.close()

    return results


async def _fetch_ipo_date_with_retry_pool(
    symbol: str, retry_pool, scenario: str = "refresh_symbol_list"
) -> Tuple[str, Optional[date]]:
    # 使用RetryConnectionPool获取单个品种的IPO日期(异步函数)
    # Args:
    #     symbol: 品种代码
    #     retry_pool: RetryConnectionPool实例
    #     scenario: 场景标识
    # Returns:
    #     (symbol, ipo_date) 元组
    attempted_servers = []

    async def fetch_task(api):
        # 在重试池内执行的 IPO 日期获取任务

        return await _fetch_single_ipo_date_with_pool(symbol, api)

    # 使用RetryConnectionPool执行带重试的下载
    result, success = await retry_pool.execute_with_retry(
        fetch_task, attempted_servers, scenario=scenario
    )

    # 无论成功失败都返回结果(失败为None)
    return symbol, result


def _download_ipo_dates_multiprocess(
    symbols: List[str],
    progress_callback: Optional[Callable] = None,
    max_workers: int = 4,
) -> Dict[str, Optional[date]]:
    results = {}

    # 分批
    batch_size = (len(symbols) + max_workers - 1) // max_workers
    batches = [symbols[i : i + batch_size] for i in range(0, len(symbols), batch_size)]

    if _NATIVE_SCHEDULER_BRIDGE is not None and _NATIVE_SCHEDULER_BRIDGE.available:
        futures = []
        queue_capacity = max(len(batches) * 2, 1024)
        try:
            _NATIVE_SCHEDULER_BRIDGE.ensure_category(
                "local_read",
                queue_capacity=queue_capacity,
                max_workers=max(1, max_workers),
            )
        except Exception:  # pragma: no cover - 安全回退
            logger.debug(
                "[IPO-下载] native_scheduler.ensure_category 调整失败，继续使用既有配置",
                exc_info=True,
                extra={"log_type": "SYSTEM"},
            )
        for batch in batches:
            if not batch:
                continue
            future = _NATIVE_SCHEDULER_BRIDGE.submit("local_read", _download_ipo_batch, (batch,), None)
            futures.append((future, len(batch)))

        completed = 0
        total = len(symbols)
        for future, batch_size in futures:
            try:
                batch_results = future.result()
            except Exception as e:  # pragma: no cover - 原生调度失败时降级
                logger.warning(f"⚠️ [IPO批量下载] 调度任务失败: {e}", extra={"log_type": "SYSTEM"})
                continue
            results.update(batch_results)
            completed += batch_size
            if progress_callback:
                try:
                    progress_callback(completed, total, "")
                except Exception as e:  # pragma: no cover - 回调异常
                    logger.warning(
                        f"⚠️ [IPO批量下载] 进度回调执行失败: {e}", extra={"log_type": "SYSTEM"}
                    )
        metrics = _NATIVE_SCHEDULER_BRIDGE.get_metrics()
        logger.debug(
            "[IPO-下载] 使用 native 调度: stats=%s", metrics, extra={"log_type": "SYSTEM"}
        )
        return results

    # 使用进程池
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_download_ipo_batch, batch): batch for batch in batches}

        completed = 0
        total = len(symbols)

        for future in as_completed(futures):
            try:
                batch_results = future.result()
                results.update(batch_results)
                completed += len(batch_results)

                if progress_callback:
                    try:
                        progress_callback(completed, total, "")
                    except Exception as e:
                        logger.warning(
                            f"⚠️ [IPO批量下载] 进度回调执行失败: {e}", extra={"log_type": "SYSTEM"}
                        )
                        pass
            except Exception as e:
                logger.warning(f"⚠️ [IPO批量下载] 批量下载失败: {e}", extra={"log_type": "SYSTEM"})

    return results


def _download_ipo_batch(symbols: List[str]) -> Dict[str, Optional[date]]:
    # 借助 tdx_asyncio.batch_get_ipo_dates 批量查询 IPO 日期
    if not symbols:
        return {}

    # 在子进程中创建新的事件循环并调用 tdx_asyncio 的协程版本
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        # 直接使用 tdx_asyncio 的协程版本批量查询
        result = loop.run_until_complete(
            batch_get_ipo_dates(symbols, pool=None, max_concurrent=38, timeout=10.0)
        )
        return result
    finally:
        loop.close()


async def _fetch_single_ipo_date_with_pool(symbol: str, api: AsyncTdxHq_API) -> Optional[date]:
    # 使用连接池获取单个品种IPO日期(协程函数)
    # Args:
    #     symbol: 品种代码
    #     api: TDX API连接(从连接池获取)
    # Returns:
    #     IPO日期
    # 使用新的封装函数(自动处理市场代码、错误处理)
    return await get_ipo_date_safe(
        api=api,
        symbol=symbol,
        market=None,  # 自动判断市场
        timeout=10.0,
    )


# ==============================================================================
# 更新导出API
# ==============================================================================

__all__ = [
    # 日志记录器
    "TaskDetailLogger",
    "get_task_logger",
    "close_task_logger",
    "close_all_task_loggers",
    # TDX解析器
    "TdxConfigFileParser",
    "BlockParser",
    # 分类器框架
    "BaseClassifier",
    "ClassifierRegistry",
    "ShanghaiStockClassifier",
    "ShenzhenStockClassifier",
    "BeijingStockClassifier",
    "T0FundClassifier",
    "ConvertibleBondClassifier",
    # 过滤器框架
    "BaseFilter",
    "FilterChain",
    "UnlistedSymbolFilter",
    "DuplicateSymbolFilter",
    "InvalidDataFilter",
    # 品种加载器
    "SymbolLoader",
    # 下载状态管理
    "DownloadState",
    "DownloadStateMachine",
    "DownloadTask",
    "TaskQueueManager",
    # 数据下载器
    "MultiProcessStockFetcher",
    # TDX读取器(已迁移到 tdx_asyncio,通过 __init__.py 导出)
    # "BaseReader",
    # "BjStockDecoder",
    # "TdxBinaryReader",
    # "TdxDataReader",
    # 动态执行器
    "TdxDynamicExecutor",
    # IPO日期下载
    "download_ipo_dates",
]
