# -*- coding: utf-8 -*-
"""
启动执行顺序验证测试

验证启动流程符合启动完整设计文档（1062-1137行）的要求：
- 单一事实原则：任何方法不能在不同阶段重复执行
- 执行顺序正确：各阶段按文档规定的顺序执行
"""

import pytest
import asyncio
from pathlib import Path
from typing import Dict, List, Any
from unittest.mock import Mock, patch

# 导入启动相关模块
from backend.startup import (
    StartupOrchestrator,
    EnvSetupStage,
    LoggingInitStage,
    QtFrameworkStage,
    BackendInitStage,
    UIActivationStage,
)
from backend.startup.context import StartupContext
from backend.core.base import get_event_engine, get_main_engine


class TestStartupExecutionOrder:
    """启动执行顺序测试"""

    def test_stage2_presets_eventengine_and_mainengine(self):
        """测试阶段2预创建EventEngine和MainEngine
        
        根据启动完整设计文档1081-1082行：
        - 阶段2应该预创建EventEngine
        - 阶段2应该预创建MainEngine
        """
        # 清空全局引擎
        from backend.core.base import set_event_engine, set_main_engine
        set_event_engine(None)
        set_main_engine(None)
        
        context = StartupContext()
        stage = QtFrameworkStage()
        
        # 执行阶段2
        result = asyncio.run(stage.execute(context))
        
        assert result.success, "阶段2应该成功执行"
        assert context.event_engine is not None, "阶段2应该预创建EventEngine"
        assert context.main_engine is not None, "阶段2应该预创建MainEngine"
        
        # 验证引擎已注册到全局
        assert get_event_engine() is not None, "EventEngine应该注册到全局"
        assert get_main_engine() is not None, "MainEngine应该注册到全局"
        
        # 验证是同一个实例（单一事实原则）
        assert get_event_engine() is context.event_engine, "全局EventEngine应该是阶段2创建的实例"
        assert get_main_engine() is context.main_engine, "全局MainEngine应该是阶段2创建的实例"

    def test_stage3_uses_preset_engines(self):
        """测试阶段3使用阶段2预创建的引擎（单一事实原则）
        
        根据启动完整设计文档1088-1090行：
        - 阶段3.1应该检查全局引擎，如果存在则使用，不重复创建
        """
        # 先执行阶段2，预创建引擎
        context = StartupContext()
        stage2 = QtFrameworkStage()
        asyncio.run(stage2.execute(context))
        
        # 记录阶段2创建的引擎ID
        event_engine_id = id(context.event_engine)
        main_engine_id = id(context.main_engine)
        
        # 执行阶段3
        stage3 = BackendInitStage()
        # 只测试_initialize_vnpy_core方法
        asyncio.run(stage3._initialize_vnpy_core(context))
        
        # 验证引擎没有被重新创建（单一事实原则）
        assert id(context.event_engine) == event_engine_id, "EventEngine不应该被重新创建"
        assert id(context.main_engine) == main_engine_id, "MainEngine不应该被重新创建"
        
        # 验证全局引擎没有被替换
        assert id(get_event_engine()) == event_engine_id, "全局EventEngine不应该被替换"
        assert id(get_main_engine()) == main_engine_id, "全局MainEngine不应该被替换"

    def test_service_initializer_uses_preset_engines(self):
        """测试ServiceInitializer使用阶段2预创建的引擎（单一事实原则）
        
        根据启动完整设计文档：
        - ServiceInitializer._initialize_vnpy_core应该检查全局引擎，如果存在则使用
        """
        # 先执行阶段2，预创建引擎
        context = StartupContext()
        stage2 = QtFrameworkStage()
        asyncio.run(stage2.execute(context))
        
        # 记录阶段2创建的引擎ID
        event_engine_id = id(context.event_engine)
        main_engine_id = id(context.main_engine)
        
        # 执行ServiceInitializer._initialize_vnpy_core
        from backend.startup.initializers.service_initializer import ServiceInitializer
        from backend.core.base import get_service_manager
        
        service_manager = get_service_manager()
        initializer = ServiceInitializer(service_manager)
        initializer._initialize_vnpy_core()
        
        # 验证引擎没有被重新创建（单一事实原则）
        assert id(initializer.event_engine) == event_engine_id, "ServiceInitializer应该使用阶段2预创建的EventEngine"
        assert id(initializer.main_engine) == main_engine_id, "ServiceInitializer应该使用阶段2预创建的MainEngine"
        
        # 验证全局引擎没有被替换
        assert id(get_event_engine()) == event_engine_id, "全局EventEngine不应该被替换"
        assert id(get_main_engine()) == main_engine_id, "全局MainEngine不应该被替换"

    def test_no_duplicate_engine_creation(self):
        """测试引擎不会被重复创建
        
        单一事实原则：EventEngine和MainEngine应该只在阶段2创建一次
        """
        # 清空全局引擎
        from backend.core.base import set_event_engine, set_main_engine
        set_event_engine(None)
        set_main_engine(None)
        
        # 创建追踪器，记录引擎创建次数
        creation_count = {"EventEngine": 0, "MainEngine": 0}
        
        original_event_engine_init = None
        original_main_engine_init = None
        
        try:
            from vnpy.event import EventEngine
            from vnpy.trader.engine import MainEngine
            
            # 保存原始__init__方法
            original_event_engine_init = EventEngine.__init__
            original_main_engine_init = MainEngine.__init__
            
            # 包装__init__方法以追踪创建次数
            def track_event_engine_init(self, *args, **kwargs):
                creation_count["EventEngine"] += 1
                return original_event_engine_init(self, *args, **kwargs)
            
            def track_main_engine_init(self, *args, **kwargs):
                creation_count["MainEngine"] += 1
                return original_main_engine_init(self, *args, **kwargs)
            
            # 替换__init__方法
            EventEngine.__init__ = track_event_engine_init
            MainEngine.__init__ = track_main_engine_init
            
            # 执行完整的启动流程
            orchestrator = StartupOrchestrator()
            orchestrator.add_stage(EnvSetupStage())
            orchestrator.add_stage(LoggingInitStage())
            orchestrator.add_stage(QtFrameworkStage())
            orchestrator.add_stage(BackendInitStage())
            
            # 只执行到阶段3，不执行UI阶段（避免需要GUI环境）
            result = asyncio.run(orchestrator.startup())
            
            # 验证引擎只创建了一次
            assert creation_count["EventEngine"] == 1, f"EventEngine应该只创建一次，实际创建了{creation_count['EventEngine']}次"
            assert creation_count["MainEngine"] == 1, f"MainEngine应该只创建一次，实际创建了{creation_count['MainEngine']}次"
            
        finally:
            # 恢复原始__init__方法
            if original_event_engine_init:
                EventEngine.__init__ = original_event_engine_init
            if original_main_engine_init:
                MainEngine.__init__ = original_main_engine_init

    def test_stage_execution_order(self):
        """测试阶段执行顺序
        
        根据启动完整设计文档，阶段应该按顺序执行：
        - 阶段0: EnvSetupStage
        - 阶段1: LoggingInitStage
        - 阶段2: QtFrameworkStage
        - 阶段3: BackendInitStage
        """
        execution_order = []
        
        # 创建带追踪的阶段
        class TrackedStage:
            def __init__(self, name):
                self.name = name
            
            async def execute(self, context):
                execution_order.append(self.name)
                return type('StageResult', (), {'success': True, 'message': '', 'elapsed_ms': 0})()
        
        orchestrator = StartupOrchestrator()
        
        # 添加阶段（简化版本，不实际执行）
        # 注意：实际测试应该使用真实的阶段实例
        
        # 验证阶段顺序（预期顺序）
        expected_order = ["env_setup", "logging_init", "qt_framework", "backend_init"]
        
        # 注意：这个测试需要实际运行启动流程才能验证
        # 这里只是示例，实际测试应该使用mock或实际执行

    @pytest.mark.skip(reason="需要完整的启动环境，暂不执行")
    def test_full_startup_order(self):
        """完整启动流程测试（需要完整环境）
        
        测试完整的启动流程是否符合文档要求
        """
        orchestrator = StartupOrchestrator()
        orchestrator.add_stage(EnvSetupStage())
        orchestrator.add_stage(LoggingInitStage())
        orchestrator.add_stage(QtFrameworkStage())
        orchestrator.add_stage(BackendInitStage())
        
        result = asyncio.run(orchestrator.startup())
        
        assert result.success, "启动应该成功"
        
        context = orchestrator.get_context()
        
        # 验证各阶段结果
        assert "env_setup" in result.stage_results, "应该有env_setup阶段结果"
        assert "logging_init" in result.stage_results, "应该有logging_init阶段结果"
        assert "qt_framework" in result.stage_results, "应该有qt_framework阶段结果"
        assert "backend_init" in result.stage_results, "应该有backend_init阶段结果"
        
        # 验证引擎已正确创建
        assert context.event_engine is not None, "EventEngine应该已创建"
        assert context.main_engine is not None, "MainEngine应该已创建"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

