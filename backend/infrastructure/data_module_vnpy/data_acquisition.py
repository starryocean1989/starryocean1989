# -*- coding: utf-8 -*-
"""
数据获取模块 - 极限合并版

本模块已完成极限合并：将原3个独立文件合并为1个统一文件data_acquisition.py

合并前文件清单：
1. task_logger.py (241行) - K线下载任务详细日志记录器
2. symbol_management.py (1,420行) - 品种管理模块（品种列表获取、分类、缓存）
3. data_fetcher.py (3,250行) - 数据获取主逻辑（股票数据获取、下载、解码）

合并后：data_acquisition.py (~4,911行)

负责股票数据的获取、下载和解码，包括：
- 股票数据获取器基类和多进程版本
- 服务器池管理
- 数据解码器
- 工作进程函数
- 品种列表的获取、分类和缓存管理
- K线下载任务详细日志记录

API兼容性：100%向后兼容，所有导入路径保持有效

合并日期：2025-10-26
"""


# ==============================================================================
# 子进程日志配置（统一日志系统集成）
# ==============================================================================


def _configure_subprocess_logging(worker_id: int, task_type: str = "worker"):
    """配置子进程日志系统，接入LogHub统一路由

    Args:
        worker_id: 子进程ID
        task_type: 任务类型（kline/ipo/finance/server_test等）

    Returns:
        配置好的logger实例
    """
    import logging
    import sys

    try:
        # 1. 获取LogHub实例
        from backend.infrastructure.system_vnpy.unified_log_system import get_logging_hub

        hub = get_logging_hub()

        # 2. 清理子进程继承的所有handler（避免重复输出）
        root_logger = logging.getLogger()
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
            handler.close()

        # 3. 将LogHub添加到root logger
        root_logger.addHandler(hub)
        root_logger.setLevel(logging.DEBUG)

        # 4. 创建子进程专用logger（带worker_id标识）
        logger_name = f"subprocess.{task_type}.{worker_id}"
        subprocess_logger = logging.getLogger(logger_name)
        subprocess_logger.propagate = True  # 让日志传播到root logger

        subprocess_logger.info(f"✅ 子进程 {worker_id} 日志系统已接入LogHub")
        return subprocess_logger

    except Exception as e:
        # 降级：如果LogHub配置失败，使用标准logger
        fallback_logger = logging.getLogger(__name__)
        fallback_logger.warning(f"⚠️ 子进程 {worker_id} LogHub配置失败，使用降级日志: {e}")
        return fallback_logger


# ==============================================================================
# 第1部分：任务日志记录器（原task_logger.py）
# ==============================================================================

import csv
import os
import time
from datetime import datetime
from typing import Dict, Optional, Tuple
from pathlib import Path
import logging

# ==================== 日志配置 ====================
# 创建专用logger（模块级别）
logger = logging.getLogger("backend.data_module.download")
logger_alert = logging.getLogger("backend.data_module.alert")


class TaskDetailLogger:
    """任务详细日志记录器"""

    def __init__(self, worker_id: int = 0, log_dir: str = "logs"):
        """初始化日志记录器

        Args:
            worker_id: Worker进程ID（用于生成独立的日志文件）
            log_dir: 日志目录
        """
        # 确保使用绝对路径
        if not Path(log_dir).is_absolute():
            from pathlib import Path as _Path

            project_root = _Path(__file__).parent.parent.parent.parent.parent
            self.log_dir = project_root / log_dir
        else:
            self.log_dir = Path(log_dir)

        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.worker_id = worker_id

        # 生成worker专属的日志文件名（避免并发写入冲突）
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = self.log_dir / f"kline_task_details_{timestamp}_worker{worker_id}.csv"

        # 构建服务器->券商映射
        try:
            from backend.infrastructure.tdx_asyncio.constants import (
                HQ_HOSTS_ALL,
                BROKER_SERVERS_7709,
            )
        except ImportError:
            print("⚠️ 无法导入服务器常量，使用空映射")
            self.server_broker_map = {}
            # 即使导入失败也要初始化文件
            self._init_file_handles()
            return

        self.server_broker_map: Dict[str, str] = {}

        # 处理所有服务器列表
        all_server_lists = [
            HQ_HOSTS_ALL,
            BROKER_SERVERS_7709,
        ]

        for server_list in all_server_lists:
            if not server_list:  # 跳过空列表
                continue
            for item in server_list:
                if not item:  # 跳过空项
                    continue
                if len(item) == 3:
                    broker_name, ip, port = item
                    key = f"{ip}:{port}"
                    # 如果已存在，保留第一个（HQ_HOSTS_ALL优先）
                    if key not in self.server_broker_map:
                        self.server_broker_map[key] = broker_name
                elif len(item) == 2:
                    # (ip, port) 格式
                    ip, port = item[0], item[1]  # 显式索引避免类型推断问题
                    key = f"{ip}:{port}"
                    if key not in self.server_broker_map:
                        self.server_broker_map[key] = "未知"

        print(f"📊 [Worker {worker_id}] 已加载 {len(self.server_broker_map)} 个服务器-券商映射")

        # 初始化文件句柄
        self._init_file_handles()

    def _init_file_handles(self):
        """初始化文件句柄和CSV写入器"""
        try:
            self.file_handle = open(self.log_file, "w", encoding="utf-8", newline="")
            self.csv_writer = csv.writer(self.file_handle)
            self._init_csv_file()
            print(f"✅ [Worker {self.worker_id}] 日志文件已创建: {self.log_file}")
        except Exception as e:
            print(f"❌ [Worker {self.worker_id}] 创建日志文件失败: {e}")
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

        # 使用已打开的csv_writer写入header
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
        """
        记录单个任务详情

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
            # 如果csv_writer未初始化，直接返回
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

            # 立即刷新到磁盘（关键！）
            self.file_handle.flush()
            os.fsync(self.file_handle.fileno())

        except Exception as e:
            # 记录日志失败不应该影响主流程
            print(f"⚠️ [Worker {self.worker_id}] 任务日志记录失败: {e}")

    def close(self):
        """关闭日志文件"""
        try:
            if hasattr(self, "file_handle") and self.file_handle:
                self.file_handle.close()
                print(f"✅ 任务详细日志已保存: {self.log_file}")
        except Exception as e:
            print(f"⚠️ 关闭任务日志文件失败: {e}")

    def __del__(self):
        """析构函数，确保文件被关闭"""
        self.close()


# 全局实例（可选）
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
# 第2部分：品种管理模块（原symbol_management.py）
# ==============================================================================


import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
from backend.infrastructure.tdx_asyncio import AsyncTdxHq_API

from .data_module import config_manager, TdxConfigFileParser

# 创建模块级logger实例
logger = logging.getLogger(__name__)


class BlockParser:
    """通达信板块文件解析器

    合并自 block_parser.py
    """

    def __init__(self, tdx_dir: Optional[Path] = None):
        """
        初始化板块解析器

        Args:
            tdx_dir: 通达信软件根目录，如果为None则自动查找
        """
        self.tdx_dir = tdx_dir
        self.block_file_path: Optional[Path] = None
        self._find_block_file()

    def _find_block_file(self) -> None:
        """查找spblock.dat文件（递归搜索）"""
        if self.tdx_dir and self.tdx_dir.exists():
            # 在指定目录下递归搜索spblock.dat
            found = self._search_spblock_in_dir(self.tdx_dir)
            if found:
                return

        # 如果未指定路径或搜索失败，尝试常见根目录并递归搜索
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
        """
        在指定目录下递归搜索spblock.dat文件

        Args:
            directory: 要搜索的目录

        Returns:
            是否找到文件
        """
        try:
            logger.info("正在递归搜索 %s 目录下的spblock.dat文件...", directory)
            for spblock_file in directory.rglob("spblock.dat"):
                if spblock_file.is_file():
                    self.block_file_path = spblock_file
                    logger.info("✓ 找到spblock.dat: %s", spblock_file)
                    return True
            logger.warning("在 %s 目录下未找到spblock.dat文件", directory)
        except OSError as e:
            # 忽略权限错误和文件系统错误
            logger.warning("搜索 %s 时发生错误: %s", directory, e)
            return False
        return False

    def parse_block_file(self) -> pd.DataFrame:
        """
        解析spblock.dat文件（直接使用自定义解析器）

        Returns:
            包含板块信息的DataFrame，列包括：
            - blockname: 板块名称
            - block_type: 板块类型
            - code: 品种代码
        """
        if not self.block_file_path or not self.block_file_path.exists():
            raise FileNotFoundError("未找到spblock.dat文件，请检查通达信软件路径")

        # 直接使用自定义解析器（pytdx的BlockReader对部分文件格式支持不好）
        return self._parse_spblock_custom()

    def _parse_spblock_custom(self) -> pd.DataFrame:
        r"""
        自定义spblock.dat解析器

        文件格式（文本格式，GBK编码）：
        #板块名称\r\n
        代码1\r\n
        代码2\r\n
        ...
        #下一个板块名称\r\n
        ...

        Returns:
            DataFrame with columns: blockname, code
        """
        if not self.block_file_path:
            raise FileNotFoundError("未找到spblock.dat文件")

        results = []

        try:
            # 使用GBK编码读取文本文件
            with open(self.block_file_path, "r", encoding="gbk", errors="ignore") as f:
                lines = f.readlines()

            current_block = ""

            for line in lines:
                line = line.strip()

                if not line:
                    continue

                # 板块名称行（以#开头）
                if line.startswith("#"):
                    current_block = line[1:].strip()  # 去掉#号
                    logger.debug("找到板块: %s", current_block)

                # 股票代码行（纯数字，可能是6位或7位）
                elif line.isdigit() and len(line) >= 6:
                    # 保留完整的原始代码（可能是7位）
                    original_code = line

                    # 提取实际的6位股票代码
                    if len(line) == 7:
                        # 7位代码：第1位是市场代码，后6位是股票代码
                        market_code = line[0]
                        stock_code = line[1:7]
                    else:
                        # 6位或其他长度，直接使用前6位
                        market_code = ""
                        stock_code = line[:6].zfill(6)

                    if current_block:
                        results.append(
                            {
                                "blockname": current_block,
                                "code": stock_code,
                                "original_code": original_code,
                                "market_code": market_code,
                                "block_type": "text",
                            }
                        )

            # 转换为DataFrame
            if not results:
                logger.warning("spblock.dat解析未找到任何数据")
                return pd.DataFrame(columns=["blockname", "code", "block_type"])  # type: ignore[arg-type]

            df = pd.DataFrame(results)
            logger.info(
                "成功解析spblock.dat: %d 条记录，%d 个板块", len(df), df["blockname"].nunique()
            )
            return df

        except Exception as e:
            logger.error("自定义解析spblock.dat失败: %s", e, exc_info=True)
            # 返回空DataFrame但保持结构
            return pd.DataFrame(columns=["blockname", "code", "block_type"])  # type: ignore[arg-type]

    def get_target_blocks(self) -> Dict[str, List[str]]:
        """
        获取目标板块的品种代码列表

        Returns:
            字典，键为板块名称，值为品种代码列表
        """
        df = self.parse_block_file()

        target_blocks: Dict[str, List[str]] = {
            "融资融券_北证A股": [],
            "T+0基金": [],
            "含可转债": [],
        }

        for _, row in df.iterrows():
            block_name = str(row["blockname"])
            code = str(row["code"])
            original_code = str(row.get("original_code", code))

            # 融资融券板块：从7位代码中提取29开头的（北证A股）
            # 7位代码格式：第1位是市场代码，后6位是股票代码
            # 29xxxxx表示北证A股（市场代码2，股票代码9xxxxx）
            if (
                "融资融券" in block_name
                and len(original_code) == 7
                and original_code.startswith("29")
            ):
                target_blocks["融资融券_北证A股"].append(code)

            # T+0基金板块
            if "T+0基金" in block_name:
                target_blocks["T+0基金"].append(code)

            # 含可转债板块
            if "含可转债" in block_name:
                target_blocks["含可转债"].append(code)

        return target_blocks

    def get_beijing_stocks(self) -> List[str]:
        """
        获取北证A股品种代码列表（从融资融券板块中提取29开头的7位代码）

        Returns:
            北证A股品种代码列表（6位代码，9xxxxx格式）
        """
        target_blocks = self.get_target_blocks()
        return target_blocks.get("融资融券_北证A股", [])

    def get_t0_funds(self) -> List[str]:
        """
        获取T+0基金品种代码列表

        Returns:
            T+0基金品种代码列表
        """
        target_blocks = self.get_target_blocks()
        return target_blocks["T+0基金"]

    def get_convertible_bonds(self) -> List[str]:
        """
        获取含可转债品种代码列表

        Returns:
            含可转债品种代码列表
        """
        target_blocks = self.get_target_blocks()
        return target_blocks["含可转债"]

    def get_t0_fund_codes(self) -> List[Dict[str, Any]]:
        """
        提取T+0基金板块中01/15开头的7位代码（仅限块名包含“T+0基金”的区段）

        7位格式：第1位是市场代码（0或1），后6位是品种代码
        示例：`0151880`表示市场代码0，品种代码151880

        Returns:
            [{"market": 0, "code": "151880"}, {"market": 1, "code": "511880"}, ...]
        """
        if not self.block_file_path or not self.block_file_path.exists():
            logger.warning("spblock.dat 文件不存在，返回空列表")
            return []

        result: List[Dict[str, Any]] = []

        try:
            # 使用GBK编码读取文本文件
            with open(self.block_file_path, "r", encoding="gbk", errors="ignore") as f:
                lines = f.readlines()

            current_block = ""

            for line in lines:
                line = line.strip()

                if not line:
                    continue

                # 板块名称行（以#开头）
                if line.startswith("#"):
                    current_block = line[1:].strip()
                    logger.debug("找到板块: %s", current_block)
                    continue

                # 仅在“T+0基金”板块内处理7位数字代码
                if "T+0基金" in current_block and line.isdigit() and len(line) == 7:
                    market_code = int(line[0])
                    stock_code = line[1:7]

                    # 只保留市场0且品种代码1开头，或市场1且品种代码5开头
                    if (market_code == 0 and stock_code.startswith("1")) or (
                        market_code == 1 and stock_code.startswith("5")
                    ):
                        result.append({"market": market_code, "code": stock_code})

            logger.info("成功提取 T+0基金代码（限块名）: %d 个", len(result))
            return result

        except Exception as e:
            logger.error("提取 T+0基金代码失败: %s", e, exc_info=True)
            return []

    def get_all_target_stocks(self) -> List[str]:
        """
        获取所有目标板块的品种代码（去重）

        Returns:
            所有目标品种代码列表
        """
        target_blocks = self.get_target_blocks()
        all_stocks = []
        for stocks in target_blocks.values():
            all_stocks.extend(stocks)
        return list(set(all_stocks))  # 去重

    def is_available(self) -> bool:
        """
        检查板块文件是否可用

        Returns:
            是否可用
        """
        return self.block_file_path is not None and self.block_file_path.exists()

    def get_file_info(self) -> Dict[str, str]:
        """
        获取板块文件信息

        Returns:
            文件信息字典
        """
        if not self.is_available() or self.block_file_path is None:
            return {"status": "不可用", "path": ""}

        file_path = str(self.block_file_path)
        file_size = self.block_file_path.stat().st_size

        return {
            "status": "可用",
            "path": file_path,
            "size": f"{file_size / 1024:.2f} KB",
        }


class SymbolLoader:
    """品种列表加载器"""

    def __init__(self, event_engine=None):
        """
        初始化加载器

        Args:
            event_engine: vnpy事件引擎（可选，传入后可推送事件）
        """
        self.logger = logger
        self.logger_alert = logger_alert

        # 初始化配置文件解析器
        tdx_dir = config_manager.get_tdx_dir()
        self.config_parser = TdxConfigFileParser(tdx_dir)
        self.block_parser = BlockParser(tdx_dir)

        # 缓存目录
        self.cache_dir = config_manager.get_cache_dir()
        self.cache_file = self.cache_dir / "stock_list_classified.json"

        # 事件发布器（从core.py迁移）
        self.event_engine = event_engine
        if event_engine:
            from .data_module import DownloadEventPublisher, EventPublisher

            self.event_publisher = EventPublisher(event_engine)
            self.download_publisher = DownloadEventPublisher(event_engine)
        else:
            self.event_publisher = None
            self.download_publisher = None

    def load_from_api(self) -> Dict[str, Any]:
        """
        从API加载完整品种列表并分类

        Returns:
            Dict {
                "classified": {
                    "上证A股": [{"code": "600000", "name": "浦发银行", "market": 1}, ...],
                    "深证A股": [...],
                    "北证A股": [...],
                    "T+0基金": [...],
                    "可转债": [...]
                },
                "empty_categories": List[str]  # 为空的品种类别列表
            }
        """
        self.logger.info("=" * 60)
        self.logger.info("开始从API加载品种列表")
        self.logger.info("=" * 60)

        # 步骤1: 获取完整品种缓存（集合D）
        complete_df = self._fetch_complete_stocks()

        # 步骤2: 分类品种
        classified = self._classify_stocks(complete_df)

        # 步骤2.5: 检查空集合（集合E,F,G,H,I）
        empty_categories = []
        category_names = {
            "上证A股": "集合E",
            "深证A股": "集合F",
            "北证A股": "集合I",
            "T+0基金": "集合H",
            "可转债": "集合G",
        }

        for category, category_code in category_names.items():
            if not classified.get(category):
                empty_categories.append(category)
                self.logger.warning("⚠️ %s（%s）为空，请排查相关问题", category, category_code)

        # 步骤3: 缓存到本地
        self._save_cache(classified)

        self.logger.info("=" * 60)
        self.logger.info(
            "API加载完成，共获取 %d 个品种", sum(len(stocks) for stocks in classified.values())
        )
        if empty_categories:
            self.logger.warning("⚠️ 存在空品种类别: %s", ", ".join(empty_categories))
        self.logger.info("=" * 60)

        return {"classified": classified, "empty_categories": empty_categories}

    def load_from_cache(self) -> Optional[Dict[str, List[Dict[str, Any]]]]:
        """
        从本地缓存加载品种分类（不验证日期，兼容旧代码）

        Returns:
            分类后的品种字典，如果缓存不存在返回None
        """
        classified, _ = self.load_from_cache_with_validation()
        return classified

    def load_from_cache_with_validation(
        self,
    ) -> tuple[Optional[Dict[str, List[Dict[str, Any]]]], bool]:
        """
        从缓存加载品种列表并验证日期

        Returns:
            Tuple[classified, is_outdated]:
            - classified: 分类后的品种字典（None表示不存在）
            - is_outdated: 是否过时（True=需要更新）
        """
        try:
            from .data_module import DailyCacheManager

            cache_data, cache_date, is_valid = DailyCacheManager.load_with_validation(
                "stock_list_classified.json"
            )

            if not cache_data:
                self.logger.info("品种列表缓存不存在")
                return None, False

            classified = cache_data.get("classified", {})

            # 🔧 记录缓存日期供core.py输出使用
            self._last_cache_date = cache_date

            # 🔧 V2优化：合并为单行汇总输出，详细信息记录到DEBUG级别
            sz_count = len(classified.get("上证A股", []))
            sh_count = len(classified.get("深证A股", []))
            bj_count = len(classified.get("北证A股", []))
            fund_count = len(classified.get("T+0基金", []))
            bond_count = len(classified.get("可转债", []))
            total_count = sz_count + sh_count + bj_count + fund_count + bond_count

            if not is_valid:
                self.logger.warning(
                    "品种列表缓存已过时（日期: %s），共%d个品种，建议更新", cache_date, total_count
                )
            else:
                self.logger.info(
                    "品种列表缓存有效（日期: %s），共%d个品种 | 沪%d+深%d+北%d+基金%d+转债%d",
                    cache_date,
                    total_count,
                    sz_count,
                    sh_count,
                    bj_count,
                    fund_count,
                    bond_count,
                )

            # 详细信息记录到DEBUG级别（需要时可查看）
            self.logger.debug("  - 上证A股: %d", sz_count)
            self.logger.debug("  - 深证A股: %d", sh_count)
            self.logger.debug("  - 北证A股: %d", bj_count)
            self.logger.debug("  - T+0基金: %d", fund_count)
            self.logger.debug("  - 可转债: %d", bond_count)

            return classified, not is_valid

        except Exception as e:
            self.logger.error("加载品种列表缓存失败: %s", e, exc_info=True)
            return None, False

    def _fetch_complete_stocks(self) -> pd.DataFrame:
        """
        获取完整品种列表（集合D）

        分别调用market=0、1，手动添加market列后合并
        注意：北交所（market=2）品种不从API获取，完全从addedcode_bj.cfg解析获得

        架构设计（asyncio并发模式）：
        - 使用asyncio.gather并发获取深圳和上海两个市场
        - 每个市场：单连接，串行请求所有页
        - 网络I/O密集型任务，asyncio比multiprocessing更高效
        - 避免在QThread中创建子进程导致的Windows spawn死锁问题

        Returns:
            包含market列的完整DataFrame
        """
        self.logger.info("步骤1: 获取完整品种缓存（集合D）")
        self.logger.info("→ asyncio并发模式：市场0和市场1并发获取...")

        # 获取最优服务器（使用IPv4池）
        from .load_balancer import server_pool_manager

        best_servers = server_pool_manager.get_servers(pool_type="ipv4")
        self.logger.info("  ✓ 获取到 %d 个已排序的最优IPv4服务器", len(best_servers))

        # 为每个市场准备3个候选服务器（支持故障切换）
        if len(best_servers) < 6:
            self.logger.warning("可用服务器不足6个，仅%d个，可能影响容错能力", len(best_servers))

        # 深圳市场候选池：服务器0, 2, 4
        # 上海市场候选池：服务器1, 3, 5
        market_server_pools = {
            0: [best_servers[i] for i in [0, 2, 4] if i < len(best_servers)],  # 深圳
            1: [best_servers[i] for i in [1, 3, 5] if i < len(best_servers)],  # 上海
        }

        # 确保每个市场至少有1个服务器
        for market, pool in market_server_pools.items():
            market_name = "深圳" if market == 0 else "上海"
            if not pool:
                raise RuntimeError(f"{market_name}市场无可用服务器")
            self.logger.info("  → %s市场候选池: %d个服务器", market_name, len(pool))
            for idx, srv in enumerate(pool):
                self.logger.info("    %d. %s:%s", idx + 1, srv[0], srv[1])

        # 🚀 修复：使用asyncio并发替代multiprocessing，避免Windows spawn死锁
        import asyncio
        import time

        self.logger.info("  创建asyncio事件循环...")
        start_time = time.time()

        # 在当前线程中创建并运行asyncio事件循环
        try:
            # 如果已有事件循环，使用它；否则创建新的
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        # 并发获取两个市场的数据
        market_data = loop.run_until_complete(self._fetch_both_markets_async(market_server_pools))

        elapsed = time.time() - start_time
        self.logger.info("  ✅ asyncio并发获取完成，耗时: %.1f秒", elapsed)

        if not market_data:
            raise RuntimeError("获取市场数据失败：所有市场均未返回数据")

        # 构建DataFrame
        stocks_list = []
        for market in [0, 1]:
            if market in market_data and market_data[market]:
                df = pd.DataFrame(market_data[market])
                df["market"] = market
                df = df.drop_duplicates(subset=["code"], keep="first")
                stocks_list.append(df)
                market_name = "深圳" if market == 0 else "上海"
                self.logger.info("  ✓ %s市场: %d 个品种", market_name, len(df))

                # 验证market字段的正确性
                if "market" in df.columns:
                    actual_markets = df["market"].unique()
                    if len(actual_markets) != 1 or actual_markets[0] != market:
                        self.logger.error(
                            "  ❌ %s市场数据异常！期望market=%d，实际包含%s",
                            market_name,
                            market,
                            actual_markets.tolist(),
                        )
                    # 显示代码前缀分布（帮助诊断数据来源）
                    if "code" in df.columns:
                        code_prefixes = df["code"].astype(str).str[:2].value_counts().head(5)
                        self.logger.info("  代码前缀分布TOP5: %s", dict(code_prefixes))
            else:
                market_name = "深圳" if market == 0 else "上海"
                self.logger.warning("  ⚠ %s市场: 无数据", market_name)

        if not stocks_list:
            raise RuntimeError("未能获取任何品种数据")

        complete_df = pd.concat(stocks_list, ignore_index=True)

        # 补齐代码位数
        complete_df["code"] = complete_df["code"].astype(str).str.zfill(6)

        self.logger.info("  ← 集合D: %d 个品种（含market列）", len(complete_df))

        return complete_df

    async def _fetch_both_markets_async(
        self, market_server_pools: dict[int, list[tuple[str, int]]]
    ) -> dict:
        """
        使用asyncio并发获取两个市场的数据

        Args:
            market_server_pools: {0: [(ip, port), ...], 1: [(ip, port), ...]}

        Returns:
            {0: [stocks_list], 1: [stocks_list]}
        """
        import asyncio

        # 并发执行两个市场的获取任务（带故障切换）
        tasks = [
            self._fetch_single_market_with_failover(0, market_server_pools[0]),
            self._fetch_single_market_with_failover(1, market_server_pools[1]),
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 处理结果
        market_data = {}
        for i, result in enumerate(results):
            market = i  # 0=深圳, 1=上海
            if isinstance(result, Exception):
                market_name = "深圳" if market == 0 else "上海"
                self.logger.error("  ❌ %s市场获取失败: %s", market_name, result)
            else:
                market_data[market] = result

        return market_data

    async def _fetch_single_market_with_failover(
        self, market: int, server_pool: list[tuple[str, int]]
    ) -> list:
        """
        带故障切换的市场数据获取

        Args:
            market: 市场代码（0=深圳，1=上海）
            server_pool: 服务器候选池

        Returns:
            stocks列表

        Raises:
            RuntimeError: 所有服务器均失败
        """
        market_name = "深圳" if market == 0 else "上海"

        for server_idx, server in enumerate(server_pool):
            try:
                self.logger.info(
                    "[%s] 尝试服务器 %d/%d: %s:%s",
                    market_name,
                    server_idx + 1,
                    len(server_pool),
                    server[0],
                    server[1],
                )

                # 单服务器重试1次
                result = await self._fetch_single_market_async(
                    market, server, max_retries=1, timeout=3.0
                )

                if result:
                    self.logger.info(
                        "[%s] ✓ 服务器 %s:%s 成功获取 %d 个品种",
                        market_name,
                        server[0],
                        server[1],
                        len(result),
                    )
                    return result
                else:
                    self.logger.warning(
                        "[%s] 服务器 %s:%s 返回空数据", market_name, server[0], server[1]
                    )

            except Exception as e:
                self.logger.warning(
                    "[%s] 服务器 %s:%s 失败: %s", market_name, server[0], server[1], str(e)
                )

                # 如果不是最后一个服务器，继续尝试下一个
                if server_idx < len(server_pool) - 1:
                    self.logger.info("[%s] 切换到下一个候选服务器...", market_name)
                    continue
                else:
                    # 所有服务器都失败了
                    raise RuntimeError(
                        f"{market_name}市场：所有{len(server_pool)}个候选服务器均失败"
                    )

        # 理论上不会到达这里
        raise RuntimeError(f"{market_name}市场：无可用服务器")

    async def _fetch_single_market_async(
        self,
        market: int,
        server: tuple[str, int],
        max_retries: int = 1,  # 新增参数：默认重试1次
        timeout: float = 3.0,  # 新增参数：默认3秒超时
    ) -> list:
        """
        异步获取单个市场的数据（从_fetch_market_in_process迁移）

        Args:
            market: 市场代码（0=深圳，1=上海）
            server: 服务器地址 (ip, port)
            max_retries: 单页请求最大重试次数
            timeout: 单次请求超时时间（秒）

        Returns:
            stocks列表
        """
        import asyncio
        from backend.infrastructure.tdx_asyncio import AsyncTdxHq_API

        market_name = "深圳" if market == 0 else "上海"

        try:
            self.logger.info("[%s] 开始连接服务器 %s:%s", market_name, server[0], server[1])

            # 建立连接
            client = await asyncio.wait_for(
                AsyncTdxHq_API.factory(
                    server=server, timeout=timeout, heartbeat=False, raise_exception=False
                ),
                timeout=timeout + 2.0,  # 连接超时比请求超时多2秒
            )

            if not client:
                raise RuntimeError(f"无法连接到服务器 {server[0]}:{server[1]}")

            self.logger.info("[%s] ✓ 连接成功，开始串行分页请求...", market_name)
            self.logger.info("[%s] 使用服务器: %s:%s", market_name, server[0], server[1])

            all_stocks = []
            start = 0
            page = 1

            try:
                while True:
                    stocks = None

                    # 重试机制（使用同一个连接）
                    for retry in range(max_retries):
                        try:
                            stocks = await asyncio.wait_for(
                                client.get_security_list(market=market, start=start),
                                timeout=timeout,  # 使用参数化的超时时间
                            )

                            if stocks:
                                # 显示样本代码以便诊断
                                sample_codes = (
                                    [s.get("code", "") for s in stocks[:3]]
                                    if len(stocks) >= 3
                                    else []
                                )
                                self.logger.info(
                                    "[%s] 第%d页: %d条 (样本代码: %s)",
                                    market_name,
                                    page,
                                    len(stocks),
                                    ", ".join(sample_codes) if sample_codes else "N/A",
                                )
                                break
                            else:
                                self.logger.debug("[%s] 第%d页返回空数据", market_name, page)
                                break

                        except asyncio.TimeoutError:
                            self.logger.warning(
                                "[%s] 第%d页超时%ds (尝试%d/%d)",
                                market_name,
                                page,
                                int(timeout),
                                retry + 1,
                                max_retries,
                            )
                        except Exception as e:
                            self.logger.debug(
                                "[%s] 第%d页失败: %s (尝试%d/%d)",
                                market_name,
                                page,
                                e,
                                retry + 1,
                                max_retries,
                            )

                    # 检查是否继续
                    if not stocks:
                        break

                    all_stocks.extend(stocks)

                    if len(stocks) < 1000:
                        break

                    start += len(stocks)
                    page += 1

            finally:
                # 关闭连接
                if client:
                    await client.close()

            self.logger.info("[%s] ✓ 获取完成: %d 个品种", market_name, len(all_stocks))
            return all_stocks

        except Exception as e:
            self.logger.error("[%s] 获取失败: %s", market_name, e, exc_info=True)
            raise

    @staticmethod
    def _fetch_market_in_process(market: int, server: tuple[str, int], shared_results: dict):
        """
        在子进程中运行的市场数据获取函数

        Args:
            market: 市场代码（0=深圳，1=上海）
            server: 服务器地址 (ip, port)
            shared_results: 共享内存字典，用于存储结果
        """
        import logging
        import asyncio

        # 为子进程设置日志
        market_name = "深圳" if market == 0 else "上海"
        logger = logging.getLogger(f"MarketFetch-{market}")

        async def fetch_market():
            """
            子进程中的异步函数：连接服务器并串行获取所有页
            """
            try:
                logger.info("[%s] 开始连接服务器 %s:%s", market_name, server[0], server[1])

                # 建立连接
                client = await asyncio.wait_for(
                    AsyncTdxHq_API.factory(
                        server=server, timeout=3.0, heartbeat=False, raise_exception=False
                    ),
                    timeout=5.0,
                )

                if not client:
                    raise RuntimeError(f"无法连接到服务器 {server[0]}:{server[1]}")

                logger.info("[%s] ✓ 连接成功，开始串行分页请求...", market_name)
                # 记录使用的服务器
                logger.info("[%s] 使用服务器: %s:%s", market_name, server[0], server[1])

                all_stocks = []
                start = 0
                page = 1
                max_retries = 3

                try:
                    while True:
                        stocks = None

                        # 重试机制（使用同一个连接）
                        for retry in range(max_retries):
                            try:
                                stocks = await asyncio.wait_for(
                                    client.get_security_list(market=market, start=start),
                                    timeout=10.0,
                                )

                                if stocks:
                                    # 显示样本代码以便诊断
                                    sample_codes = (
                                        [s.get("code", "") for s in stocks[:3]]
                                        if len(stocks) >= 3
                                        else []
                                    )
                                    logger.info(
                                        "[%s] 第%d页: %d条 (样本代码: %s)",
                                        market_name,
                                        page,
                                        len(stocks),
                                        ", ".join(sample_codes) if sample_codes else "N/A",
                                    )
                                    break
                                else:
                                    logger.debug("[%s] 第%d页返回空数据", market_name, page)
                                    break

                            except asyncio.TimeoutError:
                                logger.warning(
                                    "[%s] 第%d页超时 (尝试%d/%d)",
                                    market_name,
                                    page,
                                    retry + 1,
                                    max_retries,
                                )
                            except Exception as e:
                                logger.debug(
                                    "[%s] 第%d页失败: %s (尝试%d/%d)",
                                    market_name,
                                    page,
                                    e,
                                    retry + 1,
                                    max_retries,
                                )

                        # 检查是否继续
                        if not stocks:
                            break

                        all_stocks.extend(stocks)

                        if len(stocks) < 1000:
                            break

                        start += 1000
                        page += 1

                    logger.info(
                        "[%s] ✓ 获取完成: %d条原始数据（共%d页）",
                        market_name,
                        len(all_stocks),
                        page,
                    )

                    # 存入共享内存
                    shared_results[market] = all_stocks

                finally:
                    await client.close()
                    logger.debug("[%s] 连接已关闭", market_name)

            except Exception as e:
                logger.error("[%s] ❌ 获取失败: %s", market_name, e, exc_info=True)
                logger.error("[%s] 失败详情:", market_name)
                logger.error("  - 服务器: %s:%s", server[0], server[1])
                logger.error("  - 已获取数据量: %d", len(all_stocks))
                logger.error("  - 异常类型: %s", type(e).__name__)
                shared_results[market] = []

        # 创建新事件循环并运行
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            loop.run_until_complete(fetch_market())
        finally:
            loop.close()

    def _classify_stocks(self, complete_df: pd.DataFrame) -> Dict[str, List[Dict[str, Any]]]:
        """
        分类品种（按照需求逻辑）

        Args:
            complete_df: 完整品种DataFrame（集合D）

        Returns:
            分类后的品种字典
        """
        self.logger.info("步骤2: 分类品种")

        result = {"上证A股": [], "深证A股": [], "北证A股": [], "T+0基金": [], "可转债": []}

        # 验证DataFrame结构
        if "market" not in complete_df.columns:
            raise ValueError("DataFrame缺少market列")

        # 集合E: 上证A股 (market==1 AND code.startswith('688'|'60'))
        sh_mask = (complete_df["market"] == 1) & (
            complete_df["code"].str.startswith("688") | complete_df["code"].str.startswith("60")
        )
        sh_stocks: pd.DataFrame = complete_df[sh_mask]  # type: ignore[assignment]
        result["上证A股"] = self._build_stock_list(sh_stocks)

        # 集合F: 深证A股 (market==0 AND code.startswith('000'|'001'|'002'|'300'|'301'))
        sz_mask = (complete_df["market"] == 0) & (
            complete_df["code"].str.startswith("000")
            | complete_df["code"].str.startswith("001")
            | complete_df["code"].str.startswith("002")
            | complete_df["code"].str.startswith("300")
            | complete_df["code"].str.startswith("301")
        )
        sz_stocks: pd.DataFrame = complete_df[sz_mask]  # type: ignore[assignment]
        result["深证A股"] = self._build_stock_list(sz_stocks)

        # 集合I: 北证A股（从addedcode_bj.cfg获取）
        result["北证A股"] = self._get_beijing_stocks()

        # 集合H: T+0基金（从spblock.dat获取市场+代码，再从集合D匹配名称）
        result["T+0基金"] = self._get_t0_funds(complete_df)

        # 集合G: 可转债（从tdxstat2.cfg获取市场+代码，再从集合D匹配名称）
        result["可转债"] = self._get_convertible_bonds(complete_df)

        # 统计
        self.logger.info("  ← 分类完成:")
        for category, stocks in result.items():
            self.logger.info("    • %s: %d 个", category, len(stocks))

        # 🔧 验证所有品种数据的完整性（确保code和name都有效）
        validated_result = {}
        total_filtered = 0

        for category, stocks in result.items():
            validated_stocks = []
            for stock in stocks:
                code = stock.get("code", "").strip()
                name = stock.get("name", "").strip()
                # 确保code和name都有效
                if code and name:
                    validated_stocks.append(stock)
                else:
                    total_filtered += 1
                    self.logger.debug(
                        "过滤无效品种: code=%s, name=%s, category=%s", code, name, category
                    )
            validated_result[category] = validated_stocks

        if total_filtered > 0:
            self.logger.info("  ⚠️ 过滤了 %d 个无效品种（缺少有效code或name）", total_filtered)
            # 输出验证后的统计
            self.logger.info("  ← 验证后统计:")
            for category, stocks in validated_result.items():
                self.logger.info("    • %s: %d 个", category, len(stocks))

        return validated_result

    def _build_stock_list(self, df: pd.DataFrame) -> List[Dict[str, Any]]:
        """
        将DataFrame转换为字典列表

        Args:
            df: 品种DataFrame

        Returns:
            [{"code": "600000", "name": "浦发银行", "market": 1}, ...]
        """
        result = []
        for _, row in df.iterrows():
            result.append(
                {
                    "code": str(row["code"]),
                    "name": str(row.get("name", "")),
                    "market": int(row["market"]),
                }
            )
        return result

    def _get_beijing_stocks(self) -> List[Dict[str, Any]]:
        """
        获取北证A股（集合B → 集合I）

        从addedcode_bj.cfg读取9开头的代码和简称，添加固定市场代码2
        注意：北交所品种的代码、简称完全来源于addedcode_bj.cfg的解析，
        市场代码2为硬编码值，不从API或其他文件获取

        Returns:
            [{"code": "9xxxxx", "name": "xxx", "market": 2}, ...]
        """
        if not self.config_parser.is_available():
            self.logger.warning("  ⚠ 配置文件不可用，北证A股为空")
            return []

        try:
            beijing_stocks = self.config_parser.parse_addedcode_bj()
            result = []

            for stock in beijing_stocks:
                result.append(
                    {
                        "code": stock["code"],
                        "name": stock["name"],
                        "market": 2,
                    }  # 市场代码2为硬编码值
                )

            count = len(result)
            if count == 0:
                try:
                    info = self.config_parser.get_file_info()
                    self.logger.warning("  ⚠ 北证A股解析为空，文件信息: %s", info)
                except Exception:
                    pass
            else:
                samples = result[:3]
                self.logger.info("  → 北证A股: %d 个（样例: %s）", count, samples)

            return result

        except Exception as e:
            self.logger.warning("  ⚠ 解析北证A股失败: %s", e)
            return []

    def _get_t0_funds(self, complete_df: pd.DataFrame) -> List[Dict[str, Any]]:
        """
        获取T+0基金（集合C → 集合H）

        从spblock.dat获取市场+代码，再从完整缓存匹配名称

        Returns:
            [{"code": "151880", "name": "xxx", "market": 0}, ...]
        """
        if not self.block_parser.is_available():
            self.logger.warning("  ⚠ spblock.dat不可用，T+0基金为空")
            return []

        try:
            t0_fund_codes = self.block_parser.get_t0_fund_codes()
            total = len(t0_fund_codes)
            result = []
            unmatched_count = 0
            unmatched_samples = []

            for fund in t0_fund_codes:
                market = int(fund["market"])
                code = str(fund["code"]).zfill(6)

                # 从完整缓存中匹配
                matched = complete_df[
                    (complete_df["market"] == market) & (complete_df["code"] == code)
                ]

                if len(matched) > 0:
                    name = str(matched.iloc[0].get("name", ""))
                    result.append({"code": code, "name": name, "market": market})
                else:
                    # API中无匹配的品种视为不存在（已退市/到期），直接跳过
                    unmatched_count += 1
                    if len(unmatched_samples) < 3:
                        unmatched_samples.append({"market": market, "code": code})
                    # 不再添加空名称品种到结果列表

            matched_count = total - unmatched_count
            self.logger.info(
                "  → T+0基金: %d 个（匹配到名称: %d，API中不存在已过滤: %d，示例: %s）",
                len(result),
                matched_count,
                unmatched_count,
                unmatched_samples,
            )
            return result

        except Exception as e:
            self.logger.warning("  ⚠ 解析T+0基金失败: %s", e)
            return []

    def _get_convertible_bonds(self, complete_df: pd.DataFrame) -> List[Dict[str, Any]]:
        """
        获取可转债（集合A → 集合G）

        从tdxstat2.cfg获取市场+代码，再从完整缓存匹配名称

        Returns:
            [{"code": "110xxx", "name": "xxx", "market": 1}, ...]
        """
        if not self.config_parser.is_available():
            self.logger.warning("  ⚠ 配置文件不可用，可转债为空")
            return []

        try:
            convertible_codes_by_market = self.config_parser.parse_tdxstat2()
            total = sum(len(v) for v in convertible_codes_by_market.values())
            result = []
            unmatched_count = 0
            unmatched_samples = []

            for market, codes in convertible_codes_by_market.items():
                mkt = int(market)
                for raw_code in codes:
                    code = str(raw_code).zfill(6)

                    # 从完整缓存中匹配
                    matched: pd.DataFrame = complete_df[  # type: ignore[assignment]
                        (complete_df["market"] == mkt) & (complete_df["code"] == code)
                    ]

                    if len(matched) > 0:
                        # 如果有多个匹配，过滤掉指数
                        if len(matched) > 1:
                            non_index: pd.DataFrame = matched[  # type: ignore[assignment]
                                ~matched["name"].str.contains("指数|ETF", na=False, regex=True)
                            ]
                            if len(non_index) > 0:
                                matched = non_index

                        name = str(matched.iloc[0].get("name", ""))
                        result.append({"code": code, "name": name, "market": mkt})
                    else:
                        # API中无匹配的品种视为不存在（已退市/到期），直接跳过
                        unmatched_count += 1
                        if len(unmatched_samples) < 3:
                            unmatched_samples.append({"market": mkt, "code": code})
                        # 不再添加空名称品种到结果列表

            matched_count = total - unmatched_count
            self.logger.info(
                "  → 可转债: %d 个（匹配到名称: %d，API中不存在已过滤: %d，示例: %s）",
                len(result),
                matched_count,
                unmatched_count,
                unmatched_samples,
            )
            return result

        except Exception as e:
            self.logger.warning("  ⚠ 解析可转债失败: %s", e)
            return []

    def _save_cache(self, classified: Dict[str, List[Dict[str, Any]]]) -> None:
        """
        保存分类结果到本地缓存（使用DailyCacheManager）

        Args:
            classified: 分类后的品种字典
        """
        self.logger.info("步骤3: 保存缓存")

        try:
            from .data_module import DailyCacheManager

            cache_data = {
                "total_count": sum(len(stocks) for stocks in classified.values()),
                "classified": classified,
            }

            # 使用DailyCacheManager保存缓存（带日期）
            success = DailyCacheManager.save_with_date(cache_data, "stock_list_classified.json")

            if success:
                self.logger.info("  ✓ 缓存已保存: %s", self.cache_file)
            else:
                self.logger.error("  ✗ 保存缓存失败")
                raise RuntimeError("保存缓存失败")

        except Exception as e:
            self.logger.error("  ✗ 保存缓存失败: %s", e, exc_info=True)
            raise

    def clear_cache(self) -> bool:
        """
        删除品种列表缓存（清理集合A-I的所有缓存）

        Returns:
            是否成功删除
        """
        try:
            if self.cache_file.exists():
                self.cache_file.unlink()
                self.logger.info("✓ 已删除品种列表缓存: %s", self.cache_file)
                return True
            else:
                self.logger.warning("品种列表缓存文件不存在: %s", self.cache_file)
                return True  # 文件不存在也算成功

        except Exception as e:
            self.logger.error("删除品种列表缓存失败: %s", e, exc_info=True)
            return False

    def update_ipo_dates_and_remove_unlisted(
        self, ipo_data: Dict[str, Any], unlisted_symbols: List[str]
    ) -> tuple[bool, Dict[str, int]]:
        """从品种列表缓存中删除未上市品种，同时清理IPO缓存

        Args:
            ipo_data: {symbol: ipo_date} 映射（用于同步清理IPO缓存）
            unlisted_symbols: 未上市品种代码列表

        Returns:
            是否成功更新
        """
        try:
            # 1. 加载品种列表缓存
            classified, _ = self.load_from_cache_with_validation()
            if not classified:
                self.logger.error("无法加载品种列表缓存")
                return False, {}

            # 2. 删除未上市品种（不再写入 ipo_date 字段）
            removed_count = 0
            unlisted_set = set(unlisted_symbols)
            category_removed = {}  # 记录每个分类删除的数量

            for category in classified:
                original_count = len(classified[category])
                classified[category] = [
                    stock for stock in classified[category] if stock.get("code") not in unlisted_set
                ]
                removed = original_count - len(classified[category])
                if removed > 0:
                    category_removed[category] = removed
                    self.logger.info(f"  - {category}: 删除 {removed} 个未上市品种")
                    removed_count += removed

            self.logger.info(f"✓ 从品种列表删除 {len(unlisted_symbols)} 个未上市品种")

            # 3. 保存更新后的品种列表缓存
            self._save_cache(classified)

            # 4. 同步清理 IPO 缓存文件中的未上市品种
            if unlisted_symbols:
                try:
                    from .data_quality import get_ipo_cache

                    ipo_cache = get_ipo_cache()

                    # 从内存缓存中删除
                    for symbol in unlisted_symbols:
                        if symbol in ipo_cache._memory_cache:
                            del ipo_cache._memory_cache[symbol]

                    # 保存到文件
                    ipo_cache.batch_save()
                    self.logger.info(f"✓ 从IPO缓存删除 {len(unlisted_symbols)} 个未上市品种")

                except Exception as e:
                    self.logger.error(f"清理IPO缓存失败: {e}", exc_info=True)

            # 🆕 保存未上市品种到专用缓存文件
            if unlisted_symbols:
                try:
                    from .data_module import DailyCacheManager

                    # 保存未上市品种列表
                    unlisted_data = {
                        "symbols": unlisted_symbols,
                        "count": len(unlisted_symbols),
                        "category_stats": category_removed,
                    }

                    success_save = DailyCacheManager.save_with_date(
                        unlisted_data, "unlisted_symbols.json"
                    )
                    if success_save:
                        self.logger.info("✓ 未上市品种缓存已保存: %d个品种", len(unlisted_symbols))
                    else:
                        self.logger.warning("未上市品种缓存保存失败")
                except Exception as e:
                    self.logger.error("保存未上市品种缓存失败: %s", e, exc_info=True)

            # 🆕 返回分类统计供外层使用
            return True, category_removed

        except Exception as e:
            self.logger.error("删除未上市品种失败: %s", e, exc_info=True)
            return False, {}

    # ==================== 高级业务接口（从core.py迁移） ====================

    def reload_and_classify(self) -> Dict[str, Any]:
        """
        重新加载品种列表并分类（完整业务逻辑，从core.py迁移）

        Returns:
            Dict {
                "success": bool,
                "total_count": int,
                "empty_categories": List[str],  # 为空的品种类别列表
                "classified": Dict  # 分类后的品种字典
            }
        """
        try:
            self.logger.info("开始更新品种列表...")

            # 调用load_from_api从API加载
            result = self.load_from_api()
            classified = result.get("classified", {})
            empty_categories = result.get("empty_categories", [])

            # 验证数据
            total_count = sum(len(stocks) for stocks in classified.values())
            if total_count == 0:
                self.logger.error("获取品种列表失败: 数据为空")

                # 推送下载事件（自己推送）
                if self.download_publisher:
                    self.download_publisher.push_download_event(
                        "stock_list", "error", 0, "获取的数据为空"
                    )
                if self.event_publisher:
                    self.event_publisher.push_log_event("获取品种列表失败: 数据为空", "ERROR")

                return {
                    "success": False,
                    "total_count": 0,
                    "empty_categories": [],
                    "classified": {},
                }

            # 成功 - 推送事件
            if self.download_publisher:
                self.download_publisher.push_download_event("stock_list", "success", total_count)

            if empty_categories:
                warning_msg = (
                    f"品种列表更新成功: {total_count} 个品种，"
                    f"但存在空类别: {', '.join(empty_categories)}"
                )
                self.logger.warning(warning_msg)
                if self.event_publisher:
                    self.event_publisher.push_log_event(warning_msg, "WARNING")
            else:
                self.logger.info("品种列表更新成功: %d 个品种", total_count)
                if self.event_publisher:
                    self.event_publisher.push_log_event(f"品种列表更新成功: {total_count} 个品种")

            return {
                "success": True,
                "total_count": total_count,
                "empty_categories": empty_categories,
                "classified": classified,
            }

        except Exception as e:
            # 最外层兜底异常处理
            self.logger.error("更新品种列表失败: %s", e, exc_info=True)

            # 推送错误事件
            if self.download_publisher:
                self.download_publisher.push_download_event(
                    "stock_list", "error", 0, f"错误: {str(e)}"
                )
            if self.event_publisher:
                self.event_publisher.push_log_event(f"更新品种列表失败: {e}", "ERROR")

            return {
                "success": False,
                "total_count": 0,
                "empty_categories": [],
                "classified": {},
            }

    def get_market_stocks(self, market_type: str) -> List[Dict[str, Any]]:
        """
        获取指定市场的品种列表（从core.py迁移）

        Args:
            market_type: 市场类型（如 "上证A股", "深证A股" 等）

        Returns:
            品种列表，每个品种包含 code, name, market
        """
        try:
            classified = self.load_from_cache()
            if classified is None:
                self.logger.warning("本地缓存不存在")
                return []
            return classified.get(market_type, [])
        except Exception as e:
            self.logger.error("获取 %s 品种列表失败: %s", market_type, e)
            return []

    def get_all_classified(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        获取所有市场的品种分类（从core.py迁移）

        Returns:
            所有市场的品种分类字典，每个品种包含 code, name, market
        """
        try:
            classified = self.load_from_cache()
            if classified is None:
                self.logger.warning("本地缓存不存在")
                return {}
            return classified
        except Exception as e:
            self.logger.error("获取所有品种分类失败: %s", e)
            return {}

    def extract_all_codes(self) -> List[str]:
        """
        从所有分类中提取品种代码（扁平化，从core.py迁移）

        自动处理两种格式：
        - 字符串列表: ["600000", "000001"]
        - 字典列表: [{"code": "600000", "name": "浦发银行"}, ...]

        Returns:
            所有品种代码的扁平列表
        """
        classified = self.get_all_classified()
        all_codes: List[str] = []

        for stocks in classified.values():
            if not stocks:
                continue

            # 判断格式并提取代码
            first_item = stocks[0]
            if isinstance(first_item, str):
                # 字符串列表格式
                all_codes.extend([code for code in stocks if isinstance(code, str) and code])
            elif isinstance(first_item, dict):
                # 字典列表格式
                all_codes.extend(
                    [
                        stock.get("code", "").strip()
                        for stock in stocks
                        if isinstance(stock, dict) and stock.get("code")
                    ]
                )

        return all_codes

    def extract_codes_by_market(self, market_types: Optional[List[str]] = None) -> List[str]:
        """
        从指定市场类型中提取品种代码（从core.py迁移）

        自动处理两种格式，并支持市场类型筛选。

        Args:
            market_types: 市场类型列表（默认全部）

        Returns:
            品种代码列表
        """
        if market_types is None:
            market_types = ["上证A股", "深证A股", "北证A股", "T+0基金", "可转债"]

        classified = self.get_all_classified()
        all_stocks: List[str] = []

        for market_type in market_types:
            stocks = classified.get(market_type, [])

            if not stocks:
                continue

            # 判断格式：字符串列表还是字典列表
            first_item = stocks[0] if stocks else None

            if isinstance(first_item, str):
                # 字符串列表
                stock_codes = [code for code in stocks if isinstance(code, str) and code]
            elif isinstance(first_item, dict):
                # 字典列表: {"code": "600000", "name": "浦发银行", "market": 1}
                stock_codes = [
                    stock.get("code", "").strip()
                    for stock in stocks
                    if isinstance(stock, dict) and stock.get("code")
                ]
            else:
                stock_codes = []

            all_stocks.extend(stock_codes)

        return all_stocks

    # ==================== 增量/减量更新功能 ====================

    def reload_with_incremental_update(self) -> Dict[str, Any]:
        """
        增量/减量更新品种列表

        Returns:
            Dict: {
                "success": bool,
                "new_data": Dict,  # 新的品种列表
                "added": List[str],  # 新增的品种代码
                "removed": List[str],  # 删除的品种代码
                "unchanged": int  # 未变化的品种数
            }
        """
        try:
            # 1. 加载旧缓存
            old_classified, _ = self.load_from_cache_with_validation()

            # 2. 从API获取最新数据
            self.logger.info("开始从API获取最新品种列表...")
            result = self.load_from_api()
            new_classified = result.get("classified", {})

            if not new_classified:
                self.logger.error("从API获取的品种列表为空")
                return {
                    "success": False,
                    "new_data": {},
                    "added": [],
                    "removed": [],
                    "unchanged": 0,
                }

            # 3. 对比差异
            diff = self._compare_symbol_lists(old_classified, new_classified)

            self.logger.info(
                "品种列表对比完成：新增 %d 个，删除 %d 个，未变 %d 个",
                len(diff["added"]),
                len(diff["removed"]),
                diff["unchanged"],
            )

            # 4. 推送差异事件
            if self.event_publisher and (diff["added"] or diff["removed"]):
                self.event_publisher.push_log_event(
                    f"品种列表更新：新增 {len(diff['added'])} 个，删除 {len(diff['removed'])} 个"
                )

            return {
                "success": True,
                "new_data": new_classified,
                "added": diff["added"],
                "removed": diff["removed"],
                "unchanged": diff["unchanged"],
            }

        except Exception as e:
            self.logger.error("增量更新品种列表失败: %s", e, exc_info=True)
            return {
                "success": False,
                "new_data": {},
                "added": [],
                "removed": [],
                "unchanged": 0,
            }

    def _compare_symbol_lists(self, old_data: Optional[Dict], new_data: Dict) -> Dict[str, Any]:
        """
        对比品种列表差异

        Args:
            old_data: 旧的品种列表
            new_data: 新的品种列表

        Returns:
            差异信息字典
        """
        # 提取所有代码
        old_codes = set(self._extract_codes_from_classified(old_data)) if old_data else set()
        new_codes = set(self._extract_codes_from_classified(new_data))

        added = list(new_codes - old_codes)
        removed = list(old_codes - new_codes)
        unchanged = len(old_codes & new_codes)

        return {"added": added, "removed": removed, "unchanged": unchanged}

    def _extract_codes_from_classified(self, classified: Dict) -> List[str]:
        """
        从分类数据中提取所有品种代码

        Args:
            classified: 分类后的品种字典

        Returns:
            品种代码列表
        """
        all_codes = []
        for stocks in classified.values():
            for stock in stocks:
                if isinstance(stock, dict):
                    code = stock.get("code")
                    if code:
                        all_codes.append(code)
                elif isinstance(stock, str):
                    all_codes.append(stock)
        return all_codes


# ==============================================================================
# 第3部分：数据获取主逻辑（原data_fetcher.py）
# ==============================================================================


# ==================== 导入声明 ====================
import asyncio
import logging
import os
import threading
import time
import queue
from datetime import date, datetime
from multiprocessing import Manager, Process, cpu_count
from typing import Any, Callable, Dict, List, Optional, Union

import pandas as pd

from backend.infrastructure.tdx_asyncio import AsyncTdxHq_API

# TaskDetailLogger已在本文件第1部分定义，无需导入
from .load_balancer import (
    server_pool_manager,
    NetworkTask,
    TaskMetrics,
    TaskType,
    ResourceProfile,
)

# ==================== 负载均衡任务类 ====================


class KlineDownloadTask(NetworkTask):
    """K线批量下载任务

    用于批量下载股票K线数据，支持多周期（日线、5分钟、1分钟）。
    """

    def __init__(self, name: str, task_count: int):
        """初始化K线下载任务

        Args:
            name: 任务名称
            task_count: 预计任务数量（品种数×周期数）
        """
        super().__init__(name)
        self.task_count = task_count
        # 更新预估连接数
        self.metrics.estimated_connections = min(task_count * 2, 640)

    def _define_metrics(self) -> TaskMetrics:
        return TaskMetrics(
            task_name="kline_batch_download",
            task_type=TaskType.NETWORK,
            resource_profile=ResourceProfile.MIXED,  # 网络+磁盘
            critical_metrics=[
                "network_speed",
                "disk_io_speed",
                "average_io_latency_ms",
                "concurrent_task_count",
            ],
            estimated_duration=300,  # 预计5分钟
            estimated_memory_mb=320,  # 640连接×0.5MB
            estimated_connections=640,  # 默认值，会在__init__中更新
        )

    def execute(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """执行K线下载（占位方法）

        实际下载由MultiProcessStockFetcher.download_incremental_kline执行。
        """
        # 这个方法不会被直接调用
        return {}


class IPODownloadTask(NetworkTask):
    """IPO日期批量下载任务

    用于批量下载股票IPO日期信息。

    特点：
    - 轻量级请求（每个请求只获取finance_info）
    - 单次请求，不需要多周期
    - 适合中等并发（避免过度并发）
    """

    def __init__(self, name: str, task_count: int):
        """初始化IPO下载任务

        Args:
            name: 任务名称
            task_count: 预计任务数量（品种数）
        """
        super().__init__(name)
        self.task_count = task_count
        # 🔥 关键优化：IPO请求轻量级，限制最大连接数
        # 避免过度并发导致服务器拒绝连接
        self.metrics.estimated_connections = min(task_count, 120)  # 从200降低到120

    def _define_metrics(self) -> TaskMetrics:
        return TaskMetrics(
            task_name="ipo_batch_download",
            task_type=TaskType.NETWORK,
            resource_profile=ResourceProfile.NETWORK_IO_INTENSIVE,
            critical_metrics=[
                "network_speed",
                "concurrent_task_count",
            ],
            estimated_duration=60,  # 预计1分钟
            estimated_memory_mb=30,  # 120连接×0.25MB（轻量级请求）
            estimated_connections=120,  # 降低默认值，避免过度并发
        )

    def execute(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """执行IPO下载（占位方法）

        实际下载由MultiProcessStockFetcher.download_ipo_dates执行。
        """
        # 这个方法不会被直接调用
        return {}


# ==================== 异步工作进程函数 ====================


async def download_worker_two_phase_async(
    worker_id,
    task_queue,
    result_queue,
    metrics_queue,  # 🆕 v3.6: 添加独立的监控指标队列
    progress_queue,
    regular_servers,
    standby_servers,
    broker_map,
    threshold,
    timeout,
    stop_event,
    pause_event,
    connections_per_worker=999999,  # 🔧 移除连接上限，让系统展现真实瓶颈
):
    """两段式异步Worker - 先用regular服务器，剩余任务用standby服务器

    Args:
        worker_id: Worker进程ID
        task_queue: 共享任务队列
        result_queue: 结果队列
        metrics_queue: 监控指标队列（v3.6新增）
        progress_queue: 进度队列
        regular_servers: 乱序服务器列表
        standby_servers: 热备服务器列表
        broker_map: 服务器到券商的映射
        threshold: 任务剩余阈值（切换到第二阶段的触发点）
        timeout: 连接超时时间
        stop_event: 停止事件
        pause_event: 暂停事件
        connections_per_worker: 每个worker的异步连接数（默认无上限）
    """
    # ✅ 配置子进程日志，接入LogHub统一路由
    logger = _configure_subprocess_logging(worker_id, task_type="kline_twophase")
    logger.info("两段式Worker %s 启动，PID：%s", worker_id, os.getpid())

    # 🆕 v3.6: 启动lag监控（使用独立的metrics_queue）
    # ✅ 修复：使用绝对导入，避免多进程中的导入失败
    from backend.infrastructure.data_module_vnpy.load_balancer import (
        LagMonitor,
        ConnectionLifecycleManager,
    )

    lag_monitor_task = asyncio.create_task(
        LagMonitor.monitor_and_report(
            metrics_queue=metrics_queue,  # 🆕 v3.6: 使用独立的监控队列
            worker_id=worker_id,
            stop_event=stop_event,
            interval_seconds=0.3,
        )
    )
    logger.info(f"[Worker-{worker_id}] ✅ 已启动lag监控（K线下载-两阶段模式，使用metrics_queue）")

    # 初始化任务详细日志记录器
    task_logger = None
    try:
        print("=" * 70)
        print(f"🔧 [Worker {worker_id}] 正在初始化任务详细日志记录器...")
        print("=" * 70)
        task_logger = TaskDetailLogger(worker_id=worker_id)
        print(f"✅ [Worker {worker_id}] 任务详细日志记录器初始化成功！")
        print("=" * 70)
        logger.info("[Worker %s] 任务详细日志记录器初始化成功", worker_id)
    except Exception as e:
        print("=" * 70)
        print(f"❌ [Worker {worker_id}] 任务详细日志记录器初始化失败！")
        print(f"   错误: {type(e).__name__}: {e}")
        print("=" * 70)
        logger.error("[Worker %s] 任务详细日志记录器初始化失败: %s", worker_id, e, exc_info=True)
        import traceback

        traceback.print_exc()

    # ========== 🔧 【优化】为每个worker分配独立的服务器池（包括备用） ==========
    # 🔥 关键修复：使用随机起始位置，确保充分利用全部591个服务器
    # 原问题：线性分配导致只使用前300个服务器，后291个从未被使用
    import random

    # 随机起始位置（确保不超出范围）
    max_start = max(0, len(regular_servers) - connections_per_worker * 3)
    start_idx = random.randint(0, max_start) if max_start > 0 else 0

    # 准备3倍备用服务器（从随机位置开始轮询）
    my_ipv4_servers = []
    for i in range(connections_per_worker * 3):
        server_idx = (start_idx + i) % len(regular_servers)
        my_ipv4_servers.append(regular_servers[server_idx])

    logger.info(
        "[Phase1] Worker %s 分配Phase1服务器池: 主用%s个 + 备用%s个 (总%s个可用服务器)",
        worker_id,
        connections_per_worker,
        len(my_ipv4_servers) - connections_per_worker,
        len(regular_servers),
    )

    # ========== 第一阶段：使用前半部分服务器 ==========
    logger.info("[Phase1] Worker %s 开始Phase1，使用前半部分服务器（1.0s超时）", worker_id)

    # 🆕 v3.7: 创建Phase1连接管理器
    conn_manager_p1 = ConnectionLifecycleManager(hash(f"{worker_id}-P1") % 2**31, logger)

    phase1_connections = {}
    phase1_servers = []
    used_servers = set()  # 追踪已使用的服务器

    try:
        # 🆕 v3.7: 使用ConnectionLifecycleManager批量创建Phase1连接
        phase1_servers_to_create = my_ipv4_servers[:connections_per_worker]
        phase1_connection_list = await conn_manager_p1.create_connections(
            servers=phase1_servers_to_create, timeout=timeout, health_check=False  # Phase1优先速度
        )

        # 转换为字典并更新已使用服务器集合
        for i, client in enumerate(phase1_connection_list):
            server = phase1_servers_to_create[i]
            phase1_connections[server] = client
            phase1_servers.append(server)
            used_servers.add(server)

        logger.info("[Phase1] Worker %s 建立 %s 个Phase1连接", worker_id, len(phase1_connections))

        if not phase1_connections:
            logger.error("[Phase1] Worker %s 无可用连接，退出", worker_id)
            return

        # 第一阶段下载逻辑（0.2s超时+换服务器机制）
        async def phase1_download_loop(conn_id, client, server):
            processed = 0
            failed = 0
            current_client = client
            _current_server = server  # 用于追踪当前服务器

            while not stop_event.is_set():
                # 检查任务队列大小
                try:
                    queue_size = task_queue.qsize()
                    if queue_size <= threshold:
                        logger.info(
                            "[Phase1] Worker %s 连接%s 达到阈值（剩余%s），停止",
                            worker_id,
                            conn_id,
                            queue_size,
                        )
                        break
                except Exception:
                    pass  # qsize() 可能在某些平台不可用

                # 等待暂停
                while not pause_event.is_set():
                    if stop_event.is_set():
                        break
                    await asyncio.sleep(0.1)

                if stop_event.is_set():
                    break

                # 获取任务
                try:
                    task = await asyncio.to_thread(task_queue.get, timeout=0.5)
                except queue.Empty:
                    break
                except Exception as e:
                    logger.debug("[Phase1] Worker %s 获取任务失败：%s", worker_id, e)
                    break

                symbol, interval, start_date = task
                task_start_time = time.time()  # 记录任务开始时间

                try:
                    # 🔧 添加1.0s请求超时（给服务器足够响应时间，异常时也会切换服务器）
                    data = await asyncio.wait_for(
                        _download_single_kline_async(current_client, symbol, interval, start_date),
                        timeout=1.0,
                    )

                    if data is not None and not data.empty:
                        await asyncio.to_thread(
                            result_queue.put, (f"{symbol}_{interval}", data.to_dict("records"))
                        )
                        await asyncio.to_thread(progress_queue.put, (symbol, interval, "success"))
                        processed += 1

                        # 📝 记录成功任务
                        if task_logger:
                            task_logger.log_task(
                                symbol=symbol,
                                interval=interval,
                                server=_current_server,
                                status="success",
                                data_count=len(data),
                                elapsed_time=time.time() - task_start_time,
                                worker_id=worker_id,
                                connection_id=conn_id,
                                phase="Phase1",
                            )
                    else:
                        # 失败任务放回队列
                        await asyncio.to_thread(task_queue.put, (symbol, interval, start_date))
                        await asyncio.to_thread(progress_queue.put, (symbol, interval, "retry"))
                        failed += 1

                        # 📝 记录失败任务（数据为空）
                        if task_logger:
                            task_logger.log_task(
                                symbol=symbol,
                                interval=interval,
                                server=_current_server,
                                status="failed",
                                error_msg="返回数据为空",
                                data_count=0,
                                elapsed_time=time.time() - task_start_time,
                                worker_id=worker_id,
                                connection_id=conn_id,
                                phase="Phase1",
                            )

                except asyncio.TimeoutError:
                    # 超时：断开连接，换服务器
                    logger.warning(
                        "[Phase1] Worker %s 连接%s 超时1.0s，换服务器", worker_id, conn_id
                    )
                    await asyncio.to_thread(task_queue.put, task)
                    await asyncio.to_thread(progress_queue.put, (symbol, interval, "timeout"))

                    # 📝 记录超时任务
                    if task_logger:
                        task_logger.log_task(
                            symbol=symbol,
                            interval=interval,
                            server=_current_server,
                            status="timeout",
                            error_msg="请求超时1.0s",
                            data_count=0,
                            elapsed_time=time.time() - task_start_time,
                            worker_id=worker_id,
                            connection_id=conn_id,
                            phase="Phase1",
                        )

                    try:
                        if current_client and not current_client.closed:
                            await current_client.close()
                    except Exception:
                        pass

                    # 从备用池取新服务器
                    new_server = None
                    for backup_server in my_ipv4_servers:
                        if backup_server not in used_servers:
                            new_server = backup_server
                            used_servers.add(backup_server)
                            break

                    if new_server:
                        try:
                            current_client = await AsyncTdxHq_API.factory(
                                server=new_server,
                                timeout=timeout,
                                heartbeat=False,
                                raise_exception=False,
                            )
                            if current_client:
                                _current_server = new_server
                                logger.info(
                                    "[Phase1] Worker %s 连接%s 换用新服务器 %s",
                                    worker_id,
                                    conn_id,
                                    new_server[0],
                                )
                            else:
                                logger.error(
                                    "[Phase1] Worker %s 连接%s 连接新服务器失败", worker_id, conn_id
                                )
                                break
                        except Exception as e:
                            logger.error(
                                "[Phase1] Worker %s 连接%s 连接新服务器异常: %s",
                                worker_id,
                                conn_id,
                                e,
                            )
                            break
                    else:
                        logger.warning(
                            "[Phase1] Worker %s 连接%s 无可用备用服务器", worker_id, conn_id
                        )
                        break

                except Exception as e:
                    logger.debug(
                        "[Phase1] Worker %s 下载失败 %s_%s: %s", worker_id, symbol, interval, e
                    )
                    # 异常任务放回队列
                    await asyncio.to_thread(task_queue.put, (symbol, interval, start_date))
                    await asyncio.to_thread(progress_queue.put, (symbol, interval, "retry"))
                    failed += 1

                    # 📝 记录异常任务
                    if task_logger:
                        task_logger.log_task(
                            symbol=symbol,
                            interval=interval,
                            server=_current_server,
                            status="exception",
                            error_msg=str(e),
                            data_count=0,
                            elapsed_time=time.time() - task_start_time,
                            worker_id=worker_id,
                            connection_id=conn_id,
                            phase="Phase1",
                        )

                    # 🔧 修复：socket异常也要切换服务器！
                    # 关闭旧连接
                    try:
                        if current_client and not current_client.closed:
                            await current_client.close()
                    except Exception:
                        pass

                    # 从备用池取新服务器
                    new_server = None
                    for backup_server in my_ipv4_servers:
                        if backup_server not in used_servers:
                            new_server = backup_server
                            used_servers.add(backup_server)
                            break

                    if new_server:
                        try:
                            current_client = await AsyncTdxHq_API.factory(
                                server=new_server,
                                timeout=timeout,
                                heartbeat=False,
                                raise_exception=False,
                            )
                            if current_client:
                                _current_server = new_server
                                logger.info(
                                    "[Phase1] Worker %s 连接%s socket异常后换用新服务器 %s",
                                    worker_id,
                                    conn_id,
                                    new_server[0],
                                )
                            else:
                                logger.error(
                                    "[Phase1] Worker %s 连接%s 连接新服务器失败", worker_id, conn_id
                                )
                                break
                        except Exception as conn_e:
                            logger.error(
                                "[Phase1] Worker %s 连接%s 连接新服务器异常: %s",
                                worker_id,
                                conn_id,
                                conn_e,
                            )
                            break
                    else:
                        logger.warning(
                            "[Phase1] Worker %s 连接%s 无可用备用服务器", worker_id, conn_id
                        )
                        break

            # 关闭当前连接
            try:
                if current_client and not current_client.closed:
                    await current_client.close()
            except Exception:
                pass

            return processed, failed

        # 并发执行第一阶段
        results = await asyncio.gather(
            *[
                phase1_download_loop(idx, phase1_connections[server], server)
                for idx, server in enumerate(phase1_servers)
            ],
            return_exceptions=True,
        )

        total_phase1 = sum(r[0] for r in results if isinstance(r, tuple))
        logger.info("[Phase1] Worker %s 完成，下载：%s", worker_id, total_phase1)

    except Exception as e:
        logger.error("[Phase1] Worker %s 异常: %s", worker_id, e)
    finally:
        # 🆕 v3.7: 使用ConnectionLifecycleManager确保所有Phase1连接关闭
        await conn_manager_p1.close_all_connections(timeout=2.0)
        logger.debug("[Phase1] Worker %s 所有Phase1连接已关闭", worker_id)

    # ========== 等待Phase1完成 ==========
    logger.info("[Phase1-Phase2] Worker %s 等待Phase1协程完成...", worker_id)

    # ========== Phase2：使用后半部分服务器 ==========
    logger.info("[Phase2] Worker %s 开始Phase2，使用后半部分服务器（1.0s超时）", worker_id)

    # 🆕 v3.7: 创建Phase2连接管理器
    conn_manager_p2 = ConnectionLifecycleManager(hash(f"{worker_id}-P2") % 2**31, logger)

    # 为每个worker分配Phase2服务器（包括备用）
    worker_ipv6_start = worker_id * connections_per_worker
    my_ipv6_servers = []
    for i in range(connections_per_worker * 3):  # 3倍备用
        server_idx = (worker_ipv6_start + i) % len(standby_servers)
        my_ipv6_servers.append(standby_servers[server_idx])

    logger.info(
        "[Phase2] Worker %s 分配Phase2服务器池: 主用%s个 + 备用%s个 (总%s个可用服务器)",
        worker_id,
        connections_per_worker,
        len(my_ipv6_servers) - connections_per_worker,
        len(standby_servers),
    )

    # 🆕 v3.7: 使用ConnectionLifecycleManager批量创建Phase2连接
    phase2_servers_to_create = my_ipv6_servers[:connections_per_worker]
    phase2_connection_list = await conn_manager_p2.create_connections(
        servers=phase2_servers_to_create, timeout=timeout, health_check=False  # Phase2优先速度
    )

    # 转换为字典并更新已使用服务器集合
    phase2_connections = {}
    phase2_servers = []
    ipv6_used_servers = set()
    for i, client in enumerate(phase2_connection_list):
        server = phase2_servers_to_create[i]
        phase2_connections[server] = client
        phase2_servers.append(server)
        ipv6_used_servers.add(server)

    logger.info("[Phase2] Worker %s 建立 %s 个Phase2连接", worker_id, len(phase2_connections))

    # ========== 第二阶段：执行Phase2下载 ==========
    if not phase2_connections:
        logger.error("[Phase2] Worker %s 无可用Phase2连接，跳过Phase2", worker_id)
        return

    try:
        # 第二阶段下载逻辑（1.0s超时+换服务器机制）
        async def phase2_download_loop(conn_id, client, server):
            processed = 0
            failed = 0
            current_client = client
            _current_server = server  # 用于追踪当前服务器

            while not stop_event.is_set():
                # 等待暂停
                while not pause_event.is_set():
                    if stop_event.is_set():
                        break
                    await asyncio.sleep(0.1)

                if stop_event.is_set():
                    break

                # 获取任务
                try:
                    task = await asyncio.to_thread(task_queue.get, timeout=0.5)
                except queue.Empty:
                    logger.debug("[Phase2] Worker %s 连接%s 队列为空", worker_id, conn_id)
                    break
                except Exception as e:
                    logger.debug("[Phase2] Worker %s 获取任务失败: %s", worker_id, e)
                    break

                symbol, interval, start_date = task
                task_start_time = time.time()  # 记录任务开始时间

                try:
                    # 🔧 添加1.0s请求超时
                    data = await asyncio.wait_for(
                        _download_single_kline_async(current_client, symbol, interval, start_date),
                        timeout=1.0,
                    )

                    if data is not None and not data.empty:
                        await asyncio.to_thread(
                            result_queue.put, (f"{symbol}_{interval}", data.to_dict("records"))
                        )
                        await asyncio.to_thread(progress_queue.put, (symbol, interval, "success"))
                        processed += 1

                        # 📝 记录成功任务
                        if task_logger:
                            task_logger.log_task(
                                symbol=symbol,
                                interval=interval,
                                server=_current_server,
                                status="success",
                                data_count=len(data),
                                elapsed_time=time.time() - task_start_time,
                                worker_id=worker_id,
                                connection_id=conn_id,
                                phase="Phase2",
                            )
                    else:
                        # Phase2失败也放回队列（无限重试）
                        await asyncio.to_thread(task_queue.put, (symbol, interval, start_date))
                        await asyncio.to_thread(progress_queue.put, (symbol, interval, "retry"))
                        failed += 1

                        # 📝 记录失败任务（数据为空）
                        if task_logger:
                            task_logger.log_task(
                                symbol=symbol,
                                interval=interval,
                                server=_current_server,
                                status="failed",
                                error_msg="返回数据为空",
                                data_count=0,
                                elapsed_time=time.time() - task_start_time,
                                worker_id=worker_id,
                                connection_id=conn_id,
                                phase="Phase2",
                            )

                except asyncio.TimeoutError:
                    # 超时：断开连接，换服务器
                    logger.warning(
                        "[Phase2] Worker %s 连接%s 超时1.0s，换服务器", worker_id, conn_id
                    )
                    await asyncio.to_thread(task_queue.put, task)
                    await asyncio.to_thread(progress_queue.put, (symbol, interval, "timeout"))

                    # 📝 记录超时任务
                    if task_logger:
                        task_logger.log_task(
                            symbol=symbol,
                            interval=interval,
                            server=_current_server,
                            status="timeout",
                            error_msg="请求超时1.0s",
                            data_count=0,
                            elapsed_time=time.time() - task_start_time,
                            worker_id=worker_id,
                            connection_id=conn_id,
                            phase="Phase2",
                        )

                    try:
                        if current_client and not current_client.closed:
                            await current_client.close()
                    except Exception:
                        pass

                    # 从IPv6备用池取新服务器
                    new_server = None
                    for backup_server in my_ipv6_servers:
                        if backup_server not in ipv6_used_servers:
                            new_server = backup_server
                            ipv6_used_servers.add(backup_server)
                            break

                    if new_server:
                        try:
                            current_client = await AsyncTdxHq_API.factory(
                                server=new_server,
                                timeout=timeout,
                                heartbeat=False,
                                raise_exception=False,
                            )
                            if current_client:
                                _current_server = new_server
                                logger.info(
                                    "[Phase2] Worker %s 连接%s 换用新IPv6服务器 %s",
                                    worker_id,
                                    conn_id,
                                    new_server[0],
                                )
                            else:
                                logger.error(
                                    "[Phase2] Worker %s 连接%s 连接新服务器失败", worker_id, conn_id
                                )
                                break
                        except Exception as e:
                            logger.error(
                                "[Phase2] Worker %s 连接%s 连接新服务器异常: %s",
                                worker_id,
                                conn_id,
                                e,
                            )
                            break
                    else:
                        logger.warning(
                            "[Phase2] Worker %s 连接%s 无可用IPv6备用", worker_id, conn_id
                        )
                        break

                except Exception as e:
                    logger.debug(
                        "[Phase2] Worker %s 下载失败 %s_%s: %s", worker_id, symbol, interval, e
                    )
                    # 异常任务放回队列
                    await asyncio.to_thread(task_queue.put, (symbol, interval, start_date))
                    await asyncio.to_thread(progress_queue.put, (symbol, interval, "retry"))
                    failed += 1

                    # 📝 记录异常任务
                    if task_logger:
                        task_logger.log_task(
                            symbol=symbol,
                            interval=interval,
                            server=_current_server,
                            status="exception",
                            error_msg=str(e),
                            data_count=0,
                            elapsed_time=time.time() - task_start_time,
                            worker_id=worker_id,
                            connection_id=conn_id,
                            phase="Phase2",
                        )

                    # 🔧 修复：socket异常也要切换服务器！
                    # 关闭旧连接
                    try:
                        if current_client and not current_client.closed:
                            await current_client.close()
                    except Exception:
                        pass

                    # 从IPv6备用池取新服务器
                    new_server = None
                    for backup_server in my_ipv6_servers:
                        if backup_server not in ipv6_used_servers:
                            new_server = backup_server
                            ipv6_used_servers.add(backup_server)
                            break

                    if new_server:
                        try:
                            current_client = await AsyncTdxHq_API.factory(
                                server=new_server,
                                timeout=timeout,
                                heartbeat=False,
                                raise_exception=False,
                            )
                            if current_client:
                                _current_server = new_server
                                logger.info(
                                    "[Phase2] Worker %s 连接%s socket异常后换用新IPv6服务器 %s",
                                    worker_id,
                                    conn_id,
                                    new_server[0],
                                )
                            else:
                                logger.error(
                                    "[Phase2] Worker %s 连接%s 连接新服务器失败", worker_id, conn_id
                                )
                                break
                        except Exception as conn_e:
                            logger.error(
                                "[Phase2] Worker %s 连接%s 连接新服务器异常: %s",
                                worker_id,
                                conn_id,
                                conn_e,
                            )
                            break
                    else:
                        logger.warning(
                            "[Phase2] Worker %s 连接%s 无可用IPv6备用", worker_id, conn_id
                        )
                        break

            # 关闭当前连接
            try:
                if current_client and not current_client.closed:
                    await current_client.close()
            except Exception:
                pass

            return processed, failed

        # 并发执行第二阶段
        results = await asyncio.gather(
            *[
                phase2_download_loop(idx, phase2_connections[server], server)
                for idx, server in enumerate(phase2_servers)
            ],
            return_exceptions=True,
        )

        total_phase2 = sum(r[0] for r in results if isinstance(r, tuple))
        logger.info("[Phase2] Worker %s 完成，下载: %s", worker_id, total_phase2)

    except Exception as e:
        logger.error("[Phase2] Worker %s 异常: %s", worker_id, e)
    finally:
        # Phase2的连接已在各自的download_loop中关闭
        logger.debug("[Phase2] Worker %s 所有IPv6连接已关闭", worker_id)

        # 🆕 v3.4: 停止lag监控
        await LagMonitor.cancel_monitor(lag_monitor_task)

        # 关闭任务详细日志记录器
        if task_logger:
            task_logger.close()
            logger.info("[Worker %s] 任务详细日志已保存", worker_id)


def _run_two_phase_worker(*args):
    """在进程中运行两段式异步事件循环的辅助函数

    v3.6改进：支持传递metrics_queue
    """
    import warnings

    warnings.filterwarnings("ignore", category=ResourceWarning, message=".*socket.*")
    asyncio.run(download_worker_two_phase_async(*args))


async def download_worker_async(
    worker_id,
    task_queue,
    result_queue,
    metrics_queue,  # 🆕 v3.6: 添加独立的监控指标队列
    progress_queue,
    server_list,
    server_index,
    timeout,
    _retry_times,
    stop_event,
    pause_event,
    connections_per_worker=999999,  # 🔧 移除连接上限，让系统展现真实瓶颈
):
    """异步Worker - 每个进程维护多个 tdx_asyncio 连接

    Args:
        worker_id: Worker进程ID
        task_queue: 共享任务队列
        result_queue: 结果队列
        metrics_queue: 监控指标队列（v3.6新增）
        progress_queue: 进度队列
        server_list: 共享的可用服务器列表
        server_index: 共享的服务器索引（用于轮询）
        timeout: 连接超时时间
        retry_times: 重试次数（暂未使用）
        stop_event: 停止事件
        pause_event: 暂停事件
        connections_per_worker: 每个worker的异步连接数（默认无上限）
    """
    # ✅ 配置子进程日志，接入LogHub统一路由
    logger = _configure_subprocess_logging(worker_id, task_type="kline")
    logger.info(
        f"异步Worker {worker_id} 启动，PID: {os.getpid()}，连接数: {connections_per_worker}"
    )

    # 🆕 v3.6: 启动lag监控（使用独立的metrics_queue）
    # ✅ 修复：使用绝对导入，避免多进程中的导入失败
    from backend.infrastructure.data_module_vnpy.load_balancer import (
        LagMonitor,
        ConnectionLifecycleManager,
    )

    lag_monitor_task = asyncio.create_task(
        LagMonitor.monitor_and_report(
            metrics_queue=metrics_queue,  # 🆕 v3.6: 使用独立的监控队列
            worker_id=worker_id,
            stop_event=stop_event,
            interval_seconds=0.3,
        )
    )
    logger.info(f"[Worker-{worker_id}] ✅ 已启动lag监控（K线下载-标准模式，使用metrics_queue）")

    # 🆕 v3.7: 创建连接生命周期管理器
    conn_manager = ConnectionLifecycleManager(worker_id, logger)

    if not server_list:
        logger.error("无可用服务器")
        return

    # 创建多个 tdx_asyncio 连接 - 使用字典管理（服务器地址为键）
    # 关键原则：严格保证每个服务器只有1个连接（跨所有worker）
    connections = {}  # 字典：{(ip, port): client}
    server_list_local = []  # 本Worker的服务器列表（用于轮询）

    # 检查：确保不会对同一服务器建立多个连接
    # server_index 是全局共享计数器，所有worker共用
    # 如果 server_index 达到或超过服务器总数，说明服务器会被重复使用
    max_safe_connections = len(server_list)
    logger.info(
        f"Worker {worker_id}: 期望 {connections_per_worker} 个连接，"
        f"可用服务器 {len(server_list)} 个"
    )

    try:
        # 🔥 第一步：通过全局server_index获取本worker的服务器列表
        # 保持原有的全局协调机制，确保每个服务器只被一个worker使用
        for i in range(connections_per_worker):
            # 原子操作：获取并递增全局服务器索引
            current_idx = server_index.value

            # 关键检查：如果索引已经达到服务器总数，停止创建连接
            if current_idx >= max_safe_connections:
                logger.warning(
                    f"Worker {worker_id}: 已达到服务器上限（{max_safe_connections}个），"
                    f"停止创建更多连接（当前{i}个）"
                )
                break

            # 递增索引（原子操作）
            server_index.value += 1
            idx = current_idx % len(server_list)
            server = server_list[idx]
            server_list_local.append(server)
            logger.debug(
                f"Worker {worker_id} 分配服务器 → {server[0]}:{server[1]} "
                f"（全局索引{current_idx}，本Worker第{len(server_list_local)}个）"
            )

        if not server_list_local:
            logger.error(f"Worker {worker_id} 未能分配到任何服务器")
            return

        logger.info(f"Worker {worker_id} 已分配 {len(server_list_local)} 个服务器（全局协调）")

        # 🆕 v3.7：第二步：使用ConnectionLifecycleManager批量创建连接
        # 不做健康检查（保持原有逻辑，优先速度）
        connection_list = await conn_manager.create_connections(
            servers=server_list_local,
            timeout=timeout,
            health_check=False,  # K线下载优先速度，不做健康检查
        )

        # 转换为字典（兼容现有代码）
        connections = {server_list_local[i]: client for i, client in enumerate(connection_list)}

        logger.info(
            "Worker %s 成功建立 %s 个连接（每个连接使用不同服务器）", worker_id, len(connections)
        )

        if not connections:
            logger.error("Worker %s 无可用连接，退出", worker_id)
            return

        # 为每个连接创建下载协程
        async def download_loop(conn_id, client, _server):
            processed = 0
            failed = 0

            while not stop_event.is_set():
                # 等待暂停事件
                while not pause_event.is_set():
                    if stop_event.is_set():
                        break
                    await asyncio.sleep(0.1)

                if stop_event.is_set():
                    break

                # 从队列获取任务
                try:
                    task = await asyncio.to_thread(task_queue.get, timeout=0.5)
                except queue.Empty:
                    logger.debug("Worker %s 连接 %s 队列为空", worker_id, conn_id)
                    break
                except Exception as e:
                    logger.debug("Worker %s 连接 %s 获取任务失败: %s", worker_id, conn_id, e)
                    break

                symbol, interval, start_date = task

                try:
                    # 纯异步下载（使用 tdx_asyncio）
                    data = await _download_single_kline_async(client, symbol, interval, start_date)

                    if data is not None and not data.empty:
                        await asyncio.to_thread(
                            result_queue.put, (f"{symbol}_{interval}", data.to_dict("records"))
                        )
                        await asyncio.to_thread(progress_queue.put, (symbol, interval, "success"))
                        processed += 1
                    else:
                        await asyncio.to_thread(progress_queue.put, (symbol, interval, "failed"))
                        failed += 1

                except Exception as e:
                    logger.debug(
                        f"Worker {worker_id} 连接 {conn_id} 下载 {symbol}_{interval} 失败: {e}"
                    )
                    await asyncio.to_thread(progress_queue.put, (symbol, interval, "failed"))
                    failed += 1

            logger.info(
                f"Worker {worker_id} 连接 {conn_id} 完成, 成功: {processed}, 失败: {failed}"
            )
            return processed, failed

        # N个协程并发工作（字典方案：遍历服务器列表和字典）
        results = await asyncio.gather(
            *[
                download_loop(idx, connections[server], server)
                for idx, server in enumerate(server_list_local)
            ],
            return_exceptions=True,
        )

        # 统计总数
        total_processed = sum(r[0] for r in results if isinstance(r, tuple))
        total_failed = sum(r[1] for r in results if isinstance(r, tuple))
        logger.info(f"Worker {worker_id} 总计完成, 成功: {total_processed}, 失败: {total_failed}")

    finally:
        # 🆕 v3.7：使用ConnectionLifecycleManager关闭所有连接
        await conn_manager.close_all_connections(timeout=3.0)

        # 🆕 v3.4: 停止lag监控
        await LagMonitor.cancel_monitor(lag_monitor_task)


def _run_async_worker(*args):
    """在进程中运行异步事件循环的辅助函数

    v3.6改进：支持传递metrics_queue
    """
    import warnings

    # 🔧 抑制 socket.send() 相关的 ResourceWarning
    # 这些警告通常在连接已断开时尝试关闭连接时出现，不影响功能
    warnings.filterwarnings("ignore", category=ResourceWarning, message=".*socket.*")

    asyncio.run(download_worker_async(*args))


# ==================== IPO下载Worker ====================


def _run_ipo_worker(*args):
    """IPO下载worker进程包装函数"""
    import warnings

    warnings.filterwarnings("ignore", category=ResourceWarning, message=".*socket.*")
    asyncio.run(_ipo_worker_async(*args))


def _run_finance_two_phase_worker(
    worker_id,
    task_queue,
    result_queue,
    metrics_queue,
    progress_queue,
    regular_servers,
    standby_servers,
    timeout,
    stop_event,
    pause_event,
    connections_per_worker,
    db_path,
):
    """财务信息2段式下载worker进程包装函数

    子进程只负责下载，不直接写SQLite（避免数据库锁冲突）
    """
    import warnings

    warnings.filterwarnings("ignore", category=ResourceWarning, message=".*socket.*")

    # 子进程不创建IPODateCache，只下载数据
    # 数据由主进程统一写入SQLite
    asyncio.run(
        download_worker_finance_two_phase_async(
            worker_id,
            task_queue,
            result_queue,
            metrics_queue,
            progress_queue,
            regular_servers,
            standby_servers,
            timeout,
            stop_event,
            pause_event,
            connections_per_worker,
            ipo_cache=None,  # 子进程不使用ipo_cache
        )
    )


async def _ipo_worker_async(
    worker_id,
    task_queue,
    result_queue,
    metrics_queue,
    progress_queue,
    server_list,
    timeout,
    stop_event,
    pause_event,
    connections_per_worker,
):
    """IPO下载异步worker（统一架构版本）

    复用K线下载的worker架构，但针对IPO下载优化：
    - 单次请求（不需要多周期）
    - 结果为ipo_date或unlisted标记
    - 更宽松的延时策略
    """
    # ✅ 配置子进程日志，接入LogHub统一路由
    worker_logger = _configure_subprocess_logging(worker_id, task_type="ipo")
    worker_logger.info(f"IPO Worker {worker_id} 启动")

    # 启动lag监控
    # ✅ 修复：使用绝对导入，避免多进程中的导入失败
    from backend.infrastructure.data_module_vnpy.load_balancer import (
        LagMonitor,
        ConnectionLifecycleManager,
    )

    lag_monitor_task = asyncio.create_task(
        LagMonitor.monitor_and_report(
            metrics_queue=metrics_queue,
            worker_id=worker_id,
            stop_event=stop_event,
            interval_seconds=0.3,
        )
    )

    # 创建连接生命周期管理器
    conn_manager = ConnectionLifecycleManager(worker_id, worker_logger)

    try:
        # 获取服务器并创建连接
        server_list_local = list(server_list)[:connections_per_worker]

        if not server_list_local:
            worker_logger.error(f"Worker {worker_id} 无可用服务器")
            return

        # 使用ConnectionLifecycleManager创建连接（带健康检查）
        connection_list = await conn_manager.create_connections(
            servers=server_list_local, timeout=timeout, health_check=True, health_check_timeout=2.0
        )

        # 将连接列表转换为字典（为兼容现有代码）
        # 注意：ConnectionLifecycleManager已跟踪所有创建的连接
        connections = {server_list_local[i]: client for i, client in enumerate(connection_list)}

        if not connections:
            worker_logger.error(f"Worker {worker_id} 无可用连接")
            return

        # 为每个连接创建下载协程
        async def download_loop(conn_id, client):
            processed = 0

            while not stop_event.is_set():
                # 检查暂停
                while not pause_event.is_set():
                    if stop_event.is_set():
                        break
                    await asyncio.sleep(0.1)

                if stop_event.is_set():
                    break

                # 获取任务
                try:
                    task = await asyncio.to_thread(task_queue.get, timeout=0.5)
                except queue.Empty:
                    break

                task_type, symbol, market = task

                if task_type != "ipo":
                    continue

                try:
                    # 下载IPO数据
                    ipo_date, industry, finance_info = await _download_single_ipo_async(
                        client, symbol, market
                    )

                    if ipo_date is not None:
                        # 已上市
                        result_data = {"status": "listed", "ipo_date": ipo_date}
                        await asyncio.to_thread(result_queue.put, (symbol, result_data))
                        await asyncio.to_thread(progress_queue.put, (symbol, "success"))
                    elif industry > 0:
                        # 未上市但有行业数据
                        result_data = {
                            "status": "unlisted",
                            "industry": industry,
                            "finance_info": finance_info,
                        }
                        await asyncio.to_thread(result_queue.put, (symbol, result_data))
                        await asyncio.to_thread(progress_queue.put, (symbol, "unlisted"))
                    else:
                        # 数据异常，重试
                        await asyncio.to_thread(task_queue.put, task)
                        await asyncio.to_thread(progress_queue.put, (symbol, "retry"))

                    processed += 1

                    # 动态延时（IPO下载可以更快）
                    try:
                        queue_size = task_queue.qsize()
                        if queue_size <= 50:
                            await asyncio.sleep(0.05)
                        elif queue_size <= 200:
                            await asyncio.sleep(0.02)
                        # 大量任务时不延时
                    except Exception:
                        await asyncio.sleep(0.02)

                except Exception as e:
                    worker_logger.debug(f"Worker {worker_id} 下载 {symbol} 失败: {e}")
                    await asyncio.to_thread(task_queue.put, task)
                    await asyncio.to_thread(progress_queue.put, (symbol, "retry"))

            worker_logger.debug(f"Worker {worker_id} 连接 {conn_id} 完成，处理 {processed} 个任务")

        # 启动所有下载协程
        download_tasks = [download_loop(i, client) for i, client in enumerate(connections.values())]
        await asyncio.gather(*download_tasks, return_exceptions=True)

    finally:
        # 使用ConnectionLifecycleManager关闭所有连接
        await conn_manager.close_all_connections(timeout=3.0)

        lag_monitor_task.cancel()
        try:
            await lag_monitor_task
        except asyncio.CancelledError:
            pass


# ==================== K线下载Worker ====================


async def _download_single_kline_async(
    client: AsyncTdxHq_API, symbol: str, interval: str, start_date: Union[str, date]
) -> Optional[pd.DataFrame]:
    """下载单个品种的K线数据（异步版本，使用 tdx_asyncio）"""
    try:
        # 参数验证和转换
        if isinstance(start_date, str):
            start_date = datetime.strptime(start_date, "%Y-%m-%d").date()

        days_diff = (date.today() - start_date).days

        # 频率映射（tdx_asyncio 使用 category 参数）
        category_map = {"1d": 9, "5m": 5, "1m": 8}  # 9=日K, 5=5分钟, 8=1分钟
        category = category_map.get(interval, 9)

        # 计算下载数量
        offset_multipliers = {"1d": 1.5, "5m": 50, "1m": 250}
        multiplier = offset_multipliers.get(interval, 1.5)
        count = min(int(days_diff * multiplier), 800)

        # 市场代码判断
        if symbol.startswith("6"):
            market = 1  # 上海
        elif symbol.startswith("9") and len(symbol) == 6:
            market = 2  # 北交所
        else:
            market = 0  # 深圳

        # 调用 tdx_asyncio API
        try:
            # 📊 添加数据请求响应时间统计
            request_start = time.time()
            raw_data = await client.get_security_bars(
                category=category, market=market, code=symbol, start=0, count=count
            )
            request_time = time.time() - request_start

            # 记录请求响应时间（用于性能分析）
            logger = logging.getLogger(__name__)
            if request_time > 1.0:
                logger.warning(f"K线请求响应慢 {symbol} {interval}: {request_time*1000:.0f}ms")
            elif request_time < 0.1:
                logger.info(f"K线请求响应快 {symbol} {interval}: {request_time*1000:.0f}ms")
            else:
                logger.info(f"K线请求响应 {symbol} {interval}: {request_time*1000:.0f}ms")

            if not raw_data:
                return None
        except Exception as e:
            logging.getLogger(__name__).error(f"API调用失败 {symbol} {interval}: {e}")
            return None

        # 数据处理（tdx_asyncio 已自动处理日期格式）
        data = pd.DataFrame(raw_data)

        if data.empty or "datetime" not in data.columns:
            return None

        # 设置索引
        data["datetime"] = pd.to_datetime(data["datetime"], errors="coerce")
        data = data.dropna(subset=["datetime"])

        if data.empty:
            return None

        data = data.set_index("datetime", drop=False)

        # 列名标准化
        column_mapping = {"vol": "volume", "amount": "turnover"}
        data = data.rename(columns=column_mapping)

        # 添加元数据
        data["symbol"] = symbol
        data["interval"] = interval

        # 数值类型转换
        for col in ["open", "high", "low", "close", "volume"]:
            if col in data.columns:
                data[col] = pd.to_numeric(data[col], errors="coerce")

        # 日期过滤
        if pd.api.types.is_datetime64_any_dtype(data.index):
            start_timestamp = pd.Timestamp(start_date)
            filtered_data = data[data.index >= start_timestamp]
            data = filtered_data if isinstance(filtered_data, pd.DataFrame) else pd.DataFrame()

        return data if not data.empty else None

    except Exception as e:
        logging.getLogger(__name__).error(f"下载失败 {symbol} {interval}: {e}", exc_info=True)
        return None


# ==================== IPO日期下载函数 ====================


async def _download_single_ipo_async(
    client: AsyncTdxHq_API, symbol: str, market: int
) -> tuple[Optional[date], int, dict]:
    """下载单个品种的IPO日期和行业代码（异步版本）

    Args:
        client: tdx_asyncio客户端
        symbol: 品种代码
        market: 市场代码（0=深圳, 1=上海, 2=北京）

    Returns:
        (IPO日期或None, 行业代码, 完整finance_info)
        - (None, 0, {}): 服务器问题，需要重试
        - (None, >0, {...}): 未上市品种，不重试
        - (date, >0, {...}): 已上市品种
    """
    import logging

    local_logger = logging.getLogger(__name__)

    try:
        # 🔍 DEBUG: 记录请求参数（只进入log文件）
        if symbol in ["000001", "600000", "688001"]:  # 采样：只记录几个典型品种
            local_logger.debug(f"🔍 请求IPO数据: symbol={symbol}, market={market}")

        finance_info = await client.get_finance_info(market, symbol)

        # 🔍 DEBUG: 记录返回数据（只进入log文件）
        if symbol in ["000001", "600000", "688001"]:
            if finance_info is None:
                local_logger.debug(f"🔍 {symbol}: get_finance_info返回None")
            else:
                # 记录返回的所有字段名和关键字段值
                fields = (
                    list(finance_info.keys()) if isinstance(finance_info, dict) else "非dict类型"
                )
                local_logger.debug(f"🔍 {symbol}: 返回字段={fields}")
                if isinstance(finance_info, dict):
                    ipo_val = finance_info.get("ipo_date")
                    industry_val = finance_info.get("industry")
                    local_logger.debug(f"🔍 {symbol}: ipo_date={ipo_val}, industry={industry_val}")

        # 如果finance_info为None，视为服务器问题
        if finance_info is None:
            return None, 0, {}

        # 类型断言：此时finance_info一定是dict类型
        assert isinstance(finance_info, dict)

        ipo_timestamp = finance_info.get("ipo_date", 0)
        industry = finance_info.get("industry", 0)

        if ipo_timestamp and ipo_timestamp > 0:
            ipo_str = str(int(ipo_timestamp)).zfill(8)
            if len(ipo_str) == 8:
                parsed_date = datetime.strptime(ipo_str, "%Y%m%d").date()
                if symbol in ["000001", "600000", "688001"]:
                    local_logger.debug(f"🔍 {symbol}: 解析成功，IPO日期={parsed_date}")
                return parsed_date, industry, finance_info

        # ipo_date=0，返回None、industry和完整数据
        if symbol in ["000001", "600000", "688001"]:
            local_logger.debug(f"🔍 {symbol}: ipo_date=0，标记为未上市")
        return None, industry, finance_info
    except Exception as e:
        local_logger.debug("查询IPO失败 %s: %s", symbol, e)
        # 异常视为服务器问题
        return None, 0, {}


# ==================== 财务信息2段式下载Worker（SQLite版） ====================


async def download_worker_finance_two_phase_async(
    worker_id,
    task_queue,
    result_queue,
    metrics_queue,
    progress_queue,
    regular_servers,
    standby_servers,
    timeout,
    stop_event,
    pause_event,
    connections_per_worker=60,
    ipo_cache=None,
):
    """财务信息2段式下载Worker（SQLite后端）

    第一阶段：使用IPv4服务器池，无重试
    切换条件：剩余任务<50 且 失败次数>=1
    第二阶段：使用IPv6服务器池，失败重试2次

    Args:
        worker_id: Worker进程ID
        task_queue: 共享任务队列
        result_queue: 结果队列
        metrics_queue: 监控指标队列
        progress_queue: 进度队列
        regular_servers: IPv4服务器列表
        standby_servers: IPv6服务器列表
        timeout: 连接超时时间
        stop_event: 停止事件
        pause_event: 暂停事件
        connections_per_worker: 每个worker的异步连接数
        ipo_cache: IPODateCache实例（用于保存到SQLite）
    """
    # ✅ 配置子进程日志，接入LogHub统一路由
    logger_local = _configure_subprocess_logging(worker_id, task_type="finance")
    logger_local.info("财务信息2段式Worker %s 启动，PID：%s", worker_id, os.getpid())

    # 启动lag监控
    # ✅ 修复：使用绝对导入，避免多进程中的导入失败
    from backend.infrastructure.data_module_vnpy.load_balancer import (
        LagMonitor,
        ConnectionLifecycleManager,
    )

    lag_monitor_task = asyncio.create_task(
        LagMonitor.monitor_and_report(
            metrics_queue=metrics_queue,
            worker_id=worker_id,
            stop_event=stop_event,
            interval_seconds=0.3,
        )
    )
    logger_local.info(f"[Worker-{worker_id}] ✅ 已启动lag监控（财务信息2段式下载）")

    # ===== 第一阶段：IPv4服务器池 =====
    conn_manager_p1 = ConnectionLifecycleManager(hash(f"{worker_id}-P1") % 2**31, logger_local)
    phase1_failed_count = 0
    phase1_processed = 0

    try:
        logger_local.info("[Phase1] Worker %s 开始Phase1（IPv4服务器池）", worker_id)

        # 创建Phase1连接
        phase1_servers = regular_servers[:connections_per_worker]
        phase1_connections = await conn_manager_p1.create_connections(
            servers=phase1_servers, timeout=timeout, health_check=False  # Phase1优先速度
        )

        if not phase1_connections:
            logger_local.error("[Phase1] Worker %s 无可用连接，跳过Phase1", worker_id)
        else:
            logger_local.info(
                "[Phase1] Worker %s 建立 %s 个Phase1连接", worker_id, len(phase1_connections)
            )

            # Phase1下载循环
            async def phase1_download_loop(conn_id, client):
                nonlocal phase1_failed_count, phase1_processed
                processed = 0

                while not stop_event.is_set():
                    # 检查切换条件：剩余任务<50 且 失败次数>=1
                    try:
                        queue_size = task_queue.qsize()
                        if queue_size < 50 and phase1_failed_count >= 1:
                            logger_local.info(
                                "[Phase1] Worker %s 连接%s 满足切换条件（剩余%s，失败%s），停止",
                                worker_id,
                                conn_id,
                                queue_size,
                                phase1_failed_count,
                            )
                            break
                    except Exception:
                        pass

                    # 检查暂停
                    while not pause_event.is_set():
                        if stop_event.is_set():
                            break
                        await asyncio.sleep(0.1)

                    if stop_event.is_set():
                        break

                    # 获取任务
                    try:
                        task = await asyncio.to_thread(task_queue.get, timeout=0.5)
                    except queue.Empty:
                        break

                    task_type, symbol, market = task

                    try:
                        # 下载财务信息
                        finance_info = await client.get_finance_info(market, symbol)

                        # 判断是否成功（简化版本：只检查None和关键字段）
                        is_failed = finance_info is None
                        if not is_failed:
                            # 检查关键字段是否全为0
                            key_fields = [
                                "industry",
                                "province",
                                "liutongguben",
                                "zongguben",
                                "zongzichan",
                                "jingzichan",
                                "zhuyingshouru",
                                "jinglirun",
                            ]
                            non_zero_count = sum(
                                1
                                for field in key_fields
                                if finance_info.get(field, 0) not in (0, None, "")
                            )
                            is_failed = non_zero_count < 3  # 至少3个关键字段非零

                        if is_failed:
                            # 失败，重新入队，不重试
                            phase1_failed_count += 1
                            await asyncio.to_thread(task_queue.put, task)
                            await asyncio.to_thread(progress_queue.put, (symbol, "retry"))
                            logger_local.debug(
                                "[Phase1] Worker %s 下载失败: %s（全零或None）", worker_id, symbol
                            )
                        else:
                            # 成功，返回数据给主进程处理
                            finance_info["market"] = market  # 确保包含market字段
                            await asyncio.to_thread(result_queue.put, (symbol, finance_info))
                            await asyncio.to_thread(progress_queue.put, (symbol, "success"))
                            logger_local.debug("[Phase1] Worker %s 下载成功: %s", worker_id, symbol)

                        processed += 1
                        phase1_processed += 1

                        # 动态延时
                        try:
                            queue_size = task_queue.qsize()
                            if queue_size <= 50:
                                await asyncio.sleep(0.05)
                            elif queue_size <= 200:
                                await asyncio.sleep(0.02)
                        except Exception:
                            await asyncio.sleep(0.02)

                    except Exception as e:
                        phase1_failed_count += 1
                        await asyncio.to_thread(task_queue.put, task)
                        await asyncio.to_thread(progress_queue.put, (symbol, "retry"))
                        logger_local.debug(
                            "[Phase1] Worker %s 下载异常: %s (%s)", worker_id, symbol, e
                        )

                logger_local.debug(
                    "[Phase1] Worker %s 连接%s 完成，处理 %d 个任务", worker_id, conn_id, processed
                )
                return processed

            # 并发执行Phase1下载
            phase1_tasks = [
                phase1_download_loop(i, client) for i, client in enumerate(phase1_connections)
            ]
            await asyncio.gather(*phase1_tasks, return_exceptions=True)

        # 关闭Phase1连接
        await conn_manager_p1.close_all_connections()
        logger_local.info(
            "[Phase1] Worker %s Phase1完成，处理%d个任务，失败%d次",
            worker_id,
            phase1_processed,
            phase1_failed_count,
        )

    except Exception as e:
        logger_local.error("[Phase1] Worker %s Phase1异常: %s", worker_id, e, exc_info=True)

    # ===== 第二阶段：IPv6服务器池（重试2次） =====
    conn_manager_p2 = ConnectionLifecycleManager(hash(f"{worker_id}-P2") % 2**31, logger_local)
    phase2_processed = 0
    phase2_failed = 0

    try:
        logger_local.info("[Phase2] Worker %s 开始Phase2（IPv6服务器池，重试2次）", worker_id)

        # 创建Phase2连接
        phase2_servers = standby_servers[:connections_per_worker]
        phase2_connections = await conn_manager_p2.create_connections(
            servers=phase2_servers, timeout=timeout, health_check=True  # Phase2需要健康检查
        )

        if not phase2_connections:
            logger_local.warning("[Phase2] Worker %s 无可用IPv6连接", worker_id)
        else:
            logger_local.info(
                "[Phase2] Worker %s 建立 %s 个Phase2连接", worker_id, len(phase2_connections)
            )

            # Phase2下载循环（带重试）
            async def phase2_download_loop(conn_id, client):
                nonlocal phase2_processed, phase2_failed
                processed = 0

                while not stop_event.is_set():
                    # 检查暂停
                    while not pause_event.is_set():
                        if stop_event.is_set():
                            break
                        await asyncio.sleep(0.1)

                    if stop_event.is_set():
                        break

                    # 获取任务
                    try:
                        task = await asyncio.to_thread(task_queue.get, timeout=0.5)
                    except queue.Empty:
                        break

                    task_type, symbol, market = task
                    retry_count = 0
                    success = False

                    # 重试最多2次
                    while retry_count < 2 and not success:
                        try:
                            finance_info = await client.get_finance_info(market, symbol)

                            # 判断是否成功（简化版本：只检查None和关键字段）
                            is_valid = finance_info is not None
                            if is_valid:
                                key_fields = [
                                    "industry",
                                    "province",
                                    "liutongguben",
                                    "zongguben",
                                    "zongzichan",
                                    "jingzichan",
                                    "zhuyingshouru",
                                    "jinglirun",
                                ]
                                non_zero_count = sum(
                                    1
                                    for field in key_fields
                                    if finance_info.get(field, 0) not in (0, None, "")
                                )
                                is_valid = non_zero_count >= 3  # 至少3个关键字段非零

                            if is_valid:
                                # 成功，返回数据给主进程处理
                                finance_info["market"] = market
                                await asyncio.to_thread(result_queue.put, (symbol, finance_info))
                                await asyncio.to_thread(progress_queue.put, (symbol, "success"))
                                success = True
                                logger_local.debug(
                                    "[Phase2] Worker %s 下载成功: %s（重试%d次）",
                                    worker_id,
                                    symbol,
                                    retry_count,
                                )
                            else:
                                retry_count += 1
                                if retry_count < 2:
                                    logger_local.debug(
                                        "[Phase2] Worker %s 重试%d: %s",
                                        worker_id,
                                        retry_count,
                                        symbol,
                                    )
                                await asyncio.sleep(0.1)  # 重试前短暂延时

                        except Exception as e:
                            retry_count += 1
                            if retry_count < 2:
                                logger_local.debug(
                                    "[Phase2] Worker %s 重试%d（异常）: %s (%s)",
                                    worker_id,
                                    retry_count,
                                    symbol,
                                    e,
                                )
                            await asyncio.sleep(0.1)

                    if not success:
                        phase2_failed += 1
                        await asyncio.to_thread(progress_queue.put, (symbol, "failed"))
                        logger_local.warning("[Phase2] Worker %s 最终失败: %s", worker_id, symbol)

                    processed += 1
                    phase2_processed += 1

                logger_local.debug(
                    "[Phase2] Worker %s 连接%s 完成，处理 %d 个任务", worker_id, conn_id, processed
                )
                return processed

            # 并发执行Phase2下载
            phase2_tasks = [
                phase2_download_loop(i, client) for i, client in enumerate(phase2_connections)
            ]
            await asyncio.gather(*phase2_tasks, return_exceptions=True)

        # 关闭Phase2连接
        await conn_manager_p2.close_all_connections()
        logger_local.info(
            "[Phase2] Worker %s Phase2完成，处理%d个任务，最终失败%d个",
            worker_id,
            phase2_processed,
            phase2_failed,
        )

    except Exception as e:
        logger_local.error("[Phase2] Worker %s Phase2异常: %s", worker_id, e, exc_info=True)

    # 停止lag监控
    lag_monitor_task.cancel()
    try:
        await lag_monitor_task
    except asyncio.CancelledError:
        pass

    logger_local.info(
        "Worker %s 完成，Phase1=%d, Phase2=%d, 总失败=%d",
        worker_id,
        phase1_processed,
        phase2_processed,
        phase2_failed,
    )


# ==================== (旧download_ipo_dates_simple、download_worker_ipo_async已删除，使用统一多进程架构) ====================


# ==================== (旧StockSymbolManager已删除，使用symbol_management.SymbolLoader替代) ====================


# ==================== 多进程数据获取器 ====================


class MultiProcessStockFetcher:
    """多进程股票数据获取器（进程池+动态任务分配模式）"""

    def __init__(self, event_engine=None):
        self.logger = logger
        self.logger_alert = logger_alert
        self.event_engine = event_engine

        # 使用 tdx_asyncio 的智能IP池（延迟初始化）
        self.ip_pool = None  # 将在下载时初始化

        # 进程池配置（动态计算，在download时根据服务器数量确定）
        self.num_processes = 1  # 初始值，将在下载时动态计算

        # 硬编码超时和重试参数（优化后的快速失败策略）
        self.timeout = 2  # 连接超时2秒
        self.retry_times = 0  # 不重试，直接换热备服务器

        # 异步连接配置
        self.async_connections_per_process = 30  # 每个进程30个异步连接

        self.logger.info(
            "初始化异步下载器: 超时=%d秒, 重试=%d次, 每进程连接数=%d",
            self.timeout,
            self.retry_times,
            self.async_connections_per_process,
        )

        # 多进程共享对象
        self.manager = None
        self.task_queue: Optional[queue.Queue] = None
        self.result_queue: Optional[queue.Queue] = None
        self.progress_queue: Optional[queue.Queue] = None
        self.stop_event = None
        self.pause_event = None

        self.processes: List[Process] = []

        # 事件发布器
        if event_engine:
            from .data_module import DownloadEventPublisher, EventPublisher, AsyncioMetricsPublisher

            self.download_publisher = DownloadEventPublisher(event_engine)
            self.log_publisher = EventPublisher(event_engine)
            self.asyncio_publisher = AsyncioMetricsPublisher(event_engine)
        else:
            self.download_publisher = None
            self.log_publisher = None
            self.asyncio_publisher = None

        # 异步下载管理
        self._download_thread = None
        self._download_lock = threading.Lock()
        self._download_progress = None  # 将在_init_multiprocess_objects中初始化

    def _report_download_concurrency(self, total_concurrency: int):
        """上报当前下载并发数到监控系统

        Args:
            total_concurrency: 总并发数（进程数 × 每进程协程数）
        """
        try:
            # 延迟导入，避免循环依赖
            from backend.infrastructure.system_vnpy.monitor_system import (
                get_business_metrics_collector,
            )

            # 获取BusinessMetricsCollector实例
            collector = get_business_metrics_collector()

            # 上报并发数
            collector.record_metric(
                "download_concurrency", total_concurrency, {"task_type": "kline_download"}
            )

            self.logger.debug(f"✅ 已上报下载并发数: {total_concurrency}")

        except Exception as e:
            # 如果上报失败，不影响下载，只记录日志
            self.logger.debug(f"上报下载并发数失败: {e}")

    def _init_multiprocess_objects(self):
        """初始化多进程对象"""
        if self.manager is None:
            self.manager = Manager()
            self.task_queue = self.manager.Queue()
            self.result_queue = self.manager.Queue()
            self.metrics_queue = self.manager.Queue()  # 🆕 v3.6: 独立的监控指标队列
            self.progress_queue = self.manager.Queue()
            self.stop_event = self.manager.Event()
            self.pause_event = self.manager.Event()
            self.pause_event.set()

        # 每次调用都重新初始化_download_progress
        if self.manager:
            self._download_progress = self.manager.dict(
                {
                    "is_downloading": False,
                    "completed": 0,
                    "total": 0,
                    "current_symbol": "",
                    "current_interval": "",
                    "start_time": None,
                }
            )

    def download_incremental_kline(
        self,
        symbols: List[str],
        start_date,
        intervals: Optional[List[str]] = None,
        progress_callback=None,
        use_adaptive: bool = True,
        use_two_phase: bool = True,
    ) -> Union[Dict[str, pd.DataFrame], Dict[str, str]]:
        """主下载方法 - 使用进程池+动态任务分配

        Args:
            symbols: 品种代码列表
            start_date: 起始日期
            intervals: 周期列表（默认["1d", "5m", "1m"]）
            progress_callback: 进度回调函数
            use_adaptive: 是否使用自适应配置（默认True，企业级推荐）
            use_two_phase: 是否使用两段式下载（默认True，热备服务器优化）
        """
        if not symbols:
            self.logger.error("品种列表为空")
            return {}

        intervals = intervals or ["1d", "5m", "1m"]
        total_tasks = len(symbols) * len(intervals)

        self.logger.info(
            f"开始多进程下载: {len(symbols)}品种 × {len(intervals)}周期 = {total_tasks}任务"
        )

        try:
            # 1. 获取服务器列表（统一使用服务器池缓存）
            # 两段式下载：获取分层服务器（热备 + 乱序）
            standby_servers = []
            regular_servers = []
            broker_map = {}
            threshold = 0

            try:
                if use_two_phase:
                    # 🔧 优化：两段式模式分离IPv4/IPv6，Phase1使用IPv4，Phase2使用IPv6
                    self.logger.info("使用两段式下载模式（IPv4/IPv6分离）")

                    # Phase1使用IPv4服务器池
                    regular_servers = server_pool_manager.get_servers_shuffled(pool_type="ipv4")
                    # Phase2使用IPv6服务器池
                    standby_servers = server_pool_manager.get_servers_shuffled(pool_type="ipv6")

                    broker_map = {}  # 两段式不需要broker区分
                    available_servers = regular_servers  # 第一阶段可用的服务器

                    # 计算阈值：固定50个任务
                    threshold = 50
                    self.logger.info(f"  Phase1(IPv4)服务器池: {len(regular_servers)}个")
                    self.logger.info(f"  Phase2(IPv6)服务器池: {len(standby_servers)}个")
                    self.logger.info(f"  切换阈值: 剩余{threshold}任务时切换到Phase2")
                else:
                    # 单段式模式：使用IPv4池获取打乱的服务器
                    available_servers = server_pool_manager.get_servers_shuffled(pool_type="ipv4")

                self.logger.info("✅ 使用缓存的服务器池: %s个可用服务器", len(available_servers))
            except RuntimeError as e:
                # ❌ 缓存不可用，阻止下载
                error_msg = (
                    "服务器池缓存不可用，无法下载数据！\n\n"
                    f"原因：{str(e)}\n\n"
                    "请按以下步骤操作：\n"
                    "1. 打开'系统管理'模块\n"
                    "2. 点击'测速服务器'按钮\n"
                    "3. 等待测速完成（约7秒）\n"
                    "4. 重新尝试下载"
                )
                self.logger.error(error_msg)

                # 返回失败结果（供UI处理）
                return {"error": error_msg, "action_required": "test_servers"}

            if use_adaptive:
                # ===== 自适应模式（企业级） =====
                self.logger.info("=" * 60)
                self.logger.info("【企业级自适应下载】启动")

                # 使用LoadBalancer计算自适应配置
                from backend.infrastructure.data_module_vnpy.load_balancer import (
                    get_load_balancer,
                )

                task = KlineDownloadTask("kline_download", total_tasks)
                load_balancer = get_load_balancer()
                lb_config = load_balancer.get_optimal_config(task)

                # 从缓存服务器中选取需要的数量
                available_servers = available_servers[: lb_config.get("total_connections", 160)]

                # 使用自适应配置
                self.num_processes = lb_config.get("processes", 4)
                self.async_connections_per_process = lb_config.get("coroutines_per_process", 40)

                self.logger.info("【配置信息】")
                self.logger.info("  进程数: %d", self.num_processes)
                self.logger.info("  每进程协程: %d", self.async_connections_per_process)
                self.logger.info("  总连接数: %d", lb_config.get("total_connections", 160))
                self.logger.info("  预计内存: %.2f MB", lb_config.get("estimated_memory_mb", 80.0))
                self.logger.info("  服务器来源: 服务器池缓存 (打乱顺序)")
                self.logger.info("  压力评分: %.1f/100", lb_config.get("pressure_score", 0))
                self.logger.info("  瓶颈维度: %s", lb_config.get("bottleneck", "unknown"))
                self.logger.info(
                    "  配置原因: %s", lb_config.get("reason", "基于LoadBalancer动态配置")
                )
                self.logger.info("=" * 60)

                # 🚀 上报当前下载并发数到监控系统（TODO #9）
                total_concurrency = self.num_processes * self.async_connections_per_process
                self._report_download_concurrency(total_concurrency)
            else:
                # ===== 传统模式 =====
                self.logger.info(
                    "使用服务器池缓存（打乱顺序）: %s 个服务器", len(available_servers)
                )
                # 打印前5个服务器（已打乱）
                top5 = available_servers[:5]
                self.logger.info("前5个服务器（打乱后）: %s", top5)

                # 动态计算进程数：使用更大的并发数
                import math

                # 🔧 移除硬编码限制，使用更大的每进程连接数
                connections_per_process = 200  # 从30提升到200
                optimal_processes = max(
                    1, math.ceil(len(available_servers) / connections_per_process)
                )
                self.num_processes = optimal_processes
                self.async_connections_per_process = min(
                    connections_per_process, len(available_servers) // self.num_processes + 1
                )
                self.logger.info(
                    f"动态计算进程数: {len(available_servers)}个服务器 / {connections_per_process} = {optimal_processes}个进程"
                )
                self.logger.info(
                    f"预计总并发: 每进程约{self.async_connections_per_process}连接 "
                    f"(总计{len(available_servers)}连接)"
                )

                # 🚀 上报当前下载并发数到监控系统（TODO #9 - 传统模式）
                total_concurrency = len(available_servers)
                self._report_download_concurrency(total_concurrency)

            # 2. 初始化Manager和队列
            self._init_multiprocess_objects()
            self._clear_queues()

            # 3. 创建共享服务器列表和索引
            assert self.manager is not None, "Manager未初始化"
            server_list = self.manager.list(available_servers)  # type: ignore
            server_index = self.manager.Value("i", 0)  # type: ignore

            # 4. 填充任务队列
            tasks = [(symbol, interval, start_date) for symbol in symbols for interval in intervals]
            assert self.task_queue is not None
            for task in tasks:
                self.task_queue.put(task)

            # 5. 设置进度状态
            if self._download_progress:
                self._download_progress.update(
                    {
                        "is_downloading": True,
                        "completed": 0,
                        "total": total_tasks,
                        "start_time": datetime.now().isoformat(),
                    }
                )

            # 6. 启动worker进程池
            if use_two_phase:
                # 使用两段式worker
                self._start_two_phase_worker_pool(
                    regular_servers, standby_servers, broker_map, threshold
                )
            else:
                # 使用单段式worker
                self._start_worker_pool(server_list, server_index)

            # 7. 监控进度并收集结果
            results = self._monitor_progress_and_collect_results(total_tasks, progress_callback)

            # 8. 清理资源
            self._cleanup_processes()
            if self._download_progress:
                self._download_progress["is_downloading"] = False

            # 统计结果
            valid_count = sum(1 for v in results.values() if v is not None and not v.empty)
            self.logger.info("下载完成: %s/%s 有效任务", valid_count, total_tasks)

            return results

        except Exception as e:
            self.logger.error("多进程下载异常: %s", e, exc_info=True)
            if self._download_progress:
                self._download_progress["is_downloading"] = False
            self._cleanup_processes()
            return {}

    def _start_worker_pool(self, server_list, server_index):
        """启动异步worker进程池

        Args:
            server_list: Manager.list()共享的服务器列表
            server_index: Manager.Value()共享的服务器索引
        """
        for i in range(self.num_processes):
            try:
                # 使用异步worker
                p = Process(
                    target=_run_async_worker,
                    args=(
                        i,
                        self.task_queue,
                        self.result_queue,
                        self.metrics_queue,  # 🆕 v3.6: 传递独立的监控指标队列
                        self.progress_queue,
                        server_list,
                        server_index,
                        self.timeout,
                        self.retry_times,
                        self.stop_event,
                        self.pause_event,
                        self.async_connections_per_process,  # 传递异步连接数
                    ),
                )

                p.start()
                self.processes.append(p)
                self.logger.debug(f"启动异步进程 {i} (PID: {p.pid})")

                # 给进程一点启动时间
                time.sleep(0.1)

            except Exception as e:
                self.logger.error(f"启动进程{i}失败: {e}")

        self.logger.info(f"启动{len(self.processes)}个工作进程（进程池模式）")

        # 等待所有进程启动完成
        time.sleep(0.5)

    def _start_two_phase_worker_pool(self, regular_servers, standby_servers, broker_map, threshold):
        """启动两段式异步worker进程池

        Args:
            regular_servers: 乱序服务器列表
            standby_servers: 热备服务器列表
            broker_map: 服务器到券商的映射
            threshold: 任务剩余阈值
        """
        # 直接传递只读数据（regular_servers, standby_servers, broker_map）
        # 不使用Manager代理，避免代理对象生命周期问题导致KeyError
        # 这些数据通过pickle序列化传递给子进程，每个进程获得独立副本
        assert self.manager is not None, "Manager未初始化"

        for i in range(self.num_processes):
            try:
                # 使用两段式异步worker
                p = Process(
                    target=_run_two_phase_worker,
                    args=(
                        i,
                        self.task_queue,
                        self.result_queue,
                        self.metrics_queue,  # 🆕 v3.6: 传递独立的监控指标队列
                        self.progress_queue,
                        regular_servers,  # 直接传递原始list
                        standby_servers,  # 直接传递原始list
                        broker_map,  # 直接传递原始dict
                        threshold,
                        self.timeout,
                        self.stop_event,
                        self.pause_event,
                        self.async_connections_per_process,  # 传递异步连接数
                    ),
                )

                p.start()
                self.processes.append(p)
                self.logger.debug(f"启动两段式进程 {i} (PID: {p.pid})")

                # 给进程一点启动时间
                time.sleep(0.1)

            except Exception as e:
                self.logger.error(f"启动两段式进程{i}失败: {e}")

        self.logger.info(f"启动{len(self.processes)}个两段式工作进程")

        # 📊 【并发度监控】检查服务器分配和并发度
        total_concurrency = self.num_processes * self.async_connections_per_process
        phase1_reuse_rate = total_concurrency / len(regular_servers) if regular_servers else 0

        self.logger.info(
            f"📊 两阶段下载配置: {self.num_processes}进程 × {self.async_connections_per_process}连接/进程 = "
            f"{total_concurrency}总并发"
        )
        self.logger.info(
            f"📦 Phase1(IPv4): {len(regular_servers)}个服务器, 超时1.0s, socket异常自动切换"
        )
        self.logger.info(
            f"📦 Phase2(IPv6): {len(standby_servers)}个服务器, 超时1.0s, socket异常自动切换"
        )
        self.logger.info(f"🔄 切换阈值: 剩余{threshold}任务时从Phase1切换到Phase2")

        # 检查Phase1服务器复用率
        if phase1_reuse_rate > 2.0:
            self.logger.error(
                f"❌ Phase1服务器复用率过高: {phase1_reuse_rate:.2f}x (每个服务器平均{phase1_reuse_rate:.1f}个连接)，"
                f"可能导致大量连接拒绝！建议降低并发度或增加服务器"
            )
        elif phase1_reuse_rate > 1.5:
            self.logger.warning(
                f"⚠️ Phase1服务器复用率较高: {phase1_reuse_rate:.2f}x (每个服务器平均{phase1_reuse_rate:.1f}个连接)，"
                f"可能影响稳定性"
            )
        elif phase1_reuse_rate > 1.0:
            self.logger.warning(
                f"⚠️ Phase1服务器存在复用: {phase1_reuse_rate:.2f}x，建议增加服务器或降低connections_per_worker"
            )
        else:
            self.logger.info(
                f"✅ Phase1服务器充足，复用率: {phase1_reuse_rate:.2f}x，每个服务器独立连接"
            )

        # 等待所有进程启动完成
        time.sleep(0.5)

    def _monitor_progress_and_collect_results(
        self, total_tasks: int, progress_callback
    ) -> Dict[str, pd.DataFrame]:
        """改进的监控和结果收集"""
        results = {}
        completed = 0
        timeout_count = 0
        max_timeout_count = 600  # ✅ 增加到60秒（600 * 0.1秒），给足时间下载

        self.logger.info(
            f"开始异步下载监控: {self.num_processes}进程 × {self.async_connections_per_process}连接 = "
            f"{self.num_processes * self.async_connections_per_process}并发, 总任务数: {total_tasks}"
        )

        # 🆕 v3.4: 预先导入LagMonitor（避免循环中重复导入）
        # ✅ 修复：使用绝对导入，避免多进程中的导入失败
        from backend.infrastructure.data_module_vnpy.load_balancer import LagMonitor

        while completed < total_tasks:
            if self.stop_event and self.stop_event.is_set():
                self.logger.info("检测到停止信号，退出监控")
                break

            # 收集进度
            try:
                if self.progress_queue is not None:
                    progress_data = self.progress_queue.get(timeout=0.1)
                    # 兼容新格式：(symbol, interval, status) 或旧格式：(symbol, interval)
                    if len(progress_data) == 3:
                        symbol, interval, _ = progress_data
                    else:
                        symbol, interval = progress_data

                    completed += 1
                    timeout_count = 0  # 重置超时计数

                    if self._download_progress:
                        self._download_progress["completed"] = completed
                        self._download_progress["current_symbol"] = symbol
                        self._download_progress["current_interval"] = interval

                    if progress_callback:
                        progress_callback(completed, total_tasks, symbol, interval)

                    self.logger.debug(f"收到进度: {symbol} {interval} ({completed}/{total_tasks})")
            except queue.Empty:
                timeout_count += 1
                if timeout_count >= max_timeout_count:
                    self.logger.warning(
                        f"进度监控超时（{max_timeout_count * 0.1}秒），已完成: {completed}/{total_tasks}"
                    )
                    # ✅ 检查所有进程状态并诊断
                    alive_processes = [p for p in self.processes if p.is_alive()]
                    self.logger.warning(f"存活进程数: {len(alive_processes)}/{len(self.processes)}")

                    # ✅ 检查队列状态
                    try:
                        task_qsize = self.task_queue.qsize() if self.task_queue else 0
                        progress_qsize = self.progress_queue.qsize() if self.progress_queue else 0
                        result_qsize = self.result_queue.qsize() if self.result_queue else 0
                        self.logger.warning(
                            f"队列状态 - 任务: {task_qsize}, 进度: {progress_qsize}, 结果: {result_qsize}"
                        )
                    except Exception as e:
                        self.logger.debug(f"检查队列状态失败: {e}")

                    if not alive_processes:
                        self.logger.warning("所有进程已结束，但任务未完成！强制退出监控")
                        break

                    # ✅ 重置超时计数，继续等待（进程还在工作）
                    timeout_count = 0
                    self.logger.info("进程仍在运行，重置超时计数器，继续等待...")

            # 🆕 v3.6: 处理监控指标（从独立的metrics_queue）
            try:
                if self.metrics_queue:
                    msg = self.metrics_queue.get_nowait()
                    LagMonitor.process_lag_message(msg, self.load_balancer, self.logger)
            except queue.Empty:
                pass
            except Exception as e:
                self.logger.debug(f"处理监控指标失败: {e}")

            # 收集结果（非阻塞）
            try:
                if self.result_queue:
                    msg = self.result_queue.get_nowait()

                    # 普通结果消息
                    key, data_dict = msg
                    if data_dict is not None:
                        df = pd.DataFrame(data_dict)
                        results[key] = df
                        self.logger.debug(f"收到结果: {key} ({len(df)} 条数据)")
            except queue.Empty:
                pass

        # 最后收集剩余的结果和监控指标
        self.logger.info("收集剩余结果...")
        remaining_results = 0

        # 🆕 v3.6: 收集剩余的监控指标
        while True:
            try:
                if self.metrics_queue:
                    msg = self.metrics_queue.get_nowait()
                    LagMonitor.process_lag_message(msg, self.load_balancer, self.logger)
            except queue.Empty:
                break
            except Exception as e:
                self.logger.debug(f"处理剩余监控指标失败: {e}")
                break

        # 收集剩余的数据结果
        while True:
            try:
                if self.result_queue:
                    msg = self.result_queue.get_nowait()

                    # 普通结果消息
                    key, data_dict = msg
                    if data_dict is not None:
                        df = pd.DataFrame(data_dict)
                        results[key] = df
                        remaining_results += 1
                        self.logger.debug(f"收集剩余结果: {key} ({len(df)} 条数据)")
            except queue.Empty:
                break

        if remaining_results > 0:
            self.logger.info(f"收集到 {remaining_results} 个剩余结果")

        self.logger.info(f"监控完成: 收到 {len(results)} 个结果，完成 {completed} 个任务")
        return results

    def _cleanup_processes(self):
        """清理所有工作进程"""
        if not self.processes:
            return

        for p in self.processes:
            if p.is_alive():
                p.terminate()
                p.join(timeout=1)

        self.processes.clear()
        self.logger.info("进程清理完成")

    def _clear_queues(self):
        """清空所有队列"""
        for q in [self.task_queue, self.result_queue, self.progress_queue]:
            if q is not None:
                while True:
                    try:
                        q.get_nowait()
                    except queue.Empty:
                        break

    def set_server_count(self, num_servers: int) -> None:
        """
        动态设置进程池大小

        Args:
            num_servers: 进程数量（1-30）
        """
        cpu_cores = cpu_count()
        self.num_processes = min(num_servers, cpu_cores * 2, 30)
        self.logger.info("进程池大小已更新: %d", self.num_processes)

    def get_download_progress(self) -> Dict[str, Any]:
        """
        获取下载进度（供外部查询）

        Returns:
            进度信息字典
        """
        if self._download_progress is None:
            return {
                "is_downloading": False,
                "completed": 0,
                "total": 0,
                "current_symbol": "",
                "current_interval": "",
                "start_time": None,
            }

        # 返回进度字典的副本
        return dict(self._download_progress)

    def stop_download(self):
        """停止当前下载任务"""
        if self.stop_event:
            self.stop_event.set()
            self.logger.info("已发送停止信号")
        else:
            self.logger.warning("停止事件未初始化")

    def pause_download(self):
        """暂停当前下载任务"""
        if self.pause_event:
            self.pause_event.clear()
            self.logger.info("已发送暂停信号")
        else:
            self.logger.warning("暂停事件未初始化")

    def resume_download(self):
        """恢复暂停的下载任务"""
        if self.pause_event:
            self.pause_event.set()
            self.logger.info("已发送恢复信号")
        else:
            self.logger.warning("恢复事件未初始化")

    # ==================== IPO日期下载（统一多进程架构）====================

    def download_ipo_dates_multiprocess(
        self,
        symbols_with_markets: List[Tuple[str, int]],
        progress_callback=None,
        use_adaptive: bool = True,
        ipo_cache=None,
    ) -> Dict[str, Any]:
        """多进程财务信息下载（2段式架构，SQLite后端）

        Args:
            symbols_with_markets: [(symbol, market), ...] 品种和市场代码列表
            progress_callback: 进度回调函数 callback(symbol, status)
            use_adaptive: 是否使用自适应配置（默认True）
            ipo_cache: IPODateCache实例（用于保存到SQLite）

        Returns:
            {
                "success": bool,
                "total": int,
                "downloaded": int,
                "succeeded": int,
                "failed": int,
                "unlisted": [symbol, ...],    # 未上市品种（从SQLite查询）
                "error": str (if failed)
            }
        """
        if not symbols_with_markets:
            self.logger.error("品种列表为空")
            return {
                "success": False,
                "total": 0,
                "downloaded": 0,
                "succeeded": 0,
                "failed": 0,
                "data": {},
                "unlisted": [],
                "error": "品种列表为空",
            }

        total_symbols = len(symbols_with_markets)
        self.logger.info(f"开始多进程IPO下载: {total_symbols}个品种")

        try:
            # 1. 获取服务器列表（复用K线下载的服务器池）
            # 🔥 关键修复：增加服务器池就绪检查和等待逻辑
            try:
                # ✅ 修复：使用绝对导入，避免多进程中的导入失败
                from backend.infrastructure.data_module_vnpy.load_balancer import (
                    server_pool_manager,
                )
                import time

                # 检查服务器池是否就绪
                max_wait_seconds = 10  # 最多等待10秒
                wait_interval = 0.5  # 每次检查间隔0.5秒
                waited_seconds = 0

                while (
                    not server_pool_manager._running or not server_pool_manager._sorted_servers_ipv4
                ):
                    if waited_seconds >= max_wait_seconds:
                        raise RuntimeError(
                            f"服务器池等待超时（{max_wait_seconds}秒）！"
                            f"_running={server_pool_manager._running}, "
                            f"IPv4池={'有数据' if server_pool_manager._sorted_servers_ipv4 else '空'}"
                        )

                    if waited_seconds == 0:
                        self.logger.warning(
                            "⚠️ 服务器池未就绪，等待初始化... "
                            f"(_running={server_pool_manager._running})"
                        )

                    time.sleep(wait_interval)
                    waited_seconds += wait_interval

                    # 尝试触发初始化
                    if waited_seconds == 1.0 and not server_pool_manager._running:
                        self.logger.info("尝试手动启动服务器池...")
                        try:
                            server_pool_manager.start()
                        except Exception as start_error:
                            self.logger.error(f"手动启动服务器池失败: {start_error}")

                if waited_seconds > 0:
                    self.logger.info(f"✅ 服务器池已就绪（等待了{waited_seconds:.1f}秒）")

                available_servers = server_pool_manager.get_servers_shuffled(pool_type="ipv4")
                available_servers_ipv6 = server_pool_manager.get_servers_shuffled(pool_type="ipv6")
                self.logger.info(f"✅ 使用缓存的IPv4服务器池: {len(available_servers)}个可用服务器")
                self.logger.info(
                    f"✅ 使用缓存的IPv6服务器池: {len(available_servers_ipv6)}个可用服务器"
                )

            except RuntimeError as e:
                error_msg = f"服务器池缓存不可用，无法下载IPO数据！原因：{e}"
                self.logger.error(error_msg)
                self.logger.error("详细状态：")
                self.logger.error(f"  - _running: {server_pool_manager._running}")
                self.logger.error(
                    f"  - IPv4池: {'有数据' if server_pool_manager._sorted_servers_ipv4 else '空'}"
                )
                self.logger.error(
                    f"  - IPv6池: {'有数据' if server_pool_manager._sorted_servers_ipv6 else '空'}"
                )
                self.logger.error(
                    f"  - _starting: {getattr(server_pool_manager, '_starting', False)}"
                )

                return {
                    "success": False,
                    "total": total_symbols,
                    "downloaded": 0,
                    "succeeded": 0,
                    "failed": total_symbols,
                    "data": {},
                    "unlisted": [],
                    "error": error_msg,
                    "action_required": "test_servers",
                }

            # 2. 使用LoadBalancer计算自适应配置
            if use_adaptive:
                # ✅ 修复：使用绝对导入，避免多进程中的导入失败
                from backend.infrastructure.data_module_vnpy.load_balancer import (
                    get_load_balancer,
                    IPODownloadTask,
                )

                task = IPODownloadTask("ipo_download", total_symbols)
                load_balancer = get_load_balancer()
                lb_config = load_balancer.get_optimal_config(task)

                self.num_processes = lb_config.get("processes", 4)
                self.async_connections_per_process = lb_config.get("coroutines_per_process", 30)

                total_concurrency = self.num_processes * self.async_connections_per_process

                self.logger.info("=" * 60)
                self.logger.info("【智能IPO下载】LoadBalancer自适应配置")
                self.logger.info(f"  进程数: {self.num_processes}")
                self.logger.info(f"  每进程协程数: {self.async_connections_per_process}")
                self.logger.info(f"  总并发度: {total_concurrency}")
                self.logger.info("=" * 60)
            else:
                # 手动模式：保守配置
                self.num_processes = min(4, len(available_servers) // 10)
                self.async_connections_per_process = 15
                self.logger.info(
                    f"手动模式：{self.num_processes}进程 × {self.async_connections_per_process}协程"
                )

            # 3. 初始化多进程对象
            self._init_multiprocess_objects()

            # 4. 准备任务队列
            for symbol, market in symbols_with_markets:
                self.task_queue.put(("ipo", symbol, market))  # 任务格式: (type, symbol, market)

            # 5. 启动2段式worker进程池（传入IPv4和IPv6服务器）
            # 不传递ipo_cache对象（无法序列化），而是传递db_path
            db_path = None
            if ipo_cache:
                try:
                    db_path = (
                        str(ipo_cache.db.db_path) if hasattr(ipo_cache.db, "db_path") else None
                    )
                except Exception:
                    pass

            self._start_finance_two_phase_worker_pool(
                available_servers, available_servers_ipv6, db_path
            )

            # 7. 监控进度并收集结果（主进程统一保存到SQLite）
            results = self._monitor_ipo_progress(total_symbols, progress_callback, ipo_cache)

            # 8. 清理资源
            self._cleanup_processes()

            # 9. 统计结果（简化，因为SQLite已自动保存）
            # 从SQLite查询未上市品种
            if ipo_cache:
                unlisted_symbols = ipo_cache.get_unlisted_symbols()
            else:
                unlisted_symbols = []

            # 统计成功和失败
            succeeded_count = len(results)
            failed_count = total_symbols - succeeded_count

            self.logger.info(
                f"财务信息下载完成: 总计={total_symbols}, 成功={succeeded_count}, "
                f"未上市={len(unlisted_symbols)}, 失败={failed_count}"
            )

            # 🔍 DEBUG: 显示未上市品种示例（只进入log文件）
            if unlisted_symbols:
                sample_unlisted = unlisted_symbols[:10]
                self.logger.debug(f"🔍 未上市品种示例（前10个）: {sample_unlisted}")

            return {
                "success": True,
                "total": total_symbols,
                "downloaded": succeeded_count,
                "succeeded": succeeded_count,
                "failed": failed_count,
                "unlisted": unlisted_symbols,
            }

        except Exception as e:
            self.logger.error(f"多进程IPO下载异常: {e}", exc_info=True)
            self._cleanup_processes()
            return {
                "success": False,
                "total": total_symbols,
                "downloaded": 0,
                "succeeded": 0,
                "failed": total_symbols,
                "data": {},
                "unlisted": [],
                "error": str(e),
            }

    def _start_ipo_worker_pool(self, server_list):
        """启动IPO下载worker进程池（旧版，保留兼容）

        Args:
            server_list: Manager.list()共享的服务器列表
        """
        for i in range(self.num_processes):
            try:
                p = Process(
                    target=_run_ipo_worker,
                    args=(
                        i,
                        self.task_queue,
                        self.result_queue,
                        self.metrics_queue,
                        self.progress_queue,
                        server_list,
                        self.timeout,
                        self.stop_event,
                        self.pause_event,
                        self.async_connections_per_process,
                    ),
                )

                p.start()
                self.processes.append(p)
                self.logger.debug(f"启动IPO下载进程 {i} (PID: {p.pid})")
                time.sleep(0.1)

            except Exception as e:
                self.logger.error(f"启动IPO进程{i}失败: {e}")

        self.logger.info(f"启动{len(self.processes)}个IPO下载工作进程")

    def _start_finance_two_phase_worker_pool(self, regular_servers, standby_servers, db_path=None):
        """启动财务信息2段式下载worker进程池

        Args:
            regular_servers: IPv4服务器列表
            standby_servers: IPv6服务器列表
            db_path: 数据库路径（字符串，可序列化）
        """
        for i in range(self.num_processes):
            try:
                p = Process(
                    target=_run_finance_two_phase_worker,
                    args=(
                        i,
                        self.task_queue,
                        self.result_queue,
                        self.metrics_queue,
                        self.progress_queue,
                        regular_servers,
                        standby_servers,
                        self.timeout,
                        self.stop_event,
                        self.pause_event,
                        self.async_connections_per_process,
                        db_path,
                    ),
                )

                p.start()
                self.processes.append(p)
                self.logger.debug(f"启动财务信息2段式进程 {i} (PID: {p.pid})")
                time.sleep(0.1)

            except Exception as e:
                self.logger.error(f"启动财务信息进程{i}失败: {e}")

        self.logger.info(f"启动{len(self.processes)}个财务信息2段式下载工作进程")

    def _monitor_ipo_progress(self, total_symbols: int, progress_callback, ipo_cache=None) -> Dict:
        """监控IPO下载进度并收集结果，主进程统一保存到SQLite

        增强版：添加管道通信异常处理，防止启动卡死
        """
        results = {}
        completed = 0
        consecutive_errors = 0  # 连续错误计数器
        max_consecutive_errors = 5  # 最大容忍连续错误数

        while completed < total_symbols:
            try:
                symbol, result_data = self.result_queue.get(timeout=1)
                results[symbol] = result_data
                consecutive_errors = 0  # 成功后重置计数器

                # 主进程统一保存到SQLite（避免子进程数据库锁冲突）
                if ipo_cache and result_data:
                    try:
                        ipo_cache.set(symbol, result_data)
                    except Exception as e:
                        self.logger.error(f"保存财务信息失败 ({symbol}): {e}")

                completed += 1

                if progress_callback:
                    # 🔧 修复：传递 (completed, total_symbols) 而不是 (symbol, status)
                    # 与 ipo_progress_callback(current, total) 签名匹配
                    progress_callback(completed, total_symbols)

                if completed % 100 == 0:
                    self.logger.info(f"IPO下载进度: {completed}/{total_symbols}")

            except queue.Empty:
                # 检查进程是否还在运行
                if not any(p.is_alive() for p in self.processes):
                    self.logger.warning("所有进程已退出但任务未完成")
                    break
                continue

            except (EOFError, BrokenPipeError, ConnectionError, ConnectionResetError) as e:
                # 🔧 关键修复：捕获管道通信异常，防止启动卡死
                consecutive_errors += 1
                self.logger.error(
                    f"管道通信异常 ({consecutive_errors}/{max_consecutive_errors}): "
                    f"{type(e).__name__}: {e}"
                )

                # 检查所有子进程状态
                alive_processes = [p for p in self.processes if p.is_alive()]
                self.logger.warning(f"存活进程数: {len(alive_processes)}/{len(self.processes)}")

                if consecutive_errors >= max_consecutive_errors:
                    self.logger.error("⚠️ 连续管道通信错误超过阈值，终止IPO下载流程")
                    self.logger.error(f"已完成 {completed}/{total_symbols} 个品种的IPO信息下载")
                    self._cleanup_processes()  # 清理所有进程
                    break

                # 如果所有进程都已退出，直接终止
                if not alive_processes:
                    self.logger.error("⚠️ 所有子进程已异常退出，终止IPO下载流程")
                    self.logger.error(f"已完成 {completed}/{total_symbols} 个品种的IPO信息下载")
                    break

                # 短暂延迟后继续尝试
                import time

                time.sleep(0.5)
                continue

            except Exception as e:
                # 捕获其他未预期的异常
                self.logger.error(
                    f"IPO监控进程遇到未预期异常: {type(e).__name__}: {e}", exc_info=True
                )
                consecutive_errors += 1

                if consecutive_errors >= max_consecutive_errors:
                    self.logger.error("连续异常超过阈值，终止IPO下载流程")
                    break

                import time

                time.sleep(0.5)
                continue

        return results

    # ==================== 异步下载管理（从download_manager.py合并） ====================

    def start_incremental_download_async(
        self,
        start_date,
        symbol_loader,
        storage_manager,
        market_types=None,
        use_adaptive: bool = True,
    ) -> bool:
        """
        启动增量下载（异步执行，立即返回，从download_manager.py合并）

        Args:
            start_date: 开始日期
            symbol_loader: SymbolLoader实例
            storage_manager: StorageManager实例
            market_types: 市场类型列表
            use_adaptive: 是否使用自适应配置（默认True，企业级推荐）

        Returns:
            是否成功启动下载任务
        """
        with self._download_lock:
            # 检查是否有正在运行的下载任务
            if self._download_thread and self._download_thread.is_alive():
                self.logger.warning("已有下载任务正在运行")
                return False

            # 初始化多进程对象（如果还没初始化）
            self._init_multiprocess_objects()

            # 重置下载状态
            if self._download_progress:
                self._download_progress.update(
                    {
                        "is_downloading": False,
                        "completed": 0,
                        "total": 0,
                        "current_symbol": "",
                        "current_interval": "",
                        "start_time": None,
                    }
                )

            # 创建并启动后台下载线程
            self._download_thread = threading.Thread(
                target=self._do_download_async,
                args=(start_date, symbol_loader, storage_manager, market_types, use_adaptive),
                daemon=True,
                name="IncrementalDownloadThread",
            )
            self._download_thread.start()

            self.logger.info("✅ 增量下载任务已启动（后台线程）")
            return True

    def _do_download_async(
        self,
        start_date,
        symbol_loader,
        storage_manager,
        market_types=None,
        use_adaptive: bool = True,
    ):
        """
        实际执行增量下载的后台方法（从download_manager.py合并）

        Args:
            start_date: 开始日期
            symbol_loader: SymbolLoader实例
            storage_manager: StorageManager实例
            market_types: 市场类型列表
            use_adaptive: 是否使用自适应配置（默认True）
        """
        try:
            # 定义进度回调（限制频率，避免UI崩溃）
            def progress_callback(completed: int, total: int, symbol: str, interval: str):
                # ✅ 方案2：严格限制UI更新频率
                should_push = (
                    completed == 1  # 第一个任务
                    or completed == total  # 最后一个任务
                    or completed % 200 == 0  # 每200个任务更新一次（降低频率）
                )

                # ✅ 使用日志输出，避免UI更新
                if completed % 500 == 0 or completed == 1 or completed == total:
                    self.logger.info(
                        f"下载进度: {completed}/{total} ({completed*100/total:.1f}%) - {symbol} {interval}"
                    )

                # ✅ 方案1：添加异常保护，使用信号传递
                if should_push and self.download_publisher:
                    try:
                        progress_pct = (completed / total) * 100
                        self.download_publisher.push_download_progress_event(
                            "incremental_kline",
                            progress_pct,
                            completed,
                            total,
                            f"{symbol} {interval}",
                        )
                    except Exception as e:
                        # 捕获异常避免崩溃
                        self.logger.debug(f"推送进度事件失败: {e}")

            # 🔧 修复：直接使用当前实例的download_incremental_kline，而不是创建新实例
            # 获取品种列表
            if market_types:
                symbols = symbol_loader.extract_codes_by_market(market_types)
            else:
                symbols = symbol_loader.extract_all_codes()

            if not symbols:
                result = {
                    "success": False,
                    "total_tasks": 0,
                    "completed": 0,
                    "saved_count": 0,
                    "skipped_count": 0,
                    "failed_count": 0,
                    "message": "未找到可下载的品种",
                }
            else:
                # 直接调用当前实例的方法，确保_download_progress被正确更新
                download_results = self.download_incremental_kline(
                    symbols=symbols,
                    start_date=start_date,
                    intervals=["1d", "5m", "1m"],
                    progress_callback=progress_callback,
                    use_adaptive=use_adaptive,
                )

                # 🔍 诊断日志：检查下载结果
                self.logger.info("=" * 60)
                self.logger.info("🔍 下载结果诊断")
                self.logger.info(f"download_results类型: {type(download_results)}")
                self.logger.info(f"download_results键数量: {len(download_results)}")
                if download_results:
                    # 统计数据状态
                    none_count = sum(1 for v in download_results.values() if v is None)
                    empty_count = sum(
                        1
                        for v in download_results.values()
                        if v is not None and (not isinstance(v, pd.DataFrame) or v.empty)
                    )
                    valid_count = len(download_results) - none_count - empty_count
                    self.logger.info(f"  - None数据: {none_count}")
                    self.logger.info(f"  - 空DataFrame: {empty_count}")
                    self.logger.info(f"  - 有效数据: {valid_count}")

                    # 显示前3个结果的详情
                    for i, (key, data) in enumerate(list(download_results.items())[:3]):
                        if data is not None:
                            if isinstance(data, pd.DataFrame):
                                self.logger.info(f"  示例{i+1}: {key} -> DataFrame({len(data)}行)")
                            else:
                                self.logger.info(f"  示例{i+1}: {key} -> {type(data).__name__}")
                        else:
                            self.logger.info(f"  示例{i+1}: {key} -> None")
                else:
                    self.logger.critical("❌ download_results为空字典！")
                self.logger.info("=" * 60)

                # 存储数据
                saved_count = 0
                for key, data_records in download_results.items():
                    # 🔧 修复DataFrame判断问题
                    # data_records可能是list/dict/DataFrame/None，需要安全判断
                    if data_records is not None:
                        symbol, interval = key.split("_", 1)
                        # 如果已经是DataFrame，直接使用；否则转换
                        if isinstance(data_records, pd.DataFrame):
                            data_df = data_records
                        else:
                            data_df = pd.DataFrame(data_records)

                        if not data_df.empty:
                            self.logger.info(f"💾 正在保存: {symbol} {interval} ({len(data_df)}行)")
                            result_path = storage_manager.save_kline(symbol, interval, data_df)
                            if result_path:
                                saved_count += 1
                                self.logger.info(f"✅ 保存成功: {result_path}")
                            else:
                                self.logger.error(f"❌ 保存失败: {symbol} {interval}")

                # 🔍 保存统计日志
                self.logger.info("=" * 60)
                self.logger.info("📊 保存统计")
                self.logger.info(f"总任务数: {len(symbols) * 3}")
                self.logger.info(f"下载结果数: {len(download_results)}")
                self.logger.info(f"✅ 保存成功: {saved_count}")
                self.logger.info(f"❌ 保存失败/跳过: {len(download_results) - saved_count}")
                self.logger.info("=" * 60)

                result = {
                    "success": True,
                    "total_tasks": len(symbols) * 3,  # 3个周期
                    "completed": len(download_results),
                    "saved_count": saved_count,
                    "skipped_count": 0,
                    "failed_count": len(download_results) - saved_count,
                    "message": f"下载完成，保存了 {saved_count} 个品种的数据",
                }

            # 推送最终事件
            if result["success"]:
                if self.download_publisher:
                    self.download_publisher.push_download_event(
                        "incremental_kline", "success", result["saved_count"]
                    )
                if self.log_publisher:
                    self.log_publisher.push_log_event(result["message"])
            else:
                if self.download_publisher:
                    self.download_publisher.push_download_event(
                        "incremental_kline", "error", 0, result["message"]
                    )
                if self.log_publisher:
                    self.log_publisher.push_log_event(result["message"], "ERROR")

        except Exception as e:
            self.logger.error("增量下载失败: %s", e, exc_info=True)
            if self.download_publisher:
                self.download_publisher.push_download_event("incremental_kline", "error", 0, str(e))
            if self.log_publisher:
                self.log_publisher.push_log_event(f"增量下载失败: {e}", "ERROR")


# ==================== 统一下载接口（从core.py迁移） ====================


def download_incremental_unified(
    symbols: List[str],
    start_date: Union[str, date],
    intervals: Optional[List[str]] = None,
    use_adaptive: bool = True,
    symbol_loader=None,
    market_types: Optional[List[str]] = None,
    storage_callback: Optional[Callable[[str, str, pd.DataFrame], Optional[Any]]] = None,
    progress_callback: Optional[Callable[[int, int, str, str], None]] = None,
    event_callback: Optional[Callable[[str, str, int, str], None]] = None,
) -> Dict[str, Any]:
    """
    统一增量下载接口 - 封装所有下载业务逻辑（从core.py迁移，完全增强版）

    功能：
    1. 自动品种提取（如果传入symbol_loader）
    2. 日期验证和天数计算
    3. Bar数量自动计算（在_download_single_kline_incremental中）
    4. 多进程任务分配（支持自适应配置）
    5. 数据下载和解码
    6. 自动存储（通过回调）
    7. 进度和事件推送（通过回调）

    Args:
        symbols: 品种代码列表（如为空且提供symbol_loader，则自动提取）
        start_date: 开始日期（字符串或date对象）
        intervals: 周期列表（默认["1d", "5m", "1m"]）
        use_adaptive: 是否使用自适应配置（默认True，企业级推荐）
        symbol_loader: SymbolLoader实例（可选，用于自动提取品种）
        market_types: 市场类型列表（配合symbol_loader使用）
        storage_callback: 存储回调函数 callback(symbol, interval, data) -> Optional[Path]
        progress_callback: 进度回调函数 callback(completed, total, symbol, interval)
        event_callback: 事件回调函数 callback(event_type, status, count, message)

    Returns:
        Dict {
            "success": bool,
            "total_tasks": int,
            "completed": int,
            "saved_count": int,
            "skipped_count": int,
            "failed_count": int,
            "message": str
        }
    """
    import time
    from datetime import datetime, date as date_type

    logger = logging.getLogger(__name__)

    # 1. 自动提取品种（如果传入symbol_loader）
    if symbol_loader and (not symbols or len(symbols) == 0):
        logger.info("未提供品种列表，尝试从symbol_loader自动提取...")

        # 首先尝试从缓存加载
        classified_stocks = symbol_loader.load_from_cache() or {}

        if not classified_stocks:
            logger.warning("本地品种缓存为空，尝试重新加载品种列表")
            reload_result = symbol_loader.reload_and_classify()

            if not reload_result.get("success"):
                error_msg = "无法获取品种列表，请先在【品种列表】界面点击【重新加载品种】按钮"
                logger.error(error_msg)
                if event_callback:
                    event_callback("incremental_kline", "error", 0, error_msg)
                return {
                    "success": False,
                    "total_tasks": 0,
                    "completed": 0,
                    "saved_count": 0,
                    "skipped_count": 0,
                    "failed_count": 0,
                    "message": error_msg,
                }

        # 提取品种代码
        symbols = symbol_loader.extract_codes_by_market(market_types)

        if not symbols:
            error_msg = "品种列表为空，无法下载"
            logger.error(error_msg)
            if event_callback:
                event_callback("incremental_kline", "error", 0, error_msg)
            return {
                "success": False,
                "total_tasks": 0,
                "completed": 0,
                "saved_count": 0,
                "skipped_count": 0,
                "failed_count": 0,
                "message": error_msg,
            }

        logger.info("✓ 从symbol_loader提取到 %d 个品种", len(symbols))

    logger.info("=" * 60)
    logger.info("【统一下载接口】开始增量下载K线数据")
    logger.info("  开始时间: %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    logger.info("  品种数量: %d", len(symbols))
    logger.info("  起始日期: %s", start_date)
    logger.info("  配置模式: %s", "自适应配置（企业级）" if use_adaptive else "固定配置")
    logger.info("=" * 60)

    # 验证参数
    if not symbols or len(symbols) == 0:
        error_msg = "品种列表为空，无法下载"
        logger.error(error_msg)
        if event_callback:
            event_callback("incremental_kline", "error", 0, error_msg)
        return {
            "success": False,
            "total_tasks": 0,
            "completed": 0,
            "saved_count": 0,
            "skipped_count": 0,
            "failed_count": 0,
            "message": error_msg,
        }

    if intervals is None:
        intervals = ["1d", "5m", "1m"]

    # 日期验证
    today = date_type.today()
    actual_start_date: date_type

    if isinstance(start_date, str):
        try:
            actual_start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
        except ValueError as e:
            error_msg = f"日期格式错误: {e}"
            logger.error(error_msg)
            if event_callback:
                event_callback("incremental_kline", "error", 0, error_msg)
            return {
                "success": False,
                "total_tasks": 0,
                "completed": 0,
                "saved_count": 0,
                "skipped_count": 0,
                "failed_count": 0,
                "message": error_msg,
            }
    elif isinstance(start_date, date_type):
        actual_start_date = start_date
    else:
        actual_start_date = today

    days_diff = (today - actual_start_date).days

    logger.info("📅 增量下载日期范围:")
    logger.info("  • 开始日期: %s", actual_start_date)
    logger.info("  • 结束日期: %s", today)
    logger.info("  • 天数差: %d 天", days_diff)

    # 检查日期范围合理性
    if days_diff <= 0:
        error_msg = f"日期范围无效：开始日期{actual_start_date}晚于或等于今天{today}"
        logger.error(error_msg)
        if event_callback:
            event_callback("incremental_kline", "error", 0, error_msg)
        return {
            "success": False,
            "total_tasks": 0,
            "completed": 0,
            "saved_count": 0,
            "skipped_count": 0,
            "failed_count": 0,
            "message": error_msg,
        }

    if days_diff > 100:
        logger.warning("⚠️ 日期范围超过100天，可能导致下载大量历史数据")

    # 创建下载器（使用自适应配置）
    fetcher = MultiProcessStockFetcher()

    total_tasks = len(symbols) * len(intervals)
    logger.info("✅ 日期范围验证通过，准备调用下载器...")
    logger.info("即将下载参数:")
    logger.info("  • 品种数量: %d", len(symbols))
    logger.info("  • 起始日期: %s", start_date)
    logger.info("  • 周期列表: %s", intervals)
    logger.info("  • 预计任务数: %d", total_tasks)
    logger.info("  • 配置模式: %s", "自适应（企业级）" if use_adaptive else "固定")

    # 定义内部进度回调（限制事件推送频率）
    def internal_progress_callback(completed: int, total: int, symbol: str, interval: str):
        """内部进度回调：通过外部回调推送进度"""
        if progress_callback:
            progress_callback(completed, total, symbol, interval)

        # 限制事件推送频率
        if event_callback:
            should_push = completed % 100 == 0 or completed == 1 or completed == total
            if should_push:
                progress_pct = (completed / total) * 100
                event_callback(
                    "incremental_kline_progress",
                    "running",
                    completed,
                    f"{symbol} {interval} ({progress_pct:.1f}%)",
                )

    # 下载增量K线数据
    download_start = time.time()

    try:
        logger.info("=" * 60)
        logger.info("🚀 开始调用 download_incremental_kline()...")
        logger.info("  调用时间: %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        logger.info("=" * 60)

        download_results = fetcher.download_incremental_kline(
            symbols,
            start_date,
            intervals=intervals,
            progress_callback=internal_progress_callback,
            use_adaptive=use_adaptive,
        )

        download_elapsed = time.time() - download_start

        logger.info("=" * 60)
        logger.info("✅ download_incremental_kline() 调用完成")
        logger.info("  完成时间: %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        logger.info("  总耗时: %.2f 秒", download_elapsed)
        logger.info("  返回结果数: %d", len(download_results) if download_results else 0)
        logger.info("=" * 60)

    except Exception as download_error:
        download_elapsed = time.time() - download_start
        error_msg = f"下载异常: {str(download_error)}"
        logger.error("=" * 60)
        logger.error("❌ download_incremental_kline() 调用异常")
        logger.error("  异常时间: %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        logger.error("  已耗时: %.2f 秒", download_elapsed)
        logger.error("  异常信息: %s", str(download_error), exc_info=True)
        logger.error("=" * 60)

        if event_callback:
            event_callback("incremental_kline", "error", 0, error_msg)

        return {
            "success": False,
            "total_tasks": total_tasks,
            "completed": 0,
            "saved_count": 0,
            "skipped_count": 0,
            "failed_count": 0,
            "message": error_msg,
        }

    # 检查download_results是否为错误字典
    if isinstance(download_results, dict) and "error" in download_results:
        error_msg = str(download_results.get("error", "未知错误"))
        logger.error(f"❌ 下载失败: {error_msg}")
        if event_callback:
            event_callback("incremental_kline", "error", 0, error_msg)
        return {
            "success": False,
            "total_tasks": total_tasks,
            "completed": 0,
            "saved_count": 0,
            "skipped_count": 0,
            "failed_count": 0,
            "message": error_msg,
        }

    # 检查是否被停止
    if fetcher.stop_event and fetcher.stop_event.is_set():
        logger.warning("⛔ 下载被停止")
        if event_callback:
            event_callback("incremental_kline", "stopped", len(download_results), "下载已停止")
        return {
            "success": False,
            "total_tasks": total_tasks,
            "completed": len(download_results),
            "saved_count": 0,
            "skipped_count": 0,
            "failed_count": 0,
            "message": "下载已停止",
        }

    # 保存数据（如果提供了存储回调）
    saved_count = 0
    skipped_count = 0
    failed_count = 0

    if storage_callback:
        # 统计下载结果的详细状态
        none_count = sum(1 for v in download_results.values() if v is None)
        empty_count = sum(
            1
            for v in download_results.values()
            if v is not None and isinstance(v, pd.DataFrame) and v.empty
        )

        logger.info("=" * 60)
        logger.info("开始保存下载结果...")
        logger.info("📊 下载结果分析:")
        logger.info("  • 下载结果总数: %d", len(download_results))
        logger.info("  • 下载返回None: %d (下载失败)", none_count)
        logger.info("  • 下载返回空数据: %d (品种无数据/停牌等)", empty_count)
        logger.info(
            "  • 下载返回有效数据: %d (待保存)",
            len(download_results) - none_count - empty_count,
        )

        # pylint: disable=no-member
        for key, data in download_results.items():
            parts = key.split("_", 1)
            if len(parts) != 2:
                continue
            symbol, interval = parts

            # 检查数据有效性
            if data is None:
                logger.debug("跳过保存（下载失败）: %s %s", symbol, interval)
                skipped_count += 1
                continue

            if not isinstance(data, pd.DataFrame):
                logger.debug("跳过保存（无效数据类型）: %s %s", symbol, interval)
                skipped_count += 1
                continue

            # 此时data确定是DataFrame类型
            if data.empty or len(data) == 0:  # pylint: disable=no-member
                logger.debug("跳过保存（空数据）: %s %s", symbol, interval)
                skipped_count += 1
                continue

            # 有数据，尝试保存
            try:
                result_path = storage_callback(symbol, interval, data)
                if result_path is not None:
                    saved_count += 1
                    logger.debug("✓ 保存成功: %s %s (%d行)", symbol, interval, len(data))
                else:
                    failed_count += 1
                    logger.error("✗ 保存失败: %s %s", symbol, interval)
            except Exception as e:
                logger.error("保存 %s %s 异常: %s", symbol, interval, e)
                failed_count += 1

        # 统计汇总
        logger.info("=" * 60)
        logger.info("📊 保存统计:")
        logger.info("  • 下载结果总数: %d", len(download_results))
        logger.info("  • 成功保存: %d", saved_count)
        logger.info("  • 跳过（下载失败/空数据）: %d", skipped_count)
        logger.info("  • 保存失败: %d", failed_count)
        if (saved_count + failed_count) > 0:
            logger.info(
                "  • 保存成功率: %.1f%%",
                (saved_count / (saved_count + failed_count) * 100),
            )
        logger.info("=" * 60)

    # 推送完成事件
    if event_callback:
        event_callback(
            "incremental_kline", "success", saved_count, f"成功保存{saved_count}个数据集"
        )

    return {
        "success": True,
        "total_tasks": total_tasks,
        "completed": len(download_results),
        "saved_count": saved_count,
        "skipped_count": skipped_count,
        "failed_count": failed_count,
        "message": f"成功保存{saved_count}个数据集（跳过{skipped_count}个空数据）",
    }


# ==================== IPO日期批量下载接口 ====================


def download_ipo_dates(
    symbols: List[str],
    progress_callback=None,
    use_multiprocess: bool = True,
    ipo_cache=None,
) -> Dict[str, Any]:
    """IPO日期下载入口（统一多进程架构版本）

    Args:
        symbols: 品种代码列表
        progress_callback: 进度回调 callback(current, total)
        use_multiprocess: 是否使用多进程（默认True，推荐）
        ipo_cache: IPODateCache实例，如果为None则创建新实例（推荐传递全局实例以确保数据持久化）

    Returns:
        {
            "success": bool,
            "total": int,
            "cached": int,
            "downloaded": int,
            "succeeded": int,
            "failed": int,
            "data": {symbol: ipo_date},
            "unlisted": [symbol, ...],
            "error": str (可选)
        }
    """
    local_logger = logging.getLogger(__name__)

    if not symbols:
        return {
            "success": False,
            "total": 0,
            "cached": 0,
            "downloaded": 0,
            "succeeded": 0,
            "failed": 0,
            "data": {},
            "unlisted": [],
            "error": "品种列表为空",
        }

    # 1. 从缓存加载已有的IPO数据
    from backend.infrastructure.data_module_vnpy.data_quality import IPODateCache

    # 🔧 修复：使用传入的 ipo_cache 实例，避免创建新实例导致数据丢失
    if ipo_cache is None:
        ipo_cache = IPODateCache()

    cached_data = {}
    symbols_to_download = []

    for symbol in symbols:
        cached_date, is_cached = ipo_cache.get(symbol)
        if is_cached and cached_date is not None:
            cached_data[symbol] = cached_date
        else:
            symbols_to_download.append(symbol)

    cached_count = len(cached_data)
    local_logger.info(f"IPO数据加载: 缓存命中={cached_count}, 需下载={len(symbols_to_download)}")

    if not symbols_to_download:
        return {
            "success": True,
            "total": len(symbols),
            "cached": cached_count,
            "downloaded": 0,
            "succeeded": cached_count,
            "failed": 0,
            "data": cached_data,
            "unlisted": [],
        }

    # 2. 加载市场代码映射
    symbol_loader = SymbolLoader()
    classified = symbol_loader.get_all_classified()

    symbol_market_map = {}
    for _category, stocks in classified.items():
        for stock in stocks:
            if isinstance(stock, dict):
                code = stock.get("code")
                market = stock.get("market")
                if code and market is not None:
                    symbol_market_map[code] = market

    symbols_with_markets = []
    sample_count = 0  # 采样计数器
    for symbol in symbols_to_download:
        # 🔧 修复：直接从映射获取，不使用降级逻辑
        if symbol not in symbol_market_map:
            local_logger.warning(f"品种 {symbol} 不在市场映射中，跳过")
            continue
        market = symbol_market_map[symbol]
        symbols_with_markets.append((symbol, market))

        # 🔍 DEBUG: 采样记录market映射（只进入log文件）
        if symbol in ["000001", "600000", "688001"] or sample_count < 5:
            local_logger.debug(f"🔍 品种市场映射: {symbol} -> market={market}")
            sample_count += 1

    # 3. 使用多进程下载器
    if use_multiprocess:
        fetcher = MultiProcessStockFetcher()
        result = fetcher.download_ipo_dates_multiprocess(
            symbols_with_markets=symbols_with_markets,
            progress_callback=progress_callback,
            use_adaptive=True,
            ipo_cache=ipo_cache,
        )
    else:
        # 降级：单进程模式（保留简单版本用于调试）
        local_logger.warning("使用单进程降级模式，性能受限")
        result = {"success": False, "error": "单进程模式暂未实现，请使用多进程模式"}
        return result

    if not result.get("success"):
        return result

    # 4. 合并缓存数据和新下载数据
    all_data = {**cached_data, **result["data"]}

    # 5. 更新内存缓存
    for symbol, ipo_date in result["data"].items():
        ipo_cache.set(symbol, ipo_date)

    # 6. 处理未上市品种（从品种列表中移除）
    unlisted_symbols = result.get("unlisted", [])
    if unlisted_symbols:
        local_logger.info(f"发现 {len(unlisted_symbols)} 个未上市品种")
        try:
            success, category_removed = symbol_loader.update_ipo_dates_and_remove_unlisted(
                result["data"], unlisted_symbols
            )
            if success:
                # 🆕 统计分类
                if category_removed:
                    stock_count = (
                        category_removed.get("上证A股", 0)
                        + category_removed.get("深证A股", 0)
                        + category_removed.get("北证A股", 0)
                    )
                    bond_count = category_removed.get("可转债", 0)
                    fund_count = category_removed.get("T+0基金", 0)
                    local_logger.info("✓ 品种列表缓存已更新（已删除未上市品种）")
                    local_logger.info(
                        f"  删除统计: 股票{stock_count}个, 可转债{bond_count}个, 基金{fund_count}个"
                    )
                else:
                    local_logger.info("✓ 品种列表缓存已更新（已删除未上市品种）")
        except Exception as e:
            local_logger.error(f"更新品种列表缓存时出错: {e}", exc_info=True)

    # 7. 批量保存 IPO 缓存到独立文件
    try:
        ipo_cache.batch_save()
        local_logger.info(f"✓ IPO 缓存已保存到文件: {len(all_data)} 个品种")
    except Exception as e:
        local_logger.error(f"保存 IPO 缓存失败: {e}", exc_info=True)

    return {
        "success": True,
        "total": len(symbols),
        "cached": cached_count,
        "downloaded": result["downloaded"],
        "succeeded": len(all_data) + len(unlisted_symbols),
        "failed": result["failed"],
        "data": all_data,
        "unlisted": unlisted_symbols,
    }


# ==================== 加载市场映射辅助函数 ====================


def load_market_mapping() -> Dict[str, int]:
    """加载品种到市场代码的映射

    Returns:
        {symbol: market}字典，market: 0=深圳, 1=上海, 2=北交所
    """
    symbol_loader = SymbolLoader()
    classified = symbol_loader.get_all_classified()

    mapping = {}
    for _category, stocks in classified.items():
        for stock in stocks:
            if isinstance(stock, dict):
                code = stock.get("code")
                market = stock.get("market")
                if code and market is not None:
                    mapping[code] = market

    return mapping


# ==================== 已删除的函数 ====================
# download_ipo_dates_simple() - 已删除（使用download_ipo_dates_multiprocess替代）
# download_worker_ipo_async() - 已删除（使用_ipo_worker_async替代）
# _run_async_worker_ipo() - 已删除（使用_run_ipo_worker替代）


# ==================== 文件结尾 ====================


# ==============================================================================
# 第4部分：数据读取器（原data_readers/data_readers.py）
# ==============================================================================
# 合并来源：
# 1. base_reader.py - 基础读取器和数据结构
# 2. bj_decoder.py - 北交所数据解码器
# 3. tdx_reader.py - TDX二进制文件读取器
# 4. tdx_dynamic_executor.py - 动态并发执行器
# ==============================================================================

import logging

import struct
import time
from abc import ABC, abstractmethod
from collections import Counter, deque
from dataclasses import dataclass
import multiprocessing
from multiprocessing import Event
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, cast
import queue

import pandas as pd

from backend.infrastructure.tdx_asyncio import (
    read_day_data,
    read_minute_data,
    read_lc5_data,
)
from backend.infrastructure.data_module_vnpy.load_balancer import (
    LocalProcessingTask,
)


# ==============================================================================
# 第1部分：基类定义（原base_reader.py）
# ==============================================================================


class BaseReader(ABC):
    """数据读取器抽象基类

    定义统一的数据读取接口，所有数据读取器都应继承此基类。

    设计模式：
    - 采用模板方法模式
    - read(): 读取原始数据
    - standardize(): 标准化数据格式
    - save(): 保存标准化后的数据
    """

    def __init__(self, source_path: Path):
        """
        初始化数据读取器

        Args:
            source_path: 数据源路径（文件或目录）
        """
        self.source_path = source_path

        if not self.source_path.exists():
            raise FileNotFoundError(f"数据源路径不存在: {source_path}")

    @abstractmethod
    def read(self, **kwargs) -> Any:
        """
        读取原始数据

        Args:
            **kwargs: 读取参数

        Returns:
            原始数据（具体类型由子类决定）

        Raises:
            NotImplementedError: 子类必须实现此方法
        """
        raise NotImplementedError("子类必须实现read()方法")

    @abstractmethod
    def standardize(self, raw_data: Any) -> pd.DataFrame:
        """
        标准化数据格式

        将原始数据转换为标准的DataFrame格式，必须包含以下列：
        - datetime: 时间（datetime类型）
        - open: 开盘价（float）
        - high: 最高价（float）
        - low: 最低价（float）
        - close: 收盘价（float）
        - volume: 成交量（float）
        - symbol: 品种代码（str）
        - interval: K线周期（str，如'1d', '5m', '1m'）

        Args:
            raw_data: 原始数据

        Returns:
            标准化后的DataFrame

        Raises:
            NotImplementedError: 子类必须实现此方法
        """
        raise NotImplementedError("子类必须实现standardize()方法")

    @abstractmethod
    def save(self, dataframe: pd.DataFrame, target_path: Optional[Path] = None) -> bool:
        """
        保存标准化后的数据

        Args:
            dataframe: 标准化后的DataFrame
            target_path: 目标保存路径（可选，如不指定则使用默认路径）

        Returns:
            是否保存成功

        Raises:
            NotImplementedError: 子类必须实现此方法
        """
        raise NotImplementedError("子类必须实现save()方法")

    def process(self, **kwargs) -> bool:
        """
        完整的处理流程：读取 -> 标准化 -> 保存

        这是一个模板方法，定义了完整的处理流程。
        子类通常不需要重写此方法，只需实现read()、standardize()、save()即可。

        Args:
            **kwargs: 处理参数

        Returns:
            是否处理成功
        """
        try:
            # 1. 读取原始数据
            raw_data = self.read(**kwargs)

            # 2. 标准化数据格式
            dataframe = self.standardize(raw_data)

            # 3. 保存数据
            success = self.save(dataframe)

            return success

        except Exception as e:
            raise RuntimeError(f"数据处理失败: {e}") from e

    def validate_dataframe(self, df: pd.DataFrame) -> bool:
        """
        验证DataFrame是否符合标准格式

        Args:
            df: 待验证的DataFrame

        Returns:
            是否符合标准格式

        Raises:
            ValueError: 如果格式不符合要求
        """
        required_columns = [
            "datetime",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "symbol",
            "interval",
        ]

        # 检查必需列是否存在
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            raise ValueError(f"DataFrame缺少必需列: {missing_columns}")

        # 检查数据类型
        if not pd.api.types.is_datetime64_any_dtype(df["datetime"]):
            raise ValueError("datetime列必须是datetime类型")

        numeric_columns = ["open", "high", "low", "close", "volume"]
        for col in numeric_columns:
            if not pd.api.types.is_numeric_dtype(df[col]):
                raise ValueError(f"{col}列必须是数值类型")

        return True


# ==============================================================================
# 第2部分：北证数据解码器（原bj_decoder.py）
# ==============================================================================


class BjStockDecoder:
    """北证股票数据解码器

    基于pytdx的源码分析实现，支持读取北证市场的通达信二进制数据文件。

    二进制格式（通过分析pytdx源码得出）：
    - 格式字符串: '<IIIIIfII'
    - 字段：日期(I), 开盘(I), 最高(I), 最低(I), 收盘(I), 成交额(f), 成交量(I), 保留(I)
    - 每条记录: 32字节

    系数转换（参考上证A股）：
    - 价格系数: 0.01 (价格需要除以100)
    - 成交量系数: 0.01 (成交量需要除以100)
    """

    # 日线二进制格式
    DAY_FORMAT = "<IIIIIfII"  # 小端序，8个字段
    DAY_SIZE = struct.calcsize(DAY_FORMAT)  # 32字节

    # 分钟线二进制格式（5分钟线和1分钟线）
    MIN_FORMAT = "<HHfffffII"  # 小端序，日期(H), 时间(H), OHLC(4个f), 成交额(f), 成交量(I), 保留(I)
    MIN_SIZE = struct.calcsize(MIN_FORMAT)  # 32字节

    # 北证A股系数（参考上证/深证A股）
    PRICE_COEFFICIENT = 0.01  # 价格 / 100（仅日线需要）
    VOLUME_COEFFICIENT = 0.01  # 成交量 / 100（仅日线需要）

    def __init__(self):
        """初始化解码器"""
        self.logger = logging.getLogger(__name__)

    def read_day_file(self, file_path: Path) -> pd.DataFrame:
        """读取北证日线数据文件.

        Args:
            file_path: 数据文件路径

        Returns:
            DataFrame: 标准化的OHLCV数据
        """
        try:
            if not file_path.exists():
                raise FileNotFoundError(f"文件不存在: {file_path}")

            # 读取二进制数据
            with open(file_path, "rb") as f:
                content = f.read()

            # 解析记录（日线格式）
            records = self._unpack_day_records(content)

            if not records:
                self.logger.warning("文件为空或格式错误: %s", file_path)
                return pd.DataFrame()

            # 转换为DataFrame
            df = self._records_to_dataframe(records)

            self.logger.info("成功读取 %d 条记录: %s", len(df), file_path.name)
            return df

        except Exception as e:
            self.logger.error("读取文件失败: %s, 错误: %s", file_path, e)
            raise

    def _unpack_day_records(self, data: bytes) -> List[Tuple]:
        """解析日线二进制数据为记录列表.

        Args:
            data: 二进制数据

        Returns:
            List[Tuple]: 记录列表
        """
        records = []
        record_struct = struct.Struct(self.DAY_FORMAT)

        # 按32字节一条记录解析
        for offset in range(0, len(data), self.DAY_SIZE):
            if offset + self.DAY_SIZE > len(data):
                # 剩余数据不足一条记录，跳过
                break

            try:
                record = record_struct.unpack_from(data, offset)
                records.append(record)
            except struct.error as e:
                self.logger.warning("解析日线记录失败，offset=%d: %s", offset, e)
                continue

        return records

    def _unpack_min_records(self, data: bytes) -> List[Tuple]:
        """解析分钟线二进制数据为记录列表.

        Args:
            data: 二进制数据

        Returns:
            List[Tuple]: 记录列表
        """
        records = []
        record_struct = struct.Struct(self.MIN_FORMAT)

        # 按32字节一条记录解析
        for offset in range(0, len(data), self.MIN_SIZE):
            if offset + self.MIN_SIZE > len(data):
                # 剩余数据不足一条记录，跳过
                break

            try:
                record = record_struct.unpack_from(data, offset)
                records.append(record)
            except struct.error as e:
                self.logger.warning("解析分钟线记录失败，offset=%d: %s", offset, e)
                continue

        return records

    def _records_to_dataframe(self, records: List[Tuple]) -> pd.DataFrame:
        """将记录列表转换为DataFrame.

        Args:
            records: 记录列表，每条记录格式：
                (日期, 开盘, 最高, 最低, 收盘, 成交额, 成交量, 保留)

        Returns:
            DataFrame: 标准化的OHLCV数据
        """
        data = []

        for record in records:
            # 解析字段
            date_int = record[0]  # 例如: 20250101
            open_price = record[1] * self.PRICE_COEFFICIENT
            high_price = record[2] * self.PRICE_COEFFICIENT
            low_price = record[3] * self.PRICE_COEFFICIENT
            close_price = record[4] * self.PRICE_COEFFICIENT
            amount = record[5]  # 成交额（元）
            volume = record[6] * self.VOLUME_COEFFICIENT  # 成交量（手）
            # record[7] 是保留字段，忽略

            # 转换日期格式: 20250101 -> 2025-01-01
            date_str = str(date_int)
            if len(date_str) == 8:
                date_formatted = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
            else:
                # 日期格式异常，跳过
                self.logger.warning("日期格式异常: %d", date_int)
                continue

            data.append(
                {
                    "date": date_formatted,
                    "open": open_price,
                    "high": high_price,
                    "low": low_price,
                    "close": close_price,
                    "amount": amount,
                    "volume": volume,
                }
            )

        # 创建DataFrame
        df = pd.DataFrame(data)

        if not df.empty:
            # 转换日期为datetime
            df["datetime"] = pd.to_datetime(df["date"], errors="coerce")
            # 删除无效日期
            df = df[df["datetime"].notna()].copy()
            # 设置索引
            df = df.set_index("datetime")
            # 只返回需要的列
            return cast(pd.DataFrame, df[["open", "high", "low", "close", "amount", "volume"]])

        return df

    def _parse_min_date(self, num: int) -> Tuple[int, int, int]:
        """解析分钟线日期编码.

        编码规则（通过pytdx源码分析）：
        year = num // 2048 + 2004
        month = (num % 2048) // 100
        day = (num % 2048) % 100

        Args:
            num: 日期编码

        Returns:
            (year, month, day)
        """
        year = num // 2048 + 2004
        month = (num % 2048) // 100
        day = (num % 2048) % 100
        return year, month, day

    def _parse_min_time(self, num: int) -> Tuple[int, int]:
        """解析分钟线时间编码.

        编码规则：从0点开始的分钟数
        hour = num // 60
        minute = num % 60

        Args:
            num: 时间编码（分钟数）

        Returns:
            (hour, minute)
        """
        hour = num // 60
        minute = num % 60
        return hour, minute

    def _min_records_to_dataframe(self, records: List[Tuple]) -> pd.DataFrame:
        """将分钟线记录列表转换为DataFrame.

        Args:
            records: 记录列表，每条记录格式：
                (日期编码(H), 时间编码(H), 开盘(f), 最高(f), 最低(f), 收盘(f), 成交额(f), 成交量(I), 保留(I))

        Returns:
            DataFrame: 标准化的OHLCV数据
        """
        data = []

        for record in records:
            # 解析字段
            date_code = record[0]
            time_code = record[1]
            open_price = record[2]  # 分钟线价格已经是正确值，不需要系数
            high_price = record[3]
            low_price = record[4]
            close_price = record[5]
            amount = record[6]  # 成交额
            volume = record[7]  # 成交量（分钟线是股数，不是手数）
            # record[8] 是保留字段，忽略

            # 解析日期和时间
            try:
                year, month, day = self._parse_min_date(date_code)
                hour, minute = self._parse_min_time(time_code)

                # 构建datetime字符串
                datetime_str = f"{year:04d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}:00"

                data.append(
                    {
                        "date": datetime_str,
                        "open": open_price,
                        "high": high_price,
                        "low": low_price,
                        "close": close_price,
                        "amount": amount,
                        "volume": volume,
                    }
                )
            except Exception as e:
                self.logger.warning(
                    "解析分钟线记录失败: date=%d, time=%d, %s", date_code, time_code, e
                )
                continue

        # 创建DataFrame
        df = pd.DataFrame(data)

        if not df.empty:
            # 转换日期为datetime
            df["datetime"] = pd.to_datetime(df["date"], errors="coerce")
            # 删除无效日期
            df = df[df["datetime"].notna()].copy()
            # 设置索引
            df = df.set_index("datetime")
            # 只返回需要的列
            return cast(pd.DataFrame, df[["open", "high", "low", "close", "amount", "volume"]])

        return df

    def read_5min_file(self, file_path: Path) -> pd.DataFrame:
        """读取北证5分钟线数据文件.

        Args:
            file_path: 数据文件路径

        Returns:
            DataFrame: 标准化的OHLCV数据
        """
        try:
            if not file_path.exists():
                raise FileNotFoundError(f"文件不存在: {file_path}")

            # 读取二进制数据
            with open(file_path, "rb") as f:
                content = f.read()

            # 解析记录（分钟线格式）
            records = self._unpack_min_records(content)

            if not records:
                self.logger.warning("文件为空或格式错误: %s", file_path)
                return pd.DataFrame()

            # 转换为DataFrame
            df = self._min_records_to_dataframe(records)

            self.logger.info("成功读取 %d 条5分钟线记录: %s", len(df), file_path.name)
            return df

        except Exception as e:
            self.logger.error("读取5分钟线文件失败: %s, 错误: %s", file_path, e)
            raise

    def read_1min_file(self, file_path: Path) -> pd.DataFrame:
        """读取北证1分钟线数据文件.

        Args:
            file_path: 数据文件路径

        Returns:
            DataFrame: 标准化的OHLCV数据
        """
        try:
            if not file_path.exists():
                raise FileNotFoundError(f"文件不存在: {file_path}")

            # 读取二进制数据
            with open(file_path, "rb") as f:
                content = f.read()

            # 解析记录（分钟线格式）
            records = self._unpack_min_records(content)

            if not records:
                self.logger.warning("文件为空或格式错误: %s", file_path)
                return pd.DataFrame()

            # 转换为DataFrame
            df = self._min_records_to_dataframe(records)

            self.logger.info("成功读取 %d 条1分钟线记录: %s", len(df), file_path.name)
            return df

        except Exception as e:
            self.logger.error("读取1分钟线文件失败: %s, 错误: %s", file_path, e)
            raise


# ==============================================================================
# 第3部分：通达信二进制数据读取器（原tdx_reader.py）
# ==============================================================================


class TdxBinaryReader(BaseReader):
    """通达信二进制数据读取器

    读取通达信软件本地保存的二进制K线数据文件，并标准化保存为Parquet格式。

    支持的数据类型：
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
    DATA_TYPE_MAPPING = {
        "day": {"interval": "1d", "subdir": "lday", "ext": ".day"},
        "5min": {"interval": "5m", "subdir": "fzline", "ext": ".lc5"},
        "1min": {"interval": "1m", "subdir": "minline", "ext": ".lc1"},
    }

    def __init__(self, source_path: Optional[Path] = None):
        """
        初始化通达信数据读取器

        Args:
            source_path: 通达信软件根目录（如不指定则从配置读取）
        """
        # 延迟导入避免循环依赖
        from .data_module import config_manager
        from .data_quality import StorageManager

        if source_path is None:
            source_path = config_manager.get_tdx_reader_root_dir()
            if source_path is None:
                raise ValueError("通达信根目录未配置")

        super().__init__(source_path)

        self.logger = logging.getLogger(__name__)
        self.storage_manager = StorageManager()
        # 不再使用 mootdx Reader，改用 tdx_asyncio 的异步读取器
        # 北证数据解码器（tdx_asyncio不支持北证，使用自定义解码器）
        self.bj_decoder = BjStockDecoder()
        self._last_save_metrics: Dict[str, Any] = {}
        self._last_standardize_rows: int = 0

    async def read(
        self,
        symbol: str,
        data_type: str = "day",
        market: str = "sh",
    ) -> Any:
        """
        读取通达信二进制数据

        Args:
            symbol: 品种代码（6位）
            data_type: 数据类型（'day', '5min', '1min'）
            market: 市场代码（'sh', 'sz', 'bj'）

        Returns:
            读取的原始数据

        Raises:
            ValueError: 参数不合法
            FileNotFoundError: 数据文件不存在
        """
        # 验证参数
        if data_type not in self.DATA_TYPE_MAPPING:
            raise ValueError(
                f"不支持的数据类型: {data_type}, "
                f"支持的类型: {list(self.DATA_TYPE_MAPPING.keys())}"
            )

        if market not in self.MARKET_CODES:
            raise ValueError(
                f"不支持的市场代码: {market}, " f"支持的市场: {list(self.MARKET_CODES.keys())}"
            )

        # 构建文件路径
        type_info = self.DATA_TYPE_MAPPING[data_type]
        subdir = type_info["subdir"]
        ext = type_info["ext"]

        # 路径格式: {tdx_root}/vipdoc/{market}/{subdir}/{market}{symbol}{ext}
        # 注意：通达信的文件名格式是 {market}{symbol}{ext}，例如 sh600000.day
        data_file = self.source_path / "vipdoc" / market / subdir / f"{market}{symbol}{ext}"

        if not data_file.exists():
            raise FileNotFoundError(f"数据文件不存在: {data_file}")

        try:
            # 判断是否为北证市场，使用不同的解码器
            if market == "bj":
                # 使用自定义北证解码器（直接同步调用，worker进程不阻塞主循环）
                if data_type == "day":
                    df = self.bj_decoder.read_day_file(data_file)
                elif data_type == "5min":
                    df = self.bj_decoder.read_5min_file(data_file)
                elif data_type == "1min":
                    df = self.bj_decoder.read_1min_file(data_file)
                else:
                    raise ValueError(f"不支持的数据类型: {data_type}")

                self.logger.info("使用北证解码器读取: %s", data_file.name)
            else:
                # 使用 tdx_asyncio 异步读取器读取上证/深证数据
                if data_type == "day":
                    df = await read_day_data(data_file)
                elif data_type == "1min":
                    df = await read_minute_data(data_file)
                elif data_type == "5min":
                    df = await read_lc5_data(data_file)
                else:
                    raise ValueError(f"不支持的数据类型: {data_type}")

            if df is None or df.empty:
                return pd.DataFrame()

            # 添加元数据
            df.attrs["symbol"] = symbol
            df.attrs["data_type"] = data_type
            df.attrs["market"] = market
            df.attrs["interval"] = type_info["interval"]

            return df

        except Exception as e:
            self.logger.error("读取通达信数据失败: %s, 错误: %s", data_file, e)
            raise

    def standardize(self, raw_data: Any) -> pd.DataFrame:
        """同步标准化入口，兼容旧调用"""
        return self._standardize_impl(raw_data)

    async def standardize_async(self, raw_data: Any) -> pd.DataFrame:
        """异步标准化，避免阻塞事件循环

        v3.3: 改为直接调用，worker进程中不需要线程池
        """
        return self._standardize_impl(raw_data)

    def _standardize_impl(self, raw_data: Any) -> pd.DataFrame:
        if raw_data is None or (isinstance(raw_data, pd.DataFrame) and raw_data.empty):
            return pd.DataFrame()

        df = raw_data.copy()

        symbol = df.attrs.get("symbol", "")
        interval = df.attrs.get("interval", "1d")

        column_mapping = {
            "date": "datetime",
            "time": "datetime",
            "vol": "volume",
            "amount": "turnover",
        }

        rename_map: Dict[str, str] = {}
        for old_name, new_name in column_mapping.items():
            if old_name in df.columns:
                rename_map[old_name] = new_name

        if rename_map:
            df = df.rename(columns=rename_map)

        if "datetime" not in df.columns:
            if df.index.name is None or "date" in str(df.index.name).lower():
                df = df.reset_index()
                if len(df.columns) > 0:
                    first_col = str(df.columns[0])
                    if first_col not in ["datetime", "open", "high"]:
                        df = df.rename(columns={first_col: "datetime"})

        if df.columns.duplicated().any():
            self.logger.warning(
                "检测到重复列名: %s, 正在去重", df.columns[df.columns.duplicated()].tolist()
            )
            df = df.loc[:, ~df.columns.duplicated()]

        if "datetime" in df.columns:
            df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce")
            df = df[df["datetime"].notna()].copy()
        else:
            df["datetime"] = pd.to_datetime(df.index, errors="coerce")
            df = df[df["datetime"].notna()].copy()

        numeric_columns = ["open", "high", "low", "close", "volume"]
        for col in numeric_columns:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        df["symbol"] = symbol
        df["interval"] = interval

        if "datetime" in df.columns and isinstance(df, pd.DataFrame):
            df = df.sort_values("datetime")
            df = df.drop_duplicates(subset=["datetime"], keep="last")
            df = df.reset_index(drop=True)

        try:
            if isinstance(df, pd.DataFrame):
                self.validate_dataframe(df)
        except ValueError as e:
            self.logger.error("数据格式验证失败: %s", e)
            raise

        if isinstance(df, pd.DataFrame):
            self._last_standardize_rows = len(df)
            return df

        self._last_standardize_rows = 0
        return pd.DataFrame()

    def get_last_standardize_rows(self) -> int:
        return self._last_standardize_rows

    def get_last_save_metrics(self) -> Dict[str, Any]:
        return self._last_save_metrics

    def save(
        self, dataframe: pd.DataFrame, target_path: Optional[Path] = None, merge: bool = True
    ) -> bool:
        """
        保存标准化后的数据到Parquet格式

        Args:
            dataframe: 标准化后的DataFrame
            target_path: 目标保存路径（不使用，由StorageManager管理路径）
            merge: 是否使用增量更新模式（True=合并去重，False=覆盖）

        Returns:
            是否保存成功
        """
        if dataframe.empty:
            self.logger.warning("数据为空，跳过保存")
            self._last_save_metrics = {"mode": "skip_empty", "new_rows": 0}
            return False

        success = False
        file_path: Optional[Path] = None
        save_metrics: Dict[str, Any] = {
            "mode": "merge" if merge else "overwrite",
            "new_rows": int(len(dataframe)),
        }

        try:
            # 提取品种和周期信息
            symbol = dataframe["symbol"].iloc[0]
            interval = dataframe["interval"].iloc[0]
            save_metrics.update({"symbol": symbol, "interval": interval})

            if merge:
                query_start = time.perf_counter()
                existing_df = self.storage_manager.query_kline(symbol, interval)
                save_metrics["query_ms"] = (time.perf_counter() - query_start) * 1000
                existing_rows = int(len(existing_df)) if existing_df is not None else 0
                save_metrics["existing_rows"] = existing_rows

                if existing_df is not None and not existing_df.empty:
                    existing_df = existing_df.reset_index(drop=True)
                    dataframe = dataframe.reset_index(drop=True)

                    merge_start = time.perf_counter()
                    merged_df = pd.concat([existing_df, dataframe], ignore_index=True)
                    if "datetime" in merged_df.columns:
                        merged_df = merged_df.sort_values("datetime")
                        merged_df = merged_df.drop_duplicates(subset=["datetime"], keep="last")
                        merged_df = merged_df.reset_index(drop=True)
                    save_metrics["merge_ms"] = (time.perf_counter() - merge_start) * 1000

                    write_start = time.perf_counter()
                    file_path = self.storage_manager.save_kline(symbol, interval, merged_df)
                    save_metrics["write_ms"] = (time.perf_counter() - write_start) * 1000
                    save_metrics["result_rows"] = int(len(merged_df))

                    if file_path:
                        self.logger.info(
                            "数据增量保存成功: %s %s (合并模式，合并后共 %d 条)",
                            symbol,
                            interval,
                            len(merged_df),
                        )
                        success = True
                    else:
                        self.logger.error("数据增量保存失败: %s %s", symbol, interval)
                        success = False
                else:
                    write_start = time.perf_counter()
                    file_path = self.storage_manager.save_kline(symbol, interval, dataframe)
                    save_metrics["write_ms"] = (time.perf_counter() - write_start) * 1000
                    save_metrics["result_rows"] = int(len(dataframe))

                    if file_path:
                        self.logger.info("数据保存成功: %s %s (首次保存)", symbol, interval)
                        success = True
                    else:
                        self.logger.error("数据保存失败: %s %s", symbol, interval)
                        success = False
            else:
                write_start = time.perf_counter()
                file_path = self.storage_manager.save_kline(symbol, interval, dataframe)
                save_metrics["write_ms"] = (time.perf_counter() - write_start) * 1000
                save_metrics["existing_rows"] = 0
                save_metrics["result_rows"] = int(len(dataframe))

                if file_path:
                    self.logger.info(
                        "数据保存成功: %s %s -> %s (覆盖模式)", symbol, interval, file_path
                    )
                    success = True
                else:
                    self.logger.error("数据保存失败: %s %s", symbol, interval)
                    success = False

        except Exception as e:
            import traceback

            error_detail = traceback.format_exc()
            self.logger.error("❌ 保存数据时出错: %s", e, exc_info=True)
            print(f"❌ 保存失败: {e}")
            print(error_detail)
            save_metrics["error"] = str(e)
            success = False

        self._last_save_metrics = save_metrics
        return success

    async def save_async(
        self, dataframe: pd.DataFrame, target_path: Optional[Path] = None, merge: bool = True
    ) -> bool:
        """异步保存包装，避免阻塞事件循环

        v3.3: 改为直接调用，worker进程中不需要线程池
        """
        return self.save(dataframe, target_path, merge)

    async def read_batch(
        self,
        symbols: List[str],
        data_type: str = "day",
        market: str = "sh",
    ) -> Dict[str, pd.DataFrame]:
        """
        批量读取多个品种的数据

        Args:
            symbols: 品种代码列表
            data_type: 数据类型
            market: 市场代码

        Returns:
            品种代码到DataFrame的映射字典
        """
        results = {}

        for symbol in symbols:
            try:
                df = await self.read(symbol=symbol, data_type=data_type, market=market)
                if not df.empty:
                    results[symbol] = df
            except Exception as e:
                self.logger.error("读取 %s 失败: %s", symbol, e)

        self.logger.info("批量读取完成: 成功 %d/%d", len(results), len(symbols))
        return results


# ==============================================================================
# 第4部分：TDX动态执行器（原tdx_dynamic_executor.py）
# ==============================================================================


# ==================== 模块级worker函数（可pickle） ====================


class AdjustableAsyncSemaphore:
    """Semaphore with runtime-adjustable (and optional) limit."""

    def __init__(
        self, initial_limit: Optional[int], logger: Optional[logging.Logger] = None
    ) -> None:
        if initial_limit is not None and initial_limit <= 0:
            raise ValueError("initial_limit must be positive when provided")
        self._limit: Optional[int] = initial_limit
        self._in_use = 0
        self._cond = asyncio.Condition()
        self._logger = logger

    async def __aenter__(self):
        await self.acquire()
        return None

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.release()

    async def acquire(self) -> None:
        if self._limit is None:
            self._in_use += 1
            return
        async with self._cond:
            while self._in_use >= self._limit:
                await self._cond.wait()
            self._in_use += 1

    async def release(self) -> None:
        if self._limit is None:
            if self._in_use > 0:
                self._in_use -= 1
            return
        async with self._cond:
            if self._in_use > 0:
                self._in_use -= 1
            self._cond.notify_all()

    async def set_limit(self, new_limit: Optional[int]) -> Tuple[Optional[int], Optional[int], int]:
        if new_limit is not None and new_limit <= 0:
            new_limit = 1
        async with self._cond:
            old = self._limit
            self._limit = new_limit
            in_use = self._in_use
            self._cond.notify_all()
        if self._logger:
            self._logger.debug(
                "AdjustableAsyncSemaphore limit change: %s -> %s (in_use=%d)",
                old,
                new_limit,
                in_use,
            )
        return old, new_limit, in_use

    def snapshot(self) -> Dict[str, Optional[int]]:
        return {"limit": self._limit, "in_use": self._in_use}


def _tdx_worker_process(
    worker_id: int,
    task_queue,  # 🆕 v3.6: 改为从共享任务队列拉取任务
    data_type: str,
    market: str,
    tdx_dir_str: str,
    result_queue,
    metrics_queue,  # 🆕 v3.5: 独立的监控指标队列
    stop_event,
    config_queue=None,
    initial_coroutines: Optional[int] = None,
):
    """Worker进程入口点（模块级函数，可以被pickle）

    v3.5改进：分离数据队列和监控队列，防止队列阻塞
    v3.6改进：从共享task_queue拉取任务，支持动态进程管理
    """
    import sys
    from pathlib import Path
    import asyncio

    sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

    # 在worker进程中创建reader实例
    worker_reader = TdxBinaryReader(Path(tdx_dir_str))

    # 运行worker的异步逻辑
    asyncio.run(
        _tdx_worker_async(
            worker_id,
            worker_reader,
            task_queue,  # 🆕 v3.6: 传递共享任务队列
            data_type,
            market,
            result_queue,
            metrics_queue,  # 🆕 传递独立的监控队列
            stop_event,
            config_queue=config_queue,
            initial_coroutines=initial_coroutines,
        )
    )


async def _tdx_worker_async(
    worker_id: int,
    reader,
    task_queue,  # 🆕 v3.6: 改为从共享任务队列拉取任务
    data_type: str,
    market: str,
    result_queue,
    metrics_queue,  # 🆕 v3.5: 独立的监控指标队列
    stop_event,
    config_queue=None,
    initial_coroutines: Optional[int] = None,
):
    """Worker的异步处理逻辑（模块级函数）

    v3.5改进：
    - 使用独立的metrics_queue传递监控指标
    - 数据结果使用非阻塞put+重试机制
    - 彻底防止队列阻塞导致的死锁

    v3.6改进：
    - 从共享task_queue循环拉取任务
    - 支持运行时动态增减进程
    """
    import logging
    import time
    import queue

    # ✅ 配置子进程日志，接入LogHub统一路由
    logger = _configure_subprocess_logging(worker_id, task_type="tdx_read")

    logger.info("[Worker-%d] 启动，从共享任务队列拉取任务", worker_id)

    # 🔧 v3.6: 从共享任务队列循环拉取任务
    logger.info("[Worker-%d] 启动全并发模式，从共享队列拉取任务", worker_id)

    # 🆕 v3.5: 使用独立的metrics_queue启动lag监控
    # ✅ 修复：使用绝对导入，避免多进程中的导入失败
    from backend.infrastructure.data_module_vnpy.load_balancer import LagMonitor

    lag_monitor_task = asyncio.create_task(
        LagMonitor.monitor_and_report(
            metrics_queue=metrics_queue,  # 🆕 使用独立的监控队列
            worker_id=worker_id,
            stop_event=stop_event,
            interval_seconds=0.3,
        )
    )
    logger.info(f"[Worker-{worker_id}] ✅ 已启动lag监控协程（使用独立metrics_queue）")

    # 🆕 v3.6: 跟踪已处理任务数
    processed_count = 0

    # 🆕 v3.5: 非阻塞put辅助函数（防止队列满时阻塞）
    async def _safe_put_result(msg: tuple, max_retries: int = 5):
        """非阻塞put+重试，防止队列满时阻塞worker进程"""
        for attempt in range(max_retries):
            try:
                result_queue.put_nowait(msg)
                return True
            except Exception:
                if attempt < max_retries - 1:
                    await asyncio.sleep(0.02)  # 20ms后重试
                else:
                    logger.warning(f"[Worker-{worker_id}] 队列满，丢弃结果: {msg[0]}")
                    return False
        return False

    async def _execute_symbol(symbol: str):
        if stop_event.is_set():
            return

        start_time = time.perf_counter()
        stage_metrics: Dict[str, Any] = {"symbol": symbol}
        try:
            # 1. 读取TDX数据
            read_start = time.perf_counter()
            raw_df = await reader.read(symbol=symbol, data_type=data_type, market=market)
            stage_metrics["read_ms"] = (time.perf_counter() - read_start) * 1000
            stage_metrics["raw_rows"] = int(len(raw_df)) if hasattr(raw_df, "__len__") else 0

            if raw_df.empty:
                stage_metrics["reason"] = "empty_raw"
                # 🆕 v3.5: 使用非阻塞put+重试
                await _safe_put_result(
                    (symbol, False, stage_metrics, time.perf_counter() - start_time)
                )
                return

            # 2. 标准化数据（添加symbol和interval列）
            standardize_start = time.perf_counter()
            standardized_df = await reader.standardize_async(raw_df)
            stage_metrics["standardize_ms"] = (time.perf_counter() - standardize_start) * 1000
            stage_metrics["standardized_rows"] = reader.get_last_standardize_rows()

            if standardized_df.empty:
                stage_metrics["reason"] = "standardize_empty"
                # 🆕 v3.5: 使用非阻塞put+重试
                await _safe_put_result(
                    (symbol, False, stage_metrics, time.perf_counter() - start_time)
                )
                return

            # 3. 保存标准化数据（异步包装避免阻塞事件循环）
            save_start = time.perf_counter()
            save_result = await reader.save_async(
                standardized_df,
                None,  # target_path
                True,  # merge=True (增量更新模式)
            )
            stage_metrics["save_ms"] = (time.perf_counter() - save_start) * 1000
            stage_metrics["save_details"] = reader.get_last_save_metrics()

            if save_result:
                # 🆕 v3.5: 使用非阻塞put+重试
                await _safe_put_result(
                    (symbol, True, stage_metrics, time.perf_counter() - start_time)
                )
            else:
                stage_metrics["reason"] = "save_failed"
                # 🆕 v3.5: 使用非阻塞put+重试
                await _safe_put_result(
                    (symbol, False, stage_metrics, time.perf_counter() - start_time)
                )

        except Exception as e:
            stage_metrics["reason"] = "exception"
            stage_metrics["error"] = str(e)
            # 🆕 v3.5: 使用非阻塞put+重试
            await _safe_put_result((symbol, False, stage_metrics, time.perf_counter() - start_time))

    # 🆕 v3.6: 从共享任务队列循环拉取任务
    empty_count = 0  # 连续空队列计数
    max_empty_before_exit = 3  # 连续3次空队列后退出

    logger.info(f"[Worker-{worker_id}] 开始从共享队列拉取任务...")

    while not stop_event.is_set():
        try:
            # 从队列拉取任务（超时1秒）
            symbol = task_queue.get(timeout=1.0)
            empty_count = 0  # 重置空队列计数

            # 执行任务
            await _execute_symbol(symbol)
            processed_count += 1

            # 每处理100个任务输出一次进度
            if processed_count % 100 == 0:
                logger.info(f"[Worker-{worker_id}] 已处理 {processed_count} 个任务")

        except queue.Empty:
            # 队列为空，等待新任务
            empty_count += 1
            if empty_count >= max_empty_before_exit:
                # 连续多次空队列，可能没有更多任务了
                logger.info(f"[Worker-{worker_id}] 队列连续{empty_count}次为空，准备退出")
                break
            await asyncio.sleep(0.1)  # 短暂等待
        except Exception as e:
            logger.error(f"[Worker-{worker_id}] 处理任务时发生错误: {e}")
            await asyncio.sleep(0.1)

    # 停止lag监控（使用LagMonitor工具）
    await LagMonitor.cancel_monitor(lag_monitor_task)

    logger.info(f"[Worker-{worker_id}] 完成，共处理 {processed_count} 个任务")


# ==================== 数据类 ====================


@dataclass
class ExecutionResult:
    """执行结果"""

    success: bool
    symbol: str
    message: Optional[str] = None
    duration: float = 0.0
    details: Optional[Dict[str, Any]] = None


class TdxLocalReadTask(LocalProcessingTask):
    """TDX本地读取任务（带资源指标）"""

    def __init__(self, name: str, total_count: int):
        self.total_count = total_count
        super().__init__(name)

    def _define_metrics(self):
        metrics = super()._define_metrics()
        # 依据批量规模估算处理指标
        metrics.estimated_duration = max(0.5, self.total_count / 2000.0)
        metrics.estimated_workers = max(1, min(8, self.total_count // 500 or 1))
        return metrics

    def execute(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """占位执行，用于兼容LoadBalancer接口。"""
        return {
            "task": self.name,
            "total_count": self.total_count,
            "config": config,
        }


class TdxDynamicExecutor:
    """TDX动态执行器 - 支持动态并发调整

    支持：
    1. 每秒监控资源压力
    2. 动态调整协程数（进程数固定）
    3. 详细的调整历史记录
    """

    def __init__(
        self,
        tdx_dir: Path,  # TDX数据目录
        logger: Optional[logging.Logger] = None,
    ):
        self.tdx_dir = tdx_dir
        self.logger = logger or logging.getLogger(__name__)

        # 动态调整配置
        self.adjustment_interval = 0.3  # 0.3秒检查一次（实际调整由LoadBalancer控制）

        # 执行状态
        self.current_processes = 0
        self.current_coroutines_per_process = 0
        self.total_coroutines = 0
        self.adjustment_history = deque(maxlen=1800)
        self.last_run_summary: Optional[Dict[str, Any]] = None

        # LoadBalancer在主进程创建（用于调整监控）
        # ✅ 修复：使用绝对导入，避免多进程中的导入失败
        from backend.infrastructure.data_module_vnpy.load_balancer import get_load_balancer

        self.load_balancer = get_load_balancer()

        # 协程性能监控发布器（event_engine需要在使用时注入）
        from .data_module import AsyncioMetricsPublisher

        self.asyncio_publisher = AsyncioMetricsPublisher(event_engine=None)

    async def execute_batch(
        self,
        symbols: List[str],
        data_type: str = "day",
        market: str = "sh",
        initial_processes: int = 2,
        initial_coroutines: int = 20,
        enable_throttling: bool = True,
    ) -> Dict[str, ExecutionResult]:
        """
        执行批量读取（支持动态调整）

        Args:
            symbols: 品种列表
            data_type: 数据类型
            market: 市场代码
            initial_processes: 初始进程数（固定不变）
            initial_coroutines: 初始协程数（动态调整）

        Returns:
            {symbol: ExecutionResult}
        """
        total_count = len(symbols)
        overall_start = time.time()
        self.logger.info("=" * 80)
        self.logger.info("🚀 TdxDynamicExecutor 开始执行")
        self.logger.info("  - 品种数: %d", total_count)
        throttle_label = str(initial_coroutines) if enable_throttling else "∞"
        self.logger.info("  - 初始配置: %d进程 × %s协程", initial_processes, throttle_label)
        if enable_throttling:
            self.logger.info("  - 动态调整: 每%.1f秒", self.adjustment_interval)
        else:
            self.logger.info("  - 动态调整: 已禁用 (全并发读取)")
        self.logger.info("=" * 80)

        # 初始化配置
        self.current_processes = initial_processes
        if enable_throttling:
            self.current_coroutines_per_process = initial_coroutines
            self.total_coroutines = initial_processes * initial_coroutines
        else:
            self.current_coroutines_per_process = 0
            self.total_coroutines = total_count

        # 创建任务
        task = TdxLocalReadTask("tdx_batch_read", total_count)

        # 🔍 测量事件循环延迟（批量任务开始前）
        if hasattr(self, "asyncio_publisher") and self.asyncio_publisher.event_engine:
            await self.asyncio_publisher.measure_and_publish_lag("TdxDynamicExecutor_Start")

        # 🆕 v3.6: 使用动态进程池架构（支持运行时进程增减）
        ctx = multiprocessing.get_context("spawn")
        task_queue = ctx.Queue()  # 🆕 v3.6: 共享任务队列
        result_queue = ctx.Queue(maxsize=5000)  # 数据结果队列（大容量）
        metrics_queue = ctx.Queue(maxsize=200)  # 监控指标队列（独立通道）
        stop_event = ctx.Event()
        config_queue = ctx.Queue() if enable_throttling else None  # 用于传递动态配置

        self.logger.info("📊 队列架构: 任务队列(共享) + 数据队列(5000) + 监控队列(200)")

        # 🆕 v3.6: 将所有任务放入共享队列（而不是预分配）
        for symbol in symbols:
            task_queue.put(symbol)

        self.logger.info(f"📦 任务队列: 已加入{total_count}个品种")

        # 🆕 v3.6: 使用DynamicProcessPool管理进程
        # ✅ 修复：使用绝对导入，避免多进程中的导入失败
        from backend.infrastructure.data_module_vnpy.load_balancer import DynamicProcessPool

        self.pool = DynamicProcessPool(
            initial_processes=initial_processes,
            worker_function=_tdx_worker_process,
            shared_queues={
                "task_queue": task_queue,
                "result_queue": result_queue,
                "metrics_queue": metrics_queue,
            },
            worker_kwargs={
                "data_type": data_type,
                "market": market,
                "tdx_dir_str": str(self.tdx_dir),
                "config_queue": config_queue,
                "initial_coroutines": initial_coroutines if enable_throttling else None,
            },
            logger=self.logger,
        )

        await self.pool.start()
        processes = self.pool.processes  # 保留对进程列表的引用，用于监控

        # 启动动态调整监控（如启用限流）
        adjustment_task: Optional[asyncio.Task]
        if enable_throttling:
            adjustment_task = asyncio.create_task(
                self._adjustment_monitor(task, config_queue, stop_event)
            )
        else:
            adjustment_task = None

        # 🆕 v3.5: 使用专用队列消费协程（最佳实践）
        results = {}
        # ✅ 修复：使用绝对导入，避免多进程中的导入失败
        from backend.infrastructure.data_module_vnpy.load_balancer import LagMonitor

        # 数据结果消费协程
        async def result_consumer():
            """专用协程：高效消费数据结果队列"""
            while any(p.is_alive() for p in processes):
                batch = []
                # 批量读取（最多100个）
                while len(batch) < 100:
                    try:
                        msg = result_queue.get_nowait()
                        batch.append(msg)
                    except queue.Empty:
                        break

                # 批量处理
                for msg in batch:
                    symbol, success, payload, duration = msg
                    message: Optional[str]
                    details: Optional[Dict[str, Any]]
                    if isinstance(payload, dict):
                        details = payload
                        message = payload.get("reason") if not success else None
                    else:
                        details = None
                        message = str(payload) if payload is not None else None

                    results[symbol] = ExecutionResult(
                        success=success,
                        symbol=symbol,
                        message=message,
                        duration=duration,
                        details=details,
                    )

                await asyncio.sleep(0)  # 只让出控制权

        # 监控指标消费协程
        async def metrics_consumer():
            """专用协程：消费监控指标队列"""
            while any(p.is_alive() for p in processes):
                try:
                    while not metrics_queue.empty():
                        msg = metrics_queue.get_nowait()
                        LagMonitor.process_lag_message(msg, self.load_balancer, self.logger)
                except queue.Empty:
                    pass
                except Exception as e:
                    self.logger.debug(f"处理监控指标失败: {e}")

                await asyncio.sleep(0.1)  # 监控指标可以稍慢

        # 启动两个消费协程
        result_task = asyncio.create_task(result_consumer())
        metrics_task = asyncio.create_task(metrics_consumer())

        # 等待消费协程完成
        await asyncio.gather(result_task, metrics_task)

        # 停止监控
        stop_event.set()
        if adjustment_task is not None:
            try:
                await asyncio.wait_for(adjustment_task, timeout=2.0)
            except asyncio.TimeoutError:
                self.logger.warning("调整监控停止超时")

        # 🆕 v3.5: 分别收集剩余结果（两个独立队列）
        # 1. 收集剩余的数据结果
        while not result_queue.empty():
            try:
                msg = result_queue.get_nowait()
                symbol, success, payload, duration = msg
                message: Optional[str]
                details: Optional[Dict[str, Any]]
                if isinstance(payload, dict):
                    details = payload
                    message = payload.get("reason") if not success else None
                else:
                    details = None
                    message = str(payload) if payload is not None else None

                results[symbol] = ExecutionResult(
                    success=success,
                    symbol=symbol,
                    message=message,
                    duration=duration,
                    details=details,
                )
            except queue.Empty:
                break

        # 2. 收集剩余的监控指标
        while not metrics_queue.empty():
            try:
                msg = metrics_queue.get_nowait()
                LagMonitor.process_lag_message(msg, self.load_balancer, self.logger)
            except queue.Empty:
                break

        success_count = sum(1 for r in results.values() if r.success)
        self.logger.info("=" * 80)
        self.logger.info("✅ 执行完成: 成功%d/%d", success_count, total_count)
        self.logger.info("=" * 80)

        duration = time.time() - overall_start
        avg_speed = success_count / duration if duration > 0 else 0.0
        actions = Counter(entry.get("action") for entry in self.adjustment_history)
        per_process_coroutines = self.current_coroutines_per_process if enable_throttling else 0
        self.last_run_summary = {
            "total_symbols": total_count,
            "success": success_count,
            "duration": duration,
            "avg_symbols_per_sec": avg_speed,
            "final_total_coroutines": self.total_coroutines if enable_throttling else None,
            "final_coroutines_per_process": per_process_coroutines if enable_throttling else None,
            "processes": self.current_processes,
            "adjustment_counts": dict(actions),
            "throttling_enabled": enable_throttling,
        }
        total_label = str(self.total_coroutines) if enable_throttling else f"无上限(≈{total_count})"
        per_process_label = str(per_process_coroutines) if enable_throttling else "无上限"
        self.logger.info(
            "📈 运行摘要: 用时%.2fs, 平均%.2f个/秒, 最终并发=%s (每进程=%s), 调整统计=%s",
            duration,
            avg_speed,
            total_label,
            per_process_label,
            dict(actions),
        )

        return results

    async def _adjustment_monitor(
        self, task: TdxLocalReadTask, config_queue, stop_event: "Event"  # MPQueue
    ):
        """动态调整监控循环"""
        adjustment_count = 0
        call_count = 0  # 总调用次数（包括hold）
        start_time = time.time()

        self.logger.info("=" * 80)
        self.logger.info(
            "🚀 动态调整监控启动 (间隔%.3f秒 = %.0fms)",
            self.adjustment_interval,
            self.adjustment_interval * 1000,
        )
        self.logger.info("=" * 80)

        while not stop_event.is_set():
            sleep_start = time.time()
            self.logger.info(
                "⏰ 准备睡眠%.0fms (interval=%.3f)",
                self.adjustment_interval * 1000,
                self.adjustment_interval,
            )
            await asyncio.sleep(self.adjustment_interval)
            sleep_elapsed = (time.time() - sleep_start) * 1000
            self.logger.info("⏰ 实际睡眠%.0fms", sleep_elapsed)

            if stop_event.is_set():
                break

            call_count += 1
            call_timestamp = time.time()
            elapsed_since_start = call_timestamp - start_time

            # v3.3: 使用event_loop_lag指导的并发决策
            try:
                lb_start = time.time()
                decision = self.load_balancer.get_concurrency_decision_with_lag(
                    task=task,
                    current_processes=self.current_processes,
                    current_coroutines=self.current_coroutines_per_process,
                    force_realtime=True,
                )
                lb_elapsed = (time.time() - lb_start) * 1000

                action = decision["action"]
                suggested_coroutines = decision["suggested_coroutines_per_process"]
                suggested_processes = decision["suggested_processes"]  # 🆕 v3.6: 读取建议进程数
                reason = decision["reason"]
                lag_ms = decision["lag_ms"]
                pressure = decision["pressure_score"]

                # 🆕 v3.6: 应用决策（支持运行时动态进程调整）
                new_coroutines_per_process = suggested_coroutines
                new_processes = suggested_processes  # 🆕 v3.6: 使用建议的进程数
                new_coroutines_total = new_processes * new_coroutines_per_process

                # 判断是否需要调整
                need_adjustment = (
                    new_processes != self.current_processes
                    or new_coroutines_per_process != self.current_coroutines_per_process
                )

                if need_adjustment:
                    old_total = self.total_coroutines
                    old_coroutines_per_process = self.current_coroutines_per_process
                    old_processes = self.current_processes

                    # 🆕 v3.6: 调整进程数（如有变化）
                    if new_processes != self.current_processes:
                        self.logger.info(
                            f"🔧 调整进程数: {self.current_processes} → {new_processes}"
                        )
                        await self.pool.adjust_processes(new_processes)
                        self.current_processes = new_processes

                    # 调整协程数（如有变化）
                    if new_coroutines_per_process != self.current_coroutines_per_process:
                        self.logger.info(
                            f"🔧 调整协程数: {self.current_coroutines_per_process} → {new_coroutines_per_process}"
                        )
                        self.current_coroutines_per_process = new_coroutines_per_process
                        self.total_coroutines = new_coroutines_total

                        # 广播新配置到所有worker
                        for _ in range(self.current_processes):
                            config_queue.put(new_coroutines_per_process)

                    adjustment_count += 1

                    self.logger.info(
                        "📊 [调用%d/调整%d] %.1fs ⏱️睡眠%.0fms+LB%.0fms\n"
                        "   决策=%s | 原因: %s\n"
                        "   进程: %d → %d | 协程/进程: %d → %d | 总协程: %d → %d\n"
                        "   延迟: %.1fms | 压力: %.1f",
                        call_count,
                        adjustment_count,
                        elapsed_since_start,
                        sleep_elapsed,
                        lb_elapsed,
                        action,
                        reason,
                        old_processes,
                        new_processes,
                        old_coroutines_per_process,
                        new_coroutines_per_process,
                        old_total,
                        new_coroutines_total,
                        lag_ms,
                        pressure,
                    )
                else:
                    # hold状态也输出，便于观察
                    self.logger.info(
                        "📊 [调用%d] %.1fs ⏱️睡眠%.0fms+LB%.0fms 决策=%s | 协程: %d (不变) | 延迟: %.1fms | 压力: %.1f",
                        call_count,
                        elapsed_since_start,
                        sleep_elapsed,
                        lb_elapsed,
                        action,
                        self.total_coroutines,
                        lag_ms,
                        pressure,
                    )

                self.adjustment_history.append(
                    {
                        "timestamp": call_timestamp,
                        "action": action,
                        "requested_concurrency": new_coroutines_total,
                        "applied_concurrency": self.total_coroutines,
                        "lag_ms": lag_ms,
                        "pressure_score": pressure,
                        "reason": reason,
                        "lb_latency_ms": lb_elapsed,
                        "sleep_elapsed_ms": sleep_elapsed,
                    }
                )

            except Exception as e:
                self.logger.error("动态调整失败: %s", e, exc_info=True)

        elapsed = time.time() - start_time
        self.logger.info("=" * 80)
        self.logger.info(
            "📊 动态调整监控结束: 运行%.1f秒，总调用%d次，成功调整%d次",
            elapsed,
            call_count,
            adjustment_count,
        )
        self.logger.info("   平均调用间隔: %.3f秒", elapsed / call_count if call_count > 0 else 0)
        self.logger.info(
            "   调整成功率: %.1f%%", 100 * adjustment_count / call_count if call_count > 0 else 0
        )
        self.logger.info("=" * 80)


# ==============================================================================
# 模块导出
# ==============================================================================

__all__ = [
    # 基类
    "BaseReader",
    # 解码器
    "BjStockDecoder",
    # 读取器
    "TdxBinaryReader",
    # 执行器
    "TdxDynamicExecutor",
    "ExecutionResult",
]
