# -*- coding: utf-8 -*-
"""
通达信配置文件解析模块

负责解析通达信软件根目录下的配置文件：
- tdxstat2.cfg: 可转债代码（市场1的11开头、市场0的12开头）
- addedcode_bj.cfg: 北交所股票代码和简称（9开头，GBK编码）
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class TdxConfigFileParser:
    """通达信配置文件解析器"""

    def __init__(self, tdx_dir: Optional[Path] = None):
        """
        初始化配置文件解析器

        Args:
            tdx_dir: 通达信软件根目录，如果为None则自动查找
        """
        self.tdx_dir = tdx_dir
        self.tdxstat2_path: Optional[Path] = None
        self.addedcode_bj_path: Optional[Path] = None
        self._find_config_files()

    def _find_config_files(self) -> None:
        """查找配置文件（递归搜索）"""
        if self.tdx_dir and self.tdx_dir.exists():
            # 在指定目录下递归搜索
            self._search_config_files_in_dir(self.tdx_dir)
            if self.tdxstat2_path and self.addedcode_bj_path:
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
            if root_dir.exists() and self._search_config_files_in_dir(root_dir):
                break

    def _search_config_files_in_dir(self, directory: Path) -> bool:
        """
        在指定目录下递归搜索配置文件

        Args:
            directory: 要搜索的目录

        Returns:
            是否找到所有配置文件
        """
        try:
            logger.info("正在递归搜索 %s 目录下的配置文件...", directory)

            # 搜索 tdxstat2.cfg
            if not self.tdxstat2_path:
                for file in directory.rglob("tdxstat2.cfg"):
                    if file.is_file():
                        self.tdxstat2_path = file
                        logger.info("✓ 找到 tdxstat2.cfg: %s", file)
                        break

            # 搜索 addedcode_bj.cfg
            if not self.addedcode_bj_path:
                for file in directory.rglob("addedcode_bj.cfg"):
                    if file.is_file():
                        self.addedcode_bj_path = file
                        logger.info("✓ 找到 addedcode_bj.cfg: %s", file)
                        break

            # 如果都找到了，返回True
            if self.tdxstat2_path and self.addedcode_bj_path:
                return True

            if not self.tdxstat2_path:
                logger.warning("在 %s 目录下未找到 tdxstat2.cfg 文件", directory)
            if not self.addedcode_bj_path:
                logger.warning("在 %s 目录下未找到 addedcode_bj.cfg 文件", directory)

            return False

        except OSError as e:
            logger.warning("搜索 %s 时发生错误: %s", directory, e)
            return False

    def parse_tdxstat2(self) -> Dict[int, List[str]]:
        """
        解析tdxstat2.cfg文件，获取可转债代码

        文件格式：每行一个品种代码，纯数字
        - 市场代码1且品种代码11开头的6位代码
        - 市场代码0且品种代码12开头的6位代码

        Returns:
            {market: [codes]}  # market=1的11开头, market=0的12开头
        """
        if not self.tdxstat2_path or not self.tdxstat2_path.exists():
            logger.warning("tdxstat2.cfg 文件不存在，返回空字典")
            return {0: [], 1: []}

        result: Dict[int, List[str]] = {0: [], 1: []}

        try:
            with open(self.tdxstat2_path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    # 每行应该是一个6位数字代码
                    if line.isdigit() and len(line) == 6:
                        code = line

                        # 判断市场代码：11开头的是市场1，12开头的是市场0
                        if code.startswith("11"):
                            result[1].append(code)
                        elif code.startswith("12"):
                            result[0].append(code)

            logger.info(
                "成功解析 tdxstat2.cfg: 市场0有 %d 个可转债, 市场1有 %d 个可转债",
                len(result[0]),
                len(result[1]),
            )
            return result

        except Exception as e:
            logger.error("解析 tdxstat2.cfg 失败: %s", e, exc_info=True)
            return {0: [], 1: []}

    def parse_addedcode_bj(self) -> List[Dict[str, str]]:
        """
        解析addedcode_bj.cfg文件（GBK编码），获取北交所股票代码和简称

        文件格式：每行为 `代码|简称`，GBK编码
        - 代码为9开头的6位数字

        Returns:
            [{"code": "9xxxxx", "name": "简称"}, ...]
        """
        if not self.addedcode_bj_path or not self.addedcode_bj_path.exists():
            logger.warning("addedcode_bj.cfg 文件不存在，返回空列表")
            return []

        result = []

        try:
            # 使用GBK编码读取文件
            with open(self.addedcode_bj_path, "r", encoding="gbk", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    # 格式：代码|简称
                    parts = line.split("|")
                    if len(parts) >= 2:
                        code = parts[0].strip()
                        name = parts[1].strip()

                        # 只保留9开头的6位代码
                        if code.isdigit() and len(code) == 6 and code.startswith("9"):
                            result.append({"code": code, "name": name})

            logger.info("成功解析 addedcode_bj.cfg: %d 个北交所股票", len(result))
            return result

        except Exception as e:
            logger.error("解析 addedcode_bj.cfg 失败: %s", e, exc_info=True)
            return []

    def is_available(self) -> bool:
        """
        检查配置文件是否可用

        Returns:
            是否可用
        """
        return (self.tdxstat2_path is not None and self.tdxstat2_path.exists()) or (
            self.addedcode_bj_path is not None and self.addedcode_bj_path.exists()
        )

    def get_file_info(self) -> Dict[str, Dict[str, str]]:
        """
        获取配置文件信息

        Returns:
            文件信息字典
        """
        info = {}

        if self.tdxstat2_path and self.tdxstat2_path.exists():
            info["tdxstat2.cfg"] = {
                "status": "可用",
                "path": str(self.tdxstat2_path),
                "size": f"{self.tdxstat2_path.stat().st_size / 1024:.2f} KB",
            }
        else:
            info["tdxstat2.cfg"] = {"status": "不可用", "path": ""}

        if self.addedcode_bj_path and self.addedcode_bj_path.exists():
            info["addedcode_bj.cfg"] = {
                "status": "可用",
                "path": str(self.addedcode_bj_path),
                "size": f"{self.addedcode_bj_path.stat().st_size / 1024:.2f} KB",
            }
        else:
            info["addedcode_bj.cfg"] = {"status": "不可用", "path": ""}

        return info
