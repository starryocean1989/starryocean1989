import asyncio
import logging
import os
import sys
from collections import Counter
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.infrastructure.data_module_vnpy.data_readers.data_readers import (  # noqa: E402
    TdxDynamicExecutor,
)


async def run_test(
    tdx_root: Path,
    symbol_limit: int,
    initial_processes: int,
    initial_coroutines: int,
    market: str = "sh",
    data_type: str = "1min",
):
    executor = TdxDynamicExecutor(tdx_root)
    executor.adjustment_interval = 0.3

    data_dir = tdx_root / "vipdoc" / market / "minline"
    if not data_dir.exists():
        raise FileNotFoundError(f"TDX 数据目录不存在: {data_dir}")

    # 统一按文件名排序，取前 symbol_limit 个品种
    symbols = [p.stem[2:] for p in sorted(data_dir.glob("sh*.lc1"))]
    if not symbols:
        raise RuntimeError("未找到任何符合条件的lc1文件")

    symbols = symbols[:symbol_limit]
    logging.info("使用 %d 个品种进行批量任务", len(symbols))

    await executor.execute_batch(
        symbols=symbols,
        data_type=data_type,
        market=market,
        initial_processes=initial_processes,
        initial_coroutines=initial_coroutines,
    )

    summary = executor.last_run_summary or {}
    logging.info(
        "⏱️ 总耗时%.2fs, 成功%d/%d, 平均%.2f个/秒, 最终并发=%d (每进程=%d)",
        summary.get("duration", 0.0),
        summary.get("success", 0),
        summary.get("total_symbols", len(symbols)),
        summary.get("avg_symbols_per_sec", 0.0),
        summary.get("final_total_coroutines", executor.total_coroutines),
        summary.get("final_coroutines_per_process", executor.current_coroutines_per_process),
    )

    history = list(executor.adjustment_history)
    action_count = Counter(entry["action"] for entry in history if entry.get("action"))
    final_total = executor.total_coroutines
    per_process = (
        final_total // executor.current_processes if executor.current_processes else final_total
    )

    logging.info("调整动作统计: %s", dict(action_count))
    logging.info(
        "最终并发: 总计=%d, 每进程=%d", final_total, per_process
    )

    return {
        "history": history,
        "actions": dict(action_count),
        "final_total": final_total,
        "per_process": per_process,
        "summary": summary,
    }


async def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    tdx_root_env = os.environ.get("TDX_DATA_ROOT")
    if not tdx_root_env:
        raise EnvironmentError("请设置环境变量 TDX_DATA_ROOT")

    tdx_root = Path(tdx_root_env)
    if not tdx_root.exists():
        raise FileNotFoundError(f"TDX 根目录不存在: {tdx_root}")

    initial_processes = int(os.environ.get("TDX_INITIAL_PROCESSES", "8"))
    initial_coroutines = int(os.environ.get("TDX_INITIAL_COROS", "50"))
    symbol_limit = int(os.environ.get("TDX_SYMBOL_LIMIT", "2000"))

    result = await run_test(
        tdx_root,
        symbol_limit=symbol_limit,
        initial_processes=initial_processes,
        initial_coroutines=initial_coroutines,
    )

    actions = result["actions"]
    if not actions.get("hold") and not actions.get("decrease"):
        logging.info("未出现 hold/decrease，使用每进程并发 %d 进行二次测试", result["per_process"])
        await run_test(
            tdx_root,
            symbol_limit=symbol_limit,
            initial_processes=initial_processes,
            initial_coroutines=max(result["per_process"], initial_coroutines),
        )


if __name__ == "__main__":
    asyncio.run(main())
