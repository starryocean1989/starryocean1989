# -*- coding: utf-8 -*-
"""
通达信板块文件解析模块

负责解析通达信软件根目录下的spblock.dat文件，提取特定板块的品种代码：
- 融资融券板块：提取9开头品种（北证A股）
- T+0基金板块
- 含可转债板块

基于pytdx.reader.BlockReader扩展，支持完整GBK编码解析。
"""

from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd  # noqa: TC002


class BlockParser:
    """通达信板块文件解析器"""

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
        import logging

        logger = logging.getLogger(__name__)

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
        import logging

        logger = logging.getLogger(__name__)

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
                return pd.DataFrame(columns=["blockname", "code", "block_type"])  # type: ignore[call-overload]

            df = pd.DataFrame(results)
            logger.info(
                "成功解析spblock.dat: %d 条记录，%d 个板块", len(df), df["blockname"].nunique()
            )
            return df

        except Exception as e:
            logger.error("自定义解析spblock.dat失败: %s", e, exc_info=True)
            # 返回空DataFrame但保持结构
            return pd.DataFrame(columns=["blockname", "code", "block_type"])  # type: ignore[call-overload]

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


class CustomBlockParser:
    """自定义板块解析器，支持更灵活的板块识别"""

    def __init__(self, tdx_dir: Optional[Path] = None):
        """
        初始化自定义板块解析器

        Args:
            tdx_dir: 通达信软件根目录
        """
        self.tdx_dir = tdx_dir
        self.parser = BlockParser(tdx_dir)

    def parse_by_keywords(self, keywords: List[str]) -> Dict[str, List[str]]:
        """
        根据关键词解析板块

        Args:
            keywords: 关键词列表

        Returns:
            包含关键词的板块及其品种代码
        """
        if not self.parser.is_available():
            return {}

        df = self.parser.parse_block_file()
        result: Dict[str, List[str]] = {}

        for keyword in keywords:
            result[keyword] = []

            for _, row in df.iterrows():
                block_name = str(row["blockname"])
                code = str(row["code"])

                if keyword in block_name:
                    result[keyword].append(code)

        return result

    def get_stocks_by_pattern(self, pattern: str) -> List[str]:
        """
        根据代码模式获取品种

        Args:
            pattern: 代码模式，如"9*"表示9开头的品种

        Returns:
            匹配模式的品种代码列表
        """
        if not self.parser.is_available():
            return []

        df = self.parser.parse_block_file()
        stocks = []

        # 将模式映射为前缀
        pattern_map = {
            "9*": "9",
            "688*": "688",
            "60*": "60",
            "000*": "000",
            "001*": "001",
            "002*": "002",
            "300*": "300",
            "301*": "301",
        }

        prefix = pattern_map.get(pattern)
        if prefix is None:
            return []

        for _, row in df.iterrows():
            code = str(row["code"])
            if code.startswith(prefix):
                stocks.append(code)

        return list(set(stocks))  # 去重
