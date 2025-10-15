#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from mootdx.quotes import Quotes

def test_beijing_stocks():
    """测试获取北交所股票数据"""
    quotes = Quotes.factory()

    print("测试获取北交所股票数据（market=2）...")

    try:
        df = quotes.stocks(2)  # 北交所

        if df is not None and not df.empty:
            print(f"✅ 北交所股票数量: {len(df)}")
            print("前5个股票:")
            for i, stock in enumerate(df.head().to_dict('records')[:5]):
                print(f"  {i+1}. {stock}")
        else:
            print("❌ 北交所数据为空")

    except Exception as e:
        print(f"❌ 获取北交所数据失败: {e}")
        print(f"错误类型: {type(e)}")

    # 测试其他市场代码
    for market in [0, 1, 2]:
        try:
            df = quotes.stocks(market)
            print(f"市场 {market}: {len(df) if df is not None else 0} 个股票")
        except Exception as e:
            print(f"市场 {market}: 错误 - {e}")

if __name__ == "__main__":
    test_beijing_stocks()
