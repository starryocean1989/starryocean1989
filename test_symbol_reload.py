# -*- coding: utf-8 -*-
"""
测试品种列表重新加载功能（增强版）

测试目标：
1. 验证10页限制已删除
2. 观察两个市场进程的执行情况
3. 检查上海市场数据是否正常获取
4. 验证增强的日志输出
"""

import sys
import logging
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 配置详细日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/test_symbol_reload.log", encoding="utf-8"),
    ],
)

logger = logging.getLogger(__name__)


def main():
    """主测试函数"""
    logger.info("=" * 80)
    logger.info("品种列表重新加载测试 - 增强版")
    logger.info("=" * 80)

    try:
        # 导入必要模块
        logger.info("导入模块...")
        from backend.infrastructure.data_module_vnpy.symbol_management import SymbolLoader
        from backend.infrastructure.data_module_vnpy.server_pool_manager import server_pool_manager

        # 启动服务器池
        logger.info("启动服务器池...")
        server_pool_manager.start()
        logger.info("服务器池已启动")

        # 创建SymbolLoader实例（不传event_engine，独立运行）
        logger.info("创建SymbolLoader实例...")
        loader = SymbolLoader()

        # 执行重新加载
        logger.info("=" * 80)
        logger.info("开始重新加载品种列表...")
        logger.info("=" * 80)

        result = loader.load_from_api()

        logger.info("=" * 80)
        logger.info("加载完成！")
        logger.info("=" * 80)

        # 分析结果
        classified = result.get("classified", {})
        empty_categories = result.get("empty_categories", [])

        logger.info("\n📊 品种列表统计：")
        logger.info("-" * 60)
        total_count = 0
        for category, stocks in classified.items():
            count = len(stocks)
            total_count += count
            status = "✅" if count > 0 else "❌"
            logger.info(f"{status} {category:12s}: {count:5d} 个品种")

            # 显示前3个样本
            if count > 0:
                samples = stocks[:3]
                for stock in samples:
                    logger.info(
                        f"    - {stock.get('code')}: {stock.get('name')} (market={stock.get('market')})"
                    )

        logger.info("-" * 60)
        logger.info(f"总计: {total_count} 个品种")

        # 检查空类别
        if empty_categories:
            logger.warning("\n⚠️  警告：以下类别为空：")
            for cat in empty_categories:
                logger.warning(f"  - {cat}")
        else:
            logger.info("\n✅ 所有类别都有数据！")

        # 验证上证A股
        logger.info("\n🔍 上证A股详细检查：")
        sh_stocks = classified.get("上证A股", [])
        if sh_stocks:
            logger.info(f"  ✅ 获取到 {len(sh_stocks)} 只上证A股")
            # 检查代码前缀分布
            code_prefixes = {}
            for stock in sh_stocks:
                prefix = stock.get("code", "")[:2]
                code_prefixes[prefix] = code_prefixes.get(prefix, 0) + 1
            logger.info(f"  代码前缀分布: {code_prefixes}")
        else:
            logger.error("  ❌ 上证A股为空！请检查日志中的详细信息")

        # 验证深证A股
        logger.info("\n🔍 深证A股详细检查：")
        sz_stocks = classified.get("深证A股", [])
        if sz_stocks:
            logger.info(f"  ✅ 获取到 {len(sz_stocks)} 只深证A股")
            # 检查代码前缀分布
            code_prefixes = {}
            for stock in sz_stocks:
                prefix = stock.get("code", "")[:2]
                code_prefixes[prefix] = code_prefixes.get(prefix, 0) + 1
            logger.info(f"  代码前缀分布: {code_prefixes}")
        else:
            logger.error("  ❌ 深证A股为空！请检查日志中的详细信息")

        logger.info("\n" + "=" * 80)
        logger.info("测试完成！")
        logger.info("=" * 80)

        return result

    except Exception as e:
        logger.error("测试过程中发生异常:", exc_info=True)
        return None


if __name__ == "__main__":
    main()
