# -*- coding: utf-8 -*-
"""
测试真实股票代码的批量查询限制
"""
from mootdx.quotes import Quotes

print("=" * 100)
print("使用真实股票代码测试批量查询限制")
print("=" * 100)
print()

# 创建客户端
client = Quotes.factory(market="std")

# 先获取真实的股票列表
print("正在获取股票列表...")
try:
    stocks_sz = client.client.get_security_list(market=0, start=0)  # 深圳
    stocks_sh = client.client.get_security_list(market=1, start=0)  # 上海

    # 提取股票代码
    sz_codes = [(0, stock["code"]) for stock in stocks_sz[:150]]  # 深圳150只
    sh_codes = [(1, stock["code"]) for stock in stocks_sh[:150]]  # 上海150只

    all_codes = sz_codes + sh_codes  # 共300只

    print(f"深圳股票: {len(sz_codes)} 只")
    print(f"上海股票: {len(sh_codes)} 只")
    print(f"总计: {len(all_codes)} 只")
    print()

    # 测试不同批量大小
    test_sizes = [10, 50, 100, 200, 290, 300]

    print("=" * 100)
    print("批量查询测试结果：")
    print("=" * 100)

    for size in test_sizes:
        batch = all_codes[:size]
        try:
            print(f"[{size:3d}只] 查询中...", end=" ", flush=True)

            # 调用底层API（支持批量）
            result = client.client.get_security_quotes(batch)

            if result:
                actual_count = len(result)
                print(f"✓ 成功返回 {actual_count} 条数据", end="")

                if actual_count < size:
                    print(f" (请求{size}只，返回{actual_count}只，限制为{actual_count})")
                else:
                    print()
            else:
                print("✗ 返回空数据")

        except Exception as e:
            error_msg = str(e)
            if len(error_msg) > 60:
                error_msg = error_msg[:60] + "..."
            print(f"✗ 失败: {error_msg}")

    print()
    print("=" * 100)
    print("结论：")
    print("=" * 100)
    print("通达信行情接口的批量查询限制可能取决于:")
    print("1. 服务器策略（最大290只）")
    print("2. 网络数据包大小限制")
    print("3. 客户端实现限制")

except Exception as e:
    print(f"测试失败: {e}")
    import traceback

    traceback.print_exc()

finally:
    try:
        client.close()
    except:
        pass

print()
print("测试完成")



