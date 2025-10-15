# -*- coding: utf-8 -*-
"""
启动阻塞诊断脚本 - 逐步加载每个组件

通过逐步加载来精确定位哪个组件导致启动卡住
"""

import sys
import os
import time
from pathlib import Path

# 设置项目路径
project_root = Path(__file__).parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# 设置环境变量
os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"
os.environ["CONFIG_FILE"] = str(project_root / "config" / "terminal_config.json")

def test_step(step_name, func):
    """测试单个步骤"""
    print(f"\n{'='*70}")
    print(f"[测试] {step_name}")
    print('='*70)
    start = time.time()
    try:
        result = func()
        elapsed = (time.time() - start) * 1000
        print(f"✅ {step_name} 完成 ({elapsed:.0f}ms)")
        return True, result
    except Exception as e:
        elapsed = (time.time() - start) * 1000
        print(f"❌ {step_name} 失败 ({elapsed:.0f}ms)")
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()
        return False, None

def step1_import_vnpy():
    """步骤1: 导入VNPY"""
    from vnpy.event import EventEngine
    from vnpy.trader.engine import MainEngine
    return EventEngine, MainEngine

def step2_create_event_engine():
    """步骤2: 创建EventEngine"""
    from vnpy.event import EventEngine
    return EventEngine(interval=0.5)

def step3_create_main_engine(event_engine):
    """步骤3: 创建MainEngine"""
    from vnpy.trader.engine import MainEngine
    print("开始创建MainEngine...")
    main_engine = MainEngine(event_engine)
    print("MainEngine创建完成")
    return main_engine

def step4_import_data_module():
    """步骤4: 导入data_module_vnpy"""
    from backend.infrastructure.data_module_vnpy.core import ChinaStockEngine
    return ChinaStockEngine

def step5_create_china_stock_engine(main_engine, event_engine):
    """步骤5: 创建ChinaStockEngine"""
    from backend.infrastructure.data_module_vnpy.core import ChinaStockEngine
    print("开始创建ChinaStockEngine...")
    engine = ChinaStockEngine(main_engine, event_engine)
    print("ChinaStockEngine创建完成")
    return engine

def step6_import_services():
    """步骤6: 导入所有服务"""
    print("导入DataCenterService...")
    from backend.services.data_center_service import DataCenterService
    
    print("导入TradingGatewayService...")
    from backend.services.trading_gateway_service import TradingGatewayService
    
    print("导入StrategyCenterService...")
    from backend.services.strategy_center_service import StrategyCenterService
    
    print("导入SystemManagerService...")
    from backend.services.system_manager_service import SystemManagerService
    
    return True

def step7_init_logging_alert():
    """步骤7: 初始化日志和告警系统"""
    print("初始化日志系统...")
    from backend.core.logging_system import initialize_logging_system
    initialize_logging_system()
    
    print("初始化告警系统...")
    from backend.core.alert_system import initialize_alert_system
    initialize_alert_system()
    
    return True

def main():
    """主测试流程"""
    print("="*70)
    print("启动阻塞诊断 - 逐步测试")
    print("="*70)
    print("提示: 如果某个步骤卡住超过10秒，按Ctrl+C中断")
    print("="*70)
    
    # 步骤1: 导入VNPY
    success, result = test_step("步骤1: 导入VNPY模块", step1_import_vnpy)
    if not success:
        print("\n❌ 诊断结论: VNPY导入失败")
        return
    
    # 步骤2: 创建EventEngine
    success, event_engine = test_step("步骤2: 创建EventEngine", step2_create_event_engine)
    if not success:
        print("\n❌ 诊断结论: EventEngine创建失败")
        return
    
    # 步骤3: 创建MainEngine
    success, main_engine = test_step(
        "步骤3: 创建MainEngine", 
        lambda: step3_create_main_engine(event_engine)
    )
    if not success:
        print("\n❌ 诊断结论: MainEngine创建失败")
        return
    
    print("\n⚠️ 关键点: MainEngine创建成功！")
    print("如果启动卡在VNPY初始化，问题不在这里\n")
    
    # 步骤4: 导入data_module_vnpy
    success, _ = test_step("步骤4: 导入data_module_vnpy", step4_import_data_module)
    if not success:
        print("\n❌ 诊断结论: data_module_vnpy导入失败")
        return
    
    # 步骤5: 创建ChinaStockEngine
    success, china_engine = test_step(
        "步骤5: 创建ChinaStockEngine",
        lambda: step5_create_china_stock_engine(main_engine, event_engine)
    )
    if not success:
        print("\n❌ 诊断结论: ChinaStockEngine创建失败")
        return
    
    print("\n⚠️ 关键点: ChinaStockEngine创建成功！\n")
    
    # 步骤6: 导入所有服务
    success, _ = test_step("步骤6: 导入所有服务模块", step6_import_services)
    if not success:
        print("\n❌ 诊断结论: 服务模块导入失败")
        return
    
    # 步骤7: 初始化日志和告警
    success, _ = test_step("步骤7: 初始化日志和告警系统", step7_init_logging_alert)
    if not success:
        print("\n❌ 诊断结论: 日志/告警系统初始化失败")
        return
    
    print("\n" + "="*70)
    print("✅ 所有步骤测试通过！")
    print("="*70)
    print("\n诊断结论:")
    print("- VNPY核心组件正常")
    print("- 数据引擎正常")
    print("- 服务模块正常")
    print("- 日志告警系统正常")
    print("\n⚠️ 问题可能在:")
    print("1. 后续的服务初始化过程")
    print("2. UI组件创建过程")
    print("3. 信号槽连接过程")
    print("4. 某个隐藏的阻塞调用")
    
    # 清理
    print("\n清理资源...")
    try:
        main_engine.close()
        event_engine.stop()
        print("✅ 资源清理完成")
    except Exception as e:
        print(f"⚠️ 清理异常: {e}")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n❌ 测试被中断！")
        print("中断位置就是阻塞点！")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ 测试异常: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
