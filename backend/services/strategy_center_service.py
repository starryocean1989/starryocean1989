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
from enum import Enum
import logging

from backend.core.service_base import BaseService, LoggerMixin
from backend.services.database_adapter import get_db_manager

# 专用logger - 日志埋点v4.0
logger_backtest = logging.getLogger("backend.strategy.backtest")
logger_alert = logging.getLogger("backend.strategy.alert")


# =============================================================================
# 回测结果渲染器（从backtest_renderers.py合并）
# =============================================================================


class StrategyType(Enum):
    """策略类型枚举."""

    CTA = "ctastrategy"
    ALGO = "algotrading"
    OPTION = "optionmaster"
    PORTFOLIO = "portfoliostrategy"
    SPREAD = "spreadtrading"
    SCRIPT = "scripttrader"


class BacktestRenderer:
    """回测结果渲染器基类."""

    def render(self, backtest_result: Dict[str, Any]) -> Dict[str, Any]:  # noqa: U100
        """渲染回测结果.

        Args:
            backtest_result: 回测结果数据

        Returns:
            Dict: 渲染后的展示数据
        """
        raise NotImplementedError


class CTABacktestRenderer(BacktestRenderer):
    """CTA策略回测结果渲染器."""

    def render(self, backtest_result: Dict[str, Any]) -> Dict[str, Any]:
        """渲染CTA策略回测结果.

        重点：资金曲线、回撤曲线、交易统计

        Args:
            backtest_result: 回测结果

        Returns:
            Dict: 渲染数据
        """
        statistics = backtest_result.get("statistics", {})
        daily_results = backtest_result.get("daily_results", [])

        # 提取关键指标
        total_return = statistics.get("total_return", 0)
        sharpe_ratio = statistics.get("sharpe_ratio", 0)
        max_drawdown = statistics.get("max_drawdown", 0)
        win_rate = statistics.get("win_rate", 0)
        profit_loss_ratio = statistics.get("profit_loss_ratio", 0)
        total_trades = statistics.get("total_trades", 0)

        # 构建展示数据
        rendered = {
            "template_type": "cta",
            "title": "CTA策略回测结果",
            "summary": {
                "总收益率": f"{total_return:.2%}",
                "夏普比率": f"{sharpe_ratio:.2f}",
                "最大回撤": f"{max_drawdown:.2%}",
                "胜率": f"{win_rate:.2%}",
                "盈亏比": f"{profit_loss_ratio:.2f}",
                "总交易次数": total_trades,
            },
            "charts": [
                {
                    "type": "line",
                    "title": "资金曲线",
                    "data": self._extract_equity_curve(daily_results),
                },
                {
                    "type": "line",
                    "title": "回撤曲线",
                    "data": self._extract_drawdown_curve(daily_results),
                },
                {
                    "type": "bar",
                    "title": "月度收益分布",
                    "data": self._extract_monthly_returns(daily_results),
                },
            ],
            "raw_statistics": statistics,
        }

        return rendered

    def _extract_equity_curve(self, daily_results: List[Dict]) -> List[Dict]:
        """提取资金曲线数据."""
        return [{"date": day.get("date"), "value": day.get("balance", 0)} for day in daily_results]

    def _extract_drawdown_curve(self, daily_results: List[Dict]) -> List[Dict]:
        """提取回撤曲线数据."""
        return [{"date": day.get("date"), "value": day.get("drawdown", 0)} for day in daily_results]

    def _extract_monthly_returns(self, daily_results: List[Dict]) -> List[Dict]:  # noqa: U100
        """提取月度收益数据."""
        # 简化实现：返回空列表，实际需要按月聚合
        return []


class OptionBacktestRenderer(BacktestRenderer):
    """期权策略回测结果渲染器."""

    def render(self, backtest_result: Dict[str, Any]) -> Dict[str, Any]:
        """渲染期权策略回测结果.

        重点：Greeks曲线、期权组合盈亏、波动率敏感性

        Args:
            backtest_result: 回测结果

        Returns:
            Dict: 渲染数据
        """
        statistics = backtest_result.get("statistics", {})
        greeks_history = backtest_result.get("greeks_history", [])

        rendered = {
            "template_type": "option",
            "title": "期权策略回测结果",
            "summary": {
                "总收益率": f"{statistics.get('total_return', 0):.2%}",
                "最大Delta暴露": statistics.get("max_delta_exposure", 0),
                "平均Gamma": statistics.get("avg_gamma", 0),
                "Vega敏感度": statistics.get("vega_sensitivity", 0),
            },
            "charts": [
                {
                    "type": "multi_line",
                    "title": "Greeks曲线",
                    "series": [
                        {"name": "Delta", "data": self._extract_greek(greeks_history, "delta")},
                        {"name": "Gamma", "data": self._extract_greek(greeks_history, "gamma")},
                        {"name": "Vega", "data": self._extract_greek(greeks_history, "vega")},
                        {"name": "Theta", "data": self._extract_greek(greeks_history, "theta")},
                    ],
                },
                {
                    "type": "heatmap",
                    "title": "波动率敏感性矩阵",
                    "data": statistics.get("volatility_sensitivity_matrix", []),
                },
            ],
            "raw_statistics": statistics,
        }

        return rendered

    def _extract_greek(self, greeks_history: List[Dict], greek_name: str) -> List[Dict]:
        """提取指定Greek值历史."""
        return [
            {"date": item.get("date"), "value": item.get(greek_name, 0)} for item in greeks_history
        ]


class PortfolioBacktestRenderer(BacktestRenderer):
    """组合策略回测结果渲染器."""

    def render(self, backtest_result: Dict[str, Any]) -> Dict[str, Any]:
        """渲染组合策略回测结果.

        重点：各品种收益贡献、相关性矩阵、风险分散效果

        Args:
            backtest_result: 回测结果

        Returns:
            Dict: 渲染数据
        """
        statistics = backtest_result.get("statistics", {})
        symbol_performance = backtest_result.get("symbol_performance", {})

        rendered = {
            "template_type": "portfolio",
            "title": "组合策略回测结果",
            "summary": {
                "总收益率": f"{statistics.get('total_return', 0):.2%}",
                "组合波动率": f"{statistics.get('portfolio_volatility', 0):.2%}",
                "品种数量": len(symbol_performance),
                "分散度": f"{statistics.get('diversification_ratio', 0):.2f}",
            },
            "charts": [
                {
                    "type": "pie",
                    "title": "品种收益贡献度",
                    "data": self._extract_symbol_contribution(symbol_performance),
                },
                {
                    "type": "heatmap",
                    "title": "品种相关性矩阵",
                    "data": statistics.get("correlation_matrix", []),
                },
                {
                    "type": "bar",
                    "title": "各品种收益对比",
                    "data": self._extract_symbol_returns(symbol_performance),
                },
            ],
            "symbol_details": symbol_performance,
            "raw_statistics": statistics,
        }

        return rendered

    def _extract_symbol_contribution(self, symbol_performance: Dict) -> List[Dict]:
        """提取品种收益贡献度."""
        return [
            {"name": symbol, "value": perf.get("contribution", 0)}
            for symbol, perf in symbol_performance.items()
        ]

    def _extract_symbol_returns(self, symbol_performance: Dict) -> List[Dict]:
        """提取各品种收益."""
        return [
            {"name": symbol, "value": perf.get("return", 0)}
            for symbol, perf in symbol_performance.items()
        ]


class AlgoBacktestRenderer(BacktestRenderer):
    """算法交易策略回测结果渲染器."""

    def render(self, backtest_result: Dict[str, Any]) -> Dict[str, Any]:
        """渲染算法交易策略回测结果.

        重点：成交价格分布、滑点分析、VWAP/TWAP偏差

        Args:
            backtest_result: 回测结果

        Returns:
            Dict: 渲染数据
        """
        statistics = backtest_result.get("statistics", {})
        execution_details = backtest_result.get("execution_details", [])

        rendered = {
            "template_type": "algo",
            "title": "算法交易策略回测结果",
            "summary": {
                "总收益率": f"{statistics.get('total_return', 0):.2%}",
                "平均滑点": f"{statistics.get('avg_slippage', 0):.4f}",
                "VWAP偏差": f"{statistics.get('vwap_deviation', 0):.4f}",
                "执行成功率": f"{statistics.get('execution_success_rate', 0):.2%}",
            },
            "charts": [
                {
                    "type": "histogram",
                    "title": "成交价格分布",
                    "data": self._extract_price_distribution(execution_details),
                },
                {
                    "type": "scatter",
                    "title": "滑点分布",
                    "data": self._extract_slippage_data(execution_details),
                },
                {
                    "type": "line",
                    "title": "VWAP对比",
                    "data": self._extract_vwap_comparison(execution_details),
                },
            ],
            "raw_statistics": statistics,
        }

        return rendered

    def _extract_price_distribution(self, execution_details: List[Dict]) -> List[Dict]:
        """提取价格分布数据."""
        return [
            {"price": trade.get("price", 0), "volume": trade.get("volume", 0)}
            for trade in execution_details
        ]

    def _extract_slippage_data(self, execution_details: List[Dict]) -> List[Dict]:
        """提取滑点数据."""
        return [
            {"x": i, "y": trade.get("slippage", 0)} for i, trade in enumerate(execution_details)
        ]

    def _extract_vwap_comparison(self, execution_details: List[Dict]) -> List[Dict]:
        """提取VWAP对比数据."""
        return [
            {
                "time": trade.get("time"),
                "actual": trade.get("price", 0),
                "vwap": trade.get("vwap", 0),
            }
            for trade in execution_details
        ]


class SpreadBacktestRenderer(BacktestRenderer):
    """价差交易策略回测结果渲染器."""

    def render(self, backtest_result: Dict[str, Any]) -> Dict[str, Any]:
        """渲染价差交易策略回测结果.

        重点：价差序列、价差分布、套利机会统计

        Args:
            backtest_result: 回测结果

        Returns:
            Dict: 渲染数据
        """
        statistics = backtest_result.get("statistics", {})
        spread_history = backtest_result.get("spread_history", [])

        rendered = {
            "template_type": "spread",
            "title": "价差交易策略回测结果",
            "summary": {
                "总收益率": f"{statistics.get('total_return', 0):.2%}",
                "平均价差": f"{statistics.get('avg_spread', 0):.4f}",
                "套利机会次数": statistics.get("arbitrage_opportunities", 0),
                "平均持仓时间": f"{statistics.get('avg_holding_period', 0):.1f}分钟",
            },
            "charts": [
                {
                    "type": "line",
                    "title": "价差序列",
                    "data": self._extract_spread_series(spread_history),
                },
                {
                    "type": "histogram",
                    "title": "价差分布",
                    "data": self._extract_spread_distribution(spread_history),
                },
                {
                    "type": "scatter",
                    "title": "套利机会识别",
                    "data": self._extract_arbitrage_points(spread_history),
                },
            ],
            "raw_statistics": statistics,
        }

        return rendered

    def _extract_spread_series(self, spread_history: List[Dict]) -> List[Dict]:
        """提取价差序列数据."""
        return [
            {"time": item.get("time"), "spread": item.get("spread", 0)} for item in spread_history
        ]

    def _extract_spread_distribution(self, spread_history: List[Dict]) -> List[Dict]:  # noqa: U100
        """提取价差分布数据."""
        # 简化实现
        return []

    def _extract_arbitrage_points(self, spread_history: List[Dict]) -> List[Dict]:
        """提取套利点数据."""
        return [
            {"x": i, "y": item.get("spread", 0)}
            for i, item in enumerate(spread_history)
            if item.get("is_arbitrage", False)
        ]


class DefaultBacktestRenderer(BacktestRenderer):
    """默认回测结果渲染器（用于脚本交易等通用情况）."""

    def render(self, backtest_result: Dict[str, Any]) -> Dict[str, Any]:
        """渲染默认回测结果.

        基础统计信息展示

        Args:
            backtest_result: 回测结果

        Returns:
            Dict: 渲染数据
        """
        statistics = backtest_result.get("statistics", {})

        rendered = {
            "template_type": "default",
            "title": "策略回测结果",
            "summary": {
                "总收益率": f"{statistics.get('total_return', 0):.2%}",
                "夏普比率": f"{statistics.get('sharpe_ratio', 0):.2f}",
                "最大回撤": f"{statistics.get('max_drawdown', 0):.2%}",
                "总交易次数": statistics.get("total_trades", 0),
            },
            "raw_statistics": statistics,
            "raw_data": backtest_result,
        }

        return rendered


class BacktestRendererFactory:
    """回测结果渲染器工厂."""

    _renderers = {
        StrategyType.CTA: CTABacktestRenderer(),
        StrategyType.ALGO: AlgoBacktestRenderer(),
        StrategyType.OPTION: OptionBacktestRenderer(),
        StrategyType.PORTFOLIO: PortfolioBacktestRenderer(),
        StrategyType.SPREAD: SpreadBacktestRenderer(),
        StrategyType.SCRIPT: DefaultBacktestRenderer(),
    }

    @classmethod
    def get_renderer(cls, strategy_type: str) -> BacktestRenderer:
        """获取渲染器.

        Args:
            strategy_type: 策略类型

        Returns:
            BacktestRenderer: 渲染器实例
        """
        try:
            strategy_enum = StrategyType(strategy_type)
            return cls._renderers.get(strategy_enum, DefaultBacktestRenderer())
        except ValueError:
            return DefaultBacktestRenderer()

    @classmethod
    def render_backtest_result(
        cls, strategy_type: str, backtest_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """渲染回测结果.

        Args:
            strategy_type: 策略类型
            backtest_result: 回测结果数据

        Returns:
            Dict: 渲染后的展示数据
        """
        renderer = cls.get_renderer(strategy_type)
        return renderer.render(backtest_result)


# =============================================================================
# 策略中心服务
# =============================================================================


class StrategyCenterService(BaseService, LoggerMixin):
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

        # 回测任务（内存缓存）
        self._backtest_tasks: Dict[str, Dict[str, Any]] = {}

        # 数据库管理器（使用统一database）
        self.db_manager = get_db_manager()

        # 业务指标埋点 - 策略中心服务 ✅
        # 已启用基础架构，可在业务方法中调用 self.metrics_collector.record_metric()
        from backend.infrastructure.system_vnpy import get_business_metrics_collector

        self.metrics_collector = get_business_metrics_collector()
        self.logger.info("业务指标采集器已启用（策略中心服务）")

        # 支持的指标类型：
        # - backtest_execution_time_sec: 回测执行时间
        # - strategy_signal_latency_ms: 策略信号延迟
        # - kline_calculation_time_ms: K线计算时间
        # - strategy_error_rate: 策略错误率
        # - backtest_throughput: 回测吞吐量（条/秒）
        #
        # 使用示例（在回测方法中）：
        # start_time = time.time()
        # backtest_result = run_backtest(strategy, data)
        # execution_time_sec = time.time() - start_time
        #
        # self.metrics_collector.record_metric('backtest_execution_time_sec', execution_time_sec,
        #                                      {'strategy': strategy_name, 'data_size': len(data)})
        #
        # throughput = len(data) / execution_time_sec if execution_time_sec > 0 else 0
        # self.metrics_collector.record_metric('backtest_throughput', throughput,
        #                                      {'strategy': strategy_name})
        #
        # TODO: 在以下方法中添加实际埋点:
        # - run_backtest(): 记录回测执行时间和吞吐量
        # - on_bar(): 记录K线计算时间（策略内部需要修改）

    def _do_initialize(self) -> bool:
        """初始化策略中心服务."""
        try:
            self.log_operation_start("策略中心服务初始化")

            # 确保策略目录存在
            self.strategy_root.mkdir(parents=True, exist_ok=True)
            self.logger.debug("策略目录已就绪：%s", self.strategy_root)

            # 初始化回测引擎
            self._init_backtest_engine()

            # 加载历史回测任务
            self._load_historical_backtests()

            self.log_operation_success("策略中心服务初始化")
            return True

        except Exception as e:
            self.log_operation_failure("策略中心服务初始化", e)
            self._log_error("初始化", e)
            return False

    def _do_shutdown(self) -> bool:
        """关闭策略中心服务."""
        try:
            self.log_operation_start("策略中心服务关闭")

            # 停止所有回测任务
            active_tasks = len(
                [t for t in self._backtest_tasks.values() if t.get("status") == "running"]
            )
            if active_tasks > 0:
                self.logger.info("停止 %d 个运行中的回测任务", active_tasks)
            self._stop_all_backtests()

            self.log_operation_success("策略中心服务关闭")
            return True
        except Exception as e:
            self.log_operation_failure("策略中心服务关闭", e)
            self._log_error("关闭", e)
            return False

    def _do_health_check(self) -> Dict[str, Any]:
        """健康检查."""
        return {
            "strategy_root_exists": self.strategy_root.exists(),
            "backtest_engine_available": self.backtest_engine is not None,
            "active_backtests": len(self._backtest_tasks),
        }

    def _load_historical_backtests(self):
        """从数据库加载历史回测任务（使用统一database）."""
        try:
            # 从database加载回测任务（最近30天）
            import json

            tasks = self.db_manager.execute_query(
                """
                SELECT id as task_id, strategy_id as strategy_file, parameters as config, status, progress, created_at
                FROM backtest_tasks
                WHERE created_at >= datetime('now', '-30 days')
                ORDER BY created_at DESC
                LIMIT 100
            """
            )

            loaded_count = 0
            for task_row in tasks:
                task_id = task_row.get("task_id")
                if not task_id:
                    continue

                # 解析config
                config_str = task_row.get("config", "{}")
                try:
                    config = json.loads(config_str) if isinstance(config_str, str) else config_str
                except Exception:
                    config = {}

                # 恢复任务到内存
                created_at = task_row.get("created_at")
                self._backtest_tasks[task_id] = {
                    "status": task_row.get("status", "unknown"),
                    "strategy_file": task_row.get("strategy_file"),
                    "config": config,
                    "start_time": (
                        datetime.fromisoformat(created_at)
                        if created_at and isinstance(created_at, str)
                        else datetime.now()
                    ),
                    "progress": task_row.get("progress", 0),
                    "result": None,  # result需要从backtest_results表加载
                }
                loaded_count += 1

            if loaded_count > 0:
                self.logger.info("从数据库加载了 %d 个历史回测任务", loaded_count)
            else:
                self.logger.info("没有历史回测任务")

        except Exception as e:
            self.logger.warning("加载历史回测任务失败：%s", e)

    def _init_backtest_engine(self):
        """初始化回测引擎."""
        try:
            self.logger.debug("初始化回测引擎...")

            # 检查main_engine是否可用
            if self.main_engine:
                # 回测引擎需要main_engine和event_engine
                self.backtest_engine = self.main_engine.get_engine("CtaBacktester")
                if self.backtest_engine:
                    self.logger.info("回测引擎初始化成功")
                else:
                    # 回测引擎是可选功能，降低日志级别
                    self.logger.debug("回测引擎获取失败")
            else:
                # 回测引擎是可选功能，降低日志级别
                self.logger.debug("MainEngine不可用，无法初始化回测引擎")

        except ImportError:
            # 回测引擎是可选功能，降低日志级别
            self.logger.debug("vnpy_ctabacktester不可用")

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
            self.logger.warning("读取模板文件失败：%s", e)
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

            self.logger.info("扫描到 %d 个策略（%d 个文件夹）", len(strategies), len(folders))

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
                self.logger.error("策略文件不存在：%s", file_path)
                return None

            # 解析策略文件获取信息
            strategy_info = self._parse_strategy_file(target_file)

            if not strategy_info:
                self.logger.error("无法解析策略文件：%s", file_path)
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
            self.logger.warning("策略文件语法错误 %s：%s", file_path.name, e)
            return None
        except Exception as e:
            self.logger.warning("解析策略文件失败 %s：%s", file_path.name, e)
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

            self.log_operation_start("启动回测任务", task_id=task_id, strategy=strategy_file)

            # 检查回测引擎是否可用
            if not self.backtest_engine:
                self.logger.error("回测引擎不可用（vnpy_ctabacktester未安装）")
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
                    self.logger.error("策略文件不存在：%s", strategy_file)
                    return {
                        "success": False,
                        "message": f"策略文件不存在: {strategy_file}",
                    }

                # 解析回测配置
                start_date = config.get("start_date", "2024-01-01")
                end_date = config.get("end_date", "2024-12-31")
                capital = config.get("capital", 1000000)
                symbol = config.get("symbol", "000001")

                self.logger.info(
                    "回测配置：%s %s~%s，初始资金：%s", symbol, start_date, end_date, capital
                )

                # 注册任务（实际回测在后台执行）
                task_data = {
                    "status": "running",
                    "strategy_file": strategy_file,
                    "config": config,
                    "start_time": datetime.now(),
                    "progress": 0,  # 真实进度，从0开始
                    "result": None,
                }
                self._backtest_tasks[task_id] = task_data

                # 保存到数据库（使用统一database）
                import json

                self.db_manager.execute_update(
                    """
                    INSERT INTO backtest_tasks
                    (task_id, strategy_file, config, status, progress, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        task_id,
                        strategy_file,
                        json.dumps(config, ensure_ascii=False),
                        "running",
                        0,
                        task_data["start_time"].isoformat(),
                        task_data["start_time"].isoformat(),
                    ),
                )

                self.logger.debug("回测任务已注册并保存到数据库：%s", task_id)

                # 在后台线程执行实际回测
                import threading

                def run_backtest():
                    """后台线程执行回测."""
                    import time

                    start_time = time.time()

                    # 切换到回测阶段 - 日志埋点v4.0
                    try:
                        from backend.infrastructure.system_vnpy.logging_context import (
                            get_logging_context,
                        )

                        ctx = get_logging_hub()
                        ctx.set_stage("backtest")
                        self.logger.info("📍 切换到回测阶段")
                    except ImportError:
                        ctx = None
                        self.logger.debug("logging_context模块不可用，跳过阶段切换")

                    try:
                        task = self._backtest_tasks[task_id]

                        # 使用场景上下文 - 日志埋点v4.0 (已移除scenario)
                        # 直接执行,不使用scenario上下文
                        scenario_ctx = None

                        # 更新进度：准备阶段
                        task["progress"] = 10
                        logger_backtest.info("[回测-%s] 准备阶段...", task_id)

                        # 尝试导入回测引擎
                        try:
                            from vnpy_ctabacktester import BacktesterEngine
                            from vnpy.trader.engine import MainEngine, EventEngine

                            # 更新进度：加载数据
                            task["progress"] = 20
                            self.logger.info("[回测-%s] 加载数据...", task_id)

                            # 创建回测引擎
                            event_engine = EventEngine()
                            main_engine = MainEngine(event_engine)
                            backtest_engine = BacktesterEngine(main_engine, event_engine)

                            # 更新进度：配置参数
                            task["progress"] = 30
                            self.logger.info("[回测-%s] 配置参数...", task_id)

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

                            self.logger.info(
                                "[回测-%s] 成功加载策略类：%s", task_id, strategy_class.__name__
                            )

                            # 更新进度：加载历史数据
                            task["progress"] = 40
                            self.logger.info("[回测-%s] 加载历史数据...", task_id)

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
                                    data_count = len(data_result["data"])
                                    self.logger.info(
                                        "[回测-%s] 从数据中心加载 %d 条历史数据",
                                        task_id,
                                        data_count,
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
                                                    "[回测-%s] 回测数据质量较低 (%.2f)，可能影响结果准确性",
                                                    task_id,
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
                            self.logger.info("[回测-%s] 执行回测...", task_id)

                            # 3. 配置并执行回测
                            # 运行回测（直接调用run_backtesting方法）
                            backtest_start = time.time()
                            self.logger.info("[回测-%s] 开始执行回测引擎...", task_id)
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

                            backtest_duration = (time.time() - backtest_start) * 1000
                            self.logger.info(
                                "[回测-%s] 回测执行完成，耗时：%.2fms", task_id, backtest_duration
                            )

                            # 更新进度：计算结果
                            task["progress"] = 80
                            self.logger.info("[回测-%s] 计算统计指标...", task_id)

                            # 4. 计算统计结果
                            statistics = backtest_engine.result_statistics

                            # 更新进度：生成报告
                            task["progress"] = 90
                            self.logger.info("[回测-%s] 生成报告...", task_id)

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
                                    self.logger.info("[回测-%s] 成功生成回测图表数据", task_id)
                            except Exception as chart_error:
                                self.logger.warning(
                                    "[回测-%s] 生成图表数据失败：%s", task_id, chart_error
                                )

                            # 回测完成
                            total_duration = (time.time() - start_time) * 1000
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

                            # 回测完成通知 - 日志埋点v4.0
                            self.logger.info(
                                "回测完成: 策略=%s, 收益率=%.2f%%, 夏普比率=%.2f, 最大回撤=%.2f%%, 总交易次数=%d",
                                strategy_file,
                                total_return * 100,
                                sharpe_ratio,
                                max_drawdown * 100,
                                total_trades,
                            )

                            # 更新数据库（使用统一database）
                            self.db_manager.execute_update(
                                """
                                UPDATE backtest_tasks
                                SET status = ?, progress = ?, updated_at = ?
                                WHERE task_id = ?
                            """,
                                ("completed", 100, datetime.now().isoformat(), task_id),
                            )

                            # 保存回测结果到database
                            import json

                            self.db_manager.execute_update(
                                """
                                INSERT INTO backtest_results
                                (task_id, total_return, sharpe_ratio, max_drawdown,
                                 total_trades, winning_rate, statistics, created_at)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                                (
                                    task_id,
                                    float(total_return),
                                    float(sharpe_ratio),
                                    float(max_drawdown),
                                    int(total_trades),
                                    float(winning_rate),
                                    json.dumps(statistics, ensure_ascii=False),
                                    datetime.now().isoformat(),
                                ),
                            )

                            # 记录性能日志和结果日志
                            self.log_performance(
                                "回测执行",
                                total_duration,
                                True,
                                {
                                    "task_id": task_id,
                                    "strategy": strategy_file,
                                    "total_trades": total_trades,
                                },
                            )

                            self.logger.info(
                                "[回测-%s] 完成 - "
                                f"总收益: {total_return:.2%}, "
                                f"夏普比率: {sharpe_ratio:.2f}, "
                                f"最大回撤: {max_drawdown:.2%}, "
                                f"交易次数: {total_trades}, "
                                f"胜率: {winning_rate:.2%}"
                            )

                            # 清理策略模块
                            if strategy_module_name in sys.modules:
                                del sys.modules[strategy_module_name]

                        except ImportError as e:
                            self.logger.warning(
                                "[回测-%s] vnpy_ctabacktester未安装：%s", task_id, e
                            )
                            task["status"] = "failed"
                            task["progress"] = 0
                            task["result"] = {
                                "error": "vnpy_ctabacktester包未安装",
                            }

                            # 更新数据库状态
                            self.db_manager.execute_update(
                                """
                                UPDATE backtest_tasks
                                SET status = ?, progress = ?, updated_at = ?
                                WHERE task_id = ?
                            """,
                                ("failed", 0, datetime.now().isoformat(), task_id),
                            )

                    except Exception as e:
                        total_duration = (time.time() - start_time) * 1000
                        self.log_performance(
                            "回测执行", total_duration, False, {"task_id": task_id, "error": str(e)}
                        )
                        logger_alert.error("[回测-%s] 失败：%s", task_id, e, exc_info=True)
                        task["status"] = "failed"
                        task["progress"] = 0
                        task["result"] = {
                            "error": str(e),
                        }

                        # 更新数据库状态
                        self.db_manager.execute_update(
                            """
                            UPDATE backtest_tasks
                            SET status = ?, progress = ?, updated_at = ?
                            WHERE task_id = ?
                        """,
                            ("failed", 0, datetime.now().isoformat(), task_id),
                        )
                    finally:
                        # 退出场景上下文并恢复阶段 - 日志埋点v4.0
                        if scenario_ctx:
                            try:
                                scenario_ctx.__exit__(None, None, None)
                            except Exception:
                                pass
                        if ctx:
                            try:
                                ctx.set_stage("sensing")
                                self.logger.info("📍 回测结束，恢复到数据感知阶段")
                            except Exception:
                                pass

                # 启动后台线程
                backtest_thread = threading.Thread(target=run_backtest, daemon=True)
                backtest_thread.start()

                self.log_operation_success("启动回测任务", task_id=task_id)
                self.logger.info("回测任务 %s 已在后台线程启动", task_id)

                return {
                    "success": True,
                    "task_id": task_id,
                    "message": "回测已启动",
                }

            except Exception as e:
                self.log_operation_failure("启动回测任务", e, task_id=task_id)
                return {
                    "success": False,
                    "message": f"回测启动失败: {str(e)}",
                }

        except Exception as e:
            self.log_operation_failure("启动回测", e)
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
