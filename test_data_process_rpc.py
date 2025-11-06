# -*- coding: utf-8 -*-
"""
测试数据进程RPC通信
"""

import asyncio
import sys
import time
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))


async def test_data_process_rpc():
    """测试数据进程RPC通信"""
    print("=" * 60)
    print("测试数据进程RPC通信")
    print("=" * 60)

    try:
        from backend.infrastructure.data_module_vnpy.data_process_client import (
            get_data_process_client,
        )

        # 获取数据进程客户端
        print("\n📍 获取数据进程客户端...")
        client = get_data_process_client()

        # 连接数据进程（使用异步方法）
        print("📍 连接数据进程...")
        if await client.connect_async():
            print("✅ 数据进程连接成功")

            # 测试1: 获取品种列表
            print("\n📍 测试1: 获取品种列表...")
            try:
                result = await client.call_async("get_symbol_list")
                if result and result.get("success"):
                    symbol_count = len(result.get("data", []))
                    print(f"✅ 获取品种列表成功: {symbol_count} 个品种")
                else:
                    print(f"⚠️ 获取品种列表失败: {result}")
            except Exception as e:
                print(f"❌ 获取品种列表失败: {e}")

            # 测试2: 获取K线数据
            print("\n📍 测试2: 获取K线数据...")
            try:
                result = await client.call_async(
                    "get_kline_data",
                    symbol="000001.SZ",
                    interval="1d",
                    start_date="2024-01-01",
                    end_date="2024-01-31",
                )
                if result and result.get("success"):
                    data = result.get("data", [])
                    print(f"✅ 获取K线数据成功: {len(data)} 条记录")
                    if data:
                        print(f"   第一条: {data[0]}")
                else:
                    print(f"⚠️ 获取K线数据失败: {result}")
            except Exception as e:
                print(f"❌ 获取K线数据失败: {e}")

            # 断开连接
            print("\n📍 断开连接...")
            client.disconnect()
            print("✅ 数据进程连接已断开")

            return True
        else:
            print("❌ 数据进程连接失败")
            return False

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("\n⚠️ 注意: 请先运行 test_three_process_startup.py 启动数据进程")
    print("等待5秒后开始测试...\n")
    time.sleep(5)

    success = asyncio.run(test_data_process_rpc())
    print("\n" + "=" * 60)
    print(f"测试结果: {'✅ 通过' if success else '❌ 失败'}")
    print("=" * 60)
