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
from pytdx.reader.block_reader import (
    BlockReader,
    BlockReader_TYPE_FLAT,
)


class BlockParser:
    """通达信板块文件解析器"""

    def __init__(self, tdx_dir: Optional[Path] = None):
        """
        初始化板块解析器

        Args:
            tdx_dir: 通达信软件根目录，如果为None则自动查找
        """
        self.tdx_dir = tdx_dir
        self.block_file_path = None
        self._find_block_file()

    def _find_block_file(self) -> None:
        """查找spblock.dat文件"""
        if self.tdx_dir and self.tdx_dir.exists():
            block_file = self.tdx_dir / "new_tdx" / "spblock.dat"
            if block_file.exists():
                self.block_file_path = block_file
                return

        # 尝试常见路径
        common_paths = [
            Path("C:/通达信金融终端V7/new_tdx/spblock.dat"),
            Path("C:/Program Files/通达信金融终端V7/new_tdx/spblock.dat"),
            Path("D:/通达信金融终端V7/new_tdx/spblock.dat"),
        ]

        for path in common_paths:
            if path.exists():
                self.block_file_path = path
                return

    def parse_block_file(self) -> pd.DataFrame:
        """
        解析spblock.dat文件

        Returns:
            包含板块信息的DataFrame，列包括：
            - blockname: 板块名称
            - block_type: 板块类型
            - code: 品种代码
        """
        if not self.block_file_path or not self.block_file_path.exists():
            raise FileNotFoundError("未找到spblock.dat文件，请检查通达信软件路径")

        try:
            reader = BlockReader()
            df = reader.get_df(str(self.block_file_path), BlockReader_TYPE_FLAT)
            return df
        except Exception as e:
            raise RuntimeError(f"解析spblock.dat文件失败: {e}") from e

    def get_target_blocks(self) -> Dict[str, List[str]]:
        """
        获取目标板块的品种代码列表

        Returns:
            字典，键为板块名称，值为品种代码列表
        """
        df = self.parse_block_file()

        target_blocks = {"融资融券": [], "T+0基金": [], "含可转债": []}

        for _, row in df.iterrows():
            block_name = str(row["blockname"])
            code = str(row["code"])

            # 融资融券板块：提取9开头的品种（北证A股）
            if "融资融券" in block_name and code.startswith("9"):
                target_blocks["融资融券"].append(code)

            # T+0基金板块
            elif "T+0基金" in block_name:
                target_blocks["T+0基金"].append(code)

            # 含可转债板块
            elif "含可转债" in block_name:
                target_blocks["含可转债"].append(code)

        return target_blocks

    def get_beijing_stocks(self) -> List[str]:
        """
        获取北证A股品种代码列表

        Returns:
            北证A股品种代码列表
        """
        target_blocks = self.get_target_blocks()
        return target_blocks["融资融券"]

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
        result = {}

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
