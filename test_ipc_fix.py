# -*- coding: utf-8 -*-
"""
测试IPC通信修复

验证native_ipc缓冲区大小修复是否有效
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

async def test_large_data_transfer():
    """测试大数据传输"""
    if not IPC_AVAILABLE:
        logger.error("IPC扩展不可用，请编译C扩展")
        return False
    
    # 创建测试数据（模拟监控数据）
    test_data = {
        "timestamp": "2025-11-02T14:30:00",
        "system": {
            "cpu_percent": 45.2,
            "memory_percent": 67.8,
            "disk_io": {"read_bytes": 1024000, "write_bytes": 512000},
            "network_io": {"bytes_sent": 2048000, "bytes_recv": 1536000}
        },
        "process": {
            "processes": [
                {
                    "pid": i,
                    "name": f"process_{i}",
                    "cpu_percent": 1.2 + i * 0.1,
                    "memory_percent": 2.3 + i * 0.2,
                    "memory_info": {
                        "rss": 1024000 + i * 1000,
                        "vms": 2048000 + i * 2000
                    },
                    "cmdline": [f"/usr/bin/process_{i}", "--config", f"/etc/config_{i}.conf"]
                }
                for i in range(100)  # 100个进程，模拟大数据
            ]
        },
        "hardware": {
            "temperature": [
                {"name": f"CPU Core #{i}", "value": 45.0 + i, "unit": "°C"}
                for i in range(16)
            ],
            "fan": [
                {"name": f"Fan #{i}", "value": 1200 + i * 100, "unit": "RPM"}
                for i in range(8)
            ]
        },
        "smart": {
            f"Disk_{i}": {
                "model": f"Samsung SSD 980 PRO {i}TB",
                "serial": f"S6B2NS0T{i:06d}",
                "attributes": [
                    {"id": 5, "name": "Reallocated_Sector_Ct", "value": 0},
                    {"id": 9, "name": "Power_On_Hours", "value": 1000 + i * 100},
                    {"id": 194, "name": "Temperature_Celsius", "value": 35 + i},
                ]
            }
            for i in range(4)
        }
    }
    
    # 序列化测试数据
    test_json = json.dumps(test_data, separators=(',', ':'))
    test_bytes = test_json.encode()
    
    logger.info(f"测试数据大小: {len(test_bytes)} bytes")
    
    if len(test_bytes) < 4096:
        logger.warning("测试数据小于4KB，增加更多数据")
        # 添加更多数据确保超过4KB
        for i in range(200):
            test_data["process"]["processes"].append({
                "pid": 1000 + i,
                "name": f"large_process_{i}",
                "cpu_percent": 0.1,
                "memory_percent": 0.2,
                "memory_info": {"rss": 1024000, "vms": 2048000},
                "cmdline": [f"/usr/bin/large_process_{i}", "--very-long-config-path", f"/etc/very/long/path/to/config/file_{i}.conf"]
            })
        test_json = json.dumps(test_data, separators=(',', ':'))
        test_bytes = test_json.encode()
        logger.info(f"扩展后测试数据大小: {len(test_bytes)} bytes")
    
    try:
        # 启动服务端
        server_task = asyncio.create_task(run_server(test_bytes))
        await asyncio.sleep(0.5)  # 等待服务端启动
        
        # 启动客户端
        client_task = asyncio.create_task(run_client())
        
        # 等待完成
        server_result, client_result = await asyncio.gather(server_task, client_task, return_exceptions=True)
        
        if isinstance(server_result, Exception):
            logger.error(f"服务端错误: {server_result}")
            return False
        
        if isinstance(client_result, Exception):
            logger.error(f"客户端错误: {client_result}")
            return False
        
        # 验证数据完整性
        if client_result == test_bytes:
            logger.info("✅ 大数据传输测试成功")
            return True
        else:
            logger.error(f"❌ 数据不匹配，发送: {len(test_bytes)} bytes，接收: {len(client_result) if client_result else 0} bytes")
            return False
            
    except Exception as e:
        logger.error(f"测试失败: {e}")
        return False

async def run_server(test_data: bytes):
    """运行服务端"""
    try:
        async with await AsyncIPCPipe.server("test_large_data") as pipe:
            logger.info("服务端启动，等待客户端连接...")
            
            # 等待客户端请求
            request_data = await pipe.read(size=1024)
            request = json.loads(request_data.decode())
            logger.info(f"收到客户端请求: {request}")
            
            # 发送大数据
            logger.info(f"发送数据，大小: {len(test_data)} bytes")
            await pipe.write(test_data)
            logger.info("数据发送完成")
            
    except Exception as e:
        logger.error(f"服务端错误: {e}")
        raise

async def run_client():
    """运行客户端"""
    try:
        async with await AsyncIPCPipe.client("test_large_data") as pipe:
            logger.info("客户端连接成功")
            
            # 发送请求
            request = {"action": "get_large_data"}
            request_bytes = json.dumps(request).encode()
            await pipe.write(request_bytes)
            logger.info("请求已发送")
            
            # 接收大数据（使用大缓冲区）
            logger.info("接收数据...")
            response_data = await pipe.read(size=65536)  # 64KB缓冲区
            logger.info(f"接收到数据，大小: {len(response_data)} bytes")
            
            # 验证JSON格式
            try:
                parsed_data = json.loads(response_data.decode())
                logger.info("✅ JSON解析成功")
                return response_data
            except json.JSONDecodeError as e:
                logger.error(f"❌ JSON解析失败: {e}")
                logger.error(f"数据前100字符: {response_data[:100]}")
                logger.error(f"数据后100字符: {response_data[-100:]}")
                return None
            
    except Exception as e:
        logger.error(f"客户端错误: {e}")
        raise

async def main():
    """主函数"""
    logger.info("开始IPC大数据传输测试...")
    
    if not IPC_AVAILABLE:
        logger.error("❌ IPC扩展不可用")
        logger.info("请运行以下命令编译C扩展:")
        logger.info("cd backend/infrastructure/native_ipc")
        logger.info("python setup.py build_ext --inplace")
        return
    
    success = await test_large_data_transfer()
    
    if success:
        logger.info("🎉 所有测试通过！IPC大数据传输修复成功")
    else:
        logger.error("❌ 测试失败，需要进一步调试")

if __name__ == "__main__":
    asyncio.run(main())