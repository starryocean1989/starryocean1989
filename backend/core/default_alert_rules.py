# -*- coding: utf-8 -*-
"""
默认告警规则定义.

提供系统预置的告警规则，包括：
- 日志级别监控
- 系统资源监控
- 业务指标监控
- 性能监控
"""

from typing import List
from backend.core.alert_system import LogAlertRule
from backend.core.utils import AlertRule, AlertSeverity


def get_default_log_alert_rules() -> List[LogAlertRule]:
    """获取默认的日志告警规则.
    
    Returns:
        日志告警规则列表
    """
    rules = []
    
    # ERROR级别日志监控
    rules.append(LogAlertRule(
        rule_id="log_error_monitoring",
        name="ERROR级别日志监控",
        log_levels=["ERROR"],
        severity=AlertSeverity.ERROR,
        description="监控所有ERROR级别日志记录",
        suppression_window=60,  # 1分钟抑制窗口
        enabled=True,
        priority=2,
    ))
    
    # CRITICAL级别日志监控
    rules.append(LogAlertRule(
        rule_id="log_critical_monitoring",
        name="CRITICAL级别日志监控",
        log_levels=["CRITICAL"],
        severity=AlertSeverity.CRITICAL,
        description="监控所有CRITICAL级别日志记录",
        suppression_window=30,  # 30秒抑制窗口
        enabled=True,
        priority=1,  # 最高优先级
    ))
    
    # 连接失败监控
    rules.append(LogAlertRule(
        rule_id="log_connection_failures",
        name="连接失败监控",
        keywords=[
            "连接失败", "连接超时", "网络错误", 
            "Connection failed", "Connection timeout", "Network error"
        ],
        severity=AlertSeverity.WARNING,
        description="监控连接相关的错误日志",
        suppression_window=120,  # 2分钟抑制窗口
        enabled=True,
        priority=3,
    ))
    
    # 数据库错误监控
    rules.append(LogAlertRule(
        rule_id="log_database_errors",
        name="数据库错误监控",
        keywords=[
            "数据库错误", "SQL错误", "连接池", 
            "Database error", "SQL error", "Connection pool"
        ],
        severity=AlertSeverity.ERROR,
        description="监控数据库相关的错误日志",
        suppression_window=60,  # 1分钟抑制窗口
        enabled=True,
        priority=2,
    ))
    
    # 数据中心模块错误监控
    rules.append(LogAlertRule(
        rule_id="log_data_center_errors",
        name="数据中心错误监控",
        modules=["data_center_service", "data_fetcher", "data_quality"],
        log_levels=["ERROR", "CRITICAL"],
        severity=AlertSeverity.ERROR,
        description="监控数据中心模块的错误日志",
        suppression_window=120,  # 2分钟抑制窗口
        enabled=True,
        priority=3,
    ))
    
    # 交易网关模块错误监控
    rules.append(LogAlertRule(
        rule_id="log_trading_gateway_errors",
        name="交易网关错误监控",
        modules=["trading_gateway_service", "gateway_adapters"],
        log_levels=["ERROR", "CRITICAL"],
        severity=AlertSeverity.CRITICAL,
        description="监控交易网关模块的错误日志",
        suppression_window=60,  # 1分钟抑制窗口
        enabled=True,
        priority=1,  # 交易相关最高优先级
    ))
    
    # 策略中心模块错误监控
    rules.append(LogAlertRule(
        rule_id="log_strategy_center_errors",
        name="策略中心错误监控",
        modules=["strategy_center_service", "backtest_renderers"],
        log_levels=["ERROR", "CRITICAL"],
        severity=AlertSeverity.WARNING,
        description="监控策略中心模块的错误日志",
        suppression_window=180,  # 3分钟抑制窗口
        enabled=True,
        priority=3,
    ))
    
    # 数据下载失败监控
    rules.append(LogAlertRule(
        rule_id="log_data_download_failures",
        name="数据下载失败监控",
        keywords=[
            "下载失败", "数据获取失败", "Download failed", 
            "Failed to fetch", "数据源不可用"
        ],
        severity=AlertSeverity.WARNING,
        description="监控数据下载失败的日志",
        suppression_window=300,  # 5分钟抑制窗口
        enabled=True,
        priority=4,
    ))
    
    # 订单拒绝监控
    rules.append(LogAlertRule(
        rule_id="log_order_rejections",
        name="订单拒绝监控",
        keywords=[
            "订单被拒绝", "订单失败", "Order rejected", 
            "Order failed", "拒单"
        ],
        severity=AlertSeverity.ERROR,
        description="监控订单被拒绝的日志",
        suppression_window=60,  # 1分钟抑制窗口
        enabled=True,
        priority=2,
    ))
    
    # 回测异常监控
    rules.append(LogAlertRule(
        rule_id="log_backtest_errors",
        name="回测异常监控",
        keywords=[
            "回测失败", "回测异常", "Backtest failed", 
            "Backtest error", "策略执行失败"
        ],
        severity=AlertSeverity.WARNING,
        description="监控回测异常的日志",
        suppression_window=180,  # 3分钟抑制窗口
        enabled=True,
        priority=4,
    ))
    
    return rules


def get_default_system_alert_rules() -> List[AlertRule]:
    """获取默认的系统告警规则.
    
    Returns:
        系统告警规则列表
    """
    rules = []
    
    # CPU使用率过高
    rules.append(AlertRule(
        rule_id="system_cpu_high",
        name="CPU使用率过高",
        condition="cpu_percent > 90",
        severity=AlertSeverity.WARNING,
        enabled=True,
        priority=3,
        group="system_resource",
        description="CPU使用率超过90%时触发告警",
    ))
    
    # 内存不足
    rules.append(AlertRule(
        rule_id="system_memory_low",
        name="内存不足",
        condition="memory_percent > 85",
        severity=AlertSeverity.ERROR,
        enabled=True,
        priority=2,
        group="system_resource",
        description="内存使用率超过85%时触发告警",
    ))
    
    # 磁盘空间不足
    rules.append(AlertRule(
        rule_id="system_disk_low",
        name="磁盘空间不足",
        condition="disk_percent > 90",
        severity=AlertSeverity.ERROR,
        enabled=True,
        priority=2,
        group="system_resource",
        description="磁盘使用率超过90%时触发告警",
    ))
    
    # 服务不可用
    rules.append(AlertRule(
        rule_id="service_unavailable",
        name="服务不可用",
        condition="service_status == 'offline'",
        severity=AlertSeverity.CRITICAL,
        enabled=True,
        priority=1,
        group="service_health",
        description="关键服务离线时触发告警",
    ))
    
    return rules


def get_default_business_alert_rules() -> List[AlertRule]:
    """获取默认的业务告警规则.
    
    Returns:
        业务告警规则列表
    """
    rules = []
    
    # 数据下载失败率过高
    rules.append(AlertRule(
        rule_id="business_data_download_failure_rate",
        name="数据下载失败率过高",
        condition="download_failure_rate > 10",
        severity=AlertSeverity.ERROR,
        enabled=True,
        priority=3,
        group="data_quality",
        description="数据下载失败率超过10%时触发告警",
    ))
    
    # 网关频繁断线
    rules.append(AlertRule(
        rule_id="business_gateway_disconnect_frequent",
        name="网关频繁断线",
        condition="disconnect_count_per_hour > 3",
        severity=AlertSeverity.WARNING,
        enabled=True,
        priority=2,
        group="trading",
        description="网关1小时内断线超过3次时触发告警",
    ))
    
    # 订单拒绝率过高
    rules.append(AlertRule(
        rule_id="business_order_rejection_rate",
        name="订单拒绝率过高",
        condition="order_rejection_rate > 5",
        severity=AlertSeverity.ERROR,
        enabled=True,
        priority=2,
        group="trading",
        description="订单拒绝率超过5%时触发告警",
    ))
    
    # 数据质量异常
    rules.append(AlertRule(
        rule_id="business_data_quality_issue",
        name="数据质量异常",
        condition="missing_data_rate > 5 or duplicate_data_rate > 1",
        severity=AlertSeverity.WARNING,
        enabled=True,
        priority=3,
        group="data_quality",
        description="数据缺失率>5%或重复率>1%时触发告警",
    ))
    
    return rules


def initialize_default_alert_rules() -> None:
    """初始化默认告警规则.
    
    将所有默认规则注册到告警引擎。
    """
    from backend.core.utils import alert_engine
    
    print("[启动] 开始初始化默认告警规则...")
    
    # 注册日志告警规则
    log_rules = get_default_log_alert_rules()
    for rule in log_rules:
        alert_engine.add_rule(rule)
    print(f"[启动] ✅ 已注册 {len(log_rules)} 个日志告警规则")
    
    # 注册系统告警规则
    system_rules = get_default_system_alert_rules()
    for rule in system_rules:
        alert_engine.add_rule(rule)
    print(f"[启动] ✅ 已注册 {len(system_rules)} 个系统告警规则")
    
    # 注册业务告警规则
    business_rules = get_default_business_alert_rules()
    for rule in business_rules:
        alert_engine.add_rule(rule)
    print(f"[启动] ✅ 已注册 {len(business_rules)} 个业务告警规则")
    
    total_rules = len(log_rules) + len(system_rules) + len(business_rules)
    print(f"[启动] ✅ 默认告警规则初始化完成，共 {total_rules} 个规则")


if __name__ == "__main__":
    # 测试代码
    initialize_default_alert_rules()
    
    from backend.core.utils import alert_engine
    all_rules = alert_engine.get_all_rules()
    print(f"\n当前告警规则总数: {len(all_rules)}")
    
    for rule in all_rules:
        print(f"- [{rule.severity.value}] {rule.name} (ID: {rule.rule_id})")
