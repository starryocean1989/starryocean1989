# -*- coding: utf-8 -*-
"""
RPC编解码性能测试 - 验证orjson优化效果

测试项目:
1. JSON序列化性能对比（orjson vs json）
2. JSON反序列化性能对比（orjson vs json）
3. 大数据量测试（1000条K线数据）
4. 小数据量测试（1条K线数据）
5. 复杂对象测试（嵌套字典和列表）
"""

import json
import time
from typing import Dict, List, Any

# 尝试导入orjson
try:
    import orjson
    HAS_ORJSON = True
except ImportError:
    HAS_ORJSON = False
    print("⚠️ orjson未安装，请运行: pip install orjson>=3.8.0")
    exit(1)


def generate_kline_data(num_rows: int) -> List[Dict[str, Any]]:
    """生成测试用的K线数据"""
    data = []
    for i in range(num_rows):
        data.append({
            "datetime": f"2023-01-01 09:30:00",
            "symbol": "000001.SZ",
            "open": 10.0 + i * 0.01,
            "high": 10.1 + i * 0.01,
            "low": 9.9 + i * 0.01,
            "close": 10.05 + i * 0.01,
            "volume": 1000000 + i * 1000,
            "turnover": 10000000.0 + i * 10000,
        })
    return data


def generate_complex_request() -> Dict[str, Any]:
    """生成复杂的RPC请求"""
    return {
        "id": "12345678-1234-1234-1234-123456789012",
        "method": "get_kline_data",
        "params": {
            "symbol": "000001.SZ",
            "interval": "1d",
            "start_date": "2023-01-01",
            "end_date": "2023-12-31",
            "check_gaps": True,
            "prefer_format": "arrow",
        },
        "timestamp": 1234567890.123456,
    }


def test_serialization_performance(data: Any, num_iterations: int = 1000) -> Dict[str, float]:
    """测试序列化性能
    
    Args:
        data: 要序列化的数据
        num_iterations: 迭代次数
        
    Returns:
        性能结果字典
    """
    results = {}
    
    # 测试orjson序列化
    start_time = time.perf_counter()
    for _ in range(num_iterations):
        orjson.dumps(data)
    orjson_time = time.perf_counter() - start_time
    results["orjson_time"] = orjson_time
    
    # 测试标准json序列化
    start_time = time.perf_counter()
    for _ in range(num_iterations):
        json.dumps(data, ensure_ascii=False).encode("utf-8")
    json_time = time.perf_counter() - start_time
    results["json_time"] = json_time
    
    # 计算性能提升
    results["speedup"] = json_time / orjson_time
    results["improvement_pct"] = (json_time - orjson_time) / json_time * 100
    
    return results


def test_deserialization_performance(data: Any, num_iterations: int = 1000) -> Dict[str, float]:
    """测试反序列化性能
    
    Args:
        data: 要反序列化的数据（原始对象）
        num_iterations: 迭代次数
        
    Returns:
        性能结果字典
    """
    results = {}
    
    # 先序列化为bytes/str
    orjson_bytes = orjson.dumps(data)
    json_str = json.dumps(data, ensure_ascii=False).encode("utf-8")
    
    # 测试orjson反序列化
    start_time = time.perf_counter()
    for _ in range(num_iterations):
        orjson.loads(orjson_bytes)
    orjson_time = time.perf_counter() - start_time
    results["orjson_time"] = orjson_time
    
    # 测试标准json反序列化
    start_time = time.perf_counter()
    for _ in range(num_iterations):
        json.loads(json_str.decode("utf-8"))
    json_time = time.perf_counter() - start_time
    results["json_time"] = json_time
    
    # 计算性能提升
    results["speedup"] = json_time / orjson_time
    results["improvement_pct"] = (json_time - orjson_time) / json_time * 100
    
    return results


def print_results(test_name: str, results: Dict[str, float], data_size_bytes: int):
    """打印测试结果"""
    print(f"\n{'='*80}")
    print(f"测试项目: {test_name}")
    print(f"{'='*80}")
    print(f"数据大小: {data_size_bytes:,} bytes ({data_size_bytes/1024:.2f} KB)")
    print(f"\nOrjson 时间: {results['orjson_time']*1000:.2f} ms")
    print(f"Json 时间:   {results['json_time']*1000:.2f} ms")
    print(f"\n性能提升: {results['speedup']:.2f}x")
    print(f"改进百分比: {results['improvement_pct']:.1f}%")
    print(f"{'='*80}")


def main():
    """主测试函数"""
    print("\n" + "="*80)
    print("RPC编解码性能测试 - orjson vs json")
    print("="*80)
    
    # 测试1: 小数据量（单条K线）
    print("\n📊 测试1: 小数据量 - 单条K线数据")
    small_data = generate_kline_data(1)[0]
    small_data_size = len(json.dumps(small_data, ensure_ascii=False).encode("utf-8"))
    
    print("\n  [序列化性能测试]")
    small_ser_results = test_serialization_performance(small_data, num_iterations=10000)
    print_results("小数据序列化（1条K线）", small_ser_results, small_data_size)
    
    print("\n  [反序列化性能测试]")
    small_deser_results = test_deserialization_performance(small_data, num_iterations=10000)
    print_results("小数据反序列化（1条K线）", small_deser_results, small_data_size)
    
    # 测试2: 中等数据量（100条K线）
    print("\n📊 测试2: 中等数据量 - 100条K线数据")
    medium_data = generate_kline_data(100)
    medium_data_size = len(json.dumps(medium_data, ensure_ascii=False).encode("utf-8"))
    
    print("\n  [序列化性能测试]")
    medium_ser_results = test_serialization_performance(medium_data, num_iterations=1000)
    print_results("中等数据序列化（100条K线）", medium_ser_results, medium_data_size)
    
    print("\n  [反序列化性能测试]")
    medium_deser_results = test_deserialization_performance(medium_data, num_iterations=1000)
    print_results("中等数据反序列化（100条K线）", medium_deser_results, medium_data_size)
    
    # 测试3: 大数据量（1000条K线）
    print("\n📊 测试3: 大数据量 - 1000条K线数据")
    large_data = generate_kline_data(1000)
    large_data_size = len(json.dumps(large_data, ensure_ascii=False).encode("utf-8"))
    
    print("\n  [序列化性能测试]")
    large_ser_results = test_serialization_performance(large_data, num_iterations=100)
    print_results("大数据序列化（1000条K线）", large_ser_results, large_data_size)
    
    print("\n  [反序列化性能测试]")
    large_deser_results = test_deserialization_performance(large_data, num_iterations=100)
    print_results("大数据反序列化（1000条K线）", large_deser_results, large_data_size)
    
    # 测试4: 复杂RPC请求
    print("\n📊 测试4: 复杂RPC请求")
    complex_request = generate_complex_request()
    complex_data_size = len(json.dumps(complex_request, ensure_ascii=False).encode("utf-8"))
    
    print("\n  [序列化性能测试]")
    complex_ser_results = test_serialization_performance(complex_request, num_iterations=10000)
    print_results("复杂RPC请求序列化", complex_ser_results, complex_data_size)
    
    print("\n  [反序列化性能测试]")
    complex_deser_results = test_deserialization_performance(complex_request, num_iterations=10000)
    print_results("复杂RPC请求反序列化", complex_deser_results, complex_data_size)
    
    # 总结
    print("\n" + "="*80)
    print("总结")
    print("="*80)
    
    avg_ser_speedup = (
        small_ser_results["speedup"] + 
        medium_ser_results["speedup"] + 
        large_ser_results["speedup"] + 
        complex_ser_results["speedup"]
    ) / 4
    
    avg_deser_speedup = (
        small_deser_results["speedup"] + 
        medium_deser_results["speedup"] + 
        large_deser_results["speedup"] + 
        complex_deser_results["speedup"]
    ) / 4
    
    print(f"\n平均序列化性能提升: {avg_ser_speedup:.2f}x")
    print(f"平均反序列化性能提升: {avg_deser_speedup:.2f}x")
    print(f"综合性能提升: {(avg_ser_speedup + avg_deser_speedup) / 2:.2f}x")
    
    # 判断是否达到验收标准
    print("\n" + "="*80)
    print("验收标准检查")
    print("="*80)
    
    if avg_ser_speedup >= 2.0 and avg_deser_speedup >= 2.0:
        print("✅ 通过: RPC编解码速度提升2倍以上")
        print(f"   - 序列化提升: {avg_ser_speedup:.2f}x")
        print(f"   - 反序列化提升: {avg_deser_speedup:.2f}x")
    else:
        print("❌ 未通过: RPC编解码速度提升未达到2倍")
        print(f"   - 序列化提升: {avg_ser_speedup:.2f}x (目标: ≥2.0x)")
        print(f"   - 反序列化提升: {avg_deser_speedup:.2f}x (目标: ≥2.0x)")
    
    print("\n" + "="*80)


if __name__ == "__main__":
    main()
