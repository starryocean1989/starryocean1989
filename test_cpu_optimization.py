#!/usr/bin/env python3
"""
测试CPU优化效果
"""
import sys
import os
import time
import threading

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def monitor_cpu_usage(duration=60):
    """监控CPU使用率"""
    try:
        import psutil
        
        print(f"🔍 开始监控CPU使用率 ({duration}秒)...")
        
        # 获取当前进程
        current_pid = os.getpid()
        current_process = psutil.Process(current_pid)
        
        samples = []
        start_time = time.time()
        
        while time.time() - start_time < duration:
            try:
                # 获取进程CPU使用率
                cpu_percent = current_process.cpu_percent(interval=1)
                memory_mb = current_process.memory_info().rss / 1024 / 1024
                
                samples.append({
                    'time': time.time() - start_time,
                    'cpu': cpu_percent,
                    'memory': memory_mb
                })
                
                print(f"  {len(samples):2d}秒: CPU {cpu_percent:5.1f}% | 内存 {memory_mb:6.1f}MB")
                
            except Exception as e:
                print(f"  监控错误: {e}")
                break
        
        # 统计结果
        if samples:
            cpu_values = [s['cpu'] for s in samples]
            avg_cpu = sum(cpu_values) / len(cpu_values)
            max_cpu = max(cpu_values)
            min_cpu = min(cpu_values)
            
            print(f"\n📊 CPU使用率统计:")
            print(f"   平均: {avg_cpu:.1f}%")
            print(f"   最高: {max_cpu:.1f}%")
            print(f"   最低: {min_cpu:.1f}%")
            
            if avg_cpu < 5:
                print("   ✅ CPU使用率很低，优化效果良好")
            elif avg_cpu < 15:
                print("   ⚠️ CPU使用率中等，还有优化空间")
            else:
                print("   ❌ CPU使用率较高，需要进一步优化")
        
    except ImportError:
        print("❌ 需要安装psutil: pip install psutil")
    except Exception as e:
        print(f"❌ 监控失败: {e}")

def test_system_manager_service():
    """测试SystemManagerService的CPU使用率"""
    print("🧪 测试SystemManagerService CPU使用率...")
    
    try:
        from backend.services.system_manager_service import SystemManagerService
        
        # 创建服务实例
        service = SystemManagerService()
        print("✅ SystemManagerService实例已创建")
        
        # 测试基础数据获取
        print("\n📊 测试基础数据获取性能...")
        
        start_time = time.time()
        for i in range(5):
            data = service._get_basic_system_data()
            elapsed = time.time() - start_time
            print(f"  第{i+1}次: {elapsed:.3f}秒 | 数据源: {data.get('source', 'unknown')}")
        
        avg_time = elapsed / 5
        print(f"\n平均耗时: {avg_time:.3f}秒/次")
        
        if avg_time < 0.01:
            print("✅ 数据获取性能优秀")
        elif avg_time < 0.05:
            print("⚠️ 数据获取性能一般")
        else:
            print("❌ 数据获取性能较差")
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

def main():
    """主函数"""
    print("🔧 CPU优化效果测试")
    print("=" * 50)
    
    # 1. 测试SystemManagerService性能
    test_system_manager_service()
    
    print("\n" + "=" * 50)
    
    # 2. 监控CPU使用率
    print("📈 即将开始30秒CPU监控...")
    print("   请在另一个终端启动应用程序，观察CPU使用率变化")
    input("   按回车键开始监控...")
    
    monitor_cpu_usage(30)
    
    print("\n💡 优化建议:")
    print("1. 如果CPU使用率仍然较高，考虑进一步增加监控间隔")
    print("2. 检查是否有其他定时器或循环任务")
    print("3. 使用性能分析工具找出热点函数")
    print("4. 考虑使用事件驱动替代轮询机制")

if __name__ == "__main__":
    main()