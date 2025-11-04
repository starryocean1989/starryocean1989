# -*- coding: utf-8 -*-
"""
行情看板诊断脚本

用于诊断行情看板不显示的问题，输出关键日志信息
"""

import sys
import re
from pathlib import Path
from datetime import datetime

def find_latest_log():
    """查找最新的启动日志文件"""
    log_dir = Path(__file__).parent.parent / "logs" / "ai"
    
    if not log_dir.exists():
        print(f"❌ 日志目录不存在: {log_dir}")
        return None
    
    # 查找最新的application_startup_*.log文件
    log_files = list(log_dir.glob("application_startup_*.log"))
    
    if not log_files:
        print(f"❌ 未找到启动日志文件在: {log_dir}")
        return None
    
    # 按修改时间排序，取最新的
    latest_log = max(log_files, key=lambda p: p.stat().st_mtime)
    return latest_log

def diagnose_market_board(log_file):
    """诊断行情看板问题"""
    print("=" * 80)
    print("行情看板诊断报告")
    print("=" * 80)
    print(f"日志文件: {log_file}")
    print(f"分析时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    print()
    
    with open(log_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 1. 检查EVENT_UNIFIED_DATA_MANAGER_READY事件发布
    print("📊 1. 检查UnifiedDataManager就绪事件发布:")
    print("-" * 80)
    
    event_patterns = [
        (r"✅ 已发布 UnifiedDataManager 就绪事件.*",  "从步骤7发布"),
        (r"✅ 已发布 UnifiedDataManager 就绪事件.*注入逻辑", "从注入逻辑发布"),
    ]
    
    for pattern, desc in event_patterns:
        matches = re.findall(pattern, content)
        if matches:
            print(f"  ✅ {desc}: 找到{len(matches)}次")
            for match in matches[:2]:  # 只显示前2次
                print(f"     {match}")
        else:
            print(f"  ❌ {desc}: 未找到")
    print()
    
    # 2. 检查ChartWizardEnhanced初始化
    print("📊 2. 检查ChartWizardEnhanced初始化:")
    print("-" * 80)
    
    init_patterns = [
        (r"✅ 已注册 UnifiedDataManager 就绪事件监听器", "事件监听器注册"),
        (r"⚡ 检测到MainEngine已有数据接口.*", "手动触发检测"),
        (r"🔔 ===== 收到 UnifiedDataManager 就绪事件 =====", "收到就绪事件"),
        (r"🚀 调用 _initialize_data_components...", "调用数据组件初始化"),
        (r"📍 开始初始化数据组件...", "开始数据组件初始化"),
        (r"✅ 检测到需要重建图表UI", "触发UI重建"),
        (r"🔧 开始重建UI：移除等待界面，创建图表界面", "开始重建UI"),
        (r"✅ ChartWizard组件创建成功", "ChartWizard创建成功"),
        (r"✅ 图表界面重建完成", "UI重建完成"),
    ]
    
    for pattern, desc in init_patterns:
        matches = re.findall(pattern, content)
        if matches:
            print(f"  ✅ {desc}: 找到")
        else:
            print(f"  ❌ {desc}: 未找到 ⚠️")
    print()
    
    # 3. 检查错误信息
    print("📊 3. 检查错误信息:")
    print("-" * 80)
    
    error_patterns = [
        r"❌.*市场看板.*",
        r"❌.*ChartWizard.*",
        r"❌.*MainEngine.*EventEngine.*",
        r"❌.*重建UI失败.*",
        r"⚠️.*EventEngine不可用.*",
    ]
    
    errors_found = False
    for pattern in error_patterns:
        matches = re.findall(pattern, content, re.IGNORECASE)
        if matches:
            errors_found = True
            print(f"  ⚠️ 发现错误:")
            for match in matches[:3]:  # 只显示前3个
                print(f"     {match}")
    
    if not errors_found:
        print("  ✅ 未发现明显错误")
    print()
    
    # 4. 检查MainEngine数据接口
    print("📊 4. 检查MainEngine数据接口注入:")
    print("-" * 80)
    
    inject_patterns = [
        (r"\[DATA-INJECT\] 开始注入 UnifiedDataManager.*", "开始注入"),
        (r"MainEngine 数据接口已验证.*品种数.*", "接口验证成功"),
        (r"MainEngine.get_all_contracts\(\) 返回空列表", "接口未注入（占位方法）"),
    ]
    
    for pattern, desc in inject_patterns:
        matches = re.findall(pattern, content)
        if matches:
            print(f"  ✅ {desc}: 找到")
            for match in matches[:2]:
                print(f"     {match}")
        else:
            print(f"  ❌ {desc}: 未找到")
    print()
    
    # 5. 生成诊断建议
    print("=" * 80)
    print("📋 诊断建议:")
    print("=" * 80)
    
    # 检查是否收到事件
    if not re.search(r"🔔 ===== 收到 UnifiedDataManager 就绪事件 =====", content):
        print("⚠️ 问题1: UI组件未收到UnifiedDataManager就绪事件")
        print("   可能原因:")
        print("   - EventEngine未初始化")
        print("   - 事件监听器注册失败")
        print("   - 事件发布在监听器注册之前")
        print()
        print("   建议:")
        print("   1. 检查日志中是否有'✅ 已注册 UnifiedDataManager 就绪事件监听器'")
        print("   2. 检查是否有'⚡ 检测到MainEngine已有数据接口'（手动触发）")
        print("   3. 查看完整日志确认EventEngine初始化状态")
        print()
    
    # 检查是否调用了初始化
    if not re.search(r"📍 开始初始化数据组件...", content):
        print("⚠️ 问题2: 数据组件初始化未被调用")
        print("   可能原因:")
        print("   - _data_ready标志未设置")
        print("   - 事件回调中发生异常")
        print()
        print("   建议:")
        print("   1. 检查日志中是否有'🛠️ 设置数据就绪标志'")
        print("   2. 检查是否有异常堆栈信息")
        print()
    
    # 检查是否重建了UI
    if not re.search(r"✅ 图表界面重建完成", content):
        print("⚠️ 问题3: UI未成功重建")
        print("   可能原因:")
        print("   - 布局未就绪")
        print("   - 引擎未初始化")
        print("   - ChartWizard创建失败")
        print()
        print("   建议:")
        print("   1. 检查是否有'❌ MainEngine 或 EventEngine 为空'")
        print("   2. 检查是否有'❌ 重建UI失败'")
        print("   3. 查看vnpy_chartwizard是否正确安装")
        print()
    
    print("=" * 80)
    print("如需更详细的诊断，请查看完整日志文件：")
    print(f"  {log_file}")
    print("=" * 80)

if __name__ == "__main__":
    log_file = find_latest_log()
    
    if log_file:
        diagnose_market_board(log_file)
    else:
        print("❌ 无法找到日志文件，请先启动应用")
        sys.exit(1)
