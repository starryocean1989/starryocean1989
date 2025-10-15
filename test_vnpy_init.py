# -*- coding: utf-8 -*-
"""
VNPY初始化诊断脚本

用于检测VNPY EventEngine和MainEngine创建是否阻塞
"""

import sys
import time
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

def test_vnpy_initialization():
    """测试VNPY初始化过程"""
    
    print("=" * 70)
    print("VNPY初始化诊断")
    print("=" * 70)
    
    # 步骤1: 导入模块
    print("\n[步骤1] 导入VNPY模块...")
    start = time.time()
    try:
        from vnpy.event import EventEngine
        from vnpy.trader.engine import MainEngine
        elapsed = (time.time() - start) * 1000
        print(f"✅ 导入成功 ({elapsed:.0f}ms)")
    except Exception as e:
        print(f"❌ 导入失败: {e}")
        return False
    
    # 步骤2: 创建EventEngine
    print("\n[步骤2] 创建EventEngine...")
    start = time.time()
    try:
        event_engine = EventEngine(interval=0.1)
        elapsed = (time.time() - start) * 1000
        print(f"✅ EventEngine创建成功 ({elapsed:.0f}ms)")
    except Exception as e:
        print(f"❌ EventEngine创建失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # 步骤3: 创建MainEngine
    print("\n[步骤3] 创建MainEngine...")
    start = time.time()
    try:
        main_engine = MainEngine(event_engine)
        elapsed = (time.time() - start) * 1000
        print(f"✅ MainEngine创建成功 ({elapsed:.0f}ms)")
    except Exception as e:
        print(f"❌ MainEngine创建失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # 步骤4: 清理
    print("\n[步骤4] 清理资源...")
    start = time.time()
    try:
        main_engine.close()
        event_engine.stop()
        elapsed = (time.time() - start) * 1000
        print(f"✅ 清理成功 ({elapsed:.0f}ms)")
    except Exception as e:
        print(f"⚠️ 清理异常: {e}")
    
    print("\n" + "=" * 70)
    print("✅ VNPY初始化测试通过")
    print("=" * 70)
    return True

if __name__ == "__main__":
    # 设置超时保护
    import signal
    
    def timeout_handler(signum, frame):
        print("\n❌ 测试超时（30秒）！VNPY初始化可能存在阻塞问题")
        sys.exit(1)
    
    # 设置30秒超时
    try:
        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(30)
    except AttributeError:
        # Windows不支持signal.SIGALRM
        print("⚠️ Windows系统，无法设置超时保护")
    
    # 运行测试
    success = test_vnpy_initialization()
    
    # 取消超时
    try:
        signal.alarm(0)
    except AttributeError:
        pass
    
    sys.exit(0 if success else 1)
