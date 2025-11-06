#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
tdx_asyncio v2.2 新功能测试脚本

测试以下新增功能：
1. 财务数据API（batch_get_ipo_dates）
2. 服务器测速工具（ServerTester）
3. 文件路径管理工具（TdxPathHelper）
4. 数据格式转换工具（tdx_bars_to_dataframe）
"""

import asyncio
import sys
from pathlib import Path
from datetime import date

# 添加项目根目录到路径
project_root = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(project_root))

from backend.infrastructure.tdx_asyncio import (
    # 连接池
    AsyncConnectionPool,
    ConnectionPoolConfig,
    # 财务数据API
    batch_get_ipo_dates,
    batch_get_finance_info,
    # 服务器测速
    ServerTester,
    test_server,
    batch_test_servers,
    get_fastest_servers,
    # 文件路径管理
    TdxPathHelper,
    find_tdx_root,
    get_market_from_code,
    # 数据格式转换
    tdx_bars_to_dataframe,
    tdx_quotes_to_dataframe,
    normalize_tdx_data,
    # 行情API
    AsyncTdxHq_API,
)


# ==============================================================================
# 测试1: 财务数据API
# ==============================================================================

async def test_finance_api():
    """测试财务数据API"""
    print("\n" + "="*80)
    print("测试1: 财务数据API")
    print("="*80)
    
    # 准备服务器列表
    servers = [
        ("119.147.212.81", 7709),
        ("202.108.253.131", 7709),
    ]
    
    # 创建连接池
    config = ConnectionPoolConfig(
        max_primary_connections=10,
        max_standby_connections=5,
        timeout=5.0,
        enable_monitoring=True,
    )
    pool = AsyncConnectionPool(servers=servers, config=config)
    
    try:
        async with pool:
            # 测试品种
            symbols = [
                ("600000", 1),  # 浦发银行
                ("000001", 0),  # 平安银行
                ("430047", 2),  # 诺思兰德（北证）
            ]
            
            print(f"\n📊 批量查询IPO日期（{len(symbols)}个品种）...")
            ipo_dates = await batch_get_ipo_dates(
                symbols=symbols,
                pool=pool,
                max_concurrent=10
            )
            
            print("\n✅ IPO日期查询结果:")
            for symbol, ipo_date in ipo_dates.items():
                if ipo_date:
                    print(f"  {symbol}: {ipo_date}")
                else:
                    print(f"  {symbol}: 未查询到")
            
            print(f"\n📊 批量查询财务信息（{len(symbols)}个品种）...")
            finance_data = await batch_get_finance_info(
                symbols=symbols,
                pool=pool,
                max_concurrent=10
            )
            
            print("\n✅ 财务信息查询结果:")
            for symbol, data in finance_data.items():
                if data:
                    print(f"  {symbol}: 流通股本={data.get('liutongguben', 'N/A')}, "
                          f"总股本={data.get('zongguben', 'N/A')}")
                else:
                    print(f"  {symbol}: 未查询到")
    
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()


# ==============================================================================
# 测试2: 服务器测速工具
# ==============================================================================

async def test_server_tester():
    """测试服务器测速工具"""
    print("\n" + "="*80)
    print("测试2: 服务器测速工具")
    print("="*80)
    
    # 准备服务器列表
    servers = [
        ("119.147.212.81", 7709),
        ("202.108.253.131", 7709),
        ("121.14.110.210", 7709),
        ("114.80.63.12", 7709),
        ("180.153.18.170", 7709),
    ]
    
    try:
        # 方式1: 使用类
        print("\n📊 方式1: 使用ServerTester类...")
        tester = ServerTester()
        
        # 测试单个服务器
        print(f"\n测试单个服务器: {servers[0]}")
        response_time = await tester.test_server(servers[0][0], servers[0][1])
        if response_time:
            print(f"✅ 响应时间: {response_time:.3f}秒")
        else:
            print("❌ 连接失败")
        
        # 批量测试
        print(f"\n📊 批量测试{len(servers)}个服务器...")
        results = await tester.batch_test_servers(servers, max_concurrent=10)
        
        print("\n✅ 测速结果:")
        for (ip, port), response_time in sorted(results.items(), key=lambda x: x[1] or 999):
            if response_time:
                print(f"  {ip}:{port} - {response_time:.3f}秒")
            else:
                print(f"  {ip}:{port} - 失败")
        
        # 获取最快的3个服务器
        print("\n📊 获取最快的3个服务器...")
        fastest = await tester.get_fastest_servers(servers, top_n=3)
        
        print("\n✅ 最快的服务器:")
        for i, (ip, port) in enumerate(fastest, 1):
            response_time = results.get((ip, port))
            if response_time:
                print(f"  {i}. {ip}:{port} - {response_time:.3f}秒")
        
        # 方式2: 使用函数
        print("\n📊 方式2: 使用函数...")
        response_time = await test_server(servers[0][0], servers[0][1])
        if response_time:
            print(f"✅ 响应时间: {response_time:.3f}秒")
    
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()


# ==============================================================================
# 测试3: 文件路径管理工具
# ==============================================================================

def test_path_helper():
    """测试文件路径管理工具"""
    print("\n" + "="*80)
    print("测试3: 文件路径管理工具")
    print("="*80)
    
    try:
        # 自动查找通达信根目录
        print("\n📊 自动查找通达信根目录...")
        tdx_root = find_tdx_root()
        if tdx_root:
            print(f"✅ 找到通达信根目录: {tdx_root}")
        else:
            print("❌ 未找到通达信根目录")
            return
        
        # 创建路径辅助类
        helper = TdxPathHelper(tdx_root)
        
        # 测试日K线文件路径
        print("\n📊 测试日K线文件路径...")
        test_cases = [
            (1, "600000"),  # 上海
            (0, "000001"),  # 深圳
            (2, "430047"),  # 北京
        ]
        
        for market, code in test_cases:
            day_file = helper.get_day_file_path(market, code)
            exists = "✅" if day_file.exists() else "❌"
            print(f"  {exists} {day_file}")
        
        # 测试分钟线文件路径
        print("\n📊 测试分钟线文件路径...")
        minute_file = helper.get_minute_file_path(1, "600000")
        exists = "✅" if minute_file.exists() else "❌"
        print(f"  {exists} {minute_file}")
        
        # 测试5分钟线文件路径
        print("\n📊 测试5分钟线文件路径...")
        lc5_file = helper.get_lc5_file_path(1, "600000")
        exists = "✅" if lc5_file.exists() else "❌"
        print(f"  {exists} {lc5_file}")
        
        # 测试配置文件查找
        print("\n📊 测试配置文件查找...")
        config_files = ["T0002.cfg", "T0002.DAT", "block_zs.dat"]
        for filename in config_files:
            config_file = helper.get_config_file_path(filename)
            if config_file:
                print(f"  ✅ {filename}: {config_file}")
            else:
                print(f"  ❌ {filename}: 未找到")
        
        # 测试市场推断
        print("\n📊 测试市场推断...")
        test_codes = ["600000", "000001", "430047", "688001"]
        for code in test_codes:
            market = get_market_from_code(code)
            market_name = {0: "深圳", 1: "上海", 2: "北京"}.get(market, "未知")
            print(f"  {code} -> 市场{market} ({market_name})")
    
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()


# ==============================================================================
# 测试4: 数据格式转换工具
# ==============================================================================

async def test_data_converter():
    """测试数据格式转换工具"""
    print("\n" + "="*80)
    print("测试4: 数据格式转换工具")
    print("="*80)
    
    # 本测试在当前环境使用模拟数据，不依赖外部网络
    
    try:
        # 使用本地模拟数据替代网络依赖
        print("\n📊 测试K线数据转DataFrame（本地模拟数据）...")
        bars = [
            {"open": 10.0, "high": 10.5, "low": 9.8, "close": 10.3, "vol": 123456, "amount": 12345678,
             "year": 2024, "month": 11, "day": 1},
            {"open": 10.3, "high": 10.6, "low": 10.1, "close": 10.4, "vol": 234567, "amount": 22345678,
             "year": 2024, "month": 11, "day": 4},
        ]
        df_bars = tdx_bars_to_dataframe(bars, symbol="600000", interval="1d")
        print(f"✅ 转换成功，共{len(df_bars)}行")
        print("\n前5行数据:")
        print(df_bars.head())

        print("\n📊 测试行情数据转DataFrame（本地模拟数据）...")
        quotes = [
            {"code": "600000", "price": 10.35, "open": 10.0, "high": 10.6, "low": 9.8, "vol": 345678, "amount": 32345678},
            {"code": "000001", "price": 12.50, "open": 12.3, "high": 12.7, "low": 12.1, "vol": 456789, "amount": 42345678},
        ]
        df_quotes = tdx_quotes_to_dataframe(quotes)
        print(f"✅ 转换成功，共{len(df_quotes)}行")
        print("\n行情数据:")
        print(df_quotes)

        print("\n📊 测试数据标准化（K线）...")
        normalized_df = normalize_tdx_data(bars, data_type="bars", symbol="600000", interval="1d")
        print(f"✅ 标准化成功，索引类型: {type(normalized_df.index)}")

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        pass


# ==============================================================================
# 主函数
# ==============================================================================

async def main():
    """主函数"""
    print("\n" + "="*80)
    print("tdx_asyncio v2.2 新功能测试")
    print("="*80)
    
    # 测试1: 财务数据API
    await test_finance_api()
    
    # 测试2: 服务器测速工具
    await test_server_tester()
    
    # 测试3: 文件路径管理工具（同步）
    test_path_helper()
    
    # 测试4: 数据格式转换工具
    await test_data_converter()
    
    print("\n" + "="*80)
    print("✅ 所有测试完成")
    print("="*80)


if __name__ == "__main__":
    asyncio.run(main())
