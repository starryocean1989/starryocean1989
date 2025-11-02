#!/usr/bin/env python3
"""
快速CPU分析工具
"""
import sys
import os
import time

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def main():
    """主函数"""
    print("🔍 快速CPU分析")
    
    try:
        import psutil
        
        # 基础信息
        print(f"CPU: {psutil.cpu_count(logical=False)}核心/{psutil.cpu_count(logical=True)}线程")
        print(f"频率: {psutil.cpu_freq().current:.0f}MHz (最大: {psutil.cpu_freq().max:.0f}MHz)")
        
        # CPU使用率
        print("\n正在采集CPU数据...")
        cpu_overall = []
        cpu_per_core = []
        
        for i in range(3):
            overall = psutil.cpu_percent(interval=1)
            per_core = psutil.cpu_percent(interval=0, percpu=True)
            cpu_overall.append(overall)
            cpu_per_core.append(per_core)
            print(f"样本{i+1}: 总体{overall:.1f}%")
        
        avg_cpu = sum(cpu_overall) / len(cpu_overall)
        print(f"\n平均CPU使用率: {avg_cpu:.1f}%")
        
        # 每核心分析
        if cpu_per_core:
            num_cores = len(cpu_per_core[0])
            print(f"\n各核心平均使用率:")
            
            core_stats = []
            for core_idx in range(num_cores):
                core_usage = [sample[core_idx] for sample in cpu_per_core]
                avg_usage = sum(core_usage) / len(core_usage)
                max_usage = max(core_usage)
                core_stats.append((core_idx, avg_usage, max_usage))
            
            # 排序并显示
            core_stats.sort(key=lambda x: x[1], reverse=True)
            
            high_cores = 0
            for core_idx, avg_usage, max_usage in core_stats:
                if avg_usage > 30:
                    high_cores += 1
                status = "🔥" if avg_usage > 50 else "🔸" if avg_usage > 20 else "💤"
                print(f"  核心{core_idx:2d}: {avg_usage:5.1f}% (峰值{max_usage:4.1f}%) {status}")
            
            print(f"\n高负载核心(>30%): {high_cores}/{num_cores}")
            
            # 负载分布分析
            if high_cores <= 2 and avg_cpu < 50:
                print("⚠️ 检测到可能的单核心瓶颈或不均匀负载")
            elif avg_cpu < 30:
                print("✅ CPU负载较低，温度问题可能来自其他原因")
        
        # 进程分析
        print(f"\n高CPU进程 (>5%):")
        processes = []
        for proc in psutil.process_iter(['pid', 'name', 'cpu_percent']):
            try:
                info = proc.info
                if info['cpu_percent'] > 5.0:
                    processes.append(info)
            except:
                pass
        
        processes.sort(key=lambda x: x['cpu_percent'], reverse=True)
        for proc in processes[:5]:
            print(f"  {proc['name']:<20} {proc['cpu_percent']:5.1f}%")
        
        if not processes:
            print("  (无高CPU使用率进程)")
        
        # 温度检测
        print(f"\n温度传感器:")
        try:
            temps = psutil.sensors_temperatures()
            if temps:
                for name, entries in temps.items():
                    for entry in entries:
                        temp_status = "🔥" if entry.current > 80 else "⚠️" if entry.current > 70 else "✅"
                        print(f"  {name}: {entry.current:.1f}°C {temp_status}")
            else:
                print("  ❌ 无法检测温度（需要管理员权限或专用工具）")
        except:
            print("  ❌ 温度检测不可用")
        
        # 分析结论
        print(f"\n🔍 分析结论:")
        if avg_cpu < 30:
            print("• CPU使用率较低，但如果温度仍然很高，可能原因:")
            print("  1. 散热系统问题（风扇、硅脂、灰尘）")
            print("  2. CPU频率锁定在高频状态")
            print("  3. 后台有隐藏的高负载进程")
            print("  4. 硬件老化或故障")
            print("  5. 环境温度过高")
        elif high_cores <= 2:
            print("• 检测到少数核心高负载，可能是:")
            print("  1. 单线程应用瓶颈")
            print("  2. 某些核心过热降频")
            print("  3. 不均匀的任务分配")
        
        print(f"\n💡 建议:")
        print("1. 使用HWiNFO64或Core Temp监测实时温度")
        print("2. 检查任务管理器的详细进程视图")
        print("3. 检查电源计划设置（控制面板->电源选项）")
        print("4. 清理机箱灰尘，检查风扇运转")
        print("5. 如果是笔记本，检查是否堵塞散热口")
        
    except ImportError:
        print("❌ 需要安装psutil: pip install psutil")
    except Exception as e:
        print(f"❌ 分析失败: {e}")

if __name__ == "__main__":
    main()