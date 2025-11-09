import importlib
import sys

def main():
    print("=== 检查 native_scheduler 模块 ===")
    try:
        # 打印 Python 路径
        print("\nPython 路径:")
        for path in sys.path:
            print(f"  - {path}")
            
        # 尝试导入模块
        print("\n尝试导入 native_scheduler 模块...")
        module = importlib.import_module("backend.infrastructure.native.native_scheduler")
        
        # 打印模块信息
        print("\n✅ 模块加载成功")
        print(f"模块路径: {module.__file__}")
        print("\n模块属性:")
        for attr in dir(module):
            if not attr.startswith('_'):  # 不显示私有属性
                try:
                    value = getattr(module, attr)
                    print(f"  - {attr}: {value}")
                except Exception as e:
                    print(f"  - {attr}: <无法获取值: {e}>")
        
        # 检查关键属性
        print("\n关键属性检查:")
        for attr in ['SCHEDULER_AVAILABLE', 'USING_NATIVE_CORE', 'NativeScheduler']:
            try:
                value = getattr(module, attr, '未找到')
                print(f"  - {attr}: {value}") 
                if attr == 'NativeScheduler' and value != '未找到':
                    print(f"    - 方法: {[m for m in dir(value) if not m.startswith('_')]}")
            except Exception as e:
                print(f"  - {attr}: 访问错误 - {e}")
        
        # 尝试创建 NativeScheduler 实例
        if hasattr(module, 'NativeScheduler'):
            print("\n尝试创建 NativeScheduler 实例...")
            try:
                scheduler = module.NativeScheduler()
                print("✅ NativeScheduler 实例创建成功")
                # 测试注册类别
                scheduler.register_category("test", 10, 2)
                print("✅ 测试类别注册成功")
                # 获取统计信息
                stats = scheduler.stats()
                print(f"✅ 获取统计信息: {stats}")
            except Exception as e:
                print(f"❌ 创建实例或调用方法失败: {e}")
                import traceback
                traceback.print_exc()
        
    except Exception as e:
        print(f"\n❌ 模块加载失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True

if __name__ == "__main__":
    success = main()
    if success:
        print("\n✅ 模块检查完成，未发现明显问题")
    else:
        print("\n❌ 模块检查发现问题，请查看上面的错误信息")
