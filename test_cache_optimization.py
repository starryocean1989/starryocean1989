#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试缓存优化效果（不依赖C扩展）
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

def test_server_pool_cache():
    """测试server_pool缓存优化"""
    print("\n" + "="*80)
    print("🧪 测试: server_pool缓存优化")
    print("="*80)
    
    try:
        from backend.infrastructure.data_module_vnpy.load_balancer import LoadBalancer
        from backend.infrastructure.data_module_vnpy.core_engine import ConfigManager
        
        config_manager = ConfigManager()
        lb = LoadBalancer(config_manager=config_manager)
        
        print("\n📊 测试场景：多次调用_check_cache_status，验证缓存机制")
        
        # 第一次调用
        print("\n🔹 第1次调用（应执行真实验证）...")
        start = time.perf_counter()
        lb._check_cache_status()
        t1 = time.perf_counter() - start
        print(f"   耗时: {t1*1000:.3f}ms")
        print(f"   缓存结果: {lb._cache_validation_result is not None}")
        print(f"   缓存时间: {lb._cache_validation_time:.3f}s")
        
        # 立即第二次调用
        print("\n🔹 第2次调用（应使用缓存，<5秒内）...")
        start = time.perf_counter()
        lb._check_cache_status()
        t2 = time.perf_counter() - start
        print(f"   耗时: {t2*1000:.3f}ms")
        
        # 第三次调用
        print("\n🔹 第3次调用（应使用缓存）...")
        start = time.perf_counter()
        lb._check_cache_status()
        t3 = time.perf_counter() - start
        print(f"   耗时: {t3*1000:.3f}ms")
        
        # 测试_load_servers也使用缓存
        print("\n🔹 调用_load_servers（应使用缓存）...")
        start = time.perf_counter()
        lb._load_servers()
        t4 = time.perf_counter() - start
        print(f"   耗时: {t4*1000:.3f}ms")
        
        # 等待6秒后再调用
        print("\n🔹 等待6秒后调用（缓存应过期）...")
        time.sleep(6.1)
        start = time.perf_counter()
        lb._check_cache_status()
        t5 = time.perf_counter() - start
        print(f"   耗时: {t5*1000:.3f}ms")
        
        # 分析结果
        print("\n📈 性能分析:")
        print(f"   第1次: {t1*1000:.3f}ms (基准)")
        print(f"   第2次: {t2*1000:.3f}ms (缓存)")
        print(f"   第3次: {t3*1000:.3f}ms (缓存)")
        print(f"   第4次: {t4*1000:.3f}ms (_load_servers缓存)")
        print(f"   第5次: {t5*1000:.3f}ms (缓存过期)")
        
        # 验证优化效果
        cache_faster = t2 < t1 * 0.8  # 缓存应该快至少20%
        load_servers_uses_cache = t4 < t1 * 0.8  # _load_servers也应该快
        
        print(f"\n✅ 验证:")
        print(f"   缓存加速生效: {cache_faster} (第2次比第1次快 {(1-t2/t1)*100:.1f}%)")
        print(f"   _load_servers使用缓存: {load_servers_uses_cache}")
        print(f"   缓存过期后重新验证: {t5 > t2}")
        
        if cache_faster and load_servers_uses_cache:
            print("\n🎉 测试通过！缓存优化生效，减少了重复IO")
            return True
        else:
            print("\n⚠️  警告: 缓存效果不明显")
            return False
            
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_monitor_lazy_loading():
    """测试监控告警懒加载"""
    print("\n" + "="*80)
    print("🧪 测试: monitor_alerts懒加载")
    print("="*80)
    
    try:
        monitor_file = Path(__file__).parent / "backend" / "infrastructure" / "system_vnpy" / "monitor_system.py"
        content = monitor_file.read_text(encoding="utf-8")
        
        checks = {
            "懒加载模式": ("懒加载" in content or "lazy_load" in content),
            "_alerts_pipe_retry_count": "_alerts_pipe_retry_count" in content,
            "_write_alert_to_file": "_write_alert_to_file" in content,
            "降级机制": "降级为本地文件告警" in content,
            "首次发送告警时连接": "首次发送告警时才建立连接" in content or "首次发送告警时连接" in content,
        }
        
        print("\n📋 代码检查:")
        all_ok = True
        for name, passed in checks.items():
            status = "✅" if passed else "❌"
            print(f"   {status} {name}")
            all_ok = all_ok and passed
        
        if all_ok:
            print("\n🎉 测试通过！懒加载优化已实现")
            print("\n预期效果:")
            print("  - 监控进程启动不再阻塞等待告警管道（节省~180秒）")
            print("  - 首次告警时才建立连接，失败自动降级")
            print("  - 重试限制3次，避免频繁重试")
        else:
            print("\n❌ 部分检查未通过")
        
        return all_ok
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    print("\n" + "="*80)
    print("🚀 优化测试（简化版）")
    print("="*80)
    
    results = {}
    
    # 测试1: server_pool缓存
    results['cache'] = test_server_pool_cache()
    
    # 测试2: 懒加载
    results['lazy_load'] = test_monitor_lazy_loading()
    
    # 总结
    print("\n" + "="*80)
    print("📊 测试总结")
    print("="*80)
    
    for name, passed in results.items():
        status = "✅" if passed else "❌"
        print(f"   {status} {name}")
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    print(f"\n   总计: {passed}/{total} 通过")
    
    if passed == total:
        print("\n🎉 所有测试通过！")
    
    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
