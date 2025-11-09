# -*- coding: utf-8 -*-
"""
简单的阶段5测试
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from backend.infrastructure.native.logging_bridge import log_from_native, NativeLogLevel

print("Testing native logging bridge...")

try:
    log_from_native(
        NativeLogLevel.INFO,
        "test.stage5",
        "simple_test",
        1,
        "Stage 5 logging integration test",
        "details: native modules ready"
    )
    print("✓ Native logging bridge works!")
except Exception as e:
    print(f"✗ Native logging bridge failed: {e}")

# 测试native_rpc_bridge
try:
    from backend.infrastructure.native.native_rpc_bridge import create_request_header
    result = create_request_header(1, 1024)
    print(f"✓ RPC bridge works: {result}")
except Exception as e:
    print(f"✗ RPC bridge failed: {e}")

# 测试native_serialization
try:
    from backend.infrastructure.native.native_serialization import batch_serialize
    result = batch_serialize([1, 2, 3])
    print(f"✓ Serialization works: {len(result)} items")
except Exception as e:
    print(f"✗ Serialization failed: {e}")

print("Stage 5 integration test completed.")
