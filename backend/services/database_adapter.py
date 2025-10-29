# -*- coding: utf-8 -*-
"""
统一数据库管理模块 - 合并版本.

整合了以下模块:
- database.py: DatabaseManager类 (直接SQLite3操作)
- sqlite_manager.py: SQLiteManager类 (基于vnpy_sqlite的封装)

提供两种数据库访问方式:
1. DatabaseManager - 使用标准sqlite3库，适用于通用场景
2. SQLiteManager - 使用vnpy_sqlite包，适用于vnpy集成场景
"""

import json
import logging
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    # 类型检查时的导入，避免运行时依赖
    try:
        from vnpy_sqlite import Driver as VnpyDriver  # type: ignore
    except ImportError:
        # 创建一个假的Driver类用于类型检查
        class VnpyDriver:  # type: ignore
            """假的vnpy_sqlite Driver类，用于类型检查"""

            def __init__(self, *args, **kwargs) -> None:  # type: ignore
                _ = args, kwargs  # type: ignore

            def init(self, settings: Dict[str, Any]) -> None:  # type: ignore
                _ = settings  # type: ignore

            def execute(self, query: str, params: tuple = ()) -> Any:  # type: ignore
                _ = query, params  # type: ignore

            def fetchone(self, query: str, params: tuple = ()) -> Any:  # type: ignore
                _ = query, params  # type: ignore

            def fetchall(self, query: str, params: tuple = ()) -> Any:  # type: ignore
                _ = query, params  # type: ignore

            def close(self) -> None:  # type: ignore
                pass


logger = logging.getLogger(__name__)

# 专用logger - 日志埋点v4.0
logger_alert = logging.getLogger("backend.database.alert")


# =============================================================================
# Part 1: DatabaseManager类（基于标准sqlite3）
# =============================================================================


class DatabaseManager:
    """
    数据库管理器（标准sqlite3）.

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

        # ✅ 连接池优化：使用共享连接，启用WAL模式
        self._connection: Optional[sqlite3.Connection] = None
        self._connection_lock = threading.Lock()
        self._initialize_connection()

        # 初始化数据库表
        self._init_tables()

    def _initialize_connection(self) -> None:
        """初始化共享连接并启用WAL模式."""
        self._connection = sqlite3.connect(
            str(self.db_path),
            check_same_thread=False,  # 允许多线程共享连接
            timeout=30.0,  # 增加锁超时到30秒
        )
        self._connection.row_factory = sqlite3.Row

        # ✅ 启用WAL模式：允许并发读写，避免锁竞争
        self._connection.execute("PRAGMA journal_mode=WAL")
        # ✅ 同步模式优化：NORMAL模式在WAL下安全且快速
        self._connection.execute("PRAGMA synchronous=NORMAL")
        # ✅ 增加缓存大小：减少磁盘I/O
        self._connection.execute("PRAGMA cache_size=10000")

        logger.info("✅ 数据库连接池已初始化：WAL模式，共享连接")

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

            # 下载历史表
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS download_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    start_time TIMESTAMP NOT NULL,
                    end_time TIMESTAMP NOT NULL,
                    duration REAL NOT NULL,
                    status TEXT NOT NULL,
                    total_tasks INTEGER DEFAULT 0,
                    completed_tasks INTEGER DEFAULT 0,
                    success_count INTEGER DEFAULT 0,
                    failed_count INTEGER DEFAULT 0,
                    skipped_count INTEGER DEFAULT 0,
                    start_date TEXT,
                    message TEXT,
                    log_text TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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

            # 🔧 关键修复：为timestamp创建降序索引，优化日志查询性能
            # 避免ORDER BY timestamp DESC时全表扫描，防止UI卡死
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_system_logs_timestamp
                ON system_logs(timestamp DESC)
            """
            )

            # 监控数据历史表（每5分钟一条记录）
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS monitoring_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TIMESTAMP NOT NULL,
                    metric_type TEXT NOT NULL,
                    metric_name TEXT NOT NULL,
                    value REAL NOT NULL,
                    unit TEXT,
                    metadata TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
            )

            # 自适应阈值学习数据表
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS adaptive_thresholds (
                    metric_name TEXT PRIMARY KEY,
                    mean REAL,
                    stddev REAL,
                    p95 REAL,
                    p99 REAL,
                    sample_count INTEGER,
                    last_updated TIMESTAMP,
                    threshold_warning REAL,
                    threshold_critical REAL
                )
            """
            )

            # 本地数据索引表（用于追踪已下载的品种）
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS local_data_index (
                    symbol TEXT PRIMARY KEY,
                    updated_at TEXT
                )
            """
            )

            # 失效品种表（用于追踪不再有效的品种）
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS invalid_symbols (
                    symbol TEXT PRIMARY KEY,
                    reason TEXT,
                    detected_at TEXT
                )
            """
            )

            # 硬盘SMART历史表
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS smart_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    disk_name TEXT NOT NULL,
                    timestamp TIMESTAMP NOT NULL,
                    smart_data TEXT NOT NULL,
                    health_status TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_monitoring_history_timestamp ON monitoring_history(timestamp)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_monitoring_history_metric ON monitoring_history(metric_name)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_smart_history_disk ON smart_history(disk_name)"
            )

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

            # 下载历史表索引
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_download_history_task_id ON download_history(task_id)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_download_history_start_time ON download_history(start_time DESC)"
            )

            # 财务信息表（存储完整33字段财务数据，替代JSON ipo_dates.json）
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS finance_info (
                    symbol TEXT PRIMARY KEY,
                    market INTEGER NOT NULL,

                    -- 基础信息
                    industry INTEGER,
                    province INTEGER,
                    updated_date INTEGER,
                    ipo_date INTEGER,

                    -- 股本结构（万股）
                    liutongguben REAL,
                    zongguben REAL,
                    guojiagu REAL,
                    faqirenfarengu REAL,
                    farengu REAL,
                    bgu REAL,
                    hgu REAL,
                    zhigonggu REAL,
                    gudongrenshu REAL,

                    -- 资产负债（万元）
                    zongzichan REAL,
                    liudongzichan REAL,
                    gudingzichan REAL,
                    wuxingzichan REAL,
                    liudongfuzhai REAL,
                    changqifuzhai REAL,
                    zibengongjijin REAL,
                    jingzichan REAL,

                    -- 经营成果（万元）
                    zhuyingshouru REAL,
                    zhuyinglirun REAL,
                    yingshouzhangkuan REAL,
                    yingyelirun REAL,
                    touzishouyu REAL,
                    lirunzonghe REAL,
                    shuihoulirun REAL,
                    jinglirun REAL,
                    weifenpeilirun REAL,
                    cunhuo REAL,

                    -- 现金流量（万元）
                    jingyingxianjinliu REAL,
                    zongxianjinliu REAL,

                    -- 财务指标
                    meigujingzichan REAL,

                    -- 元数据
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
            )

            # 财务信息表索引
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_finance_ipo_date ON finance_info(ipo_date)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_finance_industry ON finance_info(industry)"
            )
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_finance_market ON finance_info(market)")

            conn.commit()
            logger.info("数据库表初始化完成")

    def close(self) -> None:
        """关闭数据库连接（程序退出时调用）."""
        with self._connection_lock:
            if self._connection:
                try:
                    self._connection.close()
                    logger.info("✅ 数据库连接已关闭")
                except Exception as e:
                    logger.warning("关闭数据库连接时出错：%s", e)
                finally:
                    self._connection = None

    def __del__(self):
        """析构函数：确保连接被关闭."""
        self.close()

    @contextmanager
    def get_connection(self):
        """
        获取数据库连接（上下文管理器）

        ✅ 优化：使用共享连接+线程锁，避免频繁创建连接导致的锁竞争

        Yields:
            sqlite3.Connection: 数据库连接
        """
        with self._connection_lock:
            # 检查连接是否有效
            if self._connection is None:
                self._initialize_connection()

            try:
                # 验证连接有效性
                if self._connection:
                    self._connection.execute("SELECT 1")
            except (sqlite3.ProgrammingError, sqlite3.OperationalError):
                # 连接失效，重新初始化
                self._initialize_connection()

            # 断言连接不为None（类型检查）
            assert self._connection is not None
            yield self._connection
            # ✅ 不关闭连接，保持连接池

    def execute_query(self, query: str, params: Optional[Tuple] = None) -> List[Dict[str, Any]]:
        """
        执行查询并返回结果

        Args:
            query: SQL查询语句
            params: 查询参数

        Returns:
            查询结果列表
        """
        # 慢查询监控 - 日志埋点v4.0
        import time

        start_time = time.time()

        with self.get_connection() as conn:
            cursor = conn.cursor()
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)

            rows = cursor.fetchall()
            result = [dict(row) for row in rows]

        # 慢查询告警 - 日志埋点v4.0
        elapsed = time.time() - start_time
        if elapsed > 1.0:  # 超过1秒的慢查询
            logger_alert.warning(
                "慢查询检测: 耗时=%.2fs, 结果数=%d, SQL=%s", elapsed, len(result), query[:200]
            )

        return result

    def execute_update(self, query: str, params: Optional[Tuple] = None) -> int:
        """
        执行更新操作

        Args:
            query: SQL更新语句
            params: 更新参数

        Returns:
            受影响的行数
        """
        # 慢查询监控 - 日志埋点v4.0
        import time

        start_time = time.time()

        with self.get_connection() as conn:
            cursor = conn.cursor()
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            conn.commit()
            rowcount = cursor.rowcount

        # 慢查询告警 - 日志埋点v4.0
        elapsed = time.time() - start_time
        if elapsed > 1.0:  # 超过1秒的慢查询
            logger_alert.warning(
                "慢更新检测: 耗时=%.2fs, 影响行数=%d, SQL=%s", elapsed, rowcount, query[:200]
            )

        return rowcount

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

    # ========== 下载历史管理 ==========

    def save_download_history(self, history_data: Dict[str, Any]) -> bool:
        """
        保存下载历史记录

        Args:
            history_data: 历史数据字典

        Returns:
            是否保存成功
        """
        try:
            query = """
                INSERT INTO download_history (
                    task_id, start_time, end_time, duration, status,
                    total_tasks, completed_tasks, success_count,
                    failed_count, skipped_count, start_date, message, log_text
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            params = (
                history_data.get("task_id", ""),
                history_data.get("start_time"),
                history_data.get("end_time"),
                history_data.get("duration", 0.0),
                history_data.get("status", "unknown"),
                history_data.get("total_tasks", 0),
                history_data.get("completed_tasks", 0),
                history_data.get("success_count", 0),
                history_data.get("failed_count", 0),
                history_data.get("skipped_count", 0),
                history_data.get("start_date", ""),
                history_data.get("message", ""),
                history_data.get("log_text", ""),
            )
            self.execute_update(query, params)
            logger.info("下载历史记录已保存：%s", history_data.get("task_id"))
            return True
        except Exception as e:
            logger.error("保存下载历史失败：%s", e, exc_info=True)
            return False

    def get_download_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        """
        获取下载历史记录

        Args:
            limit: 限制数量（默认20条）

        Returns:
            历史记录列表
        """
        try:
            query = """
                SELECT id, task_id, start_time, end_time, duration, status,
                       total_tasks, completed_tasks, success_count, failed_count,
                       skipped_count, start_date, message, log_text, created_at
                FROM download_history
                ORDER BY start_time DESC
                LIMIT ?
            """
            results = self.execute_query(query, (limit,))
            return results
        except Exception as e:
            logger.error("获取下载历史失败：%s", e, exc_info=True)
            return []

    def delete_download_history(self, record_id: int) -> bool:
        """
        删除下载历史记录

        Args:
            record_id: 记录ID

        Returns:
            是否删除成功
        """
        try:
            query = "DELETE FROM download_history WHERE id = ?"
            self.execute_update(query, (record_id,))
            logger.info("下载历史记录已删除：ID=%d", record_id)
            return True
        except Exception as e:
            logger.error("删除下载历史失败：%s", e, exc_info=True)
            return False

    def cleanup_old_download_history(self, keep_count: int = 20) -> int:
        """
        清理旧的下载历史记录，只保留最近的N条

        Args:
            keep_count: 保留数量（默认20条）

        Returns:
            删除的记录数
        """
        try:
            # 删除超出保留数量的旧记录
            query = """
                DELETE FROM download_history
                WHERE id NOT IN (
                    SELECT id FROM download_history
                    ORDER BY start_time DESC
                    LIMIT ?
                )
            """
            count = self.execute_update(query, (keep_count,))
            if count > 0:
                logger.info("清理旧下载历史：删除了 %d 条记录", count)
            return count
        except Exception as e:
            logger.error("清理旧下载历史失败：%s", e, exc_info=True)
            return 0

    # ========== 本地数据索引管理 ==========

    def upsert_local_data_index(self, symbols: List[str]) -> bool:
        """
        批量更新本地数据索引

        Args:
            symbols: 品种代码列表

        Returns:
            是否成功
        """
        try:
            from datetime import datetime

            updated_at = datetime.now().isoformat()

            query = "INSERT OR REPLACE INTO local_data_index (symbol, updated_at) VALUES (?, ?)"
            params_list = [(symbol, updated_at) for symbol in symbols]

            self.execute_many(query, params_list)
            logger.info("本地数据索引已更新：%d 个品种", len(symbols))
            return True
        except Exception as e:
            logger.error("更新本地数据索引失败：%s", e, exc_info=True)
            return False

    def get_local_data_index(self) -> List[str]:
        """
        获取本地数据索引

        Returns:
            品种代码列表
        """
        try:
            query = "SELECT symbol FROM local_data_index ORDER BY symbol"
            results = self.execute_query(query)
            return [row["symbol"] for row in results]
        except Exception as e:
            logger.error("获取本地数据索引失败：%s", e, exc_info=True)
            return []

    # ========== 失效品种管理 ==========

    def upsert_invalid_symbols(self, symbols: List[str], reason: str = "not_in_reference") -> bool:
        """
        批量更新失效品种池

        Args:
            symbols: 失效品种代码列表
            reason: 失效原因

        Returns:
            是否成功
        """
        try:
            from datetime import datetime

            detected_at = datetime.now().isoformat()

            # 先清空旧数据，再写入新数据
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM invalid_symbols")
                conn.commit()

            if symbols:
                query = "INSERT INTO invalid_symbols (symbol, reason, detected_at) VALUES (?, ?, ?)"
                params_list = [(symbol, reason, detected_at) for symbol in symbols]
                self.execute_many(query, params_list)

            logger.info("失效品种池已更新：%d 个品种", len(symbols))
            return True
        except Exception as e:
            logger.error("更新失效品种池失败：%s", e, exc_info=True)
            return False

    def get_invalid_symbols(self) -> List[str]:
        """
        获取失效品种列表

        Returns:
            失效品种代码列表
        """
        try:
            query = "SELECT symbol FROM invalid_symbols ORDER BY symbol"
            results = self.execute_query(query)
            return [row["symbol"] for row in results]
        except Exception as e:
            logger.error("获取失效品种列表失败：%s", e, exc_info=True)
            return []

    def clear_invalid_symbols(self) -> bool:
        """
        清空失效品种池

        Returns:
            是否成功
        """
        try:
            query = "DELETE FROM invalid_symbols"
            self.execute_update(query)
            logger.info("失效品种池已清空")
            return True
        except Exception as e:
            logger.error("清空失效品种池失败：%s", e, exc_info=True)
            return False


# =============================================================================
# Part 2: SQLiteManager类（基于vnpy_sqlite）
# =============================================================================


class SQLiteManager:
    """SQLite数据库管理器（vnpy_sqlite集成）."""

    def __init__(self, db_path: Optional[Path] = None):
        """初始化SQLite管理器.

        Args:
            db_path: 数据库文件路径，默认为data/terminal.db
        """
        if db_path is None:
            # 默认数据库路径（使用绝对路径）
            from backend.infrastructure.data_module_vnpy.data_module import config_manager

            db_path = config_manager.get_db_file()

        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # 延迟导入vnpy_sqlite，避免启动时强制依赖
        self.database: Any = None  # 类型: sqlite3.Connection or VnpyDriver
        self._initialized = False

        logger.info("SQLite管理器初始化：%s", self.db_path)

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
            logger.error("❌ SQLite数据库初始化失败：%s", e, exc_info=True)
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
            logger.error("创建数据表失败：%s", e, exc_info=True)

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
            logger.error("保存配置失败：%s", e)
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
            logger.error("获取配置失败：%s", e)
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
            logger.error("获取模块配置失败：%s", e)
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
            logger.error("保存交易记录失败：%s", e)
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
            logger.error("查询交易记录失败：%s", e)
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
            logger.error("保存回测结果失败：%s", e)
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
            logger.error("查询回测结果失败：%s", e)
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
            logger.error("保存日志失败：%s", e)
            return False

    # ========== 通用方法 ==========

    def close(self):
        """关闭数据库连接."""
        if self.database and self._initialized:
            try:
                self.database.close()
                logger.info("SQLite数据库连接已关闭")
            except Exception as e:
                logger.error("关闭数据库连接失败：%s", e)

        self._initialized = False


# =============================================================================
# Part 3: 统一工厂函数
# =============================================================================

# 全局数据库管理器实例
_db_manager: Optional[DatabaseManager] = None
_sqlite_manager: Optional[SQLiteManager] = None


def get_db_manager() -> DatabaseManager:
    """
    获取全局数据库管理器实例（单例模式）

    Returns:
        DatabaseManager: 数据库管理器实例（标准sqlite3）
    """
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager()
    return _db_manager


def get_sqlite_manager() -> SQLiteManager:
    """获取SQLite管理器单例.

    Returns:
        SQLite管理器实例（vnpy_sqlite集成）
    """
    global _sqlite_manager
    if _sqlite_manager is None:
        _sqlite_manager = SQLiteManager()
        _sqlite_manager.initialize()
    return _sqlite_manager


def get_database_manager(use_vnpy: bool = False) -> Any:
    """获取数据库管理器（统一入口）.

    Args:
        use_vnpy: 是否使用vnpy_sqlite，默认False使用标准sqlite3

    Returns:
        数据库管理器实例
    """
    if use_vnpy:
        return get_sqlite_manager()
    else:
        return get_db_manager()


__all__ = [
    "DatabaseManager",
    "SQLiteManager",
    "get_db_manager",
    "get_sqlite_manager",
    "get_database_manager",
]
