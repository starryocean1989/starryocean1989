# -*- coding: utf-8 -*-
"""
启动稳定性测试 - 测试启动崩溃率.

验收标准：连续启动100次，崩溃率 < 1%
"""

import logging
import multiprocessing
import sys
import time
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
)


def single_startup_test(test_id: int) -> bool:
    """单次启动测试.
    
    Args:
        test_id: 测试序号
        
    Returns:
        是否成功启动
    """
    try:
        print(f"\n[测试 #{test_id}] 开始启动测试...")
        
        # 启动日志/告警进程
        from backend.processes.process_manager import get_process_manager
        
        pm = get_process_manager()
        
        # 注册进程
        pm.register_process(
            name="log_alert",
            target_module="backend.processes.log_alert_process",
            health_port=5559,
        )
        
        # 启动进程
        success = pm.start_process("log_alert")
        
        if not success:
            print(f"[测试 #{test_id}] ❌ 进程启动失败")
            return False
        
        # 等待稳定
        time.sleep(1)
        
        # 健康检查
        health = pm.check_health("log_alert")
        
        if not health.get("healthy"):
            print(f"[测试 #{test_id}] ❌ 健康检查失败: {health}")
            pm.stop_process("log_alert")
            return False
        
        print(f"[测试 #{test_id}] ✅ 启动成功")
        
        # 清理
        pm.stop_process("log_alert")
        time.sleep(0.5)
        
        return True
        
    except Exception as e:
        print(f"[测试 #{test_id}] ❌ 异常: {e}")
        import traceback
        traceback.print_exc()
        return False


def run_stability_test(num_tests: int = 100):
    """运行稳定性测试.
    
    Args:
        num_tests: 测试次数
    """
    print("=" * 70)
    print(f"启动稳定性测试 - {num_tests}次")
    print("=" * 70)
    
    success_count = 0
    failure_count = 0
    
    start_time = time.time()
    
    for i in range(1, num_tests + 1):
        if single_startup_test(i):
            success_count += 1
        else:
            failure_count += 1
        
        # 每10次显示进度
        if i % 10 == 0:
            crash_rate = (failure_count / i) * 100
            print(f"\n[进度] {i}/{num_tests} 完成，成功率: {100-crash_rate:.1f}%")
    
    elapsed_time = time.time() - start_time
    
    # 最终统计
    crash_rate = (failure_count / num_tests) * 100
    
    print("\n" + "=" * 70)
    print("测试结果")
    print("=" * 70)
    print(f"总测试次数: {num_tests}")
    print(f"成功次数: {success_count}")
    print(f"失败次数: {failure_count}")
    print(f"崩溃率: {crash_rate:.2f}%")
    print(f"总耗时: {elapsed_time:.1f}秒")
    print(f"平均每次: {elapsed_time/num_tests:.2f}秒")
    
    # 验收标准
    if crash_rate < 1.0:
        print("\n✅ 验收通过：崩溃率 < 1%")
        return True
    else:
        print(f"\n❌ 验收失败：崩溃率 {crash_rate:.2f}% >= 1%")
        return False


def main():
    """主函数."""
    # 默认测试10次（快速验证）
    # 完整测试使用100次
    num_tests = 10
    
    if len(sys.argv) > 1:
        num_tests = int(sys.argv[1])
    
    try:
        result = run_stability_test(num_tests)
        sys.exit(0 if result else 1)
    except KeyboardInterrupt:
        print("\n[测试] 收到中断信号")
        sys.exit(1)


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
