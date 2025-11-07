# -*- coding: utf-8 -*-
"""
启动架构集成测试脚本

用于测试新的启动架构是否正常工作。
"""

import sys
import logging
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# 统一日志
log = logging.getLogger(__name__)

def test_imports():
    """测试所有导入是否正常"""
    log.info("=" * 70, extra={"log_type": "STAGE_NODE"})
    log.info("测试1: 导入测试", extra={"log_type": "STAGE_NODE"})
    log.info("=" * 70, extra={"log_type": "STAGE_NODE"})
    
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
        log.info("✅ 所有导入成功", extra={"log_type": "STAGE_NODE"})
        return True
    except Exception as e:
        log.error(f"❌ 导入失败: {e}", extra={"log_type": "STAGE_NODE"}, exc_info=True)
        return False

def test_orchestrator_creation():
    """测试创建启动编排器"""
    log.info("\n" + "=" * 70, extra={"log_type": "STAGE_NODE"})
    log.info("测试2: 启动编排器创建测试", extra={"log_type": "STAGE_NODE"})
    log.info("=" * 70, extra={"log_type": "STAGE_NODE"})
    
    try:
        from backend.startup import StartupOrchestrator
        
        orchestrator = StartupOrchestrator()
        log.info("✅ StartupOrchestrator 创建成功", extra={"log_type": "STAGE_NODE"})
        return True
    except Exception as e:
        log.error(f"❌ StartupOrchestrator 创建失败: {e}", extra={"log_type": "STAGE_NODE"}, exc_info=True)
        return False

def test_stages_creation():
    """测试创建所有阶段"""
    log.info("\n" + "=" * 70, extra={"log_type": "STAGE_NODE"})
    log.info("测试3: 阶段创建测试", extra={"log_type": "STAGE_NODE"})
    log.info("=" * 70, extra={"log_type": "STAGE_NODE"})
    
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
        
        log.info(f"✅ 所有阶段创建成功（共 {len(stages)} 个阶段）", extra={"log_type": "STAGE_NODE"})
        for stage in stages:
            log.info(f"   - {stage.name}: {stage.description}", extra={"log_type": "STAGE_NODE"})
        return True
    except Exception as e:
        log.error(f"❌ 阶段创建失败: {e}", extra={"log_type": "STAGE_NODE"}, exc_info=True)
        return False

def test_workers_creation():
    """测试创建所有Worker"""
    log.info("\n" + "=" * 70, extra={"log_type": "STAGE_NODE"})
    log.info("测试4: Worker创建测试", extra={"log_type": "STAGE_NODE"})
    log.info("=" * 70, extra={"log_type": "STAGE_NODE"})
    
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
        
        log.info(f"✅ 所有Worker创建成功（共 {len(workers)} 个Worker）", extra={"log_type": "STAGE_NODE"})
        for worker in workers:
            log.info(f"   - {worker.name}: {worker.description}", extra={"log_type": "STAGE_NODE"})
        return True
    except Exception as e:
        log.error(f"❌ Worker创建失败: {e}", extra={"log_type": "STAGE_NODE"}, exc_info=True)
        return False

def test_context_creation():
    """测试创建启动上下文"""
    log.info("\n" + "=" * 70, extra={"log_type": "STAGE_NODE"})
    log.info("测试5: 启动上下文创建测试", extra={"log_type": "STAGE_NODE"})
    log.info("=" * 70, extra={"log_type": "STAGE_NODE"})
    
    try:
        from backend.startup import StartupContext
        
        context = StartupContext()
        log.info("✅ StartupContext 创建成功", extra={"log_type": "STAGE_NODE"})
        log.info(f"   - 项目根目录: {context.project_root}", extra={"log_type": "STAGE_NODE"})
        log.info(f"   - 配置文件: {context.config_file}", extra={"log_type": "STAGE_NODE"})
        return True
    except Exception as e:
        log.error(f"❌ StartupContext 创建失败: {e}", extra={"log_type": "STAGE_NODE"}, exc_info=True)
        return False

def test_orchestrator_setup():
    """测试设置启动编排器"""
    log.info("\n" + "=" * 70, extra={"log_type": "STAGE_NODE"})
    log.info("测试6: 启动编排器设置测试", extra={"log_type": "STAGE_NODE"})
    log.info("=" * 70, extra={"log_type": "STAGE_NODE"})
    
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
        
        log.info(f"✅ 启动编排器设置成功（共 {len(orchestrator.stages)} 个阶段）", extra={"log_type": "STAGE_NODE"})
        for stage in orchestrator.stages:
            log.info(f"   - {stage.name}: {stage.description}", extra={"log_type": "STAGE_NODE"})
        
        # 验证上下文
        context = orchestrator.get_context()
        log.info("✅ 启动上下文获取成功", extra={"log_type": "STAGE_NODE"})
        
        return True
    except Exception as e:
        log.error(f"❌ 启动编排器设置失败: {e}", extra={"log_type": "STAGE_NODE"}, exc_info=True)
        return False

def test_logging_system():
    """测试日志系统"""
    log.info("\n" + "=" * 70, extra={"log_type": "STAGE_NODE"})
    log.info("测试7: 日志系统测试", extra={"log_type": "STAGE_NODE"})
    log.info("=" * 70, extra={"log_type": "STAGE_NODE"})
    
    try:
        from backend.startup.startup_logging.startup_logger import (
            StartupLogger,
            OrderedLogQueue,
        )

        # 测试StartupLogger
        logger = StartupLogger()
        log.info("✅ StartupLogger 创建成功", extra={"log_type": "STAGE_NODE"})

        # 测试OrderedLogQueue
        queue = OrderedLogQueue(max_wait_seconds=30)
        log.info("✅ OrderedLogQueue 创建成功", extra={"log_type": "STAGE_NODE"})

        # 🔧 优化：StartupAILogHandler已删除，AI日志统一通过LoggingHub的AILogFileHandler处理
        log.info("✅ StartupAILogHandler已移除，AI日志由LoggingHub统一处理", extra={"log_type": "STAGE_NODE"})
        
        return True
    except Exception as e:
        log.error(f"❌ 日志系统测试失败: {e}", extra={"log_type": "STAGE_NODE"}, exc_info=True)
        return False

def main():
    """主测试函数"""
    log.info("=" * 70, extra={"log_type": "STAGE_NODE"})
    log.info("🚀 启动架构集成测试", extra={"log_type": "STAGE_NODE"})
    log.info("=" * 70, extra={"log_type": "STAGE_NODE"})
    log.info("", extra={"log_type": "STAGE_NODE"})
    
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
            log.error(f"\n❌ 测试 '{name}' 发生异常: {e}", extra={"log_type": "STAGE_NODE"}, exc_info=True)
            results.append((name, False))
    
    # 汇总结果
    log.info("\n" + "=" * 70, extra={"log_type": "STAGE_NODE"})
    log.info("测试结果汇总", extra={"log_type": "STAGE_NODE"})
    log.info("=" * 70, extra={"log_type": "STAGE_NODE"})
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        log.info(f"{status}: {name}", extra={"log_type": "STAGE_NODE"})
    
    log.info("\n" + "=" * 70, extra={"log_type": "STAGE_NODE"})
    log.info(f"总计: {passed}/{total} 测试通过", extra={"log_type": "STAGE_NODE"})
    log.info("=" * 70, extra={"log_type": "STAGE_NODE"})
    
    if passed == total:
        log.info("\n🎉 所有测试通过！", extra={"log_type": "STAGE_NODE"})
        return 0
    else:
        log.warning(f"\n⚠️ {total - passed} 个测试失败", extra={"log_type": "STAGE_NODE"})
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)

