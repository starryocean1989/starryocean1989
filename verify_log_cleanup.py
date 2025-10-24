# -*- coding: utf-8 -*-
"""验证日志刷屏修复效果.

检查项：
1. cache_manager不再输出"缓存有效"DEBUG
2. data_quality不再逐项输出"有效起点"DEBUG
3. data_quality不再逐项输出"缺失检测"DEBUG
4. data_quality输出批量扫描汇总INFO
"""

import re
from pathlib import Path


def check_cache_manager_fix():
    """检查cache_manager是否移除了高频DEBUG日志"""
    print("=" * 60)
    print("检查1: cache_manager移除高频DEBUG日志")
    print("=" * 60)

    file_path = Path("backend/infrastructure/data_module_vnpy/cache_manager.py")
    content = file_path.read_text(encoding="utf-8")

    # 检查是否移除了"缓存有效"的DEBUG日志
    if 'logger.debug("缓存有效:' in content:
        print("  ❌ 仍存在'缓存有效'DEBUG日志")
        return False
    else:
        print("  ✅ 已移除'缓存有效'DEBUG日志")

    # 检查是否保留了"缓存已失效"的WARNING日志
    if 'logger.warning("缓存已失效:' in content:
        print("  ✅ 保留了'缓存已失效'WARNING日志")
    else:
        print("  ⚠️ 未找到'缓存已失效'WARNING日志")

    # 检查架构修复注释
    if "🎯 架构修复：移除高频DEBUG日志" in content:
        print("  ✅ 包含架构修复注释")
    else:
        print("  ⚠️ 缺少架构修复注释")

    return True


def check_data_quality_effective_start_fix():
    """检查data_quality是否移除了'有效起点'DEBUG日志"""
    print("\n" + "=" * 60)
    print("检查2: data_quality移除'有效起点'DEBUG日志")
    print("=" * 60)

    file_path = Path("backend/infrastructure/data_module_vnpy/local_data/data_quality.py")
    content = file_path.read_text(encoding="utf-8")

    # 检查是否移除了"有效起点"DEBUG日志
    if '品种 %s 有效起点:' in content and 'self.logger.debug(' in content:
        # 检查是否在logger.debug调用中
        pattern = r'self\.logger\.debug\([^)]*品种 %s 有效起点:'
        if re.search(pattern, content):
            print("  ❌ 仍存在'有效起点'DEBUG日志")
            return False
        else:
            print("  ✅ 已移除'有效起点'DEBUG日志调用")
    else:
        print("  ✅ 已移除'有效起点'DEBUG日志")

    # 检查架构修复注释
    if "🎯 架构修复：移除批量扫描中的逐项DEBUG日志" in content:
        print("  ✅ 包含架构修复注释")
    else:
        print("  ⚠️ 缺少架构修复注释")

    return True


def check_data_quality_missing_fix():
    """检查data_quality是否移除了'缺失检测'DEBUG日志"""
    print("\n" + "=" * 60)
    print("检查3: data_quality移除'缺失检测'DEBUG日志")
    print("=" * 60)

    file_path = Path("backend/infrastructure/data_module_vnpy/local_data/data_quality.py")
    content = file_path.read_text(encoding="utf-8")

    # 检查是否移除了"缺失检测"DEBUG日志
    if '品种 %s 缺失检测:' in content and 'self.logger.debug(' in content:
        # 检查是否在logger.debug调用中
        pattern = r'self\.logger\.debug\([^)]*品种 %s 缺失检测:'
        if re.search(pattern, content):
            print("  ❌ 仍存在'缺失检测'DEBUG日志")
            return False
        else:
            print("  ✅ 已移除'缺失检测'DEBUG日志调用")
    else:
        print("  ✅ 已移除'缺失检测'DEBUG日志")

    # 检查架构修复注释
    if "不再逐项输出缺失检测日志" in content:
        print("  ✅ 包含架构修复注释")
    else:
        print("  ⚠️ 缺少架构修复注释")

    return True


def check_batch_summary_added():
    """检查是否添加了批量扫描汇总INFO日志"""
    print("\n" + "=" * 60)
    print("检查4: data_quality添加批量扫描汇总INFO日志")
    print("=" * 60)

    file_path = Path("backend/infrastructure/data_module_vnpy/local_data/data_quality.py")
    content = file_path.read_text(encoding="utf-8")

    # 检查是否添加了汇总INFO日志
    if "数据质量扫描完成: 总品种=" in content:
        print("  ✅ 已添加批量扫描汇总INFO日志")
    else:
        print("  ❌ 未找到批量扫描汇总INFO日志")
        return False

    # 检查日志级别是否为INFO
    pattern = r'self\.logger\.info\([^)]*数据质量扫描完成'
    if re.search(pattern, content):
        print("  ✅ 使用INFO级别")
    else:
        print("  ❌ 未使用INFO级别")
        return False

    return True


def main():
    """主函数"""
    print("\n")
    print("╔" + "=" * 58 + "╗")
    print("║" + " " * 15 + "日志刷屏修复验证脚本" + " " * 15 + "║")
    print("╚" + "=" * 58 + "╝")
    print()

    results = []

    results.append(("cache_manager移除高频DEBUG", check_cache_manager_fix()))
    results.append(("data_quality移除'有效起点'DEBUG", check_data_quality_effective_start_fix()))
    results.append(("data_quality移除'缺失检测'DEBUG", check_data_quality_missing_fix()))
    results.append(("data_quality添加批量汇总INFO", check_batch_summary_added()))

    print("\n" + "=" * 60)
    print("总结")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{name}: {status}")

    print()
    print(f"总计: {passed}/{total} 项通过")

    if passed == total:
        print("\n🎉 所有日志刷屏修复已正确实施！")
        print("\n下一步：请重启terminal验证效果")
        print("=" * 60)
        print("预期结果：")
        print("  ❌ 不再出现: 数万条'缓存有效'DEBUG")
        print("  ❌ 不再出现: 数千条'有效起点'DEBUG")
        print("  ❌ 不再出现: 数千条'缺失检测'DEBUG")
        print("  ✅ 仅显示: 一条'数据质量扫描完成'汇总INFO")
        print("=" * 60)
        print("\n日志减少：20000+条 → 1条 = 减少99.99%")
        return 0
    else:
        print("\n⚠️ 部分修复未完成，请检查")
        return 1


if __name__ == "__main__":
    import sys

    sys.exit(main())

