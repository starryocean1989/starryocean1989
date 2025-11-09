# -*- coding: utf-8 -*-
"""巡检 native 模块日志桥接状态。

执行内容：
1. 校验 `backend.infrastructure.native.logging_bridge` 可正常安装。
2. 检测所有 native 模块（backend.infrastructure.native）是否按约定注册桥接：
   - Python 封装是否导入了 `logging_bridge` 或使用守护装饰器。
   - C 扩展是否依赖 `native_log_bridge`（通过文件探测 / 预定义列表）。
3. 为核心模块执行冒烟测试，验证日志输出：
   - 通过 `install_native_logging_bridge` 注入捕获 handler。
   - 调用模块公开 API，检查 handler 是否收到日志。

使用方式：
    python scripts/check_native_logging.py [--verbose]

返回：
    进程 exit code = 0 表示全部通过；否则打印失败详情并返回 1。
"""

from __future__ import annotations

import argparse
import importlib
import json
import logging
import pathlib
import pkgutil
import sys
from contextlib import contextmanager
from types import ModuleType
from typing import Any, Callable, Dict, Iterable, Iterator, List, Optional, Tuple

ROOT = pathlib.Path(__file__).resolve().parents[1]
PROJECT_SRC = ROOT / "backend" / "infrastructure" / "native"
NATIVE_PACKAGE = "backend.infrastructure.native"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# 核心模块（至少要执行冒烟测试）
SMOKE_MODULES = {
    "native_process_metrics": {
        "callable": "get_system_metrics",
        "kwargs": {"use_native": False},
    },
}

PASS = "✅"
FAIL = "❌"
WARNING = "⚠️"


class InspectionError(RuntimeError):
    pass


@contextmanager
def capture_native_logs(collected: List[Dict[str, Any]], *, verbose: bool = False) -> Iterator[None]:
    from backend.infrastructure.native import logging_bridge

    def handler(record: Dict[str, Any]) -> None:
        collected.append(record)
        if verbose:
            component = record.get("component")
            level = record.get("level")
            message = record.get("message")
            print(f"[bridge] {level} {component}: {message}")

    logging_bridge.install_native_logging_bridge(handler=handler)
    try:
        yield
    finally:
        logging_bridge.install_native_logging_bridge(handler=None)


def iter_native_modules() -> Iterable[Tuple[str, Optional[pathlib.Path]]]:
    package = importlib.import_module(NATIVE_PACKAGE)
    package_file = getattr(package, "__file__", None)
    if not package_file:
        raise InspectionError(f"无法定位 native 包路径：{NATIVE_PACKAGE}")
    package_path = pathlib.Path(package_file).resolve().parent
    for module_info in pkgutil.iter_modules([str(package_path)]):
        if module_info.ispkg:
            yield module_info.name, package_path / module_info.name
        else:
            yield module_info.name, package_path / f"{module_info.name}.py"


def module_uses_logging_bridge(module: ModuleType) -> bool:
    source = getattr(module, "__file__", "")
    if not source:
        return False
    path = pathlib.Path(source)
    if path.suffix not in {".py", ".pyi"}:
        return False
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    return "logging_bridge" in text or "native_call_guard" in text


def check_python_wrappers(*, verbose: bool = False) -> List[str]:
    missing: List[str] = []
    for name, _ in iter_native_modules():
        if name.startswith("__"):
            continue
        full_name = f"{NATIVE_PACKAGE}.{name}"
        try:
            module = importlib.import_module(full_name)
        except Exception as exc:
            missing.append(f"{name}: 导入失败 -> {exc}")
            continue
        if not module_uses_logging_bridge(module):
            missing.append(f"{name}: 未检测到 logging_bridge 接入")
    if verbose:
        print(f"Python 包装层检查完成，缺失 {len(missing)} 项。")
    return missing


def check_c_extensions(*, verbose: bool = False) -> List[str]:
    issues: List[str] = []
    expected_headers = list(PROJECT_SRC.glob("**/native_log_bridge.h"))
    if not expected_headers:
        issues.append("未找到 native_log_bridge.h，可能未同步阶段1产物")
    for module_dir in PROJECT_SRC.iterdir():
        if not module_dir.is_dir():
            continue
        c_matches = list(module_dir.glob("**/*.c")) + list(module_dir.glob("**/*.cpp"))
        if not c_matches:
            continue
        uses_bridge = any("native_log_bridge" in p.read_text(errors="ignore") for p in c_matches)
        if not uses_bridge:
            issues.append(f"{module_dir.name}: 未检测到 native_log_bridge 引用")
    if verbose:
        print(f"C 扩展检查完成，缺失 {len(issues)} 项。")
    return issues


def run_smoke_tests(*, verbose: bool = False) -> List[str]:
    failures: List[str] = []
    collected: List[Dict[str, Any]] = []
    with capture_native_logs(collected, verbose=verbose):
        for module_name, spec in SMOKE_MODULES.items():
            try:
                module = importlib.import_module(f"{NATIVE_PACKAGE}.{module_name}")
            except Exception as exc:
                failures.append(f"{module_name}: 导入失败 -> {exc}")
                continue
            callable_name = spec["callable"]
            kwargs = spec.get("kwargs", {})
            func = getattr(module, callable_name, None)
            if func is None:
                failures.append(f"{module_name}: 缺少调用 {callable_name}")
                continue
            try:
                func(**kwargs)
            except Exception as exc:
                failures.append(f"{module_name}.{callable_name} 调用失败 -> {exc}")
    if not collected:
        failures.append("冒烟测试未捕获任何 native 日志")
    else:
        smoke_summary = json.dumps(collected[:3], ensure_ascii=False, indent=2)
        if verbose:
            print("捕获日志示例:\n" + smoke_summary)
    return failures


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="巡检 native 日志桥接与冒烟测试")
    parser.add_argument("--verbose", action="store_true", help="输出详细检查记录")
    args = parser.parse_args(list(argv) if argv is not None else None)

    problems: List[str] = []
    problems.extend(check_python_wrappers(verbose=args.verbose))
    problems.extend(check_c_extensions(verbose=args.verbose))
    problems.extend(run_smoke_tests(verbose=args.verbose))

    if problems:
        print(f"{FAIL} 巡检失败，共 {len(problems)} 项：")
        for item in problems:
            print(f" - {item}")
        return 1

    print(f"{PASS} 巡检通过：所有模块均检测到桥接，冒烟测试捕获日志。")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(main())
