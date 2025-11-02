#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试HTTP时间服务"""

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

def test_http_time():
    """测试HTTP时间服务"""
    logger.info("=" * 70)
    logger.info("开始测试HTTP时间服务")
    logger.info("=" * 70)
    
    try:
        from backend.infrastructure.data_module_vnpy.core_engine import NetworkTimeSync
        
        # 创建实例
        sync = NetworkTimeSync.get_instance()
        logger.info("✓ NetworkTimeSync实例创建成功")
        
        # 直接调用HTTP方法
        logger.info("测试_sync_time_http方法...")
        success, offset = sync._sync_time_http(timeout=10.0)
        
        if success:
            logger.info(f"✅ HTTP时间同步成功!")
            logger.info(f"   时间偏移: {offset:.3f}秒")
        else:
            logger.error("❌ HTTP时间同步失败")
        
        logger.info("=" * 70)
        return success
        
    except Exception as e:
        logger.exception(f"测试过程中发生异常: {e}")
        return False

if __name__ == "__main__":
    success = test_http_time()
    sys.exit(0 if success else 1)
