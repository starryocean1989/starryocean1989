#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
IPC重连修复验证脚本

测试SystemManagerService的IPC重连功能是否正常工作。
"""

import asyncio
import json
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

def test_ipc_reconnect():
    """测试IPC重连功能"""
    try:
        logger.info("🔍 开始测试IPC重连功能...")
        
        # 1. 检查监控进程是否运行
        logger.info("📊 步骤1: 检查监控进程状态")
        import psutil
        
        monitor_processes = []
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                if proc.info['cmdline'] and any('monitor_system.py' in arg for arg in proc.info['cmdline']):
                    monitor_processes.append(proc)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        if not monitor_processes:
            logger.error("❌ 监控进程未运行，请先启动系统")
            return False
        
        logger.info(f"✅ 找到 {len(monitor_processes)} 个监控进程")
        for proc in monitor_processes:
            logger.info(f"   PID: {proc.pid}, 命令: {' '.join(proc.cmdline())}")
        
        # 2. 测试原始IPC连接
        logger.info("📊 步骤2: 测试原始IPC连接")
        if not test_basic_ipc_connection():
            logger.error("❌ 基础IPC连接失败")
            return False
        
        # 3. 创建SystemManagerService实例
        logger.info("📊 步骤3: 创建SystemManagerService实例")
        from backend.services.system_manager_service import SystemManagerService
        from backend.core.base import get_main_engine
        
        # 获取MainEngine
        main_engine = get_main_engine()
        if not main_engine:
            logger.error("❌ MainEngine未初始化")
            return False
        
        # 创建SystemManagerService
        system_service = SystemManagerService()
        if not system_service.initialize(main_engine):
            logger.error("❌ SystemManagerService初始化失败")
            return False
        
        logger.info("✅ SystemManagerService初始化成功")
        
        # 4. 测试正常查询
        logger.info("📊 步骤4: 测试正常监控数据查询")
        data = system_service.get_current_monitoring_data()
        if data:
            logger.info("✅ 正常查询成功，数据字段: %s", list(data.keys()))
        else:
            logger.warning("⚠️ 正常查询返回空数据")
        
        # 5. 模拟连接断开（通过直接关闭管道）
        logger.info("📊 步骤5: 模拟IPC连接断开")
        if system_service._query_pipe:
            try:
                # 关闭查询管道来模拟连接断开
                asyncio.run_coroutine_threadsafe(
                    system_service._close_pipe(system_service._query_pipe), 
                    system_service._ipc_loop
                ).result(timeout=5.0)
                system_service._query_pipe = None
                logger.info("✅ 已模拟连接断开")
            except Exception as e:
                logger.error("❌ 模拟连接断开失败: %s", e)
                return False
        
        # 6. 测试重连功能
        logger.info("📊 步骤6: 测试IPC重连功能")
        time.sleep(2)  # 等待一下
        
        reconnect_success = system_service._test_ipc_connection()
        if reconnect_success:
            logger.info("✅ IPC重连成功")
        else:
            logger.error("❌ IPC重连失败")
            return False
        
        # 7. 测试重连后的查询
        logger.info("📊 步骤7: 测试重连后的监控数据查询")
        data_after_reconnect = system_service.get_current_monitoring_data()
        if data_after_reconnect:
            logger.info("✅ 重连后查询成功，数据字段: %s", list(data_after_reconnect.keys()))
        else:
            logger.warning("⚠️ 重连后查询返回空数据")
        
        # 8. 清理
        logger.info("📊 步骤8: 清理资源")
        try:
            system_service.shutdown()
            logger.info("✅ SystemManagerService已关闭")
        except Exception as e:
            logger.warning("⚠️ 关闭SystemManagerService时出错: %s", e)
        
        logger.info("🎉 IPC重连功能测试完成！")
        return True
        
    except Exception as e:
        logger.error("❌ 测试过程中发生异常: %s", e, exc_info=True)
        return False

def test_basic_ipc_connection():
    """测试基础IPC连接"""
    try:
        from backend.infrastructure.native_ipc import aopen_client, IPC_AVAILABLE
        
        if not IPC_AVAILABLE:
            logger.error("❌ IPC扩展不可用")
            return False
        
        async def test_connection():
            try:
                async with await aopen_client("monitor_query") as pipe:
                    logger.info("✅ 基础IPC连接成功")
                    
                    # 发送测试请求
                    request = {"action": "get_data"}
                    request_bytes = json.dumps(request).encode('utf-8')
                    
                    await pipe.write(request_bytes)
                    response_bytes = await asyncio.wait_for(pipe.read(size=65536), timeout=3.0)
                    
                    if response_bytes:
                        response = json.loads(response_bytes.decode('utf-8'))
                        logger.info("✅ 基础IPC通信成功，响应字段: %s", list(response.keys()) if isinstance(response, dict) else type(response))
                        return True
                    else:
                        logger.warning("⚠️ 基础IPC通信无响应")
                        return False
                        
            except Exception as e:
                logger.error("❌ 基础IPC连接失败: %s", e)
                return False
        
        return asyncio.run(test_connection())
        
    except Exception as e:
        logger.error("❌ 基础IPC测试异常: %s", e)
        return False

if __name__ == "__main__":
    success = test_ipc_reconnect()
    if success:
        print("\n🎉 IPC重连修复验证成功！")
        sys.exit(0)
    else:
        print("\n❌ IPC重连修复验证失败！")
        sys.exit(1)