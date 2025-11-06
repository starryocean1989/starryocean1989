# -*- coding: utf-8 -*-
"""
通达信板块文件解析器

负责解析spblock.dat文件，获取板块分类信息，
特别是提取T+0基金列表。
"""

import asyncio
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

# 🚀 原生IOCP异步文件I/O：直接使用native_iocp
from backend.infrastructure.native.native_iocp.compat import aopen as compat_aopen  # type: ignore

logger = logging.getLogger(__name__)


class BlockParser:
    """通达信板块文件解析器

    负责解析spblock.dat文件，获取板块分类信息，
    特别是提取T+0基金列表。
    """

    def __init__(self, tdx_dir: Optional[Path] = None):
        """初始化板块解析器

        Args:
            tdx_dir: 通达信软件根目录，如果为None则尝试常见根目录
        """
        if tdx_dir is None:
            # 尝试常见根目录
            common_root_dirs = [
                Path("C:/new_tdx"),
                Path("C:/通达信金融终端V7"),
                Path("C:/Program Files/通达信金融终端V7"),
                Path("D:/通达信金融终端V7"),
                Path("C:/tdx"),
                Path("D:/tdx"),
            ]

            self.tdx_dir = None
            for root_dir in common_root_dirs:
                if root_dir.exists():
                    self.tdx_dir = root_dir
                    break

            if not self.tdx_dir:
                logger.warning(
                    "未找到TDX目录，将使用默认路径C:/new_tdx",
                    extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"},
                )
                self.tdx_dir = Path("C:/new_tdx")
        else:
            self.tdx_dir = tdx_dir

        logger.debug(f"BlockParser 初始化，TDX目录: {self.tdx_dir} (存在: {self.tdx_dir.exists()})")

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

        支持文本格式的spblock.dat文件（GBK编码）：
        格式：
        #板块名称
        股票代码1
        股票代码2
        ...

        Returns:
            T+0基金列表，每个元素为字典：
            {
                'code': '159001',
                'name': '易方达黄金ETF',
                'market': 0,  # 0=深证，1=上证
                'exchange': 'SZSE'
            }
        """
        # 🚀 使用异步实现，内部调用asyncio.run()
        try:
            asyncio.get_running_loop()
            # 如果事件循环已经在运行，在新线程中运行
            import concurrent.futures
            import threading

            future = concurrent.futures.Future()

            def _run():
                try:
                    result = asyncio.run(self._get_t0_fund_codes_async())
                    future.set_result(result)
                except Exception as e:
                    future.set_exception(e)

            thread = threading.Thread(target=_run)
            thread.start()
            thread.join()
            return future.result()
        except RuntimeError:
            # 如果没有运行中的事件循环，直接使用asyncio.run()
            return asyncio.run(self._get_t0_fund_codes_async())

    async def _get_t0_fund_codes_async(self) -> List[Dict[str, Any]]:
        """异步获取T+0基金代码列表（内部实现）"""
        if not self.block_file_path or not self.block_file_path.exists():
            logger.warning(
                "⚠️ 未找到spblock.dat文件，无法获取T+0基金列表",
                extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"},
            )
            return []

        try:
            # 🔧 修复：直接解析文本格式的spblock.dat文件（GBK编码）
            # 参考 AsyncTdxBlockReader 的解析逻辑，支持文本格式
            results = []

            # 🚀 使用native_iocp异步读取文件（真异步，无线程池开销）
            # 使用二进制模式读取，然后手动解码为GBK，确保兼容性
            async with await compat_aopen(self.block_file_path, "rb") as f:
                raw_data = await f.read()
            # 解码为GBK文本
            content = raw_data.decode("gbk", errors="ignore")

            lines = content.strip().split("\n")
            current_block = None
            current_codes = []

            for line in lines:
                line = line.strip()

                if not line:
                    continue

                # 板块名称以#开头
                if line.startswith("#"):
                    # 处理上一个板块（如果是T+0基金板块）
                    if current_block and current_codes:
                        block_name = str(current_block)
                        if (
                            "T+0" in block_name
                            or "T0" in block_name
                            or "t+0" in block_name.lower()
                            or "t0" in block_name.lower()
                        ):
                            logger.debug(
                                f"找到T+0基金板块: {block_name}，包含 {len(current_codes)} 个品种",
                                extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"},
                            )

                            # 处理每个代码
                            for code_str in current_codes:
                                code_str = str(code_str).strip()
                                if not code_str or not code_str.isdigit():
                                    continue

                                # 移除前导0（如果有），然后补齐到6位
                                # 例如：0159001 -> 159001，0000001 -> 000001
                                code_str = str(int(code_str)).zfill(6)

                                # 从代码中推断市场代码
                                # 01开头和15开头通常为深证（ETF/LOF），其他为上证
                                if code_str.startswith("01") or code_str.startswith("15"):
                                    market = 0  # 深证
                                    exchange = "SZSE"
                                else:
                                    market = 1  # 上证
                                    exchange = "SSE"

                                results.append(
                                    {
                                        "code": code_str,
                                        "name": "",  # 板块文件不包含品种名称，需要从API匹配
                                        "market": market,
                                        "exchange": exchange,
                                    }
                                )

                    # 开始新板块
                    current_block = line[1:]  # 去掉#
                    current_codes = []
                else:
                    # 股票代码
                    if current_block:
                        current_codes.append(line)

            # 处理最后一个板块
            if current_block and current_codes:
                block_name = str(current_block)
                if (
                    "T+0" in block_name
                    or "T0" in block_name
                    or "t+0" in block_name.lower()
                    or "t0" in block_name.lower()
                ):
                    logger.debug(
                        f"找到T+0基金板块: {block_name}，包含 {len(current_codes)} 个品种",
                        extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"},
                    )

                    for code_str in current_codes:
                        code_str = str(code_str).strip()
                        if not code_str or not code_str.isdigit():
                            continue

                        # 移除前导0（如果有），然后补齐到6位
                        # 例如：0159001 -> 159001，0000001 -> 000001
                        code_str = str(int(code_str)).zfill(6)

                        # 从代码中推断市场代码
                        if code_str.startswith("01") or code_str.startswith("15"):
                            market = 0  # 深证
                            exchange = "SZSE"
                        else:
                            market = 1  # 上证
                            exchange = "SSE"

                        results.append(
                            {
                                "code": code_str,
                                "name": "",
                                "market": market,
                                "exchange": exchange,
                            }
                        )

            if results:
                logger.info(
                    f"✅ 解析T+0基金成功，共 {len(results)} 个品种",
                    extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"},
                )
            else:
                logger.warning(
                    "⚠️ T+0基金板块文件为空或不存在，无法分类T+0基金",
                    extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"},
                )

            return results

        except Exception as e:
            logger.error(
                f"❌ 解析spblock.dat文件失败: {e}",
                exc_info=True,
                extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"},
            )
            # 添加详细的诊断信息
            if self.block_file_path and self.block_file_path.exists():
                file_size = self.block_file_path.stat().st_size
                logger.error(
                    f"   文件路径: {self.block_file_path}",
                    extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"},
                )
                logger.error(
                    f"   文件大小: {file_size} 字节",
                    extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"},
                )
                try:
                    with open(self.block_file_path, "rb") as f:
                        first_bytes = f.read(16)
                        logger.error(
                            f"   文件前16字节(hex): {first_bytes.hex()}",
                            extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"},
                        )
                        logger.error(
                            f"   文件前16字节(ascii): {first_bytes}",
                            extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"},
                        )
                except Exception as read_e:
                    logger.error(
                        f"   读取文件头失败: {read_e}",
                        extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"},
                    )
            return []
