# -*- coding: utf-8 -*-
"""
组合投资服务.

提供组合管理和监控功能，包括：
- 组合管理（自动识别、自定义组合、虚拟网关）
- 组合监控（实时业绩、风险指标、历史分析）
"""

import hashlib
from typing import Any, Dict, List, Optional
from datetime import datetime
from threading import Timer

from backend.services.base_and_utils import BaseService


class PortfolioService(BaseService):
    """组合投资服务.

    管理投资组合，提供：
    1. 自动组合识别 - 识别激活超过1个策略的网关
    2. 自定义组合管理 - 用户创建虚拟网关组合
    3. 组合监控 - 实时业绩、风险指标、历史分析
    """

    def __init__(self):
        """初始化组合投资服务."""
        super().__init__()

        # 自动识别的组合（不可删除）
        self.auto_portfolios: Dict[str, Dict[str, Any]] = {}

        # 自定义组合（可删除）
        self.custom_portfolios: Dict[str, Dict[str, Any]] = {}

        # 虚拟网关
        self.virtual_gateways: Dict[str, Any] = {}

        # 定时扫描器
        self.scan_timer: Optional[Timer] = None
        self.scan_interval = 30  # 扫描间隔（秒）

        self.logger.info("组合投资服务已创建")

    def _do_initialize(self) -> bool:
        """初始化组合投资服务."""
        try:
            self.logger.info("初始化组合投资服务...")

            # 扫描现有网关，自动识别组合
            self._scan_and_create_auto_portfolios()

            # 启动定时扫描
            self._start_auto_scan()

            return True

        except Exception as e:
            self._log_error("初始化", e)
            return False

    def _do_shutdown(self) -> bool:
        """关闭组合投资服务."""
        try:
            # 停止定时扫描
            self._stop_auto_scan()

            # 清理所有组合
            self.auto_portfolios.clear()
            self.custom_portfolios.clear()
            self.virtual_gateways.clear()
            return True
        except Exception as e:
            self._log_error("关闭", e)
            return False

    def _do_health_check(self) -> Dict[str, Any]:
        """健康检查."""
        return {
            "auto_portfolio_count": len(self.auto_portfolios),
            "custom_portfolio_count": len(self.custom_portfolios),
            "virtual_gateway_count": len(self.virtual_gateways),
        }

    def _scan_and_create_auto_portfolios(self):
        """扫描并创建自动识别的组合."""
        try:
            # 从trading_gateway_service获取网关和策略信息
            from backend.core.base import get_service_manager

            service_manager = get_service_manager()
            gateway_service = service_manager.get_service("trading_gateway_service")

            if not gateway_service:
                self.logger.warning("TradingGatewayService不可用，无法扫描自动组合")
                return

            # 识别激活超过1个策略的网关
            for gw_name, strategies in gateway_service.strategy_instances.items():
                active_strategies = [s for s in strategies.values() if s.get("status") == "running"]

                # 如果激活了多个策略，创建自动组合
                if len(active_strategies) > 1:
                    portfolio_id = f"auto_{gw_name}"
                    if portfolio_id not in self.auto_portfolios:
                        self.auto_portfolios[portfolio_id] = {
                            "id": portfolio_id,
                            "gateway_name": gw_name,
                            "strategy_count": len(active_strategies),
                            "create_time": datetime.now(),
                        }
                        self.logger.info(
                            f"自动创建组合: {portfolio_id} ({len(active_strategies)}个策略)"
                        )

        except Exception as e:
            self.logger.error(f"扫描自动组合失败: {e}")

    def _start_auto_scan(self):
        """启动自动扫描定时器."""
        try:
            self.logger.info(f"启动组合自动扫描（间隔{self.scan_interval}秒）")
            self._schedule_next_scan()
        except Exception as e:
            self.logger.error(f"启动自动扫描失败: {e}")

    def _stop_auto_scan(self):
        """停止自动扫描定时器."""
        if self.scan_timer:
            self.scan_timer.cancel()
            self.scan_timer = None
            self.logger.info("已停止组合自动扫描")

    def _schedule_next_scan(self):
        """调度下一次扫描."""
        if self.scan_timer:
            self.scan_timer.cancel()

        def scan_task():
            try:
                self._scan_and_create_auto_portfolios()
                self._schedule_next_scan()  # 递归调度
            except Exception as e:
                self.logger.error(f"定时扫描任务失败: {e}")

        self.scan_timer = Timer(self.scan_interval, scan_task)
        self.scan_timer.daemon = True
        self.scan_timer.start()

    # ==================== 组合管理 ====================

    def create_custom_portfolio(
        self,
        portfolio_name: str,
        gateway_names: List[str],
        weights: Optional[Dict[str, float]] = None,
    ) -> Dict[str, Any]:
        """创建自定义组合.

        Args:
            portfolio_name: 组合名称
            gateway_names: 成员网关列表
            weights: 权重配置（可选）

        Returns:
            Dict: 创建结果
        """
        try:
            if portfolio_name in self.custom_portfolios:
                return {"success": False, "message": "组合名称已存在"}

            # 生成虚拟网关ID
            virtual_gw_id = self._generate_virtual_gateway_id(portfolio_name)

            # 创建组合
            self.custom_portfolios[portfolio_name] = {
                "name": portfolio_name,
                "gateway_names": gateway_names,
                "weights": weights or {},
                "virtual_gateway_id": virtual_gw_id,
                "create_time": datetime.now(),
            }

            # 创建虚拟网关
            self.virtual_gateways[virtual_gw_id] = {
                "id": virtual_gw_id,
                "portfolio_name": portfolio_name,
                "gateway_names": gateway_names,
            }

            return {
                "success": True,
                "message": "自定义组合创建成功",
                "portfolio_name": portfolio_name,
                "virtual_gateway_id": virtual_gw_id,
            }

        except Exception as e:
            self._log_error("创建自定义组合", e)
            return {"success": False, "message": str(e)}

    def delete_custom_portfolio(self, portfolio_name: str) -> Dict[str, Any]:
        """删除自定义组合.

        Args:
            portfolio_name: 组合名称

        Returns:
            Dict: 操作结果
        """
        try:
            if portfolio_name not in self.custom_portfolios:
                return {"success": False, "message": "组合不存在"}

            # 获取虚拟网关ID
            virtual_gw_id = self.custom_portfolios[portfolio_name]["virtual_gateway_id"]

            # 删除组合和虚拟网关
            del self.custom_portfolios[portfolio_name]
            if virtual_gw_id in self.virtual_gateways:
                del self.virtual_gateways[virtual_gw_id]

            return {
                "success": True,
                "message": "自定义组合已删除",
            }

        except Exception as e:
            self._log_error("删除自定义组合", e)
            return {"success": False, "message": str(e)}

    def list_portfolios(self) -> Dict[str, Any]:
        """列出所有组合.

        Returns:
            Dict: 组合列表
        """
        portfolios = {
            "auto_portfolios": list(self.auto_portfolios.values()),
            "custom_portfolios": list(self.custom_portfolios.values()),
        }
        return {
            "success": True,
            "portfolios": portfolios,
        }

    def _generate_virtual_gateway_id(self, portfolio_name: str) -> str:
        """生成虚拟网关ID.

        Args:
            portfolio_name: 组合名称

        Returns:
            str: 虚拟网关ID
        """
        unique_str = f"{portfolio_name}_{datetime.now().isoformat()}"
        return f"VG_{hashlib.md5(unique_str.encode()).hexdigest()[:8]}"

    # ==================== 组合监控 ====================

    def get_portfolio_monitoring(self, portfolio_name: str) -> Dict[str, Any]:
        """获取组合监控数据.

        Args:
            portfolio_name: 组合名称或虚拟网关ID

        Returns:
            Dict: 监控数据
        """
        try:
            # 查找组合
            portfolio = None
            gateway_names = []

            # 先检查自定义组合
            if portfolio_name in self.custom_portfolios:
                portfolio = self.custom_portfolios[portfolio_name]
                gateway_names = portfolio["gateway_names"]
            # 再检查自动组合
            elif portfolio_name in self.auto_portfolios:
                portfolio = self.auto_portfolios[portfolio_name]
                gateway_names = [portfolio["gateway_name"]]
            else:
                return {
                    "success": False,
                    "message": f"组合 '{portfolio_name}' 不存在",
                }

            # 从TradingGatewayService获取监控数据
            from backend.core.base import get_service_manager

            service_manager = get_service_manager()
            gateway_service = service_manager.get_service("trading_gateway_service")

            if not gateway_service:
                return {
                    "success": False,
                    "message": "TradingGatewayService不可用",
                }

            # 聚合多个网关的数据
            aggregated_data = {
                "positions": [],
                "accounts": [],
                "total_balance": 0,
                "total_pnl": 0,
            }

            for gw_name in gateway_names:
                try:
                    result = gateway_service.get_monitoring_data(gw_name)
                    if result.get("success"):
                        data = result.get("data", {})
                        aggregated_data["positions"].extend(data.get("positions", []))
                        aggregated_data["accounts"].extend(data.get("accounts", []))

                        # 计算总资金
                        for account in data.get("accounts", []):
                            aggregated_data["total_balance"] += account.get("balance", 0)

                        # 计算总盈亏
                        for position in data.get("positions", []):
                            aggregated_data["total_pnl"] += position.get("pnl", 0)

                except Exception as e:
                    self.logger.warning(f"获取网关 {gw_name} 数据失败: {e}")

            return {
                "success": True,
                "portfolio_name": portfolio_name,
                "data": aggregated_data,
            }

        except Exception as e:
            self._log_error("获取组合监控", e)
            return {"success": False, "message": str(e)}

    def get_historical_performance(
        self,
        portfolio_name: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        period: str = "daily",
    ) -> Dict[str, Any]:
        """获取组合历史业绩分析.

        对应需求：组合投资的历史业绩分析功能

        Args:
            portfolio_name: 组合名称
            start_date: 开始日期
            end_date: 结束日期
            period: 统计周期（daily/weekly/monthly/yearly）

        Returns:
            Dict: 历史业绩数据
        """
        try:
            from datetime import datetime, timedelta

            # 默认查询最近30天
            if not end_date:
                end_date = datetime.now().strftime("%Y-%m-%d")
            if not start_date:
                start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

            # TODO: 从数据库或日志中获取历史交易记录
            # 这里暂时返回模拟数据结构
            historical_data = {
                "performance_curve": [],  # 历史业绩曲线
                "period_statistics": [],  # 按周期统计
                "drawdown_analysis": [],  # 历史回撤分析
            }

            return {
                "success": True,
                "portfolio_name": portfolio_name,
                "start_date": start_date,
                "end_date": end_date,
                "period": period,
                "data": historical_data,
                "message": "历史业绩数据（功能完善中，待集成实际数据源）",
            }

        except Exception as e:
            self._log_error("获取历史业绩", e)
            return {"success": False, "message": str(e)}

    def calculate_period_statistics(self, period_type: str = "daily") -> Dict[str, Any]:
        """按时间段统计业绩.

        Args:
            period_type: 周期类型（daily/weekly/monthly/yearly）

        Returns:
            Dict: 周期统计数据
        """
        try:
            # TODO: 实现按周期的业绩统计
            statistics = {
                "daily": [],  # 日度收益
                "weekly": [],  # 周度收益
                "monthly": [],  # 月度收益
                "yearly": [],  # 年度收益
            }

            return {
                "success": True,
                "period_type": period_type,
                "statistics": statistics.get(period_type, []),
            }

        except Exception as e:
            self._log_error("计算周期统计", e)
            return {"success": False, "message": str(e)}

    # ==================== 高级风险指标 ====================

    def calculate_portfolio_risk_metrics(
        self, portfolio_name: str, price_history: List[float], confidence_level: float = 0.95
    ) -> Dict[str, Any]:
        """计算组合高级风险指标.

        Args:
            portfolio_name: 组合名称
            price_history: 价格历史数据列表
            confidence_level: 置信水平（默认95%）

        Returns:
            Dict: 风险指标
        """
        try:
            import numpy as np

            if not price_history or len(price_history) < 2:
                return {
                    "success": False,
                    "message": "价格数据不足，无法计算风险指标",
                }

            # 转换为numpy数组
            prices = np.array(price_history)

            # 1. 计算收益率
            returns = np.diff(prices) / prices[:-1]

            # 2. 计算波动率（年化）
            volatility = np.std(returns) * np.sqrt(252)  # 假设252个交易日

            # 3. 计算VaR（Value at Risk）
            var_percentile = (1 - confidence_level) * 100
            var_value = np.percentile(returns, var_percentile)
            var_amount = abs(var_value * prices[-1])  # 转换为金额

            # 4. 计算CVaR（Conditional VaR，期望损失）
            cvar_returns = returns[returns <= var_value]
            cvar_value = np.mean(cvar_returns) if len(cvar_returns) > 0 else var_value
            cvar_amount = abs(cvar_value * prices[-1])

            # 5. 计算最大回撤
            cumulative = np.cumprod(1 + returns)
            running_max = np.maximum.accumulate(cumulative)
            drawdowns = (cumulative - running_max) / running_max
            max_drawdown = np.min(drawdowns) if len(drawdowns) > 0 else 0.0

            # 6. 计算夏普比率（假设无风险利率为3%）
            risk_free_rate = 0.03
            excess_returns = np.mean(returns) * 252 - risk_free_rate
            sharpe_ratio = excess_returns / volatility if volatility > 0 else 0.0

            self.logger.info(f"组合 {portfolio_name} 风险指标计算完成")

            return {
                "success": True,
                "metrics": {
                    "volatility": float(volatility),
                    "var_95": float(var_amount),
                    "cvar_95": float(cvar_amount),
                    "max_drawdown": float(max_drawdown),
                    "sharpe_ratio": float(sharpe_ratio),
                    "mean_return": float(np.mean(returns)),
                    "std_return": float(np.std(returns)),
                },
            }

        except ImportError as e:
            self.logger.warning(f"scipy或numpy未安装: {e}")
            return {
                "success": False,
                "message": "scipy或numpy未安装，无法计算高级风险指标",
            }
        except Exception as e:
            self._log_error("计算风险指标", e)
            return {
                "success": False,
                "message": f"计算失败: {str(e)}",
            }

    def calculate_correlation_matrix(
        self, portfolio_name: str, returns_data: Dict[str, List[float]]
    ) -> Dict[str, Any]:
        """计算组合内品种间的相关性矩阵.

        Args:
            portfolio_name: 组合名称
            returns_data: 各品种的收益率数据 {"symbol": [returns...]}

        Returns:
            Dict: 相关性矩阵和分析结果
        """
        try:
            import numpy as np

            if not returns_data or len(returns_data) < 2:
                return {
                    "success": False,
                    "message": "至少需要2个品种的数据才能计算相关性",
                }

            # 构建收益率矩阵
            symbols = list(returns_data.keys())
            min_length = min(len(data) for data in returns_data.values())

            returns_matrix = np.array([returns_data[symbol][:min_length] for symbol in symbols])

            # 计算相关性矩阵
            correlation_matrix = np.corrcoef(returns_matrix)

            # 转换为字典格式
            correlation_dict = {}
            for i, symbol1 in enumerate(symbols):
                correlation_dict[symbol1] = {}
                for j, symbol2 in enumerate(symbols):
                    correlation_dict[symbol1][symbol2] = float(correlation_matrix[i, j])

            # 计算平均相关性（排除对角线）
            n = len(symbols)
            avg_correlation = (np.sum(correlation_matrix) - n) / (n * (n - 1)) if n > 1 else 0.0

            self.logger.info(f"组合 {portfolio_name} 相关性矩阵计算完成")

            return {
                "success": True,
                "symbols": symbols,
                "correlation_matrix": correlation_dict,
                "avg_correlation": float(avg_correlation),
            }

        except ImportError:
            return {
                "success": False,
                "message": "numpy未安装，无法计算相关性矩阵",
            }
        except Exception as e:
            self._log_error("计算相关性矩阵", e)
            return {
                "success": False,
                "message": f"计算失败: {str(e)}",
            }

    def calculate_portfolio_volatility(
        self,
        portfolio_name: str,
        weights: Dict[str, float],
        volatilities: Dict[str, float],
        correlation_matrix: Dict[str, Dict[str, float]],
    ) -> Dict[str, Any]:
        """计算组合波动率（考虑相关性）.

        Args:
            portfolio_name: 组合名称
            weights: 各品种权重 {"symbol": weight}
            volatilities: 各品种波动率 {"symbol": volatility}
            correlation_matrix: 相关性矩阵

        Returns:
            Dict: 组合波动率
        """
        try:
            import numpy as np

            symbols = list(weights.keys())
            n = len(symbols)

            if n < 1:
                return {
                    "success": False,
                    "message": "没有品种数据",
                }

            # 构建权重向量
            w = np.array([weights[s] for s in symbols])

            # 构建协方差矩阵
            cov_matrix = np.zeros((n, n))
            for i, s1 in enumerate(symbols):
                for j, s2 in enumerate(symbols):
                    vol1 = volatilities.get(s1, 0)
                    vol2 = volatilities.get(s2, 0)
                    corr = correlation_matrix.get(s1, {}).get(s2, 0)
                    cov_matrix[i, j] = vol1 * vol2 * corr

            # 计算组合波动率: sqrt(w^T * Cov * w)
            portfolio_variance = np.dot(w, np.dot(cov_matrix, w))
            portfolio_volatility = np.sqrt(portfolio_variance)

            # 计算分散化效益
            weighted_avg_vol = np.sum(w * np.array([volatilities[s] for s in symbols]))
            diversification_benefit = weighted_avg_vol - portfolio_volatility

            self.logger.info(f"组合 {portfolio_name} 波动率计算完成: {portfolio_volatility:.4f}")

            return {
                "success": True,
                "portfolio_volatility": float(portfolio_volatility),
                "weighted_avg_volatility": float(weighted_avg_vol),
                "diversification_benefit": float(diversification_benefit),
            }

        except ImportError:
            return {
                "success": False,
                "message": "numpy未安装，无法计算组合波动率",
            }
        except Exception as e:
            self._log_error("计算组合波动率", e)
            return {
                "success": False,
                "message": f"计算失败: {str(e)}",
            }
