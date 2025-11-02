# -*- coding: utf-8 -*-
"""
测试监控系统IPC通信

直接测试现有的监控进程IPC通信
"""

import asyncio
import json
import logging
import sys
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from backend.infrastructure.native_ipc import AsyncIPCPipe, IPC_AVAILABLE

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_monitor_query():
    """测试监控进程查询"""
    if not IPC_AVAILABLE:
        logger.error("IPC扩展不可用")
        return False
    
    try:
        logger.info("连接到监控进程查询管道...")
        async with await AsyncIPCPipe.client("monitor_query") as pipe:
            logger.info("✅ 连接成功")
            
            # 发送查询请求
            request = {"action": "get_data"}
            request_bytes = json.dumps(request).encode()
            logger.info(f"发送查询请求: {request}")
            await pipe.write(request_bytes)
            
            # 接收响应（使用大缓冲区）
            logger.info("等待响应...")
            response_data = await asyncio.wait_for(pipe.read(size=65536), timeout=5.0)
            logger.info(f"收到响应，数据大小: {len(response_data)} bytes")
            
            # 尝试解析JSON
            try:
                response = json.loads(response_data.decode())
                logger.info("✅ JSON解析成功")
                logger.info(f"响应包含字段: {list(response.keys())}")
                
                # 检查关键字段
                if "timestamp" in response:
                    logger.info(f"时间戳: {response['timestamp']}")
                if "system" in response:
                    logger.info("✅ 包含系统监控数据")
                if "process" in response:
                    logger.info("✅ 包含进程监控数据")
                if "hardware" in response:
                    logger.info("✅ 包含硬件监控数据")
                
                return True
                
            except json.JSONDecodeError as e:
                logger.error(f"❌ JSON解析失败: {e}")
                logger.error(f"数据前200字符: {response_data[:200]}")
                logger.error(f"数据后200字符: {response_data[-200:]}")
                
                # 检查是否是截断问题
                if len(response_data) >= 4096:
                    logger.error("⚠️ 数据可能被截断（大小>=4096）")
                
                return False
                
    except asyncio.TimeoutError:
        logger.error("❌ 查询超时，监控进程可能未响应")
        return False
    except Exception as e:
        logger.error(f"❌ 查询失败: {e}")
        return False

async def test_monitor_status():
    """测试监控进程状态"""
    # 检查监控进程是否运行
    signal_file = Path("logs/monitor_ready.signal")
    if signal_file.exists():
        try:
            with open(signal_file, 'r') as f:
                signal_data = json.load(f)
            logger.info(f"✅ 监控进程运行中，PID: {signal_data.get('pid')}")
            logger.info(f"状态: {signal_data.get('status')}")
            logger.info(f"就绪级别: {signal_data.get('level')}")
            return True
        except Exception as e:
            logger.error(f"❌ 读取监控信号文件失败: {e}")
            return False
    else:
        logger.error("❌ 监控进程未运行（信号文件不存在）")
        return False

async def main():
    """主函数"""
    logger.info("开始监控系统IPC通信测试...")
    
    if not IPC_AVAILABLE:
        logger.error("❌ IPC扩展不可用")
        return
    
    # 检查监控进程状态
    logger.info("\n=== 检查监控进程状态 ===")
    status_ok = await test_monitor_status()
    
    if not status_ok:
        logger.error("监控进程未运行，请先启动终端")
        return
    
    # 测试IPC查询
    logger.info("\n=== 测试IPC查询 ===")
    query_ok = await test_monitor_query()
    
    if query_ok:
        logger.info("🎉 IPC通信测试成功！")
    else:
        logger.error("❌ IPC通信测试失败")

if __name__ == "__main__":
    asyncio.run(main())