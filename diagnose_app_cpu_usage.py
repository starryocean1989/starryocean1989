#!/usr/bin/env python3
"""
应用程序CPU使用率诊断工具
专门分析当前应用的CPU占用情况
"""
import sys
import os
import time
import threading
from datetime import datetime

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def main():
    """主函数"""
    print("🔍 应用程序CPU使用率诊断")
    print("=" * 50)
    
    try:
        import psutil
        
        # 获取当前进程
        current_pid = os.getpid()
        current_process = psutil.Process(current_pid)
        
        print(f"📊 当前进程信息:")
        print(f"   PID: {current_pid}")
        print(f"   进程名: {current_process.name()}")
        print(f"   启动时间: {datetime.fromtimestamp(current_process.create_time()).strftime('%H:%M:%S')}")
        
        # 1. 查找所有相关的Python进程
        print(f"\n🔍 查找所有相关Python进程:")
        python_processes = []
        
        for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'cpu_percent', 'memory_percent', 'create_time']):
            try:
                if proc.info['name'].lower().startswith('python'):
                    # 检查是否是我们项目相关的进程
                    cmdline = ' '.join(proc.info['cmdline']) if proc.info['cmdline'] else ''
                    if 'terminal_v0.50' in cmdline or proc.info['pid'] == current_pid:
                        python_processes.append({
                            'pid': proc.info['pid'],
                            'cmdline': cmdline,
                            'cpu_percent': proc.info['cpu_percent'],
                            'memory_percent': proc.info['memory_percent'],
                            'create_time': proc.info['create_time'],
                            'is_current': proc.info['pid'] == current_pid
                        })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        
        # 显示相关进程
        for proc in python_processes:
            status = "👈 当前进程" if proc['is_current'] else ""
            create_time = datetime.fromtimestamp(proc['create_time']).strftime('%H:%M:%S')
            print(f"   PID {proc['pid']:5d}: CPU {proc['cpu_percent']:5.1f}% | MEM {proc['memory_percent']:5.1f}% | {create_time} {status}")
            if len(proc['cmdline']) > 80:
                print(f"            命令: {proc['cmdline'][:80]}...")
            else:
                print(f"            命令: {proc['cmdline']}")
        
        # 2. 实时监控当前进程的CPU使用率
        print(f"\n📈 实时监控当前进程CPU使用率 (10秒):")
        cpu_samples = []
        memory_samples = []
        
        for i in range(10):
            # 获取进程CPU使用率
            cpu_percent = current_process.cpu_percent(interval=1)
            memory_info = current_process.memory_info()
            memory_mb = memory_info.rss / 1024 / 1024
            
            cpu_samples.append(cpu_percent)
            memory_samples.append(memory_mb)
            
            print(f"   秒 {i+1:2d}: CPU {cpu_percent:5.1f}% | 内存 {memory_mb:6.1f}MB")
        
        # 统计分析
        avg_cpu = sum(cpu_samples) / len(cpu_samples)
        max_cpu = max(cpu_samples)
        avg_memory = sum(memory_samples) / len(memory_samples)
        
        print(f"\n📊 统计结果:")
        print(f"   平均CPU使用率: {avg_cpu:.1f}%")
        print(f"   最高CPU使用率: {max_cpu:.1f}%")
        print(f"   平均内存使用: {avg_memory:.1f}MB")
        
        # 3. 分析进程线程
        print(f"\n🧵 线程分析:")
        try:
            threads = current_process.threads()
            print(f"   线程数量: {len(threads)}")
            
            # 获取线程详细信息
            thread_info = []
            for thread in threads:
                try:
                    # 注意：线程CPU时间在Windows上可能不准确
                    thread_info.append({
                        'id': thread.id,
                        'user_time': thread.user_time,
                        'system_time': thread.system_time
                    })
                except:
                    pass
            
            if thread_info:
                # 按CPU时间排序
                thread_info.sort(key=lambda x: x['user_time'] + x['system_time'], reverse=True)
                print(f"   前5个线程CPU时间:")
                for i, thread in enumerate(thread_info[:5]):
                    total_time = thread['user_time'] + thread['system_time']
                    print(f"      线程 {thread['id']:5d}: {total_time:.2f}秒")
            
        except Exception as e:
            print(f"   线程分析失败: {e}")
        
        # 4. 检查文件句柄和网络连接
        print(f"\n📁 资源使用分析:")
        try:
            # 文件句柄
            open_files = current_process.open_files()
            print(f"   打开文件数: {len(open_files)}")
            
            # 网络连接
            connections = current_process.connections()
            print(f"   网络连接数: {len(connections)}")
            
            # 显示一些文件句柄
            if open_files:
                print(f"   主要打开文件:")
                for i, file_info in enumerate(open_files[:5]):
                    print(f"      {file_info.path}")
            
        except Exception as e:
            print(f"   资源分析失败: {e}")
        
        # 5. 检查可能的CPU密集型操作
        print(f"\n🔥 可能的CPU密集型操作分析:")
        
        if avg_cpu > 20:
            print(f"   ⚠️ 检测到较高CPU使用率 ({avg_cpu:.1f}%)")
            print(f"   可能原因:")
            print(f"      1. 🔄 无限循环或频繁轮询")
            print(f"      2. 📊 大量数据处理")
            print(f"      3. 🖼️ UI频繁刷新")
            print(f"      4. 🌐 网络请求过于频繁")
            print(f"      5. 💾 大量文件I/O操作")
            print(f"      6. 🧮 复杂计算任务")
        elif avg_cpu > 10:
            print(f"   ⚠️ 检测到中等CPU使用率 ({avg_cpu:.1f}%)")
            print(f"   可能是正常的后台处理，但需要关注")
        else:
            print(f"   ✅ CPU使用率正常 ({avg_cpu:.1f}%)")
        
        # 6. 应用特定的分析
        print(f"\n🎯 金融终端应用特定分析:")
        print(f"   常见CPU密集型操作:")
        print(f"      1. 📈 实时行情数据处理")
        print(f"      2. 📊 图表渲染和更新")
        print(f"      3. 🔄 定时器和轮询任务")
        print(f"      4. 💾 数据库查询和缓存")
        print(f"      5. 🌐 网络数据接收和解析")
        print(f"      6. 🖥️ UI界面频繁更新")
        
        # 7. 建议的优化方向
        print(f"\n💡 优化建议:")
        if avg_cpu > 15:
            print(f"   🔧 立即优化:")
            print(f"      1. 检查定时器间隔（减少更新频率）")
            print(f"      2. 优化数据处理算法")
            print(f"      3. 减少UI刷新频率")
            print(f"      4. 使用异步处理替代同步操作")
            print(f"      5. 添加数据缓存机制")
        
        print(f"   📊 监控建议:")
        print(f"      1. 使用性能分析工具（如cProfile）")
        print(f"      2. 添加应用内性能监控")
        print(f"      3. 分析具体的热点函数")
        print(f"      4. 监控各个模块的CPU占用")
        
        # 8. 生成针对性的诊断脚本
        print(f"\n🔍 下一步诊断:")
        print(f"   建议运行以下命令进一步分析:")
        print(f"   1. python -m cProfile -s cumulative your_main_script.py")
        print(f"   2. 使用任务管理器查看详细的线程信息")
        print(f"   3. 检查应用日志中的异常或警告")
        
    except ImportError:
        print("❌ 需要安装psutil: pip install psutil")
    except Exception as e:
        print(f"❌ 诊断失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()