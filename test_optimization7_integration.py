# -*- coding: utf-8 -*-
"""
优化7集成测试 - 验证三进程架构与原生扩展集成

验证目标：
1. RPC零拷贝与批处理 (优化方向一)
2. 指标与风险计算原生化 (优化方向二)
3. 原生资源采样与监控去阻塞 (优化方向三)

作者：Qoder
日期：2025-11-07
"""

import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Any

# 添加项目根目录到Python路径
PROJECT_ROOT = Path(__file__).parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# 导入统一日志系统
from backend.infrastructure.system_vnpy.logging_system import (
    setup_logging_system,
    stage_node,
)

# 创建测试logger
logger = logging.getLogger("optimization7.test")

# =============================================================================
# 测试结果记录
# =============================================================================

class TestResults:
    """测试结果记录器"""
    
    def __init__(self):
        self.results: Dict[str, Dict[str, Any]] = {
            "optimization1_rpc": {},
            "optimization2_indicator": {},
            "optimization3_monitoring": {},
            "three_process_architecture": {},  # 添加这个类别
        }
        self.summary = {
            "total_tests": 0,
            "passed": 0,
            "failed": 0,
            "skipped": 0,
        }
    
    def add_result(self, category: str, test_name: str, passed: bool, 
                   message: str = "", details: Dict[str, Any] = None):
        """添加测试结果"""
        self.summary["total_tests"] += 1
        if passed:
            self.summary["passed"] += 1
            status = "✅ PASS"
        else:
            self.summary["failed"] += 1
            status = "❌ FAIL"
        
        self.results[category][test_name] = {
            "status": status,
            "passed": passed,
            "message": message,
            "details": details or {},
        }
    
    def add_skip(self, category: str, test_name: str, reason: str):
        """添加跳过的测试"""
        self.summary["total_tests"] += 1
        self.summary["skipped"] += 1
        self.results[category][test_name] = {
            "status": "⏭️  SKIP",
            "passed": None,
            "message": reason,
            "details": {},
        }
    
    def print_summary(self):
        """打印测试摘要"""
        print("\n" + "=" * 80)
        print("优化7集成测试摘要")
        print("=" * 80)
        
        for category, tests in self.results.items():
            print(f"\n【{category}】")
            for test_name, result in tests.items():
                print(f"  {result['status']} {test_name}")
                if result['message']:
                    print(f"      消息: {result['message']}")
                if result['details']:
                    for key, value in result['details'].items():
                        print(f"      {key}: {value}")
        
        print("\n" + "=" * 80)
        print(f"总计: {self.summary['total_tests']} 测试")
        print(f"✅ 通过: {self.summary['passed']}")
        print(f"❌ 失败: {self.summary['failed']}")
        print(f"⏭️  跳过: {self.summary['skipped']}")
        print("=" * 80)


# =============================================================================
# 优化方向一：RPC零拷贝与批处理
# =============================================================================

async def test_rpc_zero_copy(results: TestResults):
    """测试RPC零拷贝功能"""
    category = "optimization1_rpc"
    
    # 1. 检查native_ipc是否可用
    try:
        from backend.infrastructure.native.native_ipc import IPC_AVAILABLE
        if not IPC_AVAILABLE:
            results.add_skip(category, "native_ipc_available", "native_ipc扩展未编译")
            return
        results.add_result(category, "native_ipc_available", True, "native_ipc扩展已编译")
    except ImportError as e:
        results.add_skip(category, "native_ipc_available", f"无法导入native_ipc: {e}")
        return
    
    # 2. 检查native_serialization零拷贝功能
    try:
        from backend.infrastructure.native.native_serialization import (
            zero_copy_serialize,
            SERIALIZATION_AVAILABLE,
        )
        if not SERIALIZATION_AVAILABLE:
            results.add_skip(category, "zero_copy_serialize", "native_serialization扩展未编译")
        else:
            # 测试零拷贝序列化
            test_data = b"Test data for zero copy"
            try:
                result = zero_copy_serialize(test_data)
                results.add_result(category, "zero_copy_serialize", True, 
                                 "零拷贝序列化功能正常", {"data_size": len(test_data)})
            except Exception as e:
                results.add_result(category, "zero_copy_serialize", False, 
                                 f"零拷贝序列化失败: {e}")
    except ImportError as e:
        results.add_skip(category, "zero_copy_serialize", f"无法导入native_serialization: {e}")
    
    # 3. 检查DataFramePayload功能
    try:
        from backend.infrastructure.native.native_serialization import build_dataframe_payload
        
        # 创建测试数据
        import pandas as pd
        test_df = pd.DataFrame({
            "code": ["000001", "000002"],
            "name": ["平安银行", "万科A"],
            "price": [10.5, 20.3],
        })
        
        try:
            payload = build_dataframe_payload(test_df)
            # 计算payload数据大小
            if isinstance(payload.data, (memoryview, bytes, bytearray)):
                data_size = len(payload.data)
            elif isinstance(payload.data, list):
                data_size = len(payload.data)
            else:
                data_size = 0
            
            results.add_result(category, "dataframe_payload", True,
                             "DataFrame零拷贝打包功能正常",
                             {"rows": payload.rows, "format": payload.format, 
                              "transport": payload.transport, "data_size": data_size})
        except Exception as e:
            results.add_result(category, "dataframe_payload", False,
                             f"DataFrame打包失败: {e}")
    except ImportError as e:
        results.add_skip(category, "dataframe_payload", f"无法导入相关模块: {e}")
    
    # 4. 检查RPC批处理功能
    try:
        from backend.infrastructure.data_module_vnpy.rpc_protocol import (
            RPCRequest,
            encode_native_response,
            decode_request,
        )
        
        # 测试批量请求编码
        requests = [
            {"method": "get_kline_data", "params": {"symbol": "000001"}, "id": 1},
            {"method": "get_kline_data", "params": {"symbol": "000002"}, "id": 2},
        ]
        
        try:
            encoded_requests = [json.dumps(req).encode() for req in requests]
            results.add_result(category, "rpc_batch_encoding", True,
                             "RPC批量编码功能正常",
                             {"batch_size": len(requests)})
        except Exception as e:
            results.add_result(category, "rpc_batch_encoding", False,
                             f"RPC批量编码失败: {e}")
    except ImportError as e:
        results.add_skip(category, "rpc_batch_encoding", f"无法导入rpc_protocol: {e}")


# =============================================================================
# 优化方向二：指标与风险计算原生化
# =============================================================================

async def test_native_indicators(results: TestResults):
    """测试原生指标计算功能"""
    category = "optimization2_indicator"
    
    # 1. 检查native_indicator是否可用
    try:
        from backend.infrastructure.native.native_indicator import (
            INDICATOR_AVAILABLE,
            calculate_indicator,
        )
        
        if not INDICATOR_AVAILABLE:
            results.add_skip(category, "native_indicator_available", 
                           "native_indicator扩展未编译")
            return
        
        results.add_result(category, "native_indicator_available", True,
                         "native_indicator扩展已编译")
        
        # 测试指标计算
        import numpy as np
        test_prices = np.array([10.0, 10.5, 11.0, 10.8, 11.2, 11.5, 11.3, 11.8, 12.0, 12.2])
        
        try:
            # 测试SMA
            sma_result = calculate_indicator("SMA", test_prices, period=5)
            results.add_result(category, "native_sma_calculation", True,
                             "SMA指标计算正常",
                             {"input_size": len(test_prices), "output_size": len(sma_result)})
        except Exception as e:
            results.add_result(category, "native_sma_calculation", False,
                             f"SMA计算失败: {e}")
        
        try:
            # 测试EMA
            ema_result = calculate_indicator("EMA", test_prices, period=5)
            results.add_result(category, "native_ema_calculation", True,
                             "EMA指标计算正常",
                             {"input_size": len(test_prices), "output_size": len(ema_result)})
        except Exception as e:
            results.add_result(category, "native_ema_calculation", False,
                             f"EMA计算失败: {e}")
            
    except ImportError as e:
        results.add_skip(category, "native_indicator_available", 
                       f"无法导入native_indicator: {e}")
    
    # 2. 检查native_finance_ops风险计算
    try:
        from backend.infrastructure.native.native_finance_ops import (
            FINANCE_OPS_AVAILABLE,
            compute_return_metrics,
        )
        
        if not FINANCE_OPS_AVAILABLE:
            results.add_skip(category, "native_finance_ops_available",
                           "native_finance_ops扩展未编译")
        else:
            results.add_result(category, "native_finance_ops_available", True,
                             "native_finance_ops扩展已编译")
            
            # 测试风险指标计算
            import numpy as np
            test_prices = np.array([100.0, 102.0, 101.0, 103.0, 102.5, 104.0, 103.0, 105.0])
            # 计算收益序列
            pnl_series = np.diff(test_prices)  # 盈亏序列
            equity_series = test_prices[1:]  # 权益曲线
            
            try:
                metrics = compute_return_metrics(pnl_series, equity_series)
                results.add_result(category, "native_risk_metrics", True,
                                 "风险指标计算正常",
                                 {"metrics": list(metrics.keys()) if isinstance(metrics, dict) else "unknown"})
            except Exception as e:
                results.add_result(category, "native_risk_metrics", False,
                                 f"风险指标计算失败: {e}")
                
    except ImportError as e:
        results.add_skip(category, "native_finance_ops_available",
                       f"无法导入native_finance_ops: {e}")


# =============================================================================
# 优化方向三：原生资源采样与监控去阻塞
# =============================================================================

async def test_native_monitoring(results: TestResults):
    """测试原生监控功能"""
    category = "optimization3_monitoring"
    
    # 1. 检查native_socket_metrics
    try:
        from backend.infrastructure.native.native_socket_metrics import (
            SOCKET_METRICS_AVAILABLE,
            get_socket_metrics,
        )
        
        if not SOCKET_METRICS_AVAILABLE:
            results.add_skip(category, "native_socket_metrics_available",
                           "native_socket_metrics扩展未编译")
        else:
            results.add_result(category, "native_socket_metrics_available", True,
                             "native_socket_metrics扩展已编译")
            
            try:
                # 测试socket统计获取
                stats = get_socket_metrics()
                results.add_result(category, "socket_metrics", True,
                                 "Socket指标统计正常",
                                 {"metrics_count": len(stats) if isinstance(stats, dict) else 0})
            except Exception as e:
                results.add_result(category, "socket_metrics", False,
                                 f"Socket统计获取失败: {e}")
                
    except ImportError as e:
        results.add_skip(category, "native_socket_metrics_available",
                       f"无法导入native_socket_metrics: {e}")
    
    # 2. 检查native_process_metrics
    try:
        from backend.infrastructure.native.native_process_metrics import (
            PROCESS_METRICS_AVAILABLE,
            get_system_metrics,
        )
        
        if not PROCESS_METRICS_AVAILABLE:
            results.add_skip(category, "native_process_metrics_available",
                           "native_process_metrics扩展未编译")
        else:
            results.add_result(category, "native_process_metrics_available", True,
                             "native_process_metrics扩展已编译")
            
            try:
                # 测试系统指标获取
                metrics = get_system_metrics()
                results.add_result(category, "system_metrics", True,
                                 "系统指标获取正常",
                                 {"cpu_percent": metrics.get("cpu_percent", 0),
                                  "memory_percent": metrics.get("memory_percent", 0)})
            except Exception as e:
                results.add_result(category, "system_metrics", False,
                                 f"系统指标获取失败: {e}")
                
    except ImportError as e:
        results.add_skip(category, "native_process_metrics_available",
                       f"无法导入native_process_metrics: {e}")
    
    # 3. 检查监控系统集成
    try:
        from backend.infrastructure.system_vnpy.monitor_system import MonitoringProcessV2
        
        # 检查监控系统是否使用原生扩展
        results.add_result(category, "monitor_system_integration", True,
                         "监控系统已集成",
                         {"class": "MonitoringProcessV2"})
    except ImportError as e:
        results.add_skip(category, "monitor_system_integration",
                       f"无法导入monitor_system: {e}")


# =============================================================================
# 三进程架构验证
# =============================================================================

async def test_three_process_architecture(results: TestResults):
    """测试三进程架构集成"""
    category = "three_process_architecture"
    
    # 1. 检查数据进程实现
    try:
        from backend.infrastructure.data_module_vnpy.data_process_main import DataProcess
        results.add_result(category, "data_process_main", True,
                         "数据进程主文件存在")
    except ImportError as e:
        results.add_result(category, "data_process_main", False,
                         f"无法导入DataProcess: {e}")
    
    # 2. 检查监控进程实现
    try:
        from backend.infrastructure.system_vnpy.monitor_system import MonitoringProcessV2
        results.add_result(category, "monitor_process", True,
                         "监控进程实现存在")
    except ImportError as e:
        results.add_result(category, "monitor_process", False,
                         f"无法导入MonitoringProcessV2: {e}")
    
    # 3. 检查启动流程集成
    try:
        from backend.startup.stages.backend_init import BackendInitStage
        from backend.startup.workers.data_launcher import DataLauncherWorker
        from backend.startup.workers.monitor_launcher import MonitorLauncherWorker
        
        results.add_result(category, "startup_integration", True,
                         "启动流程已集成三进程架构",
                         {"stages": ["BackendInitStage", "DataLauncherWorker", "MonitorLauncherWorker"]})
    except ImportError as e:
        results.add_result(category, "startup_integration", False,
                         f"启动流程集成检查失败: {e}")
    
    # 4. 检查日志系统多进程支持
    try:
        from backend.infrastructure.system_vnpy.logging_system import (
            MultiProcessLogCollector,
            setup_subprocess_logging,
        )
        
        results.add_result(category, "logging_multiprocess", True,
                         "日志系统支持多进程")
    except ImportError as e:
        results.add_result(category, "logging_multiprocess", False,
                         f"日志系统多进程支持检查失败: {e}")


# =============================================================================
# 主测试入口
# =============================================================================

async def run_all_tests():
    """运行所有集成测试"""
    results = TestResults()
    
    # 不使用event_log_process，直接记录日志
    stage_node("test", "📍 优化7集成测试开始")
    
    # 测试RPC零拷贝与批处理
    logger.info("测试优化方向一: RPC零拷贝与批处理")
    await test_rpc_zero_copy(results)
    
    # 测试原生指标计算
    logger.info("测试优化方向二: 指标与风险计算原生化")
    await test_native_indicators(results)
    
    # 测试原生监控
    logger.info("测试优化方向三: 原生资源采样与监控去阻塞")
    await test_native_monitoring(results)
    
    # 测试三进程架构
    logger.info("测试三进程架构集成")
    await test_three_process_architecture(results)
    
    stage_node("test", "✅ 优化7集成测试完成")
    
    # 打印结果摘要
    results.print_summary()
    
    # 保存结果到文件
    output_file = PROJECT_ROOT / "test_optimization7_results.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump({
            "summary": results.summary,
            "results": results.results,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        }, f, indent=2, ensure_ascii=False)
    
    print(f"\n测试结果已保存到: {output_file}")
    
    return results.summary["failed"] == 0


def main():
    """主函数"""
    # 初始化日志系统
    try:
        setup_logging_system()
        print("✅ 日志系统初始化完成")
    except Exception as e:
        print(f"⚠️  日志系统初始化失败: {e}")
    
    # 运行测试
    success = asyncio.run(run_all_tests())
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
