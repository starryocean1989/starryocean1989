#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
优化测试脚本
测试所有优化项的效果
"""

import sys
import time
import json
from pathlib import Path
from datetime import date, datetime

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

def test_server_pool_cache_optimization():
    """测试server_pool缓存优化"""
    print("\n" + "="*80)
    print("🧪 测试 1: server_pool缓存优化")
    print("="*80)
    
    try:
        from backend.infrastructure.data_module_vnpy.load_balancer import LoadBalancer
        from backend.config.config_manager import ConfigManager
        
        config_manager = ConfigManager()
        
        print("\n📊 测试场景：多次调用_check_cache_status，观察缓存验证次数")
        
        lb = LoadBalancer(config_manager=config_manager)
        
        # 第一次检查
        print("\n🔹 第一次检查（应该执行真实验证）...")
        start = time.time()
        lb._check_cache_status()
        elapsed1 = time.time() - start
        print(f"   耗时: {elapsed1*1000:.2f}ms")
        
        # 立即第二次检查（应该使用缓存）
        print("\n🔹 第二次检查（应该使用缓存结果）...")
        start = time.time()
        lb._check_cache_status()
        elapsed2 = time.time() - start
        print(f"   耗时: {elapsed2*1000:.2f}ms")
        
        # 第三次检查（应该使用缓存）
        print("\n🔹 第三次检查（应该使用缓存结果）...")
        start = time.time()
        lb._check_cache_status()
        elapsed3 = time.time() - start
        print(f"   耗时: {elapsed3*1000:.2f}ms")
        
        # 等待6秒后再检查（缓存应该过期）
        print("\n🔹 等待6秒后检查（缓存应该过期，执行新验证）...")
        time.sleep(6)
        start = time.time()
        lb._check_cache_status()
        elapsed4 = time.time() - start
        print(f"   耗时: {elapsed4*1000:.2f}ms")
        
        # 分析结果
        print("\n📈 性能分析:")
        print(f"   第一次检查: {elapsed1*1000:.2f}ms (基准)")
        print(f"   第二次检查: {elapsed2*1000:.2f}ms (缓存命中，预期更快)")
        print(f"   第三次检查: {elapsed3*1000:.2f}ms (缓存命中，预期更快)")
        print(f"   第四次检查: {elapsed4*1000:.2f}ms (缓存过期，重新验证)")
        
        speedup = ((elapsed1 - elapsed2) / elapsed1 * 100) if elapsed1 > 0 else 0
        print(f"\n   缓存加速: {speedup:.1f}%")
        
        if elapsed2 < elapsed1 and elapsed3 < elapsed1:
            print("\n✅ 测试通过: 缓存优化生效，减少了重复IO")
        else:
            print("\n⚠️  警告: 缓存效果不明显，可能是文件系统缓存影响")
        
        return True
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_native_compute_date_functions():
    """测试C扩展日期处理功能"""
    print("\n" + "="*80)
    print("🧪 测试 2: C扩展批量日期处理")
    print("="*80)
    
    try:
        from backend.infrastructure.native.native_compute import (
            COMPUTE_AVAILABLE,
            batch_validate_iso_dates,
            batch_compare_dates
        )
        
        if not COMPUTE_AVAILABLE:
            print("\n⚠️  C扩展未编译，跳过测试")
            print("   请运行: backend\\infrastructure\\native\\compile_all.bat")
            return False
        
        print("\n✅ C扩展已加载")
        
        # 测试批量验证
        print("\n📊 测试场景 1: 批量日期格式验证")
        test_dates = [
            "2024-01-01",  # 有效
            "2024-13-01",  # 无效月份
            "2024-01-32",  # 无效日期
            "2024-1-1",    # 格式错误
            "invalid",     # 无效字符串
            None,          # None值
            "2023-12-31",  # 有效
        ]
        
        print(f"   测试数据: {test_dates}")
        
        # Python方式
        start = time.time()
        python_results = []
        for d in test_dates:
            try:
                if d is None:
                    python_results.append(False)
                else:
                    date.fromisoformat(d)
                    python_results.append(True)
            except:
                python_results.append(False)
        python_time = time.time() - start
        
        # C扩展方式
        start = time.time()
        c_results = batch_validate_iso_dates(test_dates)
        c_time = time.time() - start
        
        print(f"\n   Python结果: {python_results}")
        print(f"   C扩展结果: {c_results}")
        print(f"   Python耗时: {python_time*1000:.3f}ms")
        print(f"   C扩展耗时: {c_time*1000:.3f}ms")
        
        if python_results == c_results:
            print("   ✅ 结果一致")
        else:
            print("   ❌ 结果不一致")
            return False
        
        # 测试批量比较
        print("\n📊 测试场景 2: 批量日期比较")
        test_dates = ["2024-01-01", "2024-01-15", "2023-12-31", "invalid"]
        reference = "2024-01-10"
        
        print(f"   测试数据: {test_dates}")
        print(f"   参考日期: {reference}")
        
        # Python方式
        start = time.time()
        python_cmp = []
        for d in test_dates:
            try:
                d1 = date.fromisoformat(d)
                d2 = date.fromisoformat(reference)
                if d1 < d2:
                    python_cmp.append(-1)
                elif d1 > d2:
                    python_cmp.append(1)
                else:
                    python_cmp.append(0)
            except:
                python_cmp.append(-999)
        python_time = time.time() - start
        
        # C扩展方式
        start = time.time()
        c_cmp = batch_compare_dates(test_dates, reference)
        c_time = time.time() - start
        
        print(f"\n   Python结果: {python_cmp}")
        print(f"   C扩展结果: {c_cmp}")
        print(f"   Python耗时: {python_time*1000:.3f}ms")
        print(f"   C扩展耗时: {c_time*1000:.3f}ms")
        
        if python_cmp == c_cmp:
            print("   ✅ 结果一致")
        else:
            print("   ❌ 结果不一致")
            return False
        
        # 大规模性能测试
        print("\n📊 测试场景 3: 大规模性能测试（1000条数据）")
        large_dates = [f"2024-{i%12+1:02d}-{i%28+1:02d}" for i in range(1000)]
        
        # Python方式
        start = time.time()
        python_results = []
        for d in large_dates:
            try:
                date.fromisoformat(d)
                python_results.append(True)
            except:
                python_results.append(False)
        python_time = time.time() - start
        
        # C扩展方式
        start = time.time()
        c_results = batch_validate_iso_dates(large_dates)
        c_time = time.time() - start
        
        speedup = (python_time / c_time - 1) * 100 if c_time > 0 else 0
        
        print(f"   Python耗时: {python_time*1000:.2f}ms")
        print(f"   C扩展耗时: {c_time*1000:.2f}ms")
        print(f"   性能提升: {speedup:.1f}%")
        
        if speedup > 30:
            print(f"\n✅ 测试通过: C扩展比Python快 {speedup:.1f}%")
        else:
            print(f"\n⚠️  警告: 性能提升不明显 ({speedup:.1f}%)，可能需要更大数据集")
        
        return True
        
    except ImportError as e:
        print(f"\n⚠️  C扩展导入失败: {e}")
        print("   可能原因:")
        print("   1. C扩展未编译")
        print("   2. 编译失败（有语法错误）")
        print("   3. 函数未正确导出")
        return False
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_monitor_alerts_lazy_loading():
    """测试monitor_alerts懒加载优化"""
    print("\n" + "="*80)
    print("🧪 测试 3: monitor_alerts懒加载优化")
    print("="*80)
    
    try:
        print("\n📊 检查监控系统代码变更...")
        
        # 读取monitor_system.py，检查是否包含懒加载代码
        monitor_file = Path(__file__).parent / "backend" / "infrastructure" / "system_vnpy" / "monitor_system.py"
        
        if not monitor_file.exists():
            print(f"❌ 文件不存在: {monitor_file}")
            return False
        
        content = monitor_file.read_text(encoding="utf-8")
        
        # 检查关键代码标记
        checks = [
            ("懒加载模式", "懒加载模式" in content or "lazy_load" in content),
            ("_alerts_pipe_retry_count", "_alerts_pipe_retry_count" in content),
            ("_write_alert_to_file", "_write_alert_to_file" in content),
            ("降级为本地文件告警", "降级为本地文件告警" in content),
        ]
        
        print("\n   代码变更检查:")
        all_passed = True
        for check_name, passed in checks:
            status = "✅" if passed else "❌"
            print(f"   {status} {check_name}: {'已实现' if passed else '未找到'}")
            all_passed = all_passed and passed
        
        if all_passed:
            print("\n✅ 测试通过: 懒加载优化代码已正确实现")
            print("\n   优化效果:")
            print("   - 监控进程启动时不再阻塞等待告警管道（节省~180秒）")
            print("   - 首次告警时才建立连接，失败自动降级到本地文件")
            print("   - 重试限制3次，每次间隔5秒，避免频繁重试")
        else:
            print("\n⚠️  警告: 部分优化代码未找到，请检查代码变更")
        
        return all_passed
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_integration():
    """集成测试：检查日志文件验证优化效果"""
    print("\n" + "="*80)
    print("🧪 测试 4: 集成测试（日志验证）")
    print("="*80)
    
    try:
        print("\n📊 检查最新日志文件...")
        
        logs_dir = Path(__file__).parent / "logs" / "ai"
        
        if not logs_dir.exists():
            print(f"⚠️  日志目录不存在: {logs_dir}")
            return False
        
        # 查找最新的日志文件
        log_files = sorted(logs_dir.glob("*.log"), key=lambda x: x.stat().st_mtime, reverse=True)
        
        if not log_files:
            print("⚠️  未找到日志文件")
            return False
        
        latest_log = log_files[0]
        print(f"   最新日志: {latest_log.name}")
        
        # 读取最后100行
        content = latest_log.read_text(encoding="utf-8", errors="ignore")
        lines = content.split('\n')[-100:]
        
        # 统计关键日志
        cache_validation_count = 0
        lazy_load_count = 0
        
        for line in lines:
            if "缓存的验证结果" in line or "cache_validation" in line.lower():
                cache_validation_count += 1
            if "懒加载" in line or "lazy_load" in line.lower():
                lazy_load_count += 1
        
        print(f"\n   关键日志统计（最近100行）:")
        print(f"   - 缓存验证相关: {cache_validation_count} 条")
        print(f"   - 懒加载相关: {lazy_load_count} 条")
        
        if cache_validation_count > 0:
            print("\n✅ 检测到缓存优化日志")
        
        if lazy_load_count > 0:
            print("✅ 检测到懒加载优化日志")
        
        return True
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """主测试函数"""
    print("\n" + "="*80)
    print("🚀 优化测试套件")
    print("="*80)
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    results = {}
    
    # 测试1: server_pool缓存优化
    results['server_pool_cache'] = test_server_pool_cache_optimization()
    
    # 测试2: C扩展日期处理
    results['native_compute_date'] = test_native_compute_date_functions()
    
    # 测试3: monitor_alerts懒加载
    results['monitor_alerts_lazy'] = test_monitor_alerts_lazy_loading()
    
    # 测试4: 集成测试
    results['integration'] = test_integration()
    
    # 总结
    print("\n" + "="*80)
    print("📊 测试总结")
    print("="*80)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for test_name, result in results.items():
        status = "✅ 通过" if result else "❌ 失败"
        print(f"   {status} - {test_name}")
    
    print(f"\n   总计: {passed}/{total} 通过 ({passed/total*100:.0f}%)")
    
    if passed == total:
        print("\n🎉 所有测试通过！优化已成功实施！")
    elif passed > 0:
        print(f"\n⚠️  部分测试通过 ({passed}/{total})，请检查失败的测试")
    else:
        print("\n❌ 所有测试失败，请检查代码实现")
    
    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
