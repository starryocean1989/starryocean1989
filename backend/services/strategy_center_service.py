# -*- coding: utf-8 -*-
"""
策略中心服务.

提供策略开发和回测环境，包括：
- 策略文件管理（文件系统操作、策略分类）
- 代码编写支持（验证、AI助手集成、模板管理）
- 回测服务（配置管理、回测执行、结果处理）
"""

import ast
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime

from backend.services.base_and_utils import BaseService
from backend.core.backtest_renderers import BacktestRendererFactory


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
            # 检查main_engine是否可用
            if self.main_engine:
                # 回测引擎需要main_engine和event_engine
                self.backtest_engine = self.main_engine.get_engine("CtaBacktester")
                if self.backtest_engine:
                    self.logger.info("✅ 回测引擎初始化成功")
                else:
                    # 回测引擎是可选功能，降低日志级别
                    self.logger.debug("⚠️ 回测引擎获取失败")
            else:
                # 回测引擎是可选功能，降低日志级别
                self.logger.debug("⚠️ MainEngine不可用，无法初始化回测引擎")

        except ImportError:
            # 回测引擎是可选功能，降低日志级别
            self.logger.debug("⚠️ vnpy_ctabacktester不可用")

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

    # ==================== 策略列表API（供交易网关等模块使用） ====================

    def get_available_strategies(
        self,
        strategy_folder: Optional[str] = None,
        engine_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """获取可用的策略列表（解析后的结构化信息）.

        供交易网关等模块调用，返回可部署的策略类信息。

        Args:
            strategy_folder: 策略文件夹（可选，相对于strategy_root）
            engine_type: 策略引擎类型过滤（可选：ctastrategy/portfoliostrategy/spreadtrading等）

        Returns:
            Dict: {
                "success": bool,
                "strategies": [
                    {
                        "class_name": str,      # 策略类名
                        "file_path": str,       # 文件相对路径
                        "file_name": str,       # 文件名
                        "folder": str,          # 所属文件夹
                        "engine_type": str,     # 策略引擎类型
                        "template": str,        # 继承的模板类
                        "display_name": str,    # 显示名称
                        "author": str,          # 作者（如果定义）
                        "description": str      # 描述（从docstring提取）
                    }
                ],
                "folders": [str],  # 可用的文件夹列表
                "message": str
            }
        """
        try:
            self._log_operation("获取可用策略列表", folder=strategy_folder, engine=engine_type)

            # 确定扫描目录
            if strategy_folder:
                scan_dir = self.strategy_root / strategy_folder
                if not scan_dir.exists():
                    return {
                        "success": False,
                        "message": f"策略文件夹不存在: {strategy_folder}",
                        "strategies": [],
                        "folders": [],
                    }
            else:
                scan_dir = self.strategy_root

            # 扫描策略文件
            strategies = []
            folders_set = set()

            # 递归扫描所有.py文件
            for file_path in scan_dir.rglob("*.py"):
                # 跳过__init__文件和私有文件
                if file_path.name.startswith("__"):
                    continue

                # 解析策略文件
                strategy_info = self._parse_strategy_file(file_path)

                if strategy_info:
                    # 如果指定了engine_type，过滤
                    if engine_type and strategy_info["engine_type"] != engine_type:
                        continue

                    strategies.append(strategy_info)

                    # 记录文件夹
                    folder_name = strategy_info["folder"]
                    if folder_name:
                        folders_set.add(folder_name)

            # 排序
            strategies.sort(key=lambda s: (s["folder"], s["file_name"]))
            folders = sorted(list(folders_set))

            self.logger.info(f"扫描到 {len(strategies)} 个策略（{len(folders)} 个文件夹）")

            return {
                "success": True,
                "strategies": strategies,
                "folders": folders,
                "message": f"成功获取 {len(strategies)} 个策略",
            }

        except Exception as e:
            self._log_error("获取可用策略列表", e)
            return {
                "success": False,
                "strategies": [],
                "folders": [],
                "message": f"获取失败: {str(e)}",
            }

    def identify_strategy_type(self, file_path: str) -> Optional[str]:
        """识别策略文件的引擎类型（供交易网关调用）.

        Args:
            file_path: 策略文件路径（相对于strategy_root）

        Returns:
            str: 策略引擎类型（如"ctastrategy"），如果无法识别则返回None
        """
        try:
            target_file = self.strategy_root / file_path

            if not target_file.exists() or not target_file.is_file():
                return None

            # 解析策略文件
            strategy_info = self._parse_strategy_file(target_file)

            if strategy_info:
                return strategy_info.get("engine_type")

            return None

        except Exception as e:
            self._log_error("识别策略类型", e)
            return None

    def load_strategy_module_info(self, file_path: str) -> Optional[Dict[str, Any]]:
        """加载策略模块信息（供交易网关调用）.

        Args:
            file_path: 策略文件路径（相对于strategy_root）

        Returns:
            Dict: 策略模块信息，包含：
                - class_name: 策略类名
                - engine_type: 策略引擎类型
                - template: 模板名称
                - params: 策略参数
                - file_path: 文件相对路径
                - abs_file_path: 完整文件路径
                - module_name: Python模块名（用于导入）
        """
        try:
            target_file = self.strategy_root / file_path

            if not target_file.exists() or not target_file.is_file():
                self.logger.error(f"策略文件不存在: {file_path}")
                return None

            # 解析策略文件获取信息
            strategy_info = self._parse_strategy_file(target_file)

            if not strategy_info:
                self.logger.error(f"无法解析策略文件: {file_path}")
                return None

            # 构建模块导入路径
            # 例如: strategies/user_strategies/cta_strategies/my_strategy.py
            # 转换为: strategies.user_strategies.cta_strategies.my_strategy
            relative_path = target_file.relative_to(Path.cwd())
            module_parts = list(relative_path.parts[:-1]) + [relative_path.stem]
            module_name = ".".join(module_parts)

            return {
                "class_name": strategy_info["class_name"],
                "engine_type": strategy_info["engine_type"],
                "template": strategy_info["template"],
                "params": strategy_info.get("params", {}),
                "file_path": strategy_info["file_path"],  # 相对路径
                "abs_file_path": str(target_file),  # 绝对路径
                "module_name": module_name,
                "author": strategy_info.get("author", "未知"),
                "description": strategy_info.get("description", ""),
            }

        except Exception as e:
            self._log_error("加载策略模块信息", e)
            return None

    def _parse_strategy_file(self, file_path: Path) -> Optional[Dict[str, Any]]:
        """解析策略文件，提取策略类信息.

        Args:
            file_path: 策略文件路径

        Returns:
            Dict: 策略信息，如果解析失败或无有效策略类则返回None
        """
        try:
            # 读取文件内容
            content = file_path.read_text(encoding="utf-8")

            # 解析AST
            tree = ast.parse(content)

            # 查找策略类定义
            for node in ast.walk(tree):
                if not isinstance(node, ast.ClassDef):
                    continue

                # 检查是否继承自策略模板
                base_names = []
                for base in node.bases:
                    if isinstance(base, ast.Name):
                        base_names.append(base.id)
                    elif isinstance(base, ast.Attribute):
                        base_names.append(base.attr)

                # 识别策略引擎类型
                engine_type, template = self._identify_strategy_type_from_bases(base_names)

                if not engine_type:
                    continue  # 不是策略类

                # 提取策略参数
                params = self._extract_strategy_params(node)

                # 提取作者和描述
                author = self._extract_class_attribute(node, "author") or "未知"
                description = ast.get_docstring(node) or ""

                # 计算相对路径和文件夹
                relative_path = file_path.relative_to(self.strategy_root)
                folder_parts = relative_path.parts[:-1]
                folder = folder_parts[0] if folder_parts else "根目录"

                return {
                    "class_name": node.name,
                    "file_path": str(relative_path).replace("\\", "/"),
                    "file_name": file_path.name,
                    "folder": folder,
                    "engine_type": engine_type,
                    "template": template,
                    "display_name": f"{node.name} ({file_path.name})",
                    "author": author,
                    "description": description.split("\n")[0] if description else "",  # 只取第一行
                    "params": params,
                }

            return None  # 没有找到策略类

        except SyntaxError as e:
            self.logger.warning(f"策略文件语法错误 {file_path.name}: {e}")
            return None
        except Exception as e:
            self.logger.warning(f"解析策略文件失败 {file_path.name}: {e}")
            return None

    def _identify_strategy_type_from_bases(self, base_names: List[str]) -> tuple:
        """根据基类名识别策略引擎类型.

        Args:
            base_names: 基类名称列表

        Returns:
            tuple: (engine_type, template_name) 或 (None, None)
        """
        # 策略模板映射
        template_mapping = {
            "CtaTemplate": ("ctastrategy", "CtaTemplate"),
            "AlgoTemplate": ("algotrading", "AlgoTemplate"),
            "StrategyTemplate": ("portfoliostrategy", "StrategyTemplate"),  # PortfolioStrategy
            "SpreadStrategyTemplate": ("spreadtrading", "SpreadStrategyTemplate"),
            "OptionTemplate": ("optionmaster", "OptionTemplate"),
            # scripttrader没有固定模板，通常继承object或自定义基类
        }

        for base in base_names:
            if base in template_mapping:
                return template_mapping[base]

        # 检查是否包含特定关键词（用于识别scripttrader等）
        for base in base_names:
            base_lower = base.lower()
            if "script" in base_lower:
                return ("scripttrader", base)

        return (None, None)

    def _extract_strategy_params(self, class_node: ast.ClassDef) -> Dict[str, Any]:
        """提取策略参数定义.

        Args:
            class_node: 策略类的AST节点

        Returns:
            Dict: 参数名 -> 默认值
        """
        params = {}

        for node in class_node.body:
            # 查找类变量定义（策略参数）
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        param_name = target.id

                        # 跳过私有变量和特殊变量
                        if param_name.startswith("_") or param_name in [
                            "author",
                            "display_name",
                            "class_name",
                        ]:
                            continue

                        # 提取默认值
                        try:
                            param_value = ast.literal_eval(node.value)
                            params[param_name] = param_value
                        except (ValueError, SyntaxError):
                            # 无法直接求值的表达式，记录为字符串
                            params[param_name] = ast.unparse(node.value)

        return params

    def _extract_class_attribute(self, class_node: ast.ClassDef, attr_name: str) -> Optional[str]:
        """提取类属性值.

        Args:
            class_node: 类AST节点
            attr_name: 属性名

        Returns:
            str: 属性值，如果不存在返回None
        """
        for node in class_node.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == attr_name:
                        try:
                            return ast.literal_eval(node.value)
                        except (ValueError, SyntaxError):
                            return ast.unparse(node.value)
        return None

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
                    "progress": 0,  # 真实进度，从0开始
                    "result": None,
                }

                # 在后台线程执行实际回测
                import threading

                def run_backtest():
                    """后台线程执行回测."""
                    try:
                        task = self._backtest_tasks[task_id]

                        # 更新进度：准备阶段
                        task["progress"] = 10
                        self.logger.info(f"回测任务 {task_id}: 准备阶段...")

                        # 尝试导入回测引擎
                        try:
                            from vnpy_ctabacktester import BacktesterEngine
                            from vnpy.trader.engine import MainEngine, EventEngine

                            # 更新进度：加载数据
                            task["progress"] = 20
                            self.logger.info(f"回测任务 {task_id}: 加载数据...")

                            # 创建回测引擎
                            event_engine = EventEngine()
                            main_engine = MainEngine(event_engine)
                            backtest_engine = BacktesterEngine(main_engine, event_engine)

                            # 更新进度：配置参数
                            task["progress"] = 30
                            self.logger.info(f"回测任务 {task_id}: 配置参数...")

                            # 实现真实的策略加载和回测执行
                            import importlib.util
                            import sys
                            from datetime import datetime as dt

                            # 1. 动态加载策略类
                            strategy_module_name = f"strategy_{task_id}"
                            spec = importlib.util.spec_from_file_location(
                                strategy_module_name, strategy_path
                            )

                            if spec is None or spec.loader is None:
                                raise ValueError(f"无法加载策略文件: {strategy_path}")

                            strategy_module = importlib.util.module_from_spec(spec)
                            sys.modules[strategy_module_name] = strategy_module
                            spec.loader.exec_module(strategy_module)

                            # 查找策略类（继承自CtaTemplate的类）
                            from vnpy_ctastrategy import CtaTemplate

                            strategy_class = None
                            for name in dir(strategy_module):
                                obj = getattr(strategy_module, name)
                                if (
                                    isinstance(obj, type)
                                    and issubclass(obj, CtaTemplate)
                                    and obj is not CtaTemplate
                                ):
                                    strategy_class = obj
                                    break

                            if strategy_class is None:
                                raise ValueError("策略文件中未找到有效的策略类")

                            self.logger.info(f"成功加载策略类: {strategy_class.__name__}")

                            # 更新进度：加载历史数据
                            task["progress"] = 40
                            self.logger.info(f"回测任务 {task_id}: 加载历史数据...")

                            # 2. 获取历史数据（通过data_center_service）
                            symbol = config.get("symbol", "000001")
                            exchange = config.get("exchange", "SZSE")
                            interval_str = config.get("interval", "1d")

                            # 注：vnpy的run_backtesting方法需要interval作为字符串，直接使用interval_str

                            # 从data_center_service获取历史数据
                            from backend.core.base import get_service_manager

                            service_manager = get_service_manager()
                            data_service = service_manager.get_service("data_center_service")

                            if data_service:
                                # 调用data_center_service的查询方法
                                data_result = data_service.query_local_data(
                                    symbol=symbol,
                                    start_date=start_date,
                                    end_date=end_date,
                                    interval=interval_str,  # 统一使用interval参数名
                                )

                                if data_result.get("success") and data_result.get("data"):
                                    self.logger.info(
                                        "✅ 从数据中心加载 %d 条历史数据", len(data_result["data"])
                                    )

                                    # 检查数据质量
                                    if hasattr(data_service, "check_data_quality"):
                                        quality_result = data_service.check_data_quality(
                                            symbol, start_date, end_date, interval_str
                                        )
                                        if quality_result.get("success"):
                                            quality_score = quality_result.get("quality_score", 1.0)
                                            if quality_score < 0.8:
                                                self.logger.warning(
                                                    "⚠️ 回测数据质量较低 (%.2f)，可能影响回测结果准确性",
                                                    quality_score,
                                                )
                                else:
                                    self.logger.warning(
                                        "未能从数据中心获取历史数据，回测将使用vnpy内置数据源"
                                    )
                            else:
                                self.logger.warning("数据中心服务不可用，回测将使用vnpy内置数据源")

                            # 更新进度：执行回测
                            task["progress"] = 50
                            self.logger.info(f"回测任务 {task_id}: 执行回测...")

                            # 3. 配置并执行回测
                            # 运行回测（直接调用run_backtesting方法）
                            self.logger.info("开始执行回测...")
                            backtest_engine.run_backtesting(  # type: ignore
                                class_name=strategy_class.__name__,
                                vt_symbol=f"{symbol}.{exchange}",
                                interval=interval_str,  # 使用字符串而不是枚举
                                start=dt.strptime(start_date, "%Y-%m-%d"),
                                end=dt.strptime(end_date, "%Y-%m-%d"),
                                rate=config.get("commission_rate", 0.0003),
                                slippage=config.get("slippage", 0.0),
                                size=config.get("size", 1),
                                pricetick=config.get("pricetick", 0.01),
                                capital=int(capital),
                                setting=config.get("strategy_setting", {}),
                            )

                            # 更新进度：计算结果
                            task["progress"] = 80
                            self.logger.info(f"回测任务 {task_id}: 计算统计指标...")

                            # 4. 计算统计结果
                            statistics = backtest_engine.result_statistics

                            # 更新进度：生成报告
                            task["progress"] = 90
                            self.logger.info(f"回测任务 {task_id}: 生成报告...")

                            # 提取关键指标
                            total_return = statistics.get("total_return", 0.0)
                            sharpe_ratio = statistics.get("sharpe_ratio", 0.0)
                            max_drawdown = statistics.get("max_drawdown", 0.0)
                            total_trades = statistics.get("total_trades", 0)
                            winning_rate = statistics.get("winning_rate", 0.0)

                            # 尝试生成图表数据（使用vnpy_chartwizard）
                            chart_data = None
                            try:
                                # 获取回测结果数据
                                daily_results = backtest_engine.get_all_daily_results()
                                if daily_results:
                                    # 准备图表数据（简化版，供UI绘制）
                                    chart_data = {
                                        "dates": [str(r.date) for r in daily_results],
                                        "balance": [r.balance for r in daily_results],
                                        "drawdown": [r.max_drawdown for r in daily_results],
                                    }
                                    self.logger.info("成功生成回测图表数据")
                            except Exception as chart_error:
                                self.logger.warning(f"生成图表数据失败: {chart_error}")

                            # 回测完成
                            task["progress"] = 100
                            task["status"] = "completed"
                            task["result"] = {
                                "total_return": float(total_return),
                                "sharpe_ratio": float(sharpe_ratio),
                                "max_drawdown": float(max_drawdown),
                                "total_trades": int(total_trades),
                                "winning_rate": float(winning_rate),
                                "all_statistics": statistics,
                                "chart_data": chart_data,  # 图表数据
                                "message": "回测执行成功",
                            }
                            self.logger.info(
                                f"回测任务 {task_id} 完成 - "
                                f"总收益: {total_return:.2%}, "
                                f"夏普比率: {sharpe_ratio:.2f}, "
                                f"最大回撤: {max_drawdown:.2%}"
                            )

                            # 清理策略模块
                            if strategy_module_name in sys.modules:
                                del sys.modules[strategy_module_name]

                        except ImportError as e:
                            self.logger.warning(f"vnpy_ctabacktester未安装: {e}")
                            task["status"] = "failed"
                            task["progress"] = 0
                            task["result"] = {
                                "error": "vnpy_ctabacktester包未安装",
                            }

                    except Exception as e:
                        self.logger.error(f"回测任务 {task_id} 失败: {e}", exc_info=True)
                        task["status"] = "failed"
                        task["progress"] = 0
                        task["result"] = {
                            "error": str(e),
                        }

                # 启动后台线程
                backtest_thread = threading.Thread(target=run_backtest, daemon=True)
                backtest_thread.start()
                self.logger.info(f"回测任务 {task_id} 已在后台线程启动")

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

    def render_backtest_result(
        self, task_id: str, strategy_type: str = "ctastrategy"
    ) -> Dict[str, Any]:
        """渲染回测结果（使用策略类型专用模板）.

        对应需求文档链条4.2.2：不同策略类型的自定义展示

        Args:
            task_id: 回测任务ID
            strategy_type: 策略类型

        Returns:
            Dict: 渲染后的结果
        """
        try:
            task = self._backtest_tasks.get(task_id)
            if not task:
                return {
                    "success": False,
                    "message": "回测任务不存在",
                }

            if task["status"] != "completed":
                return {
                    "success": False,
                    "message": f"回测任务未完成，当前状态: {task['status']}",
                }

            # 获取原始回测结果
            raw_result = task.get("result", {})

            # 使用渲染器工厂渲染结果
            rendered_result = BacktestRendererFactory.render_backtest_result(
                strategy_type, raw_result
            )

            return {
                "success": True,
                "task_id": task_id,
                "strategy_type": strategy_type,
                "rendered_result": rendered_result,
            }

        except Exception as e:
            self._log_error("渲染回测结果", e)
            return {"success": False, "message": str(e)}

    def _stop_all_backtests(self):
        """停止所有回测任务."""
        for task_id in list(self._backtest_tasks.keys()):
            task = self._backtest_tasks[task_id]
            if task["status"] == "running":
                task["status"] = "stopped"
                self.logger.info("回测任务 %s 已停止", task_id)
