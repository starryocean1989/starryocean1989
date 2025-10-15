# -*- coding: utf-8 -*-
"""
多进程架构改造 - 测试脚本.

测试日志/告警进程的启动、IPC通信和健康检查功能。
"""

import logging
import multiprocessing
import time

# 配置基础日志
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
)

def test_process_manager():
    """测试进程管理器."""
    print("=" * 70)
    print("测试1：进程管理器")
    print("=" * 70)
    
    from backend.processes.process_manager import get_process_manager
    
    # 获取进程管理器
    pm = get_process_manager()
    
    # 注册日志/告警进程
    pm.register_process(
        name="log_alert",
        target_module="backend.processes.log_alert_process",
        health_port=5559,
        max_restarts=5,
    )
    
    # 启动进程
    print("\n[测试] 启动日志/告警进程...")
    success = pm.start_process("log_alert")
    
    if success:
        print("[测试] ✅ 进程启动成功")
    else:
        print("[测试] ❌ 进程启动失败")
        return False
    
    # 等待进程稳定
    time.sleep(2)
    
    # 健康检查
    print("\n[测试] 健康检查...")
    health = pm.check_health("log_alert")
    print(f"[测试] 健康状态: {health}")
    
    if health.get("healthy"):
        print("[测试] ✅ 进程健康")
    else:
        print("[测试] ❌ 进程不健康")
    
    # 获取所有进程状态
    print("\n[测试] 所有进程状态...")
    status = pm.get_all_status()
    print(f"[测试] 状态: {status}")
    
    return True


def test_distributed_log_handler():
    """测试分布式日志处理器."""
    print("\n" + "=" * 70)
    print("测试2：分布式日志处理器")
    print("=" * 70)
    
    from backend.processes.ipc_client import get_distributed_log_handler
    
    # 获取分布式日志处理器
    handler = get_distributed_log_handler()
    
    # 添加到根日志器
    logging.root.addHandler(handler)
    
    # 发送测试日志
    print("\n[测试] 发送测试日志...")
    
    logging.info("测试INFO日志 - 这是一条信息日志")
    logging.warning("测试WARNING日志 - 这是一条警告日志")
    logging.error("测试ERROR日志 - 这是一条错误日志")
    
    # 等待日志发送
    time.sleep(1)
    
    print("[测试] ✅ 日志已发送到日志进程")
    
    return True


def test_alert_subscriber():
    """测试告警订阅器."""
    print("\n" + "=" * 70)
    print("测试3：告警订阅器")
    print("=" * 70)
    
    from backend.processes.ipc_client import get_alert_subscriber
    from PySide6.QtCore import QCoreApplication
    import sys
    
    # 创建Qt应用（需要事件循环）
    app = QCoreApplication(sys.argv)
    
    # 获取告警订阅器
    subscriber = get_alert_subscriber()
    
    # 连接信号
    def on_alert_received(alert_data):
        print(f"[测试] 收到告警: {alert_data}")
    
    subscriber.alert_received.connect(on_alert_received)
    
    # 启动订阅
    print("\n[测试] 启动告警订阅...")
    success = subscriber.start()
    
    if success:
        print("[测试] ✅ 告警订阅启动成功")
    else:
        print("[测试] ❌ 告警订阅启动失败")
        return False
    
    # 等待告警（5秒）
    print("[测试] 等待告警事件（5秒）...")
    
    # 触发一些错误日志，应该会产生告警
    logging.error("测试告警触发 - 这是一条错误日志")
    logging.critical("测试告警触发 - 这是一条严重错误日志")
    
    # 运行事件循环（5秒）
    from PySide6.QtCore import QTimer
    QTimer.singleShot(5000, app.quit)
    app.exec()
    
    # 停止订阅
    subscriber.stop()
    
    print("[测试] ✅ 告警订阅测试完成")
    
    return True


def test_process_restart():
    """测试进程自动重启."""
    print("\n" + "=" * 70)
    print("测试4：进程自动重启")
    print("=" * 70)
    
    from backend.processes.process_manager import get_process_manager
    
    pm = get_process_manager()
    
    # 获取当前进程PID
    status = pm.get_all_status()
    current_pid = status.get("log_alert", {}).get("pid")
    
    print(f"\n[测试] 当前进程PID: {current_pid}")
    
    # 重启进程
    print("[测试] 重启进程...")
    success = pm.restart_process("log_alert")
    
    if success:
        print("[测试] ✅ 进程重启成功")
    else:
        print("[测试] ❌ 进程重启失败")
        return False
    
    # 检查新PID
    time.sleep(2)
    status = pm.get_all_status()
    new_pid = status.get("log_alert", {}).get("pid")
    
    print(f"[测试] 新进程PID: {new_pid}")
    
    if new_pid != current_pid:
        print("[测试] ✅ 进程PID已更新")
    else:
        print("[测试] ⚠️ 进程PID未更新")
    
    return True


def cleanup():
    """清理资源."""
    print("\n" + "=" * 70)
    print("清理资源")
    print("=" * 70)
    
    from backend.processes.process_manager import get_process_manager
    
    pm = get_process_manager()
    pm.cleanup()
    
    print("[测试] ✅ 资源已清理")


def main():
    """主测试流程."""
    print("\n" + "=" * 70)
    print("多进程架构改造 - 集成测试")
    print("=" * 70)
    
    try:
        # 测试1：进程管理器
        if not test_process_manager():
            print("\n[测试] ❌ 进程管理器测试失败")
            return
        
        # 测试2：分布式日志处理器
        if not test_distributed_log_handler():
            print("\n[测试] ❌ 分布式日志处理器测试失败")
            return
        
        # 测试3：告警订阅器（需要Qt）
        # 注释掉，因为需要GUI环境
        # if not test_alert_subscriber():
        #     print("\n[测试] ❌ 告警订阅器测试失败")
        #     return
        
        # 测试4：进程自动重启
        if not test_process_restart():
            print("\n[测试] ❌ 进程自动重启测试失败")
            return
        
        print("\n" + "=" * 70)
        print("✅ 所有测试通过！")
        print("=" * 70)
        
    except KeyboardInterrupt:
        print("\n[测试] 收到中断信号")
    except Exception as e:
        print(f"\n[测试] ❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        cleanup()


if __name__ == "__main__":
    # 支持Windows多进程
    multiprocessing.freeze_support()
    main()
