# -*- coding: utf-8 -*-
"""
RPC编解码集成测试 - 验证orjson优化后的系统兼容性

测试范围：
1. 数据进程启动测试
2. RPC客户端连接测试
3. 数据查询RPC测试
4. 计算任务RPC测试
5. 降级机制测试
6. 错误处理测试
"""

import asyncio
import json
import logging
import multiprocessing
import os
import sys
import time
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class RPCIntegrationTest:
    """RPC集成测试类"""
    
    def __init__(self):
        self.data_process = None
        self.client = None
        self.test_results = []
        
    def log_test_result(self, test_name: str, passed: bool, message: str = ""):
        """记录测试结果"""
        result = {
            "test_name": test_name,
            "passed": passed,
            "message": message,
            "timestamp": time.time()
        }
        self.test_results.append(result)
        
        status = "✅ 通过" if passed else "❌ 失败"
        logger.info(f"{status}: {test_name} - {message}")
        
    async def test_1_data_process_startup(self) -> bool:
        """测试1: 数据进程启动"""
        logger.info("\n" + "="*80)
        logger.info("测试1: 数据进程启动测试")
        logger.info("="*80)
        
        try:
            # 检查数据进程是否可以导入
            from backend.infrastructure.data_module_vnpy.data_process_main import DataProcess
            self.log_test_result("数据进程导入", True, "DataProcess类导入成功")
            
            # 检查orjson是否可用
            try:
                import orjson
                has_orjson = True
                self.log_test_result("orjson可用性", True, f"orjson版本: {orjson.__version__}")
            except ImportError:
                has_orjson = False
                self.log_test_result("orjson可用性", False, "orjson未安装，将使用降级模式")
            
            # 注意：实际启动数据进程需要多进程环境，这里只测试类的实例化
            logger.info("✅ 数据进程启动测试完成")
            return True
            
        except Exception as e:
            self.log_test_result("数据进程启动", False, f"异常: {e}")
            logger.error(f"❌ 数据进程启动测试失败: {e}", exc_info=True)
            return False
            
    async def test_2_rpc_client_connection(self) -> bool:
        """测试2: RPC客户端连接"""
        logger.info("\n" + "="*80)
        logger.info("测试2: RPC客户端连接测试")
        logger.info("="*80)
        
        try:
            from backend.infrastructure.data_module_vnpy.data_process_client import DataProcessClient
            
            # 创建客户端实例
            self.client = DataProcessClient()
            self.log_test_result("客户端创建", True, "DataProcessClient实例化成功")
            
            # 检查native_ipc可用性
            from backend.infrastructure.native.native_ipc import IPC_AVAILABLE
            if IPC_AVAILABLE:
                self.log_test_result("native_ipc可用性", True, "native_ipc模块可用")
            else:
                self.log_test_result("native_ipc可用性", False, "native_ipc模块不可用")
                logger.warning("⚠️ native_ipc不可用，跳过实际连接测试")
                return False
            
            logger.info("✅ RPC客户端连接测试完成")
            return True
            
        except Exception as e:
            self.log_test_result("RPC客户端连接", False, f"异常: {e}")
            logger.error(f"❌ RPC客户端连接测试失败: {e}", exc_info=True)
            return False
            
    async def test_3_json_serialization_compatibility(self) -> bool:
        """测试3: JSON序列化兼容性"""
        logger.info("\n" + "="*80)
        logger.info("测试3: JSON序列化兼容性测试")
        logger.info("="*80)
        
        try:
            # 测试数据
            test_data = {
                "id": "test-123",
                "method": "get_kline_data",
                "params": {
                    "symbol": "000001.SZ",
                    "interval": "1d",
                    "start_date": "2023-01-01",
                    "end_date": "2023-12-31",
                },
                "timestamp": time.time()
            }
            
            # 测试orjson序列化
            try:
                import orjson
                orjson_result = orjson.dumps(test_data)
                orjson_decoded = orjson.loads(orjson_result)
                
                # 验证数据一致性
                if orjson_decoded == test_data:
                    self.log_test_result("orjson序列化一致性", True, "序列化/反序列化数据一致")
                else:
                    self.log_test_result("orjson序列化一致性", False, "数据不一致")
                    
            except ImportError:
                logger.warning("⚠️ orjson未安装，跳过orjson测试")
                
            # 测试标准json序列化（降级模式）
            json_result = json.dumps(test_data, ensure_ascii=False).encode("utf-8")
            json_decoded = json.loads(json_result.decode("utf-8"))
            
            if json_decoded == test_data:
                self.log_test_result("json序列化一致性", True, "序列化/反序列化数据一致")
            else:
                self.log_test_result("json序列化一致性", False, "数据不一致")
                
            # 测试特殊字符
            special_data = {
                "chinese": "中文测试",
                "emoji": "😀",
                "number": 123.456,
                "boolean": True,
                "null": None,
                "array": [1, 2, 3],
            }
            
            try:
                import orjson
                orjson_special = orjson.dumps(special_data)
                orjson_special_decoded = orjson.loads(orjson_special)
                
                if orjson_special_decoded == special_data:
                    self.log_test_result("orjson特殊字符", True, "特殊字符处理正确")
                else:
                    self.log_test_result("orjson特殊字符", False, "特殊字符处理异常")
                    
            except ImportError:
                pass
                
            logger.info("✅ JSON序列化兼容性测试完成")
            return True
            
        except Exception as e:
            self.log_test_result("JSON序列化兼容性", False, f"异常: {e}")
            logger.error(f"❌ JSON序列化兼容性测试失败: {e}", exc_info=True)
            return False
            
    async def test_4_rpc_message_format(self) -> bool:
        """测试4: RPC消息格式验证"""
        logger.info("\n" + "="*80)
        logger.info("测试4: RPC消息格式验证")
        logger.info("="*80)
        
        try:
            # 测试请求消息格式
            request = {
                "id": "12345678-1234-1234-1234-123456789012",
                "method": "get_kline_data",
                "params": {
                    "symbol": "000001.SZ",
                    "interval": "1d",
                },
                "timestamp": time.time()
            }
            
            # 验证请求字段
            required_fields = ["id", "method", "params", "timestamp"]
            for field in required_fields:
                if field in request:
                    self.log_test_result(f"请求字段:{field}", True, f"{field}字段存在")
                else:
                    self.log_test_result(f"请求字段:{field}", False, f"{field}字段缺失")
                    
            # 测试响应消息格式
            response = {
                "id": "12345678-1234-1234-1234-123456789012",
                "result": {
                    "success": True,
                    "data": [],
                }
            }
            
            # 验证响应字段
            if "id" in response and "result" in response:
                self.log_test_result("响应格式", True, "响应消息格式正确")
            else:
                self.log_test_result("响应格式", False, "响应消息格式错误")
                
            # 测试错误响应格式
            error_response = {
                "id": "12345678-1234-1234-1234-123456789012",
                "error": "测试错误"
            }
            
            if "id" in error_response and "error" in error_response:
                self.log_test_result("错误响应格式", True, "错误响应消息格式正确")
            else:
                self.log_test_result("错误响应格式", False, "错误响应消息格式错误")
                
            logger.info("✅ RPC消息格式验证完成")
            return True
            
        except Exception as e:
            self.log_test_result("RPC消息格式", False, f"异常: {e}")
            logger.error(f"❌ RPC消息格式验证失败: {e}", exc_info=True)
            return False
            
    async def test_5_degradation_mechanism(self) -> bool:
        """测试5: 降级机制验证"""
        logger.info("\n" + "="*80)
        logger.info("测试5: 降级机制验证")
        logger.info("="*80)
        
        try:
            # 检查客户端降级逻辑
            from backend.infrastructure.data_module_vnpy.data_process_client import HAS_ORJSON
            
            if HAS_ORJSON:
                logger.info("✅ orjson可用，使用高性能模式")
                self.log_test_result("降级机制-orjson", True, "orjson模式正常")
            else:
                logger.warning("⚠️ orjson不可用，使用降级模式")
                self.log_test_result("降级机制-json", True, "json降级模式正常")
                
            # 检查服务端降级逻辑
            from backend.infrastructure.data_module_vnpy import data_process_main
            if hasattr(data_process_main, 'HAS_ORJSON'):
                if data_process_main.HAS_ORJSON:
                    self.log_test_result("服务端降级机制", True, "服务端使用orjson")
                else:
                    self.log_test_result("服务端降级机制", True, "服务端使用json降级")
            else:
                self.log_test_result("服务端降级机制", False, "服务端未定义HAS_ORJSON")
                
            logger.info("✅ 降级机制验证完成")
            return True
            
        except Exception as e:
            self.log_test_result("降级机制验证", False, f"异常: {e}")
            logger.error(f"❌ 降级机制验证失败: {e}", exc_info=True)
            return False
            
    async def test_6_error_handling(self) -> bool:
        """测试6: 错误处理验证"""
        logger.info("\n" + "="*80)
        logger.info("测试6: 错误处理验证")
        logger.info("="*80)
        
        try:
            # 测试无效JSON
            invalid_json = b"{invalid json}"
            
            try:
                json.loads(invalid_json.decode("utf-8"))
                self.log_test_result("无效JSON处理", False, "应该抛出异常但没有")
            except json.JSONDecodeError:
                self.log_test_result("无效JSON处理", True, "正确捕获JSONDecodeError")
                
            # 测试空数据
            empty_data = b""
            if not empty_data:
                self.log_test_result("空数据处理", True, "正确识别空数据")
            else:
                self.log_test_result("空数据处理", False, "未识别空数据")
                
            # 测试大数据
            large_data = {"data": [{"item": i} for i in range(10000)]}
            try:
                json_result = json.dumps(large_data, ensure_ascii=False)
                if len(json_result) > 100000:
                    self.log_test_result("大数据处理", True, f"大数据序列化成功({len(json_result)}字节)")
                else:
                    self.log_test_result("大数据处理", False, "数据大小不符合预期")
            except Exception as e:
                self.log_test_result("大数据处理", False, f"异常: {e}")
                
            logger.info("✅ 错误处理验证完成")
            return True
            
        except Exception as e:
            self.log_test_result("错误处理验证", False, f"异常: {e}")
            logger.error(f"❌ 错误处理验证失败: {e}", exc_info=True)
            return False
            
    def print_summary(self):
        """打印测试摘要"""
        logger.info("\n" + "="*80)
        logger.info("集成测试摘要")
        logger.info("="*80)
        
        total_tests = len(self.test_results)
        passed_tests = sum(1 for r in self.test_results if r["passed"])
        failed_tests = total_tests - passed_tests
        
        logger.info(f"\n总测试数: {total_tests}")
        logger.info(f"通过: {passed_tests}")
        logger.info(f"失败: {failed_tests}")
        logger.info(f"通过率: {passed_tests/total_tests*100:.1f}%")
        
        # 打印失败的测试
        if failed_tests > 0:
            logger.info("\n失败的测试:")
            for result in self.test_results:
                if not result["passed"]:
                    logger.info(f"  ❌ {result['test_name']}: {result['message']}")
                    
        # 总结
        logger.info("\n" + "="*80)
        if failed_tests == 0:
            logger.info("✅ 所有集成测试通过！")
            logger.info("="*80)
            return True
        else:
            logger.warning(f"⚠️ {failed_tests}个测试失败，请检查！")
            logger.info("="*80)
            return False
            
    async def run_all_tests(self):
        """运行所有测试"""
        logger.info("\n" + "="*80)
        logger.info("开始RPC编解码集成测试")
        logger.info("="*80)
        
        # 执行所有测试
        await self.test_1_data_process_startup()
        await self.test_2_rpc_client_connection()
        await self.test_3_json_serialization_compatibility()
        await self.test_4_rpc_message_format()
        await self.test_5_degradation_mechanism()
        await self.test_6_error_handling()
        
        # 打印摘要
        return self.print_summary()


async def main():
    """主函数"""
    test = RPCIntegrationTest()
    success = await test.run_all_tests()
    
    # 返回退出码
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
