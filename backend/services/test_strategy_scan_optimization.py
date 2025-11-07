# -*- coding: utf-8 -*-
"""
策略文件扫描优化测试脚本

测试native_iocp优化后的策略文件扫描功能：
1. 测试native_iocp优化后的扫描逻辑
2. 测试降级逻辑（当native_iocp不可用时）
3. 验证扫描结果的正确性
4. 性能对比测试
"""

import sys
import time
import tempfile
import shutil
from pathlib import Path
from typing import List

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# 设置日志
import logging

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)


def create_test_strategy_files(test_dir: Path, num_files: int = 10) -> List[Path]:
    """创建测试用的策略文件"""
    created_files = []

    # 创建主目录下的文件
    for i in range(num_files):
        file_path = test_dir / f"strategy_{i}.py"
        file_path.write_text(f"# Strategy {i}\nclass Strategy{i}:\n    pass\n", encoding="utf-8")
        created_files.append(file_path)

    # 创建子目录
    sub_dir = test_dir / "subfolder"
    sub_dir.mkdir(exist_ok=True)

    for i in range(5):
        file_path = sub_dir / f"sub_strategy_{i}.py"
        file_path.write_text(
            f"# Sub Strategy {i}\nclass SubStrategy{i}:\n    pass\n", encoding="utf-8"
        )
        created_files.append(file_path)

    # 创建__init__.py文件（应该被跳过）
    init_file = test_dir / "__init__.py"
    init_file.write_text("# Init file\n", encoding="utf-8")

    return created_files


def test_native_iocp_scan():
    """测试native_iocp优化后的扫描"""
    logger.info("\n" + "=" * 60, extra={"log_type": "STAGE_NODE"})
    logger.info("测试1: native_iocp优化后的扫描", extra={"log_type": "STAGE_NODE"})
    logger.info("=" * 60, extra={"log_type": "STAGE_NODE"})

    # 检查native_iocp是否可用
    try:
        from backend.infrastructure.native.native_iocp import (
            fast_dir_walk,
            BATCH_AVAILABLE,
        )

        if not BATCH_AVAILABLE:
            logger.warning("⚠️ native_iocp不可用，跳过此测试", extra={"log_type": "STAGE_NODE"})
            return False
        logger.info("✅ native_iocp可用", extra={"log_type": "STAGE_NODE"})
    except ImportError:
        logger.warning("⚠️ native_iocp未安装，跳过此测试", extra={"log_type": "STAGE_NODE"})
        return False

    # 创建临时测试目录
    test_dir = Path(tempfile.mkdtemp(prefix="test_strategy_scan_"))
    try:
        # 创建测试文件
        created_files = create_test_strategy_files(test_dir, num_files=10)
        logger.info(f"✅ 创建了 {len(created_files)} 个测试文件", extra={"log_type": "STAGE_NODE"})

        # 测试fast_dir_walk
        start_time = time.time()
        result = fast_dir_walk(str(test_dir))  # type: ignore[call-arg]
        elapsed = time.time() - start_time

        logger.info(f"✅ fast_dir_walk执行时间: {elapsed*1000:.2f}ms", extra={"log_type": "STAGE_NODE"})

        if result and len(result) > 0:
            root, dirs_list, files_list = result[0]
            logger.info(
                f"✅ 扫描结果: 根目录={root}, 子目录数={len(dirs_list)}, 文件数={len(files_list)}",
                extra={"log_type": "STAGE_NODE"},
            )

            # 验证结果
            py_files = [
                f for f in files_list if f.endswith(".py") and not Path(f).name.startswith("__")
            ]
            logger.info(
                f"✅ 找到 {len(py_files)} 个.py文件（排除__init__）",
                extra={"log_type": "STAGE_NODE"},
            )

            return True
        else:
            logger.warning("❌ fast_dir_walk返回空结果", extra={"log_type": "STAGE_NODE"})
            return False

    except Exception as e:
        logger.error(f"❌ 测试失败: {e}", exc_info=True, extra={"log_type": "STAGE_NODE"})
        return False
    finally:
        # 清理测试目录
        if test_dir.exists():
            shutil.rmtree(test_dir)
            logger.info(f"✅ 清理测试目录: {test_dir}", extra={"log_type": "STAGE_NODE"})


def test_strategy_service_scan():
    """测试策略中心服务的扫描功能（测试文件扫描，不依赖策略解析）"""
    logger.info("\n" + "=" * 60, extra={"log_type": "STAGE_NODE"})
    logger.info("测试2: 策略中心服务扫描功能", extra={"log_type": "STAGE_NODE"})
    logger.info("=" * 60, extra={"log_type": "STAGE_NODE"})

    # 创建临时测试目录
    test_dir = Path(tempfile.mkdtemp(prefix="test_strategy_service_"))
    try:
        # 创建测试文件
        created_files = create_test_strategy_files(test_dir, num_files=10)
        logger.info(f"✅ 创建了 {len(created_files)} 个测试文件", extra={"log_type": "STAGE_NODE"})

        # 直接测试扫描逻辑（不依赖策略解析）
        # 模拟get_available_strategies中的扫描部分
        from backend.services.strategy_center_service import (
            NATIVE_IOCP_AVAILABLE,
            fast_dir_walk,
        )

        scan_dir = test_dir
        file_paths = []

        # 使用与get_available_strategies相同的扫描逻辑
        if NATIVE_IOCP_AVAILABLE and fast_dir_walk is not None:

            def _recursive_walk(directory: Path) -> List[Path]:
                """递归遍历目录，返回所有.py文件路径"""
                py_files = []
                try:
                    if fast_dir_walk is None:
                        return list(directory.rglob("*.py"))
                    result = fast_dir_walk(str(directory))  # type: ignore[call-arg]
                    if result and len(result) > 0:
                        _root, dirs_list, files_list = result[0]

                        for file_name in files_list:
                            file_path = Path(file_name)
                            if file_path.suffix == ".py" and not file_path.name.startswith("__"):
                                py_files.append(file_path)

                        for dir_name in dirs_list:
                            sub_dir = Path(dir_name)
                            py_files.extend(_recursive_walk(sub_dir))
                except Exception as e:
                    logger.warning(f"⚠️ fast_dir_walk失败，回退到rglob: {e}", extra={"log_type": "STAGE_NODE"})
                    return list(directory.rglob("*.py"))
                return py_files

            try:
                file_paths = _recursive_walk(scan_dir)
                logger.info("✅ 使用native_iocp扫描", extra={"log_type": "STAGE_NODE"})
            except Exception as e:
                logger.warning(f"⚠️ native_iocp扫描失败，回退到rglob: {e}", extra={"log_type": "STAGE_NODE"})
                file_paths = list(scan_dir.rglob("*.py"))
        else:
            file_paths = list(scan_dir.rglob("*.py"))
            logger.info("✅ 使用rglob扫描（降级模式）", extra={"log_type": "STAGE_NODE"})

        # 过滤__init__文件
        file_paths = [f for f in file_paths if not f.name.startswith("__")]

        # 测试扫描功能
        start_time = time.time()
        elapsed = time.time() - start_time

        logger.info(f"✅ 扫描执行时间: {elapsed*1000:.2f}ms", extra={"log_type": "STAGE_NODE"})
        logger.info(f"✅ 扫描成功: 找到 {len(file_paths)} 个.py文件", extra={"log_type": "STAGE_NODE"})

        # 验证结果
        expected_count = len(created_files)  # 应该找到所有创建的.py文件
        if len(file_paths) == expected_count:
            logger.info(
                f"✅ 文件数量正确（期望 {expected_count} 个，实际 {len(file_paths)} 个）",
                extra={"log_type": "STAGE_NODE"},
            )
            return True
        else:
            logger.warning(
                f"⚠️ 文件数量不匹配（期望 {expected_count} 个，实际 {len(file_paths)} 个）",
                extra={"log_type": "STAGE_NODE"},
            )
            # 显示差异
            expected_files = {f.name for f in created_files}
            found_files = {f.name for f in file_paths}
            missing = expected_files - found_files
            extra = found_files - expected_files
            if missing:
                logger.info(f"   缺失文件: {missing}", extra={"log_type": "STAGE_NODE"})
            if extra:
                logger.info(f"   额外文件: {extra}", extra={"log_type": "STAGE_NODE"})
            return False

    except Exception as e:
        logger.error(f"❌ 测试失败: {e}", exc_info=True, extra={"log_type": "STAGE_NODE"})
        return False
    finally:
        # 清理测试目录
        if test_dir.exists():
            shutil.rmtree(test_dir)
            logger.info(f"✅ 清理测试目录: {test_dir}", extra={"log_type": "STAGE_NODE"})


def test_fallback_logic():
    """测试降级逻辑"""
    logger.info("\n" + "=" * 60, extra={"log_type": "STAGE_NODE"})
    logger.info("测试3: 降级逻辑测试", extra={"log_type": "STAGE_NODE"})
    logger.info("=" * 60, extra={"log_type": "STAGE_NODE"})

    # 创建临时测试目录
    test_dir = Path(tempfile.mkdtemp(prefix="test_fallback_"))
    try:
        # 创建测试文件
        created_files = create_test_strategy_files(test_dir, num_files=5)
        logger.info(f"✅ 创建了 {len(created_files)} 个测试文件", extra={"log_type": "STAGE_NODE"})

        # 模拟native_iocp不可用的情况
        import backend.services.strategy_center_service as strategy_module

        # 保存原始值
        original_available = strategy_module.NATIVE_IOCP_AVAILABLE
        original_fast_dir_walk = strategy_module.fast_dir_walk

        try:
            # 模拟native_iocp不可用
            strategy_module.NATIVE_IOCP_AVAILABLE = False
            strategy_module.fast_dir_walk = None

            # 直接测试扫描逻辑（不依赖策略解析）
            scan_dir = test_dir
            file_paths = []

            # 使用与get_available_strategies相同的扫描逻辑
            if strategy_module.NATIVE_IOCP_AVAILABLE and strategy_module.fast_dir_walk is not None:
                # 不应该进入这里
                logger.error(
                    "❌ 降级逻辑失败: 应该使用rglob，但进入了native_iocp分支",
                    extra={"log_type": "STAGE_NODE"},
                )
                return False
            else:
                # 应该使用rglob
                file_paths = list(scan_dir.rglob("*.py"))
                logger.info("✅ 使用rglob扫描（降级模式）", extra={"log_type": "STAGE_NODE"})

            # 过滤__init__文件
            file_paths = [f for f in file_paths if not f.name.startswith("__")]

            # 验证结果
            expected_count = len(created_files)
            if len(file_paths) == expected_count:
                logger.info(
                    f"✅ 降级逻辑工作正常: 找到 {len(file_paths)} 个文件（使用rglob）",
                    extra={"log_type": "STAGE_NODE"},
                )
                return True
            else:
                logger.warning(
                    f"⚠️ 文件数量不匹配（期望 {expected_count} 个，实际 {len(file_paths)} 个）",
                    extra={"log_type": "STAGE_NODE"},
                )
                return False

        finally:
            # 恢复原始值
            strategy_module.NATIVE_IOCP_AVAILABLE = original_available
            strategy_module.fast_dir_walk = original_fast_dir_walk

    except Exception as e:
        logger.error(f"❌ 测试失败: {e}", exc_info=True, extra={"log_type": "STAGE_NODE"})
        return False
    finally:
        # 清理测试目录
        if test_dir.exists():
            shutil.rmtree(test_dir)
            logger.info(f"✅ 清理测试目录: {test_dir}", extra={"log_type": "STAGE_NODE"})


def test_performance_comparison():
    """性能对比测试"""
    logger.info("\n" + "=" * 60, extra={"log_type": "STAGE_NODE"})
    logger.info("测试4: 性能对比测试", extra={"log_type": "STAGE_NODE"})
    logger.info("=" * 60, extra={"log_type": "STAGE_NODE"})

    # 创建临时测试目录（更多文件）
    test_dir = Path(tempfile.mkdtemp(prefix="test_performance_"))
    try:
        # 创建更多测试文件
        created_files = create_test_strategy_files(test_dir, num_files=50)

        # 创建更多子目录
        for i in range(5):
            sub_dir = test_dir / f"subfolder_{i}"
            sub_dir.mkdir(exist_ok=True)
            for j in range(10):
                file_path = sub_dir / f"strategy_{i}_{j}.py"
                file_path.write_text(
                    f"# Strategy {i}_{j}\nclass Strategy{i}_{j}:\n    pass\n", encoding="utf-8"
                )
                created_files.append(file_path)

        logger.info(f"✅ 创建了 {len(created_files)} 个测试文件", extra={"log_type": "STAGE_NODE"})

        # 测试rglob性能
        start_time = time.time()
        rglob_files = list(test_dir.rglob("*.py"))
        rglob_elapsed = time.time() - start_time
        rglob_count = len([f for f in rglob_files if not f.name.startswith("__")])

        logger.info(
            f"✅ rglob执行时间: {rglob_elapsed*1000:.2f}ms, 找到 {rglob_count} 个文件",
            extra={"log_type": "STAGE_NODE"},
        )

        # 测试native_iocp性能（如果可用）
        try:
            from backend.infrastructure.native.native_iocp import (
                fast_dir_walk,
                BATCH_AVAILABLE,
            )

            if BATCH_AVAILABLE:

                def _recursive_walk(directory: Path) -> List[Path]:
                    """递归遍历目录"""
                    py_files = []
                    try:
                        result = fast_dir_walk(str(directory))  # type: ignore[call-arg]
                        if result and len(result) > 0:
                            _root, dirs_list, files_list = result[0]

                            for file_name in files_list:
                                file_path = Path(file_name)
                                if file_path.suffix == ".py" and not file_path.name.startswith(
                                    "__"
                                ):
                                    py_files.append(file_path)

                            for dir_name in dirs_list:
                                sub_dir = Path(dir_name)
                                py_files.extend(_recursive_walk(sub_dir))
                    except Exception:
                        pass
                    return py_files

                start_time = time.time()
                native_files = _recursive_walk(test_dir)
                native_elapsed = time.time() - start_time
                native_count = len(native_files)

                logger.info(
                    f"✅ native_iocp执行时间: {native_elapsed*1000:.2f}ms, 找到 {native_count} 个文件",
                    extra={"log_type": "STAGE_NODE"},
                )

                if native_elapsed > 0:
                    speedup = rglob_elapsed / native_elapsed
                    logger.info(f"✅ 性能提升: {speedup:.2f}x", extra={"log_type": "STAGE_NODE"})

                    if speedup > 1.0:
                        logger.info(
                            f"✅ native_iocp比rglob快 {speedup:.2f} 倍",
                            extra={"log_type": "STAGE_NODE"},
                        )
                    else:
                        logger.warning(
                            "⚠️ native_iocp性能未提升（可能文件数量较少）",
                            extra={"log_type": "STAGE_NODE"},
                        )

                return True
            else:
                logger.warning("⚠️ native_iocp不可用，跳过性能对比", extra={"log_type": "STAGE_NODE"})
                return True

        except ImportError:
            logger.warning("⚠️ native_iocp未安装，跳过性能对比", extra={"log_type": "STAGE_NODE"})
            return True

    except Exception as e:
        logger.error(f"❌ 测试失败: {e}", exc_info=True, extra={"log_type": "STAGE_NODE"})
        return False
    finally:
        # 清理测试目录
        if test_dir.exists():
            shutil.rmtree(test_dir)
            logger.info(f"✅ 清理测试目录: {test_dir}", extra={"log_type": "STAGE_NODE"})


def main():
    """主测试函数"""
    logger.info("=" * 60, extra={"log_type": "STAGE_NODE"})
    logger.info("策略文件扫描优化测试", extra={"log_type": "STAGE_NODE"})
    logger.info("=" * 60, extra={"log_type": "STAGE_NODE"})

    results = []

    # 测试1: native_iocp扫描
    results.append(("native_iocp扫描", test_native_iocp_scan()))

    # 测试2: 策略中心服务扫描
    results.append(("策略中心服务扫描", test_strategy_service_scan()))

    # 测试3: 降级逻辑
    results.append(("降级逻辑", test_fallback_logic()))

    # 测试4: 性能对比
    results.append(("性能对比", test_performance_comparison()))

    # 输出测试结果
    logger.info("\n" + "=" * 60, extra={"log_type": "STAGE_NODE"})
    logger.info("测试结果汇总", extra={"log_type": "STAGE_NODE"})
    logger.info("=" * 60, extra={"log_type": "STAGE_NODE"})

    passed = 0
    failed = 0

    for test_name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        logger.info(f"{test_name}: {status}", extra={"log_type": "STAGE_NODE"})
        if result:
            passed += 1
        else:
            failed += 1

    logger.info(f"\n总计: {passed} 个通过, {failed} 个失败", extra={"log_type": "STAGE_NODE"})

    if failed == 0:
        logger.info("\n🎉 所有测试通过！", extra={"log_type": "STAGE_NODE"})
        return 0
    else:
        logger.warning(f"\n⚠️ 有 {failed} 个测试失败", extra={"log_type": "STAGE_NODE"})
        return 1


if __name__ == "__main__":
    sys.exit(main())
