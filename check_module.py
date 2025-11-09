import sys
import importlib

def main():
    print("=== 检查 native_scheduler 模块 ===\n")
    
    # 打印 Python 路径
    print("Python 路径:")
    for i, path in enumerate(sys.path, 1):
        print(f"  {i:2d}. {path}")
    
    # 尝试导入模块
    print("\n尝试导入模块...")
    try:
        module = importlib.import_module("backend.infrastructure.native.native_scheduler")
        print("✅ 模块导入成功")
        print(f"模块路径: {module.__file__}")
        
        # 检查关键属性
        print("\n检查关键属性:")
        attrs = ['SCHEDULER_AVAILABLE', 'USING_NATIVE_CORE', 'NativeScheduler']
        for attr in attrs:
            try:
                value = getattr(module, attr, '未找到')
                print(f"  - {attr}: {value}")
            except Exception as e:
                print(f"  - {attr}: 访问错误 - {e}")
        
    except Exception as e:
        print(f"❌ 模块导入失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True

if __name__ == "__main__":
    print("开始检查...")
    if main():
        print("\n✅ 检查完成，模块似乎正常")
    else:
        print("\n❌ 检查发现问题")
