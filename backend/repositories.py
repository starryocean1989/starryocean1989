# -*- coding: utf-8 -*-
"""
仓储层模块 - 合并版本.

整合了以下仓储类：
- base_repository: 基础仓库类和内存仓库
- data_repositories: 品种、数据源、下载任务仓库
- system_repositories: 告警、日志、配置、组合仓库
- trading_repositories: 网关、策略、回测仓库

提供统一的数据访问接口，减少文件碎片化，优化调试体验。
"""

import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, Generic, List, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


# =============================================================================
# Part 1: 基础仓库类 (来自 base_repository.py)
# =============================================================================


class BaseRepository(ABC, Generic[T]):
    """基础仓库类."""

    def __init__(self, table_name: str):
        """初始化基础仓库."""
        self.table_name = table_name
        self.logger = logging.getLogger(f"{__name__}.{table_name}")

    @abstractmethod
    async def create(self, entity: T) -> T:  # noqa: U100
        """创建实体."""
        pass

    @abstractmethod
    async def get_by_id(self, entity_id: str) -> Optional[T]:  # noqa: U100
        """根据ID获取实体."""
        pass

    @abstractmethod
    async def get_all(self, limit: int = 100, offset: int = 0) -> List[T]:  # noqa: U100
        """获取所有实体."""
        pass

    @abstractmethod
    async def update(self, entity: T) -> T:  # noqa: U100
        """更新实体."""
        pass

    @abstractmethod
    async def delete(self, entity_id: str) -> bool:  # noqa: U100
        """删除实体."""
        pass

    @abstractmethod
    async def count(self) -> int:
        """获取实体总数."""
        pass

    @abstractmethod
    async def exists(self, entity_id: str) -> bool:  # noqa: U100
        """检查实体是否存在."""
        pass

    def _log_operation(self, operation: str, **kwargs) -> None:
        """记录操作日志."""
        self.logger.info(
            "数据库操作: %s - %s",
            operation,
            ", ".join(f"{k}={v}" for k, v in kwargs.items()),
        )

    def _log_error(self, operation: str, error: Exception, **kwargs) -> None:
        """记录错误日志."""
        self.logger.error(
            "数据库操作错误: %s - %s - %s",
            operation,
            str(error),
            ", ".join(f"{k}={v}" for k, v in kwargs.items()),
        )


class InMemoryRepository(BaseRepository[T]):
    """内存仓库实现."""

    def __init__(self, table_name: str):
        """初始化内存仓库."""
        super().__init__(table_name)
        self._data: Dict[str, T] = {}
        self._id_counter = 0

    async def create(self, entity: T) -> T:
        """创建实体."""
        try:
            self._log_operation("create", table=self.table_name)

            # 生成ID
            entity_id = str(self._id_counter + 1)
            self._id_counter += 1

            # 设置ID和创建时间
            if hasattr(entity, "id"):
                entity.id = entity_id  # type: ignore
            if hasattr(entity, "created_at"):
                entity.created_at = datetime.now()  # type: ignore
            if hasattr(entity, "updated_at"):
                entity.updated_at = datetime.now()  # type: ignore

            # 保存到内存
            self._data[entity_id] = entity

            self.logger.info("实体创建成功: id=%s", entity_id)
            return entity

        except Exception as e:
            self._log_error("create", e, table=self.table_name)
            raise

    async def get_by_id(self, entity_id: str) -> Optional[T]:
        """根据ID获取实体."""
        try:
            entity = self._data.get(entity_id)
            if entity:
                self._log_operation("get_by_id", table=self.table_name, id=entity_id)
            else:
                self.logger.warning("实体不存在: id=%s", entity_id)
            return entity

        except Exception as e:
            self._log_error("get_by_id", e, table=self.table_name, id=entity_id)
            raise

    async def get_all(self, limit: int = 100, offset: int = 0) -> List[T]:
        """获取所有实体."""
        try:
            entities = list(self._data.values())[offset : offset + limit]
            self._log_operation(
                "get_all",
                table=self.table_name,
                limit=limit,
                offset=offset,
                count=len(entities),
            )
            return entities

        except Exception as e:
            self._log_error("get_all", e, table=self.table_name, limit=limit, offset=offset)
            raise

    async def update(self, entity: T) -> T:
        """更新实体."""
        try:
            # 获取实体ID
            entity_id = None
            if hasattr(entity, "id"):
                entity_id = entity.id  # type: ignore
            elif hasattr(entity, "task_id"):
                entity_id = entity.task_id  # type: ignore
            elif hasattr(entity, "source_id"):
                entity_id = entity.source_id  # type: ignore

            if not entity_id:
                raise ValueError("实体缺少ID字段")

            # 检查实体是否存在
            if entity_id not in self._data:
                raise ValueError(f"实体不存在: id={entity_id}")

            # 更新更新时间
            if hasattr(entity, "updated_at"):
                entity.updated_at = datetime.now()  # type: ignore

            # 更新实体
            self._data[entity_id] = entity

            self._log_operation("update", table=self.table_name, id=entity_id)
            self.logger.info("实体更新成功: id=%s", entity_id)
            return entity

        except Exception as e:
            self._log_error("update", e, table=self.table_name)
            raise

    async def delete(self, entity_id: str) -> bool:
        """删除实体."""
        try:
            if entity_id not in self._data:
                self.logger.warning("实体不存在: id=%s", entity_id)
                return False

            del self._data[entity_id]
            self._log_operation("delete", table=self.table_name, id=entity_id)
            self.logger.info("实体删除成功: id=%s", entity_id)
            return True

        except Exception as e:
            self._log_error("delete", e, table=self.table_name, id=entity_id)
            raise

    async def count(self) -> int:
        """获取实体总数."""
        try:
            count = len(self._data)
            self._log_operation("count", table=self.table_name, count=count)
            return count

        except Exception as e:
            self._log_error("count", e, table=self.table_name)
            raise

    async def exists(self, entity_id: str) -> bool:
        """检查实体是否存在."""
        try:
            exists = entity_id in self._data
            self._log_operation("exists", table=self.table_name, id=entity_id, exists=exists)
            return exists

        except Exception as e:
            self._log_error("exists", e, table=self.table_name, id=entity_id)
            raise

    async def search(self, filters: Dict[str, Any], limit: int = 100, offset: int = 0) -> List[T]:
        """搜索实体."""
        try:
            filtered_entities = []

            for entity in self._data.values():
                match = True
                for key, value in filters.items():
                    if hasattr(entity, key):
                        entity_value = getattr(entity, key)
                        if entity_value != value:
                            match = False
                            break
                    else:
                        match = False
                        break

                if match:
                    filtered_entities.append(entity)

            # 分页
            result = filtered_entities[offset : offset + limit]
            self._log_operation("search", table=self.table_name, filters=filters, count=len(result))
            return result

        except Exception as e:
            self._log_error("search", e, table=self.table_name, filters=filters)
            raise

    def get_statistics(self) -> Dict[str, Any]:
        """获取仓库统计信息."""
        try:
            return {
                "table_name": self.table_name,
                "total_entities": len(self._data),
                "id_counter": self._id_counter,
                "timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            self.logger.error("获取仓库统计信息失败: %s", e)
            return {
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }


# =============================================================================
# Part 2: 数据相关仓库 (来自 data_repositories.py)
# =============================================================================


class SymbolRepository:
    """品种仓库."""

    def __init__(self) -> None:
        """初始化品种仓库."""
        self.logger = logging.getLogger(f"{__name__}.SymbolRepository")
        self._symbols: Dict[str, Dict[str, Any]] = {}

    def create(self, symbol_data: Dict[str, Any]) -> bool:
        """创建品种."""
        try:
            symbol_id = f"{symbol_data['symbol']}.{symbol_data['exchange']}"
            self._symbols[symbol_id] = symbol_data
            return True
        except Exception as e:
            self.logger.error("创建品种失败: %s", e)
            return False

    def get(self, symbol: str, exchange: str) -> Optional[Dict[str, Any]]:
        """获取品种."""
        symbol_id = f"{symbol}.{exchange}"
        return self._symbols.get(symbol_id)

    def list(self, exchange: Optional[str] = None, limit: int = 1000) -> List[Dict[str, Any]]:
        """获取品种列表."""
        symbols = list(self._symbols.values())
        if exchange:
            symbols = [s for s in symbols if s.get("exchange") == exchange]
        return symbols[:limit]

    def update(self, symbol: str, exchange: str, data: Dict[str, Any]) -> bool:
        """更新品种."""
        try:
            symbol_id = f"{symbol}.{exchange}"
            if symbol_id in self._symbols:
                self._symbols[symbol_id].update(data)
                return True
            return False
        except Exception as e:
            self.logger.error("更新品种失败: %s", e)
            return False

    def delete(self, symbol: str, exchange: str) -> bool:
        """删除品种."""
        try:
            symbol_id = f"{symbol}.{exchange}"
            if symbol_id in self._symbols:
                del self._symbols[symbol_id]
                return True
            return False
        except Exception as e:
            self.logger.error("删除品种失败: %s", e)
            return False


class DataSourceRepository:
    """数据源仓库."""

    def __init__(self) -> None:
        """初始化数据源仓库."""
        self.logger = logging.getLogger(f"{__name__}.DataSourceRepository")
        self._data_sources: Dict[str, Dict[str, Any]] = {}

    def create(self, source_data: Dict[str, Any]) -> bool:
        """创建数据源."""
        try:
            source_id = source_data["source_id"]
            self._data_sources[source_id] = source_data
            return True
        except Exception as e:
            self.logger.error("创建数据源失败: %s", e)
            return False

    def get(self, source_id: str) -> Optional[Dict[str, Any]]:
        """获取数据源."""
        return self._data_sources.get(source_id)

    def list(self) -> List[Dict[str, Any]]:
        """获取所有数据源."""
        return list(self._data_sources.values())

    def update(self, source_id: str, data: Dict[str, Any]) -> bool:
        """更新数据源."""
        try:
            if source_id in self._data_sources:
                self._data_sources[source_id].update(data)
                return True
            return False
        except Exception as e:
            self.logger.error("更新数据源失败: %s", e)
            return False

    def delete(self, source_id: str) -> bool:
        """删除数据源."""
        try:
            if source_id in self._data_sources:
                del self._data_sources[source_id]
                return True
            return False
        except Exception as e:
            self.logger.error("删除数据源失败: %s", e)
            return False


class DownloadTaskRepository:
    """下载任务仓库."""

    def __init__(self) -> None:
        """初始化下载任务仓库."""
        self.logger = logging.getLogger(f"{__name__}.DownloadTaskRepository")
        self._tasks: Dict[str, Dict[str, Any]] = {}

    def create(self, task_data: Dict[str, Any]) -> bool:
        """创建任务."""
        try:
            task_id = task_data["task_id"]
            self._tasks[task_id] = task_data
            return True
        except Exception as e:
            self.logger.error("创建任务失败: %s", e)
            return False

    def get(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务."""
        return self._tasks.get(task_id)

    def list(self, limit: int = 100) -> List[Dict[str, Any]]:
        """获取任务列表."""
        tasks = list(self._tasks.values())
        tasks.sort(key=lambda t: t.get("created_time", ""), reverse=True)
        return tasks[:limit]

    def update(self, task_id: str, data: Dict[str, Any]) -> bool:
        """更新任务."""
        try:
            if task_id in self._tasks:
                self._tasks[task_id].update(data)
                return True
            return False
        except Exception as e:
            self.logger.error("更新任务失败: %s", e)
            return False

    def delete(self, task_id: str) -> bool:
        """删除任务."""
        try:
            if task_id in self._tasks:
                del self._tasks[task_id]
                return True
            return False
        except Exception as e:
            self.logger.error("删除任务失败: %s", e)
            return False


# =============================================================================
# Part 3: 系统相关仓库 (来自 system_repositories.py)
# =============================================================================


class AlertRepository:
    """告警仓库."""

    def __init__(self) -> None:
        """初始化告警仓库."""
        self.logger = logging.getLogger(f"{__name__}.AlertRepository")
        self._alerts: Dict[str, Dict[str, Any]] = {}

    def create(self, alert_data: Dict[str, Any]) -> bool:
        """创建告警."""
        try:
            alert_id = alert_data["alert_id"]
            self._alerts[alert_id] = alert_data
            return True
        except Exception as e:
            self.logger.error("创建告警失败: %s", e)
            return False

    def get(self, alert_id: str) -> Optional[Dict[str, Any]]:
        """获取告警."""
        return self._alerts.get(alert_id)

    def list(self, limit: int = 100) -> List[Dict[str, Any]]:
        """获取告警列表."""
        alerts = list(self._alerts.values())
        alerts.sort(key=lambda a: a.get("created_time", ""), reverse=True)
        return alerts[:limit]

    def update(self, alert_id: str, data: Dict[str, Any]) -> bool:
        """更新告警."""
        try:
            if alert_id in self._alerts:
                self._alerts[alert_id].update(data)
                return True
            return False
        except Exception as e:
            self.logger.error("更新告警失败: %s", e)
            return False

    def delete(self, alert_id: str) -> bool:
        """删除告警."""
        try:
            if alert_id in self._alerts:
                del self._alerts[alert_id]
                return True
            return False
        except Exception as e:
            self.logger.error("删除告警失败: %s", e)
            return False


class LogRepository:
    """日志仓库."""

    def __init__(self) -> None:
        """初始化日志仓库."""
        self.logger = logging.getLogger(f"{__name__}.LogRepository")
        self._logs: List[Dict[str, Any]] = []

    def create(self, log_data: Dict[str, Any]) -> bool:
        """创建日志记录."""
        try:
            self._logs.append(log_data)
            return True
        except Exception as e:
            self.logger.error("创建日志失败: %s", e)
            return False

    def list(self, level: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """查询日志."""
        logs = self._logs
        if level:
            logs = [log for log in logs if log.get("level") == level]
        logs.sort(key=lambda log: log.get("timestamp", ""), reverse=True)
        return logs[:limit]


class ConfigRepository:
    """配置仓库."""

    def __init__(self) -> None:
        """初始化配置仓库."""
        self.logger = logging.getLogger(f"{__name__}.ConfigRepository")
        self._configs: Dict[str, Any] = {}

    def get(self, key: str) -> Optional[Any]:
        """获取配置."""
        return self._configs.get(key)

    def set(self, key: str, value: Any) -> bool:
        """设置配置."""
        try:
            self._configs[key] = value
            return True
        except Exception as e:
            self.logger.error("设置配置失败: %s", e)
            return False

    def get_all(self) -> Dict[str, Any]:
        """获取所有配置."""
        return self._configs.copy()

    def delete(self, key: str) -> bool:
        """删除配置."""
        try:
            if key in self._configs:
                del self._configs[key]
                return True
            return False
        except Exception as e:
            self.logger.error("删除配置失败: %s", e)
            return False


class PortfolioRepository:
    """组合仓库."""

    def __init__(self) -> None:
        """初始化组合仓库."""
        self.logger = logging.getLogger(f"{__name__}.PortfolioRepository")
        self._portfolios: Dict[str, Dict[str, Any]] = {}

    def create(self, portfolio_data: Dict[str, Any]) -> bool:
        """创建组合."""
        try:
            portfolio_id = portfolio_data["portfolio_id"]
            self._portfolios[portfolio_id] = portfolio_data
            return True
        except Exception as e:
            self.logger.error("创建组合失败: %s", e)
            return False

    def get(self, portfolio_id: str) -> Optional[Dict[str, Any]]:
        """获取组合."""
        return self._portfolios.get(portfolio_id)

    def list(self) -> List[Dict[str, Any]]:
        """获取所有组合."""
        return list(self._portfolios.values())

    def update(self, portfolio_id: str, data: Dict[str, Any]) -> bool:
        """更新组合."""
        try:
            if portfolio_id in self._portfolios:
                self._portfolios[portfolio_id].update(data)
                return True
            return False
        except Exception as e:
            self.logger.error("更新组合失败: %s", e)
            return False

    def delete(self, portfolio_id: str) -> bool:
        """删除组合."""
        try:
            if portfolio_id in self._portfolios:
                del self._portfolios[portfolio_id]
                return True
            return False
        except Exception as e:
            self.logger.error("删除组合失败: %s", e)
            return False


# =============================================================================
# Part 4: 交易相关仓库 (来自 trading_repositories.py)
# =============================================================================


class GatewayRepository:
    """网关仓库."""

    def __init__(self) -> None:
        """初始化网关仓库."""
        self.logger = logging.getLogger(f"{__name__}.GatewayRepository")
        self._gateways: Dict[str, Dict[str, Any]] = {}

    def create(self, gateway_data: Dict[str, Any]) -> bool:
        """创建网关."""
        try:
            gateway_id = gateway_data["gateway_id"]
            self._gateways[gateway_id] = gateway_data
            return True
        except Exception as e:
            self.logger.error("创建网关失败: %s", e)
            return False

    def get(self, gateway_id: str) -> Optional[Dict[str, Any]]:
        """获取网关."""
        return self._gateways.get(gateway_id)

    def list(self) -> List[Dict[str, Any]]:
        """获取所有网关."""
        return list(self._gateways.values())

    def update(self, gateway_id: str, data: Dict[str, Any]) -> bool:
        """更新网关."""
        try:
            if gateway_id in self._gateways:
                self._gateways[gateway_id].update(data)
                return True
            return False
        except Exception as e:
            self.logger.error("更新网关失败: %s", e)
            return False

    def delete(self, gateway_id: str) -> bool:
        """删除网关."""
        try:
            if gateway_id in self._gateways:
                del self._gateways[gateway_id]
                return True
            return False
        except Exception as e:
            self.logger.error("删除网关失败: %s", e)
            return False


class StrategyRepository:
    """策略仓库."""

    def __init__(self) -> None:
        """初始化策略仓库."""
        self.logger = logging.getLogger(f"{__name__}.StrategyRepository")
        self._strategies: Dict[str, Dict[str, Any]] = {}

    def create(self, strategy_data: Dict[str, Any]) -> bool:
        """创建策略."""
        try:
            strategy_id = strategy_data["strategy_id"]
            self._strategies[strategy_id] = strategy_data
            return True
        except Exception as e:
            self.logger.error("创建策略失败: %s", e)
            return False

    def get(self, strategy_id: str) -> Optional[Dict[str, Any]]:
        """获取策略."""
        return self._strategies.get(strategy_id)

    def list(self) -> List[Dict[str, Any]]:
        """获取所有策略."""
        return list(self._strategies.values())

    def update(self, strategy_id: str, data: Dict[str, Any]) -> bool:
        """更新策略."""
        try:
            if strategy_id in self._strategies:
                self._strategies[strategy_id].update(data)
                return True
            return False
        except Exception as e:
            self.logger.error("更新策略失败: %s", e)
            return False

    def delete(self, strategy_id: str) -> bool:
        """删除策略."""
        try:
            if strategy_id in self._strategies:
                del self._strategies[strategy_id]
                return True
            return False
        except Exception as e:
            self.logger.error("删除策略失败: %s", e)
            return False


class BacktestRepository:
    """回测仓库."""

    def __init__(self) -> None:
        """初始化回测仓库."""
        self.logger = logging.getLogger(f"{__name__}.BacktestRepository")
        self._backtests: Dict[str, Dict[str, Any]] = {}

    def create(self, backtest_data: Dict[str, Any]) -> bool:
        """创建回测任务."""
        try:
            task_id = backtest_data["task_id"]
            self._backtests[task_id] = backtest_data
            return True
        except Exception as e:
            self.logger.error("创建回测任务失败: %s", e)
            return False

    def get(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取回测任务."""
        return self._backtests.get(task_id)

    def list(self, limit: int = 100) -> List[Dict[str, Any]]:
        """获取回测任务列表."""
        tasks = list(self._backtests.values())
        tasks.sort(key=lambda t: t.get("created_time", ""), reverse=True)
        return tasks[:limit]

    def update(self, task_id: str, data: Dict[str, Any]) -> bool:
        """更新回测任务."""
        try:
            if task_id in self._backtests:
                self._backtests[task_id].update(data)
                return True
            return False
        except Exception as e:
            self.logger.error("更新回测任务失败: %s", e)
            return False

    def delete(self, task_id: str) -> bool:
        """删除回测任务."""
        try:
            if task_id in self._backtests:
                del self._backtests[task_id]
                return True
            return False
        except Exception as e:
            self.logger.error("删除回测任务失败: %s", e)
            return False


# =============================================================================
# 导出的公共接口
# =============================================================================

__all__ = [
    # 基础仓库
    "BaseRepository",
    "InMemoryRepository",
    # 数据相关
    "SymbolRepository",
    "DataSourceRepository",
    "DownloadTaskRepository",
    # 系统相关
    "AlertRepository",
    "LogRepository",
    "ConfigRepository",
    "PortfolioRepository",
    # 交易相关
    "GatewayRepository",
    "StrategyRepository",
    "BacktestRepository",
]
