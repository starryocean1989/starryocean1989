# -*- coding: utf-8 -*-
"""
运行所有E2E测试并生成分析报告
"""

import sys
import subprocess
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


def run_test_script(script_name: str) -> bool:
    """运行测试脚本"""
    script_path = project_root / "tests" / "e2e" / script_name

    print(f"\n{'='*70}")
    print(f"运行: {script_name}")
    print(f"{'='*70}\n")

    try:
        # 使用当前Python解释器运行脚本
        result = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=str(project_root),
            capture_output=False,
            text=True,
        )

        return result.returncode == 0
    except Exception as e:
        print(f"❌ 运行{script_name}失败: {e}")
        return False


def main():
    """主函数"""
    print("\n" + "=" * 70)
    print("LoadBalancer E2E测试套件 - 完整执行")
    print("=" * 70)

    # 测试脚本列表
    test_scripts = [
        "test_loadbalancer_e2e_basic.py",
        "test_loadbalancer_e2e_variants.py",
    ]

    results = []

    # 运行所有测试
    for script in test_scripts:
        result = run_test_script(script)
        results.append((script, result))

    # 输出总结
    print("\n" + "=" * 70)
    print("测试执行总结")
    print("=" * 70)

    for script, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{status}: {script}")

    success_count = sum(1 for _, r in results if r)
    total_count = len(results)

    # 运行性能分析
    print("\n" + "=" * 70)
    print("生成性能分析报告")
    print("=" * 70)

    run_test_script("analyze_performance.py")

    # 最终结果
    if success_count == total_count:
        print(f"\n🎉 所有{total_count}个E2E测试脚本执行成功！")
        print(f"\n性能数据已保存到: tests/e2e/performance_data.json")
        return 0
    else:
        print(f"\n⚠️  {total_count - success_count}/{total_count} 个测试脚本失败")
        return 1


if __name__ == "__main__":
    exit(main())
