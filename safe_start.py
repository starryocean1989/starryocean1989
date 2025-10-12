# -*- coding: utf-8 -*-
"""
带全局异常捕获的安全启动脚本

用于诊断UI崩溃问题
"""

import sys
import logging
import traceback
from pathlib import Path

# 设置工作目录
sys.path.insert(0, str(Path(__file__).parent))

# 配置基础日志
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("logs/safe_start.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)

logger = logging.getLogger("SafeStart")


# 设置全局异常处理器
def global_exception_handler(exc_type, exc_value, exc_traceback):
    """捕获所有未处理的异常"""

    # 打印到控制台
    print("\n" + "=" * 80, flush=True)
    print("❌ 捕获到未处理异常（程序本应崩溃）：", flush=True)
    print("=" * 80, flush=True)
    traceback.print_exception(exc_type, exc_value, exc_traceback)
    print("=" * 80, flush=True)

    # 记录到日志
    logger.critical("未捕获异常", exc_info=(exc_type, exc_value, exc_traceback))

    # 不调用sys.exit()，尝试让程序继续
    print("\n⚠️ 尝试让程序继续运行...", flush=True)


# 安装全局异常处理器
sys.excepthook = global_exception_handler

print("=" * 80)
print("安全启动模式")
print("=" * 80)
print("全局异常捕获已启用")
print("所有崩溃都会被记录并尝试继续运行")
print("=" * 80)
print()

# 导入并运行原始启动脚本
if __name__ == "__main__":
    try:
        logger.info("开始启动程序...")

        # 导入start模块
        import start

        logger.info("start模块导入成功")

        # 如果start.py有main函数，调用它
        if hasattr(start, "main"):
            logger.info("调用start.main()...")
            start.main()
        else:
            # 否则直接执行start.py的代码
            logger.info("start.py没有main函数，模块已自动执行")

    except KeyboardInterrupt:
        print("\n\n程序被用户中断")
        logger.info("程序被用户中断")

    except Exception as e:
        print(f"\n❌ 启动失败: {e}")
        logger.error("启动失败", exc_info=True)
        traceback.print_exc()
        input("\n按回车键退出...")

    finally:
        logger.info("safe_start.py执行完成")
