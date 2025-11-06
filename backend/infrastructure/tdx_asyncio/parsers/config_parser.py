# -*- coding: utf-8 -*-
"""
TDX配置文件解析器

负责解析通达信配置文件，获取特定品种列表：
- addedcode_bj.cfg: 北证A股列表
- tdxstat2.cfg: 可转债列表
"""

import asyncio
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

# 🚀 原生IOCP异步文件I/O：直接使用native_iocp
from backend.infrastructure.native.native_iocp.compat import aopen as compat_aopen  # type: ignore

logger = logging.getLogger(__name__)


class TdxConfigFileParser:
    """TDX配置文件解析器

    负责解析通达信配置文件，获取特定品种列表：
    - addedcode_bj.cfg: 北证A股列表
    - tdxstat2.cfg: 可转债列表
    """

    def __init__(self, tdx_dir: Optional[Path] = None):
        """初始化解析器

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

        logger.debug(
            f"TdxConfigFileParser 初始化，TDX目录: {self.tdx_dir} (存在: {self.tdx_dir.exists()})",
            extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"},
        )

    def parse_addedcode_bj(self) -> List[Dict[str, Any]]:
        """解析北证A股配置文件 addedcode_bj.cfg

        文件格式：
        第1行：000000,0,278,20251010, （标题行，跳过）
        后续行：44|832000|920000|安徽凤凰(已切换)|20251009
        格式：字段0|旧代码|新代码|名称|日期

        Returns:
            北证品种列表，每个元素为字典：
            {
                'code': '920000',
                'name': '安徽凤凰',
                'market': 2,  # 北证固定为2
                'exchange': 'BSE'
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
                    result = asyncio.run(self._parse_addedcode_bj_async())
                    future.set_result(result)
                except Exception as e:
                    future.set_exception(e)

            thread = threading.Thread(target=_run)
            thread.start()
            thread.join()
            return future.result()
        except RuntimeError:
            # 如果没有运行中的事件循环，直接使用asyncio.run()
            return asyncio.run(self._parse_addedcode_bj_async())

    async def _parse_addedcode_bj_async(self) -> List[Dict[str, Any]]:
        """异步解析北证A股配置文件（内部实现）"""
        config_file = self._find_config_file("addedcode_bj.cfg")
        if config_file is None:
            logger.warning(
                "⚠️ 未找到 addedcode_bj.cfg 文件",
                extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"},
            )
            return []

        try:
            results = []
            # 🚀 使用native_iocp异步读取文件（真异步，无线程池开销）
            # 使用二进制模式读取，然后手动解码为GBK，确保兼容性
            async with await compat_aopen(config_file, "rb") as f:
                raw_data = await f.read()
            # 解码为GBK文本
            content = raw_data.decode("gbk", errors="ignore")

            # 解析内容
            first_line = True
            for line in content.splitlines():
                line = line.strip()
                if not line:
                    continue

                # 跳过第1行（标题行）
                if first_line:
                    first_line = False
                    continue

                # 解析行：格式 44|832000|920000|安徽凤凰(已切换)|20251009
                parts = line.split("|")
                if len(parts) < 4:
                    continue

                # 提取新代码（北证代码，通常是92开头）和名称
                old_code = parts[1].strip()  # 旧代码（可能是43/83/87开头）
                new_code = parts[2].strip()  # 新代码（92开头）
                name = parts[3].strip()

                # 清理名称（移除括号内容）
                if "(" in name:
                    name = name.split("(")[0].strip()

                # 使用新代码（92开头），如果没有新代码则使用旧代码
                code = new_code if new_code else old_code
                if not code:
                    continue

                # 补齐到6位
                code = code.zfill(6)

                results.append(
                    {
                        "code": code,
                        "name": name,
                        "market": 2,  # 北证固定为2
                        "exchange": "BSE",
                    }
                )

            logger.info(
                f"✅ 解析北证A股配置文件成功，共 {len(results)} 个品种",
                extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"},
            )
            return results

        except Exception as e:
            logger.error(
                f"❌ 解析北证A股配置文件失败: {e}。文件路径: {config_file if 'config_file' in locals() else '未知'}",
                exc_info=True,
                extra={"log_type": "ALERT", "scenario": "refresh_symbol_list"},
            )
            return []

    def parse_tdxstat2(self) -> Dict[int, List[str]]:
        """解析可转债配置文件 tdxstat2.cfg

        文件格式：文本格式（GBK编码），用|分隔
        格式：市场代码|代码|日期|...其他字段
        示例：0|000001|20251009|118706.16||94222.41||...

        Returns:
            可转债代码字典，key为市场代码（0=深证，1=上证），value为代码列表
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
                    result = asyncio.run(self._parse_tdxstat2_async())
                    future.set_result(result)
                except Exception as e:
                    future.set_exception(e)

            thread = threading.Thread(target=_run)
            thread.start()
            thread.join()
            return future.result()
        except RuntimeError:
            # 如果没有运行中的事件循环，直接使用asyncio.run()
            return asyncio.run(self._parse_tdxstat2_async())

    async def _parse_tdxstat2_async(self) -> Dict[int, List[str]]:
        """异步解析可转债配置文件（内部实现）"""
        config_file = self._find_config_file("tdxstat2.cfg")
        if config_file is None:
            logger.warning(
                "⚠️ 未找到 tdxstat2.cfg 文件",
                extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"},
            )
            return {0: [], 1: []}

        try:
            results = {0: [], 1: []}

            # 🚀 使用native_iocp异步读取文件（真异步，无线程池开销）
            # 使用二进制模式读取，然后手动解码为GBK，确保兼容性
            async with await compat_aopen(config_file, "rb") as f:
                raw_data = await f.read()
            # 解码为GBK文本
            content = raw_data.decode("gbk", errors="ignore")

            # 解析内容
            for line in content.splitlines():
                line = line.strip()
                if not line:
                    continue

                # 解析行：格式 市场代码|代码|日期|...
                parts = line.split("|")
                if len(parts) < 2:
                    continue

                # 提取市场代码和代码
                try:
                    market = int(parts[0].strip())
                    code = parts[1].strip()
                except (ValueError, IndexError):
                    continue

                if not code or not code.isdigit():
                    continue

                # 补齐到6位
                code = code.zfill(6)

                # 可转债代码通常以12/11开头（深证）或以11开头（上证）
                if market == 0 and code.startswith("12"):
                    results[0].append(code)
                elif market == 1 and code.startswith("11"):
                    results[1].append(code)

            total_count = len(results[0]) + len(results[1])
            logger.info(
                f"✅ 解析可转债配置文件成功，深证 {len(results[0])} 个，上证 {len(results[1])} 个，共 {total_count} 个",
                extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"},
            )
            return results

        except Exception as e:
            logger.error(
                f"❌ 解析可转债配置文件失败: {e}。文件路径: {config_file if 'config_file' in locals() else '未知'}",
                exc_info=True,
                extra={"log_type": "ALERT", "scenario": "refresh_symbol_list"},
            )
            return {0: [], 1: []}

    def _find_config_file(self, filename: str) -> Optional[Path]:
        """查找配置文件（递归搜索）

        Args:
            filename: 配置文件名

        Returns:
            文件路径，如果未找到则返回None
        """
        search_dirs = []

        # 首先尝试配置的TDX目录
        if self.tdx_dir and self.tdx_dir.exists():
            search_dirs.append(self.tdx_dir)
        else:
            logger.debug(
                f"TDX目录未配置或不存在: {self.tdx_dir}，尝试常见根目录",
                extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"},
            )

        # 常见根目录
        common_root_dirs = [
            Path("C:/new_tdx"),
            Path("C:/通达信金融终端V7"),
            Path("C:/Program Files/通达信金融终端V7"),
            Path("D:/通达信金融终端V7"),
            Path("C:/tdx"),
            Path("D:/tdx"),
        ]

        for root_dir in common_root_dirs:
            if root_dir.exists() and root_dir not in search_dirs:
                search_dirs.append(root_dir)

        if not search_dirs:
            logger.warning(
                f"未找到配置文件: {filename}（未找到有效的TDX目录）",
                extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"},
            )
            return None

        # 常见子目录
        common_subdirs = ["T0002", "T0001", "config", ""]

        logger.debug(
            f"🔍 搜索配置文件: {filename}（搜索 {len(search_dirs)} 个TDX目录）",
            extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"},
        )

        for tdx_dir in search_dirs:
            for subdir in common_subdirs:
                search_dir = tdx_dir / subdir if subdir else tdx_dir
                if not search_dir.exists():
                    continue

                # 递归搜索
                for config_file in search_dir.rglob(filename):
                    if config_file.is_file():
                        logger.info(
                            f"✅ 找到配置文件: {config_file}",
                            extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"},
                        )
                        return config_file

        logger.warning(
            f"⚠️ 未找到配置文件: {filename}（已搜索 {len(search_dirs)} 个TDX目录）",
            extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"},
        )
        return None
