# -*- coding: utf-8 -*-
"""
测试 mootdx 返回的字段
"""
from mootdx.quotes import Quotes

print("=" * 100)
print("测试 mootdx 的 get_security_quotes 返回字段")
print("=" * 100)
print()

# 创建客户端
client = Quotes.factory(market="std")

# 尝试连接并获取行情
try:
    # 连接到最佳服务器
    if hasattr(client, "client") and client.client:
        print("正在连接行情服务器...")

        # 获取两只股票的行情
        result = client.quotes(["000001", "600000"])

        if result is not None and not result.empty:
            print("[√] 查询成功！")
            print()
            print("=" * 100)
            print("返回的字段列表：")
            print("=" * 100)

            columns = list(result.columns)
            for i, col in enumerate(columns, 1):
                print(f"{i:2d}. {col}")

            print()
            print(f"字段总数: {len(columns)} 个")
            print()
            print("=" * 100)
            print("示例数据（前2行）：")
            print("=" * 100)
            print(result.head(2))
            print()
            print("=" * 100)
            print("数据类型：")
            print("=" * 100)
            print(result.dtypes)

        else:
            print("[×] 未获取到数据")
    else:
        print("[×] 客户端未初始化")

except Exception as e:
    print(f"[×] 发生错误: {e}")
    import traceback

    traceback.print_exc()

finally:
    # 关闭连接
    try:
        client.close()
    except:
        pass

print()
print("测试完成")



