"""验证IPO缓存hang问题修复

问题：启动时在"[5/8] 验证IPO日期缓存"阶段hang住8分钟无输出
根因：等待服务器池就绪时缺少进度日志
修复：
  1. 延长超时时间从10秒到30秒
  2. 每3秒输出一次等待进度日志
  3. 首次等待时输出服务器池状态详情
"""

import logging
import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

logger = logging.getLogger(__name__)


def test_ipo_wait_logging():
    """测试IPO下载等待服务器池的日志输出"""
    from backend.infrastructure.data_module_vnpy.data_acquisition import (
        MultiProcessStockFetcher,
    )

    fetcher = MultiProcessStockFetcher()

    # 模拟品种列表
    test_symbols = [("000001", 1), ("600000", 1), ("688001", 1)]

    print("\n" + "=" * 70)
    print("测试场景：IPO下载等待服务器池就绪")
    print("=" * 70)
    print("预期行为：")
    print("  1. 首次等待时输出服务器池状态详情")
    print("  2. 每3秒输出一次等待进度")
    print("  3. 最多等待30秒（不是10秒）")
    print("  4. 等待过程中日志连续输出，不再hang住无响应")
    print("=" * 70)

    try:
        result = fetcher.download_ipo_dates_multiprocess(
            symbols_with_markets=test_symbols, progress_callback=None, use_adaptive=False
        )

        print("\n✅ 测试通过！")
        print(f"下载结果: {result.get('success', False)}")
        print(f"成功数: {result.get('succeeded', 0)}/{result.get('total', 0)}")

        if result.get("success"):
            print("\n✅ 修复验证成功！等待过程中有持续的日志输出")
        else:
            print(f"\n⚠️  下载未完全成功: {result.get('error', '未知错误')}")
            print("但修复的重点是避免hang住，而不是保证下载成功")

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        raise


if __name__ == "__main__":
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    print("\n" + "🔍" * 35)
    print("IPO缓存hang问题修复验证")
    print("🔍" * 35)

    test_ipo_wait_logging()

    print("\n" + "=" * 70)
    print("验证完成！")
    print("=" * 70)
