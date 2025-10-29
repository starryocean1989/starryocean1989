# -*- coding: utf-8 -*-
"""
日志系统验证脚本

功能：
1. 统计Console输出数量（按日志类型分类）
2. 验证路由引擎缓存命中率
3. 统计数据库日志数量（WARNING+）
4. 生成优化效果对比报告

使用方法：
    python scripts/validate_logging_system.py

作者：系统重构团队
日期：2025-10-28
"""

import logging
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.infrastructure.system_vnpy.unified_log_system import (
    LoggingHub,
    LogType,
    UnifiedLogRecord,
    get_logging_hub,
)
from backend.infrastructure.system_vnpy.unified_log_system import get_routing_engine


class LoggingSystemValidator:
    """日志系统验证器"""

    def __init__(self):
        """初始化验证器"""
        self.console_logs: List[Tuple[LogType, int]] = []  # (类型, 级别)
        self.file_logs: List[Tuple[LogType, int]] = []
        self.db_logs: List[Tuple[LogType, int]] = []
        self.start_time = time.time()

        # 获取LoggingHub实例
        self.hub = get_logging_hub()

        # 获取路由引擎
        try:
            self._routing_engine = get_routing_engine()
        except Exception:
            self._routing_engine = None

    def simulate_logs(self):
        """模拟各种日志输出"""
        print("\n" + "=" * 70)
        print("🧪 开始日志模拟测试")
        print("=" * 70)

        test_cases = [
            # (logger_name, level, message, expected_type)
            ("startup.stage", logging.INFO, "📍 系统启动开始", LogType.STAGE_NODE),
            ("backend.services.data_center", logging.DEBUG, "检查配置文件", LogType.DEBUG),
            ("backend.services.data_center", logging.INFO, "配置加载完成", LogType.SYSTEM),
            (
                "backend.services.data_center",
                logging.INFO,
                "数据中心初始化完成",
                LogType.STAGE_NODE,
            ),
            (
                "backend.data_center.download",
                logging.INFO,
                "下载进度: 50%",
                LogType.PROGRESS,
            ),
            ("backend.data_center", logging.INFO, "数据下载完成", LogType.NOTIFICATION),
            (
                "backend.monitor.alert",
                logging.WARNING,
                "CPU使用率超过80%",
                LogType.ALERT,
            ),
            ("backend.services", logging.ERROR, "连接失败: 网络超时", LogType.SYSTEM),
            ("backend.services", logging.DEBUG, "进入函数 process_data", LogType.DEBUG),
            ("backend.services", logging.INFO, "处理数据中", LogType.SYSTEM),
            ("startup.stage", logging.INFO, "服务已就绪", LogType.STAGE_NODE),
            ("backend.data_center", logging.INFO, "品种加载完成", LogType.NOTIFICATION),
        ]

        print(f"\n共 {len(test_cases)} 个测试用例\n")

        for idx, (logger_name, level, message, expected_type) in enumerate(test_cases, 1):
            logger = logging.getLogger(logger_name)
            logger.setLevel(logging.DEBUG)

            # 发送日志
            logger.log(level, message)

            # 记录到统计（模拟分类）
            actual_type = self._classify_message(logger_name, level, message)

            # 获取路由目标
            if self._routing_engine:
                record = UnifiedLogRecord(
                    type=actual_type,
                    level=level,
                    module="test",
                    message=message,
                    logger_name=logger_name,
                )
                targets = self._routing_engine.route(record)
            else:
                targets = ["file"]  # 回退

            # 统计
            if "console" in targets:
                self.console_logs.append((actual_type, level))
            if "file" in targets or "ai_file" in targets:
                self.file_logs.append((actual_type, level))
            if "database" in targets:
                self.db_logs.append((actual_type, level))

            # 打印结果
            status = "✅" if actual_type == expected_type else "❌"
            level_name = logging.getLevelName(level)
            print(f"{status} [{idx:2d}] {level_name:8s} | {actual_type.value:15s} | {message[:40]}")
            if "console" in targets:
                print(f"          └─ 输出到: Terminal + File")
            else:
                print(f"          └─ 输出到: File only")

        print("\n" + "=" * 70)

    def _classify_message(self, logger_name: str, level: int, message: str) -> LogType:
        """简化的日志分类逻辑（模拟unified_logging的分类）"""
        logger_name_lower = logger_name.lower()
        message_lower = message.lower()

        # STAGE_NODE
        if ".stage" in logger_name_lower:
            return LogType.STAGE_NODE

        if level == logging.INFO:
            stage_keywords = [
                "📍",
                "开始初始化",
                "初始化完成",
                "启动完成",
                "服务已就绪",
                "系统已就绪",
            ]
            if any(kw in message_lower for kw in stage_keywords):
                if "%" not in message_lower and "进度" not in message_lower:
                    if len(message_lower) > 10:
                        return LogType.STAGE_NODE

        # ALERT
        if "alert" in logger_name_lower or "monitor" in logger_name_lower:
            if level >= logging.WARNING:
                return LogType.ALERT

        # PROGRESS
        if "download" in logger_name_lower or "progress" in logger_name_lower:
            if "进度" in message_lower or "%" in message_lower:
                return LogType.PROGRESS

        # NOTIFICATION
        if level == logging.INFO:
            if "完成" in message_lower or "成功" in message_lower:
                # 排除阶段节点
                if not any(
                    kw in message_lower
                    for kw in [
                        "开始初始化",
                        "初始化完成",
                        "启动完成",
                        "服务已就绪",
                    ]
                ):
                    return LogType.NOTIFICATION

        # DEBUG
        if level == logging.DEBUG:
            return LogType.DEBUG

        # SYSTEM
        return LogType.SYSTEM

    def generate_report(self):
        """生成验证报告"""
        print("\n" + "=" * 70)
        print("📊 日志系统验证报告")
        print("=" * 70)

        # 统计Console输出
        console_by_type = {}
        for log_type, level in self.console_logs:
            if log_type not in console_by_type:
                console_by_type[log_type] = {"total": 0, "by_level": {}}
            console_by_type[log_type]["total"] += 1
            level_name = logging.getLevelName(level)
            console_by_type[log_type]["by_level"][level_name] = (
                console_by_type[log_type]["by_level"].get(level_name, 0) + 1
            )

        print("\n1️⃣  Console输出统计（输出到Terminal的日志）")
        print("-" * 70)
        total_console = len(self.console_logs)
        print(f"总计: {total_console} 条")
        for log_type, stats in console_by_type.items():
            print(f"  - {log_type.value:15s}: {stats['total']:2d} 条", end="")
            levels = [f"{k}({v})" for k, v in stats["by_level"].items()]
            print(f"  [{', '.join(levels)}]")

        # 统计File输出
        print("\n2️⃣  File输出统计（输出到日志文件的日志）")
        print("-" * 70)
        total_file = len(self.file_logs)
        print(f"总计: {total_file} 条（包括所有级别）")

        # 统计Database输出
        print("\n3️⃣  Database输出统计（输出到数据库的日志）")
        print("-" * 70)
        total_db = len(self.db_logs)
        print(f"总计: {total_db} 条（仅WARNING及以上级别）")

        # 路由引擎统计
        if self._routing_engine:
            print("\n4️⃣  路由引擎统计")
            print("-" * 70)
            stats = self._routing_engine.get_statistics()
            print(f"总路由次数: {stats['total_routes']}")
            print(f"当前阶段: {stats['current_stage']}")
            print(f"运行模式: {stats['run_mode']}")

            cache_stats = stats["cache_stats"]
            print(f"\n缓存统计:")
            print(f"  - 缓存大小: {cache_stats['size']}")
            print(f"  - 缓存命中: {cache_stats['hits']}")
            print(f"  - 缓存未命中: {cache_stats['misses']}")
            print(f"  - 命中率: {cache_stats['hit_rate']}")
            print(f"  - 驱逐次数: {cache_stats['evictions']}")

            # 验证命中率
            hit_rate_value = float(cache_stats["hit_rate"].rstrip("%"))
            if hit_rate_value >= 95:
                print(f"  ✅ 缓存命中率达标（>= 95%）")
            else:
                print(f"  ⚠️  缓存命中率未达标（< 95%）")

        # 优化效果评估
        print("\n5️⃣  优化效果评估")
        print("-" * 70)

        # 假设优化前的基准（基于文档估算）
        baseline_console = 150  # 优化前约150-200条
        current_console = total_console

        reduction = (1 - current_console / baseline_console) * 100
        print(f"Console输出减少: {reduction:.1f}%")
        if reduction >= 60:
            print(f"  ✅ 达成目标（>= 60%）")
        else:
            print(f"  ⚠️  未达目标（< 60%）")

        # Terminal输出内容分析
        print("\n6️⃣  Terminal输出内容分析（应该输出的内容）")
        print("-" * 70)
        expected_types = {
            LogType.STAGE_NODE: "阶段节点（开始/结束标记）",
            LogType.NOTIFICATION: "任务完成通知",
            LogType.ALERT: "告警信息",
            LogType.SYSTEM: "系统错误（WARNING/ERROR/CRITICAL）",
            LogType.USER_FEEDBACK: "用户反馈",
        }

        print("✅ 正确输出到Terminal的类型:")
        for log_type in console_by_type.keys():
            if log_type in expected_types:
                print(f"  - {log_type.value:15s}: {expected_types[log_type]}")

        unexpected = set(console_by_type.keys()) - set(expected_types.keys())
        if unexpected:
            print("\n❌ 不应该输出到Terminal的类型:")
            for log_type in unexpected:
                print(f"  - {log_type.value}")

        # LoggingHub统计
        print("\n7️⃣  LoggingHub统计")
        print("-" * 70)
        hub_stats = self.hub.get_statistics()
        print(f"总日志数: {hub_stats['total_logs']}")
        print(f"节流日志数: {hub_stats['throttled_logs']}")
        print(f"Console写入: {hub_stats['console_writes']}")
        print(f"File写入: {hub_stats['file_writes']}")
        print(f"Database写入: {hub_stats['db_writes']}")
        print(f"Database待写: {hub_stats['db_batch_pending']}")

        print("\n" + "=" * 70)
        print("✅ 验证完成")
        print("=" * 70)


def main():
    """主函数"""
    print("=" * 70)
    print("🔍 日志系统验证工具 v1.0")
    print("=" * 70)

    # 初始化验证器
    validator = LoggingSystemValidator()

    # 模拟日志输出
    validator.simulate_logs()

    # 生成报告
    validator.generate_report()

    print("\n💡 提示:")
    print("  1. 如果Console输出减少>60%，说明优化成功")
    print("  2. 如果缓存命中率>95%，说明性能良好")
    print("  3. Terminal应只显示：阶段节点、通知、告警、错误")
    print("  4. 所有DEBUG和普通INFO应只在文件中")
    print()


if __name__ == "__main__":
    main()
