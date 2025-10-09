# -*- coding: utf-8 -*-
"""
SQLite数据库管理器

提供统一的SQLite数据库访问接口，基于vnpy_sqlite包。
用于存储配置、交易记录、回测结果等数据。
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    # 类型检查时的导入，避免运行时依赖
    try:
        from vnpy_sqlite import Driver as VnpyDriver  # type: ignore
    except ImportError:
        # 创建一个假的Driver类用于类型检查
        class VnpyDriver:  # type: ignore
            """假的vnpy_sqlite Driver类，用于类型检查"""

            def __init__(self, *args, **kwargs) -> None:  # type: ignore
                """初始化假Driver类。

                Args:
                    *args: 可变位置参数
                    **kwargs: 可变关键字参数
                """
                # 存根方法，不会被实际调用
                _ = args, kwargs  # type: ignore

            def init(self, settings: Dict[str, Any]) -> None:  # type: ignore
                """初始化数据库连接。

                Args:
                    settings: 数据库配置字典
                """
                # 存根方法，不会被实际调用
                _ = settings  # type: ignore

            def execute(self, query: str, params: tuple = ()) -> Any:  # type: ignore
                """执行SQL语句。

                Args:
                    query: SQL查询语句
                    params: 查询参数

                Returns:
                    执行结果
                """
                # 存根方法，不会被实际调用
                _ = query, params  # type: ignore

            def fetchone(self, query: str, params: tuple = ()) -> Any:  # type: ignore
                """获取单条记录。

                Args:
                    query: SQL查询语句
                    params: 查询参数

                Returns:
                    单条记录
                """
                # 存根方法，不会被实际调用
                _ = query, params  # type: ignore

            def fetchall(self, query: str, params: tuple = ()) -> Any:  # type: ignore
                """获取所有记录。

                Args:
                    query: SQL查询语句
                    params: 查询参数

                Returns:
                    所有记录列表
                """
                # 存根方法，不会被实际调用
                _ = query, params  # type: ignore

            def close(self) -> None:  # type: ignore
                """关闭数据库连接。"""
                # 存根方法，不会被实际调用
                pass


logger = logging.getLogger(__name__)


class SQLiteManager:
    """SQLite数据库管理器."""

    def __init__(self, db_path: Optional[Path] = None):
        """初始化SQLite管理器.

        Args:
            db_path: 数据库文件路径，默认为data/terminal.db
        """
        if db_path is None:
            # 默认数据库路径
            db_path = Path("data/terminal.db")

        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # 延迟导入vnpy_sqlite，避免启动时强制依赖
        self.database: Any = None  # 类型: sqlite3.Connection or VnpyDriver
        self._initialized = False

        logger.info("SQLite管理器初始化: %s", self.db_path)

    def initialize(self) -> bool:
        """初始化数据库连接.

        Returns:
            是否初始化成功
        """
        if self._initialized:
            return True

        try:
            # 导入vnpy_sqlite
            from vnpy_sqlite import Driver as SQLiteDriver  # type: ignore

            # 创建数据库驱动
            self.database = SQLiteDriver()

            # 初始化数据库
            settings = {
                "database": str(self.db_path),
            }
            self.database.init(settings)

            # 创建表结构
            self._create_tables()

            self._initialized = True
            logger.info("✅ SQLite数据库初始化成功")
            return True

        except ImportError:
            logger.warning("⚠️ vnpy_sqlite未安装，SQLite功能不可用")
            logger.warning("   请安装: pip install git+https://github.com/vnpy/vnpy_sqlite.git")
            return False
        except Exception as e:
            logger.error("❌ SQLite数据库初始化失败: %s", e, exc_info=True)
            return False

    def _create_tables(self):
        """创建数据表结构."""
        if not self.database or not self._initialized:
            return

        try:
            # 配置表
            self.database.execute(
                """
                CREATE TABLE IF NOT EXISTS configs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    module TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    description TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(module, key)
                )
            """
            )

            # 交易记录表
            self.database.execute(
                """
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    gateway_name TEXT NOT NULL,
                    strategy_name TEXT,
                    symbol TEXT NOT NULL,
                    exchange TEXT NOT NULL,
                    order_id TEXT NOT NULL,
                    trade_id TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    offset TEXT NOT NULL,
                    price REAL NOT NULL,
                    volume REAL NOT NULL,
                    trade_time TIMESTAMP NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(trade_id)
                )
            """
            )

            # 订单记录表
            self.database.execute(
                """
                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    gateway_name TEXT NOT NULL,
                    strategy_name TEXT,
                    symbol TEXT NOT NULL,
                    exchange TEXT NOT NULL,
                    order_id TEXT NOT NULL,
                    type TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    offset TEXT NOT NULL,
                    price REAL NOT NULL,
                    volume REAL NOT NULL,
                    traded REAL DEFAULT 0,
                    status TEXT NOT NULL,
                    order_time TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(order_id)
                )
            """
            )

            # 回测结果表
            self.database.execute(
                """
                CREATE TABLE IF NOT EXISTS backtest_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    strategy_name TEXT NOT NULL,
                    strategy_class TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    start_date TEXT NOT NULL,
                    end_date TEXT NOT NULL,
                    capital REAL NOT NULL,
                    total_return REAL,
                    annual_return REAL,
                    max_drawdown REAL,
                    sharpe_ratio REAL,
                    result_data TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
            )

            # 系统日志表
            self.database.execute(
                """
                CREATE TABLE IF NOT EXISTS system_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    level TEXT NOT NULL,
                    module TEXT NOT NULL,
                    message TEXT NOT NULL,
                    details TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
            )

            # 创建索引
            self.database.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_trades_symbol
                ON trades(symbol, trade_time)
            """
            )

            self.database.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_orders_symbol
                ON orders(symbol, order_time)
            """
            )

            self.database.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_backtest_strategy
                ON backtest_results(strategy_name, created_at)
            """
            )

            logger.info("✅ 数据表结构创建完成")

        except Exception as e:
            logger.error("创建数据表失败: %s", e, exc_info=True)

    # ========== 配置管理 ==========

    def save_config(self, module: str, key: str, value: str, description: str = "") -> bool:
        """保存配置.

        Args:
            module: 模块名称
            key: 配置键
            value: 配置值
            description: 配置说明

        Returns:
            是否保存成功
        """
        if not self._initialized or not self.database:
            return False

        try:
            self.database.execute(
                """
                INSERT OR REPLACE INTO configs (module, key, value, description, updated_at)
                VALUES (?, ?, ?, ?, ?)
            """,
                (module, key, value, description, datetime.now()),
            )

            return True
        except Exception as e:
            logger.error("保存配置失败: %s", e)
            return False

    def get_config(self, module: str, key: str, default: str = "") -> str:
        """获取配置.

        Args:
            module: 模块名称
            key: 配置键
            default: 默认值

        Returns:
            配置值
        """
        if not self._initialized or not self.database:
            return default

        try:
            result = self.database.fetchone(
                """
                SELECT value FROM configs WHERE module = ? AND key = ?
            """,
                (module, key),
            )

            return result[0] if result else default
        except Exception as e:
            logger.error("获取配置失败: %s", e)
            return default

    def get_module_configs(self, module: str) -> Dict[str, str]:
        """获取模块所有配置.

        Args:
            module: 模块名称

        Returns:
            配置字典
        """
        if not self._initialized or not self.database:
            return {}

        try:
            results = self.database.fetchall(
                """
                SELECT key, value FROM configs WHERE module = ?
            """,
                (module,),
            )

            return {row[0]: row[1] for row in results}
        except Exception as e:
            logger.error("获取模块配置失败: %s", e)
            return {}

    # ========== 交易记录管理 ==========

    def save_trade(self, trade_data: Dict[str, Any]) -> bool:
        """保存交易记录.

        Args:
            trade_data: 交易数据

        Returns:
            是否保存成功
        """
        if not self._initialized or not self.database:
            return False

        try:
            self.database.execute(
                """
                INSERT OR IGNORE INTO trades
                (gateway_name, strategy_name, symbol, exchange, order_id, trade_id,
                 direction, offset, price, volume, trade_time)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    trade_data.get("gateway_name", ""),
                    trade_data.get("strategy_name", ""),
                    trade_data.get("symbol", ""),
                    trade_data.get("exchange", ""),
                    trade_data.get("order_id", ""),
                    trade_data.get("trade_id", ""),
                    trade_data.get("direction", ""),
                    trade_data.get("offset", ""),
                    trade_data.get("price", 0.0),
                    trade_data.get("volume", 0.0),
                    trade_data.get("trade_time", datetime.now()),
                ),
            )

            return True
        except Exception as e:
            logger.error("保存交易记录失败: %s", e)
            return False

    def get_trades(
        self,
        symbol: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 1000,
    ) -> List[Dict[str, Any]]:
        """查询交易记录.

        Args:
            symbol: 品种代码
            start_time: 开始时间
            end_time: 结束时间
            limit: 限制数量

        Returns:
            交易记录列表
        """
        if not self._initialized or not self.database:
            return []

        try:
            query = "SELECT * FROM trades WHERE 1=1"
            params: List[Any] = []

            if symbol:
                query += " AND symbol = ?"
                params.append(symbol)
            if start_time:
                query += " AND trade_time >= ?"
                params.append(start_time)
            if end_time:
                query += " AND trade_time <= ?"
                params.append(end_time)

            query += " ORDER BY trade_time DESC LIMIT ?"
            params.append(limit)

            results = self.database.fetchall(query, tuple(params))

            # 转换为字典列表
            trades = []
            for row in results:
                trades.append(
                    {
                        "id": row[0],
                        "gateway_name": row[1],
                        "strategy_name": row[2],
                        "symbol": row[3],
                        "exchange": row[4],
                        "order_id": row[5],
                        "trade_id": row[6],
                        "direction": row[7],
                        "offset": row[8],
                        "price": row[9],
                        "volume": row[10],
                        "trade_time": row[11],
                    }
                )

            return trades
        except Exception as e:
            logger.error("查询交易记录失败: %s", e)
            return []

    # ========== 回测结果管理 ==========

    def save_backtest_result(self, result_data: Dict[str, Any]) -> bool:
        """保存回测结果.

        Args:
            result_data: 回测结果数据

        Returns:
            是否保存成功
        """
        if not self._initialized or not self.database:
            return False

        try:
            import json

            self.database.execute(
                """
                INSERT INTO backtest_results
                (strategy_name, strategy_class, symbol, start_date, end_date,
                 capital, total_return, annual_return, max_drawdown, sharpe_ratio, result_data)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    result_data.get("strategy_name", ""),
                    result_data.get("strategy_class", ""),
                    result_data.get("symbol", ""),
                    result_data.get("start_date", ""),
                    result_data.get("end_date", ""),
                    result_data.get("capital", 0.0),
                    result_data.get("total_return", 0.0),
                    result_data.get("annual_return", 0.0),
                    result_data.get("max_drawdown", 0.0),
                    result_data.get("sharpe_ratio", 0.0),
                    json.dumps(result_data.get("details", {})),
                ),
            )

            return True
        except Exception as e:
            logger.error("保存回测结果失败: %s", e)
            return False

    def get_backtest_results(
        self, strategy_name: Optional[str] = None, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """查询回测结果.

        Args:
            strategy_name: 策略名称
            limit: 限制数量

        Returns:
            回测结果列表
        """
        if not self._initialized or not self.database:
            return []

        try:
            query = "SELECT * FROM backtest_results WHERE 1=1"
            params: List[Any] = []

            if strategy_name:
                query += " AND strategy_name = ?"
                params.append(strategy_name)

            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)

            results = self.database.fetchall(query, tuple(params))

            # 转换为字典列表
            backtests = []
            for row in results:
                backtests.append(
                    {
                        "id": row[0],
                        "strategy_name": row[1],
                        "strategy_class": row[2],
                        "symbol": row[3],
                        "start_date": row[4],
                        "end_date": row[5],
                        "capital": row[6],
                        "total_return": row[7],
                        "annual_return": row[8],
                        "max_drawdown": row[9],
                        "sharpe_ratio": row[10],
                        "created_at": row[12],
                    }
                )

            return backtests
        except Exception as e:
            logger.error("查询回测结果失败: %s", e)
            return []

    # ========== 系统日志管理 ==========

    def save_log(self, level: str, module: str, message: str, details: str = "") -> bool:
        """保存系统日志.

        Args:
            level: 日志级别
            module: 模块名称
            message: 日志消息
            details: 详细信息

        Returns:
            是否保存成功
        """
        if not self._initialized or not self.database:
            return False

        try:
            self.database.execute(
                """
                INSERT INTO system_logs (level, module, message, details)
                VALUES (?, ?, ?, ?)
            """,
                (level, module, message, details),
            )

            return True
        except Exception as e:
            logger.error("保存日志失败: %s", e)
            return False

    # ========== 通用方法 ==========

    def close(self):
        """关闭数据库连接."""
        if self.database and self._initialized:
            try:
                self.database.close()
                logger.info("SQLite数据库连接已关闭")
            except Exception as e:
                logger.error("关闭数据库连接失败: %s", e)

        self._initialized = False


def get_sqlite_manager() -> SQLiteManager:
    """获取SQLite管理器单例.

    Returns:
        SQLite管理器实例
    """
    # 使用函数级变量，避免global语句
    if "_sqlite_manager" not in locals():
        locals()["_sqlite_manager"] = None

    if locals()["_sqlite_manager"] is None:
        locals()["_sqlite_manager"] = SQLiteManager()
        locals()["_sqlite_manager"].initialize()

    return locals()["_sqlite_manager"]
