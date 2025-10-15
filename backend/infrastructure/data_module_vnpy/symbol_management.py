# -*- coding: utf-8 -*-
"""
品种管理模块

负责品种列表的获取、分类和缓存管理，包括：
- 从mootdx API获取完整品种列表
- 按照需求逻辑分类品种（上证A股、深证A股、北证A股、T+0基金、可转债）
- 缓存分类结果到本地JSON文件
- 解析通达信板块文件和配置文件

合并来源：symbol_loader.py + block_parser.py
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
from mootdx.quotes import Quotes

from .config import config_manager, TdxConfigFileParser

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
                return pd.DataFrame(columns=["blockname", "code", "block_type"])

            df = pd.DataFrame(results)
            logger.info(
                "成功解析spblock.dat: %d 条记录，%d 个板块", len(df), df["blockname"].nunique()
            )
            return df

        except Exception as e:
            logger.error("自定义解析spblock.dat失败: %s", e, exc_info=True)
            # 返回空DataFrame但保持结构
            return pd.DataFrame(columns=["blockname", "code", "block_type"])

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

    def get_t0_fund_codes(self) -> List[Dict[str, any]]:
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

        result: List[Dict[str, any]] = []

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

    def __init__(self):
        """初始化加载器"""
        self.logger = logging.getLogger(__name__)

        # 初始化配置文件解析器
        tdx_dir = config_manager.get_tdx_dir()
        self.config_parser = TdxConfigFileParser(tdx_dir)
        self.block_parser = BlockParser(tdx_dir)

        # 缓存目录
        self.cache_dir = config_manager.get_cache_dir()
        self.cache_file = self.cache_dir / "stock_list_classified.json"

    def load_from_api(self) -> Dict[str, List[Dict[str, any]]]:
        """
        从API加载完整品种列表并分类

        Returns:
            分类后的品种字典 {
                "上证A股": [{"code": "600000", "name": "浦发银行", "market": 1}, ...],
                "深证A股": [...],
                "北证A股": [...],
                "T+0基金": [...],
                "可转债": [...]
            }
        """
        self.logger.info("=" * 60)
        self.logger.info("开始从API加载品种列表")
        self.logger.info("=" * 60)

        # 步骤1: 获取完整品种缓存（集合D）
        complete_df = self._fetch_complete_stocks()

        # 步骤2: 分类品种
        classified = self._classify_stocks(complete_df)

        # 步骤3: 缓存到本地
        self._save_cache(classified)

        self.logger.info("=" * 60)
        self.logger.info(
            "API加载完成，共获取 %d 个品种", sum(len(stocks) for stocks in classified.values())
        )
        self.logger.info("=" * 60)

        return classified

    def load_from_cache(self) -> Optional[Dict[str, List[Dict[str, any]]]]:
        """
        从本地缓存加载品种分类

        Returns:
            分类后的品种字典，如果缓存不存在返回None
        """
        if not self.cache_file.exists():
            self.logger.info("本地缓存不存在: %s", self.cache_file)
            return None

        try:
            with open(self.cache_file, "r", encoding="utf-8") as f:
                cache_data = json.load(f)

            classified = cache_data.get("classified", {})
            cache_time = cache_data.get("cache_time", "")

            self.logger.info("成功加载本地缓存: %s (缓存时间: %s)", self.cache_file, cache_time)
            self.logger.info("  - 上证A股: %d", len(classified.get("上证A股", [])))
            self.logger.info("  - 深证A股: %d", len(classified.get("深证A股", [])))
            self.logger.info("  - 北证A股: %d", len(classified.get("北证A股", [])))
            self.logger.info("  - T+0基金: %d", len(classified.get("T+0基金", [])))
            self.logger.info("  - 可转债: %d", len(classified.get("可转债", [])))

            return classified

        except Exception as e:
            self.logger.error("加载本地缓存失败: %s", e, exc_info=True)
            return None

    def _fetch_complete_stocks(self) -> pd.DataFrame:
        """
        获取完整品种列表（集合D）

        分别调用market=0、1、2，手动添加market列后合并

        Returns:
            包含market列的完整DataFrame
        """
        self.logger.info("步骤1: 获取完整品种缓存（集合D）")

        quotes = Quotes.factory()
        stocks_list = []

        # 支持的市场：0=深交所, 1=上交所, 2=北交所
        for market in [0, 1, 2]:
            try:
                self.logger.info("  → 调用 stocks(market=%d)...", market)
                df = quotes.stocks(market)

                if df is None or df.empty:
                    self.logger.warning("  ⚠ market=%d 返回空数据", market)
                    continue

                # 手动添加market列
                df["market"] = market
                stocks_list.append(df)

                self.logger.info("  ✓ market=%d: %d 个品种", market, len(df))

            except Exception as e:
                self.logger.error("  ✗ market=%d 获取失败: %s", market, e)

        if not stocks_list:
            raise RuntimeError("未能获取任何品种数据")

        # 合并
        complete_df = pd.concat(stocks_list, ignore_index=True)

        # 补齐代码位数
        complete_df["code"] = complete_df["code"].astype(str).str.zfill(6)

        self.logger.info("  ← 集合D: %d 个品种（含market列）", len(complete_df))

        return complete_df

    def _classify_stocks(self, complete_df: pd.DataFrame) -> Dict[str, List[Dict[str, any]]]:
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
        result["上证A股"] = self._build_stock_list(complete_df[sh_mask])

        # 集合F: 深证A股 (market==0 AND code.startswith('000'|'001'|'002'|'300'|'301'))
        sz_mask = (complete_df["market"] == 0) & (
            complete_df["code"].str.startswith("000")
            | complete_df["code"].str.startswith("001")
            | complete_df["code"].str.startswith("002")
            | complete_df["code"].str.startswith("300")
            | complete_df["code"].str.startswith("301")
        )
        result["深证A股"] = self._build_stock_list(complete_df[sz_mask])

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

        return result

    def _build_stock_list(self, df: pd.DataFrame) -> List[Dict[str, any]]:
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

    def _get_beijing_stocks(self) -> List[Dict[str, any]]:
        """
        获取北证A股（集合B → 集合I）

        从addedcode_bj.cfg读取9开头的代码和简称，添加固定市场代码2

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
                    {"code": stock["code"], "name": stock["name"], "market": 2}  # 固定市场代码
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

    def _get_t0_funds(self, complete_df: pd.DataFrame) -> List[Dict[str, any]]:
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
                    # 无匹配，仍保留但名称为空
                    unmatched_count += 1
                    if len(unmatched_samples) < 3:
                        unmatched_samples.append({"market": market, "code": code})
                    result.append({"code": code, "name": "", "market": market})

            matched_count = total - unmatched_count
            self.logger.info(
                "  → T+0基金: %d 个（匹配到名称: %d，未匹配: %d，示例未匹配: %s）",
                len(result),
                matched_count,
                unmatched_count,
                unmatched_samples,
            )
            return result

        except Exception as e:
            self.logger.warning("  ⚠ 解析T+0基金失败: %s", e)
            return []

    def _get_convertible_bonds(self, complete_df: pd.DataFrame) -> List[Dict[str, any]]:
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
                    matched = complete_df[
                        (complete_df["market"] == mkt) & (complete_df["code"] == code)
                    ]

                    if len(matched) > 0:
                        # 如果有多个匹配，过滤掉指数
                        if len(matched) > 1:
                            non_index = matched[
                                ~matched["name"].str.contains("指数|ETF", na=False, regex=True)
                            ]
                            if len(non_index) > 0:
                                matched = non_index

                        name = str(matched.iloc[0].get("name", ""))
                        result.append({"code": code, "name": name, "market": mkt})
                    else:
                        # 无匹配，仍保留但名称为空
                        unmatched_count += 1
                        if len(unmatched_samples) < 3:
                            unmatched_samples.append({"market": mkt, "code": code})
                        result.append({"code": code, "name": "", "market": mkt})

            matched_count = total - unmatched_count
            self.logger.info(
                "  → 可转债: %d 个（匹配到名称: %d，未匹配: %d，示例未匹配: %s）",
                len(result),
                matched_count,
                unmatched_count,
                unmatched_samples,
            )
            return result

        except Exception as e:
            self.logger.warning("  ⚠ 解析可转债失败: %s", e)
            return []

    def _save_cache(self, classified: Dict[str, List[Dict[str, any]]]) -> None:
        """
        保存分类结果到本地缓存

        Args:
            classified: 分类后的品种字典
        """
        self.logger.info("步骤3: 保存缓存")

        try:
            cache_data = {
                "cache_time": datetime.now().isoformat(),
                "total_count": sum(len(stocks) for stocks in classified.values()),
                "classified": classified,
            }

            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)

            self.logger.info("  ✓ 缓存已保存: %s", self.cache_file)

        except Exception as e:
            self.logger.error("  ✗ 保存缓存失败: %s", e, exc_info=True)
            raise
