#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试品种加载修复

验证 symbol_management.py 中的服务器连接问题是否已修复
"""

import sys
import os
import logging

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.infrastructure.data_module_vnpy.symbol_management import SymbolLoader

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_symbol_reload():
    """测试品种重新加载功能"""
    logger.info("=" * 60)
    logger.info("测试品种重新加载功能")
    logger.info("=" * 60)
    
    try:
        # 创建SymbolLoader
        loader = SymbolLoader()
        logger.info("✓ SymbolLoader 创建成功")
        
        # 尝试重新加载品种
        logger.info("\n开始重新加载品种...")
        result = loader.reload_and_classify()
        
        # 检查结果
        logger.info("\n" + "=" * 60)
        logger.info("加载结果:")
        logger.info("=" * 60)
        logger.info(f"成功: {result.get('success')}")
        logger.info(f"总数: {result.get('total_count', 0)}")
        logger.info(f"消息: {result.get('message', '')}")
        
        if result.get('success'):
            # 显示分类统计
            classified = loader.load_from_cache()
            if classified:
                logger.info("\n分类统计:")
                for market_type, stocks in classified.items():
                    logger.info(f"  {market_type}: {len(stocks)} 个品种")
                
                logger.info("\n✓✓✓ 品种加载修复成功！")
                return True
            else:
                logger.error("✗ 缓存为空")
                return False
        else:
            logger.error(f"✗ 加载失败: {result.get('message')}")
            return False
        
    except Exception as e:
        logger.error(f"测试异常: {e}", exc_info=True)
        return False

if __name__ == "__main__":
    success = test_symbol_reload()
    sys.exit(0 if success else 1)

