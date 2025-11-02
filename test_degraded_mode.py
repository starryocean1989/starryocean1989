#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
降级模式测试脚本

测试SystemManagerService在没有管理员权限时的降级功能。
"""

import logging
import sys
import time
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_degraded_mode():
    """测试降级模式功能"""
    try:
        logger.info("🔍 开始测试降级模式功能...")
        
        # 1. 检查当前权限
        logger.info("📊 步骤1: 检查当前权限状态")
        try:
            import ctypes
            is_admin = ctypes.windll.shell32.IsUserAnAdmin()
            logger.info(f"当前权限状态: {'管理员' if is_admin else '普通用户'}")
        except Exception:
            logger.info("当前权限状态: 无法检测（可能是非Windows系统）")
        
        # 2. 创建SystemManagerService实例
        logger.info("📊 步骤2: 创建SystemManagerService实例")
        from backend.services.system_manager_service import SystemManagerService
        
        # 获取真实的MainEngine
        from backend.core.base import get_main_engine
        
        main_engine = get_main_engine()
        if not main_engine:
            logger.warning("⚠️ MainEngine未初始化，创建模拟引擎")
            class MockMainEngine:
                def __init__(self):
                    self.event_engine = None
            main_engine = MockMainEngine()
        
        # 创建SystemManagerService
        system_service = SystemManagerService()
        logger.info("✅ SystemManagerService实例已创建")
        
        # 3. 检查权限检查功能
        logger.info("📊 步骤3: 测试权限检查功能")
        has_admin = system_service._check_admin_privileges()
        logger.info(f"权限检查结果: {'有管理员权限' if has_admin else '无管理员权限'}")
        
        # 4. 初始化服务
        logger.info("📊 步骤4: 初始化SystemManagerService")
        try:
            # 设置MainEngine
            system_service.main_engine = main_engine
            success = system_service.initialize()
            if success:
                logger.info("✅ SystemManagerService初始化成功")
                logger.info(f"IPC模式: {system_service._ipc_mode}")
                logger.info(f"IPC可用: {system_service._ipc_available}")
            else:
                logger.error("❌ SystemManagerService初始化失败")
                return False
        except Exception as e:
            logger.error("❌ SystemManagerService初始化异常: %s", e, exc_info=True)
            return False
        
        # 5. 测试数据获取
        logger.info("📊 步骤5: 测试监控数据获取")
        for i in range(3):
            logger.info(f"第{i+1}次数据获取测试...")
            data = system_service.get_current_monitoring_data()
            
            if data:
                logger.info("✅ 数据获取成功")
                logger.info(f"   数据模式: {data.get('mode', 'unknown')}")
                logger.info(f"   数据源: {data.get('source', 'unknown')}")
                logger.info(f"   时间戳: {data.get('timestamp', 'unknown')}")
                
                if 'system' in data:
                    system_data = data['system']
                    logger.info(f"   系统数据字段: {list(system_data.keys())}")
                    
                    if 'cpu_percent' in system_data:
                        logger.info(f"   CPU使用率: {system_data['cpu_percent']}%")
                    if 'memory_percent' in system_data:
                        logger.info(f"   内存使用率: {system_data['memory_percent']}%")
                
                if 'message' in data:
                    logger.info(f"   提示信息: {data['message']}")
                    
            else:
                logger.warning("⚠️ 数据获取返回空")
            
            if i < 2:  # 不是最后一次
                time.sleep(2)
        
        # 6. 测试健康检查
        logger.info("📊 步骤6: 测试健康检查")
        health = system_service.health_check()
        logger.info("健康检查结果:")
        for key, value in health.items():
            logger.info(f"   {key}: {value}")
        
        # 7. 清理
        logger.info("📊 步骤7: 清理资源")
        try:
            system_service.shutdown()
            logger.info("✅ SystemManagerService已关闭")
        except Exception as e:
            logger.warning("⚠️ 关闭SystemManagerService时出错: %s", e)
        
        logger.info("🎉 降级模式测试完成！")
        return True
        
    except Exception as e:
        logger.error("❌ 测试过程中发生异常: %s", e, exc_info=True)
        return False

if __name__ == "__main__":
    success = test_degraded_mode()
    if success:
        print("\n🎉 降级模式测试成功！")
        print("SystemManagerService可以在没有管理员权限的情况下正常工作。")
        sys.exit(0)
    else:
        print("\n❌ 降级模式测试失败！")
        sys.exit(1)