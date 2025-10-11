# -*- coding: utf-8 -*-
"""
完整测试 TradeX.dll 行情API - 使用32位Python
验证：
1. 非交易时间能否获取数据
2. 返回的字段有哪些
3. 最多能返回多少个品种
"""
import ctypes
import os
import sys
from datetime import datetime
import threading
import queue

# 让 32 位 Python 能导入 venv 的第三方库（mootdx/tdxpy）
sys.path.append(r"C:\Users\USER\Desktop\terminal_v0.50\venv310\Lib\site-packages")


def main():
    print("=" * 100)
    print("TradeX.dll 行情API 完整测试")
    print("=" * 100)
    print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Python位数: {ctypes.sizeof(ctypes.c_voidp) * 8} 位")
    print()

    # 加载 DLL
    dll_path = r"C:\Users\USER\Desktop\terminal_v0.50\backend\infrastructure\Trademy-src\bin\TradeXDemo\TradeX.dll"

    if not os.path.exists(dll_path):
        print(f"错误：找不到 DLL 文件: {dll_path}")
        input("按回车键退出...")
        return 1

    print(f"正在加载 DLL: {dll_path}")

    try:
        dll = ctypes.WinDLL(dll_path)
        print("[√] DLL 加载成功")
    except Exception as e:
        print(f"[×] DLL 加载失败: {e}")
        input("按回车键退出...")
        return 1

    print()

    # 设置函数签名
    print("设置函数签名...")

    dll.TdxHq_Connect.argtypes = [
        ctypes.c_char_p,
        ctypes.c_short,
        ctypes.c_char_p,
        ctypes.c_char_p,
    ]
    dll.TdxHq_Connect.restype = ctypes.c_bool

    dll.TdxHq_GetSecurityQuotes.argtypes = [
        ctypes.POINTER(ctypes.c_char),
        ctypes.POINTER(ctypes.c_char_p),
        ctypes.POINTER(ctypes.c_short),
        ctypes.c_char_p,
        ctypes.c_char_p,
    ]
    dll.TdxHq_GetSecurityQuotes.restype = ctypes.c_bool

    dll.TdxHq_Disconnect.argtypes = []
    dll.TdxHq_Disconnect.restype = None

    print("[√] 函数签名设置完成")
    print()

    # 连接行情服务器
    print("=" * 100)
    print("测试1: 连接行情服务器")
    print("=" * 100)

    result = ctypes.create_string_buffer(1024 * 1024)
    err_info = ctypes.create_string_buffer(256)

    # 尝试多个行情服务器（动态汇总 mootdx 与 tdxpy 的全部服务器，并去重）
    try:
        from mootdx.consts import HQ_HOSTS as MOOTDX_HQ, EX_HOSTS as MOOTDX_EX
        from tdxpy.constants import hq_hosts as TDXPY_HQ
        combined_hosts = []
        for name, addr, port in TDXPY_HQ:
            combined_hosts.append((addr, int(port), f"tdxpy:{name}"))
        # 仅测试券商/公共节点（来自 tdxpy.constants.hq_hosts）
        # 去重并保序
        seen = set()
        servers = []
        for ip, port, name in combined_hosts:
            key = f"{ip}:{port}"
            if key in seen:
                continue
            seen.add(key)
            servers.append((ip, port, name))
    except Exception:
        # 备用方案：直接解析 venv 下的常量文件，提取 ('name','ip',port) 形式
        combined_hosts = []
        try:
            def _parse_hosts_from_file(path, keys):
                hosts = []
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        txt = f.read()
                    import re
                    # 匹配 ('名称', 'IP', 端口)
                    pattern = re.compile(r"\('([^']+)'\s*,\s*'(\d{1,3}(?:\.\d{1,3}){3})'\s*,\s*(\d{2,5})\)")
                    for m in pattern.finditer(txt):
                        name, ip, port = m.group(1), m.group(2), int(m.group(3))
                        hosts.append((name, ip, port))
                except Exception:
                    pass
                return hosts

            mootdx_consts = r"C:\Users\USER\Desktop\terminal_v0.50\venv310\Lib\site-packages\mootdx\consts.py"
            tdxpy_consts = r"C:\Users\USER\Desktop\terminal_v0.50\venv310\Lib\site-packages\tdxpy\constants.py"

            mh = _parse_hosts_from_file(mootdx_consts, ['HQ_HOSTS','EX_HOSTS'])
            th = _parse_hosts_from_file(tdxpy_consts, ['hq_hosts'])
            # 标注来源
            for name, ip, port in th:
                combined_hosts.append((ip, int(port), f"tdxpy:{name}"))
            for name, ip, port in mh:
                # 根据名称简单归类
                src = "mootdx_ex" if "扩展" in name or "EX" in name.upper() else "mootdx"
                combined_hosts.append((ip, int(port), f"{src}:{name}"))

            # 去重
            seen = set()
            servers = []
            for ip, port, name in combined_hosts:
                key = f"{ip}:{port}"
                if key in seen:
                    continue
                seen.add(key)
                servers.append((ip, port, name))
        except Exception:
            # 若依然失败，最后回退
            servers = [
                ("47.112.95.207", 7720, "用户指定服务器"),
                ("120.46.186.223", 7709, "备用1"),
                ("115.238.90.165", 7709, "可达节点"),
                ("119.147.212.81", 7709, "深圳行情服务器"),
                ("202.108.253.131", 7709, "北京行情服务器"),
                ("106.120.74.86", 7709, "上海行情服务器"),
            ]

    connected = False
    connected_server = None

    # 调试输出：打印将要尝试的服务器数量与前5个
    try:
        print(f"将尝试服务器数量: {len(servers)}")
        for i, s in enumerate(servers[:5], 1):
            ip, port, name = s
            print(f"  {i}. {name} ({ip}:{port})")
    except Exception as _e:
        print(f"服务器清单调试输出异常: {type(_e).__name__}: {_e}")

    for server_ip, server_port, server_name in servers:
        print(f"\n尝试连接: {server_name} ({server_ip}:{server_port})")

        # 使用线程包装，避免 TdxHq_Connect 长时间阻塞
        q: "queue.Queue[bool]" = queue.Queue(maxsize=1)
        def _connect():
            try:
                ok = dll.TdxHq_Connect(server_ip.encode("gbk"), server_port, result, err_info)
                q.put(bool(ok))
            except Exception:
                q.put(False)
        t = threading.Thread(target=_connect, daemon=True)
        t.start()
        try:
            success = q.get(timeout=10.0)  # 10秒连接超时
        except queue.Empty:
            success = False
            print("[×] 连接超时（>10s）")

        if success:
            print(f"[√] 连接成功!")
            connect_result = result.value.decode("gbk", errors="ignore")
            if connect_result:
                print(f"    连接信息: {connect_result}")
            connected = True
            connected_server = f"{server_ip}:{server_port}"
            break
        else:
            error_msg = err_info.value.decode("gbk", errors="ignore")
            if error_msg.strip():
                print(f"[×] 连接失败: {error_msg}")
            # 清理可能残留的信息缓冲
            result.value = b""
            err_info.value = b""

    if not connected:
        print("\n所有服务器连接失败！")
        input("按回车键退出...")
        return 1

    print()
    print("=" * 100)
    print("测试2: 查询2只股票的五档行情（查看返回字段）")
    print("=" * 100)
    print()

    # 准备查询参数 - 2只股票
    markets = (ctypes.c_char * 2)()
    markets[0] = 0  # 深圳
    markets[1] = 1  # 上海

    symbols = (ctypes.c_char_p * 2)()
    symbols[0] = b"000001"
    symbols[1] = b"600000"

    count = ctypes.c_short(2)

    # 清空缓冲区
    result = ctypes.create_string_buffer(1024 * 1024)
    err_info = ctypes.create_string_buffer(256)

    print("查询证券: 000001 (平安银行), 600000 (浦发银行)")
    print()

    success = dll.TdxHq_GetSecurityQuotes(markets, symbols, ctypes.byref(count), result, err_info)

    if not success:
        error_msg = err_info.value.decode("gbk", errors="ignore")
        print(f"[×] 查询失败: {error_msg}")
        dll.TdxHq_Disconnect()
        input("按回车键退出...")
        return 1

    # 解析结果
    result_str = result.value.decode("gbk", errors="ignore")

    print("[√] 查询成功!")
    print()
    print("=" * 100)
    print("返回的原始CSV数据：")
    print("=" * 100)
    print(result_str)
    print("=" * 100)
    print()

    # 解析字段
    lines = result_str.strip().split("\n")
    if len(lines) >= 1:
        headers = lines[0].split("\t")
        print(f"字段总数: {len(headers)} 个")
        print()
        print("字段列表：")
        print("-" * 100)
        for i, header in enumerate(headers, 1):
            print(f"{i:2d}. {header}")
        print("-" * 100)

        # 显示数据行
        if len(lines) > 1:
            print()
            print("数据示例（第1行）：")
            print("-" * 100)
            values = lines[1].split("\t")
            for i, (header, value) in enumerate(zip(headers, values), 1):
                print(f"{i:2d}. {header:<15s} = {value}")
            print("-" * 100)

    # 测试批量查询限制
    print()
    print("=" * 100)
    print("测试3: 批量查询限制（测试能返回多少个品种）")
    print("=" * 100)
    print()

    # 构造测试用的股票代码
    test_stocks = []
    # 深圳：000001-000100, 000300-000400
    for i in range(1, 101):
        test_stocks.append((0, f"{i:06d}"))
    for i in range(300, 400):
        test_stocks.append((0, f"{i:06d}"))
    # 上海：600000-600100
    for i in range(600000, 600100):
        test_stocks.append((1, f"{i}"))

    test_sizes = [10, 50, 100, 150, 200, 250, 290, 300]

    print("批量查询测试结果：")
    print("-" * 100)

    max_successful = 0

    for size in test_sizes:
        batch = test_stocks[:size]

        try:
            # 准备参数
            markets_arr = (ctypes.c_char * size)()
            symbols_arr = (ctypes.c_char_p * size)()

            for i, (market, symbol) in enumerate(batch):
                markets_arr[i] = market
                symbols_arr[i] = symbol.encode("gbk")

            count_ptr = ctypes.c_short(size)
            result_buf = ctypes.create_string_buffer(1024 * 1024)
            err_buf = ctypes.create_string_buffer(256)

            print(f"[{size:3d}只] 查询中...", end=" ", flush=True)

            success = dll.TdxHq_GetSecurityQuotes(
                markets_arr, symbols_arr, ctypes.byref(count_ptr), result_buf, err_buf
            )

            if success:
                result_text = result_buf.value.decode("gbk", errors="ignore")
                result_lines = result_text.strip().split("\n")
                actual_count = len(result_lines) - 1  # 减去表头行

                if actual_count > 0:
                    print(f"✓ 成功返回 {actual_count} 条数据", end="")
                    max_successful = max(max_successful, actual_count)

                    if actual_count < size:
                        print(f" (限制)")
                    else:
                        print()
                else:
                    print("✗ 返回空数据")
            else:
                error_msg = err_buf.value.decode("gbk", errors="ignore")
                print(f"✗ 失败: {error_msg[:50]}")

        except Exception as e:
            print(f"✗ 异常: {str(e)[:50]}")

    print("-" * 100)
    print(f"\n实测最大返回数量: {max_successful} 只")

    # 断开连接
    print()
    dll.TdxHq_Disconnect()
    print("[√] 已断开连接")
    print()
    print("=" * 100)
    print("测试完成！")
    print("=" * 100)
    print()
    print("总结：")
    print(f"1. 非交易时间连接: {'成功' if connected else '失败'}")
    print(f"2. 连接服务器: {connected_server if connected else '无'}")
    print(f"3. 返回字段数量: {len(headers) if 'headers' in locals() else '未知'}")
    print(f"4. 批量查询限制: 最多 {max_successful} 只")

    input("\n按回车键退出...")
    return 0


if __name__ == "__main__":
    sys.exit(main())



