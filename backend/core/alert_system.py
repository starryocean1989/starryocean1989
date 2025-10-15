# -*- coding: utf-8 -*-
"""
扩展告警系统.

在现有 AlertEngine 基础上，增加日志告警功能，实现日志监控和告警推送。
"""

import json
import sqlite3
import threading
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from backend.core.utils import (
    Alert,
    AlertEngine,
    AlertRule,
    AlertSeverity,
    AlertStatus,
    EVENT_ALERT_CREATED,
    EVENT_ALERT_UPDATED,
)


class LogAlertRule(AlertRule):
    """日志告警规则.

    监听指定级别的日志记录，触发告警。
    """

    def __init__(
        self,
        rule_id: str,
        name: str,
        log_levels: List[str] = None,
        modules: List[str] = None,
        keywords: List[str] = None,
        severity: AlertSeverity = AlertSeverity.ERROR,
        enabled: bool = True,
        priority: int = 0,
        group: str = "log_monitoring",
        description: str = "",
        suppression_window: int = 300,  # 5分钟抑制窗口
    ):
        """初始化日志告警规则.

        Args:
            rule_id: 规则ID
            name: 规则名称
            log_levels: 要监控的日志级别列表 ['ERROR', 'CRITICAL']
            modules: 要监控的模块列表 ['data_center', 'trading_gateway']
            keywords: 要监控的关键字列表 ['连接失败', '异常']
            severity: 告警严重程度
            enabled: 是否启用
            priority: 优先级
            group: 规则分组
            description: 描述
            suppression_window: 抑制窗口（秒）
        """
        # 创建条件表达式
        conditions = []

        if log_levels:
            level_condition = " or ".join([f"level == '{level}'" for level in log_levels])
            conditions.append(f"({level_condition})")

        if modules:
            module_condition = " or ".join([f"module == '{module}'" for module in modules])
            conditions.append(f"({module_condition})")

        if keywords:
            keyword_condition = " or ".join([f"'{keyword}' in message" for keyword in keywords])
            conditions.append(f"({keyword_condition})")

        # 如果没有指定条件，默认监控所有ERROR和CRITICAL
        if not conditions:
            conditions.append("(level == 'ERROR' or level == 'CRITICAL')")

        condition = " and ".join(conditions)

        super().__init__(
            rule_id=rule_id,
            name=name,
            condition=condition,
            severity=severity,
            enabled=enabled,
            priority=priority,
            group=group,
            description=description,
        )

        # 日志告警特有属性
        self.log_levels = log_levels or ['ERROR', 'CRITICAL']
        self.modules = modules or []
        self.keywords = keywords or []
        self.suppression_window = suppression_window

        # 抑制跟踪
        self._last_trigger_times: Dict[str, datetime] = {}

    def evaluate_log_record(self, log_data: Dict[str, Any]) -> bool:
        """评估日志记录是否触发告警.

        Args:
            log_data: 日志数据

        Returns:
            是否触发告警
        """
        if not self.enabled:
            return False

        try:
            # 检查日志级别
            if self.log_levels and log_data.get('level') not in self.log_levels:
                return False

            # 检查模块
            if self.modules and log_data.get('module') not in self.modules:
                return False

            # 检查关键字
            if self.keywords:
                message = log_data.get('message', '').lower()
                if not any(keyword.lower() in message for keyword in self.keywords):
                    return False

            # 检查抑制窗口
            suppression_key = f"{self.rule_id}:{log_data.get('module', '')}:{log_data.get('level', '')}"
            if suppression_key in self._last_trigger_times:
                last_time = self._last_trigger_times[suppression_key]
                if datetime.now() - last_time < timedelta(seconds=self.suppression_window):
                    return False

            # 更新抑制时间
            self._last_trigger_times[suppression_key] = datetime.now()

            return True

        except Exception as e:
            print(f"日志告警规则评估失败 {self.name}: {e}")
            return False


class AlertDatabase:
    """告警数据库管理器.

    提供告警记录的持久化存储和查询功能。
    """

    def __init__(self, db_path: str = "data/alerts.db"):
        """初始化告警数据库.

        Args:
            db_path: 数据库文件路径
        """
        self.db_path = db_path
        self._lock = threading.Lock()

        # 确保数据库目录存在
        from pathlib import Path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        # 初始化数据库
        self._init_database()

    def _init_database(self) -> None:
        """初始化数据库表结构."""
        import time
        db_init_start = time.time()

        print(f"[DEBUG] 初始化告警数据库: {self.db_path}")

        try:
            # 使用更长的超时时间防止阻塞
            print(f"[DEBUG] 连接告警数据库，timeout=30.0s...")
            conn_start = time.time()
            with sqlite3.connect(self.db_path, timeout=30.0) as conn:
                conn_end = time.time()
                print(f"[DEBUG] 告警数据库连接成功，耗时: {conn_end - conn_start:.3f}s")

                print(f"[DEBUG] 创建告警表结构...")
                table_start = time.time()
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS alerts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        alert_id TEXT UNIQUE NOT NULL,
                        rule_id TEXT NOT NULL,
                        rule_name TEXT,
                        severity TEXT NOT NULL,
                        status TEXT NOT NULL,
                        message TEXT NOT NULL,
                        context TEXT,
                        source_type TEXT DEFAULT 'log',
                        source_data TEXT,
                        created_at REAL NOT NULL,
                        updated_at REAL NOT NULL,
                        acknowledged_at REAL,
                        resolved_at REAL,
                        notes TEXT
                    )
                """)
                table_end = time.time()
                print(f"[DEBUG] 告警表创建完成，耗时: {table_end - table_start:.3f}s")

                # 创建索引
                print(f"[DEBUG] 创建告警索引...")
                index_start = time.time()
                conn.execute("CREATE INDEX IF NOT EXISTS idx_alerts_status ON alerts(status)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_alerts_severity ON alerts(severity)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_alerts_created_at ON alerts(created_at)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_alerts_rule_id ON alerts(rule_id)")
                index_end = time.time()
                print(f"[DEBUG] 告警索引创建完成，耗时: {index_end - index_start:.3f}s")

                print(f"[DEBUG] 提交告警数据库事务...")
                commit_start = time.time()
                conn.commit()
                commit_end = time.time()
                print(f"[DEBUG] 告警数据库事务提交完成，耗时: {commit_end - commit_start:.3f}s")

            db_init_end = time.time()
            total_time = db_init_end - db_init_start
            print(f"[DEBUG] ✅ 告警数据库初始化完成，总耗时: {total_time:.3f}s")

        except Exception as e:
            db_init_end = time.time()
            total_time = db_init_end - db_init_start
            print(f"[DEBUG] ❌ 告警数据库初始化失败，耗时: {total_time:.3f}s，错误: {e}")
            raise

    def save_alert(self, alert: Alert) -> None:
        """保存告警记录.

        Args:
            alert: 告警对象
        """
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    conn.execute("""
                        INSERT OR REPLACE INTO alerts
                        (alert_id, rule_id, rule_name, severity, status, message, context,
                         source_type, source_data, created_at, updated_at, acknowledged_at,
                         resolved_at, notes)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        alert.alert_id,
                        alert.rule.rule_id,
                        alert.rule.name,
                        alert.severity.value,
                        alert.status.value,
                        alert.message,
                        json.dumps(alert.context) if alert.context else None,
                        getattr(alert, 'source_type', 'log'),
                        getattr(alert, 'source_data', None),
                        alert.created_at.timestamp(),
                        alert.updated_at.timestamp(),
                        alert.acknowledged_at.timestamp() if alert.acknowledged_at else None,
                        alert.resolved_at.timestamp() if alert.resolved_at else None,
                        json.dumps(alert.notes) if alert.notes else None,
                    ))
                    conn.commit()

        except Exception as e:
            print(f"告警数据库保存失败: {e}")

    def get_alert(self, alert_id: str) -> Optional[Alert]:
        """获取告警记录.

        Args:
            alert_id: 告警ID

        Returns:
            告警对象或None
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    "SELECT * FROM alerts WHERE alert_id = ?",
                    (alert_id,)
                )

                row = cursor.fetchone()
                if row:
                    return self._row_to_alert(row)

        except Exception as e:
            print(f"获取告警失败: {e}")

        return None

    def get_alerts(
        self,
        status: Optional[str] = None,
        severity: Optional[str] = None,
        rule_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Alert]:
        """查询告警记录.

        Args:
            status: 状态筛选
            severity: 严重程度筛选
            rule_id: 规则ID筛选
            limit: 返回数量限制
            offset: 偏移量

        Returns:
            告警记录列表
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row

                # 构建查询条件
                conditions = []
                params = []

                if status:
                    conditions.append("status = ?")
                    params.append(status)

                if severity:
                    conditions.append("severity = ?")
                    params.append(severity)

                if rule_id:
                    conditions.append("rule_id = ?")
                    params.append(rule_id)

                where_clause = " AND ".join(conditions) if conditions else "1=1"

                # 执行查询
                cursor = conn.execute(f"""
                    SELECT * FROM alerts
                    WHERE {where_clause}
                    ORDER BY created_at DESC
                    LIMIT ? OFFSET ?
                """, params + [limit, offset])

                # 转换结果
                alerts = []
                for row in cursor.fetchall():
                    alert = self._row_to_alert(row)
                    if alert:
                        alerts.append(alert)

                return alerts

        except Exception as e:
            print(f"查询告警失败: {e}")
            return []

    def get_unresolved_alerts(self) -> List[Alert]:
        """获取未解决的告警.

        Returns:
            未解决告警列表
        """
        return self.get_alerts(
            status=AlertStatus.NEW.value,
            limit=1000
        )

    def update_alert_status(self, alert_id: str, status: AlertStatus, note: str = "") -> bool:
        """更新告警状态.

        Args:
            alert_id: 告警ID
            status: 新状态
            note: 备注

        Returns:
            是否更新成功
        """
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    # 更新状态和时间
                    now = datetime.now().timestamp()

                    if status == AlertStatus.ACKNOWLEDGED:
                        conn.execute("""
                            UPDATE alerts
                            SET status = ?, acknowledged_at = ?, updated_at = ?
                            WHERE alert_id = ?
                        """, (status.value, now, now, alert_id))
                    elif status == AlertStatus.RESOLVED:
                        conn.execute("""
                            UPDATE alerts
                            SET status = ?, resolved_at = ?, updated_at = ?
                            WHERE alert_id = ?
                        """, (status.value, now, now, alert_id))
                    else:
                        conn.execute("""
                            UPDATE alerts
                            SET status = ?, updated_at = ?
                            WHERE alert_id = ?
                        """, (status.value, now, alert_id))

                    # 添加备注
                    if note:
                        conn.execute("""
                            UPDATE alerts
                            SET notes = COALESCE(notes, '[]') || ?
                            WHERE alert_id = ?
                        """, (f', "[{status.value}] {note}"', alert_id))

                    conn.commit()
                    return True

        except Exception as e:
            print(f"更新告警状态失败: {e}")
            return False

    def delete_resolved_alerts(self, older_than_days: int = 30) -> int:
        """删除已解决的旧告警.

        Args:
            older_than_days: 超过多少天的已解决告警将被删除

        Returns:
            删除的记录数量
        """
        try:
            cutoff_time = (datetime.now() - timedelta(days=older_than_days)).timestamp()

            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.execute("""
                        DELETE FROM alerts
                        WHERE status = ? AND resolved_at < ?
                    """, (AlertStatus.RESOLVED.value, cutoff_time))

                    deleted_count = cursor.rowcount
                    conn.commit()

                    return deleted_count

        except Exception as e:
            print(f"删除旧告警失败: {e}")
            return 0

    def _row_to_alert(self, row: sqlite3.Row) -> Optional[Alert]:
        """将数据库行转换为Alert对象.

        Args:
            row: 数据库行

        Returns:
            Alert对象或None
        """
        try:
            # 获取规则（需要从AlertEngine获取）
            alert_engine = AlertEngine()
            rule = alert_engine.get_rule(row["rule_id"])

            if not rule:
                # 如果规则不存在，创建一个临时的
                rule = AlertRule(
                    rule_id=row["rule_id"],
                    name=row["rule_name"] or "未知规则",
                    condition="True",  # 不会被评估
                    severity=AlertSeverity(row["severity"]),
                )

            # 创建告警对象
            alert = Alert(
                alert_id=row["alert_id"],
                rule=rule,
                message=row["message"],
                context=json.loads(row["context"]) if row["context"] else {},
            )

            # 设置状态和时间
            alert.status = AlertStatus(row["status"])

            if row["acknowledged_at"]:
                alert.acknowledged_at = datetime.fromtimestamp(row["acknowledged_at"])

            if row["resolved_at"]:
                alert.resolved_at = datetime.fromtimestamp(row["resolved_at"])

            if row["notes"]:
                alert.notes = json.loads(row["notes"])

            return alert

        except Exception as e:
            print(f"转换告警对象失败: {e}")
            return None


class AlertEventPublisher:
    """告警事件发布器.

    监听 AlertEngine 的告警事件，推送到 VnPy EventEngine。
    """

    def __init__(self, event_engine, alert_database: AlertDatabase):
        """初始化告警事件发布器.

        Args:
            event_engine: VnPy事件引擎实例
            alert_database: 告警数据库实例
        """
        self.event_engine = event_engine
        self.alert_database = alert_database

        # 监听 AlertEngine 事件
        self._setup_alert_engine_listeners()

    def _setup_alert_engine_listeners(self) -> None:
        """设置告警引擎事件监听器."""
        try:
            alert_engine = AlertEngine()

            # 使用更安全的方法替换，避免竞态条件
            if hasattr(alert_engine, 'evaluate_rules') and not hasattr(alert_engine, '_original_evaluate_rules'):
                print(f"[DEBUG] 设置告警引擎监听器...")
                original_evaluate_rules = alert_engine.evaluate_rules

                def patched_evaluate_rules(context: Dict[str, Any]) -> List[Alert]:
                    """增强的规则评估函数."""
                    try:
                        triggered_alerts = original_evaluate_rules(context)

                        # 保存新触发的告警
                        for alert in triggered_alerts:
                            # 检查是否为日志告警
                            if hasattr(alert.rule, 'log_levels'):
                                # 设置日志告警特有属性
                                alert.source_type = 'log'
                                alert.source_data = context

                                # 保存到数据库
                                try:
                                    self.alert_database.save_alert(alert)
                                except Exception as e:
                                    print(f"[DEBUG] 保存告警到数据库失败: {e}")

                                # 发布事件
                                try:
                                    self.publish_alert_created(alert)
                                except Exception as e:
                                    print(f"[DEBUG] 发布告警事件失败: {e}")

                        return triggered_alerts
                    except Exception as e:
                        print(f"[DEBUG] 告警规则评估异常: {e}")
                        # 返回空列表而不是抛出异常
                        return []

                # 保存原始方法引用
                alert_engine._original_evaluate_rules = original_evaluate_rules
                # 替换方法
                alert_engine.evaluate_rules = patched_evaluate_rules
                print(f"[DEBUG] 告警引擎监听器设置完成")
            else:
                print(f"[DEBUG] 跳过告警引擎监听器设置（已存在或无方法）")

        except Exception as e:
            print(f"[DEBUG] 设置告警引擎监听器失败: {e}")
            # 不抛出异常，继续初始化

    def publish_alert_created(self, alert: Alert) -> None:
        """发布告警创建事件.

        Args:
            alert: 告警对象
        """
        if not self.event_engine:
            return

        try:
            from vnpy.event import Event

            # 创建事件数据
            event_data = {
                "alert_id": alert.alert_id,
                "rule_id": alert.rule.rule_id,
                "rule_name": alert.rule.name,
                "severity": alert.severity.value,
                "status": alert.status.value,
                "message": alert.message,
                "context": alert.context,
                "created_at": alert.created_at.isoformat(),
                "source_type": getattr(alert, 'source_type', 'unknown'),
            }

            # 创建事件
            event = Event(EVENT_ALERT_CREATED, event_data)

            # 发布事件
            self.event_engine.put(event)

        except Exception as e:
            print(f"发布告警创建事件失败: {e}")

    def publish_alert_updated(self, alert: Alert) -> None:
        """发布告警更新事件.

        Args:
            alert: 告警对象
        """
        if not self.event_engine:
            return

        try:
            from vnpy.event import Event

            # 创建事件数据
            event_data = {
                "alert_id": alert.alert_id,
                "status": alert.status.value,
                "updated_at": alert.updated_at.isoformat(),
                "acknowledged_at": alert.acknowledged_at.isoformat() if alert.acknowledged_at else None,
                "resolved_at": alert.resolved_at.isoformat() if alert.resolved_at else None,
            }

            # 创建事件
            event = Event(EVENT_ALERT_UPDATED, event_data)

            # 发布事件
            self.event_engine.put(event)

        except Exception as e:
            print(f"发布告警更新事件失败: {e}")


# 全局告警数据库实例
_alert_database: Optional[AlertDatabase] = None
_alert_database_lock = threading.Lock()


def get_alert_database() -> AlertDatabase:
    """获取全局告警数据库实例.

    Returns:
        告警数据库实例
    """
    global _alert_database
    if _alert_database is None:
        with _alert_database_lock:
            if _alert_database is None:
                _alert_database = AlertDatabase()
    return _alert_database


def initialize_alert_system(event_engine, config: Optional[Dict[str, Any]] = None) -> bool:
    """初始化扩展告警系统.

    Args:
        event_engine: VnPy事件引擎实例
        config: 配置字典

    Returns:
        是否初始化成功
    """
    try:
        import time
        start_time = time.time()

        print(f"[DEBUG] 开始初始化告警系统... (事件引擎: {event_engine is not None})")

        # 获取配置
        if config is None:
            config = {
                "db_path": "data/alerts.db",
                "suppression_window": 300,
            }

        print(f"[DEBUG] 告警系统配置: {config}")

        # 创建全局告警数据库
        print(f"[DEBUG] 创建 AlertDatabase...")
        db_start = time.time()
        global _alert_database
        with _alert_database_lock:
            _alert_database = AlertDatabase(config.get("db_path", "data/alerts.db"))
        db_end = time.time()
        print(f"[DEBUG] AlertDatabase 创建完成，耗时: {db_end - db_start:.3f}s")

        # 创建告警事件发布器
        print(f"[DEBUG] 创建 AlertEventPublisher...")
        publisher_start = time.time()
        alert_publisher = AlertEventPublisher(event_engine, _alert_database)
        publisher_end = time.time()
        print(f"[DEBUG] AlertEventPublisher 创建完成，耗时: {publisher_end - publisher_start:.3f}s")

        # 创建日志告警规则（延迟到需要时才创建，避免初始化阻塞）
        print(f"[DEBUG] 跳过默认日志告警规则创建，改为延迟初始化")

        total_time = time.time() - start_time
        print(f"[DEBUG] ✅ 扩展告警系统初始化完成，总耗时: {total_time:.3f}s")

        return True

    except Exception as e:
        total_time = time.time() - start_time if 'start_time' in locals() else 0
        print(f"[DEBUG] 💥 初始化扩展告警系统失败，耗时: {total_time:.3f}s，错误: {e}")
        return False


def _create_default_log_alert_rules() -> None:
    """创建默认的日志告警规则."""
    import time

    print(f"[DEBUG] 开始创建默认日志告警规则...")

    try:
        alert_engine = AlertEngine()

        rules_start = time.time()

        # ERROR级别日志告警规则
        print(f"[DEBUG] 创建 ERROR 级别日志告警规则...")
        error_rule_start = time.time()
        error_rule = LogAlertRule(
            rule_id="log_error_monitoring",
            name="ERROR级别日志监控",
            log_levels=["ERROR"],
            severity=AlertSeverity.ERROR,
            description="监控所有ERROR级别日志记录",
            suppression_window=60,  # 1分钟抑制窗口
        )
        alert_engine.add_rule(error_rule)
        error_rule_end = time.time()
        print(f"[DEBUG] ERROR级别规则创建完成，耗时: {error_rule_end - error_rule_start:.3f}s")

        # CRITICAL级别日志告警规则
        print(f"[DEBUG] 创建 CRITICAL 级别日志告警规则...")
        critical_rule_start = time.time()
        critical_rule = LogAlertRule(
            rule_id="log_critical_monitoring",
            name="CRITICAL级别日志监控",
            log_levels=["CRITICAL"],
            severity=AlertSeverity.CRITICAL,
            description="监控所有CRITICAL级别日志记录",
            suppression_window=30,  # 30秒抑制窗口
        )
        alert_engine.add_rule(critical_rule)
        critical_rule_end = time.time()
        print(f"[DEBUG] CRITICAL级别规则创建完成，耗时: {critical_rule_end - critical_rule_start:.3f}s")

        # 连接失败告警规则
        print(f"[DEBUG] 创建连接失败告警规则...")
        connection_rule_start = time.time()
        connection_rule = LogAlertRule(
            rule_id="log_connection_failures",
            name="连接失败监控",
            keywords=["连接失败", "连接超时", "网络错误", "Connection failed", "Connection timeout"],
            severity=AlertSeverity.WARNING,
            description="监控连接相关的错误日志",
            suppression_window=120,  # 2分钟抑制窗口
        )
        alert_engine.add_rule(connection_rule)
        connection_rule_end = time.time()
        print(f"[DEBUG] 连接失败规则创建完成，耗时: {connection_rule_end - connection_rule_start:.3f}s")

        # 数据库错误告警规则
        print(f"[DEBUG] 创建数据库错误告警规则...")
        db_rule_start = time.time()
        db_rule = LogAlertRule(
            rule_id="log_database_errors",
            name="数据库错误监控",
            keywords=["数据库错误", "SQL错误", "连接池", "Database error", "SQL error"],
            severity=AlertSeverity.ERROR,
            description="监控数据库相关的错误日志",
            suppression_window=60,  # 1分钟抑制窗口
        )
        alert_engine.add_rule(db_rule)
        db_rule_end = time.time()
        print(f"[DEBUG] 数据库错误规则创建完成，耗时: {db_rule_end - db_rule_start:.3f}s")

        rules_end = time.time()
        total_time = rules_end - rules_start
        print(f"[DEBUG] ✅ 所有默认日志告警规则创建完成，总耗时: {total_time:.3f}s")

    except Exception as e:
        rules_end = time.time()
        total_time = rules_end - rules_start if 'rules_start' in locals() else 0
        print(f"[DEBUG] ❌ 创建默认日志告警规则失败，耗时: {total_time:.3f}s，错误: {e}")
        raise


def shutdown_alert_system() -> None:
    """关闭扩展告警系统."""
    global _alert_database
    if _alert_database:
        _alert_database = None
        print("扩展告警系统已关闭")
