# -*- coding: utf-8 -*-
"""
日志系统诊断脚本

验证server_pool_manager的logger是否能正常输出
"""

import logging


def test_logger_configuration():
    """测试logger配置"""
    print("=" * 70)
    print("日志系统诊断")
    print("=" * 70)

    # 测试1：tdx_asyncio logger（有自己的handler）
    from backend.infrastructure.tdx_asyncio.logger import logger as tdx_logger

    print(f"\n[测试1] tdx_asyncio logger:")
    print(f"  Name: {tdx_logger.name}")
    print(f"  Level: {tdx_logger.level}")
    print(f"  Handlers: {len(tdx_logger.handlers)}")
    for h in tdx_logger.handlers:
        print(f"    - {h.__class__.__name__}: Level={h.level}")
    tdx_logger.info("测试消息：tdx_asyncio logger 可以输出")

    # 测试2：server_pool_manager logger（没有自己的handler）
    spm_logger = logging.getLogger("backend.infrastructure.data_module_vnpy.server_pool_manager")
    print(f"\n[测试2] server_pool_manager logger:")
    print(f"  Name: {spm_logger.name}")
    print(f"  Level: {spm_logger.level}")
    print(f"  Handlers: {len(spm_logger.handlers)}")
    print(f"  Propagate: {spm_logger.propagate}")
    spm_logger.info("测试消息：server_pool_manager logger 能输出吗？")

    # 测试3：root logger
    root_logger = logging.getLogger()
    print(f"\n[测试3] root logger:")
    print(f"  Name: '{root_logger.name}'")
    print(f"  Level: {root_logger.level}")
    print(f"  Handlers: {len(root_logger.handlers)}")
    for h in root_logger.handlers:
        print(f"    - {h.__class__.__name__}: Level={h.level}")

    # 测试4：配置root logger后再测试
    print(f"\n[测试4] 配置root logger后:")
    if not root_logger.handlers:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)
        root_logger.setLevel(logging.INFO)
        print("  已添加console handler到root logger")

    spm_logger2 = logging.getLogger("backend.infrastructure.data_module_vnpy.server_pool_manager")
    spm_logger2.info("测试消息：现在server_pool_manager logger应该能输出了")

    print("\n" + "=" * 70)
    print("诊断完成")
    print("=" * 70)


if __name__ == "__main__":
    test_logger_configuration()
