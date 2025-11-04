# -*- coding: utf-8 -*-
"""
启动架构集成测试脚本

用于测试新的启动架构是否正常工作。
"""

import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

def test_imports():
    """测试所有导入是否正常"""
    print("=" * 70)
    print("测试1: 导入测试")
    print("=" * 70)
    
    try:
        from backend.startup import (
            StartupOrchestrator,
            StartupResult,
            StartupContext,
            EnvSetupStage,
            LoggingInitStage,
            QtFrameworkStage,
            BackendInitStage,
            UIActivationStage,
        )
        print("✅ 所有导入成功")
        return True
    except Exception as e:
        print(f"❌ 导入失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_orchestrator_creation():
    """测试创建启动编排器"""
    print("\n" + "=" * 70)
    print("测试2: 启动编排器创建测试")
    print("=" * 70)
    
    try:
        from backend.startup import StartupOrchestrator
        
        orchestrator = StartupOrchestrator()
        print("✅ StartupOrchestrator 创建成功")
        return True
    except Exception as e:
        print(f"❌ StartupOrchestrator 创建失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_stages_creation():
    """测试创建所有阶段"""
    print("\n" + "=" * 70)
    print("测试3: 阶段创建测试")
    print("=" * 70)
    
    try:
        from backend.startup import (
            EnvSetupStage,
            LoggingInitStage,
            QtFrameworkStage,
            BackendInitStage,
            UIActivationStage,
        )
        
        stages = [
            EnvSetupStage(),
            LoggingInitStage(),
            QtFrameworkStage(),
            BackendInitStage(),
            UIActivationStage(),
        ]
        
        print(f"✅ 所有阶段创建成功（共 {len(stages)} 个阶段）")
        for stage in stages:
            print(f"   - {stage.name}: {stage.description}")
        return True
    except Exception as e:
        print(f"❌ 阶段创建失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_workers_creation():
    """测试创建所有Worker"""
    print("\n" + "=" * 70)
    print("测试4: Worker创建测试")
    print("=" * 70)
    
    try:
        from backend.startup.workers import (
            BackendInitializerWorker,
            MonitorLauncherWorker,
            CacheValidatorWorker,
        )
        
        workers = [
            BackendInitializerWorker(),
            MonitorLauncherWorker(),
            CacheValidatorWorker(),
        ]
        
        print(f"✅ 所有Worker创建成功（共 {len(workers)} 个Worker）")
        for worker in workers:
            print(f"   - {worker.name}: {worker.description}")
        return True
    except Exception as e:
        print(f"❌ Worker创建失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_context_creation():
    """测试创建启动上下文"""
    print("\n" + "=" * 70)
    print("测试5: 启动上下文创建测试")
    print("=" * 70)
    
    try:
        from backend.startup import StartupContext
        
        context = StartupContext()
        print("✅ StartupContext 创建成功")
        print(f"   - 项目根目录: {context.project_root}")
        print(f"   - 配置文件: {context.config_file}")
        return True
    except Exception as e:
        print(f"❌ StartupContext 创建失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_orchestrator_setup():
    """测试设置启动编排器"""
    print("\n" + "=" * 70)
    print("测试6: 启动编排器设置测试")
    print("=" * 70)
    
    try:
        from backend.startup import (
            StartupOrchestrator,
            EnvSetupStage,
            LoggingInitStage,
            QtFrameworkStage,
            BackendInitStage,
            UIActivationStage,
        )
        
        orchestrator = StartupOrchestrator()
        
        # 添加所有阶段
        orchestrator.add_stage(EnvSetupStage())
        orchestrator.add_stage(LoggingInitStage())
        orchestrator.add_stage(QtFrameworkStage())
        orchestrator.add_stage(BackendInitStage())
        orchestrator.add_stage(UIActivationStage())
        
        print(f"✅ 启动编排器设置成功（共 {len(orchestrator.stages)} 个阶段）")
        for stage in orchestrator.stages:
            print(f"   - {stage.name}: {stage.description}")
        
        # 验证上下文
        context = orchestrator.get_context()
        print(f"✅ 启动上下文获取成功")
        
        return True
    except Exception as e:
        print(f"❌ 启动编排器设置失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_logging_system():
    """测试日志系统"""
    print("\n" + "=" * 70)
    print("测试7: 日志系统测试")
    print("=" * 70)
    
    try:
        from backend.startup.startup_logging.startup_logger import (
            StartupLogger,
            OrderedLogQueue,
            StartupAILogHandler,
        )
        
        # 测试StartupLogger
        logger = StartupLogger()
        print("✅ StartupLogger 创建成功")
        
        # 测试OrderedLogQueue
        queue = OrderedLogQueue(max_wait_seconds=30)
        print("✅ OrderedLogQueue 创建成功")
        
        # 测试StartupAILogHandler
        handler = StartupAILogHandler()
        print("✅ StartupAILogHandler 创建成功")
        
        return True
    except Exception as e:
        print(f"❌ 日志系统测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """主测试函数"""
    print("=" * 70)
    print("🚀 启动架构集成测试")
    print("=" * 70)
    print()
    
    tests = [
        ("导入测试", test_imports),
        ("启动编排器创建", test_orchestrator_creation),
        ("阶段创建", test_stages_creation),
        ("Worker创建", test_workers_creation),
        ("启动上下文创建", test_context_creation),
        ("启动编排器设置", test_orchestrator_setup),
        ("日志系统", test_logging_system),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n❌ 测试 '{name}' 发生异常: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))
    
    # 汇总结果
    print("\n" + "=" * 70)
    print("测试结果汇总")
    print("=" * 70)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{status}: {name}")
    
    print("\n" + "=" * 70)
    print(f"总计: {passed}/{total} 测试通过")
    print("=" * 70)
    
    if passed == total:
        print("\n🎉 所有测试通过！")
        return 0
    else:
        print(f"\n⚠️ {total - passed} 个测试失败")
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)

