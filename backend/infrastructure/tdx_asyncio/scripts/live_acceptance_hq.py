#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
定向服务器 HQ 联网端到端验收

- 直接连接到经过测速可用的服务器: 180.153.18.170:7709
- 成功连接后验证：
  1) get_security_bars_by_interval("600000", "1d") -> tdx_bars_to_dataframe
  2) get_security_quotes([(1, "600000"), (0, "000001")]) -> tdx_quotes_to_dataframe
  3) get_security_list_batch(market=1, max_pages=1) -> tdx_security_list_to_dataframe
"""

import sys
import asyncio
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(project_root))

from backend.infrastructure.tdx_asyncio.api.hq import (
    AsyncTdxHq_API,
    get_security_bars_by_interval,
    get_security_list_batch,
)
from backend.infrastructure.tdx_asyncio.utils.data_converter import (
    tdx_bars_to_dataframe,
    tdx_quotes_to_dataframe,
    tdx_security_list_to_dataframe,
)


TARGET_SERVER = ("180.153.18.170", 7709)


async def connect_target(timeout: float = 4.0) -> AsyncTdxHq_API | None:
    ip, port = TARGET_SERVER
    try:
        api = await AsyncTdxHq_API.factory((ip, port), timeout=timeout, heartbeat=False, auto_retry=False)
        if api:
            print(f"✅ 已连接: {ip}:{port}")
            return api
    except Exception as e:
        print(f"❌ 连接失败: {ip}:{port} -> {type(e).__name__}: {e}")
    return None


async def test_bars(api: AsyncTdxHq_API):
    print("\n[1] 测试 K线接口 -> DataFrame")
    try:
        bars = await get_security_bars_by_interval(api, symbol="600000", interval="1d", market=1, start=0, count=120)
        if not bars:
            print("  ⚠️ bars 返回为空")
            return False
        df = tdx_bars_to_dataframe(bars, symbol="600000", interval="1d")
        print(f"  条目: {len(bars)}, DataFrame行数: {len(df)}，列: {list(df.columns)[:6]}")
        return True
    except Exception as e:
        print(f"  ❌ K线测试异常: {type(e).__name__}: {e}")
        return False


async def test_quotes(api: AsyncTdxHq_API):
    print("\n[2] 测试 行情接口 -> DataFrame")
    try:
        quotes = await api.get_security_quotes([(1, "600000"), (0, "000001")])
        if not quotes:
            print("  ⚠️ quotes 返回为空")
            return False
        df = tdx_quotes_to_dataframe(quotes)
        sample_cols = [c for c in ["price", "open", "high", "low"] if c in df.columns]
        print(f"  条目: {len(quotes)}, DataFrame行数: {len(df)}，示例列: {sample_cols}")
        return True
    except Exception as e:
        print(f"  ❌ 行情测试异常: {type(e).__name__}: {e}")
        return False


async def test_list(api: AsyncTdxHq_API):
    print("\n[3] 测试 股票列表 -> DataFrame（最多1页）")
    try:
        stocks = await get_security_list_batch(api, market=1, start=0, page_size=1000, max_pages=1)
        if not stocks:
            print("  ⚠️ list 返回为空")
            return False
        df = tdx_security_list_to_dataframe(stocks)
        sample_cols = [c for c in ["name", "category"] if c in df.columns]
        print(f"  条目: {len(stocks)}, DataFrame行数: {len(df)}，示例列: {sample_cols}")
        return True
    except Exception as e:
        print(f"  ❌ 列表测试异常: {type(e).__name__}: {e}")
        return False


async def main():
    api = await connect_target(timeout=4.0)
    if not api:
        print("\n🛡️ 未能连接到目标服务器，验收失败。")
        return 2

    ok = True
    try:
        ok &= await test_bars(api)
        ok &= await test_quotes(api)
        ok &= await test_list(api)
    finally:
        try:
            await api.disconnect()
        except Exception:
            pass

    if ok:
        print("\n✅ HQ 联网端到端验收通过")
        return 0
    else:
        print("\n❌ HQ 联网端到端验收未全部通过")
        return 1


if __name__ == "__main__":
    code = asyncio.run(main())
    sys.exit(code)