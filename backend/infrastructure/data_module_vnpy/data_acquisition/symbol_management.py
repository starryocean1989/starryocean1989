# -*- coding: utf-8 -*-
"""
品种管理模块

负责品种列表的获取、分类和缓存管理，包括：
- 从tdx_asyncio API获取完整品种列表（仅市场代码0=深交所、1=上交所）
- 从addedcode_bj.cfg获取北证A股品种列表（市场代码2为硬编码值）
- 按照需求逻辑分类品种（上证A股、深证A股、北证A股、T+0基金、可转债）
- 缓存分类结果到本地JSON文件
- 解析通达信板块文件和配置文件

合并来源：symbol_loader.py + block_parser.py
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
from backend.infrastructure.tdx_asyncio import AsyncTdxHq_API

from ..config import config_manager, TdxConfigFileParser

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

            if not is_valid:
                self.logger.warning("品种列表缓存已过时（日期: %s），建议更新", cache_date)
            else:
                self.logger.info("品种列表缓存有效（日期: %s）", cache_date)

            self.logger.info("  - 上证A股: %d", len(classified.get("上证A股", [])))
            self.logger.info("  - 深证A股: %d", len(classified.get("深证A股", [])))
            self.logger.info("  - 北证A股: %d", len(classified.get("北证A股", [])))
            self.logger.info("  - T+0基金: %d", len(classified.get("T+0基金", [])))
            self.logger.info("  - 可转债: %d", len(classified.get("可转债", [])))

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
        from ..server_pool_manager import server_pool_manager

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
    def _fetch_market_in_process(market: int, server: tuple, shared_results: dict):
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
