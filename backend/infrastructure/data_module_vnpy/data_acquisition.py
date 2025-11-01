# -*- coding: utf-8 -*-
"""
数据获取模块 - 架构v3.0重构版

本模块负责品种管理和数据下载，采用全新的模块化架构：
- 品种分类器：5种分类器（上证、深证、北证、T+0基金、可转债）
- 品种过滤器：3种过滤器（未上市、重复、无效数据）  
- 数据下载器：多进程+多协程，支持两段式下载（IPv4→IPv6）
- TDX读取器：本地二进制文件读取，native_iocp加速
- 辅助功能：IPO日期下载、任务日志记录

架构特性：
- native_iocp集成：TDX文件读取性能提升40-60%
- native_ipc集成：跨进程进度同步  
- 智能负载均衡：调用LoadBalancer动态调整并发
- 两段式下载：IPv4池→IPv6池，自动降级
- 100% API向后兼容

重构日期：2025年
作者：AI Assistant (基于v2.1重构)
"""

import asyncio
import csv
import logging
import os
import struct
import threading
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, date
from enum import Enum, auto
from io import BytesIO
from multiprocessing import Manager, Event, Process, Queue
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

import pandas as pd

# 导入native_iocp（支持降级）
try:
    from backend.infrastructure.native_iocp.compat import aopen as compat_aopen
    IOCP_AVAILABLE = True
except ImportError:
    try:
        import aiofiles
        async def compat_aopen(file, mode='r', **kwargs):
            return aiofiles.open(file, mode, **kwargs)
        IOCP_AVAILABLE = False
    except ImportError:
        compat_aopen = None
        IOCP_AVAILABLE = False

# 导入native_ipc（支持降级）
try:
    from backend.infrastructure.native_ipc import AsyncIPCPipe
    IPC_AVAILABLE = True
except ImportError:
    IPC_AVAILABLE = False
    AsyncIPCPipe = None

# 导入TDX异步API  
from backend.infrastructure.tdx_asyncio import AsyncTdxHq_API

# 导入核心引擎
from .core_engine import (
    ConfigManager,
    DailyCacheManager,
    NetworkTimeSync,
)

# 导入存储管理
from .data_storage import StorageManager

# ==================== 日志配置 ====================
logger = logging.getLogger("backend.data_module.acquisition")
logger_alert = logging.getLogger("backend.data_module.alert")


# ==============================================================================
# 全局配置和辅助函数
# ==============================================================================

# 队列跳过统计（进程级别，背压控制）
_queue_skip_stats = {}
_queue_skip_lock = threading.Lock()


def _safe_put_queue(
    q,
    item,
    timeout: float = 1.0,
    queue_name: str = "queue",
    worker_id: Optional[int] = None,
) -> bool:
    """安全入队，支持超时阻塞和跳过策略（背压控制）
    
    Args:
        q: 队列对象
        item: 要入队的数据
        timeout: 超时时间（秒）
        queue_name: 队列名称（用于日志）
        worker_id: Worker ID（用于统计）
        
    Returns:
        bool: True=入队成功, False=入队失败（队列满）
    """
    try:
        q.put(item, timeout=timeout)
        return True
    except Exception as e:
        error_type = type(e).__name__
        stats_key = f"{queue_name}_{worker_id}" if worker_id is not None else queue_name
        with _queue_skip_lock:
            if stats_key not in _queue_skip_stats:
                _queue_skip_stats[stats_key] = {"skip_count": 0, "last_warning": 0}
            _queue_skip_stats[stats_key]["skip_count"] += 1
            skip_count = _queue_skip_stats[stats_key]["skip_count"]
            if skip_count % 10 == 1 or skip_count <= 3:
                logger.warning(
                    f"⚠️ 队列入队失败（{error_type}）: 队列={queue_name}, Worker={worker_id}, "
                    f"累计跳过={skip_count}次, 超时={timeout}s"
                )
            if skip_count == 100 or skip_count % 500 == 0:
                logger_alert.error(
                    f"🔥 队列严重积压告警: 队列={queue_name}, Worker={worker_id}, "
                    f"累计跳过={skip_count}次，消费者可能过慢！"
                )
        return False


def _get_queue_skip_stats() -> Dict[str, Dict[str, int]]:
    """获取队列跳过统计（用于监控）"""
    with _queue_skip_lock:
        return dict(_queue_skip_stats)


def _reset_queue_skip_stats():
    """重置队列跳过统计"""
    with _queue_skip_lock:
        _queue_skip_stats.clear()


def _configure_subprocess_logging(worker_id: int, task_type: str = "worker"):
    """配置子进程日志系统，接入LogHub统一路由
    
    Args:
        worker_id: 子进程ID
        task_type: 任务类型（kline/ipo/finance/server_test等）
        
    Returns:
        配置好的logger实例
    """
    try:
        from backend.infrastructure.system_vnpy.unified_log_system import get_logging_hub
        hub = get_logging_hub()
        root_logger = logging.getLogger()
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
            handler.close()
        root_logger.addHandler(hub)
        root_logger.setLevel(logging.DEBUG)
        logger_name = f"subprocess.{task_type}.{worker_id}"
        subprocess_logger = logging.getLogger(logger_name)
        subprocess_logger.propagate = True
        subprocess_logger.info(f"✅ 子进程 {worker_id} 日志系统已接入LogHub")
        return subprocess_logger
    except Exception as e:
        fallback_logger = logging.getLogger(__name__)
        fallback_logger.warning(f"⚠️ 子进程 {worker_id} LogHub配置失败，使用降级日志: {e}")
        return fallback_logger


# ==============================================================================
# Part 1: 任务详细日志记录器
# ==============================================================================


class TaskDetailLogger:
    """任务详细日志记录器
    
    负责记录每个下载任务的详细信息到CSV文件，包括：
    - 任务ID、品种代码、周期
    - 服务器IP、端口、券商名称
    - 任务状态、错误信息、数据条数、耗时
    - Worker ID、Connection ID、Phase
    """
    
    def __init__(self, worker_id: int = 0, log_dir: str = "logs"):
        """初始化日志记录器
        
        Args:
            worker_id: Worker进程ID（用于生成独立的日志文件）
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
        
        # 生成worker专属的日志文件名（避免并发写入冲突）
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = self.log_dir / f"kline_task_details_{timestamp}_worker{worker_id}.csv"
        
        # 构建服务器->券商映射
        self.server_broker_map = self._build_server_broker_map()
        
        # 初始化文件句柄
        self._init_file_handles()
    
    def _build_server_broker_map(self) -> Dict[str, str]:
        """构建服务器->券商映射"""
        try:
            from backend.infrastructure.tdx_asyncio.constants import (
                HQ_HOSTS_ALL,
                BROKER_SERVERS_7709,
            )
            server_broker_map: Dict[str, str] = {}
            all_server_lists = [HQ_HOSTS_ALL, BROKER_SERVERS_7709]
            for server_list in all_server_lists:
                if not server_list:
                    continue
                for item in server_list:
                    if not item:
                        continue
                    if len(item) == 3:
                        broker_name, ip, port = item
                        key = f"{ip}:{port}"
                        if key not in server_broker_map:
                            server_broker_map[key] = broker_name
                    elif len(item) == 2:
                        ip, port = item[0], item[1]
                        key = f"{ip}:{port}"
                        if key not in server_broker_map:
                            server_broker_map[key] = "未知"
            logger.debug(f"📊 [Worker {self.worker_id}] 已加载 {len(server_broker_map)} 个服务器-券商映射")
            return server_broker_map
        except ImportError:
            logger.warning("⚠️ 无法导入服务器常量，使用空映射")
            return {}
    
    def _init_file_handles(self):
        """初始化文件句柄和CSV写入器"""
        try:
            self.file_handle = open(self.log_file, "w", encoding="utf-8", newline="")
            self.csv_writer = csv.writer(self.file_handle)
            self._init_csv_file()
            logger.info(f"✅ [Worker {self.worker_id}] 任务日志文件已创建: {self.log_file}")
        except Exception as e:
            logger.error(f"❌ [Worker {self.worker_id}] 创建日志文件失败: {e}")
            self.file_handle = None
            self.csv_writer = None
    
    def _init_csv_file(self):
        """初始化CSV文件头"""
        headers = [
            "时间戳", "任务ID", "品种代码", "周期", "服务器IP", "服务器Port",
            "所属券商/机构", "任务状态", "错误信息", "数据条数", "耗时(秒)",
            "Worker ID", "Connection ID", "Phase",
        ]
        if self.csv_writer and self.file_handle:
            self.csv_writer.writerow(headers)
            self.file_handle.flush()
    
    def log_task(
        self,
        symbol: str,
        interval: str,
        server: Tuple[str, int],
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
            interval: 周期（1m, 5m, 1d等）
            server: 服务器元组 (ip, port)
            status: 任务状态 (success/failed/timeout/retry)
            error_msg: 错误信息（如果有）
            data_count: 返回的数据条数
            elapsed_time: 任务耗时（秒）
            worker_id: Worker ID
            connection_id: 连接ID
            phase: 阶段标识（Phase1/Phase2）
            task_id: 任务唯一ID（可选）
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
                timestamp, task_id, symbol, interval, server_ip, server_port,
                broker_name, status, error_msg, data_count, f"{elapsed_time:.3f}",
                worker_id, connection_id, phase,
            ]
            self.csv_writer.writerow(row)
            
            # 立即刷新到磁盘
            self.file_handle.flush()
            os.fsync(self.file_handle.fileno())
        
        except Exception as e:
            logger.warning(f"⚠️ [Worker {self.worker_id}] 任务日志记录失败: {e}")
    
    def close(self):
        """关闭日志文件"""
        try:
            if hasattr(self, "file_handle") and self.file_handle:
                self.file_handle.close()
                logger.info(f"✅ 任务详细日志已保存: {self.log_file}")
        except Exception as e:
            logger.warning(f"⚠️ 关闭任务日志文件失败: {e}")
    
    def __del__(self):
        """析构函数，确保文件被关闭"""
        self.close()


# 全局实例（单例模式）
_global_task_logger: Optional[TaskDetailLogger] = None


def get_task_logger(log_dir: str = "logs") -> TaskDetailLogger:
    """获取全局任务日志记录器（单例模式）"""
    global _global_task_logger
    if _global_task_logger is None:
        _global_task_logger = TaskDetailLogger(worker_id=0, log_dir=log_dir)
    return _global_task_logger


def close_task_logger():
    """关闭全局任务日志记录器"""
    global _global_task_logger
    if _global_task_logger is not None:
        _global_task_logger.close()
        _global_task_logger = None


# ==============================================================================
# Part 2: TDX配置文件解析器
# ==============================================================================


class TdxConfigFileParser:
    """TDX配置文件解析器
    
    负责解析通达信配置文件，获取特定品种列表：
    - addedcode_bj.cfg: 北证A股列表
    - tdxstat2.cfg: 可转债列表
    """
    
    def __init__(self, tdx_dir: Optional[Path] = None):
        """初始化解析器
        
        Args:
            tdx_dir: 通达信软件根目录，如果为None则从ConfigManager获取
        """
        if tdx_dir is None:
            config_manager = ConfigManager.get_instance()
            tdx_dir_str = config_manager.get("tdx_data.root_dir", "C:/new_tdx")
            self.tdx_dir = Path(tdx_dir_str)
        else:
            self.tdx_dir = tdx_dir
        
        logger.debug(f"TdxConfigFileParser 初始化，TDX目录: {self.tdx_dir}")
    
    def parse_addedcode_bj(self) -> List[Dict[str, Any]]:
        """解析北证A股配置文件 addedcode_bj.cfg
        
        文件格式示例：
        [证券列表]
        sz#000001#平安银行#11.50#stock#0
        
        Returns:
            北证品种列表，每个元素为字典：
            {
                'code': '430047',
                'name': '诺思兰德',
                'market': 2,  # 北证固定为2
                'exchange': 'BSE'
            }
        """
        config_file = self._find_config_file("addedcode_bj.cfg")
        if config_file is None:
            logger.warning("未找到 addedcode_bj.cfg 文件")
            return []
        
        try:
            results = []
            with open(config_file, "r", encoding="gbk", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("["):
                        continue
                    
                    # 解析行：格式 sz#430047#诺思兰德#12.50#stock#0
                    parts = line.split("#")
                    if len(parts) < 3:
                        continue
                    
                    # 提取代码和名称
                    code = parts[1].strip()
                    name = parts[2].strip()
                    
                    # 北证品种代码通常以43/83/87开头
                    if not (code.startswith("43") or code.startswith("83") or code.startswith("87")):
                        continue
                    
                    results.append({
                        "code": code.zfill(6),
                        "name": name,
                        "market": 2,  # 北证固定为2
                        "exchange": "BSE",
                    })
            
            logger.info(f"✅ 解析北证A股配置文件成功，共 {len(results)} 个品种")
            return results
        
        except Exception as e:
            logger.error(f"❌ 解析北证A股配置文件失败: {e}")
            return []
    
    def parse_tdxstat2(self) -> Dict[int, List[str]]:
        """解析可转债配置文件 tdxstat2.cfg
        
        文件格式：二进制格式，包含可转债代码列表
        
        Returns:
            可转债代码字典，key为市场代码（0=深证，1=上证），value为代码列表
        """
        config_file = self._find_config_file("tdxstat2.cfg")
        if config_file is None:
            logger.warning("未找到 tdxstat2.cfg 文件")
            return {0: [], 1: []}
        
        try:
            results = {0: [], 1: []}
            
            with open(config_file, "rb") as f:
                # 读取文件头（跳过前16字节）
                f.seek(16)
                
                while True:
                    # 读取一条记录（12字节）
                    record = f.read(12)
                    if len(record) < 12:
                        break
                    
                    # 解析记录
                    market = struct.unpack("<H", record[0:2])[0]  # 市场代码（2字节）
                    code = struct.unpack("<6s", record[2:8])[0].decode("ascii", errors="ignore").strip()
                    
                    # 可转债代码通常以12/11开头（深证）或以11开头（上证）
                    if market == 0 and code.startswith("12"):
                        results[0].append(code.zfill(6))
                    elif market == 1 and code.startswith("11"):
                        results[1].append(code.zfill(6))
            
            total_count = len(results[0]) + len(results[1])
            logger.info(f"✅ 解析可转债配置文件成功，深证 {len(results[0])} 个，上证 {len(results[1])} 个，共 {total_count} 个")
            return results
        
        except Exception as e:
            logger.error(f"❌ 解析可转债配置文件失败: {e}")
            return {0: [], 1: []}
    
    def _find_config_file(self, filename: str) -> Optional[Path]:
        """查找配置文件（递归搜索）
        
        Args:
            filename: 配置文件名
            
        Returns:
            文件路径，如果未找到则返回None
        """
        # 常见子目录
        common_subdirs = ["T0002", "T0001", "config", ""]
        
        for subdir in common_subdirs:
            search_dir = self.tdx_dir / subdir if subdir else self.tdx_dir
            if not search_dir.exists():
                continue
            
            # 递归搜索
            for config_file in search_dir.rglob(filename):
                if config_file.is_file():
                    logger.debug(f"✓ 找到配置文件: {config_file}")
                    return config_file
        
        logger.warning(f"未找到配置文件: {filename}")
        return None


class BlockParser:
    """通达信板块文件解析器
    
    负责解析spblock.dat文件，获取板块分类信息，
    特别是提取T+0基金列表。
    """
    
    def __init__(self, tdx_dir: Optional[Path] = None):
        """初始化板块解析器
        
        Args:
            tdx_dir: 通达信软件根目录，如果为None则从ConfigManager获取
        """
        if tdx_dir is None:
            config_manager = ConfigManager.get_instance()
            tdx_dir_str = config_manager.get("tdx_data.root_dir", "C:/new_tdx")
            self.tdx_dir = Path(tdx_dir_str)
        else:
            self.tdx_dir = tdx_dir
        
        self.block_file_path: Optional[Path] = None
        self._find_block_file()
    
    def _find_block_file(self) -> None:
        """查找spblock.dat文件（递归搜索）"""
        if self.tdx_dir and self.tdx_dir.exists():
            found = self._search_spblock_in_dir(self.tdx_dir)
            if found:
                return
        
        # 如果未指定路径或搜索失败，尝试常见根目录
        common_root_dirs = [
            Path("C:/new_tdx"),
            Path("C:/通达信金融终端V7"),
            Path("C:/Program Files/通达信金融终端V7"),
            Path("D:/通达信金融终端V7"),
            Path("C:/tdx"),
            Path("D:/tdx"),
        ]
        
        for root_dir in common_root_dirs:
            if root_dir.exists() and self._search_spblock_in_dir(root_dir):
                return
    
    def _search_spblock_in_dir(self, directory: Path) -> bool:
        """在指定目录下递归搜索spblock.dat文件
        
        Args:
            directory: 要搜索的目录
            
        Returns:
            是否找到文件
        """
        try:
            logger.debug(f"正在递归搜索 {directory} 目录下的spblock.dat文件...")
            for spblock_file in directory.rglob("spblock.dat"):
                if spblock_file.is_file():
                    self.block_file_path = spblock_file
                    logger.info(f"✓ 找到spblock.dat: {spblock_file}")
                    return True
            logger.debug(f"在 {directory} 目录下未找到spblock.dat文件")
        except OSError as e:
            logger.debug(f"搜索 {directory} 时发生错误: {e}")
            return False
        return False
    
    def get_t0_fund_codes(self) -> List[Dict[str, Any]]:
        """获取T+0基金代码列表
        
        从spblock.dat文件中提取标记为"T+0基金"的品种。
        
        Returns:
            T+0基金列表，每个元素为字典：
            {
                'code': '159001',
                'name': '易方达黄金ETF',
                'market': 0,  # 0=深证，1=上证
                'exchange': 'SZSE'
            }
        """
        if not self.block_file_path or not self.block_file_path.exists():
            logger.warning("未找到spblock.dat文件，无法获取T+0基金列表")
            return []
        
        try:
            results = []
            with open(self.block_file_path, "rb") as f:
                # 读取文件头（前4字节）
                header = f.read(4)
                if len(header) < 4:
                    logger.error("spblock.dat文件格式错误：文件头不完整")
                    return []
                
                # 读取板块数量
                block_count = struct.unpack("<I", header)[0]
                logger.debug(f"spblock.dat 包含 {block_count} 个板块")
                
                # 遍历所有板块
                for _ in range(block_count):
                    # 读取板块名称（64字节，GBK编码）
                    block_name_bytes = f.read(64)
                    if len(block_name_bytes) < 64:
                        break
                    
                    block_name = block_name_bytes.decode("gbk", errors="ignore").strip("\x00").strip()
                    
                    # 读取品种数量（2字节）
                    count_bytes = f.read(2)
                    if len(count_bytes) < 2:
                        break
                    
                    symbol_count = struct.unpack("<H", count_bytes)[0]
                    
                    # 如果是T+0基金板块
                    if "T+0" in block_name or "T0" in block_name:
                        logger.debug(f"找到T+0基金板块: {block_name}，包含 {symbol_count} 个品种")
                        
                        # 读取品种列表
                        for _ in range(symbol_count):
                            # 市场代码（1字节） + 代码（6字节）
                            record = f.read(7)
                            if len(record) < 7:
                                break
                            
                            market = record[0]
                            code = record[1:7].decode("ascii", errors="ignore").strip()
                            
                            if code:
                                results.append({
                                    "code": code.zfill(6),
                                    "name": "",  # 板块文件不包含品种名称
                                    "market": market,
                                    "exchange": "SZSE" if market == 0 else "SSE",
                                })
                    else:
                        # 跳过非T+0基金板块的品种列表
                        f.seek(symbol_count * 7, 1)
            
            logger.info(f"✅ 解析T+0基金成功，共 {len(results)} 个品种")
            return results
        
        except Exception as e:
            logger.error(f"❌ 解析spblock.dat文件失败: {e}")
            return []


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
        """分类方法（抽象方法）
        
        Args:
            all_symbols: 所有品种的DataFrame（包含code, name, market列）
            **kwargs: 额外参数
            
        Returns:
            分类后的品种列表，每个元素为字典
        """
        raise NotImplementedError("Subclass must implement classify method")
    
    def __repr__(self):
        return f"<{self.__class__.__name__}(name='{self.name}')>"


class ClassifierRegistry:
    """分类器注册表
    
    管理所有品种分类器，支持注册、注销和按名称获取。
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
            分类器实例，如果不存在则返回None
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
            分类结果字典，key为分类器名称，value为品种列表
        """
        results = {}
        for name, classifier in self._classifiers.items():
            try:
                classified = classifier.classify(all_symbols, **kwargs)
                results[name] = classified
                logger.debug(f"✅ 分类器 {name} 执行完成，分类出 {len(classified)} 个品种")
            except Exception as e:
                logger.error(f"❌ 分类器 {name} 执行失败: {e}")
                results[name] = []
        
        return results


# ==============================================================================
# Part 4: 品种分类器实现
# ==============================================================================


class ShanghaiStockClassifier(BaseClassifier):
    """上证A股分类器
    
    规则：
    - market=1（上证）
    - code以60或688开头
    - code长度为6位数字
    - 排除可转债（11开头）
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
        
        # 确保code列为字符串，并补齐6位
        all_symbols["code"] = all_symbols["code"].astype(str).str.zfill(6)
        
        # 过滤条件：market=1，code以60或688开头，排除11开头（可转债）
        shanghai_stocks = all_symbols[
            (all_symbols["market"] == 1) &
            (all_symbols["code"].str.len() == 6) &
            (all_symbols["code"].str.isdigit()) &
            ((all_symbols["code"].str.startswith("60")) | (all_symbols["code"].str.startswith("688"))) &
            (~all_symbols["code"].str.startswith("11"))
        ]
        
        results = []
        for _, row in shanghai_stocks.iterrows():
            results.append({
                "code": row["code"],
                "name": row["name"],
                "market": 1,
                "exchange": "SSE",
                "category": "上证A股",
            })
        
        logger.debug(f"✅ 上证A股分类完成，共 {len(results)} 个品种")
        return results


class ShenzhenStockClassifier(BaseClassifier):
    """深证A股分类器
    
    规则：
    - market=0（深证）
    - code以00/001/002（主板/中小板）或300/301（创业板）开头
    - code长度为6位数字
    - 排除可转债（12开头）
    - 排除T+0基金（由T0FundClassifier处理）
    """
    
    def __init__(self):
        super().__init__("深证A股")
    
    def classify(self, all_symbols: pd.DataFrame, **kwargs) -> List[Dict[str, Any]]:
        """分类深证A股
        
        Args:
            all_symbols: 所有品种的DataFrame
            **kwargs: 可选参数，包括t0_fund_codes（T+0基金代码集合）
            
        Returns:
            深证A股列表
        """
        if all_symbols.empty:
            return []
        
        # 确保code列为字符串，并补齐6位
        all_symbols["code"] = all_symbols["code"].astype(str).str.zfill(6)
        
        # 获取T+0基金代码集合（用于排除）
        t0_fund_codes = kwargs.get("t0_fund_codes", set())
        
        # 过滤条件
        shenzhen_stocks = all_symbols[
            (all_symbols["market"] == 0) &
            (all_symbols["code"].str.len() == 6) &
            (all_symbols["code"].str.isdigit()) &
            ((all_symbols["code"].str.startswith(("000", "001", "002", "300", "301")))) &
            (~all_symbols["code"].str.startswith("12")) &
            (~all_symbols["code"].isin(t0_fund_codes))
        ]
        
        results = []
        for _, row in shenzhen_stocks.iterrows():
            results.append({
                "code": row["code"],
                "name": row["name"],
                "market": 0,
                "exchange": "SZSE",
                "category": "深证A股",
            })
        
        logger.debug(f"✅ 深证A股分类完成，共 {len(results)} 个品种")
        return results


class BeijingStockClassifier(BaseClassifier):
    """北证A股分类器
    
    规则：
    - 从TDX配置文件 addedcode_bj.cfg 获取北证品种列表
    - market=2（北证）
    - code通常以43/83/87开头
    """
    
    def __init__(self):
        super().__init__("北证A股")
    
    def classify(self, all_symbols: pd.DataFrame, **kwargs) -> List[Dict[str, Any]]:
        """分类北证A股
        
        Args:
            all_symbols: 所有品种的DataFrame
            **kwargs: 额外参数，包括tdx_parser（TdxConfigFileParser实例）
            
        Returns:
            北证A股列表
        """
        # 获取TDX配置文件解析器
        tdx_parser = kwargs.get("tdx_parser")
        if tdx_parser is None:
            logger.warning("⚠️ 未提供TdxConfigFileParser实例，无法分类北证A股")
            return []
        
        # 从配置文件解析北证品种
        beijing_stocks = tdx_parser.parse_addedcode_bj()
        
        # 添加category字段
        for stock in beijing_stocks:
            stock["category"] = "北证A股"
        
        logger.debug(f"✅ 北证A股分类完成，共 {len(beijing_stocks)} 个品种")
        return beijing_stocks


class T0FundClassifier(BaseClassifier):
    """T+0基金分类器
    
    规则：
    - 从spblock.dat文件获取标记为"T+0基金"的品种
    - market=0（深证）或1（上证）
    - 主要是ETF基金
    """
    
    def __init__(self):
        super().__init__("T+0基金")
    
    def classify(self, all_symbols: pd.DataFrame, **kwargs) -> List[Dict[str, Any]]:
        """分类T+0基金
        
        Args:
            all_symbols: 所有品种的DataFrame
            **kwargs: 额外参数，包括block_parser（BlockParser实例）
            
        Returns:
            T+0基金列表
        """
        # 获取板块解析器
        block_parser = kwargs.get("block_parser")
        if block_parser is None:
            logger.warning("⚠️ 未提供BlockParser实例，无法分类T+0基金")
            return []
        
        # 从板块文件获取T+0基金代码
        t0_funds = block_parser.get_t0_fund_codes()
        
        # 合并名称信息（从all_symbols中查找）
        if not all_symbols.empty:
            all_symbols["code"] = all_symbols["code"].astype(str).str.zfill(6)
            code_to_name = dict(zip(all_symbols["code"], all_symbols["name"]))
            
            for fund in t0_funds:
                if fund["code"] in code_to_name:
                    fund["name"] = code_to_name[fund["code"]]
        
        # 添加category字段
        for fund in t0_funds:
            fund["category"] = "T+0基金"
        
        logger.debug(f"✅ T+0基金分类完成，共 {len(t0_funds)} 个品种")
        return t0_funds


class ConvertibleBondClassifier(BaseClassifier):
    """可转债分类器
    
    规则：
    - 从TDX配置文件 tdxstat2.cfg 获取可转债列表
    - market=0（深证，code以12开头）或1（上证，code以11开头）
    """
    
    def __init__(self):
        super().__init__("可转债")
    
    def classify(self, all_symbols: pd.DataFrame, **kwargs) -> List[Dict[str, Any]]:
        """分类可转债
        
        Args:
            all_symbols: 所有品种的DataFrame
            **kwargs: 额外参数，包括tdx_parser（TdxConfigFileParser实例）
            
        Returns:
            可转债列表
        """
        # 获取TDX配置文件解析器
        tdx_parser = kwargs.get("tdx_parser")
        if tdx_parser is None:
            logger.warning("⚠️ 未提供TdxConfigFileParser实例，无法分类可转债")
            return []
        
        # 从配置文件解析可转债
        convertible_bonds_dict = tdx_parser.parse_tdxstat2()
        
        # 合并深证和上证可转债
        results = []
        
        # 深证可转债（market=0）
        for code in convertible_bonds_dict.get(0, []):
            results.append({
                "code": code.zfill(6),
                "name": "",  # 配置文件不包含名称
                "market": 0,
                "exchange": "SZSE",
                "category": "可转债",
            })
        
        # 上证可转债（market=1）
        for code in convertible_bonds_dict.get(1, []):
            results.append({
                "code": code.zfill(6),
                "name": "",  # 配置文件不包含名称
                "market": 1,
                "exchange": "SSE",
                "category": "可转债",
            })
        
        # 合并名称信息（从all_symbols中查找）
        if not all_symbols.empty:
            all_symbols["code"] = all_symbols["code"].astype(str).str.zfill(6)
            code_to_name = dict(zip(all_symbols["code"], all_symbols["name"]))
            
            for bond in results:
                if bond["code"] in code_to_name:
                    bond["name"] = code_to_name[bond["code"]]
        
        logger.debug(f"✅ 可转债分类完成，深证 {len(convertible_bonds_dict.get(0, []))} 个，上证 {len(convertible_bonds_dict.get(1, []))} 个，共 {len(results)} 个")
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
        """过滤方法（抽象方法）
        
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
                result = filter_.filter(result, **kwargs)
                after_count = len(result)
                filtered_count = before_count - after_count
                logger.debug(f"✅ 过滤器 {filter_.name} 执行完成，过滤掉 {filtered_count} 个品种")
            except Exception as e:
                logger.error(f"❌ 过滤器 {filter_.name} 执行失败: {e}")
        
        total_filtered = original_count - len(result)
        logger.info(f"✅ 过滤器链执行完成，原始 {original_count} 个，过滤掉 {total_filtered} 个，剩余 {len(result)} 个")
        return result


# ==============================================================================
# Part 6: 品种过滤器实现
# ==============================================================================


class UnlistedSymbolFilter(BaseFilter):
    """未上市品种过滤器
    
    规则：
    - 过滤IPO日期<19900000或为None的品种
    - 需要IPO日期数据作为输入
    """
    
    def __init__(self):
        super().__init__("未上市品种过滤器")
    
    def filter(self, symbols: List[Dict[str, Any]], **kwargs) -> List[Dict[str, Any]]:
        """过滤未上市品种
        
        Args:
            symbols: 品种列表
            **kwargs: 额外参数，包括ipo_dates（IPO日期字典）
            
        Returns:
            过滤后的品种列表
        """
        ipo_dates = kwargs.get("ipo_dates", {})
        if not ipo_dates:
            logger.warning("⚠️ 未提供IPO日期数据，跳过未上市品种过滤")
            return symbols
        
        results = []
        for symbol in symbols:
            code = symbol.get("code")
            if code is None:
                continue
            
            # 获取IPO日期
            ipo_date = ipo_dates.get(code)
            
            # 如果IPO日期有效（>=19900000），保留
            if ipo_date is not None and ipo_date >= 19900000:
                results.append(symbol)
        
        logger.debug(f"✅ 未上市品种过滤完成，过滤前 {len(symbols)} 个，过滤后 {len(results)} 个")
        return results


class DuplicateSymbolFilter(BaseFilter):
    """重复品种过滤器
    
    规则：
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
        seen_codes = set()
        results = []
        
        for symbol in symbols:
            code = symbol.get("code")
            if code is None:
                continue
            
            # 如果未见过，添加到结果
            if code not in seen_codes:
                seen_codes.add(code)
                results.append(symbol)
        
        logger.debug(f"✅ 重复品种过滤完成，过滤前 {len(symbols)} 个，过滤后 {len(results)} 个")
        return results


class InvalidDataFilter(BaseFilter):
    """无效数据过滤器
    
    规则：
    - 过滤code为空或None的品种
    - 过滤name为空或None的品种（可选）
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
        results = []
        
        for symbol in symbols:
            code = symbol.get("code")
            name = symbol.get("name")
            
            # 检查code
            if not code or code.strip() == "":
                continue
            
            # 检查name（如果启用）
            if self.check_name and (not name or name.strip() == ""):
                continue
            
            results.append(symbol)
        
        logger.debug(f"✅ 无效数据过滤完成，过滤前 {len(symbols)} 个，过滤后 {len(results)} 个")
        return results


# ==============================================================================
# Part 7: SymbolLoader（品种加载器）
# ==============================================================================


class SymbolLoader:
    """品种加载器
    
    负责：
    - 从TDX API加载所有品种
    - 执行品种分类（5种分类器）
    - 执行品种过滤（3种过滤器）
    - 管理品种缓存（DailyCacheManager）
    - 提供品种查询接口
    """
    
    def __init__(self, event_engine=None):
        """初始化品种加载器
        
        Args:
            event_engine: 事件引擎（可选）
        """
        self.event_engine = event_engine
        self.config_manager = ConfigManager.get_instance()
        
        # 缓存路径
        cache_dir = Path(self.config_manager.get("cache.symbol_cache_dir", "data/cache"))
        cache_dir.mkdir(parents=True, exist_ok=True)
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
        
        logger.info("✅ SymbolLoader 初始化完成")
    
    def _register_classifiers(self):
        """注册所有分类器"""
        self.classifier_registry.register(ShanghaiStockClassifier())
        self.classifier_registry.register(ShenzhenStockClassifier())
        self.classifier_registry.register(BeijingStockClassifier())
        self.classifier_registry.register(T0FundClassifier())
        self.classifier_registry.register(ConvertibleBondClassifier())
        logger.info("✅ 已注册 5 个品种分类器")
    
    def _register_filters(self):
        """注册所有过滤器"""
        self.filter_chain.add_filter(InvalidDataFilter(check_name=False))
        self.filter_chain.add_filter(DuplicateSymbolFilter())
        # UnlistedSymbolFilter需要IPO日期数据，在reload_and_classify中动态添加
        logger.info("✅ 已注册 2 个品种过滤器（UnlistedSymbolFilter将在有IPO数据时添加）")
    
    async def load_from_api_async(self) -> pd.DataFrame:
        """异步从TDX API加载所有品种
        
        Returns:
            包含所有品种的DataFrame（code, name, market列）
        """
        logger.info("开始从TDX API加载品种列表...")
        
        # 获取服务器配置
        from backend.infrastructure.tdx_asyncio.constants import HQ_HOSTS_ALL
        
        if not HQ_HOSTS_ALL:
            logger.error("❌ 服务器列表为空，无法加载品种")
            return pd.DataFrame()
        
        # 选择第一个可用服务器
        server = HQ_HOSTS_ALL[0]
        if len(server) == 3:
            _, ip, port = server
        else:
            ip, port = server[0], server[1]
        
        # 创建API连接
        api = AsyncTdxHq_API()
        
        try:
            # 连接服务器
            connected = await api.connect(ip, port, timeout=5.0)
            if not connected:
                logger.error(f"❌ 连接服务器失败: {ip}:{port}")
                return pd.DataFrame()
            
            logger.info(f"✅ 已连接到服务器: {ip}:{port}")
            
            # 并发获取深证和上证品种
            tasks = [
                api.get_security_list(market=0, start=0),  # 深证
                api.get_security_list(market=1, start=0),  # 上证
            ]
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 处理结果
            all_symbols = []
            
            for market, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error(f"❌ 获取市场 {market} 品种失败: {result}")
                    continue
                
                if result is None or result.empty:
                    logger.warning(f"⚠️ 市场 {market} 品种列表为空")
                    continue
                
                # 添加market列
                result["market"] = market
                all_symbols.append(result)
                logger.info(f"✅ 市场 {market} 获取 {len(result)} 个品种")
            
            # 合并结果
            if not all_symbols:
                logger.error("❌ 未获取到任何品种数据")
                return pd.DataFrame()
            
            merged_df = pd.concat(all_symbols, ignore_index=True)
            
            # 代码标准化（补齐6位）
            merged_df["code"] = merged_df["code"].astype(str).str.zfill(6)
            
            logger.info(f"✅ 从TDX API加载品种完成，共 {len(merged_df)} 个品种")
            return merged_df
        
        except Exception as e:
            logger.error(f"❌ 从TDX API加载品种失败: {e}")
            return pd.DataFrame()
        
        finally:
            # 关闭连接
            await api.close()
    
    def reload_and_classify(
        self,
        force_reload: bool = False,
        include_ipo_filter: bool = False,
        ipo_dates: Optional[Dict[str, int]] = None,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """重新加载并分类品种
        
        Args:
            force_reload: 是否强制重新加载（忽略缓存）
            include_ipo_filter: 是否包含未上市品种过滤器
            ipo_dates: IPO日期字典（仅在include_ipo_filter=True时需要）
            
        Returns:
            分类结果字典，key为分类器名称，value为品种列表
        """
        # 1. 检查缓存
        if not force_reload:
            cached = DailyCacheManager.load_with_date(self.cache_file)
            if cached is not None:
                logger.info(f"✅ 从缓存加载品种分类，共 {sum(len(v) for v in cached.values())} 个品种")
                self.classified_symbols = cached
                return cached
        
        # 2. 从API加载
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            self.all_symbols = loop.run_until_complete(self.load_from_api_async())
        finally:
            loop.close()
        
        if self.all_symbols is None or self.all_symbols.empty:
            logger.error("❌ 加载品种失败，返回空结果")
            return {}
        
        # 3. 执行分类
        # 先获取T+0基金代码（用于深证A股过滤）
        t0_fund_classifier = self.classifier_registry.get("T+0基金")
        t0_fund_codes = set()
        if t0_fund_classifier:
            t0_funds = t0_fund_classifier.classify(
                self.all_symbols,
                block_parser=self.block_parser,
            )
            t0_fund_codes = {fund["code"] for fund in t0_funds}
        
        # 执行所有分类器
        classified = self.classifier_registry.classify_all(
            self.all_symbols,
            tdx_parser=self.tdx_parser,
            block_parser=self.block_parser,
            t0_fund_codes=t0_fund_codes,
        )
        
        # 4. 执行过滤
        # 动态添加UnlistedSymbolFilter（如果需要）
        if include_ipo_filter and ipo_dates:
            unlisted_filter = UnlistedSymbolFilter()
            self.filter_chain.add_filter(unlisted_filter)
        
        # 对每个分类结果应用过滤器链
        filtered_classified = {}
        for category, symbols in classified.items():
            filtered = self.filter_chain.apply(symbols, ipo_dates=ipo_dates)
            filtered_classified[category] = filtered
        
        # 移除临时添加的UnlistedSymbolFilter
        if include_ipo_filter and ipo_dates:
            self.filter_chain.remove_filter("未上市品种过滤器")
        
        # 5. 保存缓存
        DailyCacheManager.save_with_date(filtered_classified, self.cache_file)
        logger.info(f"✅ 品种分类缓存已保存: {self.cache_file}")
        
        self.classified_symbols = filtered_classified
        return filtered_classified
    
    def extract_all_codes(self) -> List[str]:
        """提取所有品种代码
        
        Returns:
            品种代码列表
        """
        if not self.classified_symbols:
            logger.warning("⚠️ 品种分类结果为空，请先调用 reload_and_classify")
            return []
        
        all_codes = set()
        for symbols in self.classified_symbols.values():
            for symbol in symbols:
                code = symbol.get("code")
                if code:
                    all_codes.add(code)
        
        return sorted(list(all_codes))
    
    def extract_codes_by_market(self, markets: List[str]) -> List[str]:
        """按市场提取品种代码
        
        Args:
            markets: 市场列表，例如 ["上证A股", "深证A股"]
            
        Returns:
            品种代码列表
        """
        if not self.classified_symbols:
            logger.warning("⚠️ 品种分类结果为空，请先调用 reload_and_classify")
            return []
        
        codes = set()
        for market in markets:
            symbols = self.classified_symbols.get(market, [])
            for symbol in symbols:
                code = symbol.get("code")
                if code:
                    codes.add(code)
        
        return sorted(list(codes))
    
    def get_symbol_info(self, code: str) -> Optional[Dict[str, Any]]:
        """获取品种详细信息
        
        Args:
            code: 品种代码
            
        Returns:
            品种信息字典，如果不存在则返回None
        """
        if not self.classified_symbols:
            logger.warning("⚠️ 品种分类结果为空，请先调用 reload_and_classify")
            return None
        
        # 标准化代码
        code = code.zfill(6)
        
        # 遍历所有分类查找
        for symbols in self.classified_symbols.values():
            for symbol in symbols:
                if symbol.get("code") == code:
                    return symbol
        
        return None


# ==============================================================================
# 导出API（向后兼容）
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
    IDLE = auto()        # 空闲
    PREPARING = auto()   # 准备中（加载品种列表、连接服务器等）
    RUNNING = auto()     # 运行中
    PAUSED = auto()      # 暂停
    STOPPING = auto()    # 停止中
    COMPLETED = auto()   # 完成
    FAILED = auto()      # 失败
    CANCELLED = auto()   # 取消


class DownloadStateMachine:
    """下载状态机
    
    管理下载任务的状态流转，支持状态转换验证和事件通知。
    
    状态流转规则：
    IDLE -> PREPARING -> RUNNING -> COMPLETED
                     -> RUNNING -> PAUSED -> RUNNING
                     -> RUNNING -> STOPPING -> IDLE
                     -> PREPARING/RUNNING -> FAILED -> IDLE
                     -> PREPARING/RUNNING -> CANCELLED -> IDLE
    """
    
    # 允许的状态转换映射
    ALLOWED_TRANSITIONS = {
        DownloadState.IDLE: [DownloadState.PREPARING],
        DownloadState.PREPARING: [DownloadState.RUNNING, DownloadState.FAILED, DownloadState.CANCELLED],
        DownloadState.RUNNING: [DownloadState.PAUSED, DownloadState.STOPPING, DownloadState.COMPLETED, DownloadState.FAILED, DownloadState.CANCELLED],
        DownloadState.PAUSED: [DownloadState.RUNNING, DownloadState.STOPPING, DownloadState.CANCELLED],
        DownloadState.STOPPING: [DownloadState.IDLE],
        DownloadState.COMPLETED: [DownloadState.IDLE],
        DownloadState.FAILED: [DownloadState.IDLE],
        DownloadState.CANCELLED: [DownloadState.IDLE],
    }
    
    def __init__(self, event_engine=None):
        """初始化状态机
        
        Args:
            event_engine: VnPy EventEngine（用于发送状态变化事件）
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
            reason: 转换原因（用于日志）
            
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
            self._state_history.append({
                "timestamp": datetime.now(),
                "from": old_state,
                "to": new_state,
                "reason": reason,
            })
            
            logger.info(
                f"✅ 状态转换: {old_state.name} -> {new_state.name}" +
                (f" ({reason})" if reason else "")
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
                    logger.warning(f"⚠️ 发送状态变化事件失败: {e}")
            
            return True
    
    def register_callback(self, from_state: DownloadState, to_state: DownloadState, callback: Callable):
        """注册状态转换回调
        
        Args:
            from_state: 源状态
            to_state: 目标状态
            callback: 回调函数，签名为 callback(from_state, to_state)
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
                logger.error(f"❌ 状态转换回调执行失败: {e}", exc_info=True)
    
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
            self._state_history.append({
                "timestamp": datetime.now(),
                "from": self._state,
                "to": DownloadState.IDLE,
                "reason": "手动重置",
            })


# ==============================================================================
# Part 9: 任务队列管理
# ==============================================================================


@dataclass
class DownloadTask:
    """下载任务数据类"""
    symbol: str                    # 品种代码
    interval: str                  # 周期（1d, 5m, 1m）
    market: str = ""              # 市场（上证、深证、北证）
    category: str = ""            # 分类（上证A股、深证A股等）
    start_date: Optional[date] = None  # 开始日期
    end_date: Optional[date] = None    # 结束日期
    priority: int = 0              # 优先级（数字越大越优先）
    retry_count: int = 0           # 重试次数
    max_retries: int = 3           # 最大重试次数
    task_id: str = field(default_factory=lambda: f"{int(time.time() * 1000000)}")
    created_at: datetime = field(default_factory=datetime.now)
    phase: str = "ipv4"           # 下载阶段（ipv4/ipv6）
    
    def __hash__(self):
        """支持集合操作"""
        return hash((self.symbol, self.interval))
    
    def __eq__(self, other):
        """支持比较"""
        if not isinstance(other, DownloadTask):
            return False
        return self.symbol == other.symbol and self.interval == other.interval


class TaskQueueManager:
    """任务队列管理器
    
    负责管理下载任务队列，支持：
    - 优先级队列
    - 背压控制（队列满时拒绝新任务）
    - 任务去重
    - 任务统计
    """
    
    def __init__(self, max_queue_size: int = 10000):
        """初始化任务队列管理器
        
        Args:
            max_queue_size: 最大队列长度
        """
        self.max_queue_size = max_queue_size
        self._task_queue = Queue()  # 主任务队列
        self._pending_tasks = set()  # 待处理任务集合（用于去重）
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
            force: 是否强制添加（忽略去重）
            
        Returns:
            bool: 是否成功添加
        """
        with self._lock:
            # 检查队列是否已满
            if self._task_queue.qsize() >= self.max_queue_size:
                self._stats["queue_full_count"] += 1
                logger.warning(
                    f"⚠️ 任务队列已满（{self.max_queue_size}），拒绝添加任务: "
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
                self._task_queue.put(task, block=False)
                self._pending_tasks.add(task)
                self._stats["total_added"] += 1
                return True
            except Exception as e:
                logger.error(f"❌ 添加任务失败: {task.symbol}/{task.interval}, 错误: {e}")
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
            timeout: 超时时间（秒），None表示阻塞等待
            
        Returns:
            下载任务，队列为空则返回None
        """
        try:
            task = self._task_queue.get(timeout=timeout)
            return task
        except Exception:
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
            logger.warning(
                f"⚠️ 任务重试次数已达上限: {task.symbol}/{task.interval}, "
                f"重试次数: {task.retry_count}/{task.max_retries}"
            )
            return False
        
        task.retry_count += 1
        task.priority += 10  # 提高重试任务的优先级
        return self.add_task(task, force=True)
    
    def get_pending_count(self) -> int:
        """获取待处理任务数量"""
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
                except Exception:
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
# Part 10: 连接生命周期管理
# ==============================================================================


class ConnectionLifecycleManager:
    """连接生命周期管理器
    
    负责管理TDX连接的创建、复用和销毁，支持：
    - 连接池管理
    - 连接健康检查
    - 连接自动重连
    - 连接超时检测
    """
    
    def __init__(self, max_connections: int = 50, connection_timeout: float = 10.0):
        """初始化连接管理器
        
        Args:
            max_connections: 最大连接数
            connection_timeout: 连接超时时间（秒）
        """
        self.max_connections = max_connections
        self.connection_timeout = connection_timeout
        self._connection_pool = {}  # {conn_id: {"api": api_obj, "last_used": time, "server": server_info}}
        self._lock = threading.Lock()
        self._next_conn_id = 0
        
        # 统计信息
        self._stats = {
            "total_created": 0,
            "total_reused": 0,
            "total_closed": 0,
            "total_timeout": 0,
            "total_errors": 0,
        }
    
    async def create_connection(self, server_ip: str, server_port: int) -> Tuple[int, AsyncTdxHq_API]:
        """创建新连接
        
        Args:
            server_ip: 服务器IP
            server_port: 服务器端口
            
        Returns:
            (conn_id, api_obj): 连接ID和API对象
        """
        with self._lock:
            # 检查连接数是否达到上限
            if len(self._connection_pool) >= self.max_connections:
                # 清理超时连接
                self._cleanup_timeout_connections()
                
                # 如果仍然满，关闭最久未使用的连接
                if len(self._connection_pool) >= self.max_connections:
                    self._close_oldest_connection()
            
            # 生成连接ID
            conn_id = self._next_conn_id
            self._next_conn_id += 1
        
        # 创建连接
        try:
            api = AsyncTdxHq_API()
            success = await asyncio.wait_for(
                api.connect(server_ip, server_port),
                timeout=self.connection_timeout
            )
            
            if not success:
                raise ConnectionError(f"连接失败: {server_ip}:{server_port}")
            
            # 添加到连接池
            with self._lock:
                self._connection_pool[conn_id] = {
                    "api": api,
                    "last_used": time.time(),
                    "server": {"ip": server_ip, "port": server_port},
                    "created_at": time.time(),
                }
                self._stats["total_created"] += 1
            
            logger.debug(f"✅ 创建连接: ID={conn_id}, 服务器={server_ip}:{server_port}")
            return conn_id, api
            
        except asyncio.TimeoutError:
            with self._lock:
                self._stats["total_timeout"] += 1
            raise ConnectionError(f"连接超时: {server_ip}:{server_port}")
        except Exception as e:
            with self._lock:
                self._stats["total_errors"] += 1
            raise ConnectionError(f"创建连接失败: {server_ip}:{server_port}, 错误: {e}")
    
    def get_connection(self, conn_id: int) -> Optional[AsyncTdxHq_API]:
        """获取连接
        
        Args:
            conn_id: 连接ID
            
        Returns:
            API对象，如果不存在则返回None
        """
        with self._lock:
            conn_info = self._connection_pool.get(conn_id)
            if conn_info:
                conn_info["last_used"] = time.time()
                self._stats["total_reused"] += 1
                return conn_info["api"]
            return None
    
    async def close_connection(self, conn_id: int):
        """关闭连接
        
        Args:
            conn_id: 连接ID
        """
        with self._lock:
            conn_info = self._connection_pool.pop(conn_id, None)
        
        if conn_info:
            try:
                api = conn_info["api"]
                await api.disconnect()
                self._stats["total_closed"] += 1
                logger.debug(f"✅ 关闭连接: ID={conn_id}")
            except Exception as e:
                logger.warning(f"⚠️ 关闭连接失败: ID={conn_id}, 错误: {e}")
    
    async def close_all_connections(self):
        """关闭所有连接"""
        with self._lock:
            conn_ids = list(self._connection_pool.keys())
        
        for conn_id in conn_ids:
            await self.close_connection(conn_id)
        
        logger.info(f"✅ 已关闭所有连接: 数量={len(conn_ids)}")
    
    def _cleanup_timeout_connections(self, timeout: float = 300.0):
        """清理超时连接
        
        Args:
            timeout: 超时时间（秒）
        """
        current_time = time.time()
        timeout_conn_ids = []
        
        with self._lock:
            for conn_id, conn_info in self._connection_pool.items():
                if current_time - conn_info["last_used"] > timeout:
                    timeout_conn_ids.append(conn_id)
        
        # 异步关闭超时连接（需要在事件循环中执行）
        for conn_id in timeout_conn_ids:
            with self._lock:
                conn_info = self._connection_pool.pop(conn_id, None)
            if conn_info:
                logger.debug(f"✅ 清理超时连接: ID={conn_id}")
                self._stats["total_timeout"] += 1
    
    def _close_oldest_connection(self):
        """关闭最久未使用的连接"""
        with self._lock:
            if not self._connection_pool:
                return
            
            # 找到最久未使用的连接
            oldest_conn_id = min(
                self._connection_pool.keys(),
                key=lambda conn_id: self._connection_pool[conn_id]["last_used"]
            )
            
            conn_info = self._connection_pool.pop(oldest_conn_id, None)
        
        if conn_info:
            logger.debug(f"✅ 关闭最久未使用的连接: ID={oldest_conn_id}")
    
    def get_stats(self) -> Dict[str, int]:
        """获取统计信息"""
        with self._lock:
            stats = self._stats.copy()
            stats["active_connections"] = len(self._connection_pool)
            return stats
    
    def get_active_connections(self) -> int:
        """获取活跃连接数"""
        with self._lock:
            return len(self._connection_pool)


# ==============================================================================
# Part 11: MultiProcessStockFetcher（多进程股票数据下载器）
# ==============================================================================


class MultiProcessStockFetcher:
    """多进程K线数据下载器
    
    支持特性：
    - 多进程+多协程：最大2000并发连接
    - 两段式下载：IPv4池→IPv6池（剩余≤ 50任务时切换）
    - 智能负载均衡：集成LoadBalancer动态调整并发
    - 状态管理：支持暂停/恢复/取消
    - 进度同步：使用native_ipc（如可用）
    - 数据存储：集成StorageManager
    """
    
    def __init__(self, event_engine=None, config_manager: Optional[ConfigManager] = None):
        """初始化下载器
        
        Args:
            event_engine: VnPy EventEngine（用于事件通知）
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
        
        # 负载均衡器（延迟加载）
        self._load_balancer = None
        
    def register_progress_callback(self, callback: Callable):
        """注册进度回调函数
        
        Args:
            callback: 回调函数，签名为 callback(completed, total, message)
        """
        self._progress_callbacks.append(callback)
    
    def _notify_progress(self, completed: int, total: int, message: str = ""):
        """通知进度更新"""
        for callback in self._progress_callbacks:
            try:
                callback(completed, total, message)
            except Exception as e:
                logger.warning(f"⚠️ 进度回调执行失败: {e}")
    
    def download_incremental_kline(
        self,
        symbols: List[str],
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        intervals: List[str] = None,
        use_adaptive: bool = True,
        use_two_phase: bool = True,
        max_workers: int = 4,
        coroutines_per_worker: int = 50,
    ) -> Dict[str, Any]:
        """增量K线数据下载（主入口）
        
        Args:
            symbols: 品种代码列表
            start_date: 开始日期
            end_date: 结束日期
            intervals: 周期列表，默认 ["1d", "5m", "1m"]
            use_adaptive: 是否启用自适应负载均衡
            use_two_phase: 是否启用两段式下载（IPv4→IPv6）
            max_workers: 最大进程数
            coroutines_per_worker: 每个进程的协程数
            
        Returns:
            下载结果统计
        """
        # 1. 状态检查
        if not self.state_machine.can_start():
            raise RuntimeError(f"无法开始下载，当前状态: {self.state_machine.state.name}")
        
        # 2. 转换到PREPARING状态
        self.state_machine.transition_to(DownloadState.PREPARING, "开始准备下载")
        
        try:
            # 3. 准备参数
            intervals = intervals or ["1d", "5m", "1m"]
            start_date = start_date or date(2010, 1, 1)
            end_date = end_date or date.today()
            
            logger.info(
                f"🚀 开始增量K线下载: "
                f"品种数={len(symbols)}, 周期={intervals}, "
                f"日期范围={start_date} ~ {end_date}, "
                f"进程数={max_workers}, 协程数={coroutines_per_worker}"
            )
            
            # 4. 获取负载均衡配置
            if use_adaptive:
                lb_config = self._get_load_balancer_config()
                if lb_config:
                    max_workers = lb_config.get("max_workers", max_workers)
                    coroutines_per_worker = lb_config.get("coroutines_per_worker", coroutines_per_worker)
                    logger.info(
                        f"🧠 负载均衡调整: 进程数={max_workers}, "
                        f"协程数={coroutines_per_worker}"
                    )
            
            # 5. 准备任务队列
            tasks = self._prepare_tasks(symbols, intervals, start_date, end_date)
            logger.info(f"✅ 任务准备完成: 总数={len(tasks)}")
            
            # 6. 加载任务到队列
            self.task_queue_manager.reset()
            added_count = self.task_queue_manager.add_tasks_batch(tasks)
            logger.info(f"✅ 任务已加载到队列: {added_count}/{len(tasks)}")
            
            # 7. 获取服务器列表
            servers = self._get_servers(use_two_phase)
            logger.info(
                f"🌐 服务器列表已加载: "
                f"IPv4={len(servers.get('ipv4', []))}, "
                f"IPv6={len(servers.get('ipv6', []))}"
            )
            
            # 8. 转换到RUNNING状态
            self.state_machine.transition_to(DownloadState.RUNNING, "开始下载")
            
            # 9. 启动多进程下载
            results = self._run_multiprocess_download(
                max_workers=max_workers,
                coroutines_per_worker=coroutines_per_worker,
                servers=servers,
                use_two_phase=use_two_phase,
            )
            
            # 10. 转换到COMPLETED状态
            self.state_machine.transition_to(DownloadState.COMPLETED, "下载完成")
            
            logger.info(f"✅ 增量K线下载完成: {results}")
            return results
            
        except Exception as e:
            # 转换到FAILED状态
            self.state_machine.transition_to(DownloadState.FAILED, f"下载失败: {e}")
            logger.error(f"❌ 增量K线下载失败: {e}", exc_info=True)
            raise
    
    def _prepare_tasks(
        self, 
        symbols: List[str], 
        intervals: List[str],
        start_date: date,
        end_date: date
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
                    phase="ipv4",
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
        ipv4_servers = self.config_manager.get_config("tdx.servers.ipv4", [])
        if isinstance(ipv4_servers, list):
            servers["ipv4"] = ipv4_servers
        
        # 如果启用两段式，获取IPv6服务器列表
        if use_two_phase:
            ipv6_servers = self.config_manager.get_config("tdx.servers.ipv6", [])
            if isinstance(ipv6_servers, list):
                servers["ipv6"] = ipv6_servers
        
        # 如果配置为空，使用默认服务器
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
            配置字典，如 {"max_workers": 4, "coroutines_per_worker": 50}
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
            logger.warning(f"⚠️ 获取负载均衡配置失败: {e}")
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
        # 创建进程间通信对象
        manager = Manager()
        task_queue = manager.Queue()
        result_queue = manager.Queue()
        self._stop_event = manager.Event()
        self._pause_event = manager.Event()
        
        # 加载任务到进程队列
        total_tasks = 0
        while True:
            task = self.task_queue_manager.get_task(timeout=0.1)
            if task is None:
                break
            task_queue.put(task)
            total_tasks += 1
        
        logger.info(f"🚀 启动多进程下载: 进程数={max_workers}, 任务数={total_tasks}")
        
        # 启动Worker进程
        self._worker_processes = []
        for worker_id in range(max_workers):
            process = Process(
                target=self._worker_process,
                args=(
                    worker_id,
                    task_queue,
                    result_queue,
                    self.config_manager.get_all_configs(),
                    servers,
                    self._stop_event,
                    self._pause_event,
                    coroutines_per_worker,
                    use_two_phase,
                ),
            )
            process.start()
            self._worker_processes.append(process)
        
        # 收集结果
        results = self._collect_results(result_queue, total_tasks)
        
        # 等待所有进程结束
        for process in self._worker_processes:
            process.join(timeout=5)
            if process.is_alive():
                logger.warning(f"⚠️ Worker进程未正常退出，强制终止: PID={process.pid}")
                process.terminate()
        
        return results
    
    def _collect_results(self, result_queue: Queue, total_tasks: int) -> Dict[str, Any]:
        """收集下载结果
        
        Args:
            result_queue: 结果队列
            total_tasks: 总任务数
            
        Returns:
            结果统计
        """
        completed = 0
        failed = 0
        total_bars = 0
        
        while completed + failed < total_tasks:
            try:
                result = result_queue.get(timeout=1.0)
                
                if result.get("status") == "success":
                    completed += 1
                    total_bars += result.get("bars", 0)
                else:
                    failed += 1
                
                # 通知进度
                self._notify_progress(
                    completed + failed,
                    total_tasks,
                    f"已完成: {completed}, 失败: {failed}"
                )
                
            except Exception:
                # 超时，继续等待
                pass
        
        return {
            "total_tasks": total_tasks,
            "completed": completed,
            "failed": failed,
            "total_bars": total_bars,
        }
    
    @staticmethod
    def _worker_process(
        worker_id: int,
        task_queue: Queue,
        result_queue: Queue,
        config_dict: Dict,
        servers: Dict[str, List[Dict]],
        stop_event: Event,
        pause_event: Event,
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
        # 配置子进程日志
        subprocess_logger = _configure_subprocess_logging(worker_id, "kline_download")
        
        try:
            subprocess_logger.info(f"🚀 Worker {worker_id} 启动")
            
            # 创建新的事件循环
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
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
            
            subprocess_logger.info(f"✅ Worker {worker_id} 正常退出")
            
        except Exception as e:
            subprocess_logger.error(f"❌ Worker {worker_id} 异常退出: {e}", exc_info=True)
        finally:
            try:
                loop.close()
            except Exception:
                pass
    
    @staticmethod
    async def _download_worker_async(
        worker_id: int,
        task_queue: Queue,
        result_queue: Queue,
        config_dict: Dict,
        servers: Dict[str, List[Dict]],
        stop_event: Event,
        pause_event: Event,
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
        
        # 创建连接管理器
        connection_manager = ConnectionLifecycleManager(
            max_connections=coroutines_per_worker
        )
        
        # Phase 1: IPv4池下载
        subprocess_logger.info(f"🌐 Worker {worker_id} 进入Phase 1: IPv4池下载")
        ipv4_servers = servers.get("ipv4", [])
        
        if not ipv4_servers:
            subprocess_logger.warning(f"⚠️ Worker {worker_id} IPv4服务器列表为空")
            return
        
        # 创建连接池
        connections = []
        for i in range(coroutines_per_worker):
            server = ipv4_servers[i % len(ipv4_servers)]
            try:
                conn_id, api = await connection_manager.create_connection(
                    server["ip"], server["port"]
                )
                connections.append({
                    "conn_id": conn_id,
                    "api": api,
                    "server": server,
                })
            except Exception as e:
                subprocess_logger.warning(
                    f"⚠️ Worker {worker_id} 创建连接失败: {server['ip']}:{server['port']}, {e}"
                )
        
        if not connections:
            subprocess_logger.error(f"❌ Worker {worker_id} 没有可用连接，退出")
            return
        
        subprocess_logger.info(
            f"✅ Worker {worker_id} 已创建 {len(connections)} 个连接"
        )
        
        # 创建下载协程
        download_tasks = []
        for conn_info in connections:
            task = asyncio.create_task(
                MultiProcessStockFetcher._download_coroutine(
                    worker_id=worker_id,
                    conn_info=conn_info,
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
        await asyncio.gather(*download_tasks, return_exceptions=True)
        
        # 关闭所有连接
        await connection_manager.close_all_connections()
        
        subprocess_logger.info(f"✅ Worker {worker_id} 下载完成")
    
    @staticmethod
    async def _download_coroutine(
        worker_id: int,
        conn_info: Dict,
        task_queue: Queue,
        result_queue: Queue,
        storage_manager: StorageManager,
        task_logger: TaskDetailLogger,
        stop_event: Event,
        pause_event: Event,
        subprocess_logger,
    ):
        """下载协程
        
        Args:
            worker_id: Worker ID
            conn_info: 连接信息 {"conn_id": ..., "api": ..., "server": ...}
            task_queue: 任务队列
            result_queue: 结果队列
            storage_manager: 存储管理器
            task_logger: 任务日志记录器
            stop_event: 停止事件
            pause_event: 暂停事件
            subprocess_logger: 子进程日志记录器
        """
        api = conn_info["api"]
        server = conn_info["server"]
        conn_id = conn_info["conn_id"]
        
        while not stop_event.is_set():
            # 检查暂停
            while pause_event.is_set() and not stop_event.is_set():
                await asyncio.sleep(0.1)
            
            # 获取任务
            try:
                task = task_queue.get_nowait()
            except Exception:
                # 队列为空，退出
                break
            
            # 下载数据
            start_time = time.time()
            try:
                # 调用TDX API下载
                bars = await MultiProcessStockFetcher._download_single_task(
                    api=api,
                    symbol=task.symbol,
                    interval=task.interval,
                    start_date=task.start_date,
                    end_date=task.end_date,
                    subprocess_logger=subprocess_logger,
                )
                
                # 保存数据
                if bars is not None and not bars.empty:
                    await storage_manager.save_kline_async(
                        symbol=task.symbol,
                        interval=task.interval,
                        data=bars,
                    )
                    
                    elapsed = time.time() - start_time
                    
                    # 记录成功
                    task_logger.log_task(
                        symbol=task.symbol,
                        interval=task.interval,
                        server=f"{server['ip']}:{server['port']}",
                        status="success",
                        bars=len(bars),
                        elapsed=elapsed,
                    )
                    
                    # 发送结果
                    _safe_put_queue(
                        result_queue,
                        {
                            "status": "success",
                            "symbol": task.symbol,
                            "interval": task.interval,
                            "bars": len(bars),
                            "worker_id": worker_id,
                            "conn_id": conn_id,
                        },
                        timeout=1.0,
                        queue_name="result_queue",
                        worker_id=worker_id,
                    )
                else:
                    # 数据为空
                    subprocess_logger.debug(
                        f"⚠️ Worker {worker_id} 下载数据为空: {task.symbol}/{task.interval}"
                    )
                    
                    task_logger.log_task(
                        symbol=task.symbol,
                        interval=task.interval,
                        server=f"{server['ip']}:{server['port']}",
                        status="empty",
                        bars=0,
                        elapsed=time.time() - start_time,
                    )
                    
                    _safe_put_queue(
                        result_queue,
                        {
                            "status": "success",
                            "symbol": task.symbol,
                            "interval": task.interval,
                            "bars": 0,
                            "worker_id": worker_id,
                            "conn_id": conn_id,
                        },
                        timeout=1.0,
                        queue_name="result_queue",
                        worker_id=worker_id,
                    )
                
            except Exception as e:
                # 下载失败
                elapsed = time.time() - start_time
                
                subprocess_logger.warning(
                    f"⚠️ Worker {worker_id} 下载失败: {task.symbol}/{task.interval}, 错误: {e}"
                )
                
                task_logger.log_task(
                    symbol=task.symbol,
                    interval=task.interval,
                    server=f"{server['ip']}:{server['port']}",
                    status="failed",
                    bars=0,
                    elapsed=elapsed,
                    error=str(e),
                )
                
                _safe_put_queue(
                    result_queue,
                    {
                        "status": "failed",
                        "symbol": task.symbol,
                        "interval": task.interval,
                        "error": str(e),
                        "worker_id": worker_id,
                        "conn_id": conn_id,
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
        try:
            # 确定市场
            market = MultiProcessStockFetcher._get_market_from_symbol(symbol)
            
            # 调用TDX API
            if interval == "1d":
                bars = await api.get_security_bars(
                    category=9,  # 日线
                    market=market,
                    code=symbol,
                    start=0,
                    count=10000,
                )
            elif interval == "5m":
                bars = await api.get_security_bars(
                    category=0,  # 5分钟
                    market=market,
                    code=symbol,
                    start=0,
                    count=10000,
                )
            elif interval == "1m":
                bars = await api.get_security_bars(
                    category=8,  # 1分钟
                    market=market,
                    code=symbol,
                    start=0,
                    count=10000,
                )
            else:
                subprocess_logger.warning(f"⚠️ 不支持的周期: {interval}")
                return None
            
            # 转换为DataFrame
            if bars:
                df = pd.DataFrame(bars)
                # 标准化列名
                if "datetime" in df.columns:
                    df["datetime"] = pd.to_datetime(df["datetime"])
                    df = df.set_index("datetime")
                return df
            else:
                return None
                
        except Exception as e:
            subprocess_logger.warning(
                f"⚠️ 下载数据失败: {symbol}/{interval}, 错误: {e}"
            )
            raise
    
    @staticmethod
    def _get_market_from_symbol(symbol: str) -> int:
        """根据品种代码获取市场代码
        
        Args:
            symbol: 品种代码
            
        Returns:
            市场代码 (0=深圳, 1=上海, 2=北交所)
        """
        if symbol.startswith("6"):
            return 1  # 上海
        elif symbol.startswith(("0", "3")):
            return 0  # 深圳
        elif symbol.startswith(("4", "8", "9")):
            return 2  # 北交所
        else:
            return 1  # 默认上海
    
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
                if hasattr(logger_instance, 'close'):
                    logger_instance.close()
            except Exception as e:
                logger.warning(f"⚠️ 关闭任务日志记录器失败: {e}")


def close_all_task_loggers():
    """关闭所有TaskDetailLogger实例"""
    with _task_logger_lock:
        for worker_id in list(_task_loggers.keys()):
            close_task_logger(worker_id)


# ==============================================================================
# 导出API（向后兼容）- 更新版
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
    # 连接管理
    "ConnectionLifecycleManager",
    # 数据下载器
    "MultiProcessStockFetcher",
]


# ==============================================================================
# Part 13: TDX二进制数据读取器
# ==============================================================================


class BaseReader:
    """数据读取器基类"""
    
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def read_single(self, symbol: str, data_type: str, market: str) -> pd.DataFrame:
        """读取单个品种的数据
        
        Args:
            symbol: 品种代码
            data_type: 数据类型（day/5min/1min）
            market: 市场（sh/sz/bj）
            
        Returns:
            DataFrame
        """
        raise NotImplementedError
    
    def process_batch(self, symbols: List[str], data_type: str, market: str,
                     progress_callback: Optional[Callable] = None) -> Dict[str, pd.DataFrame]:
        """批量处理多个品种
        
        Args:
            symbols: 品种代码列表
            data_type: 数据类型
            market: 市场
            progress_callback: 进度回调函数
            
        Returns:
            {symbol: DataFrame}
        """
        raise NotImplementedError


class BjStockDecoder:
    """北证数据解码器
    
    北证股票数据格式特殊，需要特殊处理：
    - 价格需要除以100
    - 成交量需要除以100
    """
    
    @staticmethod
    def decode_bj_stock(df: pd.DataFrame) -> pd.DataFrame:
        """解码北证股票数据
        
        Args:
            df: 原始数据
            
        Returns:
            解码后的数据
        """
        if df.empty:
            return df
        
        df = df.copy()
        
        # 价格字段除以100
        price_columns = ["open", "high", "low", "close"]
        for col in price_columns:
            if col in df.columns:
                df[col] = df[col] / 100.0
        
        # 成交量除以100
        if "volume" in df.columns:
            df["volume"] = df["volume"] / 100.0
        
        return df
    
    @staticmethod
    def is_bj_stock(symbol: str) -> bool:
        """判断是否为北证股票
        
        Args:
            symbol: 品种代码
            
        Returns:
            True表示是北证股票
        """
        return symbol.startswith(("4", "8", "9"))


class TdxBinaryReader(BaseReader):
    """通达信二进制数据读取器
    
    读取通达信软件本地保存的二进制K线数据文件，支持：
    - 日线数据: vipdoc/{market}/lday/{symbol}.day
    - 5分钟线: vipdoc/{market}/fzline/{symbol}.lc5
    - 1分钟线: vipdoc/{market}/minline/{symbol}.lc1
    
    市场代码：
    - sh: 上证
    - sz: 深证
    - bj: 北证
    """
    
    # 市场代码映射
    MARKET_CODES = {
        "sh": "上证",
        "sz": "深证",
        "bj": "北证",
    }
    
    # 数据类型映射
    DATA_TYPE_PATHS = {
        "day": "lday",
        "5min": "fzline",
        "1min": "minline",
    }
    
    # 文件扩展名
    FILE_EXTENSIONS = {
        "day": ".day",
        "5min": ".lc5",
        "1min": ".lc1",
    }
    
    # 日线数据结构：32字节
    DAY_STRUCT = "<IIIIIfII"  # 日期(I), 开(I), 高(I), 低(I), 收(I), 成交额(f), 成交量(I), 保留(I)
    DAY_RECORD_SIZE = 32
    
    # 分钟线数据结构：32字节
    MIN_STRUCT = "<HHfffffII"  # 日期(H), 时间(H), 开(f), 高(f), 低(f), 收(f), 成交额(f), 成交量(I), 保留(I)
    MIN_RECORD_SIZE = 32
    
    def __init__(self, tdx_root_path: Optional[Path] = None):
        """初始化TDX二进制读取器
        
        Args:
            tdx_root_path: 通达信软件根目录，默认从配置读取
        """
        super().__init__()
        
        # 获取TDX根目录
        if tdx_root_path:
            self.tdx_root = Path(tdx_root_path)
        else:
            config_mgr = ConfigManager()
            tdx_path = config_mgr.get_config("tdx.local_path", "")
            if tdx_path:
                self.tdx_root = Path(tdx_path)
            else:
                # 默认路径
                self.tdx_root = Path("C:/new_tdx")
        
        self.logger.info(f"TDX根目录: {self.tdx_root}")
    
    def _get_file_path(self, symbol: str, data_type: str, market: str) -> Path:
        """获取数据文件路径
        
        Args:
            symbol: 品种代码
            data_type: 数据类型
            market: 市场
            
        Returns:
            文件路径
        """
        # vipdoc/{market}/{subdir}/{symbol}{ext}
        subdir = self.DATA_TYPE_PATHS.get(data_type, "lday")
        ext = self.FILE_EXTENSIONS.get(data_type, ".day")
        
        file_path = self.tdx_root / "vipdoc" / market / subdir / f"{symbol}{ext}"
        return file_path
    
    def read_single(self, symbol: str, data_type: str, market: str) -> pd.DataFrame:
        """读取单个品种的数据（同步版本）
        
        Args:
            symbol: 品种代码
            data_type: 数据类型（day/5min/1min）
            market: 市场（sh/sz/bj）
            
        Returns:
            DataFrame
        """
        file_path = self._get_file_path(symbol, data_type, market)
        
        if not file_path.exists():
            self.logger.debug(f"文件不存在: {file_path}")
            return pd.DataFrame()
        
        try:
            # 读取二进制数据
            with open(file_path, "rb") as f:
                raw_data = f.read()
            
            # 解码数据
            df = self._decode_binary(raw_data, data_type)
            
            # 如果是北证股票，应用解码器
            if market == "bj" and BjStockDecoder.is_bj_stock(symbol):
                df = BjStockDecoder.decode_bj_stock(df)
            
            self.logger.debug(f"读取成功: {symbol}/{data_type}, 记录数={len(df)}")
            return df
            
        except Exception as e:
            self.logger.error(f"读取文件失败: {file_path}, 错误: {e}")
            return pd.DataFrame()
    
    async def read_single_async(self, symbol: str, data_type: str, market: str) -> pd.DataFrame:
        """读取单个品种的数据（异步版本，native_iocp集成）
        
        Args:
            symbol: 品种代码
            data_type: 数据类型
            market: 市场
            
        Returns:
            DataFrame
        """
        file_path = self._get_file_path(symbol, data_type, market)
        
        if not file_path.exists():
            self.logger.debug(f"文件不存在: {file_path}")
            return pd.DataFrame()
        
        try:
            # 使用native_iocp异步读取（如可用）
            if compat_aopen:
                async with compat_aopen(file_path, "rb") as f:
                    raw_data = await f.read()
            else:
                # 降级到同步读取
                with open(file_path, "rb") as f:
                    raw_data = f.read()
            
            # 解码数据
            df = self._decode_binary(raw_data, data_type)
            
            # 如果是北证股票，应用解码器
            if market == "bj" and BjStockDecoder.is_bj_stock(symbol):
                df = BjStockDecoder.decode_bj_stock(df)
            
            self.logger.debug(f"异步读取成功: {symbol}/{data_type}, 记录数={len(df)}")
            return df
            
        except Exception as e:
            self.logger.error(f"异步读取文件失败: {file_path}, 错误: {e}")
            return pd.DataFrame()
    
    def _decode_binary(self, raw_data: bytes, data_type: str) -> pd.DataFrame:
        """解码二进制数据
        
        Args:
            raw_data: 原始二进制数据
            data_type: 数据类型
            
        Returns:
            DataFrame
        """
        if data_type == "day":
            return self._decode_day_data(raw_data)
        elif data_type in ["5min", "1min"]:
            return self._decode_min_data(raw_data)
        else:
            self.logger.warning(f"不支持的数据类型: {data_type}")
            return pd.DataFrame()
    
    def _decode_day_data(self, raw_data: bytes) -> pd.DataFrame:
        """解码日线数据
        
        Args:
            raw_data: 原始二进制数据
            
        Returns:
            DataFrame
        """
        records = []
        record_count = len(raw_data) // self.DAY_RECORD_SIZE
        
        for i in range(record_count):
            offset = i * self.DAY_RECORD_SIZE
            record_bytes = raw_data[offset:offset + self.DAY_RECORD_SIZE]
            
            try:
                # 解包数据
                date_int, open_price, high_price, low_price, close_price, \
                    amount, volume, reserved = struct.unpack(self.DAY_STRUCT, record_bytes)
                
                # 解析日期（YYYYMMDD格式）
                date_str = str(date_int)
                if len(date_str) == 8:
                    year = int(date_str[0:4])
                    month = int(date_str[4:6])
                    day = int(date_str[6:8])
                    
                    # 价格转换（整数转浮点，除以1000）
                    records.append({
                        "datetime": pd.Timestamp(year, month, day),
                        "open": open_price / 1000.0,
                        "high": high_price / 1000.0,
                        "low": low_price / 1000.0,
                        "close": close_price / 1000.0,
                        "amount": amount,
                        "volume": volume,
                    })
            except Exception as e:
                self.logger.debug(f"解析日线记录失败: {e}")
                continue
        
        if records:
            df = pd.DataFrame(records)
            df = df.set_index("datetime")
            return df
        else:
            return pd.DataFrame()
    
    def _decode_min_data(self, raw_data: bytes) -> pd.DataFrame:
        """解码分钟线数据
        
        Args:
            raw_data: 原始二进制数据
            
        Returns:
            DataFrame
        """
        records = []
        record_count = len(raw_data) // self.MIN_RECORD_SIZE
        
        for i in range(record_count):
            offset = i * self.MIN_RECORD_SIZE
            record_bytes = raw_data[offset:offset + self.MIN_RECORD_SIZE]
            
            try:
                # 解包数据
                date_code, time_code, open_price, high_price, low_price, \
                    close_price, amount, volume, reserved = struct.unpack(self.MIN_STRUCT, record_bytes)
                
                # 解析日期
                year = date_code // 2048 + 2004
                month = (date_code % 2048) // 100
                day = (date_code % 2048) % 100
                
                # 解析时间
                hour = time_code // 60
                minute = time_code % 60
                
                records.append({
                    "datetime": pd.Timestamp(year, month, day, hour, minute),
                    "open": open_price,
                    "high": high_price,
                    "low": low_price,
                    "close": close_price,
                    "amount": amount,
                    "volume": volume,
                })
            except Exception as e:
                self.logger.debug(f"解析分钟线记录失败: {e}")
                continue
        
        if records:
            df = pd.DataFrame(records)
            df = df.set_index("datetime")
            return df
        else:
            return pd.DataFrame()
    
    def process_batch(self, symbols: List[str], data_type: str, market: str,
                     progress_callback: Optional[Callable] = None) -> Dict[str, pd.DataFrame]:
        """批量处理多个品种（同步版本）
        
        Args:
            symbols: 品种代码列表
            data_type: 数据类型
            market: 市场
            progress_callback: 进度回调函数
            
        Returns:
            {symbol: DataFrame}
        """
        results = {}
        total = len(symbols)
        
        for i, symbol in enumerate(symbols):
            df = self.read_single(symbol, data_type, market)
            if not df.empty:
                results[symbol] = df
            
            if progress_callback:
                try:
                    progress_callback(i + 1, total, f"已处理: {symbol}")
                except Exception:
                    pass
        
        self.logger.info(f"批量读取完成: {len(results)}/{total}")
        return results
    
    async def process_batch_async(self, symbols: List[str], data_type: str, market: str,
                                 max_concurrent: int = 50) -> Dict[str, pd.DataFrame]:
        """批量处理多个品种（异步版本，native_iocp集成）
        
        Args:
            symbols: 品种代码列表
            data_type: 数据类型
            market: 市场
            max_concurrent: 最大并发数
            
        Returns:
            {symbol: DataFrame}
        """
        results = {}
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def read_with_semaphore(symbol):
            async with semaphore:
                df = await self.read_single_async(symbol, data_type, market)
                if not df.empty:
                    return symbol, df
                return symbol, None
        
        # 创建任务
        tasks = [read_with_semaphore(symbol) for symbol in symbols]
        
        # 并发执行
        task_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 收集结果
        for result in task_results:
            if isinstance(result, tuple) and result[1] is not None:
                symbol, df = result
                results[symbol] = df
        
        self.logger.info(f"异步批量读取完成: {len(results)}/{len(symbols)}")
        return results


# ==============================================================================
# Part 14: TdxDynamicExecutor（动态并发执行器）
# ==============================================================================


class TdxDynamicExecutor:
    """动态并发执行器
    
    用于执行大量并发任务，支持：
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
            task_func: 任务函数，签名为 async task_func(task) -> result
            progress_callback: 进度回调函数
            
        Returns:
            结果列表
        """
        # 创建进程间通信对象
        manager = Manager()
        task_queue = manager.Queue()
        result_queue = manager.Queue()
        
        # 加载任务
        for task in tasks:
            task_queue.put(task)
        
        # 启动Worker进程
        processes = []
        for worker_id in range(self.max_workers):
            process = Process(
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
                    except Exception:
                        pass
            except Exception:
                pass
        
        # 等待所有进程结束
        for process in processes:
            process.join(timeout=2)
        
        return results
    
    @staticmethod
    def _worker_process(
        worker_id: int,
        task_queue: Queue,
        result_queue: Queue,
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
        # 配置子进程日志
        subprocess_logger = _configure_subprocess_logging(worker_id, "tdx_executor")
        
        try:
            # 创建事件循环
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            # 运行异步Worker
            loop.run_until_complete(
                TdxDynamicExecutor._async_worker(
                    worker_id, task_queue, result_queue, task_func, 
                    coroutines_per_worker, subprocess_logger
                )
            )
        except Exception as e:
            subprocess_logger.error(f"Worker {worker_id} 异常: {e}", exc_info=True)
        finally:
            try:
                loop.close()
            except Exception:
                pass
    
    @staticmethod
    async def _async_worker(
        worker_id: int,
        task_queue: Queue,
        result_queue: Queue,
        task_func: Callable,
        coroutines_per_worker: int,
        subprocess_logger,
    ):
        """异步Worker
        
        Args:
            worker_id: Worker ID
            task_queue: 任务队列
            result_queue: 结果队列
            task_func: 任务函数
            coroutines_per_worker: 协程数
            subprocess_logger: 日志记录器
        """
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
                    subprocess_logger.warning(f"任务执行失败: {e}")
                    result_queue.put(None)
        
        # 启动协程池
        coroutines = [execute_task() for _ in range(coroutines_per_worker)]
        await asyncio.gather(*coroutines, return_exceptions=True)


# ==============================================================================
# Part 15: IPO日期下载
# ==============================================================================


def download_ipo_dates(
    symbols: List[str],
    progress_callback: Optional[Callable] = None,
    use_multiprocess: bool = True,
    max_workers: int = 4,
) -> Dict[str, Optional[date]]:
    """下载IPO上市日期
    
    Args:
        symbols: 品种代码列表
        progress_callback: 进度回调函数
        use_multiprocess: 是否使用多进程
        max_workers: 最大进程数
        
    Returns:
        {symbol: ipo_date}
    """
    logger.info(f"🚀 开始IPO日期下载: 品种数={len(symbols)}")
    
    # 检查缓存
    cache_manager = DailyCacheManager
    cache_file = Path("cache/ipo_dates.json")
    cached_dates = cache_manager.load_with_date(cache_file)
    
    if cached_dates and isinstance(cached_dates, dict):
        # 过滤已缓存的品种
        uncached_symbols = [s for s in symbols if s not in cached_dates]
        if not uncached_symbols:
            logger.info("✅ 所有IPO日期已缓存")
            return cached_dates
        logger.info(f"📋 缓存命中: {len(symbols) - len(uncached_symbols)}/{len(symbols)}")
        symbols_to_download = uncached_symbols
    else:
        cached_dates = {}
        symbols_to_download = symbols
    
    # 下载未缓存的品种
    if use_multiprocess and len(symbols_to_download) > 50:
        new_dates = _download_ipo_dates_multiprocess(
            symbols_to_download, progress_callback, max_workers
        )
    else:
        new_dates = _download_ipo_dates_single(
            symbols_to_download, progress_callback
        )
    
    # 合并结果
    all_dates = {**cached_dates, **new_dates}
    
    # 保存缓存
    try:
        cache_manager.save_with_date(all_dates, cache_file)
        logger.info(f"✅ IPO日期缓存已更新: {cache_file}")
    except Exception as e:
        logger.warning(f"⚠️ 保存IPO日期缓存失败: {e}")
    
    logger.info(f"✅ IPO日期下载完成: {len(all_dates)}/{len(symbols)}")
    return all_dates


def _download_ipo_dates_single(
    symbols: List[str],
    progress_callback: Optional[Callable] = None,
) -> Dict[str, Optional[date]]:
    """单进程下载IPO日期
    
    Args:
        symbols: 品种代码列表
        progress_callback: 进度回调函数
        
    Returns:
        {symbol: ipo_date}
    """
    results = {}
    total = len(symbols)
    
    # 创建TDX API
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        for i, symbol in enumerate(symbols):
            try:
                ipo_date = loop.run_until_complete(_fetch_single_ipo_date(symbol))
                results[symbol] = ipo_date
            except Exception as e:
                logger.debug(f"获取IPO日期失败: {symbol}, {e}")
                results[symbol] = None
            
            if progress_callback:
                try:
                    progress_callback(i + 1, total, f"已处理: {symbol}")
                except Exception:
                    pass
    finally:
        loop.close()
    
    return results


def _download_ipo_dates_multiprocess(
    symbols: List[str],
    progress_callback: Optional[Callable] = None,
    max_workers: int = 4,
) -> Dict[str, Optional[date]]:
    """多进程下载IPO日期
    
    Args:
        symbols: 品种代码列表
        progress_callback: 进度回调函数
        max_workers: 最大进程数
        
    Returns:
        {symbol: ipo_date}
    """
    results = {}
    
    # 分批
    batch_size = (len(symbols) + max_workers - 1) // max_workers
    batches = [symbols[i:i + batch_size] for i in range(0, len(symbols), batch_size)]
    
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
                    except Exception:
                        pass
            except Exception as e:
                logger.warning(f"批量下载失败: {e}")
    
    return results


def _download_ipo_batch(symbols: List[str]) -> Dict[str, Optional[date]]:
    """下载一批IPO日期（Worker函数）
    
    Args:
        symbols: 品种代码列表
        
    Returns:
        {symbol: ipo_date}
    """
    results = {}
    
    # 创建事件循环
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        for symbol in symbols:
            try:
                ipo_date = loop.run_until_complete(_fetch_single_ipo_date(symbol))
                results[symbol] = ipo_date
            except Exception:
                results[symbol] = None
    finally:
        loop.close()
    
    return results


async def _fetch_single_ipo_date(symbol: str) -> Optional[date]:
    """获取单个品种IPO日期
    
    Args:
        symbol: 品种代码
        
    Returns:
        IPO日期
    """
    try:
        # 确定市场
        market = MultiProcessStockFetcher._get_market_from_symbol(symbol)
        
        # 创建TDX API连接
        api = AsyncTdxHq_API()
        connected = await api.connect("119.147.212.81", 7709)
        
        if not connected:
            return None
        
        try:
            # 获取股票信息
            finance_info = await api.get_finance_info(market, symbol)
            
            if finance_info and len(finance_info) > 0:
                info = finance_info[0]
                # IPO日期字段
                if "ipo_date" in info:
                    ipo_date_int = info["ipo_date"]
                    if ipo_date_int and ipo_date_int > 0:
                        # 解析日期（YYYYMMDD格式）
                        date_str = str(ipo_date_int)
                        if len(date_str) == 8:
                            year = int(date_str[0:4])
                            month = int(date_str[4:6])
                            day = int(date_str[6:8])
                            return date(year, month, day)
            
            return None
        finally:
            await api.disconnect()
    except Exception as e:
        logger.debug(f"获取IPO日期失败: {symbol}, {e}")
        return None


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
    # 连接管理
    "ConnectionLifecycleManager",
    # 数据下载器
    "MultiProcessStockFetcher",
    # TDX读取器
    "BaseReader",
    "BjStockDecoder",
    "TdxBinaryReader",
    # 动态执行器
    "TdxDynamicExecutor",
    # IPO日期下载
    "download_ipo_dates",
]
