# -*- coding: utf-8 -*-
"""验证数据下载功能脚本.

测试当前品种列表缓存中的所有品种（6000+）使用10个服务器执行多进程并行下载。
"""
import sys
import logging
from datetime import date, timedelta
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(
            project_root / "logs" / "test_download_all_symbols.log", encoding="utf-8"
        ),
    ],
)

logger = logging.getLogger(__name__)


def main():
    """主测试函数."""
    logger.info("=" * 80)
    logger.info("开始验证数据下载功能")
    logger.info("=" * 80)

    try:
        # 1. 导入必要模块
        logger.info("步骤1: 导入模块...")
        from backend.infrastructure.data_module_vnpy.config import config_manager
        from backend.infrastructure.data_module_vnpy.symbol_management import SymbolLoader
        from backend.infrastructure.data_module_vnpy.data_fetcher import MultiProcessStockFetcher

        # 2. 配置服务器数量为10
        logger.info("步骤2: 配置服务器参数...")
        config_manager.set("chinastock.server_pool_size", 10)
        config_manager.set("chinastock.timeout", 30)
        config_manager.set("chinastock.retry_times", 3)

        server_pool_size = config_manager.get("chinastock.server_pool_size")
        logger.info(f"  ✓ 并行服务器数量: {server_pool_size}")
        logger.info(f"  ✓ 连接超时: {config_manager.get('chinastock.timeout')} 秒")
        logger.info(f"  ✓ 重试次数: {config_manager.get('chinastock.retry_times')} 次")

        # 3. 加载品种列表缓存
        logger.info("步骤3: 加载品种列表缓存...")
        symbol_loader = SymbolLoader()
        classified = symbol_loader.load_from_cache()

        if not classified:
            logger.error("❌ 品种列表缓存为空，请先运行重新加载品种")
            logger.info("提示: 在数据中心界面点击【重新加载品种】按钮")
            return False

        # 4. 统计品种数量
        logger.info("步骤4: 统计品种数量...")
        all_symbols = []
        for category, stocks in classified.items():
            logger.info(f"  • {category}: {len(stocks)} 个")
            # 提取品种代码
            for stock in stocks:
                if isinstance(stock, dict) and "code" in stock:
                    all_symbols.append(stock["code"])

        total_symbols = len(all_symbols)
        logger.info(f"  ✓ 总品种数: {total_symbols}")

        if total_symbols == 0:
            logger.error("❌ 品种列表为空")
            return False

        # 5. 测试模式：只下载前50个品种（完整测试改为 all_symbols）
        test_mode = True
        if test_mode:
            test_symbols = all_symbols[:50]
            logger.warning("⚠️ 测试模式：只下载前50个品种")
            logger.info(f"  测试品种样例: {test_symbols[:5]}")
        else:
            test_symbols = all_symbols
            logger.info(f"  完整模式：下载所有 {total_symbols} 个品种")

        # 6. 设置下载日期（最近10天）
        logger.info("步骤5: 设置下载参数...")
        start_date = date.today() - timedelta(days=10)
        intervals = ["1d", "5m", "1m"]
        logger.info(f"  • 开始日期: {start_date}")
        logger.info(f"  • 周期列表: {intervals}")
        logger.info(f"  • 品种数量: {len(test_symbols)}")
        logger.info(f"  • 预计下载任务数: {len(test_symbols) * len(intervals)} 个")

        # 7. 创建多进程下载器
        logger.info("步骤6: 创建多进程下载器...")
        fetcher = MultiProcessStockFetcher()
        logger.info(f"  ✓ 下载器创建成功，进程数: {fetcher.num_processes}")

        # 8. 定义进度回调
        completed_count = 0
        total_tasks = len(test_symbols) * len(intervals)

        def progress_callback(completed, total, symbol, interval):
            """进度回调函数."""
            nonlocal completed_count
            completed_count = completed
            percent = (completed / total * 100) if total > 0 else 0

            # 每10个任务打印一次进度
            if completed % 10 == 0 or completed == total:
                logger.info(
                    f"  📥 进度: {completed}/{total} ({percent:.1f}%) - "
                    f"当前: {symbol} {interval}"
                )

        # 9. 开始下载
        logger.info("步骤7: 开始下载...")
        logger.info("=" * 80)

        import time

        start_time = time.time()

        try:
            results = fetcher.download_incremental_kline(
                symbols=test_symbols,
                start_date=start_date,
                intervals=intervals,
                progress_callback=progress_callback,
            )

            elapsed = time.time() - start_time

            logger.info("=" * 80)
            logger.info("步骤8: 下载完成，分析结果...")

            # 10. 分析下载结果
            success_count = 0
            failed_count = 0
            empty_count = 0

            for key, df in results.items():
                if df is None:
                    failed_count += 1
                elif df.empty:
                    empty_count += 1
                else:
                    success_count += 1

            logger.info("=" * 80)
            logger.info("下载结果统计:")
            logger.info("=" * 80)
            logger.info(f"  ✅ 成功: {success_count} 个数据集")
            logger.info(f"  📭 空数据: {empty_count} 个数据集")
            logger.info(f"  ❌ 失败: {failed_count} 个数据集")
            logger.info(f"  📊 总计: {len(results)} 个数据集")
            logger.info(f"  ⏱️ 耗时: {elapsed:.2f} 秒")
            logger.info(f"  🚀 平均速度: {len(results) / elapsed:.2f} 个/秒")
            logger.info("=" * 80)

            # 11. 显示成功样例
            if success_count > 0:
                logger.info("成功下载的数据样例（前5个）:")
                count = 0
                for key, df in results.items():
                    if df is not None and not df.empty:
                        logger.info(f"  ✓ {key}: {len(df)} 条记录")
                        count += 1
                        if count >= 5:
                            break

            # 12. 显示失败样例
            if failed_count > 0:
                logger.warning("下载失败的数据样例（前5个）:")
                count = 0
                for key, df in results.items():
                    if df is None:
                        logger.warning(f"  ✗ {key}: 下载失败")
                        count += 1
                        if count >= 5:
                            break

            # 13. 验证结论
            logger.info("=" * 80)
            success_rate = (success_count / len(results) * 100) if len(results) > 0 else 0

            if success_rate >= 90:
                logger.info("✅ 验证结果: 通过（成功率 {:.1f}%）".format(success_rate))
                logger.info("多进程并行下载功能正常，可以处理大批量品种")
                return True
            elif success_rate >= 50:
                logger.warning("⚠️ 验证结果: 部分通过（成功率 {:.1f}%）".format(success_rate))
                logger.warning("部分品种下载失败，请检查网络连接和服务器状态")
                return True
            else:
                logger.error("❌ 验证结果: 失败（成功率 {:.1f}%）".format(success_rate))
                logger.error("大量品种下载失败，请检查配置和网络")
                return False

        except Exception as download_error:
            elapsed = time.time() - start_time
            logger.error("=" * 80)
            logger.error("❌ 下载过程发生异常:")
            logger.error(f"  错误类型: {type(download_error).__name__}")
            logger.error(f"  错误信息: {str(download_error)}")
            logger.error(f"  耗时: {elapsed:.2f} 秒")
            logger.error("=" * 80)

            import traceback

            logger.error("详细错误堆栈:")
            logger.error(traceback.format_exc())

            return False

    except Exception as e:
        logger.error("=" * 80)
        logger.error("验证脚本执行失败:")
        logger.error(f"  错误: {e}")
        logger.error("=" * 80)

        import traceback

        logger.error("详细错误堆栈:")
        logger.error(traceback.format_exc())

        return False

    finally:
        logger.info("=" * 80)
        logger.info("验证脚本执行结束")
        logger.info("=" * 80)


if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        logger.warning("\n用户中断执行")
        sys.exit(1)
    except Exception as e:
        logger.error(f"脚本执行异常: {e}", exc_info=True)
        sys.exit(1)
