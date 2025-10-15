# -*- coding: utf-8 -*-
"""
日志/告警进程.

独立进程，负责：
1. 日志聚合（接收所有进程的日志）
2. 日志存储（SQLite）
3. 告警规则检查
4. 告警推送（ZeroMQ PUB）
5. 健康检查响应
"""

import json
import logging
import multiprocessing
import os
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import msgpack
import zmq


class LogAlertProcess:
    """日志/告警进程."""

    def __init__(
        self,
        log_port: int = 5557,
        alert_port: int = 5558,
        health_port: int = 5559,
        db_path: str = "data/logs.db",
        alert_db_path: str = "data/alerts.db",
    ):
        """初始化日志/告警进程.

        Args:
            log_port: 日志接收端口（PULL）
            alert_port: 告警推送端口（PUB）
            health_port: 健康检查端口（REP）
            db_path: 日志数据库路径
            alert_db_path: 告警数据库路径
        """
        self.log_port = log_port
        self.alert_port = alert_port
        self.health_port = health_port
        self.db_path = db_path
        self.alert_db_path = alert_db_path

        # ZeroMQ上下文和套接字
        self.context: Optional[zmq.Context] = None
        self.log_receiver: Optional[zmq.Socket] = None
        self.alert_publisher: Optional[zmq.Socket] = None
        self.health_responder: Optional[zmq.Socket] = None
        self.poller: Optional[zmq.Poller] = None

        # 日志和告警管理器
        self.log_manager = None
        self.alert_engine = None

        # 运行标志
        self.running = False

        # 进程启动时间
        self.start_time = datetime.now()

        # 日志批处理
        self.log_batch: list = []
        self.log_batch_size = 100
        self.last_flush_time = time.time()

        # 性能统计
        self.stats = {
            "logs_received": 0,
            "alerts_triggered": 0,
            "health_checks": 0,
            "errors": 0,
        }

    def run(self) -> None:
        """进程主循环."""
        try:
            print(f"[LogAlert] 日志/告警进程启动中... PID={os.getpid()}")

            # 初始化ZeroMQ
            self._init_zmq()

            # 初始化日志和告警系统
            self._init_logging_and_alert()

            # 主循环
            self.running = True
            print(f"[LogAlert] 日志/告警进程就绪，监听端口: 日志={self.log_port}, 告警={self.alert_port}, 健康={self.health_port}")

            self._main_loop()

        except KeyboardInterrupt:
            print(f"[LogAlert] 接收到中断信号，正在关闭...")
        except Exception as e:
            print(f"[LogAlert] 进程异常: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self._cleanup()

    def _init_zmq(self) -> None:
        """初始化ZeroMQ."""
        self.context = zmq.Context()

        # 日志接收器（PULL）
        self.log_receiver = self.context.socket(zmq.PULL)
        self.log_receiver.bind(f"tcp://127.0.0.1:{self.log_port}")
        self.log_receiver.setsockopt(zmq.RCVTIMEO, 100)  # 100ms超时

        # 告警发布器（PUB）
        self.alert_publisher = self.context.socket(zmq.PUB)
        self.alert_publisher.bind(f"tcp://127.0.0.1:{self.alert_port}")

        # 健康检查响应器（REP）
        self.health_responder = self.context.socket(zmq.REP)
        self.health_responder.bind(f"tcp://127.0.0.1:{self.health_port}")
        self.health_responder.setsockopt(zmq.RCVTIMEO, 100)  # 100ms超时

        # 创建轮询器
        self.poller = zmq.Poller()
        self.poller.register(self.log_receiver, zmq.POLLIN)
        self.poller.register(self.health_responder, zmq.POLLIN)

        print(f"[LogAlert] ZeroMQ初始化完成")

    def _init_logging_and_alert(self) -> None:
        """初始化日志和告警系统."""
        # 添加项目根目录到Python路径
        project_root = str(Path(__file__).parent.parent.parent)
        if project_root not in sys.path:
            sys.path.insert(0, project_root)

        # 初始化日志管理器
        from backend.core.logging_system import LogDatabase, LogManager
        from backend.core.base import get_event_engine

        try:
            event_engine = get_event_engine()

            # 创建日志数据库
            log_db = LogDatabase(self.db_path)

            # 创建日志管理器（不注册处理器，避免递归）
            self.log_manager = LogManager(
                db_path=self.db_path,
                event_engine=event_engine,
                retention_days=30,
            )

            print(f"[LogAlert] 日志管理器初始化完成")
        except Exception as e:
            print(f"[LogAlert] 日志管理器初始化失败: {e}")
            # 降级：不使用日志管理器
            self.log_manager = None

        # 初始化告警引擎
        # 注意：在子进程中，我们不使用AlertEngine单例
        # 而是直接使用LogAlertRule来检测日志告警
        from backend.core.alert_system import LogAlertRule, AlertDatabase
        from backend.core.utils import AlertSeverity

        try:
            # 创建告警数据库（用于存储告警历史）
            self.alert_db = AlertDatabase(self.alert_db_path)

            # 不使用AlertEngine，而是直接管理告警规则
            self.alert_rules = []
            self.alert_engine = None  # 标记为None

            # 加载默认告警规则
            self._load_default_alert_rules()

            print(f"[LogAlert] 告警引擎初始化完成")
        except Exception as e:
            print(f"[LogAlert] 告警引擎初始化失败: {e}")
            # 降级：不使用告警引擎
            self.alert_engine = None

    def _load_default_alert_rules(self) -> None:
        """加载默认告警规则."""
        from backend.core.alert_system import LogAlertRule
        from backend.core.utils import AlertSeverity

        try:
            # 错误日志告警
            error_rule = LogAlertRule(
                rule_id="log_error",
                name="错误日志告警",
                log_levels=["ERROR", "CRITICAL"],
                severity=AlertSeverity.ERROR,
                enabled=True,
                priority=1,
                description="监控ERROR和CRITICAL级别日志",
                suppression_window=300,  # 5分钟抑制
            )
            self.alert_rules.append(error_rule)

            # 数据中心告警
            data_center_rule = LogAlertRule(
                rule_id="data_center_error",
                name="数据中心错误",
                log_levels=["ERROR", "CRITICAL"],
                modules=["data_center_service", "data_module_vnpy"],
                severity=AlertSeverity.CRITICAL,
                enabled=True,
                priority=1,
                description="监控数据中心模块的错误",
                suppression_window=300,
            )
            self.alert_rules.append(data_center_rule)

            # 交易网关告警
            trading_rule = LogAlertRule(
                rule_id="trading_gateway_error",
                name="交易网关错误",
                log_levels=["ERROR", "CRITICAL"],
                modules=["trading_gateway_service"],
                severity=AlertSeverity.CRITICAL,
                enabled=True,
                priority=1,
                description="监控交易网关模块的错误",
                suppression_window=180,  # 3分钟抑制
            )
            self.alert_rules.append(trading_rule)

            print(f"[LogAlert] 默认告警规则已加载（3条规则）")

        except Exception as e:
            print(f"[LogAlert] 加载默认告警规则失败: {e}")

    def _main_loop(self) -> None:
        """主循环."""
        while self.running:
            try:
                # 使用轮询器，避免阻塞
                socks = dict(self.poller.poll(100))  # 100ms超时

                # 处理日志
                if self.log_receiver in socks:
                    self._handle_log()

                # 处理健康检查
                if self.health_responder in socks:
                    self._handle_health_check()

                # 批量刷新日志
                self._flush_logs_if_needed()

            except zmq.Again:
                # 超时，继续循环
                continue
            except Exception as e:
                print(f"[LogAlert] 主循环错误: {e}")
                self.stats["errors"] += 1
                time.sleep(0.1)

    def _handle_log(self) -> None:
        """处理日志条目."""
        try:
            # 接收日志（msgpack序列化）
            data = self.log_receiver.recv(zmq.NOBLOCK)
            log_entry = msgpack.unpackb(data, raw=False)

            self.stats["logs_received"] += 1

            # 添加到批处理队列
            self.log_batch.append(log_entry)

            # 如果有告警引擎，检查告警规则
            if self.alert_engine:
                self._check_log_alert(log_entry)

        except zmq.Again:
            pass
        except Exception as e:
            print(f"[LogAlert] 处理日志失败: {e}")
            self.stats["errors"] += 1

    def _flush_logs_if_needed(self) -> None:
        """批量刷新日志到数据库."""
        current_time = time.time()

        # 条件：批处理队列达到阈值，或距离上次刷新超过1秒
        should_flush = (
            len(self.log_batch) >= self.log_batch_size
            or (self.log_batch and current_time - self.last_flush_time >= 1.0)
        )

        if should_flush and self.log_batch:
            try:
                # 批量插入日志
                if self.log_manager:
                    for log_entry in self.log_batch:
                        self.log_manager.add_log_record(log_entry)

                # 清空批处理队列
                batch_count = len(self.log_batch)
                self.log_batch.clear()
                self.last_flush_time = current_time

                # 日志统计（仅在调试模式下输出）
                # print(f"[LogAlert] 批量刷新日志: {batch_count}条")

            except Exception as e:
                print(f"[LogAlert] 批量刷新日志失败: {e}")
                self.stats["errors"] += 1
                # 清空批处理队列，避免内存泄漏
                self.log_batch.clear()

    def _check_log_alert(self, log_entry: Dict[str, Any]) -> None:
        """检查日志是否触发告警.

        Args:
            log_entry: 日志条目
        """
        try:
            # 遍历所有告警规则
            from backend.core.alert_system import LogAlertRule
            from backend.core.utils import Alert, AlertStatus
            from datetime import datetime
            import uuid

            for rule in self.alert_rules:
                if isinstance(rule, LogAlertRule) and rule.evaluate_log_record(log_entry):
                    # 触发告警：创建告警对象
                    alert = Alert(
                        alert_id=f"alert_{uuid.uuid4().hex[:8]}",
                        rule_id=rule.rule_id,
                        title=rule.name,
                        message=f"{log_entry.get('level')}: {log_entry.get('message')}",
                        severity=rule.severity,
                        created_at=datetime.now(),
                        status=AlertStatus.ACTIVE,
                        source={
                            "type": "log",
                            "timestamp": log_entry.get("timestamp"),
                            "level": log_entry.get("level"),
                            "module": log_entry.get("module"),
                            "message": log_entry.get("message"),
                        },
                    )

                    self.stats["alerts_triggered"] += 1
                    
                    # 存储到数据库
                    if self.alert_db:
                        try:
                            self.alert_db.add_alert(alert.to_dict())
                        except Exception as e:
                            print(f"[LogAlert] 存储告警失败: {e}")
                    
                    # 推送告警
                    self._publish_alert(alert)

        except Exception as e:
            print(f"[LogAlert] 检查日志告警失败: {e}")
            self.stats["errors"] += 1

    def _publish_alert(self, alert) -> None:
        """推送告警到主进程.

        Args:
            alert: 告警对象
        """
        try:
            # 序列化告警数据
            alert_data = alert.to_dict()
            message = msgpack.packb(alert_data)

            # 发送到告警主题
            self.alert_publisher.send_multipart([b"alert", message])

            # 日志输出（仅在调试模式下）
            # print(f"[LogAlert] 告警已推送: {alert.title}")

        except Exception as e:
            print(f"[LogAlert] 推送告警失败: {e}")
            self.stats["errors"] += 1

    def _handle_health_check(self) -> None:
        """处理健康检查请求."""
        try:
            # 接收健康检查请求
            request = self.health_responder.recv(zmq.NOBLOCK)

            self.stats["health_checks"] += 1

            # 构建健康状态
            uptime = (datetime.now() - self.start_time).total_seconds()

            health_data = {
                "status": "healthy",
                "pid": os.getpid(),
                "uptime_seconds": uptime,
                "stats": self.stats,
                "timestamp": datetime.now().isoformat(),
            }

            # 响应
            response = msgpack.packb(health_data)
            self.health_responder.send(response)

        except zmq.Again:
            pass
        except Exception as e:
            print(f"[LogAlert] 处理健康检查失败: {e}")
            self.stats["errors"] += 1

    def _cleanup(self) -> None:
        """清理资源."""
        print(f"[LogAlert] 正在清理资源...")

        # 刷新剩余日志
        if self.log_batch:
            self._flush_logs_if_needed()

        # 关闭ZeroMQ套接字
        if self.log_receiver:
            self.log_receiver.close()
        if self.alert_publisher:
            self.alert_publisher.close()
        if self.health_responder:
            self.health_responder.close()
        if self.context:
            self.context.term()

        print(f"[LogAlert] 日志/告警进程已关闭")


def main():
    """进程入口点."""
    # 配置基础日志（仅输出到控制台）
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler()],
    )

    # 创建并启动进程
    process = LogAlertProcess()
    process.run()


if __name__ == "__main__":
    # 支持Windows多进程
    multiprocessing.freeze_support()
    main()
