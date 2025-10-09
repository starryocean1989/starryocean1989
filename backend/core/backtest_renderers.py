# -*- coding: utf-8 -*-
"""
回测结果渲染器模块.

提供不同策略类型的自定义回测结果展示模板，对应需求文档链条4.2.2。
支持6种策略类型：
- CTA策略 - 标准收益分析
- 期权策略 - Greeks展示
- 组合策略 - 多品种贡献分析
- 算法交易 - 执行质量分析
- 价差交易 - 价差分析
- 脚本交易 - 默认展示
"""

from typing import Any, Dict, List
from enum import Enum


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
