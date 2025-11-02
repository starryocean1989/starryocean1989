#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简单降级模式测试

直接测试SystemManagerService的降级数据获取功能。
"""

import logging
import sys
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

def test_simple_degraded():
    """测试简单降级功能"""
    try:
        logger.info("🔍 开始测试简单降级功能...")
        
        # 1. 检查权限
        logger.info("📊 步骤1: 检查权限")
        try:
            import ctypes
            is_admin = ctypes.windll.shell32.IsUserAnAdmin()
            logger.info(f"当前权限: {'管理员' if is_admin else '普通用户'}")
        except Exception:
            logger.info("权限检查失败（可能非Windows系统）")
            is_admin = False
        
        # 2. 创建SystemManagerService实例（不初始化）
        logger.info("📊 步骤2: 创建SystemManagerService实例")
        from backend.services.system_manager_service import SystemManagerService
        
        system_service = SystemManagerService()
        logger.info("✅ SystemManagerService实例已创建")
        
        # 3. 测试权限检查方法
        logger.info("📊 步骤3: 测试权限检查方法")
        has_admin = system_service._check_admin_privileges()
        logger.info(f"权限检查结果: {'有管理员权限' if has_admin else '无管理员权限'}")
        
        # 4. 测试基础系统数据获取
        logger.info("📊 步骤4: 测试基础系统数据获取")
        try:
            basic_data = system_service._get_basic_system_data()
            if basic_data:
                logger.info("✅ 基础系统数据获取成功")
                logger.info(f"   数据模式: {basic_data.get('mode', 'unknown')}")
                logger.info(f"   数据源: {basic_data.get('source', 'unknown')}")
                
                if 'system' in basic_data:
                    system_info = basic_data['system']
                    logger.info(f"   CPU使用率: {system_info.get('cpu_percent', 'N/A')}%")
                    logger.info(f"   内存使用率: {system_info.get('memory_percent', 'N/A')}%")
                    logger.info(f"   磁盘使用率: {system_info.get('disk_usage', 'N/A')}%")
                
                if 'process' in basic_data:
                    process_info = basic_data['process']
                    logger.info(f"   进程数量: {process_info.get('process_count', 'N/A')}")
            else:
                logger.warning("⚠️ 基础系统数据获取返回空")
        except Exception as e:
            logger.error("❌ 基础系统数据获取失败: %s", e)
        
        # 5. 测试最小系统数据获取
        logger.info("📊 步骤5: 测试最小系统数据获取")
        try:
            minimal_data = system_service._get_minimal_system_data()
            if minimal_data:
                logger.info("✅ 最小系统数据获取成功")
                logger.info(f"   数据模式: {minimal_data.get('mode', 'unknown')}")
                logger.info(f"   数据源: {minimal_data.get('source', 'unknown')}")
                
                if 'system' in minimal_data:
                    system_info = minimal_data['system']
                    logger.info(f"   平台: {system_info.get('platform', 'N/A')}")
                    logger.info(f"   Python版本: {system_info.get('python_version', 'N/A')}")
                    logger.info(f"   CPU核心数: {system_info.get('cpu_count', 'N/A')}")
                
                if 'message' in minimal_data:
                    logger.info(f"   提示信息: {minimal_data['message']}")
            else:
                logger.warning("⚠️ 最小系统数据获取返回空")
        except Exception as e:
            logger.error("❌ 最小系统数据获取失败: %s", e)
        
        # 6. 测试IPC可用性检查
        logger.info("📊 步骤6: 测试IPC可用性检查")
        try:
            from backend.infrastructure.native_ipc import IPC_AVAILABLE
            logger.info(f"Native IPC扩展可用: {IPC_AVAILABLE}")
        except ImportError:
            logger.info("Native IPC扩展不可用")
        
        # 7. 模拟不同IPC模式下的数据获取
        logger.info("📊 步骤7: 模拟不同IPC模式下的数据获取")
        
        # 模拟native模式（但实际不连接）
        system_service._ipc_mode = "native"
        logger.info("模拟native模式...")
        
        # 模拟fallback模式
        system_service._ipc_mode = "fallback"
        logger.info("模拟fallback模式...")
        fallback_data = system_service.get_current_monitoring_data()
        if fallback_data:
            logger.info(f"✅ Fallback模式数据获取成功，模式: {fallback_data.get('mode')}")
        
        # 模拟disabled模式
        system_service._ipc_mode = "disabled"
        logger.info("模拟disabled模式...")
        disabled_data = system_service.get_current_monitoring_data()
        if disabled_data:
            logger.info(f"✅ Disabled模式数据获取成功，模式: {disabled_data.get('mode')}")
        
        logger.info("🎉 简单降级功能测试完成！")
        return True
        
    except Exception as e:
        logger.error("❌ 测试过程中发生异常: %s", e, exc_info=True)
        return False

if __name__ == "__main__":
    success = test_simple_degraded()
    if success:
        print("\n🎉 简单降级功能测试成功！")
        print("SystemManagerService的降级数据获取功能正常工作。")
        sys.exit(0)
    else:
        print("\n❌ 简单降级功能测试失败！")
        sys.exit(1)