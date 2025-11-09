import sys
import logging
from backend.infrastructure.data_module_vnpy.native_scheduler_bridge import NativeSchedulerBridge

# 配置日志
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)

def simple_test():
    print("\n=== 开始简单测试 ===")
    
    try:
        # 1. 测试初始化
        print("\n1. 初始化 NativeSchedulerBridge...")
        bridge = NativeSchedulerBridge({
            "test": {"queue_capacity": 10, "max_workers": 1}
        })
        print(f"✅ Bridge 初始化成功，可用: {bridge.available}")
        
        # 2. 测试简单任务
        print("\n2. 测试简单任务...")
        def add(a, b):
            print(f"执行加法: {a} + {b}")
            return a + b
            
        future = bridge.submit("test", add, args=(2, 3))
        result = future.result(timeout=5.0)
        print(f"✅ 任务结果: {result} (期望: 5)")
        
        # 3. 关闭
        print("\n3. 关闭桥接器...")
        bridge.shutdown()
        print("✅ 测试完成")
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = simple_test()
    if success:
        print("\n🎉 测试通过！")
    else:
        print("\n❌ 测试失败")
