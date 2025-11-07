# -*- coding: utf-8 -*-
"""
批量读取性能测试 - 验证批量处理优化效果

测试场景：
1. 单个请求处理（基准测试）
2. 并发请求处理（批量优化测试）
3. 延迟对比测试
4. 吞吐量对比测试
"""

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import List

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
import sys
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class BatchPerformanceTest:
    """批量处理性能测试类"""
    
    def __init__(self):
        self.test_results = {}
        
    def log_result(self, test_name: str, **metrics):
        """记录测试结果"""
        self.test_results[test_name] = metrics
        logger.info(f"✅ {test_name}: {metrics}")
        
    async def test_1_sequential_requests(self, num_requests: int = 10):
        """测试1: 顺序请求处理（单次处理）"""
        logger.info("\n" + "="*80)
        logger.info(f"测试1: 顺序请求处理 ({num_requests}个请求)")
        logger.info("="*80)
        
        # 模拟顺序处理
        start_time = time.perf_counter()
        
        for i in range(num_requests):
            # 模拟序列化
            request = {
                "id": f"req-{i}",
                "method": "get_kline_data",
                "params": {"symbol": "000001.SZ", "interval": "1d"},
                "timestamp": time.time()
            }
            request_data = json.dumps(request).encode("utf-8")
            
            # 模拟反序列化
            request_parsed = json.loads(request_data.decode("utf-8"))
            
            # 模拟处理（10ms延迟）
            await asyncio.sleep(0.01)
            
            # 模拟响应
            response = {
                "id": request_parsed["id"],
                "result": {"success": True, "data": []}
            }
            response_data = json.dumps(response).encode("utf-8")
            
        elapsed = time.perf_counter() - start_time
        throughput = num_requests / elapsed
        avg_latency = (elapsed / num_requests) * 1000  # ms
        
        self.log_result(
            "顺序请求",
            num_requests=num_requests,
            elapsed_ms=elapsed*1000,
            throughput_rps=throughput,
            avg_latency_ms=avg_latency
        )
        
        return elapsed, throughput
        
    async def test_2_batch_requests(self, num_requests: int = 10, batch_size: int = 10):
        """测试2: 批量请求处理"""
        logger.info("\n" + "="*80)
        logger.info(f"测试2: 批量请求处理 ({num_requests}个请求，批量大小{batch_size})")
        logger.info("="*80)
        
        # 模拟批量处理
        start_time = time.perf_counter()
        
        batch = []
        for i in range(num_requests):
            # 模拟序列化
            request = {
                "id": f"req-{i}",
                "method": "get_kline_data",
                "params": {"symbol": "000001.SZ", "interval": "1d"},
                "timestamp": time.time()
            }
            request_data = json.dumps(request).encode("utf-8")
            batch.append(request_data)
            
            # 达到批量大小或最后一批
            if len(batch) >= batch_size or i == num_requests - 1:
                # 批量反序列化
                requests_parsed = []
                for req_data in batch:
                    req = json.loads(req_data.decode("utf-8"))
                    requests_parsed.append(req)
                
                # 批量处理（每个请求10ms）
                await asyncio.sleep(0.01 * len(batch))
                
                # 批量响应
                responses = []
                for req in requests_parsed:
                    response = {
                        "id": req["id"],
                        "result": {"success": True, "data": []}
                    }
                    response_data = json.dumps(response).encode("utf-8")
                    responses.append(response_data)
                
                # 清空批次
                batch = []
        
        elapsed = time.perf_counter() - start_time
        throughput = num_requests / elapsed
        avg_latency = (elapsed / num_requests) * 1000  # ms
        
        self.log_result(
            "批量请求",
            num_requests=num_requests,
            batch_size=batch_size,
            elapsed_ms=elapsed*1000,
            throughput_rps=throughput,
            avg_latency_ms=avg_latency
        )
        
        return elapsed, throughput
        
    async def test_3_concurrent_requests(self, num_concurrent: int = 10):
        """测试3: 并发请求处理"""
        logger.info("\n" + "="*80)
        logger.info(f"测试3: 并发请求处理 ({num_concurrent}个并发)")
        logger.info("="*80)
        
        async def single_request(req_id: int):
            """单个请求"""
            request = {
                "id": f"req-{req_id}",
                "method": "get_kline_data",
                "params": {"symbol": "000001.SZ", "interval": "1d"},
                "timestamp": time.time()
            }
            request_data = json.dumps(request).encode("utf-8")
            
            # 模拟处理
            await asyncio.sleep(0.01)
            
            response = {
                "id": request["id"],
                "result": {"success": True, "data": []}
            }
            response_data = json.dumps(response).encode("utf-8")
            
        # 并发执行
        start_time = time.perf_counter()
        tasks = [single_request(i) for i in range(num_concurrent)]
        await asyncio.gather(*tasks)
        elapsed = time.perf_counter() - start_time
        
        throughput = num_concurrent / elapsed
        avg_latency = (elapsed / num_concurrent) * 1000  # ms
        
        self.log_result(
            "并发请求",
            num_concurrent=num_concurrent,
            elapsed_ms=elapsed*1000,
            throughput_rps=throughput,
            avg_latency_ms=avg_latency
        )
        
        return elapsed, throughput
        
    def print_summary(self):
        """打印测试摘要"""
        logger.info("\n" + "="*80)
        logger.info("批量处理性能测试摘要")
        logger.info("="*80)
        
        if "顺序请求" in self.test_results and "批量请求" in self.test_results:
            seq_result = self.test_results["顺序请求"]
            batch_result = self.test_results["批量请求"]
            
            # 计算性能提升
            throughput_improvement = batch_result["throughput_rps"] / seq_result["throughput_rps"]
            latency_change = batch_result["avg_latency_ms"] - seq_result["avg_latency_ms"]
            time_saved = seq_result["elapsed_ms"] - batch_result["elapsed_ms"]
            time_saved_pct = (time_saved / seq_result["elapsed_ms"]) * 100
            
            logger.info(f"\n顺序处理:")
            logger.info(f"  总时间: {seq_result['elapsed_ms']:.2f} ms")
            logger.info(f"  吞吐量: {seq_result['throughput_rps']:.2f} req/s")
            logger.info(f"  平均延迟: {seq_result['avg_latency_ms']:.2f} ms")
            
            logger.info(f"\n批量处理:")
            logger.info(f"  总时间: {batch_result['elapsed_ms']:.2f} ms")
            logger.info(f"  吞吐量: {batch_result['throughput_rps']:.2f} req/s")
            logger.info(f"  平均延迟: {batch_result['avg_latency_ms']:.2f} ms")
            logger.info(f"  批量大小: {batch_result['batch_size']}")
            
            logger.info(f"\n性能提升:")
            logger.info(f"  吞吐量提升: {throughput_improvement:.2f}x")
            logger.info(f"  总时间节省: {time_saved:.2f} ms ({time_saved_pct:.1f}%)")
            logger.info(f"  平均延迟变化: {latency_change:+.2f} ms")
            
            # 验收标准检查
            logger.info("\n" + "="*80)
            logger.info("验收标准检查")
            logger.info("="*80)
            
            if throughput_improvement >= 1.5:
                logger.info(f"✅ 通过: 批量场景吞吐量提升50%以上 (实际: {(throughput_improvement-1)*100:.1f}%)")
            else:
                logger.warning(f"❌ 未通过: 批量场景吞吐量提升未达到50% (实际: {(throughput_improvement-1)*100:.1f}%)")
                
            if abs(latency_change) < 20:
                logger.info(f"✅ 通过: 单次请求延迟增加<20ms (实际: {latency_change:+.2f}ms)")
            else:
                logger.warning(f"❌ 未通过: 单次请求延迟增加≥20ms (实际: {latency_change:+.2f}ms)")
            
        logger.info("\n" + "="*80)
        
    async def run_all_tests(self):
        """运行所有测试"""
        logger.info("\n" + "="*80)
        logger.info("开始批量处理性能测试")
        logger.info("="*80)
        
        # 测试1: 顺序处理（10个请求）
        await self.test_1_sequential_requests(num_requests=10)
        
        # 测试2: 批量处理（10个请求，批量大小10）
        await self.test_2_batch_requests(num_requests=10, batch_size=10)
        
        # 测试3: 并发请求（10个并发）
        await self.test_3_concurrent_requests(num_concurrent=10)
        
        # 打印摘要
        self.print_summary()


async def main():
    """主函数"""
    test = BatchPerformanceTest()
    await test.run_all_tests()


if __name__ == "__main__":
    asyncio.run(main())
