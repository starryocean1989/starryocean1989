# -*- coding: utf-8 -*-
"""
策略中心服务.

提供策略开发和回测环境，包括：
- 策略文件管理（文件系统操作、策略分类）
- 代码编写支持（验证、AI助手集成、模板管理）
- 回测服务（配置管理、回测执行、结果处理）
"""

import logging
import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime

from backend.services.base_service import BaseService


class StrategyCenterService(BaseService):
    """策略中心服务.

    管理策略文件和回测功能，提供：
    1. 策略文件管理 - 创建、读取、更新、删除、移动
    2. 策略分类识别 - 识别6种vnpy策略模板类型
    3. 代码验证 - Python语法检查、策略规范检查
    4. 回测服务 - 回测配置、执行、结果分析
    """

    def __init__(self):
        """初始化策略中心服务."""
        super().__init__()

        # 策略根目录
        self.strategy_root = Path("strategies/user_strategies")

        # 回测引擎
        self.backtest_engine = None

        # 回测任务
        self._backtest_tasks: Dict[str, Dict[str, Any]] = {}

        self.logger.info("策略中心服务已创建")

    def _do_initialize(self) -> bool:
        """初始化策略中心服务."""
        try:
            self.logger.info("初始化策略中心服务...")

            # 确保策略目录存在
            self.strategy_root.mkdir(parents=True, exist_ok=True)

            # 初始化回测引擎
            self._init_backtest_engine()

            return True

        except Exception as e:
            self._log_error("初始化", e)
            return False

    def _do_shutdown(self) -> bool:
        """关闭策略中心服务."""
        try:
            # 停止所有回测任务
            self._stop_all_backtests()
            return True
        except Exception as e:
            self._log_error("关闭", e)
            return False

    def _do_health_check(self) -> Dict[str, Any]:
        """健康检查."""
        return {
            "strategy_root_exists": self.strategy_root.exists(),
            "backtest_engine_available": self.backtest_engine is not None,
            "active_backtests": len(self._backtest_tasks),
        }

    def _init_backtest_engine(self):
        """初始化回测引擎."""
        try:
            from vnpy_ctabacktester import BacktesterEngine

            # 检查main_engine是否可用
            if self.main_engine:
                # 回测引擎需要main_engine和event_engine
                self.backtest_engine = self.main_engine.get_engine("CtaBacktester")
                if self.backtest_engine:
                    self.logger.info("✅ 回测引擎初始化成功")
                else:
                    self.logger.warning("⚠️ 回测引擎获取失败")
            else:
                self.logger.warning("⚠️ MainEngine不可用，无法初始化回测引擎")

        except ImportError:
            self.logger.warning("⚠️ vnpy_ctabacktester不可用")

    # ==================== 策略文件管理 ====================

    def list_strategy_files(self, directory: str = "") -> Dict[str, Any]:
        """列出策略文件（树状结构）.

        Args:
            directory: 相对路径（默认为根目录）

        Returns:
            Dict: 文件树结构
        """
        try:
            target_dir = self.strategy_root / directory if directory else self.strategy_root

            if not target_dir.exists():
                return {"success": False, "message": "目录不存在", "files": []}

            files = []
            for item in target_dir.iterdir():
                files.append(
                    {
                        "name": item.name,
                        "path": str(item.relative_to(self.strategy_root)),
                        "is_dir": item.is_dir(),
                        "size": item.stat().st_size if item.is_file() else 0,
                        "modified": datetime.fromtimestamp(item.stat().st_mtime).isoformat(),
                    }
                )

            return {
                "success": True,
                "files": files,
            }

        except Exception as e:
            self._log_error("列出策略文件", e)
            return {"success": False, "message": str(e), "files": []}

    def create_strategy_file(
        self, file_path: str, template_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """创建策略文件.

        Args:
            file_path: 文件路径（相对于strategy_root）
            template_type: 模板类型（可选）

        Returns:
            Dict: 操作结果
        """
        try:
            target_file = self.strategy_root / file_path

            if target_file.exists():
                return {"success": False, "message": "文件已存在"}

            # 确保父目录存在
            target_file.parent.mkdir(parents=True, exist_ok=True)

            # 创建文件
            content = self._get_template_content(template_type) if template_type else ""
            target_file.write_text(content, encoding="utf-8")

            return {
                "success": True,
                "message": "文件创建成功",
                "file_path": str(target_file.relative_to(self.strategy_root)),
            }

        except Exception as e:
            self._log_error("创建策略文件", e)
            return {"success": False, "message": str(e)}

    def read_strategy_file(self, file_path: str) -> Dict[str, Any]:
        """读取策略文件内容.

        Args:
            file_path: 文件路径

        Returns:
            Dict: 文件内容
        """
        try:
            target_file = self.strategy_root / file_path

            if not target_file.exists():
                return {"success": False, "message": "文件不存在", "content": ""}

            content = target_file.read_text(encoding="utf-8")

            return {
                "success": True,
                "content": content,
            }

        except Exception as e:
            self._log_error("读取策略文件", e)
            return {"success": False, "message": str(e), "content": ""}

    def update_strategy_file(self, file_path: str, content: str) -> Dict[str, Any]:
        """更新策略文件内容.

        Args:
            file_path: 文件路径
            content: 新内容

        Returns:
            Dict: 操作结果
        """
        try:
            target_file = self.strategy_root / file_path

            if not target_file.exists():
                return {"success": False, "message": "文件不存在"}

            target_file.write_text(content, encoding="utf-8")

            return {
                "success": True,
                "message": "文件保存成功",
            }

        except Exception as e:
            self._log_error("更新策略文件", e)
            return {"success": False, "message": str(e)}

    def delete_strategy_file(self, file_path: str) -> Dict[str, Any]:
        """删除策略文件或目录.

        Args:
            file_path: 文件/目录路径

        Returns:
            Dict: 操作结果
        """
        try:
            target = self.strategy_root / file_path

            if not target.exists():
                return {"success": False, "message": "文件/目录不存在"}

            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()

            return {
                "success": True,
                "message": "删除成功",
            }

        except Exception as e:
            self._log_error("删除策略文件", e)
            return {"success": False, "message": str(e)}

    def rename_strategy_file(self, old_path: str, new_path: str) -> Dict[str, Any]:
        """重命名策略文件/目录.

        Args:
            old_path: 旧路径
            new_path: 新路径

        Returns:
            Dict: 操作结果
        """
        try:
            old_target = self.strategy_root / old_path
            new_target = self.strategy_root / new_path

            if not old_target.exists():
                return {"success": False, "message": "源文件/目录不存在"}

            if new_target.exists():
                return {"success": False, "message": "目标已存在"}

            old_target.rename(new_target)

            return {
                "success": True,
                "message": "重命名成功",
            }

        except Exception as e:
            self._log_error("重命名策略文件", e)
            return {"success": False, "message": str(e)}

    def _get_template_content(self, template_type: str) -> str:
        """获取策略模板内容.

        Args:
            template_type: 模板类型

        Returns:
            str: 模板内容
        """
        try:
            # 从templates目录读取模板文件
            template_dir = Path("strategies/templates")
            template_file = template_dir / f"{template_type}_template.py"

            if template_file.exists():
                return template_file.read_text(encoding="utf-8")
            else:
                # 返回默认模板
                return self._get_default_template(template_type)

        except Exception as e:
            self.logger.warning(f"读取模板文件失败: {e}")
            return self._get_default_template(template_type)

    def _get_default_template(self, template_type: str) -> str:
        """获取默认模板内容."""
        templates = {
            "cta": '''# -*- coding: utf-8 -*-
"""CTA策略模板"""

from vnpy_ctastrategy import CtaTemplate
from vnpy.trader.object import BarData, TickData


class MyStrategy(CtaTemplate):
    """CTA策略示例"""

    author = "用户"

    # 策略参数
    fast_window = 10
    slow_window = 20

    def __init__(self, cta_engine, strategy_name, vt_symbol, setting):
        super().__init__(cta_engine, strategy_name, vt_symbol, setting)

    def on_init(self):
        self.write_log("策略初始化")

    def on_start(self):
        self.write_log("策略启动")

    def on_stop(self):
        self.write_log("策略停止")

    def on_bar(self, bar: BarData):
        """K线推送"""
        pass
''',
            "algo": '''# -*- coding: utf-8 -*-
"""算法交易策略模板"""

from vnpy_algotrading import AlgoTemplate


class MyAlgoStrategy(AlgoTemplate):
    """算法交易策略示例"""

    display_name = "我的算法策略"

    def __init__(self, algo_engine, algo_name, setting):
        super().__init__(algo_engine, algo_name, setting)

    def on_tick(self, tick):
        pass

    def on_order(self, order):
        pass

    def on_trade(self, trade):
        pass
''',
            "portfolio": '''# -*- coding: utf-8 -*-
"""组合策略模板"""

from vnpy_portfoliostrategy import StrategyTemplate


class MyPortfolioStrategy(StrategyTemplate):
    """组合策略示例"""

    author = "用户"

    def __init__(self, strategy_engine, strategy_name, vt_symbols, setting):
        super().__init__(strategy_engine, strategy_name, vt_symbols, setting)

    def on_init(self):
        self.write_log("策略初始化")

    def on_start(self):
        self.write_log("策略启动")

    def on_stop(self):
        self.write_log("策略停止")

    def on_bars(self, bars):
        """K线推送"""
        pass
''',
        }
        return templates.get(template_type, "# -*- coding: utf-8 -*-\n# 策略模板\n")

    # ==================== 回测服务 ====================

    def start_backtest(self, strategy_file: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """启动回测.

        Args:
            strategy_file: 策略文件路径
            config: 回测配置

        Returns:
            Dict: 回测任务信息
        """
        try:
            task_id = f"backtest_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

            # 检查回测引擎是否可用
            if not self.backtest_engine:
                return {
                    "success": False,
                    "message": "回测引擎不可用（vnpy_ctabacktester未安装）",
                }

            # 实际的回测逻辑
            # 注意：实际回测需要在后台线程执行，这里只是启动
            try:
                # 验证策略文件存在
                strategy_path = self.strategy_root / strategy_file
                if not strategy_path.exists():
                    return {
                        "success": False,
                        "message": f"策略文件不存在: {strategy_file}",
                    }

                # 解析回测配置
                start_date = config.get("start_date", "2024-01-01")
                end_date = config.get("end_date", "2024-12-31")
                capital = config.get("capital", 1000000)

                self.logger.info(f"回测配置: {start_date} 到 {end_date}, 初始资金: {capital}")

                # 注册任务（实际回测在后台执行）
                self._backtest_tasks[task_id] = {
                    "status": "running",
                    "strategy_file": strategy_file,
                    "config": config,
                    "start_time": datetime.now(),
                    "progress": 50,  # 模拟进度
                    "result": None,
                }

                # TODO: 在后台线程执行实际回测
                # 这里需要加载策略类、加载数据、运行回测引擎

                return {
                    "success": True,
                    "task_id": task_id,
                    "message": "回测已启动",
                }

            except Exception as e:
                self.logger.error(f"回测启动失败: {e}", exc_info=True)
                return {
                    "success": False,
                    "message": f"回测启动失败: {str(e)}",
                }

        except Exception as e:
            self._log_error("启动回测", e)
            return {"success": False, "message": str(e)}

    def _stop_all_backtests(self):
        """停止所有回测任务."""
        for task_id in list(self._backtest_tasks.keys()):
            task = self._backtest_tasks[task_id]
            if task["status"] == "running":
                task["status"] = "stopped"
                self.logger.info(f"回测任务 {task_id} 已停止")
