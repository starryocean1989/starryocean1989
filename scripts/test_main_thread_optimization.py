# -*- coding: utf-8 -*-
"""
主线程缓存检查优化验证脚本

验证点：
1. 主线程初始化不再读取缓存文件
2. 只有validation_worker读取和下载缓存
3. 事件系统正常工作
4. 启动速度提升
"""

import sys
import time
import logging
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_data_center_service_init():
    """测试 DataCenterService 初始化（不应读取缓存）"""
    logger.info("=" * 70)
    logger.info("测试1: DataCenterService 初始化（应该快速完成，不读取缓存）")
    logger.info("=" * 70)
    
    try:
        # 导入必要的模块
        from backend.core.config import init_settings
        from backend.services.data_center_service import DataCenterService
        
        # 初始化配置
        config_file = project_root / "config" / "terminal_config.json"
        init_settings(str(config_file))
        
        # 记录开始时间
        start_time = time.time()
        
        # 创建并初始化服务
        service = DataCenterService()
        success = service._do_initialize()
        
        # 记录结束时间
        end_time = time.time()
        elapsed = end_time - start_time
        
        # 验证结果
        logger.info(f"✅ 初始化{'成功' if success else '失败'}")
        logger.info(f"⏱️  耗时: {elapsed:.3f}秒")
        
        # 检查是否快速完成（应该 < 0.5秒）
        if elapsed < 0.5:
            logger.info("✅ 性能验证通过：初始化时间 < 0.5秒（未读取缓存文件）")
        else:
            logger.warning(f"⚠️ 性能验证失败：初始化时间 {elapsed:.3f}秒 >= 0.5秒")
        
        # 检查缓存状态（应该为空或由事件加载）
        if service._symbol_cache is None:
            logger.info("✅ 缓存状态验证通过：主线程未加载缓存（_symbol_cache is None）")
        else:
            logger.warning("⚠️ 缓存状态异常：主线程不应该加载缓存")
        
        return success and elapsed < 0.5 and service._symbol_cache is None
        
    except Exception as e:
        logger.error(f"❌ 测试失败: {e}", exc_info=True)
        return False


def test_event_listener_registration():
    """测试事件监听器是否正确注册"""
    logger.info("")
    logger.info("=" * 70)
    logger.info("测试2: 事件监听器注册")
    logger.info("=" * 70)
    
    try:
        from backend.core.config import init_settings
        from backend.services.data_center_service import DataCenterService
        from vnpy.event import EventEngine
        
        # 初始化配置
        config_file = project_root / "config" / "terminal_config.json"
        init_settings(str(config_file))
        
        # 创建EventEngine
        event_engine = EventEngine()
        
        # 将EventEngine设置为全局
        from backend.core import base
        base._event_engine = event_engine
        
        # 创建并初始化服务
        service = DataCenterService()
        service._do_initialize()
        
        # 检查事件监听器是否注册
        from backend.infrastructure.data_module_vnpy.events import (
            EVENT_SYMBOL_CACHE_LOADED,
            EVENT_IPO_CACHE_UPDATED,
            EVENT_VALIDATION_COMPLETED,
        )
        
        registered_events = [
            EVENT_SYMBOL_CACHE_LOADED,
            EVENT_IPO_CACHE_UPDATED,
            EVENT_VALIDATION_COMPLETED,
        ]
        
        all_registered = True
        for event_type in registered_events:
            handlers = event_engine._handlers.get(event_type, [])
            if handlers:
                logger.info(f"✅ 事件 {event_type} 已注册 {len(handlers)} 个处理器")
            else:
                logger.warning(f"⚠️ 事件 {event_type} 未注册处理器")
                all_registered = False
        
        if all_registered:
            logger.info("✅ 所有事件监听器注册验证通过")
        
        # 清理
        event_engine.stop()
        
        return all_registered
        
    except Exception as e:
        logger.error(f"❌ 测试失败: {e}", exc_info=True)
        return False


def test_cache_file_access():
    """测试缓存文件访问（主线程不应访问）"""
    logger.info("")
    logger.info("=" * 70)
    logger.info("测试3: 缓存文件访问监控")
    logger.info("=" * 70)
    logger.info("💡 提示：此测试需要手工检查日志，确认没有'本地缓存不存在'的日志")
    logger.info("    在 DataCenterService 初始化过程中")
    
    try:
        from backend.core.config import init_settings
        from backend.services.data_center_service import DataCenterService
        
        # 初始化配置
        config_file = project_root / "config" / "terminal_config.json"
        init_settings(str(config_file))
        
        # 设置监控日志级别
        data_acq_logger = logging.getLogger(
            "backend.infrastructure.data_module_vnpy.data_acquisition"
        )
        data_acq_logger.setLevel(logging.DEBUG)
        
        # 添加自定义处理器来捕获"本地缓存不存在"日志
        cache_access_detected = {"count": 0}
        
        class CacheAccessHandler(logging.Handler):
            def emit(self, record):
                if "本地缓存不存在" in record.getMessage():
                    cache_access_detected["count"] += 1
                    logger.warning(f"⚠️ 检测到缓存访问: {record.getMessage()}")
        
        handler = CacheAccessHandler()
        data_acq_logger.addHandler(handler)
        
        # 创建并初始化服务
        service = DataCenterService()
        service._do_initialize()
        
        # 检查结果
        if cache_access_detected["count"] == 0:
            logger.info("✅ 缓存访问验证通过：主线程未访问缓存文件")
        else:
            logger.warning(
                f"⚠️ 缓存访问验证失败：检测到 {cache_access_detected['count']} 次缓存访问"
            )
        
        # 清理
        data_acq_logger.removeHandler(handler)
        
        return cache_access_detected["count"] == 0
        
    except Exception as e:
        logger.error(f"❌ 测试失败: {e}", exc_info=True)
        return False


def test_method_still_exists():
    """测试 _check_symbol_cache_readonly 方法仍然存在（供事件使用）"""
    logger.info("")
    logger.info("=" * 70)
    logger.info("测试4: _check_symbol_cache_readonly 方法存在性")
    logger.info("=" * 70)
    
    try:
        from backend.services.data_center_service import DataCenterService
        
        # 检查方法是否存在
        if hasattr(DataCenterService, "_check_symbol_cache_readonly"):
            logger.info("✅ _check_symbol_cache_readonly 方法仍然存在")
            
            # 检查方法是否可调用
            service = DataCenterService()
            if callable(getattr(service, "_check_symbol_cache_readonly")):
                logger.info("✅ _check_symbol_cache_readonly 方法可调用")
                return True
            else:
                logger.error("❌ _check_symbol_cache_readonly 方法不可调用")
                return False
        else:
            logger.error("❌ _check_symbol_cache_readonly 方法不存在")
            return False
        
    except Exception as e:
        logger.error(f"❌ 测试失败: {e}", exc_info=True)
        return False


def main():
    """运行所有测试"""
    logger.info("╔═════════════════════════════════════════════════════════════════════╗")
    logger.info("║          主线程缓存检查优化验证测试                                 ║")
    logger.info("╚═════════════════════════════════════════════════════════════════════╝")
    logger.info("")
    
    results = []
    
    # 测试1: DataCenterService初始化性能
    results.append(("DataCenterService初始化性能", test_data_center_service_init()))
    
    # 测试2: 事件监听器注册
    results.append(("事件监听器注册", test_event_listener_registration()))
    
    # 测试3: 缓存文件访问监控
    results.append(("缓存文件访问监控", test_cache_file_access()))
    
    # 测试4: 方法存在性
    results.append(("_check_symbol_cache_readonly方法存在性", test_method_still_exists()))
    
    # 输出总结
    logger.info("")
    logger.info("=" * 70)
    logger.info("测试总结")
    logger.info("=" * 70)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        logger.info(f"{status} - {name}")
    
    logger.info("")
    logger.info(f"测试结果: {passed}/{total} 通过")
    
    if passed == total:
        logger.info("🎉 所有测试通过！优化验证成功！")
        return 0
    else:
        logger.warning(f"⚠️ {total - passed} 个测试失败，请检查")
        return 1


if __name__ == "__main__":
    sys.exit(main())

