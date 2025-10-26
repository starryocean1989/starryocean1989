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
# 第1部分：任务日志记录器（原task_logger.py）
# ==============================================================================

import csv
import os
import time
from datetime import datetime
from typing import Dict, Optional, Tuple
from pathlib import Path


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
        if self.csv_writer:
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
        _global_task_logger = TaskDetailLogger(log_dir)
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

from ..config import config_manager, TdxConfigFileParser

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
        self.logger = logging.getLogger(__name__)

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
            from ..events import DownloadEventPublisher, EventPublisher

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
            from ..cache_manager import DailyCacheManager

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

        架构设计（双进程模式）：
        - 进程1：处理市场0（深圳），单线程，单服务器，单连接，串行请求所有页
        - 进程2：处理市场1（上海），单线程，单服务器，单连接，串行请求所有页
        - 两个进程并行运行，充分利用双核CPU

        Returns:
            包含market列的完整DataFrame
        """
        self.logger.info("步骤1: 获取完整品种缓存（集合D）")
        self.logger.info("→ 双进程模式：市场0和市场1各用独立进程...")

        # 获取最优服务器
        from ..load_balancer import server_pool_manager

        best_servers = server_pool_manager.get_servers()
        self.logger.info("  ✓ 获取到 %d 个已排序的最优服务器", len(best_servers))

        # 为两个市场分配服务器（前2个最快的）
        if len(best_servers) < 2:
            raise RuntimeError(f"可用服务器不足（需要2个，实际{len(best_servers)}个）")

        market_servers = {
            0: best_servers[0],  # 市场0（深圳）用最快的服务器
            1: best_servers[1],  # 市场1（上海）用第二快的服务器
        }

        self.logger.info("  → 深圳市场：%s:%s", market_servers[0][0], market_servers[0][1])
        self.logger.info("  → 上海市场：%s:%s", market_servers[1][0], market_servers[1][1])

        # 使用multiprocessing创建共享内存（使用spawn上下文）
        from multiprocessing import get_context
        import time

        self.logger.info("  创建multiprocessing上下文（spawn模式）")
        ctx = get_context("spawn")
        manager = ctx.Manager()
        self.logger.info("  ✓ Manager创建成功")
        shared_results = manager.dict()  # 共享字典：{market: [stocks]}

        # 创建2个进程
        processes = []
        for market in [0, 1]:
            p = ctx.Process(
                target=self._fetch_market_in_process,
                args=(market, market_servers[market], shared_results),
                name=f"MarketFetch-{market}",
            )
            p.start()
            processes.append(p)
            market_name = "深圳" if market == 0 else "上海"
            self.logger.info("  🚀 %s市场进程已启动（PID: %s）", market_name, p.pid)

        # 等待所有进程完成
        self.logger.info("  ⏳ 等待2个进程完成...")
        start_time = time.time()

        for i, p in enumerate(processes):
            p.join()
            market_name = "深圳" if i == 0 else "上海"
            self.logger.info("  ✅ %s市场进程完成", market_name)

        elapsed = time.time() - start_time
        self.logger.info("  ✅ 双进程获取完成，耗时: %.1f秒", elapsed)

        # 从共享内存提取结果
        market_data = dict(shared_results)

        if not market_data:
            raise RuntimeError("所有进程均未返回数据")

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
            from ..cache_manager import DailyCacheManager

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
    ) -> bool:
        """将 IPO 数据写入品种列表缓存，并删除未上市品种

        Args:
            ipo_data: {symbol: ipo_date} 映射（ipo_date 是 date 对象）
            unlisted_symbols: 未上市品种代码列表

        Returns:
            是否成功更新
        """
        try:
            # 1. 加载当前缓存
            classified, _ = self.load_from_cache_with_validation()
            if not classified:
                self.logger.error("无法加载品种列表缓存")
                return False

            # 2. 更新 ipo_date 字段
            updated_count = 0
            for category, stocks in classified.items():
                for stock in stocks:
                    symbol = stock.get("code")
                    if symbol in ipo_data:
                        # 将 date 对象转换为字符串
                        ipo_date = ipo_data[symbol]
                        if hasattr(ipo_date, "strftime"):
                            stock["ipo_date"] = ipo_date.strftime("%Y-%m-%d")
                        else:
                            stock["ipo_date"] = str(ipo_date)
                        updated_count += 1

            self.logger.info(f"✓ 已更新 {updated_count} 个品种的 IPO 日期")

            # 3. 删除未上市品种
            removed_count = 0
            unlisted_set = set(unlisted_symbols)
            for category in classified:
                original_count = len(classified[category])
                classified[category] = [
                    stock for stock in classified[category] if stock.get("code") not in unlisted_set
                ]
                removed = original_count - len(classified[category])
                if removed > 0:
                    self.logger.info(f"  - {category}: 删除 {removed} 个未上市品种")
                    removed_count += 1

            self.logger.info(f"✓ 已删除 {len(unlisted_symbols)} 个未上市品种")

            # 4. 保存更新后的缓存
            self._save_cache(classified)
            self.logger.info("✓ 品种列表缓存已更新")

            return True

        except Exception as e:
            self.logger.error(f"更新品种列表缓存失败: {e}", exc_info=True)
            return False

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
from ..load_balancer import (
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
    """

    def __init__(self, name: str, task_count: int):
        """初始化IPO下载任务

        Args:
            name: 任务名称
            task_count: 预计任务数量（品种数）
        """
        super().__init__(name)
        self.task_count = task_count
        # IPO请求比K线轻量，连接数更少
        self.metrics.estimated_connections = min(task_count, 200)

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
            estimated_memory_mb=50,  # 200连接×0.25MB（轻量级请求）
            estimated_connections=200,  # 默认值，会在__init__中更新
        )

    def execute(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """执行IPO下载（占位方法）

        实际下载由MultiProcessStockFetcher.download_ipo_dates执行。
        """
        # 这个方法不会被直接调用
        return {}


# ==================== 工作进程函数（已废弃，使用异步版本） ====================
# download_worker_pooled 已废弃，不再使用同步 mootdx


# ==================== 异步工作进程函数 ====================


async def download_worker_two_phase_async(
    worker_id,
    task_queue,
    result_queue,
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
    logger = logging.getLogger(f"TwoPhaseWorker-{worker_id}")
    logger.info("两段式Worker %s 启动，PID：%s", worker_id, os.getpid())

    # 初始化任务详细日志记录器
    task_logger = None
    try:
        print(f"=" * 70)
        print(f"🔧 [Worker {worker_id}] 正在初始化任务详细日志记录器...")
        print(f"=" * 70)
        task_logger = TaskDetailLogger(worker_id=worker_id)
        print(f"✅ [Worker {worker_id}] 任务详细日志记录器初始化成功！")
        print(f"=" * 70)
        logger.info("[Worker %s] 任务详细日志记录器初始化成功", worker_id)
    except Exception as e:
        print(f"=" * 70)
        print(f"❌ [Worker {worker_id}] 任务详细日志记录器初始化失败！")
        print(f"   错误: {type(e).__name__}: {e}")
        print(f"=" * 70)
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

    phase1_connections = {}
    phase1_servers = []
    used_servers = set()  # 追踪已使用的服务器

    try:
        # 建立初始Phase1连接（使用主用服务器）
        for server in my_ipv4_servers[:connections_per_worker]:
            try:
                client = await AsyncTdxHq_API.factory(
                    server=server, timeout=timeout, heartbeat=False, raise_exception=False
                )
                if client:
                    phase1_connections[server] = client
                    phase1_servers.append(server)
                    used_servers.add(server)
                    logger.debug(
                        "[Phase1] Worker %s 连接成功: %s:%s",
                        worker_id,
                        server[0],
                        server[1],
                    )
            except Exception:
                logger.debug("[Phase1] Worker %s 连接失败：%s:%s", worker_id, server[0], server[1])

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
        # Phase1的连接已在各自的download_loop中关闭
        logger.debug("[Phase1] Worker %s 所有Phase1连接已关闭", worker_id)

    # ========== 等待Phase1完成 ==========
    logger.info("[Phase1-Phase2] Worker %s 等待Phase1协程完成...", worker_id)

    # ========== Phase2：使用后半部分服务器 ==========
    logger.info("[Phase2] Worker %s 开始Phase2，使用后半部分服务器（1.0s超时）", worker_id)

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

    # 建立Phase2连接
    phase2_connections = {}
    phase2_servers = []
    ipv6_used_servers = set()

    for server in my_ipv6_servers[:connections_per_worker]:
        try:
            client = await AsyncTdxHq_API.factory(
                server=server, timeout=timeout, heartbeat=False, raise_exception=False
            )
            if client:
                phase2_connections[server] = client
                phase2_servers.append(server)
                ipv6_used_servers.add(server)
                logger.debug(
                    "[Phase2] Worker %s 连接成功: %s:%s",
                    worker_id,
                    server[0],
                    server[1],
                )
        except Exception:
            logger.debug("[Phase2] Worker %s 连接失败：%s:%s", worker_id, server[0], server[1])

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

        # 关闭任务详细日志记录器
        if task_logger:
            task_logger.close()
            logger.info("[Worker %s] 任务详细日志已保存", worker_id)


def _run_two_phase_worker(*args):
    """在进程中运行两段式异步事件循环的辅助函数"""
    import warnings

    warnings.filterwarnings("ignore", category=ResourceWarning, message=".*socket.*")
    asyncio.run(download_worker_two_phase_async(*args))


async def download_worker_async(
    worker_id,
    task_queue,
    result_queue,
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
        progress_queue: 进度队列
        server_list: 共享的可用服务器列表
        server_index: 共享的服务器索引（用于轮询）
        timeout: 连接超时时间
        retry_times: 重试次数（暂未使用）
        stop_event: 停止事件
        pause_event: 暂停事件
        connections_per_worker: 每个worker的异步连接数（默认无上限）
    """
    logger = logging.getLogger(f"AsyncWorker-{worker_id}")
    logger.info(
        f"异步Worker {worker_id} 启动，PID: {os.getpid()}，连接数: {connections_per_worker}"
    )

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
        for i in range(connections_per_worker):
            # 原子操作：获取并递增全局服务器索引
            # 注意：不能在异步函数中使用 with lock，会阻塞事件循环
            # Manager.Value 的 get_lock() 是同步的，改为原子递增

            # 原子读取和递增（虽然不完美，但避免阻塞）
            current_idx = server_index.value

            # 关键检查：如果索引已经达到服务器总数，停止创建连接
            # 这样确保不会对同一服务器建立第二个连接
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

            # 创建 tdx_asyncio 异步连接
            try:
                client = await AsyncTdxHq_API.factory(
                    server=server, timeout=timeout, heartbeat=False, raise_exception=False
                )
                if client:
                    # 使用服务器地址作为键存储连接
                    connections[server] = client
                    server_list_local.append(server)
                    logger.debug(
                        f"Worker {worker_id} 连接 → 服务器{server[0]}:{server[1]} "
                        f"（全局索引{current_idx}，本Worker第{len(connections)}个）"
                    )
                else:
                    logger.debug(
                        f"Worker {worker_id} 连接 建立失败: {server[0]}:{server[1]} (正常现象，会尝试其他服务器)"
                    )
            except Exception as e:
                logger.warning("Worker %s 连接 建立异常: %s", worker_id, e)

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
        # 关闭所有连接（字典方案）
        for server, client in connections.items():
            try:
                # 🔧 检查连接是否还存在且未关闭
                if client and not client.closed:
                    await client.close()
                    logger.debug(f"Worker {worker_id} 连接 {server[0]}:{server[1]} 已关闭")
                else:
                    logger.debug(f"Worker {worker_id} 连接 {server[0]}:{server[1]} 已经关闭，跳过")
            except (ConnectionError, BrokenPipeError, OSError):
                # 🔧 捕获常见的连接关闭异常，避免输出警告
                logger.debug(f"Worker {worker_id} 连接 {server[0]}:{server[1]} 关闭时连接已断开")
            except Exception as e:
                logger.debug(f"Worker {worker_id} 连接 {server[0]}:{server[1]} 关闭失败: {e}")


def _run_async_worker(*args):
    """在进程中运行异步事件循环的辅助函数"""
    import warnings

    # 🔧 抑制 socket.send() 相关的 ResourceWarning
    # 这些警告通常在连接已断开时尝试关闭连接时出现，不影响功能
    warnings.filterwarnings("ignore", category=ResourceWarning, message=".*socket.*")

    asyncio.run(download_worker_async(*args))


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
        finance_info = await client.get_finance_info(market, symbol)

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
                return datetime.strptime(ipo_str, "%Y%m%d").date(), industry, finance_info

        # ipo_date=0，返回None、industry和完整数据
        return None, industry, finance_info
    except Exception as e:
        local_logger.debug("查询IPO失败 %s: %s", symbol, e)
        # 异常视为服务器问题
        return None, 0, {}


async def download_ipo_dates_simple(
    tasks_list: list[tuple[str, int]],
    num_coroutines: int = 100,
    progress_callback=None,
) -> tuple[dict, list, list]:
    """单进程多协程IPO下载（简化版）

    Args:
        tasks_list: 任务列表 [(symbol, market), ...]
        num_coroutines: 协程数量（默认100）
        progress_callback: 进度回调函数 callback(current, total, status)

    Returns:
        (results, unlisted_data, failed_tasks)
        - results: {symbol: ipo_date} 已上市品种
        - unlisted_data: [{'symbol': str, 'finance_info': dict}, ...] 未上市品种
        - failed_tasks: [(symbol, market), ...] 失败的任务
    """
    import asyncio
    import logging
    from ..load_balancer import get_random_servers

    local_logger = logging.getLogger(__name__)

    if not tasks_list:
        return {}, [], []

    local_logger.info(
        "开始单进程多协程IPO下载: %s个品种, %s个协程", len(tasks_list), num_coroutines
    )

    # 1. 准备连接池
    servers = get_random_servers(count=num_coroutines)
    local_logger.info("获取到 %s 个服务器", len(servers))

    # 2. 创建异步连接（并发连接以提速）
    async def connect_single_server(server):
        """并发连接单个服务器"""
        server_ip = None
        server_port = None
        try:
            # 🔧 修复：关闭心跳包，避免多协程并发时的socket竞态冲突
            client = AsyncTdxHq_API(heartbeat=False, auto_retry=False, raise_exception=False)
            # server 可能是元组 (ip, port) 或字典 {'ip': ..., 'port': ...}
            if isinstance(server, tuple):
                server_ip, server_port = server
            elif isinstance(server, dict):
                server_ip = server.get("ip", "")
                server_port = server.get("port", 0)
            else:
                return None

            await client.connect(server_ip, server_port, time_out=5)  # 缩短超时到5秒
            return client
        except Exception as e:
            local_logger.debug(f"连接服务器 {server_ip}:{server_port} 失败: {e}")
            return None

    # 并发连接所有服务器
    local_logger.info(f"开始并发连接 {len(servers)} 个服务器...")
    connection_tasks = [connect_single_server(server) for server in servers]
    connected_clients = await asyncio.gather(*connection_tasks, return_exceptions=True)

    # 过滤成功的连接
    clients: List[AsyncTdxHq_API] = []
    for c in connected_clients:
        if isinstance(c, AsyncTdxHq_API):
            clients.append(c)

    if not clients:
        local_logger.error("无法连接任何服务器")
        return {}, [], tasks_list

    local_logger.info("成功连接 %s 个服务器", len(clients))

    # 3. 结果收集
    results = {}  # {symbol: ipo_date}
    unlisted_data = []  # [{'symbol': str, 'finance_info': dict}, ...]
    failed_tasks = []  # [(symbol, market), ...]
    completed_count = 0
    total_count = len(tasks_list)

    # 4. 并发下载
    async def download_single_task(task, client):
        nonlocal completed_count
        symbol, market = task

        try:
            ipo_date, industry, finance_info = await _download_single_ipo_async(
                client, symbol, market
            )

            if ipo_date is not None:
                # 已上市
                results[symbol] = ipo_date
                status = "success"
            elif industry > 0:
                # 检查是否是数据异常的品种（有industry但其他财务数据全为0）
                # 判断关键字段：zongzichan, liudongzichan, zhuyingshouru
                is_data_valid = (
                    finance_info.get("zongzichan", 0) > 0
                    or finance_info.get("liudongzichan", 0) > 0
                    or finance_info.get("zhuyingshouru", 0) > 0
                )

                if is_data_valid:
                    # 真正的未上市品种（有完整财务数据）
                    unlisted_data.append(
                        {"symbol": symbol, "market": market, "finance_info": finance_info}
                    )
                    status = "unlisted"
                else:
                    # 数据异常（只有industry但无其他财务数据），视为失败重试
                    local_logger.debug(
                        f"品种 {symbol} 财务数据异常，仅有industry={industry}，其他字段为0"
                    )
                    failed_tasks.append(task)
                    status = "retry"
            else:
                # 服务器问题，稍后重试
                failed_tasks.append(task)
                status = "retry"

            completed_count += 1

            # 动态延时机制
            remaining = total_count - completed_count
            if remaining <= 30:
                await asyncio.sleep(0.2)
            elif remaining <= 100:
                await asyncio.sleep(0.1)
            elif remaining <= 200:
                await asyncio.sleep(0.05)

            # 进度回调
            if progress_callback:
                progress_callback(completed_count, total_count, status)

            # 输出进度
            if completed_count % 100 == 0:
                print(
                    f"进度: {completed_count}/{total_count} ({completed_count/total_count*100:.1f}%)"
                )

        except Exception as e:
            local_logger.debug("下载 %s 失败: %s", symbol, e)
            failed_tasks.append(task)
            completed_count += 1

    # 5. 使用任务队列模式（修复：避免多个协程共享同一客户端）
    # 创建任务队列
    task_queue = asyncio.Queue()
    for task in tasks_list:
        await task_queue.put(task)

    # 为每个客户端创建一个专属worker
    async def worker(worker_id: int, client):
        """每个worker独占一个客户端，从队列中取任务处理"""
        processed = 0
        while True:
            try:
                # 从队列获取任务（0.1秒超时）
                task = await asyncio.wait_for(task_queue.get(), timeout=0.1)
                await download_single_task(task, client)
                processed += 1
                task_queue.task_done()
            except asyncio.TimeoutError:
                # 队列为空，检查是否真的完成了
                if task_queue.empty():
                    break
                # 超时但队列未空，继续循环
                continue
            except Exception as e:
                # 处理其他异常，记录后继续
                local_logger.debug(f"Worker {worker_id} 处理任务异常: {e}")
                continue

        local_logger.debug(f"Worker {worker_id} 完成，处理了 {processed} 个任务")
        return processed

    # 启动所有worker（每个客户端一个worker）
    workers = [worker(i, client) for i, client in enumerate(clients)]
    await asyncio.gather(*workers, return_exceptions=True)

    # 6. 重试失败的品种（最多5次，使用现有连接）
    for retry_round in range(5):
        if not failed_tasks:
            break

        local_logger.info("第%s次重试: %s个品种", retry_round + 1, len(failed_tasks))
        print(f"⚠️ 重试 {len(failed_tasks)} 个失败品种 (第{retry_round + 1}/5次)")

        # 不关闭连接，直接使用现有的clients进行重试
        # 如果失败次数过多（>=3次）或连接数不足，则切换服务器
        if retry_round >= 3 or len(clients) < 10:
            local_logger.info("第%s次重试：切换服务器...", retry_round + 1)
            print("   → 切换服务器以提升成功率")

            # 关闭旧连接
            for client in clients:
                try:
                    await client.close()
                except Exception:
                    pass

            # 重新获取服务器并创建新连接
            retry_servers = get_random_servers(count=min(num_coroutines, len(failed_tasks) * 2))
            local_logger.info("重试获取到 %s 个新服务器", len(retry_servers))

            clients = []
            for i, server in enumerate(retry_servers):
                server_ip = None
                server_port = None
                try:
                    client = AsyncTdxHq_API(heartbeat=True, auto_retry=False, raise_exception=False)
                    if isinstance(server, tuple):
                        server_ip, server_port = server
                    elif isinstance(server, dict):
                        server_ip = server.get("ip", "")
                        server_port = server.get("port", 0)
                    else:
                        continue

                    await client.connect(server_ip, server_port, time_out=10)
                    clients.append(client)
                except Exception as e:
                    local_logger.debug("重试连接服务器 %s:%s 失败: %s", server_ip, server_port, e)

            if not clients:
                local_logger.warning("第%s次重试：无法连接任何服务器，停止重试", retry_round + 1)
                break

        # 使用现有或新建的连接进行重试（使用队列模式）
        retry_batch = failed_tasks[:]
        failed_tasks.clear()

        # 创建重试任务队列
        retry_queue = asyncio.Queue()
        for task in retry_batch:
            await retry_queue.put(task)

        # 为每个客户端创建重试worker
        async def retry_worker(worker_id: int, client):
            """重试worker：每个worker独占一个客户端"""
            processed = 0
            while True:
                try:
                    task = await asyncio.wait_for(retry_queue.get(), timeout=0.1)
                    await download_single_task(task, client)
                    processed += 1
                    retry_queue.task_done()
                except asyncio.TimeoutError:
                    if retry_queue.empty():
                        break
                    continue
                except Exception as e:
                    local_logger.debug(f"重试Worker {worker_id} 异常: {e}")
                    continue
            return processed

        # 启动所有重试worker
        retry_workers = [retry_worker(i, client) for i, client in enumerate(clients)]
        await asyncio.gather(*retry_workers, return_exceptions=True)

    # 7. 关闭连接
    for client in clients:
        try:
            await client.close()
        except Exception:
            pass

    local_logger.info(
        f"下载完成: 已上市{len(results)}个, 未上市{len(unlisted_data)}个, 失败{len(failed_tasks)}个"
    )

    return results, unlisted_data, failed_tasks


async def download_worker_ipo_async(
    worker_id,
    task_queue,
    result_queue,
    progress_queue,
    server_list,
    _server_index,
    timeout,
    _retry_times,
    stop_event,
    pause_event,
    connections_per_worker=999999,  # 🔧 移除连接上限，让系统展现真实瓶颈
    unlisted_debug_queue=None,
):
    """IPO下载Worker（异步版本，复用K线下载架构）

    Args:
        worker_id: Worker进程ID
        task_queue: 共享任务队列
        result_queue: 结果队列
        progress_queue: 进度队列
        server_list: 共享的可用服务器列表
        server_index: 共享的服务器索引（用于轮询）
        timeout: 连接超时时间
        retry_times: 重试次数（暂未使用）
        stop_event: 停止事件
        pause_event: 暂停事件
        connections_per_worker: 每个worker的异步连接数（默认无上限）
        unlisted_debug_queue: 用于收集unlisted品种的完整数据（调试用）
    """
    worker_logger = logging.getLogger(__name__)
    worker_logger.info("Worker %s 启动 (IPO模式)", worker_id)

    try:
        # 从共享服务器列表中获取N个服务器（每个协程1个）
        server_list_local = list(server_list)[:connections_per_worker]

        if not server_list_local:
            worker_logger.error("Worker %s 无可用服务器，退出", worker_id)
            return

        # 为每个服务器创建客户端连接
        connections = {}
        for server in server_list_local:
            try:
                client = await AsyncTdxHq_API.factory(server, timeout=timeout)
                if client:
                    connections[server] = client
                    worker_logger.debug(
                        "Worker %s 连接到服务器 %s:%s", worker_id, server[0], server[1]
                    )
            except Exception as e:
                worker_logger.debug("Worker %s 连接失败 %s: %s", worker_id, server, e)

        if not connections:
            worker_logger.error("Worker %s 无可用连接，退出", worker_id)
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
                    worker_logger.debug("Worker %s 连接 %s 队列为空", worker_id, conn_id)
                    break
                except Exception as e:
                    worker_logger.debug("Worker %s 连接 %s 获取任务失败: %s", worker_id, conn_id, e)
                    break

                symbol, market = task

                try:
                    # 异步下载IPO日期和行业代码
                    ipo_date, industry, finance_info = await _download_single_ipo_async(
                        client, symbol, market
                    )

                    if ipo_date is not None:
                        # 已上市，成功
                        await asyncio.to_thread(result_queue.put, (symbol, ipo_date, "listed"))
                        await asyncio.to_thread(progress_queue.put, (symbol, "success"))
                        processed += 1
                    elif industry > 0:
                        # 未上市品种（ipo_date=0 但 industry>0）
                        await asyncio.to_thread(result_queue.put, (symbol, None, "unlisted"))
                        await asyncio.to_thread(progress_queue.put, (symbol, "unlisted"))

                        # 🔧 保存unlisted品种的完整finance_info数据用于调试
                        if unlisted_debug_queue is not None:
                            debug_data = {
                                "symbol": symbol,
                                "market": market,
                                "finance_info": finance_info,
                                "worker_id": worker_id,
                                "conn_id": conn_id,
                            }
                            await asyncio.to_thread(unlisted_debug_queue.put, debug_data)

                        processed += 1
                    else:
                        # 服务器问题（ipo_date=0 且 industry=0），重试
                        await asyncio.to_thread(task_queue.put, (symbol, market))
                        await asyncio.to_thread(progress_queue.put, (symbol, "retry"))
                        failed += 1

                except Exception as e:
                    worker_logger.debug(
                        f"Worker {worker_id} 连接 {conn_id} 下载 {symbol} IPO失败: {e}"
                    )
                    # 异常也视为服务器问题，重试
                    await asyncio.to_thread(task_queue.put, (symbol, market))
                    await asyncio.to_thread(progress_queue.put, (symbol, "retry"))
                    failed += 1

                # 🔧 动态延时机制：根据队列剩余量调整延时，降低服务器压力
                try:
                    queue_size = task_queue.qsize()
                    if queue_size <= 30:
                        # 剩余30个以下：延时0.2秒
                        await asyncio.sleep(0.2)
                    elif queue_size <= 100:
                        # 剩余30-100个：延时0.1秒
                        await asyncio.sleep(0.1)
                    elif queue_size <= 200:
                        # 剩余100-200个：延时0.05秒
                        await asyncio.sleep(0.05)
                    # 队列>200个：不延时，全速运行
                except Exception:
                    # 获取队列大小失败时，使用默认延时
                    pass

            worker_logger.info(
                f"Worker {worker_id} 连接 {conn_id} 完成, 成功: {processed}, 失败: {failed}"
            )
            return processed, failed

        # N个协程并发工作
        tasks = []
        for idx, server in enumerate(server_list_local):
            if server in connections:
                tasks.append(download_loop(idx, connections[server], server))

        if not tasks:
            worker_logger.warning("Worker %s 没有可用连接，退出", worker_id)
            return

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 统计总数
        total_processed = sum((r[0] for r in results if isinstance(r, tuple)), 0)
        total_failed = sum((r[1] for r in results if isinstance(r, tuple)), 0)
        worker_logger.info(
            "Worker %s 总计完成, 成功: %s, 失败: %s", worker_id, total_processed, total_failed
        )

    finally:
        # 关闭所有连接
        for server, client in connections.items():
            try:
                if client and not client.closed:
                    await client.close()
                    worker_logger.debug(
                        "Worker %s 连接 %s:%s 已关闭", worker_id, server[0], server[1]
                    )
            except Exception as e:
                worker_logger.debug("Worker %s 关闭连接失败 %s: %s", worker_id, server, e)


def _run_async_worker_ipo(*args):
    """在进程中运行IPO异步worker的辅助函数"""
    import warnings

    warnings.filterwarnings("ignore", category=ResourceWarning, message=".*socket.*")
    asyncio.run(download_worker_ipo_async(*args))


# ==================== (旧StockSymbolManager已删除，使用symbol_management.SymbolLoader替代) ====================


# ==================== 多进程数据获取器 ====================


class MultiProcessStockFetcher:
    """多进程股票数据获取器（进程池+动态任务分配模式）"""

    def __init__(self, event_engine=None):
        self.logger = logging.getLogger(__name__)
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
            from ..events import DownloadEventPublisher, EventPublisher

            self.download_publisher = DownloadEventPublisher(event_engine)
            self.log_publisher = EventPublisher(event_engine)
        else:
            self.download_publisher = None
            self.log_publisher = None

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
                    # 🔧 优化：两段式模式不再分离IPv4/IPv6，Phase1和Phase2都使用全部服务器池
                    self.logger.info("使用两段式下载模式（统一服务器池）")
                    all_servers = server_pool_manager.get_servers_shuffled()

                    # Phase1和Phase2都使用全部服务器池，通过worker偏移减少冲突
                    regular_servers = all_servers  # Phase1使用全部服务器
                    standby_servers = all_servers  # Phase2也使用全部服务器
                    broker_map = {}  # 两段式不需要broker区分
                    available_servers = all_servers  # 第一阶段可用的服务器

                    # 计算阈值：固定50个任务
                    threshold = 50
                    self.logger.info(f"  总服务器: {len(all_servers)}个")
                    self.logger.info(f"  Phase1服务器池: {len(regular_servers)}个（全部）")
                    self.logger.info(
                        f"  Phase2服务器池: {len(standby_servers)}个（全部，作为备用）"
                    )
                    self.logger.info(f"  切换阈值: 剩余{threshold}任务时切换到Phase2")
                else:
                    # 单段式模式：获取打乱的服务器
                    available_servers = server_pool_manager.get_servers_shuffled()

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
                    KlineDownloadTask,
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

            # 收集结果（非阻塞）
            try:
                if self.result_queue:
                    key, data_dict = self.result_queue.get_nowait()
                    if data_dict is not None:
                        df = pd.DataFrame(data_dict)
                        results[key] = df
                        self.logger.debug(f"收到结果: {key} ({len(df)} 条数据)")
            except queue.Empty:
                pass

        # 最后收集剩余的结果
        self.logger.info("收集剩余结果...")
        remaining_results = 0
        while True:
            try:
                if self.result_queue:
                    key, data_dict = self.result_queue.get_nowait()
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
    force_refresh: bool = False,
    progress_callback: Optional[Callable] = None,
    event_callback: Optional[Callable] = None,
    _use_adaptive: bool = True,
    _use_two_phase: bool = True,
) -> Dict[str, Any]:
    """批量下载IPO日期

    Args:
        symbols: 品种代码列表
        force_refresh: 是否强制刷新（False=跳过已缓存）
        progress_callback: 进度回调函数 callback(symbol, status)
        event_callback: 事件回调函数 callback(event_type, status, count, message)
        use_adaptive: 是否使用自适应配置
        use_two_phase: 是否使用两段式下载（默认True，热备服务器优化）

    Returns:
        {
            "success": bool,
            "total": int,
            "cached": int,        # 跳过的缓存数
            "downloaded": int,    # 实际下载数
            "succeeded": int,     # 成功获取IPO的数量
            "failed": int,        # 失败数量
            "data": {symbol: ipo_date, ...}
        }
    """
    from ..local_data.data_quality import IPODateCache
    import time

    local_logger = logging.getLogger(__name__)
    local_logger.info(f"开始IPO批量下载: {len(symbols)}个品种")

    # 1. 增量过滤
    ipo_cache = IPODateCache()

    if not force_refresh:
        uncached = []
        for symbol in symbols:
            _cached_date, is_cached = ipo_cache.get(symbol)
            if not is_cached:
                uncached.append(symbol)

        local_logger.info(
            f"增量模式: {len(symbols)}个品种 → 跳过{len(symbols)-len(uncached)}个已缓存 → 下载{len(uncached)}个"
        )
        symbols_to_download = uncached
        cached_count = len(symbols) - len(uncached)
    else:
        symbols_to_download = symbols
        cached_count = 0

    if not symbols_to_download:
        local_logger.info("所有品种均已缓存，无需下载")
        return {
            "success": True,
            "total": len(symbols),
            "cached": cached_count,
            "downloaded": 0,
            "succeeded": 0,
            "failed": 0,
            "data": {},
        }

    # 2. 准备任务列表（从品种列表缓存获取市场代码）
    # 🆕 从品种列表缓存中获取市场代码映射
    local_logger.info("从品种列表缓存中加载市场代码...")
    symbol_market_map = {}
    try:
        # SymbolLoader已在本文件第2部分定义，无需导入
        symbol_loader = SymbolLoader()
        classified = symbol_loader.get_all_classified()

        # 构建 code -> market 映射
        for _category, stocks in classified.items():
            for stock in stocks:
                if isinstance(stock, dict):
                    code = stock.get("code")
                    market = stock.get("market")
                    if code and market is not None:
                        symbol_market_map[code] = market

        local_logger.info(f"✓ 成功加载 {len(symbol_market_map)} 个品种的市场代码")
    except Exception as e:
        local_logger.warning(f"加载品种市场代码失败，将使用代码前缀判断: {e}")

    # 构建任务列表
    tasks = []
    fallback_count = 0  # 使用默认判断的数量

    for symbol in symbols_to_download:
        # 优先从缓存获取市场代码
        if symbol in symbol_market_map:
            market = symbol_market_map[symbol]
        else:
            # 兜底：使用代码前缀判断（兼容性）
            if symbol.startswith("6"):
                market = 1  # 上海
            elif symbol.startswith("8") or symbol.startswith("4"):
                market = 2  # 北交所
            else:
                market = 0  # 深圳
            fallback_count += 1

        tasks.append((symbol, market))

    if fallback_count > 0:
        local_logger.info(f"⚠️ {fallback_count}个品种使用代码前缀判断市场")

    task_count = len(tasks)

    # 3. 使用简化的单进程多协程架构
    print("✓ 使用单进程多协程架构（100个协程）")
    local_logger.info("开始单进程多协程IPO下载")

    start_time = time.time()

    # 执行异步下载
    import asyncio

    def simple_progress_callback(_current, _total, status):
        """简化的进度回调"""
        if progress_callback:
            # 模拟品种名称（实际可从任务列表获取）
            progress_callback("", status)

    results, unlisted_data, failed_tasks = asyncio.run(
        download_ipo_dates_simple(
            tasks, num_coroutines=100, progress_callback=simple_progress_callback
        )
    )

    # 4. 处理结果和调试数据
    # 将unlisted_data转换为简单的symbol列表用于后续统计
    unlisted_symbols = [item["symbol"] for item in unlisted_data]

    # 保存调试数据到JSON文件
    import json
    from pathlib import Path

    # 使用配置管理器获取正确的缓存目录
    try:
        from backend.infrastructure.data_module_vnpy.config import config_manager

        cache_dir = config_manager.get_cache_dir()
        debug_file_path = cache_dir / "unlisted_symbols_debug.json"
    except Exception:
        # 兜底方案：直接指定绝对路径
        debug_file_path = (
            Path(__file__).parent.parent.parent.parent.parent
            / "data"
            / "cache"
            / "unlisted_symbols_debug.json"
        )
    debug_file_path.parent.mkdir(parents=True, exist_ok=True)

    if unlisted_data:
        with open(debug_file_path, "w", encoding="utf-8") as f:
            json.dump(unlisted_data, f, ensure_ascii=False, indent=2, default=str)

        local_logger.info(
            f"✓ 已保存 {len(unlisted_data)} 个unlisted品种的调试数据到: {debug_file_path}"
        )
        print(f"✓ 已保存 {len(unlisted_data)} 个unlisted品种的调试数据到: {debug_file_path}")

    # 🔧 V2优化：使用环境变量控制详细调试输出，避免正常使用时刷屏
    import os

    debug_unlisted = os.getenv("DEBUG_UNLISTED", "0") == "1"

    if debug_unlisted:
        # 输出详细分析（仅当DEBUG_UNLISTED=1时）
        print("\n" + "=" * 70)
        print("【Unlisted品种详细分析】")
        print(f"  - 通过worker标记的unlisted品种数: {len(unlisted_data)}")
        print(f"  - unlisted_symbols列表长度: {len(unlisted_symbols)}")

        # 检查重复
        unlisted_set = set(unlisted_symbols)
        if len(unlisted_set) != len(unlisted_symbols):
            print(f"  ⚠️ 发现重复！去重后: {len(unlisted_set)} 个")
            from collections import Counter

            duplicates = [item for item, count in Counter(unlisted_symbols).items() if count > 1]
            print(f"  重复的品种: {duplicates}")

        # 检查results和unlisted_symbols的交集
        results_set = set(results.keys())
        intersection = unlisted_set & results_set
    else:
        # 简化输出：仅汇总信息
        unlisted_set = set(unlisted_symbols)
        results_set = set(results.keys())
        intersection = unlisted_set & results_set

    if intersection and debug_unlisted:
        print(f"\n  🚨 发现关键问题：{len(intersection)}个品种同时在results和unlisted_symbols中！")
        print("  这些品种被重复计数（既标记为已上市，又标记为未上市）：")
        intersection_list = sorted(list(intersection))
        for i in range(0, len(intersection_list), 10):
            batch = intersection_list[i : i + 10]
            print(f"    {', '.join(batch)}")

        # 分析这些重复品种
        duplicate_bonds = [s for s in intersection_list if s.startswith(("11", "12", "13"))]
        duplicate_stocks = [s for s in intersection_list if not s.startswith(("11", "12", "13"))]
        print(f"\n  其中可转债{len(duplicate_bonds)}个, 股票{len(duplicate_stocks)}个")

    # 🔧 V2优化：详细列表仅在DEBUG模式输出
    if debug_unlisted:
        # 输出完整列表
        if unlisted_symbols:
            print(f"\n  完整unlisted品种列表（共{len(unlisted_symbols)}个）")
            for i in range(0, len(unlisted_symbols), 10):
                batch = unlisted_symbols[i : i + 10]
                print(f"    {', '.join(batch)}")

        # 对比debug数据
        if unlisted_data:
            debug_symbols = [item["symbol"] for item in unlisted_data]
            print(f"\n  Debug队列中的品种（共{len(debug_symbols)}个）")
            for i in range(0, len(debug_symbols), 10):
                batch = debug_symbols[i : i + 10]
                print(f"    {', '.join(batch)}")

            # 找出差异（这在单进程架构中不应该存在）
            missing_from_debug = set(unlisted_symbols) - set(debug_symbols)
            if missing_from_debug:
                print(
                    f"\n  ⚠️ 在unlisted_symbols中但不在debug数据中的品种（{len(missing_from_debug)}个）"
                )
                missing_list = sorted(list(missing_from_debug))
                for i in range(0, len(missing_list), 10):
                    batch = missing_list[i : i + 10]
                    print(f"    {', '.join(batch)}")

        print("=" * 70 + "\n")
    else:
        # 简化输出：仅关键信息
        local_logger.info(
            "Unlisted品种: %d个（详细信息已保存，如需查看设置DEBUG_UNLISTED=1）",
            len(unlisted_symbols),
        )

    total_time = time.time() - start_time
    local_logger.info(f"IPO下载完成，总耗时: {total_time:.2f}秒")

    # 5. 统计结果
    succeeded = len(results)  # 已上市品种数
    unlisted_count = len(unlisted_symbols)  # 未上市品种数
    failed = len(failed_tasks)  # 失败数
    initial_task_count = task_count
    total_retry_count = 0  # 新架构中重试次数由函数内部管理

    # 收集失败品种
    failed_symbols = [task[0] for task in failed_tasks]

    # 6. 统计结果（跳过旧的多进程监控代码）
    # 以下代码直接使用简化版函数的返回结果

    # 7. 输出三个集合的详细统计
    print("\n" + "=" * 70)
    print("【三个集合详细统计】")
    print(f"  初始任务总数: {initial_task_count}")
    print(f"  已上市品种数 (results): {succeeded}")
    print(f"  未上市品种数 (unlisted_symbols): {unlisted_count}")
    print(f"  失败品种数 (计算得出): {failed}")
    print(
        f"  总和验证: {succeeded} + {unlisted_count} + {failed} = {succeeded + unlisted_count + failed}"
    )
    if succeeded + unlisted_count + failed != initial_task_count:
        print(f"  ⚠️ 总和不匹配！差异: {initial_task_count - (succeeded + unlisted_count + failed)}")

    # 真实去重统计
    results_set = set(results.keys())
    unlisted_set = set(unlisted_symbols)
    intersection = results_set & unlisted_set
    unique_succeeded = len(results_set - intersection)
    unique_unlisted = len(unlisted_set - intersection)
    unique_total = unique_succeeded + unique_unlisted + failed

    print("\n  【去重后的真实统计】")
    print(f"  去重后已上市品种: {unique_succeeded} (原{succeeded}, 去除{len(intersection)}个重复)")
    print(
        f"  去重后未上市品种: {unique_unlisted} (原{unlisted_count}, 去除{len(intersection)}个重复)"
    )
    print(f"  失败品种: {failed}")
    print(f"  去重后总计: {unique_succeeded} + {unique_unlisted} + {failed} = {unique_total}")

    if unique_total == initial_task_count:
        print("  ✓ 去重后总和正确！")
    else:
        print(f"  ⚠️ 去重后总和仍不匹配！差异: {initial_task_count - unique_total}")

    print("=" * 70 + "\n")

    # 8. 更新品种列表缓存（合并IPO数据并删除未上市品种）
    if results or unlisted_symbols:
        local_logger.info("=" * 60)
        local_logger.info("【更新品种列表缓存】")

        # 去重：只删除真正的未上市品种（不在results中的）
        results_set = set(results.keys())
        unlisted_set = set(unlisted_symbols)
        true_unlisted = list(unlisted_set - results_set)  # 真正的未上市品种

        local_logger.info(f"  - 已上市品种: {succeeded} 个（将写入IPO日期）")
        local_logger.info(f"  - 原未上市品种数: {unlisted_count} 个")
        if len(true_unlisted) != unlisted_count:
            local_logger.warning(
                f"  - 发现重复标记: {unlisted_count - len(true_unlisted)} 个品种同时被标记为已上市和未上市"
            )
            local_logger.info(f"  - 真正未上市品种: {len(true_unlisted)} 个（将从列表中删除）")
            print(
                f"\n   🔧 去重修正：实际删除 {len(true_unlisted)} 个未上市品种（而非原来的 {unlisted_count} 个）"
            )
        else:
            local_logger.info(f"  - 未上市品种: {unlisted_count} 个（将从列表中删除）")

        try:
            # SymbolLoader已在本文件第2部分定义，无需导入
            symbol_loader = SymbolLoader()
            success = symbol_loader.update_ipo_dates_and_remove_unlisted(results, true_unlisted)
            if success:
                local_logger.info("✓ 品种列表缓存已更新（包含IPO日期，已删除未上市品种）")
            else:
                local_logger.warning("⚠️ 品种列表缓存更新失败")
        except Exception as e:
            local_logger.error(f"更新品种列表缓存时出错: {e}", exc_info=True)
        local_logger.info("=" * 60)

    # 9. 输出最终统计
    local_logger.info("=" * 60)
    local_logger.info("IPO批量下载统计:")
    local_logger.info(f"  总品种数: {len(symbols)}")
    local_logger.info(f"  跳过缓存: {cached_count}")
    local_logger.info(f"  实际下载: {task_count}")
    local_logger.info(f"  已上市品种: {succeeded}")
    local_logger.info(f"  未上市品种: {unlisted_count}")
    local_logger.info(f"  失败/无数据: {failed}")
    local_logger.info(f"  总重试次数: {total_retry_count}")
    if task_count > 0:
        local_logger.info(f"  成功率: {(succeeded + unlisted_count)/task_count*100:.1f}%")
        if total_retry_count > 0:
            local_logger.info(f"  平均重试: {total_retry_count/task_count:.2f}次/品种")

    # 输出失败品种详情（前10个）
    if failed_symbols:
        local_logger.warning("  失败品种示例（前10个）: %s", ", ".join(failed_symbols[:10]))
        if len(failed_symbols) > 10:
            local_logger.warning("    ... 还有%d个失败品种", len(failed_symbols) - 10)

    local_logger.info("=" * 60)

    # 10. 添加terminal输出
    import sys

    print("\n   IPO下载完成：")
    print(f"   - 总品种数: {len(symbols)}")
    print(f"   - 跳过缓存: {cached_count}")
    print(f"   - 实际下载: {task_count}")
    print(f"   - 已上市品种: {succeeded}")
    print(f"   - 未上市品种: {unlisted_count}")

    # 如果存在重复，显示去重后的真实数据
    if intersection:
        print(f"   ⚠️ 发现{len(intersection)}个品种被重复计数")
        print(f"   - 去重后已上市: {unique_succeeded}")
        print(f"   - 去重后未上市: {unique_unlisted}")

    print(f"   - 失败/无数据: {failed}")
    print(f"   - 总重试次数: {total_retry_count}")
    if total_retry_count > 0 and task_count > 0:
        print(f"   - 平均重试: {total_retry_count/task_count:.2f}次/品种")
    if task_count > 0:
        print(f"   - 成功率: {(succeeded + unlisted_count)/task_count*100:.1f}%")

    # 🔧 V2优化：失败品种列表汇总输出，详细列表记录到logger
    if failed_symbols:
        print(f"   - 失败品种: {len(failed_symbols)}个（前5个）: {', '.join(failed_symbols[:5])}")
        # 完整列表记录到logger（DEBUG级别可查看）
        local_logger.debug(
            "完整失败品种列表（%d个）: %s", len(failed_symbols), ", ".join(failed_symbols)
        )

        # 将完整失败品种列表保存到文件（用于分析）
        try:
            from pathlib import Path
            from backend.infrastructure.data_module_vnpy.config import config_manager

            cache_dir = config_manager.get_cache_dir()
            failed_file = cache_dir / "ipo_failed_symbols.json"

            import json

            with open(failed_file, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "timestamp": str(datetime.now()),
                        "total_failed": len(failed_symbols),
                        "failed_symbols": failed_symbols,
                    },
                    f,
                    ensure_ascii=False,
                    indent=2,
                )

            local_logger.info(f"✓ 失败品种列表已保存到: {failed_file}")
        except Exception as e:
            local_logger.warning(f"保存失败品种列表失败: {e}")

    sys.stdout.flush()

    # 11. 推送事件
    if event_callback:
        # 使用去重后的真实数据
        true_succeeded = len(results)  # results本身是字典，已去重
        true_unlisted_list = list(set(unlisted_symbols) - set(results.keys()))
        event_callback(
            "ipo_download",
            "success",
            true_succeeded + len(true_unlisted_list),
            f"成功处理{true_succeeded + len(true_unlisted_list)}个品种（已上市{true_succeeded}个，未上市{len(true_unlisted_list)}个）",
        )

    return {
        "success": True,
        "total": len(symbols),
        "cached": cached_count,
        "downloaded": task_count,
        "succeeded": succeeded,
        "unlisted": unlisted_symbols,  # 保持原始数据供调试
        "failed": failed,
        "data": results,
        "duplicate_count": (len(intersection) if "intersection" in locals() else 0),  # 添加重复计数
        "true_unlisted": (
            true_unlisted if "true_unlisted" in locals() else unlisted_symbols
        ),  # 真正的未上市品种
    }
