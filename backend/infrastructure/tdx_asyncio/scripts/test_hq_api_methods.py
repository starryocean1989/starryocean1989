#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
HQ API 方法链测试（离线安全）

- 尝试连接 HQ_HOSTS_ALL 列表中的服务器，优先成功者
- 成功连接后测试：
  1) get_security_bars_by_interval("600000", "1d") -> tdx_bars_to_dataframe
  2) get_security_quotes([(1, "600000"), (0, "000001")]) -> tdx_quotes_to_dataframe
  3) get_security_list_all(market=1)（限制最多2页）-> tdx_security_list_to_dataframe
- 若无法连接任何服务器，则安全跳过网络测试并提示
"""

import sys
import asyncio
from pathlib import Path
from typing import Optional, Tuple, List

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.infrastructure.tdx_asyncio.api.hq import (
    AsyncTdxHq_API,
    get_security_bars_by_interval,
    get_security_list_batch,
    get_security_list_all,
    get_security_bars_safe,
)
from backend.infrastructure.tdx_asyncio.utils.data_converter import (
    tdx_bars_to_dataframe,
    tdx_quotes_to_dataframe,
    tdx_security_list_to_dataframe,
)
from backend.infrastructure.tdx_asyncio.network.constants import HQ_HOSTS_ALL


async def connect_any(timeout: float = 3.0) -> Optional[AsyncTdxHq_API]:
    """遍历 HQ_HOSTS_ALL，返回首个成功连接的 API 实例"""
    # 服务器格式为 Dict[name, (ip, port)] 或 List[Tuple[name, ip, port]]
    candidates: List[Tuple[str, str, int]] = []
    if isinstance(HQ_HOSTS_ALL, dict):
        for name, (ip, port) in HQ_HOSTS_ALL.items():
            candidates.append((name, ip, port))
    elif isinstance(HQ_HOSTS_ALL, (list, tuple)):
        for item in HQ_HOSTS_ALL:
            if isinstance(item, (list, tuple)) and len(item) == 3:
                name, ip, port = item
                candidates.append((str(name), str(ip), int(port)))

    for name, ip, port in candidates:
        try:
            api = await AsyncTdxHq_API.factory((ip, port), timeout=timeout, heartbeat=False, auto_retry=False)
            if api:
                print(f"✅ 已连接: {name} ({ip}:{port})")
                return api
        except Exception as e:
            # 忽略异常继续遍历
            pass

    return None


async def test_bars(api: AsyncTdxHq_API):
    print("\n[1] 测试 K线接口 -> DataFrame")
    try:
        bars = await get_security_bars_by_interval(api, symbol="600000", interval="1d", market=1, start=0, count=200)
        if not bars:
            print("  ⚠️ bars 返回为空")
            return
        df = tdx_bars_to_dataframe(bars, symbol="600000", interval="1d")
        print(f"  条目: {len(bars)}, DataFrame行数: {len(df)}，列: {list(df.columns)[:6]}")
    except Exception as e:
        print(f"  ❌ K线测试异常: {type(e).__name__}: {e}")


async def test_quotes(api: AsyncTdxHq_API):
    print("\n[2] 测试 行情接口 -> DataFrame")
    try:
        quotes = await api.get_security_quotes([(1, "600000"), (0, "000001")])
        if not quotes:
            print("  ⚠️ quotes 返回为空")
            return
        df = tdx_quotes_to_dataframe(quotes)
        sample_cols = [c for c in ["price", "open", "high", "low"] if c in df.columns]
        print(f"  条目: {len(quotes)}, DataFrame行数: {len(df)}，示例列: {sample_cols}")
    except Exception as e:
        print(f"  ❌ 行情测试异常: {type(e).__name__}: {e}")


async def test_list(api: AsyncTdxHq_API):
    print("\n[3] 测试 股票列表 -> DataFrame（最多2页）")
    try:
        # 限制最多2页以免过长
        stocks = await get_security_list_batch(api, market=1, start=0, page_size=1000, max_pages=2)
        if not stocks:
            print("  ⚠️ list 返回为空")
            return
        df = tdx_security_list_to_dataframe(stocks)
        sample_cols = [c for c in ["name", "category"] if c in df.columns]
        print(f"  条目: {len(stocks)}, DataFrame行数: {len(df)}，示例列: {sample_cols}")
    except Exception as e:
        print(f"  ❌ 列表测试异常: {type(e).__name__}: {e}")


async def main():
    api = await connect_any(timeout=3.0)
    if not api:
        print("\n🛡️ 未连接到任何服务器，网络测试已安全跳过。")
        return

    try:
        await test_bars(api)
        await test_quotes(api)
        await test_list(api)
    finally:
        try:
            await api.disconnect()
        except Exception:
            pass


if __name__ == "__main__":
    # Windows 环境下直接运行
    try:
        asyncio.run(main())
    except RuntimeError:
        # 某些嵌套环境下回退策略
        loop = asyncio.get_event_loop()
        loop.run_until_complete(main())