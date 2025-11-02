#!/usr/bin/env python3
"""
CPU温度与使用率诊断工具
分析低使用率高温度的可能原因
"""
import sys
import os
import time
import json
from datetime import datetime

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def main():
    """主函数"""
    print("🌡️ CPU温度与使用率诊断工具")
    print("=" * 60)
    
    try:
        import psutil
        
        # 1. 基础系统信息
        print("\n📊 步骤1: 基础系统信息")
        print(f"   CPU核心数: {psutil.cpu_count(logical=False)} 物理核心")
        print(f"   逻辑处理器: {psutil.cpu_count(logical=True)} 个")
        print(f"   CPU频率: {psutil.cpu_freq().current:.0f} MHz (最大: {psutil.cpu_freq().max:.0f} MHz)")
        
        # 2. 详细CPU使用率分析
        print("\n📊 步骤2: 详细CPU使用率分析")
        print("   正在采集5秒钟的CPU数据...")
        
        # 采集多次数据
        cpu_samples = []
        per_cpu_samples = []
        
        for i in range(5):
            # 总体CPU使用率
            cpu_percent = psutil.cpu_percent(interval=1)
            cpu_samples.append(cpu_percent)
            
            # 每个核心的使用率
            per_cpu = psutil.cpu_percent(interval=0, percpu=True)
            per_cpu_samples.append(per_cpu)
            
            print(f"   样本 {i+1}: 总体CPU {cpu_percent:.1f}%")
        
        # 分析结果
        avg_cpu = sum(cpu_samples) / len(cpu_samples)
        max_cpu = max(cpu_samples)
        min_cpu = min(cpu_samples)
        
        print(f"\n   📈 CPU使用率统计:")
        print(f"      平均: {avg_cpu:.1f}%")
        print(f"      最高: {max_cpu:.1f}%")
        print(f"      最低: {min_cpu:.1f}%")
        
        # 3. 每个核心的详细分析
        print(f"\n📊 步骤3: 每个核心使用率分析")
        if per_cpu_samples:
            # 计算每个核心的平均使用率
            num_cores = len(per_cpu_samples[0])
            core_averages = []
            
            for core_idx in range(num_cores):
                core_usage = [sample[core_idx] for sample in per_cpu_samples]
                avg_usage = sum(core_usage) / len(core_usage)
                max_usage = max(core_usage)
                core_averages.append((core_idx, avg_usage, max_usage))
            
            # 按使用率排序
            core_averages.sort(key=lambda x: x[1], reverse=True)
            
            print(f"   核心使用率排序 (平均/最高):")
            for core_idx, avg_usage, max_usage in core_averages:
                status = "🔥" if avg_usage > 50 else "🔸" if avg_usage > 20 else "💤"
                print(f"      核心 {core_idx:2d}: {avg_usage:5.1f}% / {max_usage:5.1f}% {status}")
            
            # 分析核心使用模式
            high_usage_cores = [c for c in core_averages if c[1] > 30]
            medium_usage_cores = [c for c in core_averages if 10 < c[1] <= 30]
            low_usage_cores = [c for c in core_averages if c[1] <= 10]
            
            print(f"\n   📊 核心使用模式分析:")
            print(f"      高使用率核心 (>30%): {len(high_usage_cores)} 个")
            print(f"      中等使用率核心 (10-30%): {len(medium_usage_cores)} 个")
            print(f"      低使用率核心 (≤10%): {len(low_usage_cores)} 个")
        
        # 4. 进程分析
        print(f"\n📊 步骤4: 高CPU使用率进程分析")
        processes = []
        for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
            try:
                proc_info = proc.info
                if proc_info['cpu_percent'] > 1.0:  # 只显示CPU使用率>1%的进程
                    processes.append(proc_info)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        
        # 按CPU使用率排序
        processes.sort(key=lambda x: x['cpu_percent'], reverse=True)
        
        print(f"   前10个高CPU使用率进程:")
        for i, proc in enumerate(processes[:10]):
            print(f"      {i+1:2d}. {proc['name']:<20} PID:{proc['pid']:<8} CPU:{proc['cpu_percent']:5.1f}% MEM:{proc['memory_percent']:5.1f}%")
        
        # 5. 温度检测（如果可用）
        print(f"\n📊 步骤5: 温度检测")
        try:
            temps = psutil.sensors_temperatures()
            if temps:
                print(f"   检测到温度传感器:")
                for name, entries in temps.items():
                    for entry in entries:
                        temp_status = "🔥" if entry.current > 80 else "⚠️" if entry.current > 70 else "✅"
                        print(f"      {name} - {entry.label or 'N/A'}: {entry.current:.1f}°C {temp_status}")
                        if entry.high:
                            print(f"        (警告阈值: {entry.high:.1f}°C)")
            else:
                print(f"   ⚠️ 无法检测到温度传感器（可能需要管理员权限）")
        except Exception as e:
            print(f"   ❌ 温度检测失败: {e}")
        
        # 6. 电源管理状态
        print(f"\n📊 步骤6: 电源管理分析")
        try:
            # 检查电源状态
            battery = psutil.sensors_battery()
            if battery:
                power_status = "🔌 外接电源" if battery.power_plugged else "🔋 电池供电"
                print(f"   电源状态: {power_status}")
                print(f"   电池电量: {battery.percent:.1f}%")
            else:
                print(f"   电源状态: 🖥️ 台式机/无电池")
            
            # CPU频率变化检测
            print(f"   正在监测CPU频率变化...")
            freq_samples = []
            for i in range(3):
                freq = psutil.cpu_freq()
                freq_samples.append(freq.current)
                time.sleep(1)
            
            freq_avg = sum(freq_samples) / len(freq_samples)
            freq_max_sample = max(freq_samples)
            freq_min_sample = min(freq_samples)
            
            print(f"   CPU频率统计:")
            print(f"      当前: {freq_samples[-1]:.0f} MHz")
            print(f"      平均: {freq_avg:.0f} MHz")
            print(f"      变化范围: {freq_min_sample:.0f} - {freq_max_sample:.0f} MHz")
            
            # 频率调节分析
            freq_ratio = freq_avg / psutil.cpu_freq().max * 100
            if freq_ratio < 50:
                print(f"   ⚠️ CPU频率较低 ({freq_ratio:.1f}%)，可能启用了节能模式")
            elif freq_ratio > 90:
                print(f"   🔥 CPU频率较高 ({freq_ratio:.1f}%)，可能在高性能模式")
            else:
                print(f"   ✅ CPU频率正常 ({freq_ratio:.1f}%)")
                
        except Exception as e:
            print(f"   ❌ 电源管理分析失败: {e}")
        
        # 7. 可能原因分析
        print(f"\n📊 步骤7: 低使用率高温度可能原因分析")
        print(f"   🔍 常见原因:")
        print(f"      1. 🌡️ 散热问题:")
        print(f"         - 风扇故障或灰尘堵塞")
        print(f"         - 导热硅脂老化")
        print(f"         - 散热器安装不当")
        print(f"      2. ⚡ 电源管理问题:")
        print(f"         - CPU频率锁定在高频")
        print(f"         - 电源计划设置为高性能")
        print(f"         - BIOS设置问题")
        print(f"      3. 🔥 后台进程:")
        print(f"         - 隐藏的高CPU进程")
        print(f"         - 系统服务异常")
        print(f"         - 恶意软件")
        print(f"      4. 🏭 硬件问题:")
        print(f"         - CPU老化")
        print(f"         - 主板供电问题")
        print(f"         - 环境温度过高")
        
        # 8. 建议的解决方案
        print(f"\n📊 步骤8: 建议的解决方案")
        print(f"   🛠️ 立即检查:")
        print(f"      1. 检查任务管理器中的详细进程")
        print(f"      2. 检查CPU风扇是否正常运转")
        print(f"      3. 检查电源计划设置")
        print(f"      4. 运行杀毒软件全盘扫描")
        print(f"   🔧 进一步诊断:")
        print(f"      1. 使用HWiNFO64等专业工具监测温度")
        print(f"      2. 检查BIOS中的CPU设置")
        print(f"      3. 清理机箱内部灰尘")
        print(f"      4. 更换导热硅脂")
        
        # 9. 生成诊断报告
        report = {
            "timestamp": datetime.now().isoformat(),
            "cpu_info": {
                "physical_cores": psutil.cpu_count(logical=False),
                "logical_cores": psutil.cpu_count(logical=True),
                "frequency_mhz": psutil.cpu_freq().current,
                "max_frequency_mhz": psutil.cpu_freq().max
            },
            "cpu_usage": {
                "average": avg_cpu,
                "maximum": max_cpu,
                "minimum": min_cpu,
                "samples": cpu_samples
            },
            "top_processes": processes[:5],
            "analysis": {
                "low_usage_high_temp": avg_cpu < 30,  # 假设低于30%为低使用率
                "possible_thermal_issue": True,  # 需要实际温度数据确认
                "recommendations": [
                    "检查散热系统",
                    "监测CPU温度",
                    "检查电源管理设置",
                    "扫描恶意软件"
                ]
            }
        }
        
        report_file = "cpu_thermal_diagnosis_report.json"
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        print(f"\n📄 诊断报告已保存到: {report_file}")
        print(f"✅ 诊断完成")
        
    except ImportError:
        print("❌ 缺少psutil模块，请安装: pip install psutil")
    except Exception as e:
        print(f"❌ 诊断过程中出现错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()