import sys
import time

# Test native_socket_metrics
try:
    print("=== Testing native_socket_metrics ===")
    print("Step 1: Import module...")
    
    from backend.infrastructure.native.native_socket_metrics import (
        SOCKET_METRICS_AVAILABLE,
        get_socket_metrics,
    )
    
    print(f"Step 2: Check availability: {SOCKET_METRICS_AVAILABLE}")
    
    if SOCKET_METRICS_AVAILABLE:
        print("Step 3: Call get_socket_metrics()...")
        start = time.perf_counter()
        result = get_socket_metrics()
        elapsed_ms = (time.perf_counter() - start) * 1000
        
        print(f"Step 4: Success! Elapsed: {elapsed_ms:.2f}ms")
        print(f"  - TCP connections: {result.get('tcp_connections')}")
        print(f"  - Established: {result.get('established_connections')}")
        print(f"  - Recv buffer avg: {result.get('recv_buffer_size_avg')} bytes")
        print(f"  - Send buffer avg: {result.get('send_buffer_size_avg')} bytes")
        print(f" Test PASSED!")
    else:
        print(" C extension not available")
        
except Exception as e:
    print(f" Test FAILED: {e}")
    import traceback
    traceback.print_exc()
