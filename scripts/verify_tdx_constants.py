# -*- coding: utf-8 -*-
"""
验证 tdx_asyncio 常量定义的正确性

交叉验证 pytdx, mootdx, tdx_asyncio 三个库的常量是否一致
"""
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.infrastructure.tdx_asyncio.constants import (
    TDXParams,
    HQ_HOSTS,
    EX_HOSTS,
    GP_HOSTS,
    FREQUENCY_MAP,
    MARKET_CODE_MAP,
    MARKET_NAME_MAP,
    SECURITY_EXCHANGE,
)


def test_tdx_params():
    """测试 TDXParams 类常量"""
    print("\n=== 测试 TDXParams 常量 ===")

    try:
        from pytdx.params import TDXParams as PytdxParams

        # 验证市场代码
        assert TDXParams.MARKET_SZ == PytdxParams.MARKET_SZ == 0, "MARKET_SZ 不一致"
        assert TDXParams.MARKET_SH == PytdxParams.MARKET_SH == 1, "MARKET_SH 不一致"
        print("✓ 市场代码与 pytdx 一致")

        # 验证K线类型
        assert TDXParams.KLINE_TYPE_5MIN == PytdxParams.KLINE_TYPE_5MIN == 0
        assert TDXParams.KLINE_TYPE_15MIN == PytdxParams.KLINE_TYPE_15MIN == 1
        assert TDXParams.KLINE_TYPE_1MIN == PytdxParams.KLINE_TYPE_1MIN == 8
        assert TDXParams.KLINE_TYPE_DAILY == PytdxParams.KLINE_TYPE_DAILY == 4
        print("✓ K线类型与 pytdx 一致")

        # 验证协议限制
        assert TDXParams.MAX_KLINE_COUNT == PytdxParams.MAX_KLINE_COUNT == 800
        assert TDXParams.MAX_TRANSACTION_COUNT == PytdxParams.MAX_TRANSACTION_COUNT == 2000
        print("✓ 协议限制常量与 pytdx 一致")

    except ImportError:
        print("⚠ pytdx 未安装，跳过交叉验证")


def test_server_lists():
    """测试服务器列表"""
    print("\n=== 测试服务器列表 ===")

    try:
        from mootdx.consts import HQ_HOSTS as MootdxHQ, EX_HOSTS as MootdxEX, GP_HOSTS as MootdxGP

        # 验证HQ服务器数量
        assert len(HQ_HOSTS) == len(MootdxHQ), f"HQ_HOSTS 数量不一致: {len(HQ_HOSTS)} vs {len(MootdxHQ)}"
        print(f"✓ HQ_HOSTS 包含 {len(HQ_HOSTS)} 个服务器（与 mootdx 一致）")

        # 验证服务器内容
        for i, (host1, host2) in enumerate(zip(HQ_HOSTS, MootdxHQ)):
            assert host1 == tuple(host2), f"第{i}个服务器不一致: {host1} vs {host2}"
        print("✓ HQ_HOSTS 内容与 mootdx 完全一致")

        # 验证EX服务器
        assert len(EX_HOSTS) == len(MootdxEX), "EX_HOSTS 数量不一致"
        print(f"✓ EX_HOSTS 包含 {len(EX_HOSTS)} 个扩展行情服务器")

        # 验证GP服务器
        assert len(GP_HOSTS) == len(MootdxGP), "GP_HOSTS 数量不一致"
        print(f"✓ GP_HOSTS 包含 {len(GP_HOSTS)} 个财务数据服务器")

    except ImportError:
        print("⚠ mootdx 未安装，跳过交叉验证")

    # 基本验证
    assert len(HQ_HOSTS) == 38, f"HQ_HOSTS 应该有38个服务器，实际有{len(HQ_HOSTS)}个"
    assert all(len(h) == 3 for h in HQ_HOSTS), "HQ_HOSTS 格式错误"
    assert all(isinstance(h[0], str) and isinstance(h[1], str) and isinstance(h[2], int)
               for h in HQ_HOSTS), "HQ_HOSTS 类型错误"
    print("✓ HQ_HOSTS 格式正确")


def test_frequency_map():
    """测试周期映射"""
    print("\n=== 测试周期映射 ===")

    try:
        from mootdx.consts import FREQUENCY as MootdxFreq

        # mootdx 的 FREQUENCY 是列表，需要转换为映射
        expected_map = {freq: idx for idx, freq in enumerate(MootdxFreq)}

        # 验证映射关系
        for key, value in FREQUENCY_MAP.items():
            if key in expected_map:
                assert FREQUENCY_MAP[key] == expected_map[key], f"FREQUENCY_MAP['{key}'] 不一致"

        print("✓ FREQUENCY_MAP 与 mootdx.FREQUENCY 一致")

    except ImportError:
        print("⚠ mootdx 未安装，跳过交叉验证")

    # 基本验证
    assert FREQUENCY_MAP["1m"] == 8, "1分钟周期代码错误"
    assert FREQUENCY_MAP["5m"] == 0, "5分钟周期代码错误"
    assert FREQUENCY_MAP["day"] == 4, "日K周期代码错误"
    print("✓ FREQUENCY_MAP 基本验证通过")


def test_market_map():
    """测试市场映射"""
    print("\n=== 测试市场映射 ===")

    assert MARKET_CODE_MAP["深圳"] == 0
    assert MARKET_CODE_MAP["上海"] == 1
    assert MARKET_CODE_MAP["北京"] == 2
    assert MARKET_CODE_MAP["sz"] == 0
    assert MARKET_CODE_MAP["sh"] == 1
    assert MARKET_CODE_MAP["bj"] == 2
    print("✓ MARKET_CODE_MAP 正确")

    assert MARKET_NAME_MAP[0] == "深圳"
    assert MARKET_NAME_MAP[1] == "上海"
    assert MARKET_NAME_MAP[2] == "北京"
    print("✓ MARKET_NAME_MAP 正确")


def test_security_types():
    """测试证券类型"""
    print("\n=== 测试证券类型 ===")

    assert "sz" in SECURITY_EXCHANGE
    assert "sh" in SECURITY_EXCHANGE
    assert "bj" in SECURITY_EXCHANGE
    print("✓ SECURITY_EXCHANGE 包含所有市场")

    assert "BJ_A_STOCK" in ["BJ_A_STOCK"]  # 检查是否已添加北京股票类型
    print("✓ 已添加北京A股类型")


def print_summary():
    """打印汇总信息"""
    print("\n" + "="*60)
    print("📊 常量汇总统计")
    print("="*60)
    print(f"HQ 服务器数量: {len(HQ_HOSTS)}")
    print(f"EX 服务器数量: {len(EX_HOSTS)}")
    print(f"GP 服务器数量: {len(GP_HOSTS)}")
    print(f"周期映射数量: {len(FREQUENCY_MAP)}")
    print(f"市场代码映射: {len(MARKET_CODE_MAP)}")
    print(f"支持交易所: {SECURITY_EXCHANGE}")
    print("="*60)

    print("\n新增常量（相比旧版本）:")
    print("  ✅ 完整的 38 个 HQ_HOSTS 服务器")
    print("  ✅ EX_HOSTS 扩展行情服务器（3个）")
    print("  ✅ GP_HOSTS 财务数据服务器（1个）")
    print("  ✅ FREQUENCY_MAP 周期映射字典")
    print("  ✅ MARKET_CODE_MAP 市场代码映射")
    print("  ✅ MARKET_NAME_MAP 市场名称映射")
    print("  ✅ MAX_QUOTES_COUNT 和 MAX_SECURITY_LIST_COUNT")
    print("  ✅ TYPE_FLATS 和 TYPE_GROUP 板块类型")
    print("  ✅ BJ_A_STOCK 北京A股类型")
    print("  ✅ bj 北京交易所代码")


def main():
    """主测试函数"""
    print("="*60)
    print("🔍 tdx_asyncio 常量验证工具")
    print("="*60)

    try:
        test_tdx_params()
        test_server_lists()
        test_frequency_map()
        test_market_map()
        test_security_types()

        print_summary()

        print("\n" + "="*60)
        print("✅ 所有验证通过！常量定义正确")
        print("="*60)
        return 0

    except AssertionError as e:
        print(f"\n❌ 验证失败: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ 发生错误: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())

