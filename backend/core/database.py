# -*- coding: utf-8 -*-
"""
数据库管理模块

使用vnpy_sqlite作为底层数据库，提供统一的数据库访问接口。
"""

import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from contextlib import contextmanager
import logging

logger = logging.getLogger(__name__)


class DatabaseManager:
    """
    数据库管理器

    提供统一的SQLite数据库访问接口，支持连接池和事务管理。
    """

    def __init__(self, db_path: str = "data/terminal.db"):
        """
        初始化数据库管理器

        Args:
            db_path: 数据库文件路径
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # 初始化数据库表
        self._init_tables()

    def _init_tables(self) -> None:
        """初始化所有数据库表"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # 策略文件元数据表
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS strategy_files (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    path TEXT NOT NULL UNIQUE,
                    type TEXT NOT NULL,
                    content TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
            )

            # 回测任务表
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS backtest_tasks (
                    id TEXT PRIMARY KEY,
                    strategy_id TEXT NOT NULL,
                    parameters TEXT NOT NULL,
                    status TEXT NOT NULL,
                    progress REAL DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    started_at TIMESTAMP,
                    completed_at TIMESTAMP,
                    error TEXT
                )
            """
            )

            # 回测结果表
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS backtest_results (
                    task_id TEXT PRIMARY KEY,
                    result_data TEXT NOT NULL,
                    metrics TEXT,
                    trades TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (task_id) REFERENCES backtest_tasks(id)
                )
            """
            )

            # 网关实例表
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS gateway_instances (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    gateway_type TEXT NOT NULL,
                    config TEXT NOT NULL,
                    status TEXT DEFAULT 'disconnected',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
            )

            # 策略实例表
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS strategy_instances (
                    id TEXT PRIMARY KEY,
                    gateway_id TEXT NOT NULL,
                    strategy_name TEXT NOT NULL,
                    parameters TEXT,
                    status TEXT DEFAULT 'stopped',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (gateway_id) REFERENCES gateway_instances(id)
                )
            """
            )

            # 组合配置表
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS portfolios (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    type TEXT NOT NULL,
                    members TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
            )

            # 组合数据表
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS portfolio_data (
                    portfolio_id TEXT,
                    timestamp TIMESTAMP NOT NULL,
                    data_type TEXT NOT NULL,
                    data TEXT NOT NULL,
                    PRIMARY KEY (portfolio_id, timestamp, data_type),
                    FOREIGN KEY (portfolio_id) REFERENCES portfolios(id)
                )
            """
            )

            # 交易历史表（组合投资监控用）
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS trade_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    portfolio_id TEXT NOT NULL,
                    gateway_name TEXT NOT NULL,
                    strategy_name TEXT,
                    trade_date DATE NOT NULL,
                    trade_time TIMESTAMP NOT NULL,
                    symbol TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    offset TEXT,
                    price REAL NOT NULL,
                    volume INTEGER NOT NULL,
                    turnover REAL,
                    commission REAL DEFAULT 0,
                    slippage REAL DEFAULT 0,
                    pnl REAL DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
            )

            # 持仓快照表（用于计算历史业绩）
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS position_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    portfolio_id TEXT NOT NULL,
                    snapshot_date DATE NOT NULL,
                    snapshot_time TIMESTAMP NOT NULL,
                    symbol TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    volume INTEGER NOT NULL,
                    price REAL NOT NULL,
                    cost REAL NOT NULL,
                    market_value REAL NOT NULL,
                    pnl REAL DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(portfolio_id, snapshot_date, symbol, direction)
                )
            """
            )

            # 账户快照表（用于计算历史业绩）
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS account_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    portfolio_id TEXT NOT NULL,
                    snapshot_date DATE NOT NULL,
                    snapshot_time TIMESTAMP NOT NULL,
                    balance REAL NOT NULL,
                    available REAL NOT NULL,
                    frozen REAL DEFAULT 0,
                    margin REAL DEFAULT 0,
                    total_pnl REAL DEFAULT 0,
                    daily_pnl REAL DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(portfolio_id, snapshot_date)
                )
            """
            )

            # 告警规则表
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS alert_rules (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    condition TEXT NOT NULL,
                    level TEXT NOT NULL,
                    enabled INTEGER DEFAULT 1,
                    actions TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
            )

            # 告警记录表
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS alert_records (
                    id TEXT PRIMARY KEY,
                    rule_id TEXT,
                    level TEXT NOT NULL,
                    message TEXT NOT NULL,
                    data TEXT,
                    status TEXT DEFAULT 'new',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    acknowledged_at TIMESTAMP,
                    FOREIGN KEY (rule_id) REFERENCES alert_rules(id)
                )
            """
            )

            # 系统配置表
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS system_config (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    type TEXT NOT NULL,
                    description TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
            )

            # 日志表
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS system_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    level TEXT NOT NULL,
                    module TEXT NOT NULL,
                    message TEXT NOT NULL,
                    extra TEXT
                )
            """
            )

            # 创建索引
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_backtest_tasks_status ON backtest_tasks(status)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_strategy_instances_gateway ON strategy_instances(gateway_id)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_alert_records_status ON alert_records(status)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_system_logs_timestamp ON system_logs(timestamp)"
            )
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_system_logs_level ON system_logs(level)")

            # 交易历史表索引
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_trade_history_portfolio ON trade_history(portfolio_id, trade_date)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_trade_history_gateway ON trade_history(gateway_name, trade_date)"
            )

            # 持仓快照表索引
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_position_snapshots_portfolio ON position_snapshots(portfolio_id, snapshot_date)"
            )

            # 账户快照表索引
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_account_snapshots_portfolio ON account_snapshots(portfolio_id, snapshot_date)"
            )

            conn.commit()
            logger.info("数据库表初始化完成")

    @contextmanager
    def get_connection(self):
        """
        获取数据库连接（上下文管理器）

        Yields:
            sqlite3.Connection: 数据库连接
        """
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row  # 使结果可以通过列名访问
        try:
            yield conn
        finally:
            conn.close()

    def execute_query(self, query: str, params: Optional[Tuple] = None) -> List[Dict[str, Any]]:
        """
        执行查询并返回结果

        Args:
            query: SQL查询语句
            params: 查询参数

        Returns:
            查询结果列表
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)

            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def execute_update(self, query: str, params: Optional[Tuple] = None) -> int:
        """
        执行更新操作

        Args:
            query: SQL更新语句
            params: 更新参数

        Returns:
            受影响的行数
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            conn.commit()
            return cursor.rowcount

    def execute_many(self, query: str, params_list: List[Tuple]) -> int:
        """
        批量执行操作

        Args:
            query: SQL语句
            params_list: 参数列表

        Returns:
            受影响的行数
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.executemany(query, params_list)
            conn.commit()
            return cursor.rowcount


# 全局数据库管理器实例
_db_manager: Optional[DatabaseManager] = None


def get_db_manager() -> DatabaseManager:
    """
    获取全局数据库管理器实例（单例模式）

    Returns:
        DatabaseManager: 数据库管理器实例
    """
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager()
    return _db_manager
