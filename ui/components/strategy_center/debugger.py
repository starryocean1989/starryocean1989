# -*- coding: utf-8 -*-
"""基础调试器.

提供断点管理和日志断点功能：
- 断点管理
- 日志断点（在断点处插入日志代码）
- 断点持久化
"""

from typing import Dict, List, Set, Optional
from pathlib import Path
import json

from backend.core.utils import LoggerMixin


class Debugger(LoggerMixin):
    """基础调试器."""

    def __init__(self):
        """初始化调试器."""
        # 断点存储：{file_path: Set[line_numbers]}
        self.breakpoints: Dict[str, Set[int]] = {}

        # 配置文件路径
        self.config_file = Path("config/breakpoints.json")

        # 加载断点配置
        self._load_breakpoints()

        self.logger.info("调试器初始化完成")

    def set_breakpoint(self, file_path: str, line_number: int):
        """设置断点.

        Args:
            file_path: 文件路径
            line_number: 行号
        """
        if file_path not in self.breakpoints:
            self.breakpoints[file_path] = set()

        self.breakpoints[file_path].add(line_number)

        # 保存配置
        self._save_breakpoints()

        self.logger.info(f"设置断点: {file_path}:{line_number}")

    def remove_breakpoint(self, file_path: str, line_number: int):
        """移除断点.

        Args:
            file_path: 文件路径
            line_number: 行号
        """
        if file_path in self.breakpoints:
            self.breakpoints[file_path].discard(line_number)

            # 如果该文件没有断点了，删除条目
            if not self.breakpoints[file_path]:
                del self.breakpoints[file_path]

        # 保存配置
        self._save_breakpoints()

        self.logger.info(f"移除断点: {file_path}:{line_number}")

    def toggle_breakpoint(self, file_path: str, line_number: int):
        """切换断点.

        Args:
            file_path: 文件路径
            line_number: 行号
        """
        if self.has_breakpoint(file_path, line_number):
            self.remove_breakpoint(file_path, line_number)
        else:
            self.set_breakpoint(file_path, line_number)

    def has_breakpoint(self, file_path: str, line_number: int) -> bool:
        """检查是否有断点.

        Args:
            file_path: 文件路径
            line_number: 行号

        Returns:
            bool: 是否有断点
        """
        return file_path in self.breakpoints and line_number in self.breakpoints[file_path]

    def get_breakpoints(self, file_path: Optional[str] = None) -> Dict[str, List[int]]:
        """获取断点列表.

        Args:
            file_path: 文件路径（如果为None，返回所有断点）

        Returns:
            Dict: 断点列表
        """
        if file_path:
            if file_path in self.breakpoints:
                return {file_path: sorted(list(self.breakpoints[file_path]))}
            return {}

        # 返回所有断点
        return {path: sorted(list(lines)) for path, lines in self.breakpoints.items()}

    def clear_breakpoints(self, file_path: Optional[str] = None):
        """清除断点.

        Args:
            file_path: 文件路径（如果为None，清除所有断点）
        """
        if file_path:
            if file_path in self.breakpoints:
                del self.breakpoints[file_path]
                self.logger.info(f"清除文件断点: {file_path}")
        else:
            self.breakpoints.clear()
            self.logger.info("清除所有断点")

        # 保存配置
        self._save_breakpoints()

    def inject_logging_breakpoints(self, file_path: str, code: str) -> str:
        """在断点处注入日志代码.

        Args:
            file_path: 文件路径
            code: 原始代码

        Returns:
            str: 注入日志后的代码
        """
        if file_path not in self.breakpoints or not self.breakpoints[file_path]:
            return code

        lines = code.split("\n")
        breakpoint_lines = sorted(self.breakpoints[file_path], reverse=True)

        for line_num in breakpoint_lines:
            if 0 < line_num <= len(lines):
                # 获取当前行的缩进
                current_line = lines[line_num - 1]
                indent = len(current_line) - len(current_line.lstrip())

                # 创建日志代码
                log_code = " " * indent + f'self.write_log(f"🔴 断点 L{line_num}: {{locals()}}")'

                # 在断点行之前插入日志
                lines.insert(line_num - 1, log_code)

        return "\n".join(lines)

    def export_breakpoints(self, export_path: str):
        """导出断点配置.

        Args:
            export_path: 导出文件路径
        """
        try:
            export_data = {path: sorted(list(lines)) for path, lines in self.breakpoints.items()}

            with open(export_path, "w", encoding="utf-8") as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False)

            self.logger.info(f"断点已导出到: {export_path}")

        except Exception as e:
            self.logger.error(f"导出断点失败: {e}")

    def import_breakpoints(self, import_path: str):
        """导入断点配置.

        Args:
            import_path: 导入文件路径
        """
        try:
            with open(import_path, "r", encoding="utf-8") as f:
                import_data = json.load(f)

            # 清空现有断点
            self.breakpoints.clear()

            # 导入新断点
            for path, lines in import_data.items():
                self.breakpoints[path] = set(lines)

            # 保存配置
            self._save_breakpoints()

            self.logger.info(f"断点已从 {import_path} 导入")

        except Exception as e:
            self.logger.error(f"导入断点失败: {e}")

    def _load_breakpoints(self):
        """加载断点配置."""
        if not self.config_file.exists():
            return

        try:
            with open(self.config_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            # 转换为Set结构
            self.breakpoints = {path: set(lines) for path, lines in data.items()}

            self.logger.info(f"断点配置已加载: {len(self.breakpoints)} 个文件")

        except Exception as e:
            self.logger.error(f"加载断点配置失败: {e}")

    def _save_breakpoints(self):
        """保存断点配置."""
        try:
            # 确保配置目录存在
            self.config_file.parent.mkdir(parents=True, exist_ok=True)

            # 转换为可序列化格式
            data = {path: sorted(list(lines)) for path, lines in self.breakpoints.items()}

            # 保存到文件
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            self.logger.debug("断点配置已保存")

        except Exception as e:
            self.logger.error(f"保存断点配置失败: {e}")
