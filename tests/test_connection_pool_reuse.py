"""
连接池复用机制测试

测试场景：
1. 启动时测速（keep_pool=True）- 连接池应保持打开
2. 手动测速（keep_pool=False）- 连接池应立即关闭
3. 关闭连接池 - 应正常关闭
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import logging
from backend.infrastructure.data_module_vnpy.load_balancer import ServerPoolManager
from backend.infrastructure.data_module_vnpy.core_engine import ConfigManager

# 配置日志
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def test_startup_mode():
    """测试启动模式（keep_pool=True）"""
    logger.info("=" * 60)
    logger.info("测试1: 启动模式（keep_pool=True）")
    logger.info("=" * 60)
    
    config_manager = ConfigManager()
    pool_manager = ServerPoolManager(config_manager)
    
    # 测速并保持连接池
    logger.info("开始测速（keep_pool=True）...")
    pool_manager.test_servers(max_workers=2, keep_pool=True)
    
    # 检查连接池是否保持
    if pool_manager._connection_pool is not None:
        logger.info("✅ 连接池已保持打开状态")
        logger.info(f"   连接池模式: {pool_manager._pool_mode}")
    else:
        logger.error("❌ 连接池未保持打开状态")
    
    # 关闭连接池
    logger.info("关闭连接池...")
    pool_manager.close_connection_pool()
    
    # 检查连接池是否关闭
    if pool_manager._connection_pool is None:
        logger.info("✅ 连接池已成功关闭")
        logger.info(f"   连接池模式: {pool_manager._pool_mode}")
    else:
        logger.error("❌ 连接池未成功关闭")
    
    logger.info("")


def test_manual_mode():
    """测试手动模式（keep_pool=False）"""
    logger.info("=" * 60)
    logger.info("测试2: 手动模式（keep_pool=False，默认值）")
    logger.info("=" * 60)
    
    config_manager = ConfigManager()
    pool_manager = ServerPoolManager(config_manager)
    
    # 测速（不保持连接池）
    logger.info("开始测速（keep_pool=False）...")
    pool_manager.test_servers(max_workers=2, keep_pool=False)
    
    # 检查连接池是否立即关闭
    if pool_manager._connection_pool is None:
        logger.info("✅ 连接池已立即关闭（符合预期）")
        logger.info(f"   连接池模式: {pool_manager._pool_mode}")
    else:
        logger.error("❌ 连接池未立即关闭")
    
    logger.info("")


def test_default_mode():
    """测试默认模式（不传递keep_pool参数）"""
    logger.info("=" * 60)
    logger.info("测试3: 默认模式（不传递keep_pool参数）")
    logger.info("=" * 60)
    
    config_manager = ConfigManager()
    pool_manager = ServerPoolManager(config_manager)
    
    # 测速（使用默认参数）
    logger.info("开始测速（使用默认参数）...")
    pool_manager.test_servers(max_workers=2)
    
    # 检查连接池是否立即关闭
    if pool_manager._connection_pool is None:
        logger.info("✅ 连接池已立即关闭（默认行为）")
        logger.info(f"   连接池模式: {pool_manager._pool_mode}")
    else:
        logger.error("❌ 连接池未立即关闭")
    
    logger.info("")


def test_close_twice():
    """测试重复关闭连接池"""
    logger.info("=" * 60)
    logger.info("测试4: 重复关闭连接池")
    logger.info("=" * 60)
    
    config_manager = ConfigManager()
    pool_manager = ServerPoolManager(config_manager)
    
    # 测速并保持连接池
    logger.info("开始测速（keep_pool=True）...")
    pool_manager.test_servers(max_workers=2, keep_pool=True)
    
    # 第一次关闭
    logger.info("第一次关闭连接池...")
    pool_manager.close_connection_pool()
    
    # 第二次关闭（应该不会报错）
    logger.info("第二次关闭连接池（应该不会报错）...")
    pool_manager.close_connection_pool()
    
    logger.info("✅ 重复关闭测试通过")
    logger.info("")


if __name__ == "__main__":
    try:
        # 运行所有测试
        test_startup_mode()
        test_manual_mode()
        test_default_mode()
        test_close_twice()
        
        logger.info("=" * 60)
        logger.info("✅ 所有测试完成")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"❌ 测试失败: {e}", exc_info=True)
        sys.exit(1)
