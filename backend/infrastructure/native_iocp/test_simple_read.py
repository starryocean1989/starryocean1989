# -*- coding: utf-8 -*-
"""
简单的IOCP读取测试
"""

import asyncio
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

try:
    from backend.infrastructure.native_iocp import aopen
    print("✅ IOCP模块导入成功")
except ImportError as e:
    print(f"❌ 导入失败: {e}")
    sys.exit(1)

async def test_simple_read():
    """测试简单读取"""
    # 创建测试文件
    test_file = Path("test_iocp.txt")
    test_file.write_text("Hello, IOCP!", encoding='utf-8')

    try:
        print("\n📖 测试异步读取...")
        file = await aopen(test_file, 'rb')
        async with file:
            data = await file.read()
            print(f"✅ 读取成功: {len(data)} 字节")
            print(f"   内容: {data.decode('utf-8')}")

        return True
    except Exception as e:
        print(f"❌ 读取失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # 清理（等待文件关闭）
        import time
        time.sleep(0.1)  # 等待文件句柄释放
        if test_file.exists():
            try:
                test_file.unlink()
            except PermissionError:
                pass  # 文件可能还在使用中，忽略错误

if __name__ == "__main__":
    success = asyncio.run(test_simple_read())
    sys.exit(0 if success else 1)

