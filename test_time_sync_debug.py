#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试网络时间同步"""

import logging
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 配置日志
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

def test_network_time_sync():
    """测试网络时间同步"""
    logger.info("=" * 70)
    logger.info("开始测试网络时间同步")
    logger.info("=" * 70)
    
    try:
        from backend.infrastructure.data_module_vnpy.core_engine import NetworkTimeSync
        
        # 创建实例
        sync = NetworkTimeSync.get_instance()
        logger.info("✓ NetworkTimeSync实例创建成功")
        
        # 执行同步
        logger.info("开始同步网络时间...")
        success, offset = sync.sync_time()
        
        if success:
            logger.info(f"✅ 时间同步成功!")
            logger.info(f"   时间偏移: {offset:.3f}秒")
            
            # 获取统计信息
            stats = sync.get_stats()
            logger.info("统计信息:")
            for key, value in stats.items():
                logger.info(f"   {key}: {value}")
        else:
            logger.error("❌ 时间同步失败")
            logger.error("请检查:")
            logger.error("   1. 网络连接是否正常")
            logger.error("   2. 防火墙是否阻止NTP请求(UDP 123端口)")
            logger.error("   3. DNS解析是否正常")
        
        logger.info("=" * 70)
        return success
        
    except Exception as e:
        logger.exception(f"测试过程中发生异常: {e}")
        return False

if __name__ == "__main__":
    success = test_network_time_sync()
    sys.exit(0 if success else 1)
