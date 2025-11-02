#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简单IPC连接测试
"""

import asyncio
import json
import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

async def test_ipc():
    """测试IPC连接"""
    try:
        from backend.infrastructure.native_ipc import aopen_client, IPC_AVAILABLE
        
        if not IPC_AVAILABLE:
            print("❌ IPC扩展不可用")
            return False
        
        print("🔍 测试IPC连接...")
        
        async with await aopen_client("monitor_query") as pipe:
            print("✅ IPC连接成功")
            
            # 发送测试请求
            request = {"action": "get_data"}
            request_bytes = json.dumps(request).encode('utf-8')
            
            await pipe.write(request_bytes)
            response_bytes = await asyncio.wait_for(pipe.read(size=65536), timeout=3.0)
            
            if response_bytes:
                response = json.loads(response_bytes.decode('utf-8'))
                print(f"✅ 收到响应，数据字段: {list(response.keys()) if isinstance(response, dict) else type(response)}")
                return True
            else:
                print("❌ 无响应数据")
                return False
                
    except FileNotFoundError:
        print("❌ 监控进程未启动或monitor_query管道不存在")
        return False
    except Exception as e:
        print(f"❌ IPC测试失败: {e}")
        return False

if __name__ == "__main__":
    success = asyncio.run(test_ipc())
    if success:
        print("🎉 IPC连接测试成功！")
    else:
        print("❌ IPC连接测试失败！")