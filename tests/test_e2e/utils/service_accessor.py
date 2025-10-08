# -*- coding: utf-8 -*-
"""
服务访问工具.

提供访问后端服务内部状态的便捷方法。
"""

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class ServiceAccessor:
    """访问后端服务内部状态的工具类."""

    def __init__(self):
        """初始化服务访问器."""
        self.logger = logging.getLogger(self.__class__.__name__)

    def get_cache_stats(self, symbol_service) -> Dict[str, Any]:
        """
        获取品种服务的缓存统计信息.

        Args:
            symbol_service: SymbolService实例

        Returns:
            缓存统计信息字典
        """
        try:
            # 访问私有属性获取缓存状态
            cache_size = len(symbol_service._symbols_cache)
            cache_updated = symbol_service._cache_updated

            # 获取缓存中的交易所和产品类型
            exchanges = set()
            products = set()
            for symbol_info in symbol_service._symbols_cache.values():
                exchanges.add(symbol_info.exchange)
                if symbol_info.product:
                    products.add(symbol_info.product)

            stats = {
                "cache_size": cache_size,
                "cache_updated": cache_updated,
                "exchanges_count": len(exchanges),
                "products_count": len(products),
                "exchanges": sorted(list(exchanges)),
                "products": sorted(list(products)),
            }

            self.logger.info(f"品种缓存统计: 共 {cache_size} 个品种")
            return stats

        except Exception as e:
            self.logger.error(f"获取缓存统计失败: {e}")
            return {
                "cache_size": 0,
                "cache_updated": False,
                "error": str(e),
            }

    def verify_cache_content(
        self,
        symbol_service,
        expected_min_size: int = 1,
    ) -> Dict[str, Any]:
        """
        验证缓存内容的有效性.

        Args:
            symbol_service: SymbolService实例
            expected_min_size: 期望的最小缓存大小

        Returns:
            验证结果字典
        """
        try:
            cache = symbol_service._symbols_cache
            cache_updated = symbol_service._cache_updated

            # 基础验证
            if not cache_updated:
                return {
                    "valid": False,
                    "reason": "缓存未更新",
                    "cache_size": len(cache),
                }

            if len(cache) < expected_min_size:
                return {
                    "valid": False,
                    "reason": f"缓存大小不足: {len(cache)} < {expected_min_size}",
                    "cache_size": len(cache),
                }

            # 验证缓存键格式
            invalid_keys = []
            for key in cache.keys():
                if "." not in key:
                    invalid_keys.append(key)

            if invalid_keys:
                return {
                    "valid": False,
                    "reason": f"发现无效的缓存键格式: {invalid_keys[:5]}",
                    "cache_size": len(cache),
                }

            # 验证缓存值
            invalid_values = []
            for key, value in list(cache.items())[:10]:  # 只检查前10个
                if not hasattr(value, "symbol") or not hasattr(value, "exchange"):
                    invalid_values.append(key)

            if invalid_values:
                return {
                    "valid": False,
                    "reason": f"发现无效的缓存值: {invalid_values}",
                    "cache_size": len(cache),
                }

            self.logger.info(f"缓存内容验证通过: {len(cache)} 个品种")
            return {
                "valid": True,
                "cache_size": len(cache),
                "cache_updated": cache_updated,
            }

        except Exception as e:
            self.logger.error(f"验证缓存内容失败: {e}")
            return {
                "valid": False,
                "reason": f"验证过程出错: {str(e)}",
                "error": str(e),
            }

    def get_task_status(
        self,
        download_service,
        task_id: str,
    ) -> Optional[Dict[str, Any]]:
        """
        获取下载任务的状态.

        Args:
            download_service: DownloadService实例
            task_id: 任务ID

        Returns:
            任务状态字典，如果任务不存在返回None
        """
        try:
            # 从服务的私有属性获取任务
            task = download_service._tasks.get(task_id)

            if not task:
                self.logger.warning(f"任务不存在: {task_id}")
                return None

            # 检查是否有运行中的异步任务
            is_running = task_id in download_service._running_tasks

            status = {
                "task_id": task.task_id,
                "symbol": task.symbol,
                "exchange": task.exchange,
                "status": task.status,
                "progress": task.progress,
                "total_count": task.total_count,
                "downloaded_count": task.downloaded_count,
                "error_message": task.error_message,
                "is_running": is_running,
                "created_at": task.created_at.isoformat() if task.created_at else None,
                "updated_at": task.updated_at.isoformat() if task.updated_at else None,
            }

            self.logger.info(f"任务状态: {task_id} - {task.status}")
            return status

        except Exception as e:
            self.logger.error(f"获取任务状态失败: {e}")
            return None

    def get_all_tasks_summary(
        self,
        download_service,
    ) -> Dict[str, Any]:
        """
        获取所有下载任务的摘要信息.

        Args:
            download_service: DownloadService实例

        Returns:
            任务摘要字典
        """
        try:
            tasks = download_service._tasks
            running_tasks = download_service._running_tasks

            # 按状态分组统计
            status_counts = {}
            for task in tasks.values():
                status = task.status
                status_counts[status] = status_counts.get(status, 0) + 1

            summary = {
                "total_tasks": len(tasks),
                "running_tasks": len(running_tasks),
                "status_counts": status_counts,
                "task_ids": list(tasks.keys()),
            }

            self.logger.info(f"任务摘要: 共 {len(tasks)} 个任务")
            return summary

        except Exception as e:
            self.logger.error(f"获取任务摘要失败: {e}")
            return {
                "total_tasks": 0,
                "running_tasks": 0,
                "error": str(e),
            }

    def get_datasource_connection_state(
        self,
        datasource_service,
    ) -> Dict[str, Any]:
        """
        获取数据源连接状态.

        Args:
            datasource_service: DataSourceService实例

        Returns:
            连接状态字典
        """
        try:
            # 访问数据源服务的连接状态
            connected_source = getattr(datasource_service, "_connected_source", None)
            connection_state = getattr(datasource_service, "_connection_state", "disconnected")
            is_pushing = getattr(datasource_service, "_is_pushing_data", False)

            state = {
                "connected_source": connected_source,
                "connection_state": connection_state,
                "is_pushing": is_pushing,
                "available_sources": ["data_engine", "ifind", "rqdata", "tushare"],
            }

            self.logger.info(
                f"数据源状态: source={connected_source}, "
                f"state={connection_state}, pushing={is_pushing}"
            )
            return state

        except Exception as e:
            self.logger.error(f"获取数据源状态失败: {e}")
            return {
                "connected_source": None,
                "connection_state": "error",
                "error": str(e),
            }

    def get_strategy_pool_info(
        self,
        strategy_instance_service,
        gateway_name: str,
    ) -> Dict[str, Any]:
        """
        获取指定网关的策略池信息.

        Args:
            strategy_instance_service: StrategyInstanceService实例
            gateway_name: 网关名称

        Returns:
            策略池信息字典
        """
        try:
            # 访问策略池
            strategy_pools = getattr(strategy_instance_service, "_strategy_pools", {})
            gateway_pool = strategy_pools.get(gateway_name, [])

            # 统计策略状态
            status_counts = {}
            for strategy in gateway_pool:
                status = strategy.get("status", "unknown")
                status_counts[status] = status_counts.get(status, 0) + 1

            info = {
                "gateway_name": gateway_name,
                "total_strategies": len(gateway_pool),
                "status_counts": status_counts,
                "strategy_ids": [s.get("id") for s in gateway_pool],
            }

            self.logger.info(
                f"策略池信息: gateway={gateway_name}, " f"strategies={len(gateway_pool)}"
            )
            return info

        except Exception as e:
            self.logger.error(f"获取策略池信息失败: {e}")
            return {
                "gateway_name": gateway_name,
                "total_strategies": 0,
                "error": str(e),
            }

    def get_health_check_results(
        self,
        health_check_service,
    ) -> Dict[str, Any]:
        """
        获取健康检查结果.

        Args:
            health_check_service: HealthCheckService实例

        Returns:
            健康检查结果字典
        """
        try:
            # 访问健康检查结果
            health_results = getattr(health_check_service, "_health_results", {})

            # 统计健康状态
            healthy_count = sum(1 for r in health_results.values() if r.get("healthy", False))
            unhealthy_count = len(health_results) - healthy_count

            results = {
                "total_services": len(health_results),
                "healthy_count": healthy_count,
                "unhealthy_count": unhealthy_count,
                "services": health_results,
            }

            self.logger.info(
                f"健康检查结果: 总计={len(health_results)}, "
                f"健康={healthy_count}, 不健康={unhealthy_count}"
            )
            return results

        except Exception as e:
            self.logger.error(f"获取健康检查结果失败: {e}")
            return {
                "total_services": 0,
                "healthy_count": 0,
                "unhealthy_count": 0,
                "error": str(e),
            }

    def get_alert_statistics(
        self,
        alert_service,
    ) -> Dict[str, Any]:
        """
        获取告警统计信息.

        Args:
            alert_service: AlertService实例

        Returns:
            告警统计字典
        """
        try:
            # 访问告警列表
            alerts = getattr(alert_service, "_alerts", [])

            # 按级别统计
            level_counts = {}
            for alert in alerts:
                level = alert.get("level", "unknown")
                level_counts[level] = level_counts.get(level, 0) + 1

            # 按状态统计
            status_counts = {}
            for alert in alerts:
                status = alert.get("status", "unknown")
                status_counts[status] = status_counts.get(status, 0) + 1

            stats = {
                "total_alerts": len(alerts),
                "level_counts": level_counts,
                "status_counts": status_counts,
            }

            self.logger.info(f"告警统计: 总计={len(alerts)}, 级别分布={level_counts}")
            return stats

        except Exception as e:
            self.logger.error(f"获取告警统计失败: {e}")
            return {
                "total_alerts": 0,
                "error": str(e),
            }

    def get_portfolio_monitoring_data(
        self,
        portfolio_service,
        portfolio_id: str,
    ) -> Dict[str, Any]:
        """
        获取组合监控数据.

        Args:
            portfolio_service: PortfolioService实例
            portfolio_id: 组合ID

        Returns:
            监控数据字典
        """
        try:
            # 访问组合监控数据
            monitoring_data = getattr(portfolio_service, "_monitoring_data", {})
            portfolio_data = monitoring_data.get(portfolio_id, {})

            data = {
                "portfolio_id": portfolio_id,
                "performance": portfolio_data.get("performance", {}),
                "risk": portfolio_data.get("risk", {}),
                "positions": portfolio_data.get("positions", []),
                "last_update": portfolio_data.get("last_update"),
            }

            self.logger.info(f"组合监控数据: portfolio_id={portfolio_id}")
            return data

        except Exception as e:
            self.logger.error(f"获取组合监控数据失败: {e}")
            return {
                "portfolio_id": portfolio_id,
                "error": str(e),
            }


# 导出公共接口
__all__ = ["ServiceAccessor"]
