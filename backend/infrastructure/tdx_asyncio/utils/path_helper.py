# -*- coding: utf-8 -*-
"""
通达信文件路径管理工具

提供通达信本地文件路径管理功能:
- 日K线文件路径
- 分钟线文件路径
- 配置文件路径
- 板块文件路径
"""

import logging
from pathlib import Path
from typing import Optional, List

logger = logging.getLogger(__name__)


# ==============================================================================
# 通达信路径辅助类
# ==============================================================================


class TdxPathHelper:
    """通达信文件路径辅助类

    功能:
    - 获取各类数据文件路径
    - 自动查找配置文件
    - 支持多市场(上海/深圳/北京)

    示例:
        >>> helper = TdxPathHelper(Path("C:/new_tdx"))
        >>> # 获取日K线文件路径
        >>> day_file = helper.get_day_file_path(market=1, code="600000")
        >>> print(day_file)  # C:/new_tdx/vipdoc/sh/lday/sh600000.day
        >>>
        >>> # 获取分钟线文件路径
        >>> min_file = helper.get_minute_file_path(market=0, code="000001")
        >>> print(min_file)  # C:/new_tdx/vipdoc/sz/minline/sz000001.lc1
    """
    # 说明：本类仅负责拼接并返回规范化路径字符串，不校验文件是否存在；
    # 使用者可结合 Path.exists()/is_file() 在读取前进行检查。
    
    # 市场代码映射
    MARKET_PREFIX = {
        0: "sz",  # 深圳
        1: "sh",  # 上海
        2: "bj",  # 北京
    }

    MARKET_DIR = {
        0: "sz",  # 深圳
        1: "sh",  # 上海
        2: "bj",  # 北京
    }

    def __init__(self, tdx_root: Path):
        """初始化路径辅助类

        Args:
            tdx_root: 通达信软件根目录
        """
        self.tdx_root = Path(tdx_root)

        if not self.tdx_root.exists():
            logger.warning(f"通达信根目录不存在: {self.tdx_root}")

    def get_day_file_path(self, market: int, code: str) -> Path:
        """获取日K线文件路径

        Args:
            market: 市场代码 (0=深圳, 1=上海, 2=北京)
            code: 股票代码

        Returns:
            文件路径,如 C:/new_tdx/vipdoc/sh/lday/sh600000.day

        示例:
            >>> helper = TdxPathHelper(Path("C:/new_tdx"))
            >>> path = helper.get_day_file_path(market=1, code="600000")
            >>> print(path)  # C:/new_tdx/vipdoc/sh/lday/sh600000.day
        """
        # 路径规则：vipdoc/<market>/lday/<prefix><code>.day，其中 market: 0=sz,1=sh,2=bj
        # 注意：不进行存在性校验；若需读取请先检查 path.exists()
        market_prefix = self.MARKET_PREFIX.get(market, "sh")
        market_dir = self.MARKET_DIR.get(market, "sh")

        return self.tdx_root / "vipdoc" / market_dir / "lday" / f"{market_prefix}{code}.day"

    def get_minute_file_path(self, market: int, code: str) -> Path:
        """获取1分钟线文件路径

        Args:
            market: 市场代码 (0=深圳, 1=上海, 2=北京)
            code: 股票代码

        Returns:
            文件路径,如 C:/new_tdx/vipdoc/sz/minline/sz000001.lc1

        示例:
            >>> helper = TdxPathHelper(Path("C:/new_tdx"))
            >>> path = helper.get_minute_file_path(market=0, code="000001")
            >>> print(path)  # C:/new_tdx/vipdoc/sz/minline/sz000001.lc1
        """
        # 路径规则：vipdoc/<market>/minline/<prefix><code>.lc1（1分钟线）
        # 注意：不进行存在性校验；若需读取请先检查 path.exists()
        market_prefix = self.MARKET_PREFIX.get(market, "sh")
        market_dir = self.MARKET_DIR.get(market, "sh")

        return self.tdx_root / "vipdoc" / market_dir / "minline" / f"{market_prefix}{code}.lc1"

    def get_lc5_file_path(self, market: int, code: str) -> Path:
        """获取5分钟线文件路径

        Args:
            market: 市场代码 (0=深圳, 1=上海, 2=北京)
            code: 股票代码

        Returns:
            文件路径,如 C:/new_tdx/vipdoc/sh/fzline/sh600000.lc5

        示例:
            >>> helper = TdxPathHelper(Path("C:/new_tdx"))
            >>> path = helper.get_lc5_file_path(market=1, code="600000")
            >>> print(path)  # C:/new_tdx/vipdoc/sh/fzline/sh600000.lc5
        """
        # 路径规则：vipdoc/<market>/fzline/<prefix><code>.lc5（5分钟线）
        # 注意：不进行存在性校验；若需读取请先检查 path.exists()
        market_prefix = self.MARKET_PREFIX.get(market, "sh")
        market_dir = self.MARKET_DIR.get(market, "sh")

        return self.tdx_root / "vipdoc" / market_dir / "fzline" / f"{market_prefix}{code}.lc5"

    def get_vipdoc_dir(self, market: int) -> Path:
        """获取市场数据目录

        Args:
            market: 市场代码 (0=深圳, 1=上海, 2=北京)

        Returns:
            目录路径,如 C:/new_tdx/vipdoc/sh

        示例:
            >>> helper = TdxPathHelper(Path("C:/new_tdx"))
            >>> vipdoc_dir = helper.get_vipdoc_dir(market=1)
            >>> print(vipdoc_dir)  # C:/new_tdx/vipdoc/sh
        """
        # 返回 vipdoc/<market> 顶层目录；适合遍历子目录或批量读取。
        market_dir = self.MARKET_DIR.get(market, "sh")
        return self.tdx_root / "vipdoc" / market_dir

    def get_lday_dir(self, market: int) -> Path:
        """获取日K线目录

        Args:
            market: 市场代码 (0=深圳, 1=上海, 2=北京)

        Returns:
            目录路径,如 C:/new_tdx/vipdoc/sh/lday

        示例:
            >>> helper = TdxPathHelper(Path("C:/new_tdx"))
            >>> lday_dir = helper.get_lday_dir(market=1)
            >>> print(lday_dir)  # C:/new_tdx/vipdoc/sh/lday
        """
        # 返回日K线目录：vipdoc/<market>/lday
        return self.get_vipdoc_dir(market) / "lday"

    def get_minline_dir(self, market: int) -> Path:
        """获取分钟线目录

        Args:
            market: 市场代码 (0=深圳, 1=上海, 2=北京)

        Returns:
            目录路径,如 C:/new_tdx/vipdoc/sz/minline

        示例:
            >>> helper = TdxPathHelper(Path("C:/new_tdx"))
            >>> minline_dir = helper.get_minline_dir(market=0)
            >>> print(minline_dir)  # C:/new_tdx/vipdoc/sz/minline
        """
        # 返回1分钟线目录：vipdoc/<market>/minline
        return self.get_vipdoc_dir(market) / "minline"

    def get_fzline_dir(self, market: int) -> Path:
        """获取5分钟线目录

        Args:
            market: 市场代码 (0=深圳, 1=上海, 2=北京)

        Returns:
            目录路径,如 C:/new_tdx/vipdoc/sh/fzline

        示例:
            >>> helper = TdxPathHelper(Path("C:/new_tdx"))
            >>> fzline_dir = helper.get_fzline_dir(market=1)
            >>> print(fzline_dir)  # C:/new_tdx/vipdoc/sh/fzline
        """
        # 返回5分钟线目录：vipdoc/<market>/fzline
        return self.get_vipdoc_dir(market) / "fzline"

    def find_config_file(
        self, filename: str, search_subdirs: Optional[List[str]] = None
    ) -> Optional[Path]:
        """
        查找配置文件（支持多个常见位置）

        Args:
            filename: 配置文件名，如 "addedcode_bj.cfg", "tdxstat2.cfg", "spblock.dat"
            search_subdirs: 要搜索的子目录列表，如果为None则使用默认列表

        Returns:
            文件路径，如果未找到则返回None

        示例:
            >>> helper = TdxPathHelper(Path("C:/new_tdx"))
            >>> # 查找北证配置文件
            >>> path = helper.find_config_file("addedcode_bj.cfg")
            >>> if path:
            >>>     print(f"找到配置文件: {path}")
            >>> # 查找板块文件（指定搜索目录）
            >>> path = helper.find_config_file("spblock.dat", ["T0002/blocknew", "T0002/block"])
        """
        # 默认搜索路径包含：T0002/blocknew, T0002/block, T0002, T0001, config, 根目录。
        # 先尝试直接路径，再递归 rglob 搜索；返回首个命中的文件。
        # 默认搜索目录
        if search_subdirs is None:
            search_subdirs = ["T0002/blocknew", "T0002/block", "T0002", "T0001", "config", ""]

        for subdir in search_subdirs:
            if subdir:
                search_dir = self.tdx_root / subdir
            else:
                search_dir = self.tdx_root

            if not search_dir.exists():
                continue

            # 先检查直接路径
            direct_path = search_dir / filename
            if direct_path.exists() and direct_path.is_file():
                logger.debug(f"找到配置文件: {direct_path}")
                return direct_path

            # 递归搜索
            for config_file in search_dir.rglob(filename):
                if config_file.is_file():
                    logger.debug(f"找到配置文件: {config_file}")
                    return config_file

        logger.debug(f"未找到配置文件: {filename}")
        return None

    def get_block_file_path(self, filename: str = "spblock.dat") -> Optional[Path]:
        """
        获取板块文件路径（优先查找常见位置）

        Args:
            filename: 板块文件名，默认为 "spblock.dat"

        Returns:
            文件路径，如果未找到则返回None

        示例:
            >>> helper = TdxPathHelper(Path("C:/new_tdx"))
            >>> path = helper.get_block_file_path("spblock.dat")
            >>> if path:
            >>>     print(f"找到板块文件: {path}")
        """
        # 优先常见位置（T0002/T0001 下的 blocknew 与 block），否则回退到递归搜索。
        # 优先查找常见位置
        common_paths = [
            self.tdx_root / "T0002" / "blocknew" / filename,
            self.tdx_root / "T0002" / "block" / filename,
            self.tdx_root / "T0001" / "blocknew" / filename,
            self.tdx_root / "T0001" / "block" / filename,
        ]

        for path in common_paths:
            if path.exists() and path.is_file():
                logger.debug(f"找到板块文件: {path}")
                return path

        # 如果常见位置没有，使用find_config_file递归搜索
        return self.find_config_file(filename, ["T0002/blocknew", "T0002/block", "T0002", "T0001"])

    def get_config_file_path(self, filename: str) -> Optional[Path]:
        """
        获取配置文件路径（优先查找T0002目录）

        Args:
            filename: 配置文件名，如 "addedcode_bj.cfg", "tdxstat2.cfg"

        Returns:
            文件路径，如果未找到则返回None

        示例:
            >>> helper = TdxPathHelper(Path("C:/new_tdx"))
            >>> path = helper.get_config_file_path("addedcode_bj.cfg")
            >>> if path:
            >>>     print(f"找到配置文件: {path}")
        """
        # 先检查 T0002 直达路径；未命中则递归搜索（包含 T0001/config/根目录）。
        # 优先查找T0002目录
        t0002_path = self.tdx_root / "T0002" / filename
        if t0002_path.exists() and t0002_path.is_file():
            logger.debug(f"找到配置文件: {t0002_path}")
            return t0002_path

        # 如果T0002目录没有，使用find_config_file递归搜索
        return self.find_config_file(filename, ["T0002", "T0001", "config", ""])

    def get_data_file_path(self, market: int, code: str, data_type: str = "day") -> Path:
        """
        获取数据文件路径（统一接口）

        Args:
            market: 市场代码 (0=深圳, 1=上海, 2=北京)
            code: 股票代码
            data_type: 数据类型 ("day", "minute", "lc5")

        Returns:
            文件路径

        示例:
            >>> helper = TdxPathHelper(Path("C:/new_tdx"))
            >>> # 获取日K线文件路径
            >>> path = helper.get_data_file_path(1, "600000", "day")
            >>> print(path)  # C:/new_tdx/vipdoc/sh/lday/sh600000.day
            >>> # 获取分钟线文件路径
            >>> path = helper.get_data_file_path(0, "000001", "minute")
            >>> print(path)  # C:/new_tdx/vipdoc/sz/minline/sz000001.lc1
            >>> # 获取5分钟线文件路径
            >>> path = helper.get_data_file_path(1, "600000", "lc5")
            >>> print(path)  # C:/new_tdx/vipdoc/sh/fzline/sh600000.lc5
        """
        # 统一入口，根据 data_type 分发至具体路径构造函数；不进行存在性校验。
        data_type = data_type.lower()

        if data_type == "day":
            return self.get_day_file_path(market, code)
        elif data_type in ["minute", "1m", "min"]:
            return self.get_minute_file_path(market, code)
        elif data_type in ["lc5", "5m", "5min"]:
            return self.get_lc5_file_path(market, code)
        else:
            raise ValueError(f"不支持的数据类型: {data_type}")


# ==============================================================================
# 便捷函数
# ==============================================================================


def find_tdx_root() -> Optional[Path]:
    """自动查找通达信根目录

    Returns:
        通达信根目录路径,如果未找到则返回None

    示例:
        >>> tdx_root = find_tdx_root()
        >>> if tdx_root:
        >>>     print(f"找到通达信目录: {tdx_root}")
        >>>     helper = TdxPathHelper(tdx_root)
    """
    # 仅尝试常见安装路径（C:/new_tdx、通达信金融终端V7、tdx 等）；
    # 若未找到请直接传入自定义根路径创建 TdxPathHelper。
    # 常见根目录
    common_roots = [
        Path("C:/new_tdx"),
        Path("C:/通达信金融终端V7"),
        Path("C:/Program Files/通达信金融终端V7"),
        Path("D:/通达信金融终端V7"),
        Path("C:/tdx"),
        Path("D:/tdx"),
    ]

    for root in common_roots:
        if root.exists():
            logger.debug(f"找到通达信根目录: {root}")
            return root

    logger.warning("未找到通达信根目录")
    return None


from .helper import get_market_from_code  # 使用helper.py中的增强版本


# ==============================================================================
# 导出
# ==============================================================================

__all__ = [
    "TdxPathHelper",
    "find_tdx_root",
    "get_market_from_code",  # 从helper.py导入
]
